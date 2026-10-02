from sqlalchemy.orm import Session

from src.models.user import User
from src.models.profile import UserProfile
from src.models.life_role import LifeRole
from src.models.goal import Goal
from src.models.memory import Memory


def get_user_context(
    db: Session,
    user: User,
):
    profile = (
        db.query(UserProfile)
        .filter(
            UserProfile.user_id == user.id,
        )
        .first()
    )

    life_roles = (
        db.query(LifeRole)
        .filter(
            LifeRole.user_id == user.id,
        )
        .order_by(
            LifeRole.priority.asc(),
            LifeRole.created_at.asc(),
        )
        .all()
    )

    goals = (
        db.query(Goal)
        .filter(
            Goal.user_id == user.id,
        )
        .order_by(
            Goal.priority.asc(),
            Goal.created_at.desc(),
        )
        .all()
    )

    memories = (
        db.query(Memory)
        .filter(
            Memory.user_id == user.id,
        )
        .order_by(
            Memory.created_at.desc(),
        )
        .all()
    )

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
        "profile": (
            {
                "display_name": profile.display_name,
                "bio": profile.bio,
                "timezone": profile.timezone,
                "onboarding_completed": (
                    profile.onboarding_completed
                ),
            }
            if profile
            else None
        ),
        "life_roles": [
            {
                "id": role.id,
                "role": role.role,
                "description": role.description,
                "priority": role.priority,
            }
            for role in life_roles
        ],
        "goals": [
            {
                "id": goal.id,
                "title": goal.title,
                "description": goal.description,
                "category": goal.category,
                "priority": goal.priority,
                "status": goal.status,
                "target_date": goal.target_date,
            }
            for goal in goals
        ],
        "memories": [
            {
                "id": memory.id,
                "type": memory.memory_type,
                "content": memory.content,
            }
            for memory in memories
        ],
    }