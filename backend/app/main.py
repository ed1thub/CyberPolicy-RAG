from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import settings

app = FastAPI(
    title=settings.app_name,
    description="Secure AI assistant for cybersecurity policy Q&A using RAG.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
