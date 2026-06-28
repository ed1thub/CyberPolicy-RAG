"""
Tests for user-specific chat isolation.

Covers:
- Chat list never leaks across users
- Accessing another user's chat returns 404
- Deleting another user's chat returns 404
- Sending to another user's chat_id returns 403
- Logout equivalent (new token, no shared state)
"""

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


class StubRagService:
    def answer(self, question: str, role: str) -> ChatResponse:
        return ChatResponse(
            answer="Policy answer.",
            sources=[
                SourceCitation(
                    document_title="Policy Doc",
                    filename="policy.md",
                    section_heading=None,
                    page=None,
                )
            ],
            risk_flags=[],
            confidence="high",
        )


@pytest.fixture(scope="module")
def isolation_db(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Engine, sessionmaker[Session]]:
    db_path: Path = tmp_path_factory.mktemp("isolation") / "isolation.db"
    engine = create_database_engine(f"sqlite:///{db_path}")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    init_database(engine, factory)
    return engine, factory


@pytest.fixture
def iso_client(
    isolation_db: tuple[Engine, sessionmaker[Session]],
) -> Generator[TestClient, None, None]:
    _, factory = isolation_db
    stub = StubRagService()

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_rag_service] = lambda: stub
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.clear()


def _auth(username: str, role: str = "user") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(username, role)}"}


# ── Chat list isolation ────────────────────────────────────────────────────────

def test_user_sees_only_own_chats(iso_client: TestClient) -> None:
    client = iso_client

    # student1 creates a chat by sending a message (no prior chat_id)
    r = client.post(
        "/chat/query",
        json={"question": "What is the password policy?"},
        headers=_auth("student1"),
    )
    assert r.status_code == 200
    student_chat_id = r.json()["chat_id"]

    # student1's chat list contains that chat
    r = client.get("/chats/", headers=_auth("student1"))
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert student_chat_id in ids

    # analyst1's chat list does NOT contain student1's chat
    r = client.get("/chats/", headers=_auth("analyst1", "security_analyst"))
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert student_chat_id not in ids


def test_admin_does_not_see_student_chats(iso_client: TestClient) -> None:
    client = iso_client

    r = client.post(
        "/chat/query",
        json={"question": "Any question?"},
        headers=_auth("student1"),
    )
    assert r.status_code == 200
    student_chat_id = r.json()["chat_id"]

    r = client.get("/chats/", headers=_auth("admin1", "admin"))
    assert r.status_code == 200
    admin_ids = [c["id"] for c in r.json()]
    assert student_chat_id not in admin_ids


# ── Direct chat ID access ──────────────────────────────────────────────────────

def test_get_another_users_chat_returns_404(iso_client: TestClient) -> None:
    client = iso_client

    r = client.post(
        "/chat/query",
        json={"question": "Secret policy?"},
        headers=_auth("student1"),
    )
    student_chat_id = r.json()["chat_id"]

    # analyst1 tries to fetch student1's chat by ID
    r = client.get(f"/chats/{student_chat_id}", headers=_auth("analyst1", "security_analyst"))
    assert r.status_code == 404


def test_delete_another_users_chat_returns_404(iso_client: TestClient) -> None:
    client = iso_client

    r = client.post(
        "/chat/query",
        json={"question": "Another question?"},
        headers=_auth("student1"),
    )
    student_chat_id = r.json()["chat_id"]

    r = client.delete(f"/chats/{student_chat_id}", headers=_auth("admin1", "admin"))
    assert r.status_code == 404


def test_send_to_another_users_chat_id_returns_403(iso_client: TestClient) -> None:
    client = iso_client

    r = client.post(
        "/chat/query",
        json={"question": "Student question"},
        headers=_auth("student1"),
    )
    student_chat_id = r.json()["chat_id"]

    # admin1 tries to send a message into student1's chat
    r = client.post(
        "/chat/query",
        json={"question": "Can I inject into your chat?", "chat_id": student_chat_id},
        headers=_auth("admin1", "admin"),
    )
    assert r.status_code == 403


# ── Unauthenticated access ─────────────────────────────────────────────────────

def test_list_chats_requires_auth(iso_client: TestClient) -> None:
    r = iso_client.get("/chats/")
    assert r.status_code == 401


def test_get_chat_requires_auth(iso_client: TestClient) -> None:
    r = iso_client.get("/chats/1")
    assert r.status_code == 401


def test_delete_chat_requires_auth(iso_client: TestClient) -> None:
    r = iso_client.delete("/chats/1")
    assert r.status_code == 401


# ── Logout / re-login isolation (simulated via token refresh) ──────────────────

def test_new_session_sees_only_own_chats(iso_client: TestClient) -> None:
    """Simulates: student1 logs out, admin1 logs in — admin1 must not see student1 chats."""
    client = iso_client

    # student1 session
    r = client.post(
        "/chat/query",
        json={"question": "My private question"},
        headers=_auth("student1"),
    )
    student_chat_id = r.json()["chat_id"]

    # "logout" → discard token → "login" as admin1 (new token)
    r = client.get("/chats/", headers=_auth("admin1", "admin"))
    assert r.status_code == 200
    admin_chat_ids = [c["id"] for c in r.json()]
    assert student_chat_id not in admin_chat_ids


def test_user_can_access_own_previous_chats_after_relogin(iso_client: TestClient) -> None:
    """Simulates: student1 logs out and back in — still sees their own chats."""
    client = iso_client

    # First "session"
    r = client.post(
        "/chat/query",
        json={"question": "My persistent question"},
        headers=_auth("student1"),
    )
    my_chat_id = r.json()["chat_id"]

    # "Re-login" = new JWT (token expiry simulated by issuing a fresh one)
    r = client.get("/chats/", headers=_auth("student1"))
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert my_chat_id in ids


# ── Chat deletion removes content ──────────────────────────────────────────────

def test_owner_can_delete_own_chat(iso_client: TestClient) -> None:
    client = iso_client

    r = client.post(
        "/chat/query",
        json={"question": "Temporary question"},
        headers=_auth("student1"),
    )
    chat_id = r.json()["chat_id"]

    r = client.delete(f"/chats/{chat_id}", headers=_auth("student1"))
    assert r.status_code == 204

    r = client.get(f"/chats/{chat_id}", headers=_auth("student1"))
    assert r.status_code == 404
