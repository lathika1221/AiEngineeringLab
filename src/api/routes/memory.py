from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.database.session import get_db
from src.models.user import User
from src.schemas.memory import MemoryCreate, MemoryResponse
from src.services.memory_service import (
    create_memory,
    get_memories,
    get_memories_by_type,
    delete_memory,
)

router = APIRouter(
    prefix="/memory",
    tags=["Memory"],
)


@router.post(
    "",
    response_model=MemoryResponse,
)
def create(
    request: MemoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return create_memory(
        db=db,
        user=current_user,
        memory_type=request.memory_type,
        content=request.content,
    )


@router.get(
    "",
    response_model=list[MemoryResponse],
)
def list_memories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_memories(
        db=db,
        user=current_user,
    )


@router.get(
    "/type/{memory_type}",
    response_model=list[MemoryResponse],
)
def list_memories_by_type(
    memory_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_memories_by_type(
        db=db,
        user=current_user,
        memory_type=memory_type,
    )


@router.delete(
    "/{memory_id}",
)
def remove_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    memory = delete_memory(
        db=db,
        user=current_user,
        memory_id=memory_id,
    )

    if memory is None:
        raise HTTPException(
            status_code=404,
            detail="Memory not found",
        )

    return {
        "message": "Memory deleted successfully",
    }