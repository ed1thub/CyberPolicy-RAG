"""Split loaded documents into overlapping chunks with preserved metadata."""

import re
from dataclasses import dataclass
from pathlib import Path

from backend.app.documents.loader import LoadedDocument

TARGET_WORDS = 650   # aim for this chunk size
MAX_WORDS = 800      # never exceed this (unless a single paragraph is larger)
OVERLAP_WORDS = 100  # words shared between adjacent chunks


@dataclass
class DocumentChunk:
    """A single text chunk with all metadata needed for ChromaDB storage."""

    chunk_id: str
    text: str
    document_title: str
    filename: str
    sensitivity_level: str
    allowed_roles: str
    section_heading: str | None
    page: int | None

    def to_metadata(self) -> dict:
        """Return a flat scalar-only dict for ChromaDB metadata storage."""
        return {
            "document_title": self.document_title,
            "filename": self.filename,
            "sensitivity_level": self.sensitivity_level,
            "allowed_roles": self.allowed_roles,
            "section_heading": self.section_heading or "Unknown",
            "page": self.page if self.page is not None else 0,
            "chunk_id": self.chunk_id,
        }


def _word_count(text: str) -> int:
    return len(text.split())


def _make_chunk_id(filename: str, index: int) -> str:
    stem = Path(filename).stem
    return f"{stem}_{index:03d}"


def _extract_heading(line: str) -> str | None:
    """Return heading text if the line is a Markdown heading, else None."""
    match = re.match(r"^#{1,6}\s+(.+)$", line.strip())
    return match.group(1).strip() if match else None


def _split_paragraphs(text: str) -> list[str]:
    """Split text on blank lines, filtering empty blocks."""
    blocks = re.split(r"\n\s*\n", text)
    return [b.strip() for b in blocks if b.strip()]


def _build_heading_map(paragraphs: list[str], initial: str | None) -> list[str | None]:
    """
    Return a list where entry i is the section heading active at paragraph i.
    Each paragraph inherits the most recent heading seen before or at it.
    """
    result: list[str | None] = []
    current = initial
    for para in paragraphs:
        first_line = para.split("\n")[0]
        heading = _extract_heading(first_line)
        if heading:
            current = heading
        result.append(current)
    return result


def _build_chunks_from_paragraphs(
    paragraphs: list[str],
    heading_map: list[str | None],
    document: LoadedDocument,
    start_chunk_idx: int,
    base_page: int | None,
) -> list[DocumentChunk]:
    """
    Group paragraphs into chunks of TARGET_WORDS words (MAX_WORDS hard ceiling).
    Adjacent chunks share OVERLAP_WORDS words at their boundary.
    Short documents produce a single chunk.
    """
    if not paragraphs:
        return []

    chunks: list[DocumentChunk] = []
    chunk_idx = start_chunk_idx
    para_idx = 0
    n = len(paragraphs)

    while para_idx < n:
        chunk_start = para_idx
        word_count = 0
        current_heading = heading_map[para_idx]

        # Accumulate paragraphs until TARGET_WORDS or MAX_WORDS is reached
        while para_idx < n:
            para = paragraphs[para_idx]
            para_wc = _word_count(para)

            # Stop before MAX_WORDS if we have meaningful content already
            if word_count + para_wc > MAX_WORDS and word_count > 0:
                break

            word_count += para_wc
            current_heading = heading_map[para_idx]
            para_idx += 1

            if word_count >= TARGET_WORDS:
                break

        # Safety: if a single paragraph is larger than MAX_WORDS, include it anyway
        if para_idx == chunk_start:
            current_heading = heading_map[para_idx]
            para_idx += 1

        chunk_text = "\n\n".join(paragraphs[chunk_start:para_idx]).strip()

        # Compute overlap: back up para_idx so the next chunk re-reads ~OVERLAP_WORDS words
        if para_idx < n:
            overlap_accumulated = 0
            overlap_start = para_idx
            while overlap_start > chunk_start and overlap_accumulated < OVERLAP_WORDS:
                overlap_start -= 1
                overlap_accumulated += _word_count(paragraphs[overlap_start])
            # Only back up if it doesn't recreate the entire current chunk
            if overlap_start > chunk_start:
                para_idx = overlap_start

        chunks.append(
            DocumentChunk(
                chunk_id=_make_chunk_id(document.filename, chunk_idx),
                text=chunk_text,
                document_title=document.title,
                filename=document.filename,
                sensitivity_level=document.sensitivity_level,
                allowed_roles=document.allowed_roles,
                section_heading=current_heading,
                page=base_page,
            )
        )
        chunk_idx += 1

    return chunks


def chunk_document(document: LoadedDocument) -> list[DocumentChunk]:
    """
    Split a loaded document into overlapping chunks with full metadata.

    PDF documents are chunked per page so page numbers are preserved.
    Markdown and TXT documents are chunked from the full body text.
    Short documents that fall below TARGET_WORDS produce a single chunk.
    """
    if document.pages:
        return _chunk_pdf(document)
    return _chunk_text_body(document)


def _chunk_text_body(document: LoadedDocument) -> list[DocumentChunk]:
    paragraphs = _split_paragraphs(document.body)
    if not paragraphs:
        return []
    heading_map = _build_heading_map(paragraphs, initial=None)
    return _build_chunks_from_paragraphs(
        paragraphs=paragraphs,
        heading_map=heading_map,
        document=document,
        start_chunk_idx=1,
        base_page=None,
    )


def _chunk_pdf(document: LoadedDocument) -> list[DocumentChunk]:
    all_chunks: list[DocumentChunk] = []
    chunk_idx = 1
    for page in document.pages:
        paragraphs = _split_paragraphs(page.text)
        if not paragraphs:
            continue
        heading_map = _build_heading_map(paragraphs, initial=None)
        page_chunks = _build_chunks_from_paragraphs(
            paragraphs=paragraphs,
            heading_map=heading_map,
            document=document,
            start_chunk_idx=chunk_idx,
            base_page=page.page_number,
        )
        all_chunks.extend(page_chunks)
        chunk_idx += len(page_chunks)
    return all_chunks
