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


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-style AI Engineering Backend",
    version=settings.VERSION,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


logger.info("AIEngineeringLab API started successfully.")


app.include_router(auth_router)

app.include_router(ai_router)

app.include_router(memory_router)

app.include_router(users_router)

app.include_router(memory_candidate_router)

app.include_router(
    health_router,
    prefix="/health",
    tags=["Health"],
)