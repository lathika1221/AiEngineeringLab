
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
