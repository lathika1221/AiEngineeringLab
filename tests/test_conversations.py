
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.auth.dependencies import get_current_user
from src.database.base import Base
from src.database.session import get_db
from src.models import (
    User,
    Chat,
    Conversation,
    Memory,
    UserProfile,
    LifeRole,
    Goal,
    Project,
)


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="test-hash",
    )
    other_user = User(
        username="otheruser",
        email="other@example.com",
        hashed_password="other-hash",
    )

    db.add_all([user, other_user])
    db.commit()
    db.refresh(user)
    db.refresh(other_user)

    try:
        yield db, user, other_user
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def client(test_db):
    db, user, _ = test_db

    def override_get_db():
        yield db

    def override_get_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_create_conversation(client):
    response = client.post(
        "/conversations",
        json={"title": "My first chat", "category": "learning"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "My first chat"
    assert data["category"] == "learning"
    assert data["project_id"] is None
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_conversation_normalizes_category(client):
    response = client.post(
        "/conversations",
        json={"title": "Research notes", "category": "  RESEARCH  "},
    )

    assert response.status_code == 201
    assert response.json()["category"] == "research"


def test_create_conversation_rejects_invalid_category(client):
    response = client.post(
        "/conversations",
        json={"title": "Invalid category", "category": "unknown"},
    )

    assert response.status_code == 422


def test_create_conversation_uses_default_title(client):
    response = client.post(
        "/conversations",
        json={"title": "   ", "category": "general"},
    )

    assert response.status_code == 201
    assert response.json()["title"] == "New Chat"


def test_list_conversations_returns_current_users_only(client, test_db):
    db, user, other_user = test_db

    db.add_all([
        Conversation(
            user_id=user.id,
            title="My conversation",
            category="learning",
        ),
        Conversation(
            user_id=other_user.id,
            title="Other user's conversation",
            category="learning",
        ),
    ])
    db.commit()

    response = client.get("/conversations")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "My conversation"


def test_list_conversations_filters_by_category(client, test_db):
    db, user, _ = test_db

    db.add_all([
        Conversation(
            user_id=user.id,
            title="Learning chat",
            category="learning",
        ),
        Conversation(
            user_id=user.id,
            title="Research chat",
            category="research",
        ),
    ])
    db.commit()

    response = client.get("/conversations", params={"category": "research"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["category"] == "research"


def test_get_existing_conversation(client, test_db):
    db, user, _ = test_db
    conversation = Conversation(
        user_id=user.id,
        title="Existing chat",
        category="general",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    response = client.get(f"/conversations/{conversation.id}")

    assert response.status_code == 200
    assert response.json()["title"] == "Existing chat"


def test_get_other_users_conversation_returns_404(client, test_db):
    db, _, other_user = test_db
    conversation = Conversation(
        user_id=other_user.id,
        title="Private chat",
        category="general",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    response = client.get(f"/conversations/{conversation.id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_get_missing_conversation_returns_404(client):
    response = client.get("/conversations/999999")

    assert response.status_code == 404


def test_create_conversation_with_missing_project_returns_404(client):
    response = client.post(
        "/conversations",
        json={
            "title": "Project chat",
            "category": "projects",
            "project_id": 999999,
        },
    )

    assert response.status_code == 404

from src.models.chat import Chat


def test_chat_saves_response_to_correct_conversation(client, test_db, monkeypatch):
    from src.api.routes import ai as ai_routes

    db, user, _ = test_db
    conversation = Conversation(
        user_id=user.id,
        title="New Chat",
        category="learning",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    monkeypatch.setattr(
        ai_routes,
        "get_recent_chats",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        ai_routes,
        "get_memories",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        ai_routes,
        "build_request_context",
        lambda **kwargs: {"current_project": None},
    )
    monkeypatch.setattr(
        ai_routes,
        "chat_with_ai",
        lambda **kwargs: "Mocked AI response",
    )

    response = client.post(
        "/ai/chat",
        json={
            "message": "Explain Python functions",
            "conversation_id": conversation.id,
            "engine": "learn",
        },
    )

    assert response.status_code == 200
    assert response.json()["response"] == "Mocked AI response"

    saved_chat = db.query(Chat).filter(
        Chat.conversation_id == conversation.id
    ).one()

    assert saved_chat.user_message == "Explain Python functions"
    assert saved_chat.ai_response == "Mocked AI response"

    db.refresh(conversation)
    assert conversation.title == "Explain Python functions"


def test_chat_history_isolated_between_conversations(client, test_db):
    db, user, _ = test_db

    first = Conversation(
        user_id=user.id,
        title="First conversation",
        category="learning",
    )
    second = Conversation(
        user_id=user.id,
        title="Second conversation",
        category="research",
    )
    db.add_all([first, second])
    db.commit()
    db.refresh(first)
    db.refresh(second)

    db.add_all([
        Chat(
            user_id=user.id,
            conversation_id=first.id,
            user_message="First question",
            ai_response="First answer",
        ),
        Chat(
            user_id=user.id,
            conversation_id=second.id,
            user_message="Second question",
            ai_response="Second answer",
        ),
    ])
    db.commit()

    response = client.get(
        "/ai/history",
        params={"conversation_id": first.id},
    )

    assert response.status_code == 200
    history = response.json()
    assert len(history) == 1
    assert history[0]["user_message"] == "First question"
    assert history[0]["ai_response"] == "First answer"


def test_chat_rejects_another_users_conversation(
    client, test_db, monkeypatch
):
    from src.api.routes import ai as ai_routes

    db, _, other_user = test_db
    conversation = Conversation(
        user_id=other_user.id,
        title="Private conversation",
        category="general",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    monkeypatch.setattr(
        ai_routes,
        "chat_with_ai",
        lambda **kwargs: "This must not be called",
    )

    response = client.post(
        "/ai/chat",
        json={
            "message": "Try accessing private conversation",
            "conversation_id": conversation.id,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"
from src.api.routes import ai as ai_routes


def test_stream_chat_saves_complete_response(client, test_db, monkeypatch):
    db, user, _ = test_db
    conversation = Conversation(
        user_id=user.id,
        title="Streaming test",
        category="learning",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    conversation_id = conversation.id

    monkeypatch.setattr(ai_routes, "get_recent_chats", lambda **kwargs: [])
    monkeypatch.setattr(ai_routes, "get_memories", lambda **kwargs: [])
    monkeypatch.setattr(
        ai_routes,
        "build_request_context",
        lambda **kwargs: {"current_project": None},
    )

    def fake_stream(outcome=None, **kwargs):
        yield "Streaming "
        yield "works!"
        outcome["finish_reason"] = "stop"

    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", fake_stream)

    response = client.post(
        "/ai/chat/stream",
        json={
            "message": "Test streaming",
            "conversation_id": conversation_id,
            "engine": "learn",
        },
    )

    assert response.status_code == 200
    assert response.text == f"Streaming works!{ai_routes.STREAM_END_MARKER}stop"

    from sqlalchemy.orm import Session

    fresh_db = Session(bind=db.get_bind())
    try:
        saved_chat = fresh_db.query(Chat).filter(
            Chat.conversation_id == conversation_id
        ).one()

        assert saved_chat.user_message == "Test streaming"
        assert saved_chat.ai_response == "Streaming works!"
    finally:
        fresh_db.close()


def _run_stream(db, user, monkeypatch, fake_stream, message):
    conversation = Conversation(user_id=user.id, title="Stream test", category="learning")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    conversation_id = conversation.id

    monkeypatch.setattr(ai_routes, "get_recent_chats", lambda **kwargs: [])
    monkeypatch.setattr(ai_routes, "get_memories", lambda **kwargs: [])
    monkeypatch.setattr(
        ai_routes, "build_request_context", lambda **kwargs: {"current_project": None}
    )
    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", fake_stream)

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.post(
            "/ai/chat/stream",
            json={"message": message, "conversation_id": conversation_id, "engine": "learn"},
        )

    from sqlalchemy.orm import Session

    fresh_db = Session(bind=db.get_bind())
    try:
        saved = fresh_db.query(Chat).filter(Chat.conversation_id == conversation_id).all()
        return response, [chat.ai_response for chat in saved]
    finally:
        fresh_db.close()


def test_stream_chat_preserves_partial_response_on_failure(client, test_db, monkeypatch):
    db, user, _ = test_db

    def failing_stream(**kwargs):
        yield "Partial response "
        raise RuntimeError("simulated stream failure")

    response, saved = _run_stream(db, user, monkeypatch, failing_stream, "Test failed streaming")

    assert response.status_code == 200
    assert response.text == f"Partial response {ai_routes.STREAM_END_MARKER}error"
    assert len(saved) == 1
    assert saved[0].startswith("Partial response ")
    assert "Response incomplete" in saved[0]
    assert "simulated stream failure" not in response.text + saved[0]


def test_stream_chat_failure_before_any_output_saves_nothing(client, test_db, monkeypatch):
    db, user, _ = test_db

    def failing_stream(**kwargs):
        raise RuntimeError("provider down")
        yield ""  # pragma: no cover

    response, saved = _run_stream(db, user, monkeypatch, failing_stream, "Nothing arrives")

    assert response.text == f"{ai_routes.STREAM_END_MARKER}error"
    assert saved == []


def test_stream_chat_marks_length_limited_response_incomplete(client, test_db, monkeypatch):
    db, user, _ = test_db
    long_text = "## Section 6\nIntegration of " + ("word " * 400)

    def length_stream(outcome=None, **kwargs):
        yield long_text
        outcome["finish_reason"] = "length"

    response, saved = _run_stream(db, user, monkeypatch, length_stream, "Seven sections please")

    assert response.text == f"{long_text}{ai_routes.STREAM_END_MARKER}length"
    assert len(saved) == 1
    assert saved[0].startswith(long_text)
    assert "output length limit" in saved[0]


def test_stream_chat_without_finish_reason_is_incomplete(client, test_db, monkeypatch):
    db, user, _ = test_db

    def silent_stream(**kwargs):
        yield "Ended without a finish reason"

    response, saved = _run_stream(db, user, monkeypatch, silent_stream, "No finish reason")

    assert response.text == f"Ended without a finish reason{ai_routes.STREAM_END_MARKER}incomplete"
    assert len(saved) == 1
    assert saved[0].startswith("Ended without a finish reason")
    assert "may be incomplete" in saved[0]


def test_stream_chat_unexpected_finish_reason_is_incomplete(client, test_db, monkeypatch):
    db, user, _ = test_db

    def odd_stream(outcome=None, **kwargs):
        yield "Filtered reply"
        outcome["finish_reason"] = "content_filter"

    response, saved = _run_stream(db, user, monkeypatch, odd_stream, "Odd finish reason")

    assert response.text.endswith(f"{ai_routes.STREAM_END_MARKER}incomplete")
    assert "may be incomplete" in saved[0]


def test_stream_chat_stop_finish_reason_is_complete_and_unannotated(client, test_db, monkeypatch):
    db, user, _ = test_db

    def stop_stream(outcome=None, **kwargs):
        yield "All seven sections and a conclusion."
        outcome["finish_reason"] = "stop"

    response, saved = _run_stream(db, user, monkeypatch, stop_stream, "Complete reply")

    assert response.text.endswith(f"{ai_routes.STREAM_END_MARKER}stop")
    assert saved == ["All seven sections and a conclusion."]


def test_stream_chat_rolls_back_when_persistence_fails(
    client, test_db, monkeypatch
):
    db, user, _ = test_db

    conversation = Conversation(
        user_id=user.id,
        title="Persistence failure test",
        category="learning",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    rollback_calls = []
    original_rollback = db.rollback

    def tracked_rollback():
        rollback_calls.append(True)
        original_rollback()

    monkeypatch.setattr(db, "rollback", tracked_rollback)

    monkeypatch.setattr(ai_routes, "get_recent_chats", lambda **kwargs: [])
    monkeypatch.setattr(ai_routes, "get_memories", lambda **kwargs: [])
    monkeypatch.setattr(
        ai_routes,
        "build_request_context",
        lambda **kwargs: {"current_project": None},
    )

    def fake_stream(outcome=None, **kwargs):
        yield "Complete response"
        outcome["finish_reason"] = "stop"

    def failing_save_chat(**kwargs):
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", fake_stream)
    monkeypatch.setattr(ai_routes, "save_chat", failing_save_chat)

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.post(
            "/ai/chat/stream",
            json={
                "message": "Test persistence failure",
                "conversation_id": conversation.id,
                "engine": "learn",
            },
        )

    assert response.status_code == 200
    assert rollback_calls == [True]


def _make_conversation(db, user, title="Original title"):
    conversation = Conversation(user_id=user.id, title=title, category="general")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def test_rename_conversation(client, test_db):
    db, user, _ = test_db
    conversation = _make_conversation(db, user)

    response = client.patch(f"/conversations/{conversation.id}", json={"title": "  Renamed  "})

    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"
    assert client.get(f"/conversations/{conversation.id}").json()["title"] == "Renamed"


def test_rename_conversation_rejects_blank_and_overlong_titles(client, test_db):
    db, user, _ = test_db
    conversation = _make_conversation(db, user)

    for title in ["", "   ", "x" * 201]:
        response = client.patch(f"/conversations/{conversation.id}", json={"title": title})
        assert response.status_code == 422

    assert client.patch(f"/conversations/{conversation.id}", json={}).status_code == 422
    assert client.get(f"/conversations/{conversation.id}").json()["title"] == "Original title"


def test_rename_conversation_does_not_change_other_fields(client, test_db):
    db, user, _ = test_db
    conversation = _make_conversation(db, user)

    data = client.patch(
        f"/conversations/{conversation.id}",
        json={"title": "New", "category": "research", "project_id": 99},
    ).json()

    assert data["category"] == "general"
    assert data["project_id"] is None


def test_rename_missing_or_foreign_conversation_returns_404(client, test_db):
    db, _, other_user = test_db
    foreign = _make_conversation(db, other_user, "Not yours")

    assert client.patch("/conversations/9999", json={"title": "x"}).status_code == 404
    assert client.patch(f"/conversations/{foreign.id}", json={"title": "Hijacked"}).status_code == 404
    db.refresh(foreign)
    assert foreign.title == "Not yours"


def test_delete_conversation_removes_it_and_its_messages(client, test_db):
    db, user, _ = test_db
    conversation = _make_conversation(db, user)
    kept = _make_conversation(db, user, "Other chat")
    db.add_all([
        Chat(user_id=user.id, conversation_id=conversation.id, user_message="q", ai_response="a"),
        Chat(user_id=user.id, conversation_id=kept.id, user_message="q2", ai_response="a2"),
    ])
    db.commit()

    response = client.delete(f"/conversations/{conversation.id}")

    assert response.status_code == 204
    assert client.get(f"/conversations/{conversation.id}").status_code == 404
    remaining = db.query(Chat).all()
    assert [chat.user_message for chat in remaining] == ["q2"]
    assert client.get(f"/conversations/{kept.id}").status_code == 200


def test_delete_missing_or_foreign_conversation_returns_404(client, test_db):
    db, _, other_user = test_db
    foreign = _make_conversation(db, other_user, "Not yours")
    db.add(Chat(user_id=other_user.id, conversation_id=foreign.id, user_message="q", ai_response="a"))
    db.commit()

    assert client.delete("/conversations/9999").status_code == 404
    assert client.delete(f"/conversations/{foreign.id}").status_code == 404
    assert db.query(Conversation).filter(Conversation.id == foreign.id).count() == 1
    assert db.query(Chat).filter(Chat.conversation_id == foreign.id).count() == 1


def test_delete_conversation_keeps_its_project(client, test_db):
    db, user, _ = test_db
    project = client.post("/projects", json={"name": "Keep me"}).json()
    conversation = client.post(
        "/conversations", json={"title": "In project", "project_id": project["id"]}
    ).json()

    assert client.delete(f"/conversations/{conversation['id']}").status_code == 204
    assert client.get(f"/projects/{project['id']}").status_code == 200
    assert client.get(f"/conversations?project_id={project['id']}").json() == []
