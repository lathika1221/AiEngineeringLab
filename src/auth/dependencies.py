from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import hmac

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from src.auth.jwt import password_fingerprint
from src.config.settings import settings
from src.database.session import get_db
from src.models.user import User

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )

        email = payload.get("sub")

        if email is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()

    if user is None:
        raise credentials_exception

    # Tokens issued by login carry a fingerprint of the password hash; a password change
    # invalidates them. Tokens without the claim (issued before it existed) stay valid
    # until their normal expiry.
    pv = payload.get("pv")
    if pv is not None and not hmac.compare_digest(
        str(pv), password_fingerprint(user.hashed_password)
    ):
        raise credentials_exception

    return user