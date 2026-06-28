"""Chat history CRUD — each chat is owned by exactly one user."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.auth.dependencies import get_current_user
from backend.app.database import get_db
from backend.app.models import Chat, ChatMessage, User
from backend.app.schemas import ChatDetail, ChatSummary, ChatUpdateRequest, MessageOut, SourceCitation

router = APIRouter(prefix="/chats", tags=["chats"])


def require_owned_chat(chat_id: int, user: User, db: Session) -> Chat:
    """Load a chat and enforce ownership — raises 404 for missing or foreign chats."""
    chat = db.get(Chat, chat_id)
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


def message_to_out(msg: ChatMessage) -> MessageOut:
    sources_raw: list[dict] = json.loads(msg.sources or "[]")
    return MessageOut(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        sources=[SourceCitation(**s) for s in sources_raw],
        risk_flags=json.loads(msg.risk_flags or "[]"),
        confidence=msg.confidence,
        created_at=msg.created_at.isoformat(),
    )


@router.get("/", response_model=list[ChatSummary])
def list_chats(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ChatSummary]:
    """Return all chats belonging to the authenticated user, newest first."""
    chats = list(
        db.scalars(
            select(Chat)
            .where(Chat.user_id == current_user.id)
            .order_by(Chat.pinned.desc(), Chat.created_at.desc())
        ).all()
    )
    return [
        ChatSummary(id=c.id, title=c.title, pinned=c.pinned, created_at=c.created_at.isoformat())
        for c in chats
    ]


@router.post("/", response_model=ChatSummary, status_code=status.HTTP_201_CREATED)
def create_chat(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ChatSummary:
    """Create an empty chat for the authenticated user."""
    chat = Chat(user_id=current_user.id, title="New chat")
    db.add(chat)
    db.commit()
    return ChatSummary(id=chat.id, title=chat.title, pinned=chat.pinned, created_at=chat.created_at.isoformat())


@router.get("/{chat_id}", response_model=ChatDetail)
def get_chat(
    chat_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ChatDetail:
    """Return a chat with all its messages. Only the owner can access it."""
    chat = require_owned_chat(chat_id, current_user, db)
    messages = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.chat_id == chat_id)
            .order_by(ChatMessage.id)
        ).all()
    )
    return ChatDetail(
        id=chat.id,
        title=chat.title,
        created_at=chat.created_at.isoformat(),
        messages=[message_to_out(m) for m in messages],
    )


@router.patch("/{chat_id}", response_model=ChatSummary)
def update_chat(
    chat_id: int,
    body: ChatUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ChatSummary:
    """Rename or pin/unpin a chat. Only the owner can update it."""
    chat = require_owned_chat(chat_id, current_user, db)
    if body.title is not None:
        chat.title = body.title.strip()
    if body.pinned is not None:
        chat.pinned = body.pinned
    db.commit()
    return ChatSummary(id=chat.id, title=chat.title, pinned=chat.pinned, created_at=chat.created_at.isoformat())


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    chat_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Delete a chat and all its messages. Only the owner can delete it."""
    chat = require_owned_chat(chat_id, current_user, db)
    db.delete(chat)
    db.commit()
