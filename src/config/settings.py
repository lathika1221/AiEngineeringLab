from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str
    VERSION: str
    DEBUG: bool

    HOST: str
    PORT: int

    DATABASE_URL: str

    SECRET_KEY: str = Field(min_length=32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(ge=1, le=1440)

    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    AI_PROVIDER: str
    MODEL_NAME: str

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        normalized = value.strip()

        if len(normalized) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 non-whitespace characters")

        if normalized.lower() in {
            "your-secret-key",
            "change-me",
            "secret",
            "changeme",
        }:
            raise ValueError("SECRET_KEY must not be a placeholder")

        return normalized

    @field_validator("ALGORITHM")
    @classmethod
    def validate_algorithm(cls, value: str) -> str:
        if value != "HS256":
            raise ValueError("ALGORITHM must be HS256")
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
