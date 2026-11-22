from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from src.config.settings import settings


def normalize_database_url(url: str) -> str:
    """Return the URL ready for SQLAlchemy.

    Only surrounding whitespace is removed. The scheme is never rewritten: the
    supported PostgreSQL schemes (postgresql:// and postgresql+psycopg2://) are
    already valid for SQLAlchemy and anything else is rejected by the
    production settings validation.
    """
    return url.strip()


def build_engine_options(url: str, cfg=settings) -> dict:
    """Keyword arguments for create_engine, derived from the URL and settings.

    Pure function (no network, no logging) so it can be unit-tested.
    - pool_pre_ping is always on: a dead connection (for example after a
      serverless database suspended) is replaced instead of failing a request.
    - Pool sizing, SSL and the connect timeout only apply to PostgreSQL. SQLite
      uses a different pool class that rejects these arguments, so it keeps
      its previous behaviour.
    - A value already present in the URL query string (sslmode,
      connect_timeout) takes precedence over the settings.
    """
    options: dict = {"echo": cfg.DEBUG, "pool_pre_ping": True}

    parsed = make_url(url)
    if not parsed.get_backend_name() == "postgresql":
        return options

    options.update(
        pool_size=cfg.DB_POOL_SIZE,
        max_overflow=cfg.DB_MAX_OVERFLOW,
        pool_recycle=cfg.DB_POOL_RECYCLE,
        pool_timeout=cfg.DB_POOL_TIMEOUT,
    )

    connect_args: dict = {}
    if "connect_timeout" not in parsed.query:
        connect_args["connect_timeout"] = cfg.DB_CONNECT_TIMEOUT
    sslmode = cfg.database_sslmode
    if sslmode is not None and "sslmode" not in parsed.query:
        connect_args["sslmode"] = sslmode
    if connect_args:
        options["connect_args"] = connect_args
    return options


database_url = normalize_database_url(settings.DATABASE_URL)

engine = create_engine(database_url, **build_engine_options(database_url))
