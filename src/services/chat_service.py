from sqlalchemy.orm import Session
from src.models.chat import Chat
from src.models.conversation import Conversation
from src.models.user import User


def save_chat(
    db: Session,
    user: User,
    user_message: str,
    ai_response: str,
    project_id: int | None = None,
    conversation_id: int | None = None,
):
    chat = Chat(
        user_id=user.id,
        project_id=project_id,
        conversation_id=conversation_id,
        user_message=user_message,
        ai_response=ai_response,
    )
    db.add(chat)

    if conversation_id is not None:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        ).first()
        if conversation is not None:
            if conversation.title == "New Chat":
                cleaned = " ".join(user_message.split())
                conversation.title = cleaned[:197] + "..." if len(cleaned) > 200 else cleaned or "New Chat"

    db.commit()
    db.refresh(chat)
    return chat


def get_chat_history(
    db: Session,
    user: User,
    project_id: int | None = None,
    conversation_id: int | None = None,
):
    query = db.query(Chat).filter(Chat.user_id == user.id)
    if conversation_id is not None:
        query = query.filter(Chat.conversation_id == conversation_id)
    else:
        if project_id is not None:
            query = query.filter(Chat.project_id == project_id)
        else:
            query = query.filter(Chat.project_id.is_(None))
        query = query.filter(Chat.conversation_id.is_(None))
    return query.order_by(Chat.created_at.asc(), Chat.id.asc()).all()


def get_recent_chats(
    db: Session,
    user: User,
    limit: int = 10,
    project_id: int | None = None,
    conversation_id: int | None = None,
):
    query = db.query(Chat).filter(Chat.user_id == user.id)
    if conversation_id is not None:
        query = query.filter(Chat.conversation_id == conversation_id)
    else:
        if project_id is not None:
            query = query.filter(Chat.project_id == project_id)
        else:
            query = query.filter(Chat.project_id.is_(None))
        query = query.filter(Chat.conversation_id.is_(None))
    chats = query.order_by(Chat.created_at.desc(), Chat.id.desc()).limit(limit).all()
    return list(reversed(chats))
