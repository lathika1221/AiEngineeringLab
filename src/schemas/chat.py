from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatHistory(BaseModel):
    id: int
    user_message: str
    ai_response: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)