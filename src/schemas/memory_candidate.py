from pydantic import BaseModel


class MemoryCandidateRequest(BaseModel):
    message: str


class MemoryCandidate(BaseModel):
    memory_type: str
    content: str
    memory_key: str


class MemoryCandidateResponse(BaseModel):
    candidate: MemoryCandidate | None
    duplicate: bool


class MemoryConfirmRequest(BaseModel):
    memory_type: str
    content: str


class MemoryConfirmResponse(BaseModel):
    saved: bool
    duplicate: bool
    message: str