"""Password verification, user authentication, and JWT creation."""

from datetime import datetime, timedelta, timezone

from jose import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import password_context
from backend.app.models import User


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plain-text password against a stored bcrypt hash."""
    return password_context.verify(plain_password, password_hash)


def authenticate_user(database_session: Session, username: str, password: str) -> User | None:
    """Return the matching user when the supplied credentials are valid."""
    user = database_session.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(
    username: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT containing the authenticated user's identity."""
    token_lifetime = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    expires_at = datetime.now(timezone.utc) + token_lifetime
    payload = {
        "sub": username,
        "username": username,
        "role": role,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
