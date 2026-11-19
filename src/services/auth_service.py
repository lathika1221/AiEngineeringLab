from sqlalchemy.orm import Session

from src.auth.hash import hash_password
from src.auth.hash import verify_password
from src.auth.jwt import create_access_token
from src.models.user import User
from src.schemas.user import UserCreate


def create_user(db: Session, user: UserCreate):
    existing = (
        db.query(User)
        .filter(
            (User.email == user.email)
            | (User.username == user.username)
        )
        .first()
    )

    if existing:
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


def login_user(
    db: Session,
    identifier: str,
    password: str,
):
    db_user = (
        db.query(User)
        .filter(
            (User.email == identifier)
            | (User.username == identifier)
        )
        .first()
    )

    if not db_user:
        _equalize_timing(password)
        return None

    if not verify_password(
        password,
        db_user.hashed_password,
    ):
        return None

    access_token = create_access_token(
        {"sub": db_user.email}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }