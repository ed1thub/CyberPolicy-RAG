"""Split loaded documents into overlapping chunks with preserved metadata."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.documents.loader import LoadedDocument

# Word-count constants used only for PDF chunking
TARGET_WORDS = 300
MAX_WORDS = 400
OVERLAP_WORDS = 50

# Maximum words before a heading-based section is sub-split
MAX_SECTION_WORDS = 500


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
    section_number: str | None = field(default=None)

    def to_metadata(self) -> dict:
        """Return a flat scalar-only dict for ChromaDB metadata storage."""
        return {
            "document_title": self.document_title,
            "filename": self.filename,
            "sensitivity_level": self.sensitivity_level,
            "allowed_roles": self.allowed_roles,
            "section_heading": self.section_heading or "Unknown",
            "section_number": self.section_number or "",
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
    result: list[str | None] = []
    current = initial
    for para in paragraphs:
        first_line = para.split("\n")[0]
        heading = _extract_heading(first_line)
        if heading:
            current = heading
        result.append(current)
    return result


def _strip_heading_markers(text: str) -> str:
    """Convert '## Section Title' lines to plain 'Section Title' in chunk text."""
    lines = []
    for line in text.split("\n"):
        m = re.match(r"^#{1,6}\s+(.+)$", line.rstrip())
        lines.append(m.group(1) if m else line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Heading-based chunking (Markdown / TXT documents)
# ---------------------------------------------------------------------------

def _parse_sections(text: str) -> list[tuple[str, str | None, str]]:
    """
    Split document body by ## headings.

    Returns list of (heading_text, section_number_or_None, body_text).
    Content before the first ## heading (document preamble / metadata block)
    is intentionally skipped — it would otherwise inject Classification:
    header patterns into every chunk.
    """
    lines = text.split("\n")
    sections: list[tuple[str, str | None, str]] = []

    current_heading: str | None = None
    current_num: str | None = None
    current_lines: list[str] = []
    found_first = False

    for line in lines:
        m = re.match(r"^#{2}\s+(.+)$", line.rstrip())
        if m:
            if found_first and current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    sections.append((current_heading, current_num, body))  # type: ignore[arg-type]
            current_heading = m.group(1).strip()
            num_m = re.match(r"^(\d+)[\.\s]+", current_heading)
            current_num = num_m.group(1) if num_m else None
            current_lines = []
            found_first = True
        elif found_first:
            current_lines.append(line)

    if found_first and current_heading and current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append((current_heading, current_num, body))

    return sections


def _chunk_by_headings(document: LoadedDocument) -> list[DocumentChunk]:
    """
    Produce one DocumentChunk per ## section.

    Each chunk text starts with the plain-text heading followed by the raw
    section body so the heading is searchable but no ## markers appear in
    stored text.  Very large sections (>MAX_SECTION_WORDS) are sub-split
    on paragraph boundaries while keeping the heading as the first line of
    every sub-chunk.
    """
    sections = _parse_sections(document.body)
    chunks: list[DocumentChunk] = []

    for idx, (heading, section_num, body) in enumerate(sections, start=1):
        if not body.strip():
            continue

        words = body.split()
        if len(words) <= MAX_SECTION_WORDS:
            chunks.append(
                DocumentChunk(
                    chunk_id=_make_chunk_id(document.filename, idx),
                    text=f"{heading}\n\n{body}",
                    document_title=document.title,
                    filename=document.filename,
                    sensitivity_level=document.sensitivity_level,
                    allowed_roles=document.allowed_roles,
                    section_heading=heading,
                    section_number=section_num,
                    page=None,
                )
            )
        else:
            # Sub-split large sections on paragraph boundaries
            paragraphs = _split_paragraphs(body)
            sub_idx = 0
            para_pos = 0
            while para_pos < len(paragraphs):
                batch: list[str] = []
                wc = 0
                while para_pos < len(paragraphs):
                    para = paragraphs[para_pos]
                    pwc = _word_count(para)
                    if wc + pwc > MAX_SECTION_WORDS and wc > 0:
                        break
                    batch.append(para)
                    wc += pwc
                    para_pos += 1
                    if wc >= TARGET_WORDS:
                        break
                if not batch:
                    batch = [paragraphs[para_pos]]
                    para_pos += 1

                label = heading if sub_idx == 0 else f"{heading} (continued)"
                chunk_text = f"{label}\n\n" + "\n\n".join(batch)
                chunks.append(
                    DocumentChunk(
                        chunk_id=_make_chunk_id(document.filename, idx * 100 + sub_idx),
                        text=chunk_text,
                        document_title=document.title,
                        filename=document.filename,
                        sensitivity_level=document.sensitivity_level,
                        allowed_roles=document.allowed_roles,
                        section_heading=heading,
                        section_number=section_num,
                        page=None,
                    )
                )
                sub_idx += 1

    return chunks


def chunk_document(document: LoadedDocument) -> list[DocumentChunk]:
    """
    Split a loaded document into chunks with full metadata.

    Markdown and TXT documents are chunked by ## heading boundaries so each
    section (Definition, Examples, Storage Requirements, …) becomes its own
    chunk with the correct section_heading in metadata.  If no ## headings are
    found (e.g. plain TXT files), falls back to paragraph word-count chunking.

    PDF documents are chunked per page using word-count splitting because
    PDFs rarely carry Markdown heading syntax.
    """
    if document.pages:
        return _chunk_pdf(document)
    chunks = _chunk_by_headings(document)
    if not chunks:
        # No ## headings — fall back to paragraph-based word-count chunking
        return _chunk_text_body(document)
    return chunks


def _chunk_text_body(document: LoadedDocument) -> list[DocumentChunk]:
    """Word-count fallback for documents without ## section headings."""
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


# ---------------------------------------------------------------------------
# PDF word-count chunking (unchanged from original)
# ---------------------------------------------------------------------------

def _build_chunks_from_paragraphs(
    paragraphs: list[str],
    heading_map: list[str | None],
    document: LoadedDocument,
    start_chunk_idx: int,
    base_page: int | None,
) -> list[DocumentChunk]:
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

        while para_idx < n:
            para = paragraphs[para_idx]
            para_wc = _word_count(para)
            if word_count + para_wc > MAX_WORDS and word_count > 0:
                break
            word_count += para_wc
            current_heading = heading_map[para_idx]
            para_idx += 1
            if word_count >= TARGET_WORDS:
                break

        if para_idx == chunk_start:
            current_heading = heading_map[para_idx]
            para_idx += 1

        chunk_text = _strip_heading_markers(
            "\n\n".join(paragraphs[chunk_start:para_idx]).strip()
        )

        if para_idx < n:
            overlap_accumulated = 0
            overlap_start = para_idx
            while overlap_start > chunk_start and overlap_accumulated < OVERLAP_WORDS:
                overlap_start -= 1
                overlap_accumulated += _word_count(paragraphs[overlap_start])
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
