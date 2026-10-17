from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.database.session import get_db
from src.models.user import User

from src.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
)

from src.services.project_service import (
    create_project,
    get_projects,
    get_project,
    update_project,
    delete_project,
)


router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
)


@router.post(
    "",
    response_model=ProjectResponse,
)
def create(
    request: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    return create_project(
        db=db,
        user=current_user,
        name=request.name,
        description=request.description,
        status=request.status,
        engine=request.engine,
        tech_stack=request.tech_stack,
    )


@router.get(
    "",
    response_model=list[ProjectResponse],
)
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    return get_projects(
        db=db,
        user=current_user,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
def get(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    project = get_project(
        db=db,
        user=current_user,
        project_id=project_id,
    )

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    return project


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
)
def update(
    project_id: int,
    request: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    project = get_project(
        db=db,
        user=current_user,
        project_id=project_id,
    )

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    return update_project(
        db=db,
        project=project,
        data=request.model_dump(
            exclude_unset=True
        ),
    )


@router.delete(
    "/{project_id}",
)
def delete(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    project = get_project(
        db=db,
        user=current_user,
        project_id=project_id,
    )

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    delete_project(
        db=db,
        project=project,
    )

    return {
        "deleted": True,
        "project_id": project_id,
    }