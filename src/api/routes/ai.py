from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.database.session import get_db
from src.models.user import User
from src.schemas.ai import ChatRequest, ChatResponse
from src.schemas.chat import ChatHistory
from src.services.ai_service import chat_with_ai
from src.services.chat_service import save_chat, get_chat_history

router = APIRouter(
    prefix="/ai",
    tags=["AI"],
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
    response = chat_with_ai(request.message)

    save_chat(
        db=db,
        user=current_user,
        user_message=request.message,
        ai_response=response,
    )

    return ChatResponse(
        response=response,
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