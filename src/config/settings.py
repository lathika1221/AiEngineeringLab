from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DEV_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
SUPPORTED_AI_PROVIDERS = ("groq", "openai")
# The only provider allowed when ENVIRONMENT=production (free Groq tier, no paid fallback).
PRODUCTION_AI_PROVIDER = "groq"
# The app is synchronous and psycopg2-binary is the only installed driver.
SUPPORTED_DATABASE_SCHEMES = ("postgresql", "postgresql+psycopg2")


def parse_origins(value: str) -> list[str]:
    """Split a comma-separated origin list and normalise each entry.

    An origin is scheme + host (+ port) only, so a trailing slash is dropped.
    Wildcards are rejected: the API allows credentials, which browsers refuse
    to combine with "*".
    """
    origins: list[str] = []
    for raw in value.split(","):
        origin = raw.strip().rstrip("/")
        if not origin:
            continue
        if origin == "*":
            raise ValueError("CORS_ORIGINS must list explicit origins; '*' is not allowed")
        parsed = urlparse(origin)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
            raise ValueError(
                "CORS_ORIGINS entries must look like https://example.com or http://localhost:5173 "
                "(scheme, host and optional port only)"
            )
        if origin not in origins:
            origins.append(origin)
    return origins


class Settings(BaseSettings):
    # --- Environment ---------------------------------------------------------
    # "development" keeps the local behaviour. "production" turns on strict
    # startup validation (see validate_production below).
    ENVIRONMENT: Literal["development", "production"] = "development"

    PROJECT_NAME: str
    VERSION: str
    DEBUG: bool = False

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    DATABASE_URL: str

    # --- Database connection pool (PostgreSQL only; ignored for SQLite) ------
    # Total connections per process = DB_POOL_SIZE + DB_MAX_OVERFLOW. Multiply
    # by the number of worker processes when sizing against the database's limit.
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=50)
    DB_MAX_OVERFLOW: int = Field(default=5, ge=0, le=50)
    # Seconds after which an idle pooled connection is replaced.
    DB_POOL_RECYCLE: int = Field(default=300, ge=1)
    # Seconds a request waits for a free pooled connection before failing.
    DB_POOL_TIMEOUT: int = Field(default=30, ge=1)
    # Seconds allowed to open a new connection (covers a serverless database waking up).
    DB_CONNECT_TIMEOUT: int = Field(default=10, ge=1)
    # libpq sslmode. Unset = "require" in production and the driver default otherwise.
    # A sslmode written inside DATABASE_URL always wins over this setting.
    DB_SSLMODE: Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"] | None = None

    # --- Web / API surface ---------------------------------------------------
    # Comma-separated list of browser origins allowed to call the API.
    CORS_ORIGINS: str = DEFAULT_DEV_CORS_ORIGINS
    # None = automatic: docs are on in development and off in production.
    ENABLE_DOCS: bool | None = None

    # --- Auth ----------------------------------------------------------------
    SECRET_KEY: str = Field(min_length=32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(ge=1, le=1440)

    # --- AI provider ---------------------------------------------------------
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    AI_PROVIDER: str
    MODEL_NAME: str

    # --- Feature switches (enforced) -----------------------------------------
    # Development default: on. In production an ABSENT value means off (see
    # apply_production_feature_defaults): a production deployment must opt in to
    # sign-ups and to model-backed chat by setting the variable to true explicitly.
    REGISTRATION_ENABLED: bool = True
    AI_ENABLED: bool = True

    # --- Rate limits and AI quotas (enforced; see src/security/) -------------
    # Defaults are deliberately conservative for a shared free AI tier.
    # Per-minute limits are kept in process memory (single instance, reset on restart).
    RATE_LIMIT_AUTH_PER_MINUTE: int = Field(default=10, ge=1)
    RATE_LIMIT_AI_PER_MINUTE: int = Field(default=10, ge=1)
    # Daily quotas are stored in the database (UTC day) and survive restarts.
    AI_DAILY_REQUESTS_PER_USER: int = Field(default=10, ge=1)
    AI_DAILY_REQUESTS_GLOBAL: int = Field(default=80, ge=1)
    AI_DAILY_TOKENS_GLOBAL: int = Field(default=150000, ge=1)
    # Concurrent /ai/chat/stream responses per process (in memory, reset on restart).
    AI_MAX_CONCURRENT_STREAMS: int = Field(default=3, ge=1)
    # Concurrent streams one account may hold, so a single user cannot take every slot.
    AI_MAX_CONCURRENT_STREAMS_PER_USER: int = Field(default=1, ge=1)
    # How many reverse proxies in front of the app append to X-Forwarded-For.
    # 0 = ignore the header and use the socket peer address (safe default; behind a
    # proxy every client then shares the proxy's bucket). N > 0 = take the Nth entry
    # from the RIGHT, which is the one your own proxies wrote; entries further left
    # are client-controlled and never trusted. Set it only after verifying the hop
    # count of your platform.
    TRUSTED_PROXY_COUNT: int = Field(default=0, ge=0, le=5)
    # Header that carries the client address, written by the platform's own edge.
    # "" (default) = trust no header. "x-real-ip" = use exactly one valid X-Real-IP
    # value (Railway's public HTTP edge overwrites it on every request). Only enable
    # it when the app is reachable ONLY through that edge: a request that bypasses the
    # edge (for example over Railway private networking from another service in the
    # same environment, or through a TCP proxy) can send any X-Real-IP it likes.
    # X-Forwarded-For is never consulted in this mode. Not combinable with
    # TRUSTED_PROXY_COUNT > 0 in production.
    TRUSTED_CLIENT_IP_HEADER: Literal["", "x-real-ip"] = ""

    # --- Field validators ----------------------------------------------------
    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def normalize_environment(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("DATABASE_URL")
    @classmethod
    def strip_database_url(cls, value: str) -> str:
        return value.strip()

    @field_validator("DB_SSLMODE", mode="before")
    @classmethod
    def empty_sslmode_means_unset(cls, value):
        if isinstance(value, str):
            value = value.strip().lower()
            return value or None
        return value

    @field_validator("TRUSTED_CLIENT_IP_HEADER", mode="before")
    @classmethod
    def normalize_trusted_client_ip_header(cls, value):
        # Case and surrounding whitespace do not matter; any other value is rejected
        # by the Literal type ("", "x-real-ip") instead of being silently ignored.
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        parse_origins(value)
        return value

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
        } or normalized.lower().startswith("replace-with"):
            raise ValueError("SECRET_KEY must not be a placeholder")

        return normalized

    @field_validator("ALGORITHM")
    @classmethod
    def validate_algorithm(cls, value: str) -> str:
        if value != "HS256":
            raise ValueError("ALGORITHM must be HS256")
        return value

    # --- Production validation ----------------------------------------------
    # Runs before validate_production (validators run in definition order) so the
    # provider-key rule below sees the final AI_ENABLED value.
    @model_validator(mode="after")
    def apply_production_feature_defaults(self):
        """Fail closed: in production, REGISTRATION_ENABLED and AI_ENABLED are false unless
        explicitly set. An explicit value (environment variable or constructor argument,
        true or false) is always respected; only an absent one is changed. Development
        keeps the defaults above."""
        if self.ENVIRONMENT == "production":
            for name in ("REGISTRATION_ENABLED", "AI_ENABLED"):
                if name not in self.model_fields_set:
                    setattr(self, name, False)
        return self

    @model_validator(mode="after")
    def validate_production(self):
        if self.ENVIRONMENT != "production":
            return self

        problems: list[str] = []

        if self.DEBUG:
            problems.append("DEBUG must be false in production")

        origins = parse_origins(self.CORS_ORIGINS)
        if "CORS_ORIGINS" not in self.model_fields_set or not origins:
            problems.append("CORS_ORIGINS must be set explicitly to your frontend origin(s), e.g. https://app.example.com")
        elif any(not origin.startswith("https://") for origin in origins):
            problems.append("CORS_ORIGINS entries must use https:// in production")

        database_url = self.DATABASE_URL.strip()
        # Only the scheme is inspected (and never echoed). SQLAlchemy needs it lower-case.
        scheme = database_url.split("://", 1)[0] if "://" in database_url else ""
        if scheme.lower().startswith("sqlite"):
            problems.append("DATABASE_URL must point to PostgreSQL in production, not SQLite")
        elif scheme.lower() == "postgres":
            problems.append("DATABASE_URL must start with postgresql:// (not postgres://)")
        elif scheme not in SUPPORTED_DATABASE_SCHEMES:
            problems.append(
                "DATABASE_URL must be a PostgreSQL URL starting with "
                + " or ".join(f"{s}://" for s in SUPPORTED_DATABASE_SCHEMES)
                + " in production"
            )
        elif "user:password@" in database_url.lower():
            problems.append("DATABASE_URL still contains the example placeholder credentials")

        if not self.MODEL_NAME.strip() or self.MODEL_NAME.strip().lower().startswith("replace-with"):
            problems.append("MODEL_NAME must be set to a real model identifier")

        # Groq-only guard: the production deployment is limited to the free Groq tier,
        # so any other provider (the paid OpenAI path included) is rejected at startup,
        # whether or not AI is currently enabled. There is no provider fallback.
        if self.AI_PROVIDER.strip().lower() != PRODUCTION_AI_PROVIDER:
            problems.append(f"AI_PROVIDER must be {PRODUCTION_AI_PROVIDER} in production (Groq-only deployment)")
        elif self.AI_ENABLED and not self.GROQ_API_KEY.strip():
            problems.append("GROQ_API_KEY is required in production when AI_ENABLED=true")

        # Two different sources of the client address must never be configured together.
        if self.TRUSTED_CLIENT_IP_HEADER and self.TRUSTED_PROXY_COUNT > 0:
            problems.append(
                "TRUSTED_CLIENT_IP_HEADER and TRUSTED_PROXY_COUNT > 0 cannot both be set in production; "
                "choose one source of the client address"
            )

        if problems:
            raise ValueError(
                "Invalid production configuration:\n- " + "\n- ".join(problems)
            )
        return self

    # --- Derived values ------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cors_origins(self) -> list[str]:
        return parse_origins(self.CORS_ORIGINS)

    @property
    def database_sslmode(self) -> str | None:
        """The sslmode to enforce when the URL does not specify one."""
        if self.DB_SSLMODE is not None:
            return self.DB_SSLMODE
        return "require" if self.is_production else None

    @property
    def docs_enabled(self) -> bool:
        if self.ENABLE_DOCS is not None:
            return self.ENABLE_DOCS
        return not self.is_production

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Validation errors must never echo input values (they can be secrets).
        hide_input_in_errors=True,
    )


settings = Settings()
