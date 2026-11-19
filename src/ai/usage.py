"""Collects token-usage hints for one AI request, without changing any call signature.

Exact usage is taken from the provider response when it reports it. Otherwise the
caller falls back to an estimate (see src/services/ai_quota_service.py).
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

_sink: ContextVar[dict | None] = ContextVar("latz_ai_usage_sink", default=None)


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def provider_total_tokens(obj: Any) -> int | None:
    """total_tokens reported on a response or stream chunk (OpenAI-style `usage`,
    or Groq's `x_groq.usage`), or None when the provider reported nothing usable."""
    usage = getattr(obj, "usage", None)
    if usage is None:
        usage = getattr(getattr(obj, "x_groq", None), "usage", None)
    return _int_or_none(getattr(usage, "total_tokens", None))


def prompt_chars(messages: list[dict]) -> int:
    return sum(len(str(m.get("content") or "")) for m in messages)


@contextmanager
def collect_usage() -> Iterator[dict]:
    """Collect usage for the non-streaming path. Must be entered and left in the same thread."""
    sink: dict = {}
    token = _sink.set(sink)
    try:
        yield sink
    finally:
        _sink.reset(token)


def note_prompt(messages: list[dict]) -> None:
    sink = _sink.get()
    if sink is not None:
        sink["prompt_chars"] = sink.get("prompt_chars", 0) + prompt_chars(messages)


def note_response(response: Any) -> None:
    """Add one model call's reported usage (summed over tool-calling rounds)."""
    sink = _sink.get()
    if sink is None:
        return
    total = provider_total_tokens(response)
    if total is not None:
        sink["provider_tokens"] = sink.get("provider_tokens", 0) + total
