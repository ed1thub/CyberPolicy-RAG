"""Authenticated chat API routes."""

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.audit.audit_service import create_audit_log
from backend.app.auth.dependencies import get_current_user
from backend.app.database import get_db
from backend.app.models import User
from backend.app.rag.rag_service import RagService
from backend.app.rag.vector_store import VectorStore
from backend.app.schemas import ChatRequest, ChatResponse, SourceCitation
from backend.app.security.prompt_guard import BLOCKED_ANSWER, check_prompt

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
    database_session: Annotated[Session, Depends(get_db)],
) -> ChatResponse:
    """Answer an authenticated user's question using their current role."""
    # Prompt guard runs before retrieval — blocked prompts never reach the RAG service
    guard_result = check_prompt(request.question)
    if not guard_result.allowed:
        response = ChatResponse(
            answer=BLOCKED_ANSWER,
            sources=[],
            risk_flags=guard_result.risk_flags,
            confidence="blocked",
        )
        create_audit_log(
            database_session,
            user=current_user,
            question=request.question,
            answer_status="blocked",
            documents_used=[],
            risk_flags=response.risk_flags,
        )
        return response

    result = rag_service.answer(request.question, current_user.role)
    response = ChatResponse(
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
    create_audit_log(
        database_session,
        user=current_user,
        question=request.question,
        answer_status="no_source" if result.confidence == "none" else "answered",
        documents_used=[source.filename for source in result.sources],
        risk_flags=result.risk_flags,
    )
    return response
