"""Per-user stream concurrency over HTTP: several independent real accounts, real JWTs,
real concurrent requests against a file-backed SQLite database."""
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.api.routes.ai as ai_routes
from src.api.main import app
from src.auth.hash import hash_password
from src.config.settings import settings
from src.database.base import Base
from src.database.session import get_db
from src.models import AiUsageDaily, User
from src.security.stream_limiter import stream_limiter

NAMES = ["alice", "bob", "carol", "dave"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'f.db'}", connect_args={"check_same_thread": False, "timeout": 30})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with Session() as s:
        for n in NAMES:
            s.add(User(username=n, email=f"{n}@example.com", hashed_password=hash_password(f"{n.title()}-Test-Password-1")))
        s.commit()

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    for key, value in {
        "AI_ENABLED": True, "AI_MAX_CONCURRENT_STREAMS": 3, "AI_MAX_CONCURRENT_STREAMS_PER_USER": 1,
        "RATE_LIMIT_AI_PER_MINUTE": 1000, "AI_DAILY_REQUESTS_PER_USER": 100,
        "AI_DAILY_REQUESTS_GLOBAL": 1000, "AI_DAILY_TOKENS_GLOBAL": 10_000_000,
    }.items():
        monkeypatch.setattr(settings, key, value)
    stream_limiter.reset()
    client = TestClient(app, raise_server_exceptions=False)
    tokens = {}
    for n in NAMES:
        r = client.post("/auth/login", data={"username": n, "password": f"{n.title()}-Test-Password-1"})
        assert r.status_code == 200, r.text
        tokens[n] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    yield client, tokens, Session
    stream_limiter.reset()
    app.dependency_overrides.clear()
    engine.dispose()


def run_stream(headers, results, key, calls=None):
    r = TestClient(app, raise_server_exceptions=False).post("/ai/chat/stream", json={"message": "hi"}, headers=headers)
    results[key] = r


def wait_active(n, timeout=10):
    deadline = time.time() + timeout
    while stream_limiter.active() < n and time.time() < deadline:
        time.sleep(0.02)
    return stream_limiter.active()


def gated_provider(monkeypatch, gate, calls):
    def stream(outcome=None, **kwargs):
        calls.append(1)
        yield "start "
        gate.wait(15)
        yield "end"
        outcome["finish_reason"] = "stop"

    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", stream)


def test_one_user_cannot_hold_a_second_stream_and_it_costs_nothing(env, monkeypatch):
    client, tokens, Session = env
    gate, calls, results = threading.Event(), [], {}
    gated_provider(monkeypatch, gate, calls)
    t = threading.Thread(target=run_stream, args=(tokens["alice"], results, "a1"))
    t.start()
    assert wait_active(1) == 1
    r = client.post("/ai/chat/stream", json={"message": "again"}, headers=tokens["alice"])
    assert r.status_code == 429 and "already have an AI response" in r.json()["detail"]
    assert r.headers["retry-after"]
    assert len(calls) == 1  # the provider was never called for the rejected request
    with Session() as s:
        alice = s.query(User).filter_by(username="alice").one()
        row = s.query(AiUsageDaily).filter_by(scope=f"user:{alice.id}").one()
        assert row.requests == 1  # only the running stream is reserved
    gate.set()
    t.join(20)
    assert results["a1"].status_code == 200
    assert stream_limiter.active() == 0
    # Finished: alice can stream again.
    gate.set()
    assert client.post("/ai/chat/stream", json={"message": "later"}, headers=tokens["alice"]).status_code == 200


def test_other_users_keep_their_allocation_while_one_user_streams(env, monkeypatch):
    client, tokens, _ = env
    gate, calls, results = threading.Event(), [], {}
    gated_provider(monkeypatch, gate, calls)
    threads = [threading.Thread(target=run_stream, args=(tokens[n], results, n)) for n in ("alice", "bob", "carol")]
    # alice hammers first; she still only ever holds one slot
    greedy = [threading.Thread(target=run_stream, args=(tokens["alice"], results, f"alice-extra-{i}")) for i in range(4)]
    threads[0].start()
    assert wait_active(1) == 1
    [g.start() for g in greedy]
    [g.join(20) for g in greedy]
    assert all(results[f"alice-extra-{i}"].status_code == 429 for i in range(4))
    assert stream_limiter.active() == 1
    threads[1].start(); threads[2].start()
    assert wait_active(3) == 3  # bob and carol got their slots despite alice's attempts
    # global cap of 3 still holds for a fourth independent user
    r = client.post("/ai/chat/stream", json={"message": "x"}, headers=tokens["dave"])
    assert r.status_code == 429 and "Too many AI responses" in r.json()["detail"]
    gate.set()
    [t.join(20) for t in threads]
    assert [results[n].status_code for n in ("alice", "bob", "carol")] == [200, 200, 200]
    assert stream_limiter.active() == 0
    assert client.post("/ai/chat/stream", json={"message": "x"}, headers=tokens["dave"]).status_code == 200


@pytest.mark.parametrize("failure", ["midstream", "immediate"])
def test_user_slot_is_free_again_after_a_provider_failure(env, monkeypatch, failure):
    client, tokens, _ = env

    def broken(outcome=None, **kwargs):
        if failure == "immediate":
            raise RuntimeError("provider down")
        yield "partial"
        raise RuntimeError("provider died")

    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", broken)
    assert client.post("/ai/chat/stream", json={"message": "x"}, headers=tokens["bob"]).status_code == 200
    assert stream_limiter.active() == 0
    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", lambda outcome=None, **kw: iter(["ok"]))
    assert client.post("/ai/chat/stream", json={"message": "y"}, headers=tokens["bob"]).status_code == 200


def test_a_quota_rejection_does_not_pin_the_users_slot(env, monkeypatch):
    client, tokens, _ = env
    monkeypatch.setattr(settings, "AI_DAILY_REQUESTS_PER_USER", 1)
    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", lambda outcome=None, **kw: iter(["ok"]))
    assert client.post("/ai/chat/stream", json={"message": "x"}, headers=tokens["carol"]).status_code == 200
    assert client.post("/ai/chat/stream", json={"message": "y"}, headers=tokens["carol"]).status_code == 429
    assert stream_limiter.active() == 0
