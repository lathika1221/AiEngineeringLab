from datetime import datetime

from pydantic import BaseModel


class ChatHistory(BaseModel):
    id: int
    user_message: str
    ai_response: str
    created_at: datetime

    class Config:
        from_attributes = True