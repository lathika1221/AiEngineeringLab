from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.database.session import get_db
from src.models.user import User
from src.services.memory_extraction_service import (
    detect_memory_candidate,
)
from src.services.memory_service import (
    find_duplicate_memory,
)

router = APIRouter(
    prefix="/ai",
    tags=["Memory Intelligence"],
)


@router.post("/memory-candidate")
def memory_candidate(
    message: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    text = message.get("message", "").strip()

    if not text:
        return {
            "candidate": None,
            "duplicate": False,
        }

    candidate = detect_memory_candidate(text)

    if candidate is None:
        return {
            "candidate": None,
            "duplicate": False,
        }

    duplicate = find_duplicate_memory(
        db=db,
        user=current_user,
        memory_type=candidate["memory_type"],
        content=candidate["content"],
    )

    if duplicate:
        return {
            "candidate": candidate,
            "duplicate": True,
            "existing_memory": {
                "id": duplicate.id,
                "memory_type": duplicate.memory_type,
                "content": duplicate.content,
            },
        }

    return {
        "candidate": candidate,
        "duplicate": False,
    }