from sqlalchemy.orm import Session

from src.auth.hash import hash_password
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