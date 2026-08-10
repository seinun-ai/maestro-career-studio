from datetime import datetime

from sqlalchemy import Boolean, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    # Render engine for this template's source: 'latex' (Jinja .tex.j2 -> pdflatex)
    # or 'typst' (raw .typ -> typst-py, data via sys_inputs). Immutable after
    # creation — changing engines invalidates the source (router rejects with 400).
    engine: Mapped[str] = mapped_column(
        Text, nullable=False, default="latex", server_default="latex"
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    origin: Mapped[str] = mapped_column(Text, nullable=False, server_default="frontend")
    last_error: Mapped[str | None] = mapped_column(Text)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Whether the compiled sample survives a strict PDF text extractor with word
    # boundaries intact (None = not yet checked). Set by validate_template.
    parse_certified: Mapped[bool | None] = mapped_column(Boolean)
    parse_report_json: Mapped[dict | None] = mapped_column(JSONB)  # extractor triple + missing probes
    default_formatting: Mapped[dict | None] = mapped_column(JSONB)
    # Hidden from the gallery and every picker, nothing else changed. Mirrors
    # base_resumes.archived_at deliberately — same column, same semantics, same
    # "not a delete" promise — so there is one archiving concept in the product
    # rather than two that behave almost alike.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
