from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


class MemoryCandidateResponse(BaseModel):
    candidate: bool
    memory_type: str | None = None
    content: str | None = None