"""Cross-account isolation tests.

Unlike the override-based tests elsewhere, these authenticate as two real users
through POST /auth/login and send real JWTs, so the whole dependency chain
(token -> get_current_user -> ownership-scoped query) is exercised. Uses an
in-memory SQLite database and never touches any external service.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.api.routes import ai as ai_routes
from src.auth.hash import hash_password
from src.database.base import Base
from src.database.session import get_db
from src.models import Chat, User

PASSWORD_A = "Alice-Test-Password-1"
PASSWORD_B = "Bob-Test-Password-22"


@pytest.fixture
def env():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = Session()
    for name, pw in (("alice", PASSWORD_A), ("bob", PASSWORD_B)):
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


def _login(client, name, password):
    r = client.post("/auth/login", data={"username": name, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def users(env):
    client, db = env
    return client, db, _login(client, "alice", PASSWORD_A), _login(client, "bob", PASSWORD_B)


# --- unauthenticated access is rejected on every protected route ------------

PROTECTED = [
    ("GET", "/users/me"), ("GET", "/users/profile"), ("GET", "/users/roles"),
    ("GET", "/users/goals"), ("GET", "/users/context"),
    ("GET", "/projects"), ("GET", "/conversations"), ("GET", "/memory"),
    ("GET", "/ai/history"),
    ("POST", "/ai/chat"), ("POST", "/ai/chat/stream"),
    ("POST", "/ai/memory-candidate"), ("POST", "/ai/memory-confirm"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_routes_reject_missing_token(env, method, path):
    client, _ = env
    r = client.request(method, path, json={} if method == "POST" else None)
    assert r.status_code == 401


@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_routes_reject_garbage_token(env, method, path):
    client, _ = env
    r = client.request(
        method, path, headers={"Authorization": "Bearer not.a.jwt"},
        json={} if method == "POST" else None,
    )
    assert r.status_code == 401


# --- projects ---------------------------------------------------------------

def test_projects_are_private(users):
    client, _, a, b = users
    pid = client.post("/projects", json={"name": "alice-proj"}, headers=a).json()["id"]
    assert [p["id"] for p in client.get("/projects", headers=a).json()] == [pid]
    assert client.get("/projects", headers=b).json() == []
    assert client.get(f"/projects/{pid}", headers=b).status_code == 404
    assert client.patch(f"/projects/{pid}", json={"name": "pwned"}, headers=b).status_code == 404
    assert client.delete(f"/projects/{pid}", headers=b).status_code == 404
    assert client.get(f"/projects/{pid}", headers=a).json()["name"] == "alice-proj"


# --- conversations ----------------------------------------------------------

def test_conversations_are_private(users):
    client, _, a, b = users
    cid = client.post("/conversations", json={"title": "secret", "category": "general"}, headers=a).json()["id"]
    assert client.get("/conversations", headers=b).json() == []
    assert client.get(f"/conversations/{cid}", headers=b).status_code == 404
    assert client.patch(f"/conversations/{cid}", json={"title": "x"}, headers=b).status_code == 404
    assert client.delete(f"/conversations/{cid}", headers=b).status_code == 404
    assert client.get(f"/conversations/{cid}", headers=a).json()["title"] == "secret"


def test_conversation_cannot_attach_to_foreign_project(users):
    client, _, a, b = users
    pid = client.post("/projects", json={"name": "alice-proj"}, headers=a).json()["id"]
    r = client.post(
        "/conversations", json={"title": "t", "category": "general", "project_id": pid}, headers=b
    )
    assert r.status_code == 404


# --- memories ---------------------------------------------------------------

def test_memories_are_private(users):
    client, _, a, b = users
    mid = client.post("/memory", json={"memory_type": "fact", "content": "alice-secret"}, headers=a).json()["id"]
    assert client.get("/memory", headers=b).json() == []
    assert client.delete(f"/memory/{mid}", headers=b).status_code in (403, 404)
    assert [m["id"] for m in client.get("/memory", headers=a).json()] == [mid]


# --- goals, roles, profile --------------------------------------------------

def test_goals_are_private(users):
    client, _, a, b = users
    gid = client.post("/users/goals", json={"title": "alice-goal"}, headers=a).json()["id"]
    assert client.get("/users/goals", headers=b).json() == []
    assert client.patch(f"/users/goals/{gid}/status", json={"status": "completed"}, headers=b).status_code in (404, 422)
    assert client.delete(f"/users/goals/{gid}", headers=b).status_code == 404
    assert [g["id"] for g in client.get("/users/goals", headers=a).json()] == [gid]


def test_life_roles_are_private(users):
    client, _, a, b = users
    rid = client.post("/users/roles", json={"role": "alice-role"}, headers=a).json()["id"]
    assert client.get("/users/roles", headers=b).json() == []
    assert client.delete(f"/users/roles/{rid}", headers=b).status_code == 404
    assert [r["id"] for r in client.get("/users/roles", headers=a).json()] == [rid]


def test_profiles_are_private(users):
    client, _, a, b = users
    assert client.post("/users/profile", json={"display_name": "Alice", "bio": "alice-bio"}, headers=a).status_code in (200, 201)
    assert client.get("/users/profile", headers=b).status_code == 404
    assert client.get("/users/profile", headers=a).json()["display_name"] == "Alice"
    assert client.get("/users/me", headers=b).json()["email"] == "bob@example.com"


# --- chat history -----------------------------------------------------------

def test_chat_history_is_private(users):
    client, db, a, b = users
    alice = db.query(User).filter(User.username == "alice").one()
    db.add(Chat(user_id=alice.id, user_message="alice question", ai_response="alice answer"))
    db.commit()
    assert client.get("/ai/history", headers=b).json() == []
    assert len(client.get("/ai/history", headers=a).json()) == 1


def test_history_rejects_foreign_project_and_conversation(users):
    client, _, a, b = users
    pid = client.post("/projects", json={"name": "p"}, headers=a).json()["id"]
    cid = client.post("/conversations", json={"title": "c", "category": "general"}, headers=a).json()["id"]
    assert client.get(f"/ai/history?project_id={pid}", headers=b).status_code == 404
    assert client.get(f"/ai/history?conversation_id={cid}", headers=b).status_code == 404


# --- AI context isolation ---------------------------------------------------

def test_ai_context_contains_only_the_callers_data(users, monkeypatch):
    """What is sent to the model for Bob must never contain Alice's memories,
    history, goals, roles or projects."""
    client, db, a, b = users
    client.post("/memory", json={"memory_type": "fact", "content": "ALICE-MEMORY-MARKER"}, headers=a)
    client.post("/users/goals", json={"title": "ALICE-GOAL-MARKER"}, headers=a)
    client.post("/users/roles", json={"role": "ALICE-ROLE-MARKER"}, headers=a)
    client.post("/projects", json={"name": "ALICE-PROJECT-MARKER"}, headers=a)
    alice = db.query(User).filter(User.username == "alice").one()
    db.add(Chat(user_id=alice.id, user_message="ALICE-CHAT-MARKER", ai_response="ALICE-REPLY-MARKER"))
    db.commit()

    captured = {}

    def fake_chat_with_ai(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(ai_routes, "chat_with_ai", fake_chat_with_ai)
    r = client.post("/ai/chat", json={"message": "hello"}, headers=b)
    assert r.status_code == 200, r.text
    assert "ALICE-" not in repr(captured)
    assert captured["message"] == "hello"
