import sys
import types
from unittest.mock import MagicMock

import pytest

from src.ai.provider import get_ai_client
from src.config.settings import settings


def test_groq_provider_selection(monkeypatch):
    fake_client = MagicMock()
    fake_module = types.ModuleType("src.ai.groq_client")
    fake_module.client = fake_client

    monkeypatch.setattr(settings, "AI_PROVIDER", "groq")
    monkeypatch.setitem(sys.modules, "src.ai.groq_client", fake_module)

    assert get_ai_client() is fake_client


def test_openai_provider_selection_without_real_api_call(monkeypatch):
    fake_client = MagicMock()
    fake_module = types.ModuleType("src.ai.openai_client")
    fake_module.client = fake_client

    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setitem(sys.modules, "src.ai.openai_client", fake_module)

    assert get_ai_client() is fake_client


def test_provider_name_is_case_insensitive(monkeypatch):
    fake_client = MagicMock()
    fake_module = types.ModuleType("src.ai.groq_client")
    fake_module.client = fake_client

    monkeypatch.setattr(settings, "AI_PROVIDER", "  GROQ  ")
    monkeypatch.setitem(sys.modules, "src.ai.groq_client", fake_module)

    assert get_ai_client() is fake_client


def test_unsupported_provider_raises_error(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "unsupported")

    with pytest.raises(ValueError, match="Unsupported AI_PROVIDER"):
        get_ai_client()
