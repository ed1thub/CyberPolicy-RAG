"""Tests for T13: Admin document upload endpoint."""

from collections.abc import Generator, Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.auth.auth_service import create_access_token
from backend.app.database import create_database_engine, get_db, init_database
from backend.app.documents.routes import (
    get_upload_dir,
    get_upload_vector_store,
)
from backend.app.documents.service import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    validate_upload,
)
from backend.app.main import app
from backend.app.rag.vector_store import VectorStore

# ---------------------------------------------------------------------------
# Deterministic embeddings — no model download needed
# ---------------------------------------------------------------------------


class KeywordEmbeddings:
    _KEYWORDS = ("policy", "password", "incident", "restricted", "general")

    def _embed(self, text: str) -> list[float]:
        lower = text.lower()
        values = [float(lower.count(kw)) for kw in self._KEYWORDS]
        if not any(values):
            values[-1] = 1.0
        return values

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


# ---------------------------------------------------------------------------
# Sample document bytes
# ---------------------------------------------------------------------------

_MD_CONTENT = b"""\
---
title: Test Password Policy
sensitivity_level: internal
allowed_roles: user,security_analyst,admin
---

# Test Password Policy

## Password Requirements

Passwords must be at least 14 characters and include uppercase, lowercase,
numbers, and special characters. Users must not reuse any of their last
12 passwords. Policy compliance is mandatory for all staff.
"""

_TXT_CONTENT = b"This is a plain text policy document.\n\nIt covers acceptable use."

_OVER_5MB = b"x" * (MAX_FILE_SIZE + 1)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def upload_database(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Engine, sessionmaker[Session]]:
    db_path = tmp_path_factory.mktemp("upload_db") / "upload.db"
    engine = create_database_engine(f"sqlite:///{db_path}")
    session_factory = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    init_database(engine, session_factory)
    return engine, session_factory


@pytest.fixture
def upload_client(
    upload_database: tuple[Engine, sessionmaker[Session]],
    tmp_path: Path,
) -> Generator[tuple[TestClient, VectorStore, Path], None, None]:
    _, session_factory = upload_database
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    store = VectorStore(
        chroma_path=tmp_path / "chroma",
        embedding_provider=KeywordEmbeddings(),
    )

    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_upload_vector_store] = lambda: store
    app.dependency_overrides[get_upload_dir] = lambda: upload_dir

    client = TestClient(app)
    try:
        yield client, store, upload_dir
    finally:
        client.close()
        app.dependency_overrides.clear()


def _token(username: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(username, role)}"}


def _post_upload(
    client: TestClient,
    role_headers: dict[str, str],
    file_bytes: bytes = _MD_CONTENT,
    filename: str = "test_policy.md",
    title: str = "Test Policy",
    sensitivity_level: str = "internal",
    allowed_roles: str = "user,security_analyst,admin",
) -> object:
    return client.post(
        "/documents/upload",
        files={"file": (filename, file_bytes, "text/plain")},
        data={
            "title": title,
            "sensitivity_level": sensitivity_level,
            "allowed_roles": allowed_roles,
        },
        headers=role_headers,
    )


# ---------------------------------------------------------------------------
# RBAC: only admin may upload
# ---------------------------------------------------------------------------


def test_unauthenticated_upload_is_rejected(
    upload_client: tuple[TestClient, VectorStore, Path],
) -> None:
    client, _, _ = upload_client
    response = client.post(
        "/documents/upload",
        files={"file": ("doc.md", _MD_CONTENT, "text/plain")},
        data={"title": "X", "sensitivity_level": "internal", "allowed_roles": "user"},
    )
    assert response.status_code == 401


def test_user_role_cannot_upload(
    upload_client: tuple[TestClient, VectorStore, Path],
) -> None:
    client, _, _ = upload_client
    response = _post_upload(client, _token("student1", "user"))
    assert response.status_code == 403
    assert "admin" in response.json()["detail"].lower()


def test_security_analyst_cannot_upload(
    upload_client: tuple[TestClient, VectorStore, Path],
) -> None:
    client, _, _ = upload_client
    response = _post_upload(client, _token("analyst1", "security_analyst"))
    assert response.status_code == 403


def test_admin_can_upload_markdown(
    upload_client: tuple[TestClient, VectorStore, Path],
) -> None:
    client, _, _ = upload_client
    response = _post_upload(client, _token("admin1", "admin"))
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "test_policy.md"
    assert body["sensitivity_level"] == "internal"
    assert body["chunk_count"] >= 1


# ---------------------------------------------------------------------------
# Validation: file type, size, sensitivity, empty
# ---------------------------------------------------------------------------


