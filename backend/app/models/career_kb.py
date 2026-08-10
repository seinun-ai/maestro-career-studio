"""Career Knowledge Base: entities, points, documents, port provenance, profile."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class KBEntity(Base):
    __tablename__ = "kb_entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # experience|project|education|certification
    title: Mapped[str] = mapped_column(Text, nullable=False)
    org: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[str | None] = mapped_column(Text)
    end_date: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="completed", server_default="completed"
    )  # ongoing|completed|archived
    detail_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa_text("'{}'::jsonb")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    # Provenance for agent-written rows. NULL = created before this existed, or
    # through the web UI. See KBPoint.origin for the vocabulary.
    origin: Mapped[str | None] = mapped_column(Text)
    origin_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    points: Mapped[list["KBPoint"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan", order_by="KBPoint.created_at"
    )
    documents: Mapped[list["KBDocument"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan", order_by="KBDocument.created_at"
    )


class KBPoint(Base):
    __tablename__ = "kb_points"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        Text, nullable=False, default="draft", server_default="draft"
    )  # draft|approved|retired
    origin: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # manual|ingested|chat|consolidated|mcp|gap_elicitation
    # Which client wrote it, when origin is an agent: "Claude Desktop", "ChatGPT".
    origin_detail: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_documents.id", ondelete="SET NULL")
    )
    tags_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa_text("'[]'::jsonb")
    )
    merge_sources_json: Mapped[list[Any] | None] = mapped_column(JSONB)  # [{resume_key, section, text}]
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    entity: Mapped[KBEntity] = relationship(back_populates="points")


class KBDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    file_path: Mapped[str | None] = mapped_column(Text)
    text_content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    ingest_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="extracted", server_default="extracted"
    )  # extracted|minted|failed
    ingest_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    entity: Mapped[KBEntity] = relationship(back_populates="documents")


class KBPortLog(Base):
    __tablename__ = "kb_port_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # CASCADE is intentional: design cascades port provenance away on point deletion (nullable is for entry-shell/cert payloads, point_id=None)
    point_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_points.id", ondelete="CASCADE"), index=True
    )
    resume_kind: Mapped[str] = mapped_column(Text, nullable=False, default="base", server_default="base")
    resume_key: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str] = mapped_column(Text, nullable=False)
    ported_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # Point text at port time; set only by adapted ports (ported_text is the
    # rewritten resume bullet there). NULL = verbatim port, where ported_text
    # doubles as the snapshot. Drift compares the snapshot to the current point.
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class KBProfile(Base):
    __tablename__ = "kb_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    contact_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa_text("'{}'::jsonb")
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    skills_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa_text("'[]'::jsonb")
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
