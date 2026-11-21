import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from jose import jwt

from src.config.settings import settings


def create_access_token(data: dict):

    payload = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload.update({"exp": expire})

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def password_fingerprint(hashed_password: str) -> str:
    """Short, non-reversible tag of the current password hash, carried in the token as
    `pv`. Changing the password changes the tag, which invalidates every token issued
    before the change without any server-side session store."""
    return hmac.new(
        settings.SECRET_KEY.encode(), hashed_password.encode(), hashlib.sha256
    ).hexdigest()[:24]
