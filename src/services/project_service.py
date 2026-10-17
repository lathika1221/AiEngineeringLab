from sqlalchemy.orm import Session

from src.models.project import Project
from src.models.user import User


def create_project(
    db: Session,
    user: User,
    name: str,
    description: str | None = None,
    status: str = "active",
    engine: str | None = None,
    tech_stack: str | None = None,
):
    project = Project(
        user_id=user.id,
        name=name,
        description=description,
        status=status,
        engine=engine,
        tech_stack=tech_stack,
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    return project


def get_projects(
    db: Session,
    user: User,
):
    return (
        db.query(Project)
        .filter(
            Project.user_id == user.id
        )
        .order_by(
            Project.created_at.desc()
        )
        .all()
    )


def get_project(
    db: Session,
    user: User,
    project_id: int,
):
    return (
        db.query(Project)
        .filter(
            Project.id == project_id,
            Project.user_id == user.id,
        )
        .first()
    )


def update_project(
    db: Session,
    project: Project,
    data: dict,
):
    for key, value in data.items():
        if value is not None:
            setattr(
                project,
                key,
                value,
            )

    db.commit()
    db.refresh(project)

    return project


def delete_project(
    db: Session,
    project: Project,
):
    db.delete(project)
    db.commit()