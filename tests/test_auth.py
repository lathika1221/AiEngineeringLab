import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.auth.dependencies import get_current_user
from src.auth.hash import hash_password, verify_password
from src.config.settings import settings
from src.database.base import Base
from src.database.session import get_db
from src.models.user import User


@pytest.fixture
def auth_client(request):
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

    def override_get_db():
        yield db

    def override_get_current_user():
        user = db.query(User).filter(
            User.email == "test@example.com"
        ).first()
        if user is None:
            user = User(
                username="testuser",
                email="test@example.com",
                hashed_password=hash_password("TestPassword123!"),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    app.dependency_overrides[get_db] = override_get_db
    if request.node.get_closest_marker("authenticated_test"):
        app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        with TestClient(app) as client:
            yield client, db
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_password_hash_is_not_plaintext():
    password = "SecureTestPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("WrongPassword123!", hashed)


def test_register_user(auth_client):
    client, db = auth_client

    response = client.post(
        "/auth/register",
        json={
            "username": "latz_test",
            "email": "latz_test@example.com",
            "password": "SecureTestPassword123!",
        },
    )

    assert response.status_code == 200
    assert "hashed_password" not in response.json()

    user = db.query(User).filter(
        User.email == "latz_test@example.com"
    ).one()
    assert verify_password(
        "SecureTestPassword123!",
        user.hashed_password,
    )


def test_duplicate_registration_is_rejected(auth_client):
    client, _ = auth_client
    payload = {
        "username": "latz_test",
        "email": "latz_test@example.com",
        "password": "SecureTestPassword123!",
    }

    assert client.post("/auth/register", json=payload).status_code == 200
    assert client.post("/auth/register", json=payload).status_code == 400


def test_login_returns_valid_bearer_token(auth_client):
    client, _ = auth_client
    client.post(
        "/auth/register",
        json={
            "username": "latz_test",
            "email": "latz_test@example.com",
            "password": "SecureTestPassword123!",
        },
    )

    response = client.post(
        "/auth/login",
        data={
            "username": "latz_test",
            "password": "SecureTestPassword123!",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"

    payload = jwt.decode(
        data["access_token"],
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
    assert payload["sub"] == "latz_test@example.com"
    assert "exp" in payload


def test_login_rejects_wrong_password(auth_client):
    client, _ = auth_client
    client.post(
        "/auth/register",
        json={
            "username": "latz_test",
            "email": "latz_test@example.com",
            "password": "SecureTestPassword123!",
        },
    )

    response = client.post(
        "/auth/login",
        data={
            "username": "latz_test",
            "password": "IncorrectPassword123!",
        },
    )

    assert response.status_code == 401


def test_protected_endpoint_rejects_missing_token(auth_client):
    client, _ = auth_client

    response = client.get("/projects")

    assert response.status_code == 401


def test_protected_endpoint_rejects_invalid_token(auth_client):
    client, _ = auth_client

    response = client.get(
        "/projects",
        headers={"Authorization": "Bearer invalid.token.value"},
    )

    assert response.status_code == 401


def test_current_user_rejects_token_without_subject(auth_client):
    client, _ = auth_client
    token = jwt.encode(
        {"role": "user"},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    response = client.get(
        "/projects",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401

def test_expired_token_is_rejected(auth_client):
    client, _ = auth_client
    from datetime import datetime, timedelta, timezone

    token = jwt.encode(
        {
            "sub": "test@example.com",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    response = client.get(
        "/projects",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.authenticated_test
def test_user_cannot_access_another_users_project(auth_client):
    client, db = auth_client
    from src.models.project import Project

    owner = User(
        username="project_owner",
        email="owner@example.com",
        hashed_password=hash_password("OwnerPassword123!"),
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    project = Project(
        user_id=owner.id,
        name="Private project",
        description="Must remain private",
        status="active",
        engine="forge",
        tech_stack="Python",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    response = client.get(f"/projects/{project.id}")

    assert response.status_code == 404


@pytest.mark.authenticated_test
def test_user_cannot_access_another_users_conversation(auth_client):
    client, db = auth_client
    from src.models.conversation import Conversation

    owner = User(
        username="conversation_owner",
        email="conversation_owner@example.com",
        hashed_password=hash_password("OwnerPassword123!"),
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    conversation = Conversation(
        user_id=owner.id,
        title="Private conversation",
        category="general",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    response = client.get(f"/conversations/{conversation.id}")

    assert response.status_code == 404


def test_registration_rejects_short_password(auth_client):
    client, _ = auth_client
    response = client.post(
        "/auth/register",
        json={
            "username": "short_password",
            "email": "short@example.com",
            "password": "short",
        },
    )
    assert response.status_code == 422


def test_registration_rejects_password_over_72_utf8_bytes(auth_client):
    client, _ = auth_client
    response = client.post(
        "/auth/register",
        json={
            "username": "long_password",
            "email": "long@example.com",
            "password": "a" * 73,
        },
    )
    assert response.status_code == 422


def test_registration_accepts_12_byte_password(auth_client):
    client, _ = auth_client
    response = client.post(
        "/auth/register",
        json={
            "username": "valid_password",
            "email": "valid@example.com",
            "password": "Abcdef123456",
        },
    )
    assert response.status_code == 200
