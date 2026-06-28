"""Tests for database models, initialisation, and demo user seeding."""

from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database import (
    DEMO_USERS,
    create_database_engine,
    init_database,
    password_context,
)
from backend.app.models import User


@pytest.fixture
def test_database(tmp_path: Path) -> tuple[Path, Engine, sessionmaker[Session]]:
    database_path = tmp_path / "test.db"
    database_engine = create_database_engine(f"sqlite:///{database_path}")
    test_session = sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    init_database(database_engine, test_session)
    return database_path, database_engine, test_session


def test_database_initialises_all_tables(
    test_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _, database_engine, _ = test_database
    table_names = set(inspect(database_engine).get_table_names())

    assert table_names == {"users", "documents", "audit_logs", "chats", "chat_messages"}


def test_demo_users_exist(
    test_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _, _, test_session = test_database
    with test_session() as database_session:
        users = database_session.scalars(select(User).order_by(User.username)).all()

    expected_users = sorted((username, role) for username, _, role in DEMO_USERS)
    assert [(user.username, user.role) for user in users] == expected_users


def test_demo_user_passwords_are_hashed(
    test_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _, _, test_session = test_database
    with test_session() as database_session:
        users = database_session.scalars(select(User)).all()

    assert all(user.password_hash != "password123" for user in users)
    assert all(password_context.verify("password123", user.password_hash) for user in users)


def test_plain_text_password_is_not_stored(
    test_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    database_path, _, _ = test_database

    assert b"password123" not in database_path.read_bytes()


def test_initialisation_is_idempotent(
    test_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _, database_engine, test_session = test_database

    init_database(database_engine, test_session)

    with test_session() as database_session:
        assert len(database_session.scalars(select(User)).all()) == len(DEMO_USERS)
