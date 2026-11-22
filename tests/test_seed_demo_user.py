"""Tests for scripts/seed_demo_user.py. They use an in-memory SQLite database only."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.database.session as session_module
from scripts import seed_demo_user as seed
from src.auth.hash import verify_password
from src.database.base import Base
from src.models import User

PASSWORD = "Correct-Horse-Battery-9"
ENV = {
    "DEMO_USER_USERNAME": "demo",
    "DEMO_USER_EMAIL": "demo@example.com",
    "DEMO_USER_PASSWORD": PASSWORD,
}


@pytest.fixture()
def factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    # main() imports SessionLocal lazily, so replacing the module attribute is enough.
    monkeypatch.setattr(session_module, "SessionLocal", maker)
    return maker


def users(maker):
    with maker() as db:
        return db.query(User).order_by(User.id).all()


def test_missing_variables_fail_before_any_database_use(monkeypatch, capsys):
    def boom(*args, **kwargs):
        raise AssertionError("the database must not be touched")

    monkeypatch.setattr(session_module, "SessionLocal", boom)
    assert seed.main({"DEMO_USER_USERNAME": "demo"}) == seed.EXIT_FAILURE
    err = capsys.readouterr().err
    assert "DEMO_USER_EMAIL" in err and "DEMO_USER_PASSWORD" in err


@pytest.mark.parametrize("password", ["short", "x" * 73, "replace-with-a-real-password-please"])
def test_bad_password_is_rejected_without_echoing_it(password, factory, capsys):
    env = {**ENV, "DEMO_USER_PASSWORD": password}
    assert seed.main(env) == seed.EXIT_FAILURE
    captured = capsys.readouterr()
    assert password not in captured.out + captured.err
    assert users(factory) == []


def test_invalid_email_is_rejected(factory, capsys):
    assert seed.main({**ENV, "DEMO_USER_EMAIL": "not-an-email"}) == seed.EXIT_FAILURE
    assert "DEMO_USER_EMAIL" not in capsys.readouterr().out
    assert users(factory) == []


def test_creates_one_user_with_a_hashed_password_and_prints_no_secret(factory, capsys):
    assert seed.main(ENV) == seed.EXIT_OK
    captured = capsys.readouterr()
    rows = users(factory)
    assert len(rows) == 1
    assert rows[0].username == "demo" and rows[0].email == "demo@example.com"
    assert rows[0].hashed_password != PASSWORD
    assert verify_password(PASSWORD, rows[0].hashed_password)
    text = captured.out + captured.err
    assert PASSWORD not in text and rows[0].hashed_password not in text


def test_is_idempotent_and_never_resets_the_password(factory, capsys):
    assert seed.main(ENV) == seed.EXIT_OK
    original_hash = users(factory)[0].hashed_password
    capsys.readouterr()

    again = {**ENV, "DEMO_USER_PASSWORD": "A-Different-Password-77"}
    assert seed.main(again) == seed.EXIT_OK
    assert "already exists" in capsys.readouterr().out
    rows = users(factory)
    assert len(rows) == 1
    assert rows[0].hashed_password == original_hash


@pytest.mark.parametrize(
    "existing",
    [
        {"username": "demo", "email": "other@example.com"},
        {"username": "someone", "email": "demo@example.com"},
    ],
)
def test_conflicting_account_is_an_error_and_is_left_untouched(existing, factory, capsys):
    with factory() as db:
        db.add(User(hashed_password="x", **existing))
        db.commit()
    assert seed.main(ENV) == seed.EXIT_FAILURE
    assert "nothing was changed" in capsys.readouterr().err
    rows = users(factory)
    assert len(rows) == 1 and rows[0].hashed_password == "x"


def test_two_different_accounts_matching_is_an_error(factory):
    with factory() as db:
        db.add(User(username="demo", email="a@example.com", hashed_password="x"))
        db.add(User(username="b", email="demo@example.com", hashed_password="y"))
        db.commit()
    assert seed.main(ENV) == seed.EXIT_FAILURE
    assert len(users(factory)) == 2


def test_database_errors_do_not_leak_details(monkeypatch, capsys):
    def broken(*args, **kwargs):
        raise RuntimeError("postgresql://user:secret-pw@host/db refused")

    monkeypatch.setattr(session_module, "SessionLocal", broken)
    assert seed.main(ENV) == seed.EXIT_FAILURE
    err = capsys.readouterr().err
    assert "secret-pw" not in err and "RuntimeError" in err


def test_script_has_no_hardcoded_credentials():
    from pathlib import Path

    source = Path(seed.__file__).read_text(encoding="utf-8")
    assert PASSWORD not in source
