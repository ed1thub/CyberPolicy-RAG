"""Persistence helpers for chatbot audit logs."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import AuditLog, User


def create_audit_log(
    database_session: Session,
    *,
    user: User,
    question: str,
    answer_status: str,
    documents_used: list[str],
    risk_flags: list[str],
) -> AuditLog:
    """Persist one authenticated chat outcome and return the saved log."""
    audit_log = AuditLog(
        user_id=user.id,
        username=user.username,
        role=user.role,
        question=question,
        answer_status=answer_status,
        documents_used=json.dumps(documents_used),
        risk_flags=json.dumps(risk_flags),
    )
    database_session.add(audit_log)
    database_session.commit()
    database_session.refresh(audit_log)
    return audit_log


def get_audit_logs(database_session: Session) -> list[AuditLog]:
    """Return all audit logs with the newest entries first."""
    return list(
        database_session.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        ).all()
    )
