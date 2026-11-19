import pytest

from src.security.rate_limit import reset_rate_limits
from src.security.stream_limiter import stream_limiter


@pytest.fixture(autouse=True)
def reset_in_memory_security_state():
    """Rate-limit counters and stream slots live in process memory by design.
    Reset them around every test so tests cannot affect each other."""
    reset_rate_limits()
    stream_limiter.reset()
    yield
    reset_rate_limits()
    stream_limiter.reset()
