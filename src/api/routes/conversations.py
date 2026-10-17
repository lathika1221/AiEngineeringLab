from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.database.session import get_db
from src.models.conversation import Conversation
from src.models.user import User
from src.schemas.conversation import ConversationCreate, ConversationRead
from src.services.project_service import get_project

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get("", response_model=list[ConversationRead])
def list_conversations(
    category: str | None = Query(default=None, max_length=50),
    project_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Conversation).filter(Conversation.user_id == current_user.id)
    if category:
        query = query.filter(Conversation.category == category)
    if project_id is not None:
        project = get_project(db=db, user=current_user, project_id=project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        query = query.filter(Conversation.project_id == project_id)
    return query.order_by(Conversation.updated_at.desc(), Conversation.id.desc()).all()


@router.post("", response_model=ConversationRead, status_code=201)
def create_conversation(
    request: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if request.project_id is not None:
        project = get_project(db=db, user=current_user, project_id=request.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
    allowed = {"projects", "learning", "experiments", "research", "general"}
    category = request.category.strip().lower()
    if category not in allowed:
        raise HTTPException(status_code=422, detail=f"category must be one of: {', '.join(sorted(allowed))}")
    conversation = Conversation(
        user_id=current_user.id,
        project_id=request.project_id,
        title=request.title.strip() or "New Chat",
        category=category,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("/{conversation_id}", response_model=ConversationRead)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation
