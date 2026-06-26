from fastapi import FastAPI

from src.config.settings import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-style AI Engineering Backend",
    version=settings.VERSION,
)


@app.get("/")
def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} 🚀",
        "status": "Running",
        "debug": settings.DEBUG,
    }