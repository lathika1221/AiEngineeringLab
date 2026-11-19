import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.ai.provider as ai_provider
import src.api.routes.ai as ai_routes
import src.services.ai_service as ai_service
from src.api.main import app
from src.auth.dependencies import get_current_user
from src.config.settings import Settings, parse_origins
from src.config.settings import settings as live_settings
from src.database.base import Base
from src.database.session import get_db
from src.models import User

REPO_ROOT = Path(__file__).resolve().parent.parent

# Obviously fake values, built only for these tests.
FAKE_SECRET = "unit-test-secret-" + "k" * 30
FAKE_PROVIDER_KEY = "fake-provider-key-for-tests"


@pytest.fixture(autouse=True)
def isolated_settings_env(monkeypatch):
    """Settings reads os.environ; clear every setting so only explicit test values count."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)


def dev_settings(**overrides):
    values = {
        "PROJECT_NAME": "LATZ Test",
        "VERSION": "0.0.1",
        "DATABASE_URL": "sqlite://",
        "SECRET_KEY": FAKE_SECRET,
        "ACCESS_TOKEN_EXPIRE_MINUTES": 30,
        "AI_PROVIDER": "groq",
        "MODEL_NAME": "test-model",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def prod_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql://app:pw@db.example.com/latz",
        "CORS_ORIGINS": "https://latz.example.com",
        "GROQ_API_KEY": FAKE_PROVIDER_KEY,
    }
    values.update(overrides)
    return dev_settings(**values)


# ---------------------------------------------------------------- development
def test_development_is_the_default_and_keeps_local_behaviour():
    s = dev_settings()
    assert s.ENVIRONMENT == "development"
    assert s.is_production is False
    assert s.DEBUG is False
    assert s.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert s.docs_enabled is True
    assert s.REGISTRATION_ENABLED is True
    assert s.AI_ENABLED is True


def test_development_does_not_require_provider_key_or_postgres():
    s = dev_settings(GROQ_API_KEY="", DATABASE_URL="sqlite://")
    assert s.GROQ_API_KEY == ""


def test_environment_value_is_case_insensitive_and_strict():
    assert dev_settings(ENVIRONMENT="DEVELOPMENT ").ENVIRONMENT == "development"
    with pytest.raises(ValidationError):
        dev_settings(ENVIRONMENT="staging")


def test_quota_settings_have_defaults_and_validate_range():
    s = dev_settings()
    assert s.AI_DAILY_REQUESTS_GLOBAL >= 1 and s.AI_MAX_CONCURRENT_STREAMS >= 1
    with pytest.raises(ValidationError):
        dev_settings(AI_DAILY_REQUESTS_PER_USER=0)


# ----------------------------------------------------------------- production
def test_valid_production_configuration_is_accepted():
    s = prod_settings()
    assert s.is_production is True
    assert s.DEBUG is False
    assert s.cors_origins == ["https://latz.example.com"]


def test_docs_are_off_by_default_in_production_and_can_be_enabled_explicitly():
    assert prod_settings().docs_enabled is False
    assert prod_settings(ENABLE_DOCS=True).docs_enabled is True
    assert dev_settings(ENABLE_DOCS=False).docs_enabled is False


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"DEBUG": True}, "DEBUG must be false"),
        ({"CORS_ORIGINS": "http://latz.example.com"}, "https://"),
        ({"CORS_ORIGINS": "http://localhost:5173"}, "https://"),
        ({"DATABASE_URL": "sqlite://"}, "not SQLite"),
        ({"DATABASE_URL": "postgres://app:pw@db.example.com/latz"}, "postgresql://"),
        ({"DATABASE_URL": "mysql://app:pw@db.example.com/latz"}, "PostgreSQL"),
        ({"DATABASE_URL": "postgresql://USER:PASSWORD@localhost/latz"}, "placeholder"),
        ({"GROQ_API_KEY": "", "AI_ENABLED": True}, "GROQ_API_KEY is required"),
        ({"GROQ_API_KEY": "   ", "AI_ENABLED": True}, "GROQ_API_KEY is required"),
        ({"AI_PROVIDER": "openai"}, "AI_PROVIDER must be groq"),
        ({"AI_PROVIDER": "mystery"}, "AI_PROVIDER must be groq"),
        ({"MODEL_NAME": ""}, "MODEL_NAME"),
        ({"MODEL_NAME": "replace-with-a-model-name"}, "MODEL_NAME"),
    ],
)
def test_production_rejects_unsafe_or_incomplete_configuration(overrides, expected):
    with pytest.raises(ValidationError) as exc:
        prod_settings(**overrides)
    assert expected in str(exc.value)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://app:pw@db.example.com/latz",
        "postgresql://app:pw@db.example.com/latz?sslmode=require",
        "postgresql+psycopg2://app:pw@db.example.com/latz",
        "postgresql+psycopg2://app:pw@db.example.com/latz?sslmode=require",
    ],
)
def test_production_accepts_only_supported_postgresql_schemes(url):
    assert prod_settings(DATABASE_URL=url).DATABASE_URL == url


@pytest.mark.parametrize(
    "url, expected",
    [
        ("postgresql+asyncpg://app:pw@db.example.com/latz", "postgresql+psycopg2://"),
        ("postgresql+psycopg://app:pw@db.example.com/latz", "postgresql+psycopg2://"),
        ("postgresql+pg8000://app:pw@db.example.com/latz", "postgresql+psycopg2://"),
        ("postgresqlfoo://app:pw@db.example.com/latz", "postgresql+psycopg2://"),
        ("postgresql+psycopg2foo://app:pw@db.example.com/latz", "postgresql+psycopg2://"),
        ("POSTGRESQL://app:pw@db.example.com/latz", "postgresql+psycopg2://"),
        ("PostgreSQL+Psycopg2://app:pw@db.example.com/latz", "postgresql+psycopg2://"),
        ("postgres://app:pw@db.example.com/latz", "not postgres://"),
        ("postgres+psycopg2://app:pw@db.example.com/latz", "postgresql+psycopg2://"),
        ("mysql://app:pw@db.example.com/latz", "postgresql+psycopg2://"),
        ("mysql+pymysql://app:pw@db.example.com/latz", "postgresql+psycopg2://"),
        ("sqlite://", "not SQLite"),
        ("sqlite:///./latz.db", "not SQLite"),
        ("SQLite:///./latz.db", "not SQLite"),
        ("db.example.com/latz", "postgresql+psycopg2://"),
        ("", "postgresql+psycopg2://"),
    ],
)
def test_production_rejects_unsupported_database_schemes(url, expected):
    with pytest.raises(ValidationError) as exc:
        prod_settings(DATABASE_URL=url)
    assert expected in str(exc.value)


def test_rejected_database_url_credentials_are_not_echoed():
    secret = "SENTINEL-db-password-for-test"
    with pytest.raises(ValidationError) as exc:
        prod_settings(DATABASE_URL=f"postgresql+asyncpg://app:{secret}@db.example.com/latz")
    assert secret not in str(exc.value)


def test_development_still_accepts_any_database_url():
    assert dev_settings(DATABASE_URL="sqlite:///./local.db").DATABASE_URL == "sqlite:///./local.db"
    assert dev_settings(DATABASE_URL="postgresql+asyncpg://u:p@localhost/x").DATABASE_URL.startswith("postgresql+asyncpg")


def test_production_requires_cors_origins_to_be_set_explicitly():
    values = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql://app:pw@db.example.com/latz",
        "GROQ_API_KEY": FAKE_PROVIDER_KEY,
    }
    with pytest.raises(ValidationError) as exc:
        dev_settings(**values)
    assert "CORS_ORIGINS must be set explicitly" in str(exc.value)


def test_production_reports_every_problem_at_once():
    with pytest.raises(ValidationError) as exc:
        prod_settings(DEBUG=True, DATABASE_URL="sqlite://", GROQ_API_KEY="", AI_ENABLED=True)
    message = str(exc.value)
    assert "DEBUG must be false" in message
    assert "not SQLite" in message
    assert "GROQ_API_KEY is required" in message


def test_provider_key_not_required_when_ai_is_disabled():
    assert prod_settings(GROQ_API_KEY="", AI_ENABLED=False).AI_ENABLED is False


# ------------------------------------------- production feature-flag defaults (L1)
def test_production_with_both_flags_absent_defaults_both_off():
    s = prod_settings()
    assert s.AI_ENABLED is False
    assert s.REGISTRATION_ENABLED is False


def test_production_with_both_flags_absent_needs_no_provider_key():
    # AI is off by default, so the provider-key rule does not apply.
    assert prod_settings(GROQ_API_KEY="").AI_ENABLED is False


def test_production_with_both_flags_explicitly_false_stays_off():
    s = prod_settings(AI_ENABLED=False, REGISTRATION_ENABLED=False)
    assert (s.AI_ENABLED, s.REGISTRATION_ENABLED) == (False, False)


def test_production_explicit_true_is_the_opt_in_and_is_respected():
    # Policy: production never enables either feature implicitly, but an explicit true is
    # honoured (that is how AI is turned on later, in a reviewed render.yaml change).
    s = prod_settings(AI_ENABLED=True, REGISTRATION_ENABLED=True)
    assert (s.AI_ENABLED, s.REGISTRATION_ENABLED) == (True, True)


def test_production_explicit_ai_true_still_requires_the_provider_key():
    with pytest.raises(ValidationError) as exc:
        prod_settings(AI_ENABLED=True, GROQ_API_KEY="")
    assert "GROQ_API_KEY is required" in str(exc.value)


def test_production_flags_are_independent_of_each_other():
    only_ai = prod_settings(AI_ENABLED=True)
    assert (only_ai.AI_ENABLED, only_ai.REGISTRATION_ENABLED) == (True, False)
    only_reg = prod_settings(REGISTRATION_ENABLED=True)
    assert (only_reg.AI_ENABLED, only_reg.REGISTRATION_ENABLED) == (False, True)


@pytest.mark.parametrize("raw,expected", [("true", True), ("false", False), ("1", True), ("0", False)])
def test_production_flags_read_from_the_environment_are_explicit(monkeypatch, raw, expected):
    monkeypatch.setenv("AI_ENABLED", raw)
    monkeypatch.setenv("REGISTRATION_ENABLED", raw)
    s = prod_settings(GROQ_API_KEY=FAKE_PROVIDER_KEY)
    assert (s.AI_ENABLED, s.REGISTRATION_ENABLED) == (expected, expected)


def test_production_absent_environment_flags_default_off(monkeypatch):
    monkeypatch.delenv("AI_ENABLED", raising=False)
    monkeypatch.delenv("REGISTRATION_ENABLED", raising=False)
    s = prod_settings()
    assert (s.AI_ENABLED, s.REGISTRATION_ENABLED) == (False, False)


def test_production_invalid_flag_value_is_rejected_not_defaulted():
    with pytest.raises(ValidationError):
        prod_settings(AI_ENABLED="maybe")


def test_development_flags_keep_their_defaults_and_explicit_values():
    assert (dev_settings().AI_ENABLED, dev_settings().REGISTRATION_ENABLED) == (True, True)
    off = dev_settings(AI_ENABLED=False, REGISTRATION_ENABLED=False)
    assert (off.AI_ENABLED, off.REGISTRATION_ENABLED) == (False, False)


def test_other_production_settings_are_not_changed_by_the_flag_defaults():
    s = prod_settings()
    assert s.ENABLE_DOCS is None and s.docs_enabled is False
    assert s.TRUSTED_PROXY_COUNT == 0
    assert s.DEBUG is False


def test_render_blueprint_sets_both_flags_explicitly_false():
    text = (REPO_ROOT / "render.yaml").read_text()
    for name in ("AI_ENABLED", "REGISTRATION_ENABLED"):
        i = text.index(f"key: {name}")
        assert 'value: "false"' in text[i : i + 120]


def test_missing_required_secret_gives_a_clear_error():
    values = {
        "PROJECT_NAME": "LATZ Test",
        "VERSION": "0.0.1",
        "DATABASE_URL": "postgresql://app:pw@db.example.com/latz",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 30,
        "AI_PROVIDER": "groq",
        "MODEL_NAME": "test-model",
        "ENVIRONMENT": "production",
        "CORS_ORIGINS": "https://latz.example.com",
        "GROQ_API_KEY": FAKE_PROVIDER_KEY,
    }
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, **values)  # no SECRET_KEY
    assert "SECRET_KEY" in str(exc.value) and "Field required" in str(exc.value)


@pytest.mark.parametrize("secret", ["replace-with-a-long-random-value-of-at-least-32-characters", "change-me"])
def test_example_placeholder_secret_is_rejected(secret):
    with pytest.raises(ValidationError):
        prod_settings(SECRET_KEY=secret)


def test_validation_errors_never_echo_secret_values():
    with pytest.raises(ValidationError) as exc:
        prod_settings(DEBUG=True, SECRET_KEY="short-secret-VALUE", GROQ_API_KEY="")
    message = str(exc.value)
    assert "short-secret-VALUE" not in message
    assert FAKE_SECRET not in message


# ----------------------------------------------------------------------- CORS
def test_cors_parsing_normalises_and_deduplicates():
    assert parse_origins(" https://a.example.com/ , https://a.example.com,http://localhost:5173 ,") == [
        "https://a.example.com",
        "http://localhost:5173",
    ]


@pytest.mark.parametrize("bad", ["*", "https://a.example.com,*", "example.com", "ftp://a.example.com", "https://a.example.com/app"])
def test_cors_rejects_wildcards_and_malformed_origins_in_any_environment(bad):
    with pytest.raises(ValidationError):
        dev_settings(CORS_ORIGINS=bad)


# ------------------------------------------- the real app under each environment
def run_app_probe(env_overrides):
    """Import the real app in a clean process (no .env file, controlled env)."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(REPO_ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PROJECT_NAME": "LATZ Test",
        "VERSION": "0.0.1",
        "DATABASE_URL": "sqlite://",
        "SECRET_KEY": FAKE_SECRET,
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "AI_PROVIDER": "groq",
        "MODEL_NAME": "test-model",
    }
    env.update(env_overrides)
    code = (
        "import json\n"
        "from src.api.main import app\n"
        "from starlette.middleware.cors import CORSMiddleware\n"
        "cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)\n"
        "print(json.dumps({'docs': app.docs_url, 'redoc': app.redoc_url, 'openapi': app.openapi_url,"
        " 'origins': cors.kwargs['allow_origins']}))\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT / "tests",  # not the repo root, so a developer's real .env is never read
        env=env,
        capture_output=True,
        text=True,
    )


