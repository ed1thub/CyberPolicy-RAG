"""Deterministic sensitivity classification catalogue built from policy Examples sections.

Built at startup from the vector store's Examples-of-X chunks. Only positive
bullet items are indexed — negative-context bullets (inside 'must not include' blocks)
are never catalogued as classification evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SENSITIVITY_RANK: dict[str, int] = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}

_NEGATIVE_STARTERS = re.compile(
    r"must\s+not\b|not\s+allowed|prohibited|must\s+never|cannot\b|do\s+not\b|never\b",
    re.IGNORECASE,
)


@dataclass
class CatalogueEntry:
    sensitivity_level: str  # lowercase
    document_title: str
    source_document: str    # filename
    source_section: str     # section heading


class SensitivityCatalogue:
    """Lookup: item name → highest sensitivity level it appears in (Examples sections only)."""

    def __init__(self) -> None:
        self._entries: dict[str, CatalogueEntry] = {}

    def lookup(self, item: str) -> CatalogueEntry | None:
        """Return entry for item or its singular/plural variant, or None."""
        for key in _normalize_variants(item):
            hit = self._entries.get(key)
            if hit:
                return hit
        return None

    def build_from_chunks(self, chunks: list) -> None:  # list[SearchResult]
        """Populate from SearchResult objects — only processes Examples sections."""
        for chunk in chunks:
            heading = str(chunk.metadata.get("section_heading", "")).lower()
            if "examples" not in heading:
                continue
            level = str(chunk.metadata.get("sensitivity_level", "")).lower()
            if level not in SENSITIVITY_RANK:
                continue
            filename = str(chunk.metadata.get("filename", ""))
            doc_title = str(chunk.metadata.get("document_title", filename))
            section = str(chunk.metadata.get("section_heading", ""))
            for item in _extract_positive_bullets(chunk.text):
                self._add(
                    item,
                    CatalogueEntry(
                        sensitivity_level=level,
                        document_title=doc_title,
                        source_document=filename,
                        source_section=section,
                    ),
                )

    def _add(self, raw_item: str, entry: CatalogueEntry) -> None:
        new_rank = SENSITIVITY_RANK.get(entry.sensitivity_level, 0)
        for key in _normalize_variants(raw_item):
            existing = self._entries.get(key)
            if existing is None or new_rank > SENSITIVITY_RANK.get(existing.sensitivity_level, 0):
                self._entries[key] = entry


def _normalize_variants(item: str) -> list[str]:
    """Return normalized forms including singular/plural variants."""
    text = re.sub(r"[^\w\s]", " ", item.lower())
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    variants = {text}
    if text.endswith("es") and len(text) > 4:
        variants.add(text[:-2])
    elif text.endswith("s") and len(text) > 3:
        variants.add(text[:-1])
    else:
        variants.add(text + "s")
    return list(variants)


def _extract_positive_bullets(section_text: str) -> list[str]:
    """Return bullet items only from positive (non-negative-context) paragraphs."""
    in_negative = False
    items: list[str] = []

    for line in section_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            in_negative = False
            continue

        is_bullet = stripped.startswith(("- ", "* ", "• "))

        if not is_bullet:
            in_negative = bool(_NEGATIVE_STARTERS.search(stripped))
            continue

        if in_negative:
            continue

        item_text = stripped[2:].strip().rstrip(".")
        if item_text and not _NEGATIVE_STARTERS.search(item_text):
            items.append(item_text)

    return items
