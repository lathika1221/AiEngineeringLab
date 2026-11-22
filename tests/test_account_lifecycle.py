"""Password change and account deletion, with real JWTs and two accounts."""
import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.auth.hash import hash_password
from src.auth.jwt import create_access_token
from src.config.settings import settings
from src.database.base import Base
from src.database.session import get_db
from src.models import AiUsageDaily, Chat, Conversation, Goal, LifeRole, Memory, Project, User, UserProfile

PW = {"alice": "Alice-Test-Password-1", "bob": "Bob-Test-Password-22"}
NEW = "Alice-Brand-New-Password-3"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 3)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _):  # enforce foreign keys like PostgreSQL does
        conn.execute("PRAGMA foreign_keys=ON")

    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = Session()
    for name, pw in PW.items():
        db.add(User(username=name, email=f"{name}@example.com", hashed_password=hash_password(pw)))
    db.commit()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, db
    finally:
        app.dependency_overrides.clear()
        db.close()


def login(client, name, password=None):
    return client.post("/auth/login", data={"username": name, "password": password or PW[name]})


def auth(client, name):
    r = login(client, name)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def change(client, h, current=PW["alice"], new=NEW):
    return client.post("/auth/change-password", json={"current_password": current, "new_password": new}, headers=h)


# --------------------------------------------------------------- password change
def test_change_requires_authentication(env):
    client, _ = env
    r = client.post("/auth/change-password", json={"current_password": "x", "new_password": NEW})
    assert r.status_code == 401


def test_change_succeeds_and_old_password_stops_working(env):
    client, _ = env
    h = auth(client, "alice")
    r = change(client, h)
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"
    assert login(client, "alice").status_code == 401
    assert login(client, "alice", NEW).status_code == 200
    assert "password" not in r.text.lower().replace("token_type", "")


def test_change_returns_a_working_token_and_kills_every_older_token(env):
    client, _ = env
    old1, old2 = auth(client, "alice"), auth(client, "alice")
    new = {"Authorization": f"Bearer {change(client, old1).json()['access_token']}"}
    assert client.get("/users/me", headers=new).status_code == 200
    assert client.get("/users/me", headers=old1).status_code == 401
    assert client.get("/users/me", headers=old2).status_code == 401


def test_change_does_not_affect_other_accounts(env):
    client, _ = env
    bob = auth(client, "bob")
    change(client, auth(client, "alice"))
    assert client.get("/users/me", headers=bob).status_code == 200
    assert login(client, "bob").status_code == 200


def test_wrong_current_password_changes_nothing(env):
    client, _ = env
    h = auth(client, "alice")
    r = change(client, h, current="not-the-password-1")
    assert r.status_code == 400
    assert login(client, "alice").status_code == 200
    assert client.get("/users/me", headers=h).status_code == 200


def test_same_password_is_rejected(env):
    client, _ = env
    assert change(client, auth(client, "alice"), new=PW["alice"]).status_code == 400


@pytest.mark.parametrize("bad", ["short", "x" * 11, "é" * 37])  # < 12 chars, < 12 chars, 74 bytes
def test_new_password_policy_is_enforced(env, bad):
    client, _ = env
    assert change(client, auth(client, "alice"), new=bad).status_code == 422
    assert login(client, "alice").status_code == 200


def test_change_is_rate_limited_per_account(env):
    client, _ = env
    h = auth(client, "alice")
    codes = [change(client, h, current="wrong-password-x").status_code for _ in range(5)]
    assert codes[:3] == [400, 400, 400] and codes[3:] == [429, 429]
    # Bob has his own allowance.
    r = client.post(
        "/auth/change-password",
        json={"current_password": PW["bob"], "new_password": "Bob-Other-Password-4"},
        headers=auth(client, "bob"),
    )
    assert r.status_code == 200


def test_login_tokens_carry_a_fingerprint_not_the_hash(env):
    client, db = env
    token = login(client, "alice").json()["access_token"]
    claims = jwt.get_unverified_claims(token)
    stored = db.query(User).filter(User.username == "alice").one().hashed_password
    assert "pv" in claims and stored not in token and claims["pv"] != stored


