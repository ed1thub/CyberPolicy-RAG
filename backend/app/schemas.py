"""Pydantic request and response schemas for the API."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Validated question submitted to the chat endpoint."""

    question: str = Field(min_length=1, max_length=1000)
    chat_id: int | None = None

    @field_validator("question")
    @classmethod
    def question_must_contain_text(cls, value: str) -> str:
        """Reject questions containing only whitespace."""
        stripped_question = value.strip()
        if not stripped_question:
            raise ValueError("Question cannot be empty")
        return stripped_question


class SourceCitation(BaseModel):
    """Document metadata supporting a generated answer."""

    document_title: str
    filename: str
    section_heading: str | None = None
    page: int | None = None
    sensitivity_level: str | None = None


class ChatResponse(BaseModel):
    """Structured response returned by the chat endpoint."""

    answer: str
    sources: list[SourceCitation]
    risk_flags: list[str]
    confidence: Literal["high", "medium", "low", "none", "blocked"]
    chat_id: int
    chat_title: str


# ── Chat history schemas ───────────────────────────────────────────────────────

class ChatSummary(BaseModel):
    """Lightweight chat row returned in list views."""

    id: int
    title: str
    pinned: bool = False
    created_at: str


class ChatUpdateRequest(BaseModel):
    """Partial update payload for rename / pin operations."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    pinned: bool | None = None


class MessageOut(BaseModel):
    """One persisted message (user or assistant) in a chat."""

    id: int
    role: str
    content: str
    sources: list[SourceCitation]
    risk_flags: list[str]
    confidence: str | None
    created_at: str


class ChatDetail(BaseModel):
    """Full chat with all messages, returned to the owning user."""

    id: int
    title: str
    created_at: str
    messages: list[MessageOut]
