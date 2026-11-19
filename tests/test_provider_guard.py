"""Groq-only production guard: startup validation, call-time guard, no provider fallback."""

import sys
import types
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.ai.provider import get_ai_client
from src.config.settings import Settings
from src.config.settings import settings as live_settings
from src.services import ai_service

FAKE_SECRET = "unit-test-secret-" + "k" * 30
FAKE_GROQ_KEY = "fake-groq-key-for-tests"
FAKE_OPENAI_KEY = "fake-openai-key-for-tests"


@pytest.fixture(autouse=True)
def clean_settings_env(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)


def make(**overrides):
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


def make_prod(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql://app:pw@db.example.com/latz",
        "CORS_ORIGINS": "https://latz.example.com",
        "GROQ_API_KEY": FAKE_GROQ_KEY,
    }
    values.update(overrides)
    return make(**values)


class ExplodingModule(types.ModuleType):
    """Stands in for a provider client module; touching its client fails the test."""

    def __getattr__(self, name):
        if name == "client":
            raise AssertionError(f"{self.__name__}.client must not be used")
        raise AttributeError(name)


# ------------------------------------------------------------- startup validation
def test_groq_is_allowed_in_production():
    assert make_prod().AI_PROVIDER == "groq"
    assert make_prod(AI_PROVIDER="  GROQ  ").AI_PROVIDER.strip().lower() == "groq"


@pytest.mark.parametrize("extra", [{}, {"OPENAI_API_KEY": FAKE_OPENAI_KEY}, {"AI_ENABLED": False}, {"AI_ENABLED": False, "OPENAI_API_KEY": FAKE_OPENAI_KEY}])
def test_openai_is_rejected_in_production_with_or_without_a_key_and_even_with_ai_off(extra):
    with pytest.raises(ValidationError) as exc:
        make_prod(AI_PROVIDER="openai", **extra)
    message = str(exc.value)
    assert "AI_PROVIDER must be groq" in message
    assert FAKE_OPENAI_KEY not in message and FAKE_GROQ_KEY not in message  # no secret echoed


@pytest.mark.parametrize("provider", ["mystery", "", "OpenAI", " openai "])
def test_any_other_provider_value_fails_production_startup(provider):
    with pytest.raises(ValidationError, match="AI_PROVIDER must be groq"):
        make_prod(AI_PROVIDER=provider)


def test_groq_in_production_still_needs_its_key_when_ai_is_enabled():
    with pytest.raises(ValidationError, match="GROQ_API_KEY is required"):
        make_prod(GROQ_API_KEY="", AI_ENABLED=True)
    assert make_prod(GROQ_API_KEY="", AI_ENABLED=False).AI_ENABLED is False


def test_development_behaviour_is_preserved():
    assert make(AI_PROVIDER="openai").AI_PROVIDER == "openai"
    assert make(AI_PROVIDER="groq").AI_PROVIDER == "groq"


# ------------------------------------------------------------- call-time guard
def test_get_ai_client_rejects_openai_in_production_without_loading_the_client(monkeypatch):
    monkeypatch.setattr(live_settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(live_settings, "AI_PROVIDER", "openai")
    monkeypatch.setitem(sys.modules, "src.ai.openai_client", ExplodingModule("src.ai.openai_client"))
    with pytest.raises(ValueError, match="not permitted in production"):
        get_ai_client()


def test_get_ai_client_rejects_unknown_provider_in_production(monkeypatch):
    monkeypatch.setattr(live_settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(live_settings, "AI_PROVIDER", "mystery")
    with pytest.raises(ValueError, match="not permitted in production"):
        get_ai_client()


def test_get_ai_client_returns_groq_in_production(monkeypatch):
    fake = types.ModuleType("src.ai.groq_client")
    fake.client = MagicMock(name="groq")
    monkeypatch.setattr(live_settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(live_settings, "AI_PROVIDER", "groq")
    monkeypatch.setitem(sys.modules, "src.ai.groq_client", fake)
    assert get_ai_client() is fake.client


def test_development_can_still_select_openai(monkeypatch):
    fake = types.ModuleType("src.ai.openai_client")
    fake.client = MagicMock(name="openai")
    monkeypatch.setattr(live_settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(live_settings, "AI_PROVIDER", "openai")
    monkeypatch.setitem(sys.modules, "src.ai.openai_client", fake)
    assert get_ai_client() is fake.client


# ------------------------------------------------------------ no automatic fallback
def failing_groq_module():
    module = types.ModuleType("src.ai.groq_client")
    module.client = MagicMock(name="groq")
    module.client.chat.completions.create.side_effect = RuntimeError("groq is down")
    return module


@pytest.fixture
def groq_down_openai_forbidden(monkeypatch):
    monkeypatch.setattr(live_settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(live_settings, "AI_PROVIDER", "groq")
    monkeypatch.setitem(sys.modules, "src.ai.groq_client", failing_groq_module())
    monkeypatch.setitem(sys.modules, "src.ai.openai_client", ExplodingModule("src.ai.openai_client"))
    monkeypatch.setattr(ai_service, "get_relevant_context", lambda **kw: {"memories": [], "life_roles": [], "goals": []})
    monkeypatch.setattr(ai_service, "build_messages", lambda **kw: [{"role": "user", "content": "hi"}])


def test_non_streaming_provider_failure_does_not_fall_back_to_another_provider(groq_down_openai_forbidden):
    with pytest.raises(RuntimeError, match="groq is down"):
        ai_service.chat_with_ai(message="hi")


def test_streaming_provider_failure_does_not_fall_back_to_another_provider(groq_down_openai_forbidden):
    with pytest.raises(RuntimeError, match="groq is down"):
        list(ai_service.stream_chat_with_ai(message="hi"))
