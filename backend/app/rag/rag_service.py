"""RAG service: orchestrates access control, routing, retrieval, generation, citations."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from backend.app.config import settings
from backend.app.rag.catalogue import SensitivityCatalogue
from backend.app.rag.llm_adapter import (
    LLMProvider,
    MockLLM,
    NO_SOURCE_ANSWER,
    POLICY_NOT_SPECIFIED_ANSWER,
)
from backend.app.rag.retriever import Retriever
from backend.app.rag.router import Route, detect_intent
from backend.app.rag.vector_store import SearchResult, VectorStore
from backend.app.security.access_control import get_allowed_sensitivity_levels


@dataclass(frozen=True)
class SourceCitation:
    document_title: str
    filename: str
    section_heading: str | None
    page: int | None
    sensitivity_level: str | None = None


@dataclass
class ChatResponse:
    answer: str
    sources: list[SourceCitation]
    risk_flags: list[str]
    confidence: str  # "high" | "medium" | "low" | "none" | "blocked"


_NO_SOURCE_RESPONSE = ChatResponse(
    answer=NO_SOURCE_ANSWER,
    sources=[],
    risk_flags=[],
    confidence="none",
)

_SENSITIVITY_NOISE = frozenset({
    "what", "is", "are", "the", "sensitivity", "level", "of", "a", "an",
    "data", "which", "for", "in", "to",
})
_VALID_LEVELS = frozenset({"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"})


class RagService:
    """
    Orchestrates the secure RAG pipeline with intent-based routing.

    Route dispatch order (enforced in answer()):
    A. Sensitivity classification → deterministic catalogue lookup
    B. Definition query → hard section filter by sensitivity + heading
    C. Storage query → hard section filter by sensitivity + heading
    D. Access review query → hard section filter by sensitivity + heading
    E. General → vector RAG with reranking

    Security invariant: role-based sensitivity filtering is applied before any
    chunk text is returned. The LLM never receives chunks the role cannot read.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        llm: LLMProvider | None = None,
    ) -> None:
        self._vector_store = vector_store
        self._retriever = Retriever(vector_store)
        self._llm: LLMProvider = llm or MockLLM()
        self._top_k = max(1, settings.rag_top_k)
        self._catalogue = SensitivityCatalogue()
        self._catalogue.build_from_chunks(vector_store.get_all_chunks())

    def answer(self, question: str, role: str) -> ChatResponse:
        intent = detect_intent(question)

        if intent.route == Route.SENSITIVITY_LOOKUP and intent.subject:
            return self._route_sensitivity_lookup(question, intent.subject, role)

        if intent.route == Route.DEFINITION and intent.sensitivity_level:
            return self._route_section(
                question,
                intent.sensitivity_level,
                "definition",
                role,
                _extract_definition_answer,
            )

        if intent.route == Route.STORAGE and intent.sensitivity_level:
            return self._route_section(
                question,
                intent.sensitivity_level,
                "storage",
                role,
                _extract_storage_answer,
            )

        if intent.route == Route.ACCESS_REVIEW and intent.sensitivity_level:
            level = intent.sensitivity_level
            return self._route_section(
                question,
                level,
                "access control",
                role,
                lambda text: _extract_access_review_answer(text, level),
            )

        return self._route_general(question, role)

    # ------------------------------------------------------------------
    # Route handlers
    # ------------------------------------------------------------------

    def _route_sensitivity_lookup(
        self, question: str, subject: str, role: str
    ) -> ChatResponse:
        entry = self._catalogue.lookup(subject)
        if entry:
            allowed = get_allowed_sensitivity_levels(role)
            if entry.sensitivity_level not in allowed:
                return _NO_SOURCE_RESPONSE
            verb = "are" if re.search(r"\bare\b", question, re.IGNORECASE) else "is"
            answer = f"{subject} {verb} {entry.sensitivity_level.capitalize()}."
            citation = SourceCitation(
                document_title=entry.document_title,
                filename=entry.source_document,
                section_heading=entry.source_section,
                page=None,
                sensitivity_level=entry.sensitivity_level,
            )
            return ChatResponse(
                answer=answer,
                sources=[citation],
                risk_flags=[],
                confidence="high",
            )

        # Catalogue miss — fall back to vector search + metadata heuristic
        results = self._retriever.retrieve_for_role(question, role, top_k=self._top_k)
        if not results:
            return _NO_SOURCE_RESPONSE
        sensitivity_answer = _try_sensitivity_level_answer(question, results[0])
        if sensitivity_answer:
            return ChatResponse(
                answer=sensitivity_answer,
                sources=_build_citations([results[0]]),
                risk_flags=[],
                confidence="high",
            )
        return self._generate_from_results(question, results)

    def _route_section(
        self,
        question: str,
        level: str,
        heading_keyword: str,
        role: str,
        extractor: Callable[[str], str | None],
    ) -> ChatResponse:
        allowed = get_allowed_sensitivity_levels(role)
        if level not in allowed:
            return _NO_SOURCE_RESPONSE
        chunk = self._vector_store.get_section(level, heading_keyword)
        if chunk is None:
            return self._route_general(question, role)
        answer = extractor(chunk.text)
        if not answer:
            return self._route_general(question, role)
        return ChatResponse(
            answer=answer,
            sources=_build_citations([chunk]),
            risk_flags=[],
            confidence="high",
        )

    def _route_general(self, question: str, role: str) -> ChatResponse:
        results = self._retriever.retrieve_for_role(question, role, top_k=self._top_k)
        if not results:
            return _NO_SOURCE_RESPONSE
        return self._generate_from_results(question, results)

    def _generate_from_results(
        self, question: str, results: list[SearchResult]
    ) -> ChatResponse:
        sensitivity_answer = _try_sensitivity_level_answer(question, results[0])
        if sensitivity_answer:
            return ChatResponse(
                answer=sensitivity_answer,
                sources=_build_citations([results[0]]),
                risk_flags=[],
                confidence="high",
            )
        answer_text = self._llm.generate(question, [results[0].text])
        if answer_text == POLICY_NOT_SPECIFIED_ANSWER:
            return ChatResponse(
                answer=answer_text,
                sources=[],
                risk_flags=[],
                confidence="none",
            )
        return ChatResponse(
            answer=answer_text,
            sources=_build_citations([results[0]]),
            risk_flags=[],
            confidence="high",
        )


