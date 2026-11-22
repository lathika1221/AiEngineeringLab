import logging
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import psycopg2

from src.api.main import app
from src.config.settings import Settings
from src.database.connection import build_engine_options, normalize_database_url
from src.database.session import get_db

# Fake values only. Nothing here ever connects: psycopg2.connect is replaced
# wherever a connection could be attempted.
PG_URL = "postgresql://app:pw@db.example.com/latz"
PSYCOPG2_URL = "postgresql+psycopg2://app:pw@db.example.com/latz"
FAKE_SECRET = "unit-test-secret-" + "k" * 30


@pytest.fixture(autouse=True)
def isolated_settings_env(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)


def make_cfg(**overrides):
    values = {
        "PROJECT_NAME": "LATZ Test",
        "VERSION": "0.0.1",
        "DATABASE_URL": PG_URL,
        "SECRET_KEY": FAKE_SECRET,
        "ACCESS_TOKEN_EXPIRE_MINUTES": 30,
        "AI_PROVIDER": "groq",
        "MODEL_NAME": "test-model",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_prod_cfg(**overrides):
    values = {"ENVIRONMENT": "production", "CORS_ORIGINS": "https://latz.example.com", "GROQ_API_KEY": "fake-key"}
    values.update(overrides)
    return make_cfg(**values)


# ------------------------------------------------------------------ settings
def test_database_pool_settings_have_safe_defaults():
    cfg = make_cfg()
    assert (cfg.DB_POOL_SIZE, cfg.DB_MAX_OVERFLOW, cfg.DB_POOL_RECYCLE, cfg.DB_POOL_TIMEOUT, cfg.DB_CONNECT_TIMEOUT) == (5, 5, 300, 30, 10)
    assert cfg.DB_SSLMODE is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"DB_POOL_SIZE": 0},
        {"DB_POOL_SIZE": 51},
        {"DB_MAX_OVERFLOW": -1},
        {"DB_POOL_RECYCLE": 0},
        {"DB_POOL_TIMEOUT": 0},
        {"DB_CONNECT_TIMEOUT": 0},
        {"DB_SSLMODE": "sometimes"},
    ],
)
def test_database_pool_settings_reject_invalid_values(overrides):
    with pytest.raises(ValidationError):
        make_cfg(**overrides)


def test_empty_sslmode_is_treated_as_unset_and_value_is_normalised():
    assert make_cfg(DB_SSLMODE="").DB_SSLMODE is None
    assert make_cfg(DB_SSLMODE=" Require ").DB_SSLMODE == "require"


def test_database_url_whitespace_is_trimmed():
    assert make_cfg(DATABASE_URL="  " + PG_URL + "\n").DATABASE_URL == PG_URL


def test_effective_sslmode_defaults_to_require_only_in_production():
    assert make_cfg().database_sslmode is None
    assert make_prod_cfg().database_sslmode == "require"
    assert make_prod_cfg(DB_SSLMODE="verify-full").database_sslmode == "verify-full"
    assert make_cfg(DB_SSLMODE="prefer").database_sslmode == "prefer"


def test_step_two_scheme_validation_is_unchanged():
    assert make_prod_cfg(DATABASE_URL=PSYCOPG2_URL).DATABASE_URL == PSYCOPG2_URL
    for bad in ("postgresql+asyncpg://u:p@h/db", "postgresqlfoo://u:p@h/db", "postgres://u:p@h/db", "sqlite://"):
        with pytest.raises(ValidationError):
            make_prod_cfg(DATABASE_URL=bad)


# ------------------------------------------------------------- URL handling
def test_normalize_only_trims_whitespace_and_never_rewrites_the_scheme():
    assert normalize_database_url("  " + PG_URL + " ") == PG_URL
    assert normalize_database_url(PSYCOPG2_URL) == PSYCOPG2_URL
    assert normalize_database_url("sqlite:///./local.db") == "sqlite:///./local.db"
    assert normalize_database_url("postgres://u:p@h/db") == "postgres://u:p@h/db"


# ------------------------------------------------------- engine option builder
@pytest.mark.parametrize("url", [PG_URL, PSYCOPG2_URL])
def test_postgres_engine_options_in_development(url):
    options = build_engine_options(url, make_cfg(DATABASE_URL=url))
    assert options["pool_pre_ping"] is True
    assert options["pool_size"] == 5
    assert options["max_overflow"] == 5
    assert options["pool_recycle"] == 300
    assert options["pool_timeout"] == 30
    assert options["connect_args"] == {"connect_timeout": 10}  # no forced sslmode in development
    assert options["echo"] is False


@pytest.mark.parametrize("url", [PG_URL, PSYCOPG2_URL])
def test_postgres_engine_options_in_production_enforce_ssl(url):
    options = build_engine_options(url, make_prod_cfg(DATABASE_URL=url))
    assert options["connect_args"] == {"connect_timeout": 10, "sslmode": "require"}