def test_app_in_development_exposes_docs_and_local_cors():
    result = run_app_probe({})
    assert result.returncode == 0, result.stderr[-500:]
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data["docs"] == "/docs" and data["openapi"] == "/openapi.json"
    assert data["origins"] == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_app_in_production_hides_docs_and_uses_configured_origins():
    result = run_app_probe(
        {
            "ENVIRONMENT": "production",
            "DATABASE_URL": "postgresql://app:pw@db.example.com/latz",
            "CORS_ORIGINS": "https://latz.example.com,https://app.example.com",
            "GROQ_API_KEY": FAKE_PROVIDER_KEY,
        }
    )
    assert result.returncode == 0, result.stderr[-500:]
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data["docs"] is None and data["redoc"] is None and data["openapi"] is None
    assert data["origins"] == ["https://latz.example.com", "https://app.example.com"]


def test_app_refuses_to_start_in_production_without_required_secrets():
    result = run_app_probe(
        {
            "ENVIRONMENT": "production",
            "DATABASE_URL": "postgresql://app:pw@db.example.com/latz",
            "CORS_ORIGINS": "https://latz.example.com",
            "AI_ENABLED": "true",  # AI is off by default in production, so enable it explicitly
            # no GROQ_API_KEY
        }
    )
    assert result.returncode != 0
    assert "GROQ_API_KEY is required" in result.stderr
    assert FAKE_SECRET not in result.stderr


