from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.database.session import get_db
from src.models.conversation import Conversation
from src.models.user import User
from src.schemas.ai import ChatRequest, ChatResponse
from src.schemas.chat import ChatHistory
from src.schemas.memory_candidate import (
    MemoryCandidateRequest,
    MemoryCandidateResponse,
    MemoryConfirmRequest,
    MemoryConfirmResponse,
)
from src.services.ai_service import chat_with_ai, stream_chat_with_ai
from src.services.chat_service import save_chat, get_chat_history, get_recent_chats
from src.services.context_service import get_user_context
from src.services.memory_extraction_service import detect_memory_candidate
from src.services.memory_service import get_memories, create_memory, find_duplicate_memory
from src.services.project_service import get_project

router = APIRouter(prefix="/ai", tags=["AI"])


def build_request_context(db: Session, user: User, project_id: int | None):
    context = get_user_context(db=db, user=user)
    if project_id is None:
        context["current_project"] = None
        return context
    project = get_project(db=db, user=user, project_id=project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    context["current_project"] = {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "engine": project.engine,
        "tech_stack": project.tech_stack,
    }
    return context


def validate_conversation(db: Session, user: User, conversation_id: int | None, project_id: int | None):
    if conversation_id is None:
        return None
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == user.id,
    ).first()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if project_id is not None and conversation.project_id != project_id:
        raise HTTPException(status_code=400, detail="Conversation does not belong to the selected project")
    return conversation


@router.post("/memory-candidate", response_model=MemoryCandidateResponse)
def memory_candidate(request: MemoryCandidateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    candidate = detect_memory_candidate(request.message)
    if candidate is None:
        return MemoryCandidateResponse(candidate=None, duplicate=False)
    duplicate = find_duplicate_memory(db=db, user=current_user, memory_type=candidate["memory_type"], content=candidate["content"])
    return MemoryCandidateResponse(candidate=candidate, duplicate=duplicate is not None)


@router.post("/memory-confirm", response_model=MemoryConfirmResponse)
def memory_confirm(request: MemoryConfirmRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    duplicate = find_duplicate_memory(db=db, user=current_user, memory_type=request.memory_type, content=request.content)
    if duplicate is not None:
        return MemoryConfirmResponse(saved=False, duplicate=True, message="This memory is already saved.")
    create_memory(db=db, user=current_user, memory_type=request.memory_type, content=request.content)
    return MemoryConfirmResponse(saved=True, duplicate=False, message="Memory saved successfully.")


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    conversation = validate_conversation(db, current_user, request.conversation_id, request.project_id)
    effective_project_id = request.project_id if conversation is None else conversation.project_id
    history = get_recent_chats(db=db, user=current_user, project_id=effective_project_id, conversation_id=request.conversation_id)
    memories = get_memories(db=db, user=current_user)
    context = build_request_context(db=db, user=current_user, project_id=effective_project_id)
    response = chat_with_ai(message=request.message, history=history, memories=memories, context=context, engine=request.engine, action=request.action)
    save_chat(db=db, user=current_user, user_message=request.message, ai_response=response, project_id=effective_project_id, conversation_id=request.conversation_id)
    return ChatResponse(response=response)


@router.post("/chat/stream")
def stream_chat(request: ChatRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    conversation = validate_conversation(db, current_user, request.conversation_id, request.project_id)
    effective_project_id = request.project_id if conversation is None else conversation.project_id
    history = get_recent_chats(db=db, user=current_user, project_id=effective_project_id, conversation_id=request.conversation_id)
    memories = get_memories(db=db, user=current_user)
    context = build_request_context(db=db, user=current_user, project_id=effective_project_id)

    def generate():
        chunks = []
        try:
            for chunk in stream_chat_with_ai(message=request.message, history=history, memories=memories, context=context, engine=request.engine, action=request.action):
                chunks.append(chunk)
                yield chunk
            complete_response = "".join(chunks)
            save_chat(db=db, user=current_user, user_message=request.message, ai_response=complete_response, project_id=effective_project_id, conversation_id=request.conversation_id)
        finally:
            db.close()

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


@router.get("/history", response_model=list[ChatHistory])
def history(project_id: int | None = None, conversation_id: int | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if project_id is not None:
        project = get_project(db=db, user=current_user, project_id=project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
    validate_conversation(db, current_user, conversation_id, project_id)
    return get_chat_history(db=db, user=current_user, project_id=project_id, conversation_id=conversation_id)
