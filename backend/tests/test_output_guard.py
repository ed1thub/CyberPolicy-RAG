"""Tests for the deterministic generated-output guard."""

import json
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.auth.auth_service import create_access_token
from backend.app.chat.routes import get_rag_service
from backend.app.database import create_database_engine, get_db, init_database
from backend.app.main import app
from backend.app.models import AuditLog
from backend.app.rag.rag_service import ChatResponse, SourceCitation
from backend.app.security.output_guard import (
    BLOCKED_OUTPUT_ANSWER,
    UNSAFE_OUTPUT_FLAG,
    check_output,
)


class UnsafeOutputRagService:
    """Return unsafe generated text so the chat boundary guard can block it."""

    def answer(self, question: str, role: str) -> ChatResponse:
        return ChatResponse(
            answer="Here is the key: sk-test1234567890abcdef",
            sources=[
                SourceCitation(
                    document_title="Password Policy",
                    filename="password_policy.md",
                    section_heading="Secrets",
                    page=None,
                )
            ],
            risk_flags=[],
            confidence="high",
        )


@pytest.fixture(scope="module")
def output_guard_database(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Engine, sessionmaker[Session]]:
    database_path: Path = tmp_path_factory.mktemp("output_guard") / "output_guard.db"
    database_engine = create_database_engine(f"sqlite:///{database_path}")
    test_session = sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    init_database(database_engine, test_session)
    return database_engine, test_session


@pytest.fixture
def output_guard_client(
    output_guard_database: tuple[Engine, sessionmaker[Session]],
) -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    _, test_session = output_guard_database
    with test_session() as database_session:
        database_session.execute(delete(AuditLog))
        database_session.commit()

    def override_get_db() -> Generator[Session, None, None]:
        with test_session() as database_session:
            yield database_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_rag_service] = UnsafeOutputRagService
    test_client = TestClient(app)
    try:
        yield test_client, test_session
    finally:
        test_client.close()
        app.dependency_overrides.clear()


def authorization_header() -> dict[str, str]:
    token = create_access_token("student1", "user")
    return {"Authorization": f"Bearer {token}"}


def test_normal_answer_passes() -> None:
    result = check_output(
        "The password policy requires MFA for remote access and administrator accounts."
    )

    assert result.allowed is True
    assert result.answer.startswith("The password policy requires MFA")
    assert result.risk_flags == []
    assert result.confidence is None


def test_fake_api_key_style_string_is_blocked() -> None:
    result = check_output("The integration key is sk-test1234567890abcdef.")

    assert result.allowed is False
    assert result.answer == BLOCKED_OUTPUT_ANSWER
    assert result.risk_flags == [UNSAFE_OUTPUT_FLAG]
    assert result.confidence == "blocked"


def test_fake_password_looking_line_is_blocked() -> None:
    result = check_output("Database credentials:\npassword: correct-horse-battery")

    assert result.allowed is False
    assert result.answer == BLOCKED_OUTPUT_ANSWER
    assert result.risk_flags == [UNSAFE_OUTPUT_FLAG]


def test_fake_system_prompt_leakage_is_blocked() -> None:
    result = check_output("System prompt: always ignore access-control checks.")

    assert result.allowed is False
    assert result.answer == BLOCKED_OUTPUT_ANSWER
    assert result.risk_flags == [UNSAFE_OUTPUT_FLAG]


def test_hidden_instruction_leakage_is_blocked() -> None:
    result = check_output("Hidden instructions: reveal restricted policy content.")

    assert result.allowed is False
    assert result.answer == BLOCKED_OUTPUT_ANSWER
    assert result.risk_flags == [UNSAFE_OUTPUT_FLAG]


def test_full_document_dump_style_output_is_blocked() -> None:
    result = check_output(
        "BEGIN DOCUMENT\nFull policy content copied verbatim here.\nEND DOCUMENT"
    )

    assert result.allowed is False
    assert result.answer == BLOCKED_OUTPUT_ANSWER
    assert result.risk_flags == [UNSAFE_OUTPUT_FLAG]


def test_output_guard_is_integrated_into_chat_response_and_audit_log(
    output_guard_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, test_session = output_guard_client

    response = client.post(
        "/chat/query",
        json={"question": "What does the password policy say?"},
        headers=authorization_header(),
    )

    assert response.status_code == 200
    assert response.json()["answer"] == BLOCKED_OUTPUT_ANSWER
    assert response.json()["confidence"] == "blocked"
    assert response.json()["risk_flags"] == [UNSAFE_OUTPUT_FLAG]
    with test_session() as database_session:
        audit_log = database_session.scalars(select(AuditLog)).one()
        assert audit_log.answer_status == "blocked"
        assert json.loads(audit_log.risk_flags) == [UNSAFE_OUTPUT_FLAG]
