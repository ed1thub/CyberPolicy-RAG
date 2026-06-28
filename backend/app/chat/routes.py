"""Authenticated chat API routes."""

import json
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.audit.audit_service import create_audit_log
from backend.app.auth.dependencies import get_current_user
from backend.app.database import get_db
from backend.app.models import Chat, ChatMessage, User
from backend.app.rag.rag_service import RagService
from backend.app.rag.vector_store import VectorStore
from backend.app.schemas import ChatRequest, ChatResponse, SourceCitation
from backend.app.security.output_guard import check_output
from backend.app.security.prompt_guard import BLOCKED_ANSWER, check_prompt

router = APIRouter(prefix="/chat", tags=["chat"])

_NEW_CHAT_TITLE = "New chat"


@lru_cache
def get_rag_service() -> RagService:
    """Create the application's local RAG service on first use."""
    return RagService(vector_store=VectorStore())


def _get_or_create_chat(
    chat_id: int | None, user: User, db: Session
) -> Chat:
    """Return an existing chat (verified owner) or create a new one."""
    if chat_id is not None:
        chat = db.get(Chat, chat_id)
        if chat is None or chat.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Chat not found or access denied",
            )
        return chat
    chat = Chat(user_id=user.id, title=_NEW_CHAT_TITLE)
    db.add(chat)
    db.flush()   # populate chat.id without committing yet
    return chat


def _persist_exchange(
    db: Session,
    chat: Chat,
    question: str,
    answer: str,
    sources: list[SourceCitation],
    risk_flags: list[str],
    confidence: str,
) -> None:
    """Append user + assistant messages and update chat title from first question."""
    if chat.title == _NEW_CHAT_TITLE:
        snippet = question[:60] + ("…" if len(question) > 60 else "")
        chat.title = snippet
        db.add(chat)

    sources_json = json.dumps([s.model_dump() for s in sources])

    db.add(ChatMessage(chat_id=chat.id, role="user", content=question))
    db.add(ChatMessage(
        chat_id=chat.id,
        role="assistant",
        content=answer,
        sources=sources_json,
        risk_flags=json.dumps(risk_flags),
        confidence=confidence,
    ))
    db.commit()


@router.post("/query", response_model=ChatResponse)
def query_chat(
    request: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    rag_service: Annotated[RagService, Depends(get_rag_service)],
    database_session: Annotated[Session, Depends(get_db)],
) -> ChatResponse:
    """Answer an authenticated user's question using their current role."""
    chat = _get_or_create_chat(request.chat_id, current_user, database_session)

    # Prompt guard runs before retrieval — blocked prompts never reach the RAG service
    guard_result = check_prompt(request.question)
    if not guard_result.allowed:
        _persist_exchange(
            database_session, chat,
            question=request.question,
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
            risk_flags=guard_result.risk_flags,
        )
        return ChatResponse(
            answer=BLOCKED_ANSWER,
            sources=[],
            risk_flags=guard_result.risk_flags,
            confidence="blocked",
            chat_id=chat.id,
            chat_title=chat.title,
        )

    result = rag_service.answer(request.question, current_user.role)
    api_sources = [
        SourceCitation(
            document_title=source.document_title,
            filename=source.filename,
            section_heading=source.section_heading,
            page=source.page,
            sensitivity_level=source.sensitivity_level,
        )
        for source in result.sources
    ]
    response = ChatResponse(
        answer=result.answer,
        sources=api_sources,
        risk_flags=result.risk_flags,
        confidence=result.confidence,
        chat_id=chat.id,
        chat_title=chat.title,
    )

    output_guard_result = check_output(response.answer)
    if not output_guard_result.allowed:
        merged_flags = _merge_risk_flags(response.risk_flags, output_guard_result.risk_flags)
        response = ChatResponse(
            answer=output_guard_result.answer,
            sources=response.sources,
            risk_flags=merged_flags,
            confidence="blocked",
            chat_id=chat.id,
            chat_title=chat.title,
        )

    _persist_exchange(
        database_session, chat,
        question=request.question,
        answer=response.answer,
        sources=response.sources,
        risk_flags=response.risk_flags,
        confidence=response.confidence,
    )

    create_audit_log(
        database_session,
        user=current_user,
        question=request.question,
        answer_status=_answer_status_for(response.confidence),
        documents_used=[source.filename for source in response.sources],
        risk_flags=response.risk_flags,
    )
    return response


def _merge_risk_flags(existing_flags: list[str], new_flags: list[str]) -> list[str]:
    """Append new risk flags without duplicates while preserving order."""
    merged_flags = list(existing_flags)
    for flag in new_flags:
        if flag not in merged_flags:
            merged_flags.append(flag)
    return merged_flags


def _answer_status_for(confidence: str) -> str:
    """Map final chat confidence to the stored audit status."""
    if confidence == "none":
        return "no_source"
    if confidence == "blocked":
        return "blocked"
    return "answered"
