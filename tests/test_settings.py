import pytest
from pydantic import ValidationError

from src.config.settings import Settings


def make_settings(**overrides):
    values = {
        "DATABASE_URL": "sqlite://",
        "SECRET_KEY": "a" * 32,
        "ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 30,
        "AI_PROVIDER": "groq",
        "MODEL_NAME": "test-model",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_settings_accept_valid_secret():
    settings = make_settings()
    assert settings.SECRET_KEY == "a" * 32


def test_settings_normalize_secret_whitespace():
    settings = make_settings(SECRET_KEY="  " + "a" * 32 + "  ")
    assert settings.SECRET_KEY == "a" * 32


@pytest.mark.parametrize(
    "secret",
    [" " * 40, "a" * 31, "your-secret-key", "change-me"],
)
def test_settings_reject_invalid_secret(secret):
    with pytest.raises(ValidationError):
        make_settings(SECRET_KEY=secret)


def test_settings_reject_unsupported_algorithm():
    with pytest.raises(ValidationError):
        make_settings(ALGORITHM="HS512")


def test_settings_reject_invalid_token_expiry():
    with pytest.raises(ValidationError):
        make_settings(ACCESS_TOKEN_EXPIRE_MINUTES=0)
