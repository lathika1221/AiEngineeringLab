from pydantic import BaseModel, ConfigDict


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

    model_config = ConfigDict(from_attributes=True)