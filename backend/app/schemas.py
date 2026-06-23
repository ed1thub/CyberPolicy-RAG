"""Pydantic request and response schemas for the API."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Validated question submitted to the chat endpoint."""

    question: str = Field(min_length=1, max_length=1000)

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


class ChatResponse(BaseModel):
    """Structured response returned by the chat endpoint."""

    answer: str
    sources: list[SourceCitation]
    risk_flags: list[str]
    confidence: Literal["high", "medium", "low", "none", "blocked"]
