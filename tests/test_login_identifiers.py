"""F3: login identifiers are unambiguous and deterministic.

SQLite tests cover the application rules; the PostgreSQL-gated tests (run in CI and with
LATZ_TEST_PG_ADMIN_URL) prove the same on the production database engine, including
legacy rows that already collide (inserted with raw SQL, as they could exist in a database
created before the rule)."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session as SASession, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.auth.hash import hash_password
from src.config.settings import settings
from src.database.base import Base
from src.database.session import get_db
from src.models import User
from src.schemas.user import UserCreate
from src.services.auth_service import create_user, login_user

VICTIM_PW, ATTACKER_PW = "Victim-Password-123", "Attacker-Password-123"


def make(username, email, password="Valid-Password-1234"):
    return UserCreate(username=username, email=email, password=password)


# ------------------------------------------------------------------ schema rules
@pytest.mark.parametrize("bad", ["a@b.com", "x@", "@x", "ab", "has space", " lead", "trail ", "tab\tx", "new\nline", "x" * 101, ""])
def test_registration_rejects_unsafe_usernames(bad):
    with pytest.raises(ValidationError):
        make(bad, "ok@example.com")


@pytest.mark.parametrize("good", ["latz", "demo", "abc", "user_1", "user.name-2", "Ünïcode", "x" * 100])
def test_registration_accepts_normal_usernames(good):
    assert make(good, "ok@example.com").username == good


def test_model_refuses_to_assign_a_username_with_at_sign():
    with pytest.raises(ValueError):
        User(username="victim@example.com", email="a@example.com", hashed_password="x")
    user = User(username="fine", email="a@example.com", hashed_password="x")
    with pytest.raises(ValueError):
        user.username = "other@example.com"  # any later update path is covered too


def test_registration_endpoint_rejects_at_sign_username_with_422(monkeypatch):
    monkeypatch.setattr(settings, "REGISTRATION_ENABLED", True)
    r = TestClient(app).post("/auth/register", json={"username": "v@example.com", "email": "x@example.com", "password": "Valid-Password-1234"})
    assert r.status_code == 422


# --------------------------------------------------------------- shared scenarios
def seed_legacy_collision(conn):
    """Rows as an old database could hold them: attacker's username == victim's e-mail."""
    conn.execute(text("insert into users (username, email, hashed_password) values (:u, :e, :p)"),
                 {"u": "victim", "e": "victim@example.com", "p": hash_password(VICTIM_PW)})
    conn.execute(text("insert into users (username, email, hashed_password) values (:u, :e, :p)"),
                 {"u": "victim@example.com", "e": "attacker@example.com", "p": hash_password(ATTACKER_PW)})


def assert_deterministic_and_safe(db):
    for _ in range(5):  # same answer every time, whatever order the engine returns rows in
        v = login_user(db, "victim@example.com", VICTIM_PW)
        assert v is not None                                    # victim is never locked out
        assert login_user(db, "victim@example.com", ATTACKER_PW) is None  # no takeover
        assert login_user(db, "victim", VICTIM_PW) is not None
        assert login_user(db, "attacker@example.com", ATTACKER_PW) is not None  # attacker keeps own account
        assert login_user(db, "victim", ATTACKER_PW) is None
    claims_sub = __import__("jose").jwt.get_unverified_claims(login_user(db, "victim@example.com", VICTIM_PW)["access_token"])["sub"]
    assert claims_sub == "victim@example.com"


def test_legacy_collision_is_resolved_for_the_email_owner_on_sqlite():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        seed_legacy_collision(conn)
    with SASession(engine) as db:
        assert_deterministic_and_safe(db)


def test_create_user_refuses_every_collision_shape():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with SASession(engine) as db:
        assert create_user(db, make("victim", "victim@example.com")) is not None
        assert create_user(db, make("victim", "other@example.com")) is None        # same username
        assert create_user(db, make("other", "victim@example.com")) is None        # same e-mail
    with engine.begin() as conn:  # legacy row whose username is an address
        conn.execute(text("insert into users (username, email, hashed_password) values ('legacy@example.com','l@example.com','x')"))
    with SASession(engine) as db:
        assert create_user(db, make("newname", "legacy@example.com")) is None      # new e-mail == legacy username


def test_existing_accounts_still_log_in_by_username_or_email():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with SASession(engine) as db:
        db.add(User(username="latz", email="latz@example.com", hashed_password=hash_password(VICTIM_PW)))
        db.commit()
        assert login_user(db, "latz", VICTIM_PW) and login_user(db, "latz@example.com", VICTIM_PW)
        assert login_user(db, "LATZ", VICTIM_PW) is None  # unchanged: exact match, no new case folding


def test_login_http_is_deterministic_for_the_legacy_collision():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        seed_legacy_collision(conn)
    Session = sessionmaker(bind=engine)

    def gen():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = gen
    try:
        c = TestClient(app)
        ok = c.post("/auth/login", data={"username": "victim@example.com", "password": VICTIM_PW})
        bad = c.post("/auth/login", data={"username": "victim@example.com", "password": ATTACKER_PW})
        assert (ok.status_code, bad.status_code) == (200, 401)
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------- PostgreSQL (gated)
def _pg():
    sys.path.insert(0, str(Path(__file__).parent))
    from test_migrations import ADMIN_URL, _create_throwaway_db, _drop_throwaway_db, validate_admin_url

    if not ADMIN_URL:
        pytest.skip("LATZ_TEST_PG_ADMIN_URL not set")
    validate_admin_url(ADMIN_URL)
    return ADMIN_URL, _create_throwaway_db, _drop_throwaway_db


@pytest.fixture
def pg_engine():
    admin, create, drop = _pg()
    name, url = create(admin)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        drop(admin, name)


def test_postgres_legacy_collision_login_is_deterministic_and_takeover_free(pg_engine):
    with pg_engine.begin() as conn:
        seed_legacy_collision(conn)
    with SASession(pg_engine) as db:
        assert_deterministic_and_safe(db)


def test_postgres_both_orders_of_insertion_resolve_identically(pg_engine):
    """Row order in the heap must not matter: insert the attacker row FIRST."""
    with pg_engine.begin() as conn:
        conn.execute(text("insert into users (username, email, hashed_password) values ('victim@example.com','attacker@example.com',:p)"), {"p": hash_password(ATTACKER_PW)})
        conn.execute(text("insert into users (username, email, hashed_password) values ('victim','victim@example.com',:p)"), {"p": hash_password(VICTIM_PW)})
    with SASession(pg_engine) as db:
        assert_deterministic_and_safe(db)


def test_postgres_registration_collisions_and_unique_constraints(pg_engine):
    with SASession(pg_engine) as db:
        assert create_user(db, make("victim", "victim@example.com")) is not None
        assert create_user(db, make("victim", "x@example.com")) is None
        assert create_user(db, make("other", "victim@example.com")) is None
        with pytest.raises(ValueError):
            create_user(db, UserCreate.model_construct(username="v@example.com", email="z@example.com", password="Valid-Password-1234")) or (_ for _ in ()).throw(ValueError)
        assert db.query(User).count() == 1


def test_postgres_existing_style_accounts_unaffected(pg_engine):
    with SASession(pg_engine) as db:
        db.add(User(username="latz", email="latz@example.com", hashed_password=hash_password(VICTIM_PW)))
        db.commit()
        assert login_user(db, "latz", VICTIM_PW) and login_user(db, "latz@example.com", VICTIM_PW)
        assert login_user(db, "latz", "wrong-password-xx") is None


# ------------------------------------------------------------------ e-mail case (registration fix)
@pytest.fixture
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_email_is_stored_lowercase_and_username_case_is_kept(db_session):
    created = create_user(db_session, make("Mixed.Case", "LATHIKAPRANAV777@GMAIL.COM"))
    assert created.email == "lathikapranav777@gmail.com"
    assert created.username == "Mixed.Case"


@pytest.mark.parametrize("second", ["person@example.com", "PERSON@EXAMPLE.COM", "Person@Example.Com", " person@example.com "])
def test_duplicate_email_is_rejected_whatever_the_case(db_session, second):
    assert create_user(db_session, make("first", "Person@Example.com")) is not None
    assert create_user(db_session, make("second", second.strip())) is None
    assert db_session.query(User).count() == 1


def test_login_resolves_any_case_of_the_same_email(db_session):
    create_user(db_session, make("someone", "Someone@Example.com", "Valid-Password-1234"))
    for ident in ["someone@example.com", "SOMEONE@EXAMPLE.COM", "Someone@Example.Com", " someone@example.com "]:
        assert login_user(db_session, ident, "Valid-Password-1234") is not None, ident
    assert login_user(db_session, "someone", "Valid-Password-1234") is not None
    assert login_user(db_session, "someone@example.com", "wrong-wrong-12345") is None


def test_username_login_stays_case_sensitive(db_session):
    create_user(db_session, make("CaseUser", "case@example.com", "Valid-Password-1234"))
    assert login_user(db_session, "CaseUser", "Valid-Password-1234") is not None
    assert login_user(db_session, "caseuser", "Valid-Password-1234") is None


def test_legacy_mixed_case_email_row_still_logs_in_and_blocks_duplicates(db_session):
    # A row written before normalisation existed (raw insert, mixed case).
    db_session.add(User(username="legacy", email="Legacy@Example.com", hashed_password=hash_password("Valid-Password-1234")))
    db_session.commit()
    assert login_user(db_session, "legacy@example.com", "Valid-Password-1234") is not None
    assert login_user(db_session, "LEGACY@EXAMPLE.COM", "Valid-Password-1234") is not None
    assert create_user(db_session, make("other", "legacy@example.com")) is None


def test_registration_endpoint_case_insensitive_duplicate_and_validation_shape(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(settings, "REGISTRATION_ENABLED", True)
    try:
        client = TestClient(app)
        ok = client.post("/auth/register", json={"username": "user1", "email": "New@Example.COM", "password": "Valid-Password-1234"})
        assert ok.status_code == 200 and ok.json()["email"] == "new@example.com"
        dup = client.post("/auth/register", json={"username": "user2", "email": "NEW@example.com", "password": "Valid-Password-1234"})
        assert dup.status_code == 400
        short = client.post("/auth/register", json={"username": "user3", "email": "user3@example.com", "password": "Short-pw-11"})
        assert short.status_code == 422
        assert isinstance(short.json()["detail"], list)
        assert short.json()["detail"][0]["loc"] == ["body", "password"]
        login = client.post("/auth/login", data={"username": "NEW@EXAMPLE.COM", "password": "Valid-Password-1234"})
        assert login.status_code == 200
    finally:
        app.dependency_overrides.clear()
