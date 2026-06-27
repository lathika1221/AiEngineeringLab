from fastapi import FastAPI

from src.config.settings import settings
from src.api.routes.health import router as health_router
from src.utils.logger import logger
from src.api.routes.auth import router as auth_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-style AI Engineering Backend",
    version=settings.VERSION,
)

logger.info("AIEngineeringLab API started successfully.")
app.include_router(auth_router)

app.include_router(
    
    health_router,
    prefix="/health",
    tags=["Health"],
)