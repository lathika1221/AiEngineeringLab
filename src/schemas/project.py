from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    status: str = "active"
    engine: str | None = None
    tech_stack: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    engine: str | None = None
    tech_stack: str | None = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str | None
    status: str
    engine: str | None
    tech_stack: str | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {
        "from_attributes": True,
    }