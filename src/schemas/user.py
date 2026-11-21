from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator


USERNAME_MIN, USERNAME_MAX = 3, 100


def validate_username(value: str) -> str:
    """A username must never be able to look like an e-mail address, because login accepts
    either one in the same field. '@' is therefore not allowed, which keeps the two
    identifier spaces disjoint. Whitespace and control characters are refused so that
    visually identical names cannot coexist."""
    if not USERNAME_MIN <= len(value) <= USERNAME_MAX:
        raise ValueError(f"Username must be {USERNAME_MIN} to {USERNAME_MAX} characters")
    if "@" in value:
        raise ValueError("Username must not contain '@'")
    if any(ch.isspace() or not ch.isprintable() for ch in value):
        raise ValueError("Username must not contain spaces or control characters")
    return value


def normalize_email(value: str) -> str:
    return value.strip().lower()


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str = Field(min_length=12)

    @field_validator("username")
    @classmethod
    def validate_username_rules(cls, value: str) -> str:
        return validate_username(value)

    @field_validator("email")
    @classmethod
    def normalize_email_case(cls, value: str) -> str:
        # E-mail addresses are stored and compared in lower case so that "A@x.com" and
        # "a@x.com" are one account. Usernames keep the case the user typed.
        return normalize_email(value)

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


def _check_password_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password must not exceed 72 UTF-8 bytes")
    return value


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=12)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_bytes(cls, value: str) -> str:
        return _check_password_bytes(value)


class AccountDeletion(BaseModel):
    password: str = Field(min_length=1, max_length=200)
