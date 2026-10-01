from sqlalchemy.orm import Session

from src.models.memory import Memory
from src.models.user import User
from src.services.memory_extraction_service import (
    build_memory_key,
)

def create_memory(
    db: Session,
    user: User,
    memory_type: str,
    content: str,
):
    memory = Memory(
        user_id=user.id,
        memory_type=memory_type,
        content=content,
    )

    db.add(memory)
    db.commit()
    db.refresh(memory)

    return memory


def get_memories(
    db: Session,
    user: User,
):
    return (
        db.query(Memory)
        .filter(Memory.user_id == user.id)
        .order_by(Memory.created_at.desc())
        .all()
    )


def get_memories_by_type(
    db: Session,
    user: User,
    memory_type: str,
):
    return (
        db.query(Memory)
        .filter(
            Memory.user_id == user.id,
            Memory.memory_type == memory_type,
        )
        .order_by(Memory.created_at.desc())
        .all()
    )


def delete_memory(
    db: Session,
    user: User,
    memory_id: int,
):
    memory = (
        db.query(Memory)
        .filter(
            Memory.id == memory_id,
            Memory.user_id == user.id,
        )
        .first()
    )

    if memory is None:
        return None

    db.delete(memory)
    db.commit()

    return memory
def find_duplicate_memory(
    db: Session,
    user: User,
    memory_type: str,
    content: str,
):
    memories = (
        db.query(Memory)
        .filter(
            Memory.user_id == user.id,
            Memory.memory_type == memory_type,
        )
        .all()
    )

    target_key = build_memory_key(
        memory_type,
        content,
    )

    target_text = target_key.split(":", 1)[1]

    target_words = set(
        target_text.split()
    )

    for memory in memories:
        existing_key = build_memory_key(
            memory.memory_type,
            memory.content,
        )

        if existing_key == target_key:
            return memory

        existing_text = existing_key.split(
            ":",
            1,
        )[1]

        existing_words = set(
            existing_text.split()
        )

        if not target_words or not existing_words:
            continue

        if (
            target_words.issubset(existing_words)
            or existing_words.issubset(target_words)
        ):
            return memory

        overlap = (
            len(target_words & existing_words)
            / len(target_words | existing_words)
        )

        if overlap >= 0.6:
            return memory

    return None