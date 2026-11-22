"""The quota's atomic admission must also hold on PostgreSQL (the production database).

Runs only when LATZ_TEST_PG_ADMIN_URL names a disposable loopback server, exactly like
tests/test_migrations.py, and uses its throwaway-database helpers.
"""

import threading

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.database.base import Base
from src.models import User
from src.services import ai_quota_service as quota
from test_migrations import ADMIN_URL, _create_throwaway_db, _drop_throwaway_db, validate_admin_url


@pytest.fixture
def pg_engine():
    if not ADMIN_URL:
        pytest.skip("LATZ_TEST_PG_ADMIN_URL not set")
    validate_admin_url(ADMIN_URL)
    name, url = _create_throwaway_db(ADMIN_URL)
    import src.models  # noqa: F401

    engine = create_engine(url, pool_size=25)
    Base.metadata.create_all(engine)
    with Session(bind=engine) as s:  # reserve() requires the account to exist
        s.add_all(User(id=i, username=f"q{i}", email=f"q{i}@example.com", hashed_password="x") for i in range(1, 26))
        s.commit()
    try:
        yield engine
    finally:
        engine.dispose()
        _drop_throwaway_db(ADMIN_URL, name)


def _race(engine, user_ids):
    outcomes, lock, barrier = [], threading.Lock(), threading.Barrier(len(user_ids))

    def worker(uid):
        with Session(bind=engine) as s:
            barrier.wait()
            try:
                quota.reserve(s, uid, 100)
                result = "ok"
            except quota.QuotaExceeded as exc:
                result = exc.scope
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=worker, args=(u,)) for u in user_ids]
    [t.start() for t in threads]
    [t.join(60) for t in threads]
    return outcomes


def _count(engine, scope):
    with engine.connect() as c:
        return c.execute(text("select requests from ai_usage_daily where scope=:s"), {"s": scope}).scalar()


def test_postgres_per_user_limit_holds_under_concurrency(pg_engine, monkeypatch):
    monkeypatch.setattr(settings, "AI_DAILY_REQUESTS_PER_USER", 5)
    monkeypatch.setattr(settings, "AI_DAILY_REQUESTS_GLOBAL", 1000)
    monkeypatch.setattr(settings, "AI_DAILY_TOKENS_GLOBAL", 10_000_000)
    outcomes = _race(pg_engine, [1] * 20)
    assert outcomes.count("ok") == 5 and outcomes.count("user") == 15
    assert _count(pg_engine, "user:1") == 5


def test_postgres_global_limit_holds_under_concurrency_without_deadlock(pg_engine, monkeypatch):
    monkeypatch.setattr(settings, "AI_DAILY_REQUESTS_PER_USER", 100)
    monkeypatch.setattr(settings, "AI_DAILY_REQUESTS_GLOBAL", 4)
    monkeypatch.setattr(settings, "AI_DAILY_TOKENS_GLOBAL", 10_000_000)
    outcomes = _race(pg_engine, list(range(1, 21)))
    assert outcomes.count("ok") == 4 and outcomes.count("global") == 16
    assert _count(pg_engine, quota.GLOBAL_SCOPE) == 4
    # Rejected users' increments were rolled back with their failed admission.
    with pg_engine.connect() as c:
        assert c.execute(text("select coalesce(sum(requests),0) from ai_usage_daily where scope like 'user:%'")).scalar() == 4
