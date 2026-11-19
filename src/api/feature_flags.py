from fastapi import HTTPException

from src.config.settings import settings


def require_registration_enabled() -> None:
    """Reject new sign-ups while REGISTRATION_ENABLED is false."""
    if not settings.REGISTRATION_ENABLED:
        raise HTTPException(status_code=403, detail="Registration is currently closed.")


def require_ai_enabled() -> None:
    """Reject model-backed requests while AI_ENABLED is false."""
    if not settings.AI_ENABLED:
        raise HTTPException(status_code=503, detail="AI features are temporarily unavailable.")
