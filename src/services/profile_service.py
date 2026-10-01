from sqlalchemy.orm import Session

from src.models.profile import UserProfile
from src.models.user import User
from src.schemas.profile import ProfileCreate, ProfileUpdate


def get_profile(
    db: Session,
    user: User,
):
    return (
        db.query(UserProfile)
        .filter(UserProfile.user_id == user.id)
        .first()
    )


def create_profile(
    db: Session,
    user: User,
    profile_data: ProfileCreate,
):
    profile = UserProfile(
        user_id=user.id,
        display_name=profile_data.display_name,
        bio=profile_data.bio,
        timezone=profile_data.timezone,
        onboarding_completed="false",
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)

    return profile


def update_profile(
    db: Session,
    profile: UserProfile,
    profile_data: ProfileUpdate,
):
    if profile_data.display_name is not None:
        profile.display_name = profile_data.display_name

    if profile_data.bio is not None:
        profile.bio = profile_data.bio

    if profile_data.timezone is not None:
        profile.timezone = profile_data.timezone

    db.commit()
    db.refresh(profile)

    return profile


def complete_onboarding(
    db: Session,
    profile: UserProfile,
):
    profile.onboarding_completed = "true"

    db.commit()
    db.refresh(profile)

    return profile