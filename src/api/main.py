from fastapi import FastAPI

from src.config.settings import settings
from src.utils.logger import logger

from src.api.routes.health import router as health_router
from src.api.routes.auth import router as auth_router
from src.api.routes.users import router as users_router
from src.api.routes.ai import router as ai_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-style AI Engineering Backend",
    version=settings.VERSION,
)

logger.info("AIEngineeringLab API started successfully.")

# Authentication Routes
app.include_router(auth_router)

app.include_router(ai_router)

# User Routes (Protected)
app.include_router(users_router)

# Health Check Routes
app.include_router(
    health_router,
    prefix="/health",
    tags=["Health"],
)