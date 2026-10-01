from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


MemoryType = Literal[
    "preference",
    "fact",
    "project",
]


class MemoryCreate(BaseModel):
    memory_type: MemoryType
    content: str


class MemoryResponse(BaseModel):
    id: int
    memory_type: MemoryType
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )