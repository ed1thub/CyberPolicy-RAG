"""Admin document upload route."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.auth.dependencies import get_current_user
from backend.app.database import get_db
from backend.app.documents.service import process_upload, validate_upload
from backend.app.models import Document, User
from backend.app.rag.vector_store import VectorStore

router = APIRouter(prefix="/documents", tags=["documents"])

_ADMIN_ROLE = "admin"


class UploadResponse(BaseModel):
    """Response returned after a successful document upload."""

    id: int
    filename: str
    title: str
    sensitivity_level: str
    chunk_count: int
    message: str


class DocumentInfo(BaseModel):
    """Summary of an indexed policy document."""

    id: int
    filename: str
    title: str
    sensitivity_level: str
    uploaded_at: str


class DeleteResponse(BaseModel):
    """Confirmation of a document deletion."""

    id: int
    chunks_removed: int
    message: str


@lru_cache
def get_upload_vector_store() -> VectorStore:
    """Singleton VectorStore used by the upload endpoint."""
    return VectorStore()


def get_upload_dir() -> Path:
    """Directory where uploaded files are persisted."""
    return Path("data/uploaded_policies")


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: Annotated[UploadFile, File(description="Policy document (.md / .txt / .pdf)")],
    title: Annotated[str, Form(description="Human-readable document title")],
    sensitivity_level: Annotated[
        str,
        Form(description="Sensitivity level: public / internal / confidential / restricted"),
    ],
    allowed_roles: Annotated[
        str,
        Form(description="Comma-separated roles that may access this document"),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db)],
    vector_store: Annotated[VectorStore, Depends(get_upload_vector_store)],
    upload_dir: Annotated[Path, Depends(get_upload_dir)],
) -> UploadResponse:
    """Upload a policy document and index it into ChromaDB.  Admin role required."""
    if current_user.role != _ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Document upload requires admin role.",
        )

    file_bytes = await file.read()
    filename = (file.filename or "uploaded_file").strip()

    try:
        validate_upload(filename, file_bytes, sensitivity_level)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    effective_title = title.strip() or Path(filename).stem.replace("_", " ").title()

    result = process_upload(
        file_bytes=file_bytes,
        original_filename=filename,
        title=effective_title,
        sensitivity_level=sensitivity_level,
        allowed_roles=allowed_roles,
        uploader_id=current_user.id,
        db_session=db_session,
        vector_store=vector_store,
        upload_dir=upload_dir,
    )

    return UploadResponse(
        id=result.document_id,
        filename=result.filename,
        title=result.title,
        sensitivity_level=result.sensitivity_level,
        chunk_count=result.chunk_count,
        message=(
            f"Document '{result.title}' uploaded and indexed successfully "
            f"({result.chunk_count} chunk{'s' if result.chunk_count != 1 else ''})."
        ),
    )


@router.get("/", response_model=list[DocumentInfo])
def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db)],
) -> list[DocumentInfo]:
    """List all indexed policy documents. Admin role required."""
    if current_user.role != _ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Listing documents requires admin role.",
        )
    docs = db_session.query(Document).order_by(Document.uploaded_at.desc()).all()
    return [
        DocumentInfo(
            id=doc.id,
            filename=doc.filename,
            title=doc.title,
            sensitivity_level=doc.sensitivity_level,
            uploaded_at=doc.uploaded_at.isoformat(),
        )
        for doc in docs
    ]


@router.delete("/{doc_id}", response_model=DeleteResponse)
def delete_document(
    doc_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db)],
    vector_store: Annotated[VectorStore, Depends(get_upload_vector_store)],
    upload_dir: Annotated[Path, Depends(get_upload_dir)],
) -> DeleteResponse:
    """Delete a document from SQLite, ChromaDB, and disk. Admin role required."""
    if current_user.role != _ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Deleting documents requires admin role.",
        )

    doc = db_session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {doc_id} not found.",
        )

    chunks_removed = vector_store.delete_by_filename(doc.filename)

    file_path = upload_dir / doc.filename
    if file_path.exists():
        file_path.unlink()

    db_session.delete(doc)
    db_session.commit()

    return DeleteResponse(
        id=doc_id,
        chunks_removed=chunks_removed,
        message=f"Document '{doc.title}' deleted ({chunks_removed} chunk{'s' if chunks_removed != 1 else ''} removed from index).",
    )