# ------------------------------------------------------------------
# Section-specific answer extractors
# ------------------------------------------------------------------

def _extract_definition_answer(text: str) -> str | None:
    """Return the first sentence of the first paragraph after the section heading."""
    heading_skipped = False
    for line in text.split("\n"):
        stripped = line.strip()
        if not heading_skipped:
            if stripped:
                heading_skipped = True
            continue
        if stripped and not stripped.startswith("#"):
            sentences = re.split(r"(?<=[.!?])\s+", stripped)
            first = sentences[0].strip() if sentences else stripped
            if len(first.split()) >= 5:
                return first
    return None


def _extract_storage_answer(text: str) -> str | None:
    """Expand 'X data may be stored in:\\n- A\\n- B' into a single sentence."""
    m = re.search(
        r"([^\n]*?(?:stored?|storage)\s+in\s*:)\s*\n+((?:\s*[-*•]\s*.+\n?)+)",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    intro = m.group(1).strip().rstrip(":")
    raw_items = re.findall(r"^\s*[-*•]\s*(.+)", m.group(2), re.MULTILINE)
    clean = [item.strip().replace("**", "").replace("`", "").rstrip(".") for item in raw_items]
    clean = [item[0].lower() + item[1:] for item in clean if item]
    if not clean:
        return None
    if len(clean) == 1:
        joined = clean[0]
    elif len(clean) == 2:
        joined = f"{clean[0]} and {clean[1]}"
    else:
        joined = ", ".join(clean[:-1]) + ", and " + clean[-1]
    return f"{intro} {joined}."


def _extract_access_review_answer(text: str, level: str) -> str | None:
    """Extract 'at least every X days' from an Access Control Requirements section."""
    m = re.search(
        r"reviewed?\s+at\s+least\s+every\s+(\d+\s+days)",
        text,
        re.IGNORECASE,
    )
    if m:
        days = m.group(1)
        return f"{level.capitalize()} data access must be reviewed at least every {days}."
    return None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _try_sensitivity_level_answer(question: str, top: SearchResult) -> str | None:
    """Return sensitivity level from chunk metadata for 'What sensitivity level is X?' queries."""
    q_lower = question.lower()
    if "sensitivity" not in q_lower:
        return None
    level = str(top.metadata.get("sensitivity_level", "")).strip().upper()
    if level not in _VALID_LEVELS:
        return None
    query_terms = [
        w for w in re.findall(r"[a-z][a-z0-9]*", q_lower)
        if w not in _SENSITIVITY_NOISE and len(w) > 2
    ]
    if not query_terms:
        return None
    text_lower = top.text.lower()
    if any(term in text_lower for term in query_terms):
        return f"{level.capitalize()}."
    return None


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
                sensitivity_level=meta.get("sensitivity_level") or None,
            )
        )
    return citations