# ------------------------------------------------------------ feature switches
@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client_with_user():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    setup = Session()
    user = User(username="control_user", email="control@example.com", hashed_password="not-a-real-hash")
    setup.add(user)
    setup.commit()

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()
    setup.close()


REGISTER_BODY = {"username": "switch_user", "email": "switch@example.com", "password": "a-long-enough-password"}


def test_registration_switch_closes_signups_only(client, monkeypatch):
    monkeypatch.setattr(live_settings, "REGISTRATION_ENABLED", False)
    closed = client.post("/auth/register", json=REGISTER_BODY)
    assert closed.status_code == 403
    assert "closed" in closed.json()["detail"].lower()


def test_registration_is_open_by_default(client):
    assert client.post("/auth/register", json=REGISTER_BODY).status_code == 200


@pytest.fixture
def provider_spies(monkeypatch):
    """Spy on every function between the route and the AI provider; none may reach the network."""
    spies = SimpleNamespace(
        chat_with_ai=Mock(return_value="stub reply"),
        stream_chat_with_ai=Mock(side_effect=lambda **kwargs: iter(["stub"])),
        service_get_ai_client=Mock(side_effect=AssertionError("provider client requested")),
        provider_get_ai_client=Mock(side_effect=AssertionError("provider client requested")),
    )
    monkeypatch.setattr(ai_routes, "chat_with_ai", spies.chat_with_ai)
    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", spies.stream_chat_with_ai)
    monkeypatch.setattr(ai_service, "get_ai_client", spies.service_get_ai_client)
    monkeypatch.setattr(ai_provider, "get_ai_client", spies.provider_get_ai_client)
    return spies


