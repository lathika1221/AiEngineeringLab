from datetime import datetime

from pydantic import BaseModel


class GoalCreate(BaseModel):
    title: str
    description: str | None = None
    category: str | None = None
    priority: int = 1
    target_date: datetime | None = None


class GoalResponse(BaseModel):
    id: int
    user_id: int
    title: str
    description: str | None
    category: str | None
    priority: int
    status: str
    target_date: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True