"""Process-local limit on concurrent streaming AI responses.

Per-process and in memory: it resets on restart and is not shared between worker
processes or instances.

Slots are leased so that a slot whose owner vanished without releasing it (a client
that aborted before the stream started, a hung provider call) is reclaimed instead of
staying occupied forever. The lease is an IDLE lease: `renew()` (called for every
streamed chunk) restarts it, so a legitimately long stream that keeps producing output
never loses its slot. Two limits remain, and the cap is only as strong as they are:

- A stream silent for longer than `lease_seconds` is treated as dead and its slot may
  be handed to another stream, so for that stalled stream the cap can be exceeded.
  renew() then reports False and the stream stops.
- A slot cannot be held longer than `max_stream_seconds` in total, however active it
  is; renew() reports False once that is exceeded and the stream stops.
"""

import itertools
import logging
import threading
import time
from typing import Callable

logger = logging.getLogger("AIEngineeringLab.streams")

# Idle time (no chunk) after which a slot is considered abandoned.
DEFAULT_LEASE_SECONDS = 300.0
# Absolute ceiling on one stream (output is capped at 2,500 tokens; normal streams take seconds).
DEFAULT_MAX_STREAM_SECONDS = 600.0


class StreamSlot:
    """A held concurrency slot. release() is idempotent and safe from any thread."""

    def __init__(self, limiter: "StreamLimiter", slot_id: int) -> None:
        self._limiter = limiter
        self._id = slot_id

    def renew(self) -> bool:
        """Restart the idle lease. False means the slot is gone (expired or over the
        maximum duration) and the caller must stop streaming."""
        return self._limiter._renew(self._id)

    def release(self) -> None:
        self._limiter._release(self._id)


class StreamLimiter:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        max_stream_seconds: float = DEFAULT_MAX_STREAM_SECONDS,
    ) -> None:
        self._clock = clock
        self._lease = lease_seconds
        self._max = max_stream_seconds
        self._held: dict[int, list[float]] = {}  # id -> [started, last_seen]
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def acquire(self, max_slots: int) -> StreamSlot | None:
        """Take a slot, or return None when `max_slots` streams are already running."""
        now = self._clock()
        with self._lock:
            expired = [i for i, (_, seen) in self._held.items() if now - seen >= self._lease]
            for slot_id in expired:
                del self._held[slot_id]
            if expired:
                logger.warning("reclaimed %d idle stream slot(s)", len(expired))
            if len(self._held) >= max_slots:
                return None
            slot_id = next(self._ids)
            self._held[slot_id] = [now, now]
            return StreamSlot(self, slot_id)

    def _renew(self, slot_id: int) -> bool:
        now = self._clock()
        with self._lock:
            entry = self._held.get(slot_id)
            if entry is None:
                return False  # already reclaimed or released
            started, seen = entry
            if now - seen >= self._lease or now - started >= self._max:
                del self._held[slot_id]
                logger.warning("stream slot ended: idle lease or maximum duration exceeded")
                return False
            entry[1] = now
            return True

    def _release(self, slot_id: int) -> None:
        with self._lock:
            self._held.pop(slot_id, None)

    def active(self) -> int:
        with self._lock:
            return len(self._held)

    def reset(self) -> None:
        with self._lock:
            self._held.clear()


stream_limiter = StreamLimiter()
