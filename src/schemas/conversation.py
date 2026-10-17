from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class ConversationCreate(BaseModel):
    title: str = Field(default="New Chat", min_length=1, max_length=200)
    category: str = Field(default="general", max_length=50)
    project_id: int | None = None


class ConversationRead(BaseModel):
    id: int
    title: str
    category: str
    project_id: int | None = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
