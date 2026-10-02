from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.database.session import get_db

from src.models.user import User

from src.services.context_service import get_user_context

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

from src.schemas.goal import GoalCreate, GoalResponse

from src.services.goal_service import (
    create_goal,
    get_goals,
    get_goal,
    update_goal_status,
    delete_goal,
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

@router.get(
    "/context",
)
def read_user_context(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_user_context(
        db=db,
        user=current_user,
    )

@router.get(
    "/goals",
    response_model=list[GoalResponse],
)
def read_goals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_goals(
        db=db,
        user=current_user,
    )


@router.post(
    "/goals",
    response_model=GoalResponse,
)
def add_goal(
    goal: GoalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return create_goal(
        db=db,
        user=current_user,
        title=goal.title,
        description=goal.description,
        category=goal.category,
        priority=goal.priority,
        target_date=goal.target_date,
    )


@router.patch(
    "/goals/{goal_id}/status",
    response_model=GoalResponse,
)
def change_goal_status(
    goal_id: int,
    status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updated_goal = update_goal_status(
        db=db,
        user=current_user,
        goal_id=goal_id,
        status=status,
    )

    if updated_goal is None:
        raise HTTPException(
            status_code=404,
            detail="Goal not found",
        )

    return updated_goal


@router.delete(
    "/goals/{goal_id}",
)
def remove_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deleted_goal = delete_goal(
        db=db,
        user=current_user,
        goal_id=goal_id,
    )

    if deleted_goal is None:
        raise HTTPException(
            status_code=404,
            detail="Goal not found",
        )

    return {
        "message": "Goal deleted successfully",
    }