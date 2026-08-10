from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatSessionCreate(BaseModel):
    title: str | None = None
    context: dict[str, Any] | None = None


class ChatSessionPatch(BaseModel):
    title: str | None = None
    context: dict[str, Any] | None = None


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    content: str | None = None
    tool_calls: list[Any] | None = None
    tool_call_id: str | None = None
    meta_json: dict[str, Any] | None = None
    created_at: datetime


class ChatSessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None = None
    context_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ChatSessionDetail(ChatSessionSummary):
    messages: list[ChatMessageRead] = Field(default_factory=list)


class ChatAttachmentRead(BaseModel):
    id: UUID
    filename: str
    mime: str | None = None
    chars: int
    preview: str


class ChatSendRequest(BaseModel):
    content: str
    # {"target_kind", "target_key", "selections": [...], "attachment_ids": [...]}
    # selections are kind-tagged references: {"kind": "resume"|"kb_entity", ...};
    # missing kind = legacy resume-path chip.
    context: dict[str, Any] | None = None


CARD_STATE_STATUSES = ("applied", "discarded")


class ChatCardStateRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        if v not in CARD_STATE_STATUSES:
            raise ValueError(f"status must be one of {CARD_STATE_STATUSES}")
        return v
