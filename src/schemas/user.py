from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str = Field(min_length=12)

    @field_validator("password")
    @classmethod
    def validate_password_byte_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes")
        return value


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)