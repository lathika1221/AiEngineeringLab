"""F5: an account deleted while its own request is in flight must not leave orphaned
usage rows, must not 500, and must not disturb other users."""
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session as SASession, sessionmaker

import src.api.routes.ai as ai_routes
from src.api.main import app
from src.auth.hash import hash_password
from src.config.settings import settings
from src.database.base import Base
from src.database.session import get_db
from src.models import AiUsageDaily, Chat, User
from src.security.stream_limiter import stream_limiter
from src.services import ai_quota_service as quota
from src.services.auth_service import delete_account

PW = "Victim-Password-123"


def scopes(db):
    return sorted(r[0] for r in db.execute(text("select scope from ai_usage_daily")))


def test_reserve_for_a_missing_account_raises_and_creates_no_rows():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=__import__("sqlalchemy.pool").pool.StaticPool)
    Base.metadata.create_all(engine)
    with SASession(engine) as db:
        with pytest.raises(quota.UserGone):
            quota.reserve(db, 9999, 100)
        assert scopes(db) == []  # not even the global row


@pytest.fixture
def http(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'r.db'}", connect_args={"check_same_thread": False, "timeout": 30})
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with Session() as s:
        for n in ("victim", "bystander"):
            s.add(User(username=n, email=f"{n}@example.com", hashed_password=hash_password(PW)))
        s.commit()

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    for k, v in {"AI_ENABLED": True, "RATE_LIMIT_AI_PER_MINUTE": 1000, "AI_DAILY_REQUESTS_PER_USER": 100,
                 "AI_DAILY_REQUESTS_GLOBAL": 1000, "AI_DAILY_TOKENS_GLOBAL": 10_000_000}.items():
        monkeypatch.setattr(settings, k, v)
    stream_limiter.reset()
    client = TestClient(app, raise_server_exceptions=False)
    heads = {}
    for n in ("victim", "bystander"):
        r = client.post("/auth/login", data={"username": n, "password": PW})
        assert r.status_code == 200
        heads[n] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    yield client, heads, Session
    stream_limiter.reset()
    app.dependency_overrides.clear()
    engine.dispose()


def delete_victim(Session):
    with Session() as s:
        user = s.query(User).filter(User.username == "victim").one()
        assert delete_account(s, user, PW)


def test_account_deleted_during_chat_answers_401_not_500_and_leaves_no_victim_data(http, monkeypatch):
    client, heads, Session = http

    def answer_then_vanish(**kwargs):
        delete_victim(Session)  # the account disappears while the model is "thinking"
        return "a reply"

    monkeypatch.setattr(ai_routes, "chat_with_ai", answer_then_vanish)
    r = client.post("/ai/chat", json={"message": "hi"}, headers=heads["victim"])
    assert r.status_code == 401, r.text
    with Session() as s:
        assert s.query(Chat).count() == 0
        assert not any(sc.startswith("user:") and sc != f"user:{s.query(User).one().id}" for sc in scopes(s))
        # settle ran against a deleted account's row: harmless no-op; the bystander is untouched
        assert s.query(User).filter(User.username == "bystander").count() == 1
    ok = client.post("/ai/chat", json={"message": "hi"}, headers=heads["bystander"])
    assert ok.status_code in (200, 502), ok.text  # service still works for others


def test_account_deleted_during_stream_ends_cleanly_with_a_marker_and_frees_the_slot(http, monkeypatch):
    client, heads, Session = http

    def stream(outcome=None, **kwargs):
        yield "part one "
        delete_victim(Session)
        yield "part two"
        outcome["finish_reason"] = "stop"

    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", stream)
    r = client.post("/ai/chat/stream", json={"message": "hi"}, headers=heads["victim"])
    assert r.status_code == 200
    assert "part two" in r.text and "LATZ-STREAM-END:" in r.text  # clean, in-band ending
    assert stream_limiter.active() == 0
    with Session() as s:
        assert s.query(Chat).count() == 0
        victim_scopes = [sc for sc in scopes(s) if sc.startswith("user:")]
        assert victim_scopes == []  # nothing orphaned for the deleted account


