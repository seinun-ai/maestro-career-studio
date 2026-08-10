import uuid

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (Index("ix_job_skills_skill_name", "skill_name"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    skill_name: Mapped[str] = mapped_column(Text, primary_key=True)
    skill_category: Mapped[str] = mapped_column(Text, primary_key=True)
    requirement_level: Mapped[str] = mapped_column(Text, primary_key=True)
