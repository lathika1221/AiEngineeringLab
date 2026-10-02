from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse

from src.auth.dependencies import get_current_user
from src.database.session import get_db
from src.models.user import User

from src.schemas.ai import ChatRequest, ChatResponse

from src.schemas.memory_candidate import (
    MemoryCandidateRequest,
    MemoryCandidateResponse,
    MemoryConfirmRequest,
    MemoryConfirmResponse,
)

from src.schemas.chat import ChatHistory

from src.services.ai_service import (
    chat_with_ai,
    stream_chat_with_ai,
)

from src.services.chat_service import (
    save_chat,
    get_chat_history,
    get_recent_chats,
)

from src.services.memory_service import (
    get_memories,
    create_memory,
    find_duplicate_memory,
)

from src.services.memory_extraction_service import (
    detect_memory_candidate,
)

from src.services.context_service import (
    get_user_context,
)


router = APIRouter(
    prefix="/ai",
    tags=["AI"],
)


@router.post(
    "/memory-candidate",
    response_model=MemoryCandidateResponse,
)
def memory_candidate(
    request: MemoryCandidateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidate = detect_memory_candidate(
        request.message,
    )

    if candidate is None:
        return MemoryCandidateResponse(
            candidate=None,
            duplicate=False,
        )

    duplicate = find_duplicate_memory(
        db=db,
        user=current_user,
        memory_type=candidate["memory_type"],
        content=candidate["content"],
    )

    return MemoryCandidateResponse(
        candidate=candidate,
        duplicate=duplicate is not None,
    )


@router.post(
    "/memory-confirm",
    response_model=MemoryConfirmResponse,
)
def memory_confirm(
    request: MemoryConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    duplicate = find_duplicate_memory(
        db=db,
        user=current_user,
        memory_type=request.memory_type,
        content=request.content,
    )

    if duplicate is not None:
        return MemoryConfirmResponse(
            saved=False,
            duplicate=True,
            message="This memory is already saved.",
        )

    create_memory(
        db=db,
        user=current_user,
        memory_type=request.memory_type,
        content=request.content,
    )

    return MemoryConfirmResponse(
        saved=True,
        duplicate=False,
        message="Memory saved successfully.",
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    history = get_recent_chats(
        db=db,
        user=current_user,
    )

    memories = get_memories(
        db=db,
        user=current_user,
    )

    context = get_user_context(
        db=db,
        user=current_user,
    )

    response = chat_with_ai(
        message=request.message,
        history=history,
        memories=memories,
        context=context,
    )

    save_chat(
        db=db,
        user=current_user,
        user_message=request.message,
        ai_response=response,
    )

    return ChatResponse(
        response=response,
    )


@router.post(
    "/chat/stream",
)
def stream_chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    history = get_recent_chats(
        db=db,
        user=current_user,
    )

    memories = get_memories(
        db=db,
        user=current_user,
    )

    context = get_user_context(
        db=db,
        user=current_user,
    )

    def generate():
        chunks = []

        for chunk in stream_chat_with_ai(
            message=request.message,
            history=history,
            memories=memories,
            context=context,
        ):
            chunks.append(chunk)
            yield chunk

        complete_response = "".join(chunks)

        save_chat(
            db=db,
            user=current_user,
            user_message=request.message,
            ai_response=complete_response,
        )

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
    )


@router.get(
    "/history",
    response_model=list[ChatHistory],
)
def history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_chat_history(
        db=db,
        user=current_user,
    )