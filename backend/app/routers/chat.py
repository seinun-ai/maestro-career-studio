import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.chat import ChatAttachment, ChatMessage, ChatSession
from app.schemas.chat import (
    ChatAttachmentRead,
    ChatCardStateRequest,
    ChatMessageRead,
    ChatSendRequest,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionPatch,
    ChatSessionSummary,
)
from app.services import chat_agent, llm_capabilities, model_settings
from app.services.attachment_extract import extract_text

router = APIRouter(prefix="/api/chat", tags=["chat"])

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


def _get_session_or_404(db: Session, session_id: UUID) -> ChatSession:
    row = db.get(ChatSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return row


@router.post("/sessions", response_model=ChatSessionSummary)
def create_session(payload: ChatSessionCreate, db: Annotated[Session, Depends(get_db)]):
    row = ChatSession(title=payload.title, context_json=payload.context)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/sessions", response_model=list[ChatSessionSummary])
def list_sessions(db: Annotated[Session, Depends(get_db)]):
    return list(db.scalars(select(ChatSession).order_by(ChatSession.updated_at.desc())))


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(session_id: UUID, db: Annotated[Session, Depends(get_db)]):
    row = _get_session_or_404(db, session_id)
    return ChatSessionDetail(
        id=row.id,
        title=row.title,
        context_json=row.context_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
        messages=[ChatMessageRead.model_validate(m) for m in row.messages],
    )


@router.patch("/sessions/{session_id}", response_model=ChatSessionSummary)
def patch_session(
    session_id: UUID, payload: ChatSessionPatch, db: Annotated[Session, Depends(get_db)]
):
    row = _get_session_or_404(db, session_id)
    if "title" in payload.model_fields_set:
        row.title = payload.title
    if "context" in payload.model_fields_set:
        row.context_json = payload.context
    db.commit()
    db.refresh(row)
    return row


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: UUID, db: Annotated[Session, Depends(get_db)]):
    row = _get_session_or_404(db, session_id)
    db.delete(row)
    db.commit()


@router.post("/sessions/{session_id}/messages")
def send_message(
    session_id: UUID, payload: ChatSendRequest, db: Annotated[Session, Depends(get_db)]
):
    """Run one agent turn; streams SSE events (delta/tool_start/change_card/…/done)."""
    row = _get_session_or_404(db, session_id)
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Message must not be empty")
    # Check the model BEFORE the StreamingResponse: `run_turn` is a generator,
    # so anything it raises fires after the headers are already out and reaches
    # the browser as a truncated stream, not an error the UI can render.
    try:
        llm_capabilities.require(db, model_settings.get_chat_model(db), "tools")
    except llm_capabilities.CapabilityMissing as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    def event_stream():
        for event in chat_agent.run_turn(db, row, payload.content, payload.context):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Card types whose cards carry Apply/Discard actions and therefore a resolution.
_RESOLVABLE_CARD_KEYS = ("proposal_ops", "proposal")


@router.patch("/messages/{message_id}/card-state", response_model=ChatMessageRead)
def set_card_state(
    message_id: UUID, payload: ChatCardStateRequest, db: Annotated[Session, Depends(get_db)]
):
    """Persist a proposal card's resolution so reloads can't re-offer it."""
    row = db.get(ChatMessage, message_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Chat message not found")
    meta = row.meta_json or {}
    if row.role != "tool" or not any(key in meta for key in _RESOLVABLE_CARD_KEYS):
        raise HTTPException(
            status_code=400, detail="Message does not carry a resolvable proposal card"
        )
    existing = (meta.get("card_state") or {}).get("status")
    if existing is not None and existing != payload.status:
        raise HTTPException(
            status_code=409, detail=f"Card already resolved as {existing!r}"
        )
    # Reassign (never mutate in place) so SQLAlchemy detects the JSONB change.
    row.meta_json = {
        **meta,
        "card_state": {"status": payload.status, "at": datetime.now(UTC).isoformat()},
    }
    db.commit()
    db.refresh(row)
    return ChatMessageRead.model_validate(row)


@router.post("/sessions/{session_id}/attachments", response_model=ChatAttachmentRead)
async def upload_attachment(
    session_id: UUID, file: UploadFile, db: Annotated[Session, Depends(get_db)]
):
    _get_session_or_404(db, session_id)
    data = await file.read()
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="Attachment exceeds 10 MB limit")
    try:
        text = extract_text(file.filename or "upload", file.content_type, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    row = ChatAttachment(
        session_id=session_id,
        filename=file.filename or "upload",
        mime=file.content_type,
        text_content=text,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ChatAttachmentRead(
        id=row.id,
        filename=row.filename,
        mime=row.mime,
        chars=len(text),
        preview=text[:500],
    )
