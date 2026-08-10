"""Career Knowledge Base router: entity/point CRUD, draft inbox, derived detail."""

import json as _json
import logging
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import get_db
from app.models.base_resume import BaseResume
from app.models.career_kb import KBDocument, KBEntity, KBPoint, KBPortLog, KBProfile
from app.schemas.career_kb import (
    ImportReport,
    ImportedBaseRead,
    SkippedFileRead,
    ConsolidationReport,
    KBAdaptApplyRequest,
    KBAdaptProposal,
    KBAdaptRequest,
    KBCaptureRequest,
    KBCaptureResponse,
    KBContextResponse,
    KBDocumentIngestResponse,
    KBDocumentOut,
    KBEntityCreate,
    KBEntityDetail,
    KBEntityPatch,
    KBEntitySummary,
    KBInboxPoint,
    KBPointCreate,
    KBPointOut,
    KBPointPatch,
    KBPortRequest,
    KBPortResponse,
    KBProfileOut,
    KBProfilePatch,
)
from app.schemas.resume import ResumeData
from app.services import base_resume_data, kb_import, career_kb as svc
from app.services import kb_adapt
from app.services import kb_consolidation
from app.services import kb_ingest
from app.services import exports as career_exports
from app.services.attachment_extract import extract_text
from app.write_origin import WriteOrigin, get_write_origin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kb", tags=["kb"])


# --- Profile ---------------------------------------------------------------


def _to_profile_out(profile: KBProfile) -> KBProfileOut:
    return KBProfileOut(
        contact=profile.contact_json or {},
        summary=profile.summary or "",
        skills=profile.skills_json or [],
        notes=profile.notes or "",
        updated_at=profile.updated_at,
    )


@router.get("/profile", response_model=KBProfileOut)
def get_profile(db: Annotated[Session, Depends(get_db)]):
    profile = svc.get_or_create_profile(db)
    db.commit()
    db.refresh(profile)
    return _to_profile_out(profile)


@router.patch("/profile", response_model=KBProfileOut)
def patch_profile(
    payload: KBProfilePatch,
    db: Annotated[Session, Depends(get_db)],
):
    profile = svc.get_or_create_profile(db)
    data = payload.model_dump(exclude_unset=True, mode="json")
    if "contact" in data:
        profile.contact_json = data["contact"]
    if "summary" in data:
        profile.summary = data["summary"]
    if "skills" in data:
        profile.skills_json = data["skills"]
    if "notes" in data:
        profile.notes = data["notes"]
    db.commit()
    db.refresh(profile)
    career_exports.best_effort_refresh(db)
    return _to_profile_out(profile)


# --- Entities --------------------------------------------------------------


@router.get("/entities", response_model=list[KBEntitySummary])
def list_entities(
    db: Annotated[Session, Depends(get_db)],
    kind: str | None = None,
    status: str | None = None,
):
    stmt = (
        select(KBEntity)
        .options(selectinload(KBEntity.points), selectinload(KBEntity.documents))
        .order_by(KBEntity.created_at)
    )
    if kind:
        stmt = stmt.where(KBEntity.kind == kind)
    if status:
        stmt = stmt.where(KBEntity.status == status)
    return [svc.entity_summary(db, entity) for entity in db.scalars(stmt).all()]


