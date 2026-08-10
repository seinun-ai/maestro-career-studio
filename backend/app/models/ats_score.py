import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AtsScore(Base):
    __tablename__ = "ats_scores"
    __table_args__ = (
        Index("ix_ats_scores_job_id_phase", "job_id", "phase"),
        Index("ix_ats_scores_application_id", "application_id"),
        # Backstop against concurrent duplicate base rows; the service still does
        # a select-then-update upsert (single-user app).
        Index(
            "uq_ats_scores_base_target",
            "job_id", "target_type", "target_id",
            unique=True,
            postgresql_where=text("phase = 'base'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(Text, nullable=False)  # base_resume | application
    target_id: Mapped[str] = mapped_column(Text, nullable=False)    # slug or application uuid str
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=True
    )
    phase: Mapped[str] = mapped_column(Text, nullable=False)        # base | tailored
    composite: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    subscores_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    skill_table_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    gaps_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    config_version: Mapped[str] = mapped_column(Text, nullable=False)
    engine_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    @property
    def jd_skills_extracted_count(self) -> int:
        return self.subscores_json.get("jd_skills_extracted_count", 0) if self.subscores_json else 0

    @property
    def jd_skills_matched_count(self) -> int:
        return self.subscores_json.get("jd_skills_matched_count", 0) if self.subscores_json else 0

    @property
    def coverage_ratio(self) -> float:
        return float(self.subscores_json.get("coverage_ratio", 0.0)) if self.subscores_json else 0.0

    @property
    def coverage_warning(self) -> str | None:
        return self.subscores_json.get("coverage_warning") if self.subscores_json else None

