import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.database.session import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/")
def health_check():
    """Liveness: the process is up. Deliberately does not touch the database."""
    return {
        "status": "Healthy",
        "service": "AIEngineeringLab API",
        "version": "1.0.0"
    }


@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    """Readiness: the database answers a trivial query.

    The failure body is fixed text. The exception details are not returned
    (they can contain host names), only the exception type is logged.
    """
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("Readiness check failed: database unreachable (%s)", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "unreachable"},
        )
    return {"status": "ready", "database": "ok"}
