"""SQLAlchemy models for application data stored in SQLite."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


def utc_now() -> datetime:
    """Return the current UTC time for model defaults."""
    return datetime.now(timezone.utc)


class User(Base):
    """Application user with a hashed password and assigned role."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Document(Base):
    """Metadata for an uploaded or sample policy document."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
    sensitivity_level: Mapped[str] = mapped_column(String(50))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditLog(Base):
    """Audit trail entry for a chatbot request."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    username: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(50))
    question: Mapped[str] = mapped_column(Text)
    answer_status: Mapped[str] = mapped_column(String(50))
    documents_used: Mapped[str] = mapped_column(Text, default="[]")
    risk_flags: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
