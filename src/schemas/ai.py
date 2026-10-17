from typing import Literal
from pydantic import BaseModel, Field

Engine = Literal["forge", "learn", "research", "explore", "solve"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    project_id: int | None = None
    conversation_id: int | None = None
    engine: Engine | None = None
    action: str | None = None


class ChatResponse(BaseModel):
    response: str


class MemoryCandidateResponse(BaseModel):
    candidate: bool
    memory_type: str | None = None
    content: str | None = None
