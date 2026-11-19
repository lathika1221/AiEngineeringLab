"""Create the single demo account for the career-portfolio deployment.

Run once from the repository root, in an environment that already has the
backend settings (DATABASE_URL, SECRET_KEY, ...), for example the Render shell:

    DEMO_USER_USERNAME=... DEMO_USER_EMAIL=... DEMO_USER_PASSWORD=... \\
        python -m scripts.seed_demo_user

Rules this script follows:
- Credentials come only from the environment. Nothing is hardcoded.
- Nothing secret is printed: no password, no hash, and no raw validation errors
  (they can echo the rejected value). Only the outcome and the numeric user id.
- Idempotent: if the demo account already exists the script changes nothing and
  exits successfully. It never resets an existing password.
- It creates exactly one ordinary user (this app has no roles or admin flag, so
  the account has no elevated rights). It does not depend on REGISTRATION_ENABLED,
  so registration can stay closed.
- A conflict (the email or username belongs to a different account) is an
  error, never an overwrite.
"""

import os
import sys
from collections.abc import Mapping

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

REQUIRED_VARIABLES = ("DEMO_USER_USERNAME", "DEMO_USER_EMAIL", "DEMO_USER_PASSWORD")
_PLACEHOLDER_PREFIXES = ("replace-with", "change-me", "changeme", "your-password")

EXIT_OK = 0
EXIT_FAILURE = 1


class SeedError(Exception):
    """A safe-to-print reason the demo account was not created."""


def read_demo_credentials(env: Mapping[str, str]):
    """Return a validated UserCreate built from the environment (no database)."""
    from src.schemas.user import UserCreate

    missing = [name for name in REQUIRED_VARIABLES if not env.get(name, "").strip()]
    if missing:
        raise SeedError("Missing required environment variables: " + ", ".join(missing))

    password = env["DEMO_USER_PASSWORD"]
    if password.strip().lower().startswith(_PLACEHOLDER_PREFIXES):
        raise SeedError("DEMO_USER_PASSWORD still looks like a placeholder")

    try:
        return UserCreate(
            username=env["DEMO_USER_USERNAME"].strip(),
            email=env["DEMO_USER_EMAIL"].strip(),
            password=password,
        )
    except ValidationError as exc:
        # Field names only: the default message would repeat the rejected input.
        fields = sorted({str(error["loc"][0]) for error in exc.errors() if error.get("loc")})
        raise SeedError(
            "Invalid demo account settings for: " + ", ".join(fields)
            + " (password needs 12 to 72 bytes; email must be valid)"
        ) from None


def seed_demo_user(db: Session, data) -> str:
    """Create the demo user unless it already exists. Returns 'created' or 'exists'."""
    from src.models.user import User
    from src.services.auth_service import create_user

    matches = db.query(User).filter((User.email == data.email) | (User.username == data.username)).all()
    if len(matches) > 1:
        raise SeedError("The demo username and email belong to two different accounts; nothing was changed")
    if matches:
        existing = matches[0]
        if existing.email != data.email or existing.username != data.username:
            raise SeedError("The demo username or email is already used by another account; nothing was changed")
        return "exists"

    try:
        created = create_user(db, data)
    except IntegrityError:
        # Another process created it between the check and the insert.
        db.rollback()
        again = db.query(User).filter(User.email == data.email, User.username == data.username).first()
        if again is not None:
            return "exists"
        raise SeedError("The demo account could not be created because of a conflicting account") from None

    if created is None:
        raise SeedError("The demo account could not be created because of a conflicting account")
    return "created"


def main(env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    try:
        data = read_demo_credentials(env)
    except SeedError as exc:
        print(f"seed_demo_user: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    # The database is only imported after the demo variables are validated, so a
    # missing variable fails before anything tries to connect.
    try:
        from src.database.session import SessionLocal

        with SessionLocal() as db:
            outcome = seed_demo_user(db, data)
    except SeedError as exc:
        print(f"seed_demo_user: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    except Exception as exc:  # never print the message: it can contain connection details
        print(f"seed_demo_user: failed ({type(exc).__name__}). Check DATABASE_URL and the backend settings.", file=sys.stderr)
        return EXIT_FAILURE

    print("seed_demo_user: demo account created." if outcome == "created" else "seed_demo_user: demo account already exists; nothing changed.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
