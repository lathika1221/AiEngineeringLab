from pydantic import BaseModel


class ProfileBase(BaseModel):
    display_name: str | None = None
    bio: str | None = None
    timezone: str | None = None


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(ProfileBase):
    pass


class ProfileResponse(ProfileBase):
    id: int
    user_id: int
    onboarding_completed: str

    class Config:
        from_attributes = True