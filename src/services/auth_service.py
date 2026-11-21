from sqlalchemy.orm import Session

from src.auth.hash import hash_password
from src.auth.hash import verify_password
from src.auth.jwt import create_access_token, password_fingerprint
from src.models.user import User
from src.schemas.user import UserCreate


def create_user(db: Session, user: UserCreate):
    # Also refuse when the new e-mail equals an existing username or the new username
    # equals an existing e-mail, so no two accounts can ever answer to the same login
    # identifier (the schema already forbids '@' in usernames; this guards legacy rows
    # and any caller that bypasses the schema).
    existing = (
        db.query(User)
        .filter(
            (User.email == user.email)
            | (User.username == user.username)
            | (User.username == user.email)
            | (User.email == user.username)
        )
        .first()
    )

    if existing or "@" in user.username:
        return None

    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password),
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


_timing_hash: str | None = None


def _equalize_timing(password: str) -> None:
    """Spend the same bcrypt work for an unknown account as for a known one, so
    response time does not reveal whether an account exists."""
    global _timing_hash
    if _timing_hash is None:
        _timing_hash = hash_password("latz-timing-equalisation-only")
    verify_password(password, _timing_hash)


def _find_login_user(db: Session, identifier: str):
    """Deterministic identifier resolution: an exact e-mail match always wins; only when
    no e-mail matches is the value treated as a username. Both columns are unique, so
    each step yields at most one row and no ordering depends on the database. Anyone who
    cannot own the e-mail therefore can never capture, shadow or lock out that address
    by choosing a username (usernames cannot contain '@' in any case)."""
    by_email = db.query(User).filter(User.email == identifier).one_or_none()
    if by_email is not None:
        return by_email
    return db.query(User).filter(User.username == identifier).one_or_none()


def login_user(
    db: Session,
    identifier: str,
    password: str,
):
    db_user = _find_login_user(db, identifier)

    if not db_user:
        _equalize_timing(password)
        return None

    if not verify_password(
        password,
        db_user.hashed_password,
    ):
        return None

    access_token = create_access_token(
        {"sub": db_user.email, "pv": password_fingerprint(db_user.hashed_password)}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


def change_password(db: Session, user: User, current_password: str, new_password: str):
    """Returns a fresh token, or None when the current password is wrong or the new one
    equals it. Every token issued before this call stops working."""
    if not verify_password(current_password, user.hashed_password):
        return None
    if verify_password(new_password, user.hashed_password):
        return None
    user.hashed_password = hash_password(new_password)
    db.commit()
    db.refresh(user)
    return {
        "access_token": create_access_token(
            {"sub": user.email, "pv": password_fingerprint(user.hashed_password)}
        ),
        "token_type": "bearer",
    }


def delete_account(db: Session, user: User, password: str) -> bool:
    """Permanently deletes the account and everything it owns (cascade) plus its quota
    counters. Requires the password again."""
    if not verify_password(password, user.hashed_password):
        return False
    from src.models.ai_usage import AiUsageDaily

    db.query(AiUsageDaily).filter(AiUsageDaily.scope == f"user:{user.id}").delete(
        synchronize_session=False
    )
    db.delete(user)
    db.commit()
    return True
