from pydantic import BaseModel


class LifeRoleCreate(BaseModel):
    role: str
    description: str | None = None
    priority: int = 1


class LifeRoleResponse(BaseModel):
    id: int
    user_id: int
    role: str
    description: str | None = None
    priority: int

    class Config:
        from_attributes = True