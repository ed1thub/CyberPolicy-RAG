"""Tests for the authenticated chat endpoint."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.auth.auth_service import create_access_token
from backend.app.chat.routes import get_rag_service
from backend.app.database import create_database_engine, get_db, init_database
from backend.app.main import app
from backend.app.rag.rag_service import ChatResponse, SourceCitation


class SpyRagService:
    """Record chat calls and return a stable structured response."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def answer(self, question: str, role: str) -> ChatResponse:
        self.calls.append((question, role))
        return ChatResponse(
            answer="MFA is required by the password policy.",
            sources=[
                SourceCitation(
                    document_title="Password Policy",
                    filename="password_policy.md",
                    section_heading="Multi-Factor Authentication",
                    page=None,
                )
            ],
            risk_flags=[],
            confidence="high",
        )


@pytest.fixture(scope="module")
def chat_database(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Engine, sessionmaker[Session]]:
    database_path: Path = tmp_path_factory.mktemp("chat") / "chat.db"
    database_engine = create_database_engine(f"sqlite:///{database_path}")
    test_session = sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    init_database(database_engine, test_session)
    return database_engine, test_session


@pytest.fixture
def chat_client(
    chat_database: tuple[Engine, sessionmaker[Session]],
) -> Generator[tuple[TestClient, SpyRagService], None, None]:
    _, test_session = chat_database
    spy_rag_service = SpyRagService()

    def override_get_db() -> Generator[Session, None, None]:
        with test_session() as database_session:
            yield database_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_rag_service] = lambda: spy_rag_service
    test_client = TestClient(app)
    try:
        yield test_client, spy_rag_service
    finally:
        test_client.close()
        app.dependency_overrides.clear()


def student_authorization_header() -> dict[str, str]:
    token = create_access_token("student1", "user")
    return {"Authorization": f"Bearer {token}"}


def test_unauthenticated_request_is_rejected(
    chat_client: tuple[TestClient, SpyRagService],
) -> None:
    client, rag_service = chat_client

    response = client.post("/chat/query", json={"question": "What is the policy?"})

    assert response.status_code == 401
    assert rag_service.calls == []


def test_authenticated_request_passes_question_and_role_to_rag_service(
    chat_client: tuple[TestClient, SpyRagService],
) -> None:
    client, rag_service = chat_client

    response = client.post(
        "/chat/query",
        json={"question": "What does the password policy say about MFA?"},
        headers=student_authorization_header(),
    )

    assert response.status_code == 200
    assert rag_service.calls == [
        ("What does the password policy say about MFA?", "user")
    ]


@pytest.mark.parametrize("question", ["", "   \t\n"])
def test_empty_or_whitespace_only_question_is_rejected(
    chat_client: tuple[TestClient, SpyRagService],
    question: str,
) -> None:
    client, rag_service = chat_client

    response = client.post(
        "/chat/query",
        json={"question": question},
        headers=student_authorization_header(),
    )

    assert response.status_code == 422
    assert rag_service.calls == []


def test_too_long_question_is_rejected(
    chat_client: tuple[TestClient, SpyRagService],
) -> None:
    client, rag_service = chat_client

    response = client.post(
        "/chat/query",
        json={"question": "a" * 1001},
        headers=student_authorization_header(),
    )

    assert response.status_code == 422
    assert rag_service.calls == []


def test_response_contains_required_fields(
    chat_client: tuple[TestClient, SpyRagService],
) -> None:
    client, _ = chat_client

    response = client.post(
        "/chat/query",
        json={"question": "What does the password policy say about MFA?"},
        headers=student_authorization_header(),
    )

    assert response.status_code == 200
    body = response.json()
    assert {"answer", "sources", "risk_flags", "confidence", "chat_id", "chat_title"}.issubset(body)
    assert body["sources"] == [
        {
            "document_title": "Password Policy",
            "filename": "password_policy.md",
            "section_heading": "Multi-Factor Authentication",
            "page": None,
            "sensitivity_level": None,
        }
    ]