@router.post("/entities", response_model=KBEntityDetail)
def create_entity(
    payload: KBEntityCreate,
    db: Annotated[Session, Depends(get_db)],
    write_origin: Annotated[WriteOrigin, Depends(get_write_origin)],
):
    entity = KBEntity(
        kind=payload.kind,
        title=payload.title,
        org=payload.org,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=payload.status,
        detail_json=payload.detail,
        notes=payload.notes,
        origin=write_origin.origin,
        origin_detail=write_origin.detail,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    career_exports.best_effort_refresh(db)
    return svc.entity_detail(db, entity)


@router.get("/entities/{entity_id}", response_model=KBEntityDetail)
def get_entity(entity_id: UUID, db: Annotated[Session, Depends(get_db)]):
    entity = db.get(KBEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return svc.entity_detail(db, entity)


@router.patch("/entities/{entity_id}", response_model=KBEntityDetail)
def patch_entity(
    entity_id: UUID,
    payload: KBEntityPatch,
    db: Annotated[Session, Depends(get_db)],
):
    entity = db.get(KBEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    data = payload.model_dump(exclude_unset=True)
    # detail_json is NOT NULL: an explicit {"detail": null} is ignored (mirrors
    # how patch_point guards its sibling tags field); {"detail": {}} still clears.
    if data.get("detail") is not None:
        entity.detail_json = data["detail"]
    data.pop("detail", None)
    for key, value in data.items():
        setattr(entity, key, value)
    db.commit()
    db.refresh(entity)
    career_exports.best_effort_refresh(db)
    return svc.entity_detail(db, entity)


@router.delete("/entities/{entity_id}", status_code=204)
def delete_entity(entity_id: UUID, db: Annotated[Session, Depends(get_db)]):
    entity = db.get(KBEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    db.delete(entity)
    db.commit()
    career_exports.best_effort_refresh(db)
    return Response(status_code=204)


# --- Points ----------------------------------------------------------------


@router.post("/entities/{entity_id}/points", response_model=KBPointOut)
def create_point(
    entity_id: UUID,
    payload: KBPointCreate,
    db: Annotated[Session, Depends(get_db)],
):
    entity = db.get(KBEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    point = KBPoint(
        entity_id=entity_id,
        text=payload.text,
        state="approved",
        origin="manual",
        approved_at=datetime.now(UTC),
        tags_json=payload.tags,
    )
    db.add(point)
    db.commit()
    db.refresh(point)
    career_exports.best_effort_refresh(db)
    return svc._to_point_out(db, point)


@router.post("/capture", response_model=KBCaptureResponse)
def capture_points(
    payload: KBCaptureRequest,
    db: Annotated[Session, Depends(get_db)],
    write_origin: Annotated[WriteOrigin, Depends(get_write_origin)],
):
    try:
        entity, points = kb_ingest.capture(
            db,
            payload.text,
            entity_id=payload.entity_id,
            origin=write_origin.origin or "manual",
            origin_detail=write_origin.detail,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    resp = KBCaptureResponse(
        entity_id=entity.id,
        entity_title=entity.title,
        point_ids=[p.id for p in points],
    )
    db.commit()
    career_exports.best_effort_refresh(db)
    return resp


@router.get("/points", response_model=list[KBInboxPoint])
def list_points(
    db: Annotated[Session, Depends(get_db)],
    state: str | None = None,
):
    stmt = (
        select(KBPoint)
        .options(selectinload(KBPoint.entity))
        .order_by(KBPoint.created_at)
    )
    if state:
        stmt = stmt.where(KBPoint.state == state)
    points = db.scalars(stmt).all()

    ids = [p.id for p in points]
    logs_by_point = defaultdict(list)
    if ids:
        for log in db.scalars(
            select(KBPortLog).where(KBPortLog.point_id.in_(ids)).order_by(KBPortLog.ported_at)
        ).all():
            logs_by_point[log.point_id].append(log)

    inbox: list[KBInboxPoint] = []
    for point in points:
        base = svc._to_point_out(db, point, port_logs=logs_by_point.get(point.id, []))
        inbox.append(
            KBInboxPoint(
                **base.model_dump(),
                entity_title=point.entity.title,
                entity_kind=point.entity.kind,
            )
        )
    return inbox


@router.patch("/points/{point_id}", response_model=KBPointOut)
def patch_point(
    point_id: UUID,
    payload: KBPointPatch,
    db: Annotated[Session, Depends(get_db)],
):
    point = db.get(KBPoint, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="Point not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("entity_id") is not None:
        target = db.get(KBEntity, data["entity_id"])
        if target is None:
            raise HTTPException(status_code=404, detail="Target entity not found")
        point.entity_id = data["entity_id"]
    if data.get("state") is not None:
        new_state = data["state"]
        if new_state == "approved":
            if point.approved_at is None:
                point.approved_at = datetime.now(UTC)
        else:
            # Leaving 'approved' invalidates the approval: approved_at means
            # "when the CURRENT text was approved", and an MCP edit demotes.
            point.approved_at = None
        point.state = new_state
    if data.get("text") is not None:
        point.text = data["text"]
    if data.get("tags") is not None:
        point.tags_json = data["tags"]
    db.commit()
    db.refresh(point)
    career_exports.best_effort_refresh(db)
    return svc._to_point_out(db, point)


@router.delete("/points/{point_id}", status_code=204)
def delete_point(point_id: UUID, db: Annotated[Session, Depends(get_db)]):
    point = db.get(KBPoint, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="Point not found")
    db.delete(point)
    db.commit()
    career_exports.best_effort_refresh(db)
    return Response(status_code=204)


# --- Documents -------------------------------------------------------------


def _to_document_out(document: KBDocument) -> KBDocumentOut:
    return KBDocumentOut.model_validate(document)


# Sync def (not async): extract_text is blocking CPU work and mint_document makes
# a multi-second blocking LLM call — FastAPI runs sync handlers in a threadpool, so
# this keeps a single upload from stalling the whole event loop.
@router.post("/documents/ingest", response_model=KBDocumentIngestResponse)
def ingest_document_first(
    file: UploadFile,
    db: Annotated[Session, Depends(get_db)],
):
    """Document-first entity creation: no pre-filled fields required.

    The document itself supplies the entity metadata — the LLM matches an
    existing entity or proposes a new one (kind/title/org/dates) and mints
    draft points for inbox review, all in one call.
    """
    data = file.file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Document exceeds 10 MB limit")
    try:
        entity, document, points, created = kb_ingest.ingest_document(
            db, file.filename, file.content_type, data
        )
    except kb_ingest.DocumentTextError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Couldn't read the document ({e}). Create the entity manually "
            "and attach the file from its page.",
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:  # LLM provider unavailable
        raise HTTPException(status_code=502, detail=str(e)) from e
    db.commit()
    db.refresh(document)
    db.refresh(entity)
    career_exports.best_effort_refresh(db)
    return KBDocumentIngestResponse(
        entity_id=entity.id,
        entity_title=entity.title,
        entity_kind=entity.kind,
        created_entity=created,
        point_count=len(points),
        document=_to_document_out(document),
    )


@router.post("/entities/{entity_id}/documents", response_model=KBDocumentOut)
def upload_document(
    entity_id: UUID,
    file: UploadFile,
    db: Annotated[Session, Depends(get_db)],
):
    entity = db.get(KBEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    data = file.file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Document exceeds 10 MB limit")

    ingest_summary: str | None = None
    try:
        text = extract_text(Path(file.filename or "upload").name, file.content_type, data)
        ingest_status = "extracted"
    except Exception as exc:  # noqa: BLE001 — unsupported, empty, OR corrupt/unparseable
        text = ""
        ingest_status = "failed"
        ingest_summary = str(exc)

    document = kb_ingest.store_document(
        db,
        entity_id,
        file.filename,
        file.content_type,
        data,
        text=text,
        ingest_status=ingest_status,
        ingest_summary=ingest_summary,
    )

    if document.ingest_status != "failed":
        kb_ingest.mint_document(db, document)

    db.commit()
    db.refresh(document)
    career_exports.best_effort_refresh(db)
    return _to_document_out(document)


@router.post("/documents/{document_id}/mint", response_model=KBDocumentOut)
def mint_document(document_id: UUID, db: Annotated[Session, Depends(get_db)]):
    document = db.get(KBDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    kb_ingest.mint_document(db, document)
    db.commit()
    db.refresh(document)
    career_exports.best_effort_refresh(db)
    return _to_document_out(document)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: UUID, db: Annotated[Session, Depends(get_db)]):
    document = db.get(KBDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    doc_dir = Path(settings.kb_documents_dir) / str(document.id)
    if doc_dir.exists():
        shutil.rmtree(doc_dir, ignore_errors=True)
    db.delete(document)  # points survive; source_document_id nulls via SET NULL FK
    db.commit()
    career_exports.best_effort_refresh(db)
    return Response(status_code=204)


# --- Port to base resume ---------------------------------------------------


@router.post("/port", response_model=KBPortResponse)
def port(payload: KBPortRequest, db: Annotated[Session, Depends(get_db)]):
    try:
        target, report = svc.port_to_resume(db, payload)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    from app.routers.base_resumes import _detail

    return KBPortResponse(resume=_detail(target), report=report)


@router.post("/port/adapt", response_model=KBAdaptProposal)
def port_adapt(payload: KBAdaptRequest, db: Annotated[Session, Depends(get_db)]):
    """Propose adapted bullets for selected points against one base resume (no writes)."""
    try:
        return kb_adapt.adapt_points(db, payload)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:  # LLM provider unavailable
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/port/adapt/apply", response_model=KBPortResponse)
def port_adapt_apply(payload: KBAdaptApplyRequest, db: Annotated[Session, Depends(get_db)]):
    """Apply user-approved adapted bullets; everything re-validated server-side."""
    try:
        target, report = kb_adapt.apply_adapted(db, payload)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    from app.routers.base_resumes import _detail

    return KBPortResponse(resume=_detail(target), report=report)


# --- Composed resume view --------------------------------------------------


@router.get("/compose", response_model=ResumeData)
def compose(db: Annotated[Session, Depends(get_db)]):
    """Assemble a ResumeData from the profile + non-archived entities + approved points."""
    return svc.compose_resume_data(db)


@router.get("/context", response_model=KBContextResponse)
def kb_context(db: Annotated[Session, Depends(get_db)]):
    """The full career grounding pair: approved-points resume + beyond-the-resume
    memory — the same composition chat's get_career_context tool reads, exposed
    over REST so the MCP server (Claude Desktop) can ground social posts and
    outreach in real career data."""
    return KBContextResponse(
        resume=svc.compose_resume_data(db),
        memory=svc.compose_context(db),
    )


# --- Consolidation ---------------------------------------------------------


def _parse_consolidation_slugs(raw: str | None) -> list[str]:
    """Decode the multipart slug field without trusting its JSON shape."""
    if not raw:
        return []
    try:
        parsed = _json.loads(raw)
    except (TypeError, _json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="slugs must be a JSON array of non-empty strings",
        ) from exc
    if not isinstance(parsed, list) or any(
        not isinstance(slug, str) or not slug.strip() for slug in parsed
    ):
        raise HTTPException(
            status_code=400,
            detail="slugs must be a JSON array of non-empty strings",
        )
    # Repeated sources only inflate duplicate counts and LLM prompt size.
    return list(dict.fromkeys(slug.strip() for slug in parsed))


# Sync def (not async): extract_text + parse_resume_text + consolidate() do
# blocking CPU + multi-second LLM work — FastAPI runs sync handlers in a
# threadpool, so this keeps a consolidate run from stalling the event loop.
@router.post("/import", response_model=ImportReport)
def import_resumes_endpoint(
    db: Annotated[Session, Depends(get_db)],
    files: list[UploadFile] = File(default=[]),
):
    """Onboarding: uploaded resumes become base resumes AND Career KB content.

    Resumable, not atomic — see services/kb_import. A file that cannot be parsed
    is skipped and reported; the batch still succeeds. Deliberately independent
    of the `kb.seeded` startup flag as a GATE (so it can be re-run whenever the
    user adds more resumes) while still SETTING it, so the next restart does not
    re-consolidate what was just imported.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Provide at least one file")

    uploads: list[tuple[str, str | None, bytes]] = []
    for f in files:
        name = Path(f.filename or "upload").name or "upload"
        try:
            uploads.append((name, f.content_type, f.file.read()))
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"{name}: could not read upload") from exc

    result = kb_import.import_resumes(db, uploads)
    if not result.bases and result.skipped:
        # Nothing landed — surface the first reason rather than a silent 200.
        raise HTTPException(
            status_code=422,
            detail=f"No resumes could be imported. {result.skipped[0].filename}: {result.skipped[0].reason}",
        )
    career_exports.best_effort_refresh(db)
    return ImportReport(
        bases=[ImportedBaseRead(**vars(b)) for b in result.bases],
        skipped=[SkippedFileRead(**vars(s)) for s in result.skipped],
        kb=result.kb,
    )


@router.post("/consolidate", response_model=ConsolidationReport)
def consolidate_endpoint(
    db: Annotated[Session, Depends(get_db)],
    slugs: str | None = Form(default=None),          # JSON-encoded list of base-resume slugs
    files: list[UploadFile] = File(default=[]),
):
    sources: list[tuple[str, dict]] = []

    # slug sources
    slug_list = _parse_consolidation_slugs(slugs)
    if slug_list:
        allowed = set(base_resume_data.active_base_resume_slugs(db))
        for slug in slug_list:
            if slug not in allowed:
                raise HTTPException(status_code=404, detail=f"Unknown base resume: {slug}")
            row = db.get(BaseResume, slug)
            if row is None or row.deleted_at is not None:
                raise HTTPException(status_code=404, detail=f"Unknown base resume: {slug}")
            sources.append((slug, row.data_json))

    # file sources
    for f in files:
        safe_name = Path(f.filename or "upload").name or "upload"
        try:
            data = f.file.read()
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"{safe_name}: could not read upload") from exc
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File exceeds 10 MB limit")
        try:
            text = extract_text(safe_name, f.content_type, data)
        except Exception as exc:  # noqa: BLE001 — parser libraries raise their own error types
            raise HTTPException(status_code=400, detail=f"{safe_name}: {exc}") from exc
        try:
            parsed = kb_consolidation.parse_resume_text(db, text)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{safe_name}: {exc}") from exc
        except RuntimeError as exc:
            # Upstream LLM outage — retryable, not a bad file.
            raise HTTPException(status_code=502, detail=f"{safe_name}: {exc}") from exc
        sources.append((safe_name, parsed))

    if not sources:
        raise HTTPException(status_code=400, detail="Provide at least one slug or file")

    report = kb_consolidation.consolidate(db, sources)
    career_exports.best_effort_refresh(db)
    return report
