"""In-process sliding-window rate limiting and client-address resolution.

Scope and limits (be honest about them):
- State lives in this process's memory. It is correct for the single-instance,
  single-worker Render deployment this project targets. It is NOT shared between
  processes or instances and it resets on restart or redeploy.
- Keys are client addresses or user ids, never credentials. A login key never
  contains the submitted username or password, so a limit response is identical
  whether or not an account exists.
"""

import hashlib
import ipaddress
import logging
import math
import threading
import time
from collections import OrderedDict, deque
from typing import Callable

from fastapi import HTTPException, Request

from src.config.settings import settings

logger = logging.getLogger("AIEngineeringLab.rate_limit")

WINDOW_SECONDS = 60.0
MAX_TRACKED_KEYS = 10_000
RATE_LIMIT_DETAIL = "Too many requests. Please wait a moment and try again."


class SlidingWindowLimiter:
    """Allow at most `limit` hits per key in any `window` seconds.

    Rejected hits are not recorded, so a blocked client is released as soon as its
    oldest recorded hit leaves the window instead of being kept blocked by retries.
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = MAX_TRACKED_KEYS,
    ) -> None:
        self._clock = clock
        self._max_keys = max_keys
        self._hits: "OrderedDict[str, deque[float]]" = OrderedDict()
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float = WINDOW_SECONDS) -> tuple[bool, int]:
        """Record an attempt. Returns (allowed, retry_after_seconds); retry_after is 0 when allowed."""
        now = self._clock()
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                self._make_room()
                hits = self._hits[key] = deque()
            else:
                self._hits.move_to_end(key)
            while hits and now - hits[0] >= window:
                hits.popleft()
            if len(hits) >= limit:
                return False, max(1, math.ceil(window - (now - hits[0])))
            hits.append(now)
            return True, 0

    def _make_room(self) -> None:
        # Bound memory when many distinct keys arrive. Drop the least recently used key.
        while len(self._hits) >= self._max_keys:
            self._hits.popitem(last=False)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def tracked_keys(self) -> list[str]:
        with self._lock:
            return list(self._hits)


limiter = SlidingWindowLimiter()


def reset_rate_limits() -> None:
    limiter.reset()


def _single_header_value(request: Request, name: str) -> str | None:
    """The one value of header `name`, or None unless exactly one usable value is present.

    A repeated header (several lines) is never a platform edge's doing, so it is not
    trusted and not guessed at (neither the first nor the last line is picked). An
    empty or whitespace-only value is also treated as absent. Parsing and validation
    of the address itself happen in get_client_ip.
    """
    values = request.headers.getlist(name)
    if len(values) != 1:
        return None
    value = values[0].strip()
    # "%" would be an IPv6 zone id (fe80::1%eth0): not a client address, and it would
    # break the /64 reduction below.
    if not value or "%" in value:
        return None
    return value


def get_client_ip(request: Request) -> str:
    """Best-effort client address for rate limiting.

    TRUSTED_CLIENT_IP_HEADER = "x-real-ip" (explicit opt-in, Railway): the address in
    exactly one X-Real-IP header, which the platform's public HTTP edge overwrites on
    every request. A missing, empty, repeated or non-IP value falls back to the socket
    peer address. X-Forwarded-For is never consulted in this mode, and
    TRUSTED_PROXY_COUNT is ignored. Only safe when the edge is the app's sole ingress.

    Otherwise TRUSTED_PROXY_COUNT = 0 (default): the socket peer address; X-Forwarded-For
    is ignored because any client can send it. N > 0: the Nth entry from the right of
    X-Forwarded-For, i.e. the one written by your own proxy chain. Entries to its
    left are client-supplied and ignored. Anything malformed or too short falls back
    to the peer address. IPv6 addresses are reduced to their /64 so one host cannot
    rotate through its own prefix.
    """
    peer = request.client.host if request.client else "unknown"
    candidate = peer

    count = settings.TRUSTED_PROXY_COUNT
    if settings.TRUSTED_CLIENT_IP_HEADER == "x-real-ip":
        candidate = _single_header_value(request, "x-real-ip") or peer
    elif count > 0:
        # Repeated header lines are one list (a proxy may append a new line instead of extending one).
        joined = ",".join(request.headers.getlist("x-forwarded-for"))
        parts = [p.strip() for p in joined.split(",") if p.strip()]
        if len(parts) >= count:
            candidate = parts[-count]

    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        try:
            ip = ipaddress.ip_address(peer)
        except ValueError:
            return "unknown"
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped  # ::ffff:1.2.3.4 and 1.2.3.4 are the same client
    if ip.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False).network_address)
    return str(ip)


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:10]


def enforce(scope: str, subject: str, limit: int) -> None:
    """Raise HTTP 429 with Retry-After when `subject` exceeded `limit` hits per minute in `scope`."""
    allowed, retry_after = limiter.hit(f"{scope}:{subject}", limit)
    if allowed:
        return
    # Operational signal without the raw address or any credential.
    logger.warning("rate limit exceeded scope=%s subject=%s retry_after=%ds", scope, _short_hash(subject), retry_after)
    raise HTTPException(
        status_code=429,
        detail=RATE_LIMIT_DETAIL,
        headers={"Retry-After": str(retry_after)},
    )


def limit_login(request: Request) -> None:
    """Route dependency for POST /auth/login. Runs before any account lookup or password hashing."""
    enforce("login", get_client_ip(request), settings.RATE_LIMIT_AUTH_PER_MINUTE)


def limit_register(request: Request) -> None:
    """Route dependency for POST /auth/register (same per-minute limit, separate counter)."""
    enforce("register", get_client_ip(request), settings.RATE_LIMIT_AUTH_PER_MINUTE)


def limit_ai_for_user(user_id: int) -> None:
    """Per-user per-minute limit shared by /ai/chat and /ai/chat/stream."""
    enforce("ai", str(user_id), settings.RATE_LIMIT_AI_PER_MINUTE)


def limit_account_change(user_id: int) -> None:
    """Per-account limit for password change and account deletion (both re-check the
    password, so this bounds guessing by a holder of a stolen token)."""
    enforce("account-change", str(user_id), settings.RATE_LIMIT_AUTH_PER_MINUTE)
