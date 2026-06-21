"""Tests for JWT login and authenticated user endpoints."""

from collections.abc import Generator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.auth.auth_service import create_access_token
from backend.app.config import settings
from backend.app.database import create_database_engine, get_db, init_database
from backend.app.main import app


@pytest.fixture(scope="module")
def auth_database(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Engine, sessionmaker[Session]]:
    database_path: Path = tmp_path_factory.mktemp("auth") / "auth.db"
    database_engine = create_database_engine(f"sqlite:///{database_path}")
    test_session = sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    init_database(database_engine, test_session)
    return database_engine, test_session


@pytest.fixture
def client(
    auth_database: tuple[Engine, sessionmaker[Session]],
) -> Generator[TestClient, None, None]:
    _, test_session = auth_database

    def override_get_db() -> Generator[Session, None, None]:
        with test_session() as database_session:
            yield database_session

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.clear()


def login_as_student(client: TestClient) -> str:
    response = client.post(
        "/auth/login",
        json={"username": "student1", "password": "password123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_successful_login_returns_bearer_token(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"username": "student1", "password": "password123"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    payload = jwt.decode(
        response.json()["access_token"],
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    assert payload["username"] == "student1"
    assert payload["role"] == "user"


def test_failed_login_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"username": "student1", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_me_returns_current_user_for_valid_token(client: TestClient) -> None:
    token = login_as_student(client)

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"username": "student1", "role": "user"}


def test_me_without_token_is_rejected(client: TestClient) -> None:
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_invalid_token_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert response.status_code == 401


def test_expired_token_is_rejected(client: TestClient) -> None:
    token = create_access_token("student1", "user", expires_delta=timedelta(seconds=-1))

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_auth_responses_do_not_expose_password_hash(client: TestClient) -> None:
    login_response = client.post(
        "/auth/login",
        json={"username": "student1", "password": "password123"},
    )
    token = login_response.json()["access_token"]
    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert "password_hash" not in login_response.json()
    assert "password_hash" not in me_response.json()
