"""Daily AI request and token quotas, stored in the database (table ai_usage_daily).

Design
- One counter row per (scope, UTC day): scope "global" and scope "user:<id>".
- A request is admitted by ONE conditional UPDATE per row
  (`... WHERE requests < limit`). The database applies each UPDATE atomically, so
  concurrent requests, even from different worker processes, cannot slip past a
  limit by checking and then writing separately. Rows are locked in a fixed order
  (user row, then global row) and the transaction is short.
- Tokens are RESERVED up front with a conservative estimate, then SETTLED to the
  measured value when the request finishes, or RELEASED (request and tokens
  refunded) when it failed without producing any output.

How tokens are measured
1. If the provider reports usage on the response (non-streaming) or on a stream
   chunk, that exact `total_tokens` is used.
2. Otherwise tokens are ESTIMATED as characters / 4 over the prompt that was sent
   plus the text that was generated. This is the usual rule of thumb for English
   text; code and non-Latin scripts tokenize differently, so treat the number as
   approximate. The estimate is not exact and can be off by a wide margin.
3. Non-streaming requests can make several model calls (tool rounds). When the
   provider does not report usage, only the first prompt is counted, so such
   requests can be under-counted.

Limits of this design
- No per-user token limit exists in the configuration, only a global one.
- The global token limit is NOT a strict hard cap. Reservations are checked
  atomically, but settlement replaces the reservation with the measured value, which
  can be larger (tool rounds, long prompts, estimate error). Each in-flight request
  can therefore push the total past the limit by the amount its usage exceeded its
  reservation. The request-count limits (per user and global) are exact.
- If settlement or refund fails with a DEFINITE error (the statement was rejected, the
  connection was refused or dropped before COMMIT was sent) the reservation stays
  counted: usage is over-counted rather than lost, and the call can be retried.
- A commit exception can also be AMBIGUOUS: the server may have committed and only the
  acknowledgement was lost. The code cannot tell the two apart, treats it as failed and
  may retry, so in that rare case the adjustment can be applied twice. For a settle that
  can under-count by up to (reserved - actual) tokens; for a release it can refund one
  request and the reserved tokens twice. Settlement is therefore NOT exactly-once under
  that failure mode. Exactly-once would need a durable idempotency record (for example
  a per-reservation row written in the same transaction), which is deliberately not
  implemented here.
- Day boundaries are UTC. The counters reset at 00:00 UTC.
"""

import enum
import logging
import math
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.models.ai_usage import AiUsageDaily
from src.models.user import User

logger = logging.getLogger("AIEngineeringLab.quota")

GLOBAL_SCOPE = "global"
CHARS_PER_TOKEN = 4
# Conservative allowance for the system prompt, context, memories and history.
RESERVED_INPUT_TOKENS = 4000
# Output cap for the non-streaming path (tool_calling_service uses max_tokens=1200).
CHAT_OUTPUT_TOKENS = 1200


class QuotaExceeded(Exception):
    """A daily quota is exhausted. `scope` is "user" or "global"."""

    def __init__(self, scope: str, retry_after: int) -> None:
        super().__init__(f"{scope} AI quota exhausted")
        self.scope = scope
        self.retry_after = retry_after

    @property
    def detail(self) -> str:
        if self.scope == "user":
            return "Your daily AI request limit has been reached. It resets at 00:00 UTC."
        return "The shared daily AI capacity has been reached. It resets at 00:00 UTC."


class UserGone(Exception):
    """The account was deleted while the request was in flight. No counter row is created
    for it (that would leave an orphaned `user:<id>` row behind)."""


class Settlement(enum.Enum):
    """Result of settle()/release(): tells a new application from a repeat call."""

    APPLIED = "applied"  # this call changed the counters and committed
    ALREADY_FINISHED = "already_finished"  # an earlier call already finished it; nothing changed
    FAILED = "failed"  # not committed; the reservation stays counted and may be retried


@dataclass
class QuotaReservation:
    user_scope: str
    day: date
    reserved_tokens: int
    # True only once settle()/release() COMMITTED. A failed commit leaves it False, so the
    # reservation stays counted (conservative: no bypass) and the call can be retried.
    finished: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def seconds_until_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return max(1, math.ceil((tomorrow - now).total_seconds()))


def estimate_tokens(text_chars: int) -> int:
    return math.ceil(max(0, text_chars) / CHARS_PER_TOKEN)


def reservation_tokens(max_output_tokens: int) -> int:
    return RESERVED_INPUT_TOKENS + max_output_tokens


def measured_tokens(info: dict, output_chars: int) -> int:
    """Provider-reported tokens when available, otherwise the chars/4 estimate."""
    reported = info.get("provider_tokens")
    if isinstance(reported, int) and reported > 0:
        return reported
    return estimate_tokens(info.get("prompt_chars", 0) + output_chars)


