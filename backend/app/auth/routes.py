"""Authentication API routes."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.auth.auth_service import authenticate_user, create_access_token
from backend.app.auth.dependencies import get_current_user
from backend.app.database import get_db
from backend.app.models import User

router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    """Credentials accepted by the login endpoint."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """Bearer token returned after successful authentication."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"


class CurrentUserResponse(BaseModel):
    """Safe public fields for the authenticated user."""

    username: str
    role: str


@router.post("/login", response_model=TokenResponse)
def login(
    credentials: LoginRequest,
    database_session: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    """Authenticate a username and password and return a bearer token."""
    user = authenticate_user(database_session, credentials.username, credentials.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(access_token=create_access_token(user.username, user.role))


@router.get("/me", response_model=CurrentUserResponse)
def get_authenticated_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> CurrentUserResponse:
    """Return the authenticated user's non-sensitive identity fields."""
    return CurrentUserResponse(username=current_user.username, role=current_user.role)
