from fastapi import APIRouter, Depends

from src.auth.dependencies import get_current_user
from src.models.user import User
from src.schemas.ai import ChatRequest, ChatResponse
from src.services.ai_service import chat_with_ai

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
    current_user: User = Depends(get_current_user),
):
    response = chat_with_ai(request.message)

    return ChatResponse(
        response=response,
    )