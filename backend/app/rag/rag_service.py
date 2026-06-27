"""RAG service: orchestrates access control, retrieval, generation, and citations."""

from dataclasses import dataclass

from backend.app.config import settings
from backend.app.rag.llm_adapter import (
    LLMProvider,
    MockLLM,
    NO_SOURCE_ANSWER,
    POLICY_NOT_SPECIFIED_ANSWER,
)
from backend.app.rag.retriever import Retriever
from backend.app.rag.vector_store import SearchResult, VectorStore


@dataclass(frozen=True)
class SourceCitation:
    """One document source returned alongside an answer."""

    document_title: str
    filename: str
    section_heading: str | None
    page: int | None


@dataclass
class ChatResponse:
    """Structured answer returned by the RAG service."""

    answer: str
    sources: list[SourceCitation]
    risk_flags: list[str]
    confidence: str  # "high" | "medium" | "low" | "none" | "blocked"


# Standard response when no authorised chunks are found
_NO_SOURCE_RESPONSE = ChatResponse(
    answer=NO_SOURCE_ANSWER,
    sources=[],
    risk_flags=[],
    confidence="none",
)


class RagService:
    """
    Orchestrates the secure RAG pipeline.

    Security flow (enforced in order):
    1. Determine allowed sensitivity levels for the user role.
    2. Return no-source response immediately for unknown roles.
    3. Retrieve only authorised chunks from the vector store.
    4. Return no-source response if no chunks match.
    5. Pass only the retrieved (authorised) chunks to the LLM.
    6. Build citations from retrieved chunk metadata.

    The LLM never receives chunks the user is not authorised to read.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        llm: LLMProvider | None = None,
    ) -> None:
        self._retriever = Retriever(vector_store)
        self._llm: LLMProvider = llm or MockLLM()
        self._top_k = max(1, settings.rag_top_k)

    def answer(self, question: str, role: str) -> ChatResponse:
        """Answer a question using only documents the role is allowed to access."""
        # Access control before retrieval — unknown roles get no results
        results = self._retriever.retrieve_for_role(
            question,
            role,
            top_k=self._top_k,
        )

        if not results:
            return _NO_SOURCE_RESPONSE

        # LLM only sees the authorised retrieved context
        context_chunks = [result.text for result in results]
        answer_text = self._llm.generate(question, context_chunks)
        if answer_text == POLICY_NOT_SPECIFIED_ANSWER:
            return ChatResponse(
                answer=answer_text,
                sources=[],
                risk_flags=[],
                confidence="none",
            )
        sources = _build_citations(results)

        return ChatResponse(
            answer=answer_text,
            sources=sources,
            risk_flags=[],
            confidence="high",
        )


def _build_citations(results: list[SearchResult]) -> list[SourceCitation]:
    """Deduplicate and build source citations from search results."""
    seen: set[tuple[str, str, str | None]] = set()
    citations: list[SourceCitation] = []

    for result in results:
        meta = result.metadata
        raw_section = meta.get("section_heading")
        section = None if not raw_section or raw_section == "Unknown" else raw_section

        raw_page = meta.get("page", 0)
        page = int(raw_page) if raw_page and int(raw_page) != 0 else None

        key = (meta.get("document_title", ""), meta.get("filename", ""), section)
        if key in seen:
            continue

        seen.add(key)
        citations.append(
            SourceCitation(
                document_title=meta.get("document_title", ""),
                filename=meta.get("filename", ""),
                section_heading=section,
                page=page,
            )
        )

    return citations
