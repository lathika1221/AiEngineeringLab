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


# ------------------------------------------- F5 lock order: user row first, usage rows second
from sqlalchemy import select  # noqa: E402

from src.services.auth_service import AccountGone  # noqa: E402


@pytest.fixture
def open_limits(monkeypatch):
    monkeypatch.setattr(settings, "AI_DAILY_REQUESTS_PER_USER", 10_000)
    monkeypatch.setattr(settings, "AI_DAILY_REQUESTS_GLOBAL", 1_000_000)
    monkeypatch.setattr(settings, "AI_DAILY_TOKENS_GLOBAL", 1_000_000_000)


def seed_owner(engine, n, with_usage=True):
    """A real user who already has a usage row today and a chat (the case that deadlocked)."""
    uid = new_user(engine, n)
    with SASession(engine) as s:
        s.add(Chat(user_id=uid, user_message="q", ai_response="a"))
        s.commit()
        if with_usage:
            quota.reserve(s, uid, 10)
    return uid


def leftovers(engine, uid):
    with SASession(engine) as s:
        return {
            "user": s.query(User).filter(User.id == uid).count(),
            "chats": s.query(Chat).filter(Chat.user_id == uid).count(),
            "usage": s.query(AiUsageDaily).filter(AiUsageDaily.scope == f"user:{uid}").count(),
        }


def test_postgres_original_deadlock_scenario_now_completes_for_both(pg, open_limits):
    """The exact interleaving that deadlocked: the reservation holds the user-row lock, the
    deletion starts and must wait, then the reservation updates the EXISTING usage row."""
    uid = seed_owner(pg, 1)
    bystander = seed_owner(pg, 2)
    out, started = {}, threading.Event()
    reserver = SASession(pg)
    reserver.execute(select(User.id).where(User.id == uid).with_for_update(read=True)).first()  # reserve()'s first step

    def delete():
        with SASession(pg) as s:
            started.set()
            try:
                out["d"] = delete_account(s, s.get(User, uid), PW)
            except Exception as e:  # noqa: BLE001
                out["d"] = repr(e)

    t = threading.Thread(target=delete)
    t.start()
    started.wait(5)
    t.join(1.5)
    assert t.is_alive(), "deletion must wait for the reservation's user-row lock, not run ahead of it"
    quota.reserve(reserver, uid, 10)  # updates the existing usage row, then commits and releases the lock
    t.join(15)
    assert not t.is_alive()
    assert out["d"] is True, out  # no deadlock, no error
    assert leftovers(pg, uid) == {"user": 0, "chats": 0, "usage": 0}
    assert leftovers(pg, bystander) == {"user": 1, "chats": 1, "usage": 1}
    reserver.close()


def test_postgres_second_deleter_sees_the_account_gone_not_a_500(pg):
    uid = seed_owner(pg, 3)
    results, barrier = [], threading.Barrier(2)

    def run():
        with SASession(pg) as s:
            user = s.get(User, uid)
            barrier.wait()
            try:
                results.append(delete_account(s, user, PW))
            except AccountGone:
                results.append("gone")
            except Exception as e:  # noqa: BLE001
                results.append(repr(e))

    ts = [threading.Thread(target=run) for _ in range(2)]
    [t.start() for t in ts]; [t.join(30) for t in ts]
    assert sorted(map(str, results)) == ["True", "gone"], results
    assert leftovers(pg, uid) == {"user": 0, "chats": 0, "usage": 0}


def test_postgres_wrong_password_takes_no_lock_and_deletes_nothing(pg):
    uid = seed_owner(pg, 4)
    holder = SASession(pg)
    holder.execute(select(User.id).where(User.id == uid).with_for_update()).first()  # someone holds the row lock
    with SASession(pg) as s:
        assert delete_account(s, s.get(User, uid), "Wrong-Password-123") is False  # returns at once, no waiting
    holder.rollback(); holder.close()
    assert leftovers(pg, uid) == {"user": 1, "chats": 1, "usage": 1}


def test_postgres_password_changed_while_waiting_for_the_lock_cancels_the_deletion(pg):
    uid = seed_owner(pg, 5)
    changer = SASession(pg)
    row = changer.execute(select(User).where(User.id == uid).with_for_update()).scalar_one()
    out = {}

    def delete():
        with SASession(pg) as s:
            out["d"] = delete_account(s, s.get(User, uid), PW)  # verifies the OLD password, then waits

    t = threading.Thread(target=delete)
    t.start(); t.join(1.5)
    assert t.is_alive()
    row.hashed_password = hash_password("Brand-New-Password-456")
    changer.commit()
    t.join(15)
    assert out["d"] is False
    assert leftovers(pg, uid) == {"user": 1, "chats": 1, "usage": 1}
    changer.close()


