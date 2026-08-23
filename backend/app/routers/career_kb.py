"""Career Knowledge Base router: entity/point CRUD, draft inbox, derived detail."""

import json as _json
import logging
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import ObjectDeletedError, StaleDataError

from app.config import settings
from app.db import get_db
from app.models.base_resume import BaseResume
from app.models.career_kb import KBDocument, KBEntity, KBPoint, KBPortLog, KBProfile
from app.models.setting import Setting
from app.schemas.career_kb import (
    ImportReport,
    ImportedBaseRead,
    ImportConsolidateRequest,
    IngestParsedReport,
    IngestParsedRequest,
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
    KBEntityCreateResponse,
    KBEntityDetail,
    KBEntityDuplicateHint,
    KBEntityMergeRequest,
    KBEntityPatch,
    KBEntitySummary,
    KBInboxPoint,
    KBPointBulkResponse,
    KBPointBulkState,
    KBPointCreate,
    KBPointOut,
    KBPointPatch,
    KBPortRequest,
    KBPortResponse,
    KBProfileOut,
    KBProfilePatch,
    ExtraSectionPreset,
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


def _possible_duplicate_hints(
    db: Session, payload: KBEntityCreate
) -> list[KBEntityDuplicateHint]:
    """Return the existing exact/near identity for this kind, if unambiguous."""
    if payload.kind == "experience":
        section = "experience"
        entry = {
            "company": payload.org,
            "role": payload.title,
            "start_date": payload.start_date,
        }
        index = kb_consolidation._existing_exp_index(db, incoming_org=payload.org)
    elif payload.kind == "project":
        section = "projects"
        entry = {"name": payload.title}
        index = kb_consolidation._existing_proj_index(db, incoming_org=payload.org)
    elif payload.kind == "education":
        section = "education"
        entry = {"institution": payload.org, "degree": payload.title}
        index = kb_consolidation._existing_edu_index(db, incoming_org=payload.org)
    elif payload.kind == "certification":
        section = "certifications"
        entry = payload.title if not payload.org else f"{payload.title} ({payload.org})"
        index = kb_consolidation._existing_cert_index(db, incoming_org=payload.org)
    else:
        section = "extra"
        entry = {
            "section_key": payload.detail.get("section_key"),
            "section_type": payload.detail.get("section_type"),
            "heading": payload.title,
        }
        index = kb_consolidation._existing_extra_index(db, incoming_org=payload.org)

    key = kb_consolidation.identity_key(section, entry)
    candidate = index.get(key)
    if candidate is None:
        candidate = kb_consolidation.find_near_identity(section, key, index)
    if candidate is None:
        return []
    incoming_org = kb_consolidation._norm(payload.org)
    candidate_org = kb_consolidation._norm(candidate.org)
    if incoming_org and candidate_org and incoming_org != candidate_org:
        return []
    return [
        KBEntityDuplicateHint(id=candidate.id, title=candidate.title, org=candidate.org)
    ]


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


@router.post("/entities", response_model=KBEntityCreateResponse)
def create_entity(
    payload: KBEntityCreate,
    db: Annotated[Session, Depends(get_db)],
    write_origin: Annotated[WriteOrigin, Depends(get_write_origin)],
):
    possible_duplicates = _possible_duplicate_hints(db, payload)
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
    detail = svc.entity_detail(db, entity)
    return KBEntityCreateResponse(
        **detail.model_dump(), possible_duplicates=possible_duplicates
    )


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
    section_updates = {}
    for sk in ("section_key", "section_type", "section_title"):
        if sk in data:
            section_updates[sk] = data.pop(sk)
    if section_updates:
        current_detail = dict(entity.detail_json or {})
        current_detail.update(section_updates)
        entity.detail_json = current_detail
    for key, value in data.items():
        setattr(entity, key, value)
    db.commit()
    db.refresh(entity)
    career_exports.best_effort_refresh(db)
    return svc.entity_detail(db, entity)


@router.post("/entities/{entity_id}/merge", response_model=KBEntityDetail)
def merge_entity(
    entity_id: UUID,
    payload: KBEntityMergeRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Fold `entity_id` into `target_id` and return the surviving target's detail.

    Web-only: the MCP surface deliberately gains no destructive merge tool.
    """
    try:
        target = svc.merge_entities(db, entity_id, payload.target_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (ObjectDeletedError, StaleDataError) as e:
        # Merge takes no row locks (see svc.merge_entities): a CONCURRENT merge
        # of the same source is a race whose loser lands here. A sequential
        # double-submit is not a race and gets the clean 404 above.
        raise HTTPException(
            status_code=409,
            detail="This entity was merged by another request; refresh and retry",
        ) from e
    db.commit()
    db.refresh(target)
    career_exports.best_effort_refresh(db)
    return svc.entity_detail(db, target)


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
        provenance="user_stated",
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
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    stmt = (
        select(KBPoint)
        .options(selectinload(KBPoint.entity))
    )
    if state:
        stmt = stmt.where(KBPoint.state == state)
    stmt = stmt.order_by(KBPoint.created_at, KBPoint.id).offset(offset).limit(limit)
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


def _apply_point_state(point: KBPoint, new_state: str) -> None:
    """Mirror the single-PATCH approved_at contract for bulk-state too."""
    if new_state == "approved":
        if point.approved_at is None:
            point.approved_at = datetime.now(UTC)
    else:
        # Leaving 'approved' invalidates the approval: approved_at means
        # "when the CURRENT text was approved", and an MCP edit demotes.
        point.approved_at = None
    point.state = new_state


@router.post("/points/bulk-state", response_model=KBPointBulkResponse)
def bulk_point_state(
    payload: KBPointBulkState,
    db: Annotated[Session, Depends(get_db)],
):
    """Mass approve or retire. Per-id honest results; unknown ids do not
    abort the rest of the batch. draft is not a legal target."""
    results = []
    # One result row per unique id, in first-occurrence order: a repeated id is
    # one point, and echoing it twice would misreport the batch size.
    for pid in dict.fromkeys(payload.ids):
        point = db.get(KBPoint, pid)
        if point is None:
            results.append({"id": pid, "ok": False, "state": None, "detail": "not found"})
            continue
        _apply_point_state(point, payload.state)
        results.append({"id": pid, "ok": True, "state": point.state, "detail": None})
    db.commit()
    career_exports.best_effort_refresh(db)
    return KBPointBulkResponse(results=results)


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
        _apply_point_state(point, data["state"])
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
    write_origin: Annotated[WriteOrigin, Depends(get_write_origin)],
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
            db,
            file.filename,
            file.content_type,
            data,
            origin=write_origin.origin,
            origin_detail=write_origin.detail,
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


def _source_error(index: int, path: tuple, msg: str, err_type: str) -> dict:
    """One validation error for one source, in FastAPI's own {loc, msg, type}
    shape. The handler shares this endpoint's 422 with FastAPI's request-model
    errors, so a bespoke {key, error} dialect would make the same status code
    carry two incompatible detail shapes."""
    return {"loc": ["body", "sources", index, *path], "msg": msg, "type": err_type}


@router.post("/ingest-parsed", response_model=IngestParsedReport)
def ingest_parsed(
    payload: IngestParsedRequest,
    db: Annotated[Session, Depends(get_db)],
    write_origin: Annotated[WriteOrigin, Depends(get_write_origin)],
):
    """Caller-parsed resume intake: persist into the Career KB, mint no bases.

    Strict and atomic — every source is validated as ResumeData before any
    write; one failure 422s the batch with per-source detail and persists
    nothing. Re-runs merge. Points land as DRAFTS: an agent transcribed them,
    so POST /api/kb/points/bulk-state (or the /career inbox) is the gate that
    puts them in front of composed resumes.
    """
    errors: list[dict] = []
    sources: list[tuple[str, dict]] = []
    first_use: dict[str, int] = {}
    for index, src in enumerate(payload.sources):
        if src.key in first_use:
            # Duplicate keys corrupt merge_sources provenance and make the
            # last-source-wins profile seed depend on list order.
            errors.append(_source_error(
                index, ("key",),
                f"duplicate source key {src.key!r} (first used at index {first_use[src.key]})",
                "value_error",
            ))
            continue
        first_use[src.key] = index
        try:
            data = ResumeData.model_validate(src.data).model_dump(mode="json")
        except ValidationError as exc:
            # Project each error onto exactly {loc, msg, type}, and ask
            # pydantic for nothing else: a ResumeData validator that raises
            # ValueError puts the exception OBJECT in `ctx`, and json.dumps on
            # an HTTPException detail carrying it turns this 422 into a 500.
            errors.extend(
                _source_error(
                    index,
                    ("data", *err.get("loc", ())),
                    err.get("msg") or "invalid value",
                    err.get("type") or "value_error",
                )
                for err in exc.errors(
                    include_url=False, include_context=False, include_input=False
                )
            )
            continue
        sources.append((src.key, data))
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    report = kb_consolidation.consolidate_deterministic(
        db, sources,
        origin=write_origin.origin,
        origin_detail=write_origin.detail,
        commit=False,
    )
    # Only a run that actually landed something may burn the one-shot seed
    # flag — a content-free ingest would otherwise permanently disable the
    # startup base-resume seed.
    landed = report.entities_created or report.points_created
    if landed and db.get(Setting, kb_import.KB_SEEDED_FLAG) is None:
        db.add(Setting(key=kb_import.KB_SEEDED_FLAG, value="1"))
    db.commit()
    career_exports.best_effort_refresh(db)
    return IngestParsedReport(
        entities=[
            {"id": e.id, "kind": e.kind, "title": e.title, "org": e.org, "created": e.created}
            for e in report.entities
        ],
        points=[
            {"id": p.id, "entity_id": p.entity_id, "text": p.text}
            for p in report.points
        ],
        entities_created=report.entities_created,
        entities_matched=report.entities_matched,
        points_created=report.points_created,
        duplicates_skipped=report.duplicates_skipped,
        skills_merged=report.skills_merged,
        warnings=report.warnings,
    )


# Sync def (not async): extract_text + parse_resume_text + consolidate() do
# blocking CPU + multi-second LLM work — FastAPI runs sync handlers in a
# threadpool, so this keeps a consolidate run from stalling the event loop.
@router.post("/import", response_model=ImportReport)
def import_resumes_endpoint(
    db: Annotated[Session, Depends(get_db)],
    files: list[UploadFile] = File(default=[]),
    consolidate: bool = Query(True),
):
    """Onboarding: uploaded resumes become base resumes AND Career KB content.

    Resumable, not atomic — see services/kb_import. A file that cannot be parsed
    is skipped and reported; the batch still succeeds. Deliberately independent
    of the `kb.seeded` startup flag as a GATE (so it can be re-run whenever the
    user adds more resumes) while still SETTING it, so the next restart does not
    re-consolidate what was just imported.

    ``consolidate=false`` mints bases and skips the KB pass so the UI can show
    per-file progress, then call ``POST /api/kb/import/consolidate``. Default
    True is the batched contract; MCP and external callers must not notice.
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

    result = kb_import.import_resumes(db, uploads, consolidate=consolidate)
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


@router.post("/import/consolidate", response_model=ConsolidationReport)
def import_consolidate_endpoint(
    db: Annotated[Session, Depends(get_db)],
    payload: ImportConsolidateRequest | None = None,
):
    """Run the import pipeline's consolidation pass over minted bases not yet in the KB."""
    slugs = payload.slugs if payload is not None else None
    if slugs:
        allowed = set(base_resume_data.active_base_resume_slugs(db))
        for slug in slugs:
            if slug not in allowed:
                raise HTTPException(status_code=404, detail=f"Unknown base resume: {slug}")
    report = kb_import.consolidate_imported(db, slugs)
    career_exports.best_effort_refresh(db)
    return report


@router.post("/consolidate", response_model=ConsolidationReport)
def consolidate_endpoint(
    db: Annotated[Session, Depends(get_db)],
    slugs: str | None = Form(default=None),          # JSON-encoded list of base-resume slugs
    files: list[UploadFile] = File(default=[]),
):
    sources: list[tuple[str, dict]] = []
    parse_warnings: list[str] = []

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
            parsed, warnings = kb_consolidation.parse_resume_text(db, text)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{safe_name}: {exc}") from exc
        except RuntimeError as exc:
            # Upstream LLM outage — retryable, not a bad file.
            raise HTTPException(status_code=502, detail=f"{safe_name}: {exc}") from exc
        sources.append((safe_name, parsed))
        parse_warnings.extend(f"{safe_name}: {warning}" for warning in warnings)

    if not sources:
        raise HTTPException(status_code=400, detail="Provide at least one slug or file")

    report = kb_consolidation.consolidate(db, sources)
    report.warnings.extend(parse_warnings)
    career_exports.best_effort_refresh(db)
    return report


@router.get("/extra-section-presets", response_model=list[ExtraSectionPreset])
def list_extra_section_presets():
    """Canonical extra-section presets shared between studio and Career KB."""
    from app.services.extra_section_presets import PRESETS

    return PRESETS
