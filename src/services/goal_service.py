from sqlalchemy.orm import Session

from src.models.goal import Goal
from src.models.user import User


def create_goal(
    db: Session,
    user: User,
    title: str,
    description: str | None = None,
    category: str | None = None,
    priority: int = 1,
    target_date=None,
):
    goal = Goal(
        user_id=user.id,
        title=title,
        description=description,
        category=category,
        priority=priority,
        target_date=target_date,
    )

    db.add(goal)
    db.commit()
    db.refresh(goal)

    return goal


def get_goals(
    db: Session,
    user: User,
):
    return (
        db.query(Goal)
        .filter(Goal.user_id == user.id)
        .order_by(
            Goal.priority.asc(),
            Goal.created_at.desc(),
        )
        .all()
    )


def get_goal(
    db: Session,
    user: User,
    goal_id: int,
):
    return (
        db.query(Goal)
        .filter(
            Goal.id == goal_id,
            Goal.user_id == user.id,
        )
        .first()
    )


def update_goal_status(
    db: Session,
    user: User,
    goal_id: int,
    status: str,
):
    goal = get_goal(
        db=db,
        user=user,
        goal_id=goal_id,
    )

    if goal is None:
        return None

    goal.status = status

    db.commit()
    db.refresh(goal)

    return goal


def delete_goal(
    db: Session,
    user: User,
    goal_id: int,
):
    goal = get_goal(
        db=db,
        user=user,
        goal_id=goal_id,
    )

    if goal is None:
        return None

    db.delete(goal)
    db.commit()

    return goal