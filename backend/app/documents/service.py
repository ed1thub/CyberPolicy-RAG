"""Document upload service: validation, persistence, and vector indexing."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.documents.chunker import chunk_document
from backend.app.documents.loader import (
    LoadedDocument,
    _parse_front_matter,
    load_pdf,
)
from backend.app.models import Document
from backend.app.rag.vector_store import VectorStore

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = frozenset({".md", ".txt", ".pdf"})
VALID_SENSITIVITY_LEVELS = frozenset({"public", "internal", "confidential", "restricted"})


@dataclass
class UploadResult:
    """Summary of a successfully processed upload."""

    document_id: int
    filename: str
    title: str
    sensitivity_level: str
    chunk_count: int


def validate_upload(
    filename: str,
    file_bytes: bytes,
    sensitivity_level: str,
) -> None:
    """Raise ValueError with a clear message for any invalid upload input."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{suffix}'. "
            f"Allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )
    if not file_bytes:
        raise ValueError("Uploaded file is empty.")
    if len(file_bytes) > MAX_FILE_SIZE:
        mb = len(file_bytes) / (1024 * 1024)
        raise ValueError(f"File is {mb:.1f} MB. Maximum allowed size is 5 MB.")
    if sensitivity_level not in VALID_SENSITIVITY_LEVELS:
        raise ValueError(
            f"Unknown sensitivity level '{sensitivity_level}'. "
            f"Must be one of: {sorted(VALID_SENSITIVITY_LEVELS)}"
        )


def _load_body(file_path: Path) -> LoadedDocument:
    """
    Load document body without validating front-matter metadata.

    For uploaded documents the admin specifies metadata via the form, so
    front-matter sensitivity/roles are intentionally ignored here.
    """
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return load_pdf(file_path)

    text = file_path.read_text(encoding="utf-8")
    if suffix == ".md":
        _, body = _parse_front_matter(text)
    else:
        body = text

    return LoadedDocument(
        title="",
        filename=file_path.name,
        sensitivity_level="internal",
        allowed_roles="",
        body=body,
    )


def process_upload(
    file_bytes: bytes,
    original_filename: str,
    title: str,
    sensitivity_level: str,
    allowed_roles: str,
    uploader_id: int,
    db_session: Session,
    vector_store: VectorStore,
    upload_dir: Path,
) -> UploadResult:
    """
    Persist an uploaded document file and index it in ChromaDB.

    1. Save file bytes to upload_dir.
    2. Create a Document record in SQLite.
    3. Load document body (form metadata takes priority over any file metadata).
    4. Chunk the document.
    5. Assign unique chunk IDs prefixed with the DB record ID to prevent
       collisions if the same filename is uploaded more than once.
    6. Add chunks to the vector store.
    """
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest_path = upload_dir / original_filename
    dest_path.write_bytes(file_bytes)

    doc_record = Document(
        filename=original_filename,
        title=title,
        sensitivity_level=sensitivity_level,
        uploaded_by=uploader_id,
    )
    db_session.add(doc_record)
    db_session.commit()
    db_session.refresh(doc_record)

    loaded = _load_body(dest_path)
    loaded.title = title
    loaded.sensitivity_level = sensitivity_level
    loaded.allowed_roles = allowed_roles
    loaded.filename = original_filename

    chunks = chunk_document(loaded)

    # Prefix chunk IDs with record ID to guarantee global uniqueness
    for chunk in chunks:
        chunk.chunk_id = f"upload{doc_record.id}_{chunk.chunk_id}"

    if chunks:
        vector_store.add_chunks(chunks)

    return UploadResult(
        document_id=doc_record.id,
        filename=original_filename,
        title=title,
        sensitivity_level=sensitivity_level,
        chunk_count=len(chunks),
    )
