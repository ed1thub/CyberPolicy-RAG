"""FastAPI dependencies for authenticating bearer tokens."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def authentication_error() -> HTTPException:
    """Build the standard response used for all invalid credentials."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    database_session: Annotated[Session, Depends(get_db)],
) -> User:
    """Validate a JWT and load its current user from the database."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        username = payload.get("sub")
        token_username = payload.get("username")
        role = payload.get("role")
        if not isinstance(username, str) or username != token_username or not isinstance(role, str):
            raise authentication_error()
    except JWTError as error:
        raise authentication_error() from error

    user = database_session.scalar(select(User).where(User.username == username))
    if user is None or user.role != role:
        raise authentication_error()
    return user
