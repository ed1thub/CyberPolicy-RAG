"""Role-protected audit log API routes."""

import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.audit.audit_service import get_audit_logs
from backend.app.auth.dependencies import get_current_user
from backend.app.database import get_db
from backend.app.models import AuditLog, User

router = APIRouter(prefix="/audit", tags=["audit"])

AUDIT_LOG_ROLES = frozenset({"admin", "security_analyst"})


class AuditLogResponse(BaseModel):
    """Safe audit fields exposed to authorised reviewers."""

    user_id: int
    username: str
    role: str
    question: str
    answer_status: str
    documents_used: list[str]
    risk_flags: list[str]
    created_at: datetime


def _to_response(audit_log: AuditLog) -> AuditLogResponse:
    """Convert JSON-backed list fields into the API response shape."""
    return AuditLogResponse(
        user_id=audit_log.user_id,
        username=audit_log.username,
        role=audit_log.role,
        question=audit_log.question,
        answer_status=audit_log.answer_status,
        documents_used=json.loads(audit_log.documents_used),
        risk_flags=json.loads(audit_log.risk_flags),
        created_at=audit_log.created_at,
    )


@router.get("/logs", response_model=list[AuditLogResponse])
def list_audit_logs(
    current_user: Annotated[User, Depends(get_current_user)],
    database_session: Annotated[Session, Depends(get_db)],
) -> list[AuditLogResponse]:
    """Return all audit logs to security analysts and administrators."""
    if current_user.role not in AUDIT_LOG_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view audit logs",
        )
    return [_to_response(log) for log in get_audit_logs(database_session)]
