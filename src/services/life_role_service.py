from sqlalchemy.orm import Session

from src.models.life_role import LifeRole
from src.models.user import User
from src.schemas.life_role import LifeRoleCreate


def get_life_roles(
    db: Session,
    user: User,
):
    return (
        db.query(LifeRole)
        .filter(LifeRole.user_id == user.id)
        .order_by(
            LifeRole.priority.asc(),
            LifeRole.created_at.asc(),
        )
        .all()
    )


def get_life_role(
    db: Session,
    user: User,
    role_id: int,
):
    return (
        db.query(LifeRole)
        .filter(
            LifeRole.id == role_id,
            LifeRole.user_id == user.id,
        )
        .first()
    )


def find_duplicate_role(
    db: Session,
    user: User,
    role: str,
):
    normalized_role = role.strip().lower()

    roles = (
        db.query(LifeRole)
        .filter(LifeRole.user_id == user.id)
        .all()
    )

    for existing_role in roles:
        if existing_role.role.strip().lower() == normalized_role:
            return existing_role

    return None


def create_life_role(
    db: Session,
    user: User,
    role_data: LifeRoleCreate,
):
    duplicate = find_duplicate_role(
        db=db,
        user=user,
        role=role_data.role,
    )

    if duplicate is not None:
        return None

    life_role = LifeRole(
        user_id=user.id,
        role=role_data.role.strip(),
        description=role_data.description,
        priority=role_data.priority,
    )

    db.add(life_role)
    db.commit()
    db.refresh(life_role)

    return life_role


def delete_life_role(
    db: Session,
    user: User,
    role_id: int,
):
    life_role = get_life_role(
        db=db,
        user=user,
        role_id=role_id,
    )

    if life_role is None:
        return None

    db.delete(life_role)
    db.commit()

    return life_role