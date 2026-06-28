"""Database configuration, initialisation, and development seed data."""

from collections.abc import Generator

from passlib.context import CryptContext
from passlib.hash import bcrypt
from sqlalchemy import Engine, create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


def create_database_engine(database_url: str) -> Engine:
    """Create an engine with SQLite's required thread configuration."""
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


engine = create_database_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def configure_bcrypt_backend() -> None:
    """Select a working Passlib bcrypt backend.

    bcrypt 5 rejects Passlib's legacy backend self-test. Linux's crypt backend
    still produces standard bcrypt hashes and keeps local development working.
    """
    try:
        bcrypt.set_backend()
    except ValueError as error:
        if "72 bytes" not in str(error) or not bcrypt.has_backend("os_crypt"):
            raise
        bcrypt.set_backend("os_crypt")


configure_bcrypt_backend()
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEMO_USERS = (
    ("student1", "password123", "user"),
    ("analyst1", "password123", "security_analyst"),
    ("admin1", "password123", "admin"),
)


def get_db() -> Generator[Session, None, None]:
    """Provide a database session and always close it after use."""
    with SessionLocal() as database_session:
        yield database_session


def seed_demo_users(database_session: Session) -> None:
    """Create any missing demo users with bcrypt-hashed passwords."""
    from backend.app.models import User

    existing_usernames = set(database_session.scalars(select(User.username)).all())
    for username, password, role in DEMO_USERS:
        if username not in existing_usernames:
            database_session.add(
                User(
                    username=username,
                    password_hash=password_context.hash(password),
                    role=role,
                )
            )
    database_session.commit()


def _run_migrations(database_engine: Engine) -> None:
    """Apply additive schema changes that create_all() cannot handle."""
    inspector = inspect(database_engine)
    with database_engine.begin() as conn:
        existing_tables = inspector.get_table_names()
        if "chats" in existing_tables:
            existing_cols = {c["name"] for c in inspector.get_columns("chats")}
            if "pinned" not in existing_cols:
                conn.execute(text("ALTER TABLE chats ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT 0"))


def init_database(
    database_engine: Engine = engine,
    session_factory: sessionmaker[Session] = SessionLocal,
) -> None:
    """Create database tables and seed the development users."""
    # Importing registers the model tables on Base.metadata before creation.
    from backend.app import models  # noqa: F401

    Base.metadata.create_all(bind=database_engine)
    _run_migrations(database_engine)
    with session_factory() as database_session:
        seed_demo_users(database_session)