def assert_provider_untouched(spies):
    spies.chat_with_ai.assert_not_called()
    spies.stream_chat_with_ai.assert_not_called()
    spies.service_get_ai_client.assert_not_called()
    spies.provider_get_ai_client.assert_not_called()


@pytest.mark.parametrize("path", ["/ai/chat", "/ai/chat/stream"])
def test_ai_switch_blocks_model_routes_before_any_model_call(client, monkeypatch, provider_spies, path):
    monkeypatch.setattr(live_settings, "AI_ENABLED", False)
    response = client.post(path, json={"message": "hello"})
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()
    assert_provider_untouched(provider_spies)


@pytest.mark.parametrize("path", ["/ai/chat", "/ai/chat/stream"])
def test_ai_switch_blocks_even_unauthenticated_requests_without_calling_the_provider(client, monkeypatch, provider_spies, path):
    app.dependency_overrides.pop(get_current_user, None)
    monkeypatch.setattr(live_settings, "AI_ENABLED", False)
    response = client.post(path, json={"message": "hello"})
    assert response.status_code == 503
    assert_provider_untouched(provider_spies)


@pytest.mark.parametrize(
    "path, spy_name",
    [("/ai/chat", "chat_with_ai"), ("/ai/chat/stream", "stream_chat_with_ai")],
)
def test_ai_routes_do_reach_the_provider_function_when_enabled(client_with_user, monkeypatch, provider_spies, path, spy_name):
    """Control: proves the spies are wired to the real call path, so the blocked-case assertions mean something."""
    monkeypatch.setattr(live_settings, "AI_ENABLED", True)
    response = client_with_user.post(path, json={"message": "hello"})
    assert response.status_code == 200
    getattr(provider_spies, spy_name).assert_called_once()


def test_ai_switch_does_not_block_non_model_routes(client, monkeypatch):
    monkeypatch.setattr(live_settings, "AI_ENABLED", False)
    assert client.get("/health/").status_code == 200
