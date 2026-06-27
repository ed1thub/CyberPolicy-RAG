from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from backend.app.audit.routes import router as audit_router
from backend.app.auth.routes import router as auth_router
from backend.app.chat.routes import router as chat_router
from backend.app.config import settings
from backend.app.database import init_database
from backend.app.documents.routes import router as documents_router

_UI_FILE = Path(__file__).resolve().parents[2] / "frontend" / "policy_chat_ui.html"


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
    allow_origins=["http://localhost:8501", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(audit_router)
app.include_router(documents_router)


@app.get("/", include_in_schema=False)
def root(request: Request):
    if "text/html" in request.headers.get("accept", ""):
        return FileResponse(_UI_FILE, media_type="text/html")
    return {
        "project": settings.app_name,
        "version": "0.1.0",
        "description": "Secure AI assistant for cybersecurity policy Q&A using RAG.",
        "environment": settings.environment,
        "docs": "/docs",
        "ui": "/",
    }


@app.get("/ui", include_in_schema=False)
def serve_ui_alias() -> RedirectResponse:
    return RedirectResponse(url="/")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
