from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.audit.routes import router as audit_router
from backend.app.auth.routes import router as auth_router
from backend.app.chat.routes import router as chat_router
from backend.app.config import settings
from backend.app.database import init_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialise local database tables and demo users at application startup."""
    init_database()
    yield

app = FastAPI(
    title=settings.app_name,
    description="Secure AI assistant for cybersecurity policy Q&A using RAG.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(audit_router)


@app.get("/")
def root() -> dict:
    return {
        "project": settings.app_name,
        "version": "0.1.0",
        "description": "Secure AI assistant for cybersecurity policy Q&A using RAG.",
        "environment": settings.environment,
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