def _ensure_row(db: Session, scope: str, day: date) -> None:
    values = {"scope": scope, "usage_date": day, "requests": 0, "tokens": 0}
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover - only PostgreSQL and SQLite are supported
        raise RuntimeError(f"Unsupported database dialect for AI quotas: {dialect}")
    db.execute(
        insert(AiUsageDaily)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["scope", "usage_date"])
    )


def _adjust(db: Session, scope: str, day: date, requests: int, tokens: int) -> None:
    """Apply a relative change to one counter row (used by settle and release)."""
    db.execute(
        update(AiUsageDaily)
        .where(AiUsageDaily.scope == scope, AiUsageDaily.usage_date == day)
        .values(
            requests=AiUsageDaily.requests + requests,
            tokens=AiUsageDaily.tokens + tokens,
        )
    )


def reserve(db: Session, user_id: int, tokens: int) -> QuotaReservation:
    """Atomically admit one request or raise QuotaExceeded. Commits on success."""
    day = utc_today()
    user_scope = f"user:{user_id}"
    try:
        # Account deletion removes the user's counter rows and then the user, in one
        # transaction. Taking a shared lock on the user row here makes the two serialise on
        # PostgreSQL: a deletion in flight waits for this reservation to commit (and then
        # removes the row we create), and a deletion that already committed is seen here, so
        # no counter row is ever created for an account that no longer exists.
        # (SQLite has no row locks; it serialises whole writes, and the existence check holds.)
        if db.execute(select(User.id).where(User.id == user_id).with_for_update(read=True)).first() is None:
            db.rollback()
            raise UserGone()
        _ensure_row(db, user_scope, day)
        _ensure_row(db, GLOBAL_SCOPE, day)

        user_admitted = db.execute(
            update(AiUsageDaily)
            .where(
                AiUsageDaily.scope == user_scope,
                AiUsageDaily.usage_date == day,
                AiUsageDaily.requests < settings.AI_DAILY_REQUESTS_PER_USER,
            )
            .values(requests=AiUsageDaily.requests + 1, tokens=AiUsageDaily.tokens + tokens)
        ).rowcount
        if user_admitted != 1:
            db.rollback()
            raise QuotaExceeded("user", seconds_until_utc_midnight())

        global_admitted = db.execute(
            update(AiUsageDaily)
            .where(
                AiUsageDaily.scope == GLOBAL_SCOPE,
                AiUsageDaily.usage_date == day,
                AiUsageDaily.requests < settings.AI_DAILY_REQUESTS_GLOBAL,
                AiUsageDaily.tokens + tokens <= settings.AI_DAILY_TOKENS_GLOBAL,
            )
            .values(requests=AiUsageDaily.requests + 1, tokens=AiUsageDaily.tokens + tokens)
        ).rowcount
        if global_admitted != 1:
            db.rollback()  # also undoes the user-row increment above
            raise QuotaExceeded("global", seconds_until_utc_midnight())

        db.commit()
    except (QuotaExceeded, UserGone):
        raise
    except Exception:
        db.rollback()
        raise
    return QuotaReservation(user_scope=user_scope, day=day, reserved_tokens=tokens)


def _finish(db: Session, reservation: QuotaReservation, requests: int, token_delta: int, what: str) -> Settlement:
    """Apply one relative change to the user and global rows, at most once per success.

    The per-reservation lock serialises concurrent calls, and `finished` is set only
    after the commit returned, so after a definite failure the call can be retried and
    after success a second call is ALREADY_FINISHED (never a double settle or refund).
    On failure the reservation simply stays counted. Only the exception class is logged:
    provider and database messages can echo request details.

    Limit: if COMMIT raises although the server committed (lost acknowledgement) the
    outcome is ambiguous; this code treats it as failed and a retry would apply the
    change again. See the module docstring: settlement is not exactly-once in that case.
    """
    with reservation._lock:
        if reservation.finished:
            return Settlement.ALREADY_FINISHED
        try:
            _adjust(db, reservation.user_scope, reservation.day, requests, token_delta)
            _adjust(db, GLOBAL_SCOPE, reservation.day, requests, token_delta)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
            logger.error("could not %s AI quota reservation (%s); it stays counted", what, type(exc).__name__)
            return Settlement.FAILED
        reservation.finished = True
        return Settlement.APPLIED


def settle(db: Session, reservation: QuotaReservation, actual_tokens: int) -> Settlement:
    """Replace the reserved tokens by the measured value. The request stays counted.

    The measured value may exceed the reservation (tool rounds, longer prompts): the
    global token limit is therefore approximate, see the module docstring. The overshoot
    warning is logged only when THIS call applied the settlement.
    """
    actual = max(0, actual_tokens)
    delta = actual - reservation.reserved_tokens
    result = _finish(db, reservation, 0, delta, "settle")
    if result is Settlement.APPLIED and delta > 0:
        logger.warning("AI usage exceeded its reservation by %d tokens", delta)
    return result


def release(db: Session, reservation: QuotaReservation) -> Settlement:
    """Refund a request that failed without producing output (request and tokens)."""
    return _finish(db, reservation, -1, -reservation.reserved_tokens, "release")