def test_tokens_without_the_fingerprint_claim_remain_valid_until_expiry(env):
    client, _ = env
    legacy = create_access_token({"sub": "alice@example.com"})
    assert client.get("/users/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 200


def test_a_forged_fingerprint_is_rejected(env):
    client, _ = env
    forged = create_access_token({"sub": "alice@example.com", "pv": "0" * 24})
    assert client.get("/users/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


# ------------------------------------------------------------- account deletion
def _populate(client, db, name, h):
    client.post("/projects", json={"name": f"{name}-project"}, headers=h)
    cid = client.post("/conversations", json={"title": f"{name}-conv", "category": "general"}, headers=h).json()["id"]
    client.post("/memory", json={"memory_type": "fact", "content": f"{name}-memory"}, headers=h)
    client.post("/users/goals", json={"title": f"{name}-goal"}, headers=h)
    client.post("/users/roles", json={"role": f"{name}-role"}, headers=h)
    client.post("/users/profile", json={"display_name": name}, headers=h)
    uid = db.query(User).filter(User.username == name).one().id
    db.add(Chat(user_id=uid, conversation_id=cid, user_message="q", ai_response="a"))
    db.add(AiUsageDaily(scope=f"user:{uid}", usage_date=__import__("datetime").date.today(), requests=2, tokens=100))
    db.commit()
    return uid


def _owned(db, uid):
    return {
        m.__name__: db.query(m).filter(m.user_id == uid).count()
        for m in (Project, Conversation, Memory, Goal, LifeRole, UserProfile, Chat)
    } | {"usage": db.query(AiUsageDaily).filter(AiUsageDaily.scope == f"user:{uid}").count()}


def test_delete_requires_authentication(env):
    client, _ = env
    assert client.post("/users/me/delete", json={"password": PW["alice"]}).status_code == 401


def test_delete_with_wrong_password_deletes_nothing(env):
    client, db = env
    h = auth(client, "alice")
    uid = _populate(client, db, "alice", h)
    before = _owned(db, uid)
    r = client.post("/users/me/delete", json={"password": "wrong-password-x"}, headers=h)
    assert r.status_code == 400
    assert _owned(db, uid) == before and all(v >= 1 for v in before.values())
    assert login(client, "alice").status_code == 200


def test_delete_removes_the_account_and_everything_it_owns_and_nothing_else(env):
    client, db = env
    ha, hb = auth(client, "alice"), auth(client, "bob")
    uid_a, uid_b = _populate(client, db, "alice", ha), _populate(client, db, "bob", hb)
    bob_before = _owned(db, uid_b)

    r = client.post("/users/me/delete", json={"password": PW["alice"]}, headers=ha)
    assert r.status_code == 204 and r.content == b""

    assert db.query(User).filter(User.username == "alice").count() == 0
    assert all(v == 0 for v in _owned(db, uid_a).values())
    assert _owned(db, uid_b) == bob_before
    assert client.get("/users/me", headers=ha).status_code == 401
    assert login(client, "alice").status_code == 401
    assert client.get("/projects", headers=hb).json()[0]["name"] == "bob-project"


def test_delete_is_rate_limited_per_account(env):
    client, _ = env
    h = auth(client, "alice")
    codes = [client.post("/users/me/delete", json={"password": "wrong-password-x"}, headers=h).status_code for _ in range(5)]
    assert codes == [400, 400, 400, 429, 429]
    assert login(client, "alice").status_code == 200


# ------------------------------------------- real PostgreSQL foreign keys (gated)
def test_delete_account_cascades_on_postgresql():
    """SQLite proves the logic; this proves the production database's FK rules (chats
    reference users, projects and conversations; conversations reference projects)."""
    import datetime
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from test_migrations import ADMIN_URL, _create_throwaway_db, _drop_throwaway_db, validate_admin_url

    if not ADMIN_URL:
        pytest.skip("LATZ_TEST_PG_ADMIN_URL not set")
    validate_admin_url(ADMIN_URL)
    from sqlalchemy.orm import Session as SASession

    from src.services.auth_service import delete_account

    name, url = _create_throwaway_db(ADMIN_URL)
    engine = create_engine(url)
    try:
        Base.metadata.create_all(engine)
        with SASession(engine) as s:
            users = [User(username=n, email=f"{n}@example.com", hashed_password=hash_password(PW[n])) for n in PW]
            s.add_all(users)
            s.commit()
            for u in users:
                p = Project(user_id=u.id, name=f"{u.username}-p")
                s.add(p)
                s.flush()
                c = Conversation(user_id=u.id, project_id=p.id, title="c", category="general")
                s.add(c)
                s.flush()
                s.add_all([
                    Chat(user_id=u.id, project_id=p.id, conversation_id=c.id, user_message="q", ai_response="a"),
                    Memory(user_id=u.id, memory_type="fact", content="m"),
                    Goal(user_id=u.id, title="g"),
                    LifeRole(user_id=u.id, role="r"),
                    UserProfile(user_id=u.id, display_name=u.username),
                    AiUsageDaily(scope=f"user:{u.id}", usage_date=datetime.date.today(), requests=1, tokens=1),
                ])
            s.commit()
            alice, bob = users
            assert delete_account(s, alice, "wrong-password-x") is False
            assert delete_account(s, alice, PW["alice"]) is True
            assert s.query(User).count() == 1
            for m in (Project, Conversation, Memory, Goal, LifeRole, UserProfile, Chat):
                assert s.query(m).filter(m.user_id == alice.id).count() == 0, m.__name__
                assert s.query(m).filter(m.user_id == bob.id).count() == 1, m.__name__
            assert s.query(AiUsageDaily).filter(AiUsageDaily.scope == f"user:{bob.id}").count() == 1
    finally:
        engine.dispose()
        _drop_throwaway_db(ADMIN_URL, name)
