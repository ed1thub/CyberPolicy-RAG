"""Load Markdown, TXT, and PDF policy documents into a common structure."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

VALID_SENSITIVITY_LEVELS = {"public", "internal", "confidential", "restricted"}
SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}


@dataclass
class PageContent:
    """Text extracted from a single PDF page."""

    text: str
    page_number: int  # 1-indexed


@dataclass
class LoadedDocument:
    """Normalised document with content and metadata ready for chunking."""

    title: str
    filename: str
    sensitivity_level: str
    allowed_roles: str  # comma-separated string for ChromaDB compatibility
    body: str           # full text for Markdown / TXT
    pages: list[PageContent] = field(default_factory=list)  # populated for PDF only


def _parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML front matter block and return (metadata dict, body text)."""
    if not text.startswith("---"):
        return {}, text

    end = text.find("\n---", 3)
    if end == -1:
        return {}, text

    front_matter_raw = text[3:end].strip()
    body = text[end + 4:].strip()

    try:
        metadata: dict[str, Any] = yaml.safe_load(front_matter_raw) or {}
    except yaml.YAMLError:
        metadata = {}

    return metadata, body


def _validate_metadata(metadata: dict[str, Any], filename: str) -> dict[str, str]:
    """Validate required fields and return normalised values."""
    stem = Path(filename).stem.replace("_", " ").title()
    title = str(metadata.get("title", stem))
    sensitivity_level = str(metadata.get("sensitivity_level", "internal"))
    allowed_roles = str(metadata.get("allowed_roles", ""))

    if sensitivity_level not in VALID_SENSITIVITY_LEVELS:
        raise ValueError(
            f"{filename}: unknown sensitivity_level '{sensitivity_level}'. "
            f"Must be one of: {sorted(VALID_SENSITIVITY_LEVELS)}"
        )

    return {
        "title": title,
        "sensitivity_level": sensitivity_level,
        "allowed_roles": allowed_roles,
    }


def load_markdown(file_path: Path) -> LoadedDocument:
    """Load a Markdown file and parse its YAML front matter."""
    text = file_path.read_text(encoding="utf-8")
    raw_meta, body = _parse_front_matter(text)
    validated = _validate_metadata(raw_meta, file_path.name)

    return LoadedDocument(
        title=validated["title"],
        filename=file_path.name,
        sensitivity_level=validated["sensitivity_level"],
        allowed_roles=validated["allowed_roles"],
        body=body,
    )


def load_txt(file_path: Path) -> LoadedDocument:
    """Load a plain text file. Sensitivity metadata defaults to internal."""
    text = file_path.read_text(encoding="utf-8")
    title = file_path.stem.replace("_", " ").title()

    return LoadedDocument(
        title=title,
        filename=file_path.name,
        sensitivity_level="internal",
        allowed_roles="user,security_analyst,admin",
        body=text,
    )


def load_pdf(file_path: Path) -> LoadedDocument:
    """Load a PDF file page by page using PyMuPDF (fitz)."""
    import fitz  # noqa: PLC0415  imported here so fitz is optional at module level

    title = file_path.stem.replace("_", " ").title()
    pages: list[PageContent] = []
    body_parts: list[str] = []

    with fitz.open(str(file_path)) as doc:
        for page_index, page in enumerate(doc, start=1):
            page_text = page.get_text().strip()
            if page_text:
                pages.append(PageContent(text=page_text, page_number=page_index))
                body_parts.append(page_text)

    return LoadedDocument(
        title=title,
        filename=file_path.name,
        sensitivity_level="internal",
        allowed_roles="user,security_analyst,admin",
        body="\n\n".join(body_parts),
        pages=pages,
    )


def load_document(file_path: Path) -> LoadedDocument:
    """Dispatch to the correct loader based on file extension."""
    suffix = file_path.suffix.lower()
    if suffix == ".md":
        return load_markdown(file_path)
    if suffix == ".txt":
        return load_txt(file_path)
    if suffix == ".pdf":
        return load_pdf(file_path)
    raise ValueError(
        f"Unsupported file type: '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
    )


def load_all_from_directory(directory: Path) -> list[LoadedDocument]:
    """Load all supported documents from a directory in sorted order."""
    documents: list[LoadedDocument] = []
    for file_path in sorted(directory.iterdir()):
        if file_path.suffix.lower() in SUPPORTED_EXTENSIONS and file_path.is_file():
            documents.append(load_document(file_path))
    return documents
