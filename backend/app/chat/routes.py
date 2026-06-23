"""Authenticated chat API routes."""

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.auth.dependencies import get_current_user
from backend.app.models import User
from backend.app.rag.rag_service import RagService
from backend.app.rag.vector_store import VectorStore
from backend.app.schemas import ChatRequest, ChatResponse, SourceCitation

router = APIRouter(prefix="/chat", tags=["chat"])


@lru_cache
def get_rag_service() -> RagService:
    """Create the application's local RAG service on first use."""
    return RagService(vector_store=VectorStore())


@router.post("/query", response_model=ChatResponse)
def query_chat(
    request: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    rag_service: Annotated[RagService, Depends(get_rag_service)],
) -> ChatResponse:
    """Answer an authenticated user's question using their current role."""
    result = rag_service.answer(request.question, current_user.role)
    return ChatResponse(
        answer=result.answer,
        sources=[
            SourceCitation(
                document_title=source.document_title,
                filename=source.filename,
                section_heading=source.section_heading,
                page=source.page,
            )
            for source in result.sources
        ],
        risk_flags=result.risk_flags,
        confidence=result.confidence,
    )
