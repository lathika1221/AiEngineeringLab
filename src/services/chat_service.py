from sqlalchemy.orm import Session

from src.models.chat import Chat
from src.models.user import User


def save_chat(
    db: Session,
    user: User,
    user_message: str,
    ai_response: str,
):
    chat = Chat(
        user_id=user.id,
        user_message=user_message,
        ai_response=ai_response,
    )

    db.add(chat)
    db.commit()
    db.refresh(chat)

    return chat


def get_chat_history(
    db: Session,
    user: User,
):
    return (
        db.query(Chat)
        .filter(Chat.user_id == user.id)
        .order_by(Chat.created_at.desc())
        .all()
    )
def get_recent_chats(
    db: Session,
    user: User,
    limit: int = 10,
):
    chats = (
        db.query(Chat)
        .filter(Chat.user_id == user.id)
        .order_by(Chat.created_at.desc())
        .limit(limit)
        .all()
    )

    return list(reversed(chats))