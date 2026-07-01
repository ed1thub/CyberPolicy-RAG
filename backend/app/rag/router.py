"""Query intent router — classifies questions into deterministic retrieval routes.

Routes A–D bypass vector search entirely; Route E falls back to vector RAG.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto


class Route(Enum):
    SENSITIVITY_LOOKUP = auto()  # "What sensitivity level is/are X?"
    DEFINITION = auto()          # "What is Public/Internal/... data?"
    STORAGE = auto()             # "Where can X data be stored?"
    ACCESS_REVIEW = auto()       # "How often must X data access be reviewed?"
    GENERAL = auto()             # Vector RAG fallback


_LEVEL = r"(public|internal|confidential|restricted)"

_CLASSIFICATION_PATTERNS = [
    r"what\s+(?:sensitivity\s+)?(?:level|classification)\s+(?:is|are)\s+(.+?)[\?.]?$",
    r"how\s+is\s+(.+?)\s+classified[\?.]?$",
    r"which\s+(?:sensitivity\s+)?level\s+(?:is|are|does)\s+(.+?)[\?.]?$",
    r"is\s+(.+?)\s+(?:public|internal|confidential|restricted)[\?.]?$",
]


@dataclass
class QueryIntent:
    route: Route
    sensitivity_level: str | None = None  # detected level (Routes B–D and hint for E)
    subject: str | None = None            # extracted item for Route A


def detect_intent(question: str) -> QueryIntent:
    """Classify question into a retrieval route, preserving original casing for subject."""
    subject = _extract_classification_subject(question)
    if subject:
        return QueryIntent(route=Route.SENSITIVITY_LOOKUP, subject=subject)

    q = question.lower()

    m = re.search(rf"what\s+is\s+{_LEVEL}\s+data", q)
    if m:
        return QueryIntent(route=Route.DEFINITION, sensitivity_level=m.group(1))

    m = re.search(
        rf"where\s+(?:can|should|must|may)\s+{_LEVEL}\s+data\s+(?:be\s+)?stor",
        q,
    )
    if m:
        return QueryIntent(route=Route.STORAGE, sensitivity_level=m.group(1))

    if re.search(r"how\s+(?:often|frequent)", q) and "access" in q and "review" in q:
        m = re.search(_LEVEL, q)
        if m:
            return QueryIntent(route=Route.ACCESS_REVIEW, sensitivity_level=m.group(1))

    m = re.search(_LEVEL, q)
    return QueryIntent(route=Route.GENERAL, sensitivity_level=m.group(1) if m else None)


def _extract_classification_subject(question: str) -> str | None:
    """Extract 'X' from 'What sensitivity level is X?' preserving original casing."""
    for pattern in _CLASSIFICATION_PATTERNS:
        m = re.search(pattern, question, re.IGNORECASE)
        if m:
            item = m.group(1).strip().rstrip("?.")
            item = re.sub(
                r"\b(public|internal|confidential|restricted)\b",
                "",
                item,
                flags=re.IGNORECASE,
            ).strip()
            if len(item) >= 2:
                return item
    return None
