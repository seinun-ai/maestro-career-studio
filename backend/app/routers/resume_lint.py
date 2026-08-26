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
from app.models.health_ask_answer import HealthAskAnswer
from app.models.health_gate_waiver import HealthGateWaiver
from app.services import (
    bullet_classify,
    health_guards,
    health_score,
    resume_lint,
    resume_versions,
)
from app.services.health_guards import RewriteObjective

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


class LocationBody(BaseModel):
    section: str
    index: int | None = None
    bullet_index: int | None = None


class DraftRewriteBody(BaseModel):
    location: LocationBody
    context: str = ""
    objective: RewriteObjective = "strengthen"
    expected_content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")


class AskAnswerRead(BaseModel):
    suggestion: str


class StoredAskAnswer(BaseModel):
    answer: str
    suggestion: str | None
    content_hash: str


class DraftRewriteRead(BaseModel):
    suggestion: str
    content_hash: str


CONTENT_CHANGED = "content changed since analysis; re-analyze before answering"


def _find_waiver(db: Session, kind: str, key: str, gate_id: str) -> HealthGateWaiver | None:
    return db.scalar(select(HealthGateWaiver).where(
        HealthGateWaiver.resume_kind == kind,
        HealthGateWaiver.resume_key == key,
        HealthGateWaiver.gate_id == gate_id,
    ))


class ScoreBreakdown(BaseModel):
    raw_score: int
    e_hot: float | None = None
    n_scoreable: int
    capped_by: Literal["fatal", "serious"] | None = None


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
    stale: bool = False
    insufficient_evidence: bool = False
    score_breakdown: ScoreBreakdown | None = None
    model: str | None = None
    created_at: datetime


def _score_breakdown(row) -> ScoreBreakdown | None:
    features = row.features_json or {}
    raw_score = features.get("raw_score")
    if raw_score is None:
        return None
    n_scoreable = features.get("n_scoreable")
    if n_scoreable is None:
        levels = features.get("levels") or {}
        n_scoreable = sum(
            1 for location in levels if not str(location).startswith("summary:")
        )
    cap_tier = health_score.gate_cap_tier(row.report_json.get("gates", []))
    capped_by = cap_tier if int(row.report_json.get("score", raw_score)) < int(raw_score) else None
    return ScoreBreakdown(
        raw_score=int(raw_score),
        e_hot=features.get("e_hot"),
        n_scoreable=int(n_scoreable),
        capped_by=capped_by,
    )


def _read(row, *, stale: bool = False) -> LintReportRead:
    return LintReportRead(
        id=row.id,
        resume_kind=row.resume_kind,
        resume_key=row.resume_key,
        resume_version_number=row.resume_version_number,
        model=row.model,
        created_at=row.created_at,
        stale=stale,
        score_breakdown=_score_breakdown(row),
        **row.report_json,
    )


def _is_stale(db: Session, row) -> bool:
    latest = resume_versions.latest_version(
        db, row.resume_kind, row.resume_key
    )
    latest_number = latest.version_number if latest else None
    return row.resume_version_number != latest_number


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
    return _read(row, stale=_is_stale(db, row))


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


def _bullet_text(
    resume: dict,
    loc: dict,
    expected_hash: str | None,
    *,
    hashless_ok: bool = False,
) -> str:
    """Resolve the current bullet/summary text at ``loc``.

    409 when a hash was sent and the target vanished or drifted; 422 when
    the location cannot map to a rewriteable bullet and no hash was sent.
    ``hashless_ok`` lets T7 draft from a bullet that carries no finding hash:
    the response still returns the hash of the text drafted FROM.
    """
    section, index, bi = loc.get("section"), loc.get("index"), loc.get("bullet_index")
    if section == "summary":
        return str(resume.get("summary") or "")
    if section in ("experience", "projects") and index is not None and bi is not None:
        try:
            return str((resume[section][index].get("bullets") or [])[bi])
        except (IndexError, KeyError, TypeError, AttributeError) as e:
            if expected_hash is not None or not hashless_ok:
                if expected_hash is not None:
                    raise HTTPException(status_code=409, detail=CONTENT_CHANGED) from e
                raise HTTPException(
                    status_code=422, detail="Finding no longer maps to a bullet"
                ) from e
            raise HTTPException(
                status_code=422, detail="Location does not map to a bullet"
            ) from e
    raise HTTPException(
        status_code=422,
        detail="This question isn't resolved by a bullet rewrite",
    )


def _require_hash(text: str, expected_hash: str | None) -> str:
    actual = bullet_classify.content_hash(text)
    if expected_hash is not None and actual != expected_hash:
        raise HTTPException(status_code=409, detail=CONTENT_CHANGED)
    return actual


def _upsert_ask_answer(
    db: Session,
    *,
    kind: str,
    key: str,
    finding_id: str,
    content_hash: str,
    answer: str,
    suggestion: str | None,
) -> HealthAskAnswer:
    row = db.scalar(
        select(HealthAskAnswer).where(
            HealthAskAnswer.resume_kind == kind,
            HealthAskAnswer.resume_key == key,
            HealthAskAnswer.finding_id == finding_id,
        )
    )
    if row is None:
        row = HealthAskAnswer(
            resume_kind=kind,
            resume_key=key,
            finding_id=finding_id,
            content_hash=content_hash,
            answer=answer,
            suggestion=suggestion,
        )
        db.add(row)
    else:
        row.content_hash = content_hash
        row.answer = answer
        row.suggestion = suggestion
    db.commit()
    db.refresh(row)
    return row


@router.get("/{kind}/{key}/answers")
def list_ask_answers(
    kind: Kind, key: str, db: Annotated[Session, Depends(get_db)]
) -> dict[str, StoredAskAnswer]:
    rows = db.scalars(
        select(HealthAskAnswer).where(
            HealthAskAnswer.resume_kind == kind,
            HealthAskAnswer.resume_key == key,
        )
    ).all()
    return {
        row.finding_id: StoredAskAnswer(
            answer=row.answer,
            suggestion=row.suggestion,
            content_hash=row.content_hash,
        )
        for row in rows
    }


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
    expected_hash = finding.get("content_hash")
    text = _bullet_text(resume, loc, expected_hash)
    content_hash = _require_hash(text, expected_hash)
    _upsert_ask_answer(
        db,
        kind=kind,
        key=key,
        finding_id=finding_id,
        content_hash=content_hash,
        answer=body.answer,
        suggestion=None,
    )
    suggestion = health_guards.guarded_rewrite(db, text, context=body.answer)
    if suggestion is None:
        raise HTTPException(status_code=422,
                            detail="Couldn't produce a safe rewrite from that answer")
    _upsert_ask_answer(
        db,
        kind=kind,
        key=key,
        finding_id=finding_id,
        content_hash=content_hash,
        answer=body.answer,
        suggestion=suggestion,
    )
    return AskAnswerRead(suggestion=suggestion)


@router.post("/{kind}/{key}/draft-rewrite", response_model=DraftRewriteRead)
def draft_rewrite(
    kind: Kind,
    key: str,
    body: DraftRewriteBody,
    db: Annotated[Session, Depends(get_db)],
):
    resume, _ = _load_resume(db, kind, key)
    loc = body.location.model_dump()
    text = _bullet_text(
        resume, loc, body.expected_content_hash, hashless_ok=True
    )
    content_hash = _require_hash(text, body.expected_content_hash)
    suggestion = health_guards.guarded_rewrite(
        db, text, context=body.context, objective=body.objective
    )
    if suggestion is None:
        raise HTTPException(
            status_code=422, detail="Couldn't produce a safe rewrite from that answer"
        )
    return DraftRewriteRead(suggestion=suggestion, content_hash=content_hash)
