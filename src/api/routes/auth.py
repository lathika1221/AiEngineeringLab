from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from src.api.feature_flags import require_registration_enabled
from src.database.session import get_db
from src.schemas.user import UserCreate, UserResponse
from src.schemas.login import Token
from src.security.rate_limit import limit_login, limit_register
from src.services.auth_service import create_user, login_user


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    dependencies=[Depends(require_registration_enabled), Depends(limit_register)],
)
def register(
    user: UserCreate,
    db: Session = Depends(get_db),
):
    created_user = create_user(
        db,
        user,
    )

    if created_user is None:
        raise HTTPException(
            status_code=400,
            detail="User already exists",
        )

    return created_user


@router.post(
    "/login",
    response_model=Token,
    # Rate limit first: it runs before any account lookup or password hashing.
    dependencies=[Depends(limit_login)],
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    token = login_user(
        db,
        form_data.username,
        form_data.password,
    )

    if token is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid username/email or password",
        )

    return token