def test_unsupported_file_type_rejected(
    upload_client: tuple[TestClient, VectorStore, Path],
) -> None:
    client, _, _ = upload_client
    response = _post_upload(
        client,
        _token("admin1", "admin"),
        file_bytes=b"content",
        filename="policy.docx",
    )
    assert response.status_code == 400
    assert "unsupported file type" in response.json()["detail"].lower()


def test_file_over_5mb_rejected(
    upload_client: tuple[TestClient, VectorStore, Path],
) -> None:
    client, _, _ = upload_client
    response = _post_upload(
        client,
        _token("admin1", "admin"),
        file_bytes=_OVER_5MB,
        filename="big_policy.md",
    )
    assert response.status_code == 400
    assert "5 mb" in response.json()["detail"].lower()


def test_unknown_sensitivity_level_rejected(
    upload_client: tuple[TestClient, VectorStore, Path],
) -> None:
    client, _, _ = upload_client
    response = _post_upload(
        client,
        _token("admin1", "admin"),
        sensitivity_level="top_secret",
    )
    assert response.status_code == 400
    assert "unknown sensitivity level" in response.json()["detail"].lower()


def test_empty_file_rejected(
    upload_client: tuple[TestClient, VectorStore, Path],
) -> None:
    client, _, _ = upload_client
    response = _post_upload(
        client,
        _token("admin1", "admin"),
        file_bytes=b"",
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# File system and database
# ---------------------------------------------------------------------------


def test_uploaded_file_is_saved_to_disk(
    upload_client: tuple[TestClient, VectorStore, Path],
) -> None:
    client, _, upload_dir = upload_client
    _post_upload(
        client,
        _token("admin1", "admin"),
        filename="saved_policy.md",
    )
    assert (upload_dir / "saved_policy.md").exists()


def test_upload_response_contains_required_fields(
    upload_client: tuple[TestClient, VectorStore, Path],
) -> None:
    client, _, _ = upload_client
    response = _post_upload(
        client, _token("admin1", "admin"), filename="fields_check.md"
    )
    body = response.json()
    required = {"id", "filename", "title", "sensitivity_level", "chunk_count", "message"}
    assert required.issubset(body.keys())


def test_txt_file_upload_succeeds(
    upload_client: tuple[TestClient, VectorStore, Path],
) -> None:
    client, _, _ = upload_client
    response = _post_upload(
        client,
        _token("admin1", "admin"),
        file_bytes=_TXT_CONTENT,
        filename="plain_policy.txt",
    )
    assert response.status_code == 201
    assert response.json()["chunk_count"] >= 1


# ---------------------------------------------------------------------------
# Searchability: uploaded document becomes findable via vector search
# ---------------------------------------------------------------------------


def test_uploaded_document_is_searchable(
    upload_client: tuple[TestClient, VectorStore, Path],
) -> None:
    client, store, _ = upload_client

    content = b"""\
# Network Security Policy

## Password Authentication

All staff passwords must comply with password policy requirements.
Minimum length is 14 characters with complexity requirements enforced.
Multi-factor authentication is mandatory for all privileged accounts.
"""

    response = _post_upload(
        client,
        _token("admin1", "admin"),
        file_bytes=content,
        filename="network_policy.md",
        title="Network Security Policy",
        sensitivity_level="internal",
        allowed_roles="user,security_analyst,admin",
    )
    assert response.status_code == 201

    results = store.search("password authentication", ["internal"], top_k=5)
    assert len(results) > 0
    filenames = [r.metadata.get("filename") for r in results]
    assert "network_policy.md" in filenames


# ---------------------------------------------------------------------------
# validate_upload unit tests (pure Python — no HTTP)
# ---------------------------------------------------------------------------


def test_validate_upload_passes_valid_md() -> None:
    validate_upload("policy.md", b"content", "internal")


def test_validate_upload_passes_valid_txt() -> None:
    validate_upload("policy.txt", b"content", "public")


def test_validate_upload_passes_valid_pdf() -> None:
    validate_upload("policy.pdf", b"content", "confidential")


def test_validate_upload_rejects_docx() -> None:
    with pytest.raises(ValueError, match="Unsupported file type"):
        validate_upload("policy.docx", b"content", "internal")


def test_validate_upload_rejects_empty_file() -> None:
    with pytest.raises(ValueError, match="empty"):
        validate_upload("policy.md", b"", "internal")


def test_validate_upload_rejects_oversized_file() -> None:
    with pytest.raises(ValueError, match="5 MB"):
        validate_upload("policy.md", _OVER_5MB, "internal")


def test_validate_upload_rejects_unknown_sensitivity() -> None:
    with pytest.raises(ValueError, match="Unknown sensitivity level"):
        validate_upload("policy.md", b"content", "ultra_secret")