def test_pool_settings_are_configurable():
    cfg = make_cfg(DB_POOL_SIZE=2, DB_MAX_OVERFLOW=1, DB_POOL_RECYCLE=120, DB_POOL_TIMEOUT=7, DB_CONNECT_TIMEOUT=3, DB_SSLMODE="verify-full", DEBUG=True)
    options = build_engine_options(PG_URL, cfg)
    assert (options["pool_size"], options["max_overflow"], options["pool_recycle"], options["pool_timeout"]) == (2, 1, 120, 7)
    assert options["connect_args"] == {"connect_timeout": 3, "sslmode": "verify-full"}
    assert options["echo"] is True


def test_values_in_the_url_win_over_settings():
    url = "postgresql://app:pw@db.example.com/latz?sslmode=verify-full&connect_timeout=2"
    options = build_engine_options(url, make_prod_cfg(DATABASE_URL=url))
    assert "connect_args" not in options  # nothing to add: the URL already decides both


def test_url_with_only_sslmode_still_gets_the_connect_timeout():
    url = "postgresql://app:pw@db.example.com/latz?sslmode=require"
    options = build_engine_options(url, make_prod_cfg(DATABASE_URL=url))
    assert options["connect_args"] == {"connect_timeout": 10}


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///./local.db"])
def test_sqlite_keeps_previous_behaviour_with_no_pool_or_ssl_arguments(url):
    options = build_engine_options(url, make_cfg(DATABASE_URL=url))
    assert options == {"echo": False, "pool_pre_ping": True}


def test_real_engines_accept_the_options_and_apply_them():
    pg = create_engine(PG_URL, **build_engine_options(PG_URL, make_cfg(DB_POOL_SIZE=3, DB_MAX_OVERFLOW=2, DB_POOL_RECYCLE=111, DB_POOL_TIMEOUT=9)))
    assert pg.pool.size() == 3
    assert pg.pool._max_overflow == 2
    assert pg.pool._recycle == 111
    assert pg.pool._timeout == 9
    assert pg.pool._pre_ping is True
    lite = create_engine("sqlite://", **build_engine_options("sqlite://", make_cfg(DATABASE_URL="sqlite://")))
    with lite.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_driver_receives_ssl_and_timeout_without_any_network(monkeypatch):
    seen = {}

    def fake_connect(*args, **kwargs):
        seen.update(kwargs)
        raise psycopg2.OperationalError("blocked in test")

    monkeypatch.setattr(psycopg2, "connect", fake_connect)
    cfg = make_prod_cfg(DATABASE_URL=PSYCOPG2_URL, DB_CONNECT_TIMEOUT=4)
    engine = create_engine(PSYCOPG2_URL, **build_engine_options(PSYCOPG2_URL, cfg))
    with pytest.raises(sa_exc.OperationalError):
        engine.connect()
    assert seen["sslmode"] == "require"
    assert seen["connect_timeout"] == 4
    assert seen["host"] == "db.example.com"


def test_the_module_level_engine_matches_the_test_environment():
    from src.database.connection import engine

    assert engine.dialect.name == "sqlite"  # tests run with DATABASE_URL=sqlite://


# --------------------------------------------------------------- health checks
@pytest.fixture
def sqlite_db_override():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def broken_db_override():
    """A database that fails on first use, with a message containing sensitive-looking text."""

    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise sa_exc.OperationalError("SELECT 1", {}, Exception("connection to db.internal.example failed: password=hunter2"))

        def close(self):
            pass

    def override():
        session = BrokenSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    yield
    app.dependency_overrides.clear()


def test_ready_succeeds_when_the_database_answers(sqlite_db_override):
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_ready_returns_503_when_the_database_is_down(broken_db_override):
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unreachable"}


def test_ready_failure_does_not_leak_details_in_body_or_logs(broken_db_override, caplog):
    with caplog.at_level(logging.WARNING):
        response = TestClient(app).get("/health/ready")
    assert "hunter2" not in response.text and "db.internal" not in response.text
    assert "hunter2" not in caplog.text and "db.internal" not in caplog.text
    assert "OperationalError" in caplog.text  # the type is logged for diagnosis


def test_ready_reports_a_real_unreachable_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/missing-dir/x.db")  # parent folder does not exist
    Session = sessionmaker(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    try:
        assert TestClient(app).get("/health/ready").status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_liveness_stays_up_even_when_the_database_is_down(broken_db_override):
    response = TestClient(app).get("/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "Healthy"


def test_liveness_never_opens_a_database_session(monkeypatch):
    def forbidden():
        raise AssertionError("liveness must not use the database")
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = forbidden
    try:
        assert TestClient(app).get("/health/").status_code == 200
    finally:
        app.dependency_overrides.clear()
