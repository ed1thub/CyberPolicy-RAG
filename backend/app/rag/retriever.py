"""Role-aware retriever that enforces access control before vector search."""

import re

from backend.app.rag.vector_store import SearchResult, VectorStore
from backend.app.security.access_control import get_allowed_sensitivity_levels

DEFAULT_TOP_K = 3
MAX_CANDIDATE_CHUNKS = 12
_SEARCH_STOP_WORDS = {
    "a", "about", "an", "and", "are", "can", "do", "does", "document",
    "employees", "for", "how", "if", "in", "is", "it", "must", "of",
    "policy", "required", "should", "the", "they", "this", "to", "users",
    "what", "when", "which", "with",
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
        """Return only chunks the role is authorised to read."""
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


# ---------------------------------------------------------------------------
# Reranking helpers
# ---------------------------------------------------------------------------

def _rerank_results(question: str, results: list[SearchResult]) -> list[SearchResult]:
    """Multi-signal rerank: phrase > sensitivity_level > intent_heading > lexical > vector."""
    keywords = _question_keywords(question)

    def _score(item: tuple[int, SearchResult]) -> tuple:
        idx, result = item
        phrase  = _exact_phrase_score(question, result)
        level   = _sensitivity_level_score(question, result)
        intent  = _intent_heading_boost(question, result)
        lexical = _lexical_score(keywords, result) if keywords else 0
        dist    = result.distance if result.distance is not None else float("inf")
        # Negate scores so lower tuple = better rank
        return (-phrase, -level, -intent, -lexical, dist, idx)

    indexed = list(enumerate(results))
    indexed.sort(key=_score)
    return [r for _, r in indexed]


def _exact_phrase_score(question: str, result: SearchResult) -> int:
    """Score based on exact multi-word phrase matches from the query in the chunk."""
    words = re.findall(r"[a-z0-9]+", question.lower())
    # Build bigrams and trigrams; skip phrases composed entirely of stop words
    phrases: list[str] = []
    for n in (2, 3):
        for i in range(len(words) - n + 1):
            gram = words[i : i + n]
            if any(w not in _SEARCH_STOP_WORDS for w in gram):
                phrases.append(" ".join(gram))

    if not phrases:
        return 0

    haystack = f"{result.text} {result.metadata.get('section_heading', '')}".lower()
    return sum(3 for phrase in phrases if phrase in haystack)


def _sensitivity_level_score(question: str, result: SearchResult) -> int:
    """Boost chunks whose sensitivity level is explicitly mentioned in the question."""
    q = question.lower()
    chunk_level = str(result.metadata.get("sensitivity_level", "")).lower()
    for level in ("confidential", "restricted", "internal", "public"):
        if level in q and level in chunk_level:
            return 4
    return 0


def _intent_heading_boost(question: str, result: SearchResult) -> int:
    """Return a boost when the chunk's section heading matches the question intent."""
    q = question.lower()
    heading = str(result.metadata.get("section_heading", "")).lower()

    intents = [
        # (question pattern, heading keyword, score)
        (r"\bwhat\s+is\b|\bdefin|\bmeaning\b", "definition", 4),
        (r"\bwhat\s+sensitivity\s+level|\bwhich\s+.*\blevel\b|\bwhat\s+level\b", "examples", 4),
        (r"\bexample|\bwhat\b.*\binclude|\bsource\s+code\b|\bapi\s+key", "examples", 3),
        (r"\bwhere\b.*\bstor|\bstor(age|ed|ing)\b", "storage", 3),
        (r"\bhow\s+often\b|\bhow\s+frequent|\breviewed?\b.*\baccess|\baccess\b.*\brevie", "access control", 3),
        (r"\bai\s+tool|\bartificial\s+intell|\bchatgpt|\bcopilot\b", "ai tool", 3),
        (r"\breport|\bincident\b", "incident", 3),
        (r"\btransmit|\bsend\b.*\bdata|\bshare\b.*\bdata", "transmission", 2),
        (r"\bencrypt", "encryption", 2),
        (r"\bscope\b|\bwho\b.*\bappl", "scope", 2),
        (r"\bthird.party|\bvendor\b", "third-party", 2),
    ]

    best = 0
    for pattern, heading_kw, score in intents:
        if re.search(pattern, q) and heading_kw in heading:
            best = max(best, score)
    return best


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