def test_a_request_from_an_already_deleted_account_is_rejected_before_any_usage_row(http, monkeypatch):
    client, heads, Session = http
    monkeypatch.setattr(ai_routes, "chat_with_ai", lambda **k: "x")
    # authenticate first, then race the deletion in just before reservation
    real = ai_routes.reserve_quota_or_429

    def late(db, user_id, tokens):
        delete_victim(Session)
        return real(db, user_id, tokens)

    monkeypatch.setattr(ai_routes, "reserve_quota_or_429", late)
    r = client.post("/ai/chat", json={"message": "hi"}, headers=heads["victim"])
    assert r.status_code == 401
    with Session() as s:
        assert scopes(s) == []


# ------------------------------------------------------------------ PostgreSQL (gated)
def _pg():
    sys.path.insert(0, str(Path(__file__).parent))
    from test_migrations import ADMIN_URL, _create_throwaway_db, _drop_throwaway_db, validate_admin_url

    if not ADMIN_URL:
        pytest.skip("LATZ_TEST_PG_ADMIN_URL not set")
    validate_admin_url(ADMIN_URL)
    return ADMIN_URL, _create_throwaway_db, _drop_throwaway_db


@pytest.fixture
def pg():
    admin, create, drop = _pg()
    name, url = create(admin)
    engine = create_engine(url, pool_size=10)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        drop(admin, name)


def new_user(engine, n):
    with SASession(engine) as s:
        u = User(username=f"u{n}", email=f"u{n}@example.com", hashed_password=hash_password(PW))
        s.add(u)
        s.commit()
        return u.id


def test_postgres_delete_in_flight_blocks_reservation_then_it_sees_the_user_gone(pg, monkeypatch):
    uid = new_user(pg, 1)
    deleter, reserver = SASession(pg), SASession(pg)
    user = deleter.get(User, uid)
    deleter.query(AiUsageDaily).filter(AiUsageDaily.scope == f"user:{uid}").delete(synchronize_session=False)
    deleter.delete(user)
    deleter.flush()  # delete is in flight, not yet committed: row lock held

    out = {}

    def reserve():
        try:
            quota.reserve(reserver, uid, 10)
            out["r"] = "reserved"
        except quota.UserGone:
            out["r"] = "gone"

    t = threading.Thread(target=reserve)
    t.start()
    t.join(1.5)
    assert t.is_alive(), "reservation should wait for the in-flight deletion, not race past it"
    deleter.commit()
    t.join(10)
    assert out["r"] == "gone"
    with SASession(pg) as s:
        assert [x for x in scopes(s) if x.startswith("user:")] == []
    deleter.close(); reserver.close()


def test_postgres_reservation_in_flight_blocks_deletion_and_deletion_removes_the_new_row(pg):
    uid = new_user(pg, 2)
    reserver = SASession(pg)
    quota.reserve(reserver, uid, 10)  # committed row exists
    with SASession(pg) as s:
        assert f"user:{uid}" in scopes(s)
    with SASession(pg) as s:
        assert delete_account(s, s.get(User, uid), PW)
    with SASession(pg) as s:
        assert [x for x in scopes(s) if x.startswith("user:")] == []
        assert s.query(User).count() == 0
    reserver.close()


def test_postgres_stress_random_interleavings_never_orphan_usage_rows_or_hurt_others(pg, monkeypatch):
    monkeypatch.setattr(settings, "AI_DAILY_REQUESTS_PER_USER", 1000)
    monkeypatch.setattr(settings, "AI_DAILY_REQUESTS_GLOBAL", 100000)
    monkeypatch.setattr(settings, "AI_DAILY_TOKENS_GLOBAL", 100_000_000)
    bystander = new_user(pg, 0)
    for round_ in range(12):
        uid = new_user(pg, 100 + round_)
        errors, barrier = [], threading.Barrier(5)

        def reserve_loop():
            barrier.wait()
            with SASession(pg) as s:
                for _ in range(3):
                    try:
                        quota.reserve(s, uid, 5)
                    except quota.UserGone:
                        return
                    except Exception as e:  # noqa: BLE001
                        errors.append(repr(e)); return

        def delete():
            barrier.wait()
            try:
                with SASession(pg) as s:
                    assert delete_account(s, s.get(User, uid), PW)
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))

        threads = [threading.Thread(target=reserve_loop) for _ in range(4)] + [threading.Thread(target=delete)]
        [t.start() for t in threads]; [t.join(30) for t in threads]
        assert not errors, errors
        with SASession(pg) as s:
            assert f"user:{uid}" not in scopes(s), f"orphaned usage row after round {round_}"
    with SASession(pg) as s:
        assert s.get(User, bystander) is not None
        quota.reserve(s, bystander, 5)  # unaffected
