from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.database.session import get_db

from src.models.user import User

from src.schemas.profile import (
    ProfileCreate,
    ProfileUpdate,
    ProfileResponse,
)

from src.schemas.life_role import (
    LifeRoleCreate,
    LifeRoleResponse,
)

from src.services.profile_service import (
    get_profile,
    create_profile,
    update_profile,
    complete_onboarding,
)

from src.services.life_role_service import (
    get_life_roles,
    create_life_role,
    delete_life_role,
)


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get("/me")
def read_current_user(
    current_user: User = Depends(get_current_user),
):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
    }


@router.get(
    "/profile",
    response_model=ProfileResponse,
)
def read_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = get_profile(
        db=db,
        user=current_user,
    )

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Profile not found.",
        )

    return profile


@router.post(
    "/profile",
    response_model=ProfileResponse,
)
def create_user_profile(
    profile_data: ProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing_profile = get_profile(
        db=db,
        user=current_user,
    )

    if existing_profile is not None:
        raise HTTPException(
            status_code=409,
            detail="Profile already exists.",
        )

    return create_profile(
        db=db,
        user=current_user,
        profile_data=profile_data,
    )


@router.put(
    "/profile",
    response_model=ProfileResponse,
)
def update_user_profile(
    profile_data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = get_profile(
        db=db,
        user=current_user,
    )

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Profile not found.",
        )

    return update_profile(
        db=db,
        profile=profile,
        profile_data=profile_data,
    )


@router.post(
    "/profile/complete",
    response_model=ProfileResponse,
)
def complete_user_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = get_profile(
        db=db,
        user=current_user,
    )

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Profile not found.",
        )

    return complete_onboarding(
        db=db,
        profile=profile,
    )


@router.get(
    "/roles",
    response_model=list[LifeRoleResponse],
)
def read_life_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_life_roles(
        db=db,
        user=current_user,
    )


@router.post(
    "/roles",
    response_model=LifeRoleResponse,
)
def add_life_role(
    role_data: LifeRoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role = create_life_role(
        db=db,
        user=current_user,
        role_data=role_data,
    )

    if role is None:
        raise HTTPException(
            status_code=409,
            detail="This life role is already added.",
        )

    return role


@router.delete(
    "/roles/{role_id}",
)
def remove_life_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role = delete_life_role(
        db=db,
        user=current_user,
        role_id=role_id,
    )

    if role is None:
        raise HTTPException(
            status_code=404,
            detail="Life role not found.",
        )

    return {
        "message": "Life role deleted successfully.",
    }