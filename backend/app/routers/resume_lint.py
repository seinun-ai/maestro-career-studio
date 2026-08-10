from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID as UUIDType

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.health_gate_waiver import HealthGateWaiver
from app.services import bullet_classify, health_guards, resume_lint

router = APIRouter(prefix="/api/resume-lint", tags=["resume-lint"])

Kind = Literal["base", "application"]

VALID_GATE_IDS = {"S1", "S2", "S3", "S4", "S5", "C1", "C2"}


class WaiveBody(BaseModel):
    reason: str


class OverrideBody(BaseModel):
    content_hash: str = Field(pattern=r"^[0-9a-f]{16}$")
    level: str | None = None
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class AnswerBody(BaseModel):
    answer: str


class AskAnswerRead(BaseModel):
    suggestion: str


def _find_waiver(db: Session, kind: str, key: str, gate_id: str) -> HealthGateWaiver | None:
    return db.scalar(select(HealthGateWaiver).where(
        HealthGateWaiver.resume_kind == kind,
        HealthGateWaiver.resume_key == key,
        HealthGateWaiver.gate_id == gate_id,
    ))


class LintReportRead(BaseModel):
    id: UUIDType
    resume_kind: str
    resume_key: str
    resume_version_number: int | None = None
    score: int
    grade: str
    tier: str | None = None
    counts: dict[str, int]
    gates: list[dict[str, Any]] = []
    findings: list[dict[str, Any]]
    model: str | None = None
    created_at: datetime


def _read(row) -> LintReportRead:
    return LintReportRead(
        id=row.id,
        resume_kind=row.resume_kind,
        resume_key=row.resume_key,
        resume_version_number=row.resume_version_number,
        model=row.model,
        created_at=row.created_at,
        **row.report_json,
    )


def _load_resume(db: Session, kind: Kind, key: str) -> tuple[dict, str | None]:
    if kind == "base":
        row = db.get(BaseResume, key)
        if row is None or row.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Base resume not found")
        return row.data_json, row.template_id
    try:
        application = db.get(Application, UUIDType(key))
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid application id") from e
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.customized_json is None:
        raise HTTPException(
            status_code=400,
            detail="Application has no tailored resume yet — materialize it first",
        )
    return application.customized_json, application.template_id


@router.post("/{kind}/{key}/run", response_model=LintReportRead)
def run_lint(kind: Kind, key: str, db: Annotated[Session, Depends(get_db)]):
    resume, template_id = _load_resume(db, kind, key)
    return _read(resume_lint.run_report(db, kind, key, resume, template_id=template_id))


@router.get("/{kind}/{key}", response_model=LintReportRead)
def get_latest_lint(kind: Kind, key: str, db: Annotated[Session, Depends(get_db)]):
    row = resume_lint.latest_report(db, kind, key)
    if row is None:
        raise HTTPException(status_code=404, detail="No health report yet")
    return _read(row)


@router.post("/{kind}/{key}/gates/{gate_id}/waive", status_code=204)
def waive_gate(kind: Kind, key: str, gate_id: str, body: WaiveBody,
               db: Annotated[Session, Depends(get_db)]):
    if gate_id not in VALID_GATE_IDS:
        raise HTTPException(status_code=422, detail=f"Unknown gate id: {gate_id}")
    if not body.reason.strip():
        raise HTTPException(status_code=422, detail="A waiver reason is required")
    existing = _find_waiver(db, kind, key, gate_id)
    if existing is not None:
        existing.reason = body.reason
    else:
        db.add(HealthGateWaiver(resume_kind=kind, resume_key=key,
                                gate_id=gate_id, reason=body.reason))
    db.commit()


@router.delete("/{kind}/{key}/gates/{gate_id}/waive", status_code=204)
def unwaive_gate(kind: Kind, key: str, gate_id: str,
                 db: Annotated[Session, Depends(get_db)]):
    existing = _find_waiver(db, kind, key, gate_id)
    if existing is not None:
        db.delete(existing)
        db.commit()


@router.post("/classification-override", status_code=204)
def override_level(body: OverrideBody, db: Annotated[Session, Depends(get_db)]):
    try:
        bullet_classify.set_override(db, body.content_hash, body.level, body.reason)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/{kind}/{key}/ask/{finding_id}/answer", response_model=AskAnswerRead)
def answer_ask(kind: Kind, key: str, finding_id: str, body: AnswerBody,
               db: Annotated[Session, Depends(get_db)]):
    report = resume_lint.latest_report(db, kind, key)
    if report is None:
        raise HTTPException(status_code=404, detail="No health report yet")
    finding = next((f for f in report.report_json.get("findings", [])
                    if f.get("id") == finding_id), None)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    resume, _ = _load_resume(db, kind, key)
    loc = finding.get("location") or {}
    section, index, bi = loc.get("section"), loc.get("index"), loc.get("bullet_index")
    if section == "summary":
        text = str(resume.get("summary") or "")
    elif section in ("experience", "projects") and index is not None and bi is not None:
        try:
            text = str((resume[section][index].get("bullets") or [])[bi])
        except (IndexError, KeyError, TypeError, AttributeError) as e:
            raise HTTPException(
                status_code=422, detail="Finding no longer maps to a bullet") from e
    else:
        raise HTTPException(status_code=422,
                            detail="This question isn't resolved by a bullet rewrite")
    suggestion = health_guards.guarded_rewrite(db, text, context=body.answer)
    if suggestion is None:
        raise HTTPException(status_code=422,
                            detail="Couldn't produce a safe rewrite from that answer")
    return AskAnswerRead(suggestion=suggestion)
