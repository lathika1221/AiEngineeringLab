"""Per-account rate limiting and account-bucket independence.

Real JWTs for two users, in-memory SQLite, the AI provider replaced by a stub.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.api.routes import ai as ai_routes
from src.auth.hash import hash_password
from src.config.settings import settings
from src.database.base import Base
from src.database.session import get_db
from src.models import User

PW = {"alice": "Alice-Test-Password-1", "bob": "Bob-Test-Password-22"}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    monkeypatch.setattr(settings, "TRUSTED_CLIENT_IP_HEADER", "x-real-ip")  # as in production
    monkeypatch.setattr(settings, "RATE_LIMIT_AI_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_PER_MINUTE", 3)
    monkeypatch.setattr(ai_routes, "chat_with_ai", lambda **kw: "stub reply")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
            yield client
    finally:
        app.dependency_overrides.clear()
        db.close()


def login(client, name, password=None, ip="198.51.100.1"):
    return client.post(
        "/auth/login",
        data={"username": name, "password": password or PW[name]},
        headers={"X-Real-IP": ip},
    )


def headers(client, name, ip="198.51.100.1"):
    r = login(client, name, ip=ip)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def chat(client, h, ip="198.51.100.1"):
    return client.post("/ai/chat", json={"message": "hi"}, headers={**h, "X-Real-IP": ip})


def test_ai_limit_is_per_account_not_shared(env):
    a, b = headers(env, "alice"), headers(env, "bob")
    assert [chat(env, a).status_code for _ in range(3)] == [200, 200, 429]
    # Same client address, different account: untouched by alice's limit.
    assert chat(env, b).status_code == 200


def test_ai_limit_follows_the_account_across_addresses(env):
    a = headers(env, "alice")
    assert chat(env, a, ip="198.51.100.10").status_code == 200
    assert chat(env, a, ip="198.51.100.11").status_code == 200
    # Switching address does not buy a fresh allowance.
    assert chat(env, a, ip="198.51.100.12").status_code == 429


def test_ai_limit_response_carries_retry_after_and_no_account_detail(env):
    a = headers(env, "alice")
    for _ in range(2):
        chat(env, a)
    r = chat(env, a)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert "alice" not in r.text.lower()


def test_stream_and_chat_share_one_per_account_bucket(env):
    a = headers(env, "alice")
    assert chat(env, a).status_code == 200
    assert chat(env, a).status_code == 200
    r = env.post("/ai/chat/stream", json={"message": "hi"}, headers=a)
    assert r.status_code == 429


def test_wrong_passwords_for_one_account_do_not_lock_out_another(env):
    for _ in range(3):
        assert login(env, "alice", "wrong-password-x", ip="198.51.100.20").status_code == 401
    assert login(env, "alice", "wrong-password-x", ip="198.51.100.20").status_code == 429
    # Bob, from another address, is unaffected.
    assert login(env, "bob", ip="198.51.100.21").status_code == 200


def test_the_account_owner_is_not_locked_out_by_an_attacker_elsewhere(env):
    """No per-account lockout exists, so an attacker cannot lock alice out of her own account."""
    for _ in range(3):
        login(env, "alice", "wrong-password-x", ip="203.0.113.50")
    assert login(env, "alice", ip="198.51.100.22").status_code == 200


def test_known_limitation_guesses_spread_over_addresses_are_not_throttled_per_account(env):
    """Characterization, not a goal: the login limit is per client address only. A caller
    that rotates addresses can try one password per address against one account without
    ever seeing 429. Bounded in practice by bcrypt cost and the 12-72 byte password policy,
    and listed as a launch gate in docs/OPERATIONS.md."""
    statuses = [login(env, "alice", "wrong-password-x", ip=f"203.0.113.{i}").status_code for i in range(1, 9)]
    assert statuses == [401] * 8


def test_login_and_ai_buckets_are_independent(env):
    for _ in range(3):
        login(env, "alice", "wrong-password-x", ip="198.51.100.30")
    assert login(env, "alice", ip="198.51.100.30").status_code == 429
    a = headers(env, "alice", ip="198.51.100.31")
    assert chat(env, a, ip="198.51.100.30").status_code == 200
