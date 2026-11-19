from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import settings
from src.utils.logger import logger
from src.api.routes.health import router as health_router
from src.api.routes.auth import router as auth_router
from src.api.routes.users import router as users_router
from src.api.routes.ai import router as ai_router
from src.api.routes.memory import router as memory_router
from src.api.routes.memory_candidate import router as memory_candidate_router
from src.api.routes.projects import router as projects_router
from src.api.routes.conversations import router as conversations_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-style AI Engineering Backend",
    version=settings.VERSION,
    # API docs follow ENABLE_DOCS: on by default in development, off in production.
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info(
    "AIEngineeringLab API started successfully. environment=%s docs=%s cors_origins=%d registration=%s ai=%s",
    settings.ENVIRONMENT,
    "on" if settings.docs_enabled else "off",
    len(settings.cors_origins),
    "open" if settings.REGISTRATION_ENABLED else "closed",
    "on" if settings.AI_ENABLED else "off",
)
app.include_router(auth_router)
app.include_router(ai_router)
app.include_router(conversations_router)
app.include_router(memory_router)
app.include_router(users_router)
app.include_router(memory_candidate_router)
app.include_router(projects_router)
app.include_router(health_router, prefix="/health", tags=["Health"])