def test_postgres_repeated_reservation_vs_deletion_races_never_fail_or_orphan(pg, open_limits):
    """Many rounds, existing usage row every time, several reservers racing one deleter with
    jittered starts. Allowed outcomes: a reservation succeeds or sees the account gone; the
    deletion succeeds. Anything else (deadlock, 500-class error) fails the test."""
    import random

    bystander = seed_owner(pg, 900)
    for round_ in range(40):
        uid = seed_owner(pg, 1000 + round_)
        errors, barrier = [], threading.Barrier(5)
        rng = random.Random(round_)

        def reserve_loop(delay):
            barrier.wait()
            threading.Event().wait(delay)
            with SASession(pg) as s:
                for _ in range(4):
                    try:
                        quota.reserve(s, uid, 5)
                    except quota.UserGone:
                        return
                    except Exception as e:  # noqa: BLE001
                        errors.append(f"reserve {e!r}"[:200]); return

        def delete(delay):
            barrier.wait()
            threading.Event().wait(delay)
            with SASession(pg) as s:
                try:
                    if delete_account(s, s.get(User, uid), PW) is not True:
                        errors.append("delete returned False")
                except Exception as e:  # noqa: BLE001
                    errors.append(f"delete {e!r}"[:200])

        ts = [threading.Thread(target=reserve_loop, args=(rng.random() * 0.02,)) for _ in range(4)]
        ts.append(threading.Thread(target=delete, args=(rng.random() * 0.02,)))
        [t.start() for t in ts]; [t.join(60) for t in ts]
        assert not any(t.is_alive() for t in ts), f"hang in round {round_}"
        assert not errors, f"round {round_}: {errors}"
        assert leftovers(pg, uid) == {"user": 0, "chats": 0, "usage": 0}, f"round {round_}"
    assert leftovers(pg, bystander) == {"user": 1, "chats": 1, "usage": 1}


def test_postgres_http_ai_requests_racing_account_deletion_never_500(pg, open_limits, monkeypatch):
    """Through the real routes on PostgreSQL: AI chat requests and POST /users/me/delete at the
    same time. Only 200/401/204 are acceptable; never a 5xx."""
    import random

    Session = sessionmaker(bind=pg, autoflush=False)

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_AI_PER_MINUTE", 100_000)
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 100_000)
    monkeypatch.setattr(ai_routes, "chat_with_ai", lambda **k: "ok")
    try:
        bystander = seed_owner(pg, 800)
        client = TestClient(app, raise_server_exceptions=False)
        for round_ in range(15):
            uid = seed_owner(pg, 2000 + round_)
            r = client.post("/auth/login", data={"username": f"u{2000 + round_}", "password": PW})
            assert r.status_code == 200, r.text
            head = {"Authorization": f"Bearer {r.json()['access_token']}"}
            codes, barrier, rng = [], threading.Barrier(5), random.Random(round_)

            def chat(d):
                barrier.wait(); threading.Event().wait(d)
                codes.append(("chat", TestClient(app, raise_server_exceptions=False).post("/ai/chat", json={"message": "hi"}, headers=head).status_code))

            def delete(d):
                barrier.wait(); threading.Event().wait(d)
                codes.append(("delete", TestClient(app, raise_server_exceptions=False).post("/users/me/delete", json={"password": PW}, headers=head).status_code))

            ts = [threading.Thread(target=chat, args=(rng.random() * 0.03,)) for _ in range(4)] + [threading.Thread(target=delete, args=(rng.random() * 0.03,))]
            [t.start() for t in ts]; [t.join(60) for t in ts]
            assert not any(t.is_alive() for t in ts)
            bad = [c for c in codes if c[1] >= 500 or (c[0] == "chat" and c[1] not in (200, 401, 429)) or (c[0] == "delete" and c[1] not in (204, 401))]
            assert not bad, f"round {round_}: {codes}"
            assert ("delete", 204) in codes or ("delete", 401) in codes
            assert leftovers(pg, uid) == {"user": 0, "chats": 0, "usage": 0}, f"round {round_}: {codes}"
        assert leftovers(pg, bystander) == {"user": 1, "chats": 1, "usage": 1}
    finally:
        app.dependency_overrides.clear()
