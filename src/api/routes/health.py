from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def health_check():
    return {
        "status": "Healthy",
        "service": "AIEngineeringLab API",
        "version": "1.0.0"
    }