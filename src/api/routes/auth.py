from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.schemas.user import UserCreate, UserResponse
from src.services.auth_service import create_user

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
)
def register(
    user: UserCreate,
    db: Session = Depends(get_db),
):

    created_user = create_user(db, user)

    if created_user is None:
        raise HTTPException(
            status_code=400,
            detail="User already exists",
        )

    return created_user