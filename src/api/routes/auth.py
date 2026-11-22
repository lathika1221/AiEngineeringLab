from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from src.api.feature_flags import require_registration_enabled
from src.auth.dependencies import get_current_user
from src.database.session import get_db
from src.models.user import User
from src.schemas.user import PasswordChange, UserCreate, UserResponse
from src.schemas.login import Token
from src.security.rate_limit import limit_account_change, limit_login, limit_register
from src.services.auth_service import change_password, create_user, login_user


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


@router.post("/change-password", response_model=Token)
def change_password_route(
    body: PasswordChange,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit_account_change(user.id)
    result = change_password(db, user, body.current_password, body.new_password)
    if result is None:
        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect, or the new password is the same as it.",
        )
    return result
