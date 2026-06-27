"""Role-aware retriever that enforces access control before vector search."""

import re

from backend.app.rag.vector_store import SearchResult, VectorStore
from backend.app.security.access_control import get_allowed_sensitivity_levels

DEFAULT_TOP_K = 3
MAX_CANDIDATE_CHUNKS = 12
_SEARCH_STOP_WORDS = {
    "about",
    "and",
    "are",
    "can",
    "does",
    "document",
    "employees",
    "for",
    "how",
    "if",
    "is",
    "must",
    "policy",
    "required",
    "should",
    "the",
    "this",
    "to",
    "users",
    "what",
    "when",
    "which",
}


class Retriever:
    """Combines access control with vector store search.

    Access control is applied first: the retriever determines the allowed
    sensitivity levels for the given role and passes them to the vector store
    as a hard filter. The vector store never returns chunks outside those levels.
    Unknown roles receive an empty allowed list and therefore no results.
    """

    def __init__(self, vector_store: VectorStore) -> None:
        self._vector_store = vector_store

    def retrieve_for_role(
        self,
        question: str,
        role: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[SearchResult]:
        """Return only chunks the role is authorised to read.

        Steps:
        1. Determine allowed sensitivity levels for role (deny-by-default).
        2. Return empty list immediately if role has no allowed levels.
        3. Pass allowed levels as a hard filter to vector store search.
        """
        allowed_levels = get_allowed_sensitivity_levels(role)
        if not allowed_levels:
            return []
        candidate_k = max(top_k, min(top_k * 4, MAX_CANDIDATE_CHUNKS))
        candidates = self._vector_store.search(
            question,
            allowed_levels,
            top_k=candidate_k,
        )
        return _rerank_results(question, candidates)[:top_k]


def _rerank_results(question: str, results: list[SearchResult]) -> list[SearchResult]:
    """Prefer chunks with lexical matches while preserving vector distance ties."""
    keywords = _question_keywords(question)
    if not keywords:
        return results

    indexed_results = list(enumerate(results))
    indexed_results.sort(
        key=lambda item: (
            -_lexical_score(keywords, item[1]),
            item[1].distance if item[1].distance is not None else float("inf"),
            item[0],
        )
    )
    return [result for _, result in indexed_results]


def _question_keywords(question: str) -> set[str]:
    keywords = {
        word
        for word in re.findall(r"[a-z0-9]+", question.lower())
        if len(word) > 2 and word not in _SEARCH_STOP_WORDS
    }
    if "sensitivity" in keywords:
        keywords.add("classification")
    if "classification" in keywords:
        keywords.add("sensitivity")
    if {"fix", "fixed"} & keywords:
        keywords.update({"remediation", "remediate", "remediated"})
    if "ai" in keywords:
        keywords.add("artificial")
    return keywords


def _lexical_score(keywords: set[str], result: SearchResult) -> int:
    metadata_text = " ".join(
        str(result.metadata.get(field, ""))
        for field in ("document_title", "filename", "section_heading")
    )
    haystack = f"{metadata_text} {result.text}".lower()
    return sum(haystack.count(keyword) for keyword in keywords)
