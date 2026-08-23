"""Ingestion: turn uploaded documents into draft KB points via the mint LLM."""

import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings  # re-exported so tests can patch kb_documents_dir here
from app.models.career_kb import KBDocument, KBEntity, KBPoint
from app.schemas.career_kb import KB_KINDS  # no circular import: schemas don't import services
from app.services import llm, model_settings, prompts
from app.services.attachment_extract import extract_text

__all__ = [
    "capture",
    "ingest_document",
    "mint_document",
    "store_document",
    "write_document_bytes",
    "settings",
]

logger = logging.getLogger(__name__)

MINT_INPUT_CAP = 30_000

# detail_json keys a document may populate on a NEW entity (strings only).
_DETAIL_KEYS = ("tech", "link", "field")


class DocumentTextError(ValueError):
    """The document yielded no usable text (unsupported, empty, or corrupt)."""


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _entity_context(entity: KBEntity, existing_points: list[str]) -> str:
    lines = [f"kind: {entity.kind}", f"title: {entity.title}"]
    if entity.org:
        lines.append(f"org: {entity.org}")
    tech = (entity.detail_json or {}).get("tech")
    if tech:
        lines.append(f"tech: {tech}")
    if existing_points:
        lines.append("existing points (do NOT duplicate):")
        lines.extend(f"- {p}" for p in existing_points)
    return "\n".join(lines)


def mint_document(session: Session, document: KBDocument) -> KBDocument:
    entity = document.entity
    if not (document.text_content or "").strip():
        document.ingest_status = "failed"
        document.ingest_summary = "no extractable text"
        return document
    existing = [p.text for p in entity.points if p.state != "retired"]
    prompt = (
        prompts.get_prompt("kb_mint", session)
        .replace("$entity_context", _entity_context(entity, existing))
        .replace("$document_text", document.text_content[:MINT_INPUT_CAP])
    )
    try:
        result = llm.call_openai(
            prompt=prompt,
            model=model_settings.get_smart_model(session),
            response_format="json",
            trace_name="kb-mint",
        )
    except Exception as exc:  # noqa: BLE001 — LLM failure leaves the doc re-mintable
        document.ingest_status = "failed"
        document.ingest_summary = f"mint failed: {exc}"
        return document
    if not isinstance(result, dict):
        document.ingest_status = "failed"
        document.ingest_summary = "mint returned non-object"
        return document
    seen = {_normalize(t) for t in existing}
    minted = skipped = 0
    for cand in (result.get("points") or [])[:10]:
        text = (cand.get("text") or "").strip() if isinstance(cand, dict) else ""
        if not text:
            continue
        if _normalize(text) in seen:
            skipped += 1
            continue
        seen.add(_normalize(text))
        session.add(
            KBPoint(
                entity_id=entity.id,
                text=text,
                state="draft",
                origin="ingested",
                provenance="user_authored",
                source_document_id=document.id,
            )
        )
        minted += 1
    document.ingest_status = "minted"
    document.ingest_summary = f"{minted} points minted, {skipped} skipped as duplicates"
    return document


def write_document_bytes(document: KBDocument, data: bytes) -> None:
    """Mirror the upload bytes to kb_documents_dir; degrade to a warning on OSError."""
    dest = Path(settings.kb_documents_dir) / str(document.id) / document.filename
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        document.file_path = str(dest)
    except OSError as exc:  # degrade gracefully — a missing mirror dir must not 500
        logger.warning("KB document bytes not written at %s: %s", dest, exc)


def store_document(
    session: Session,
    entity_id,
    filename: str | None,
    mime: str | None,
    data: bytes,
    *,
    text: str,
    ingest_status: str,
    ingest_summary: str | None = None,
    write_bytes: bool = True,
) -> KBDocument:
    """Persist a KBDocument row and (by default) mirror the bytes to disk.

    Strips any directory components from the client-supplied name (a raw
    "../../etc/passwd" would escape the per-document dir). Callers doing more
    DB work after this can pass ``write_bytes=False`` and call
    ``write_document_bytes`` once their writes have flushed, shrinking the
    window where a rollback would orphan the file on disk.
    """
    safe_name = Path(filename or "upload").name or "upload"
    document = KBDocument(
        entity_id=entity_id,
        filename=safe_name,
        mime=mime,
        size_bytes=len(data),
        text_content=text,
        ingest_status=ingest_status,
        ingest_summary=ingest_summary,
    )
    session.add(document)
    session.flush()  # assign document.id before the file write
    if write_bytes:
        write_document_bytes(document, data)
    return document


def _clean_extra_identity(raw_entity: dict, raw_detail: dict | None) -> tuple[str, str, str] | None:
    detail = raw_detail if isinstance(raw_detail, dict) else {}
    s_key = detail.get("section_key") or raw_entity.get("section_key")
    s_type = detail.get("section_type") or raw_entity.get("section_type")
    s_title = detail.get("section_title") or raw_entity.get("section_title")
    if not isinstance(s_key, str) or not isinstance(s_type, str) or not isinstance(s_title, str):
        return None
    try:
        from app.schemas.career_kb import _validate_extra_identity

        return _validate_extra_identity(s_key.strip(), s_type.strip(), s_title.strip())
    except ValueError:
        return None


def _build_entity_from_doc(
    new_entity: dict,
    *,
    origin: str | None = None,
    origin_detail: str | None = None,
) -> KBEntity:
    """Coerce the LLM's proposed entity; never trust output."""
    title = new_entity.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("document ingest proposed an entity without a valid title")
    kind = new_entity.get("kind")
    detail_raw = new_entity.get("detail")
    extra_identity = None
    if kind == "extra":
        extra_identity = _clean_extra_identity(new_entity, detail_raw)
        if extra_identity is None:
            kind = "project"
    elif kind not in KB_KINDS:  # untrusted LLM output; fall back rather than persist junk
        kind = "project"

    def _clean(key: str) -> str | None:
        value = new_entity.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else None

    detail: dict = {}
    if isinstance(detail_raw, dict):
        for key in _DETAIL_KEYS:
            value = detail_raw.get(key)
            if isinstance(value, str) and value.strip():
                detail[key] = value.strip()
    if extra_identity is not None:
        detail["section_key"], detail["section_type"], detail["section_title"] = extra_identity
    # Documents usually describe finished things (certs especially), unlike a
    # live capture dump — hence "completed" where capture defaults "ongoing".
    return KBEntity(
        kind=kind,
        title=title.strip(),
        org=_clean("org"),
        start_date=_clean("start_date"),
        end_date=_clean("end_date"),
        status="completed",
        detail_json=detail,
        origin=origin,
        origin_detail=origin_detail,
    )


def ingest_document(
    session: Session,
    filename: str | None,
    mime: str | None,
    data: bytes,
    *,
    origin: str | None = None,
    origin_detail: str | None = None,
):
    """Document-first ingest: one LLM call matches/proposes the entity AND mints points.

    Returns (entity, document, points, created_entity). Raises
    ``DocumentTextError`` (→422) when no text can be extracted, ``ValueError``
    (→400) for bad LLM output, and lets the LLM client's ``RuntimeError``
    (→502) propagate. Commit-free: the caller owns the transaction.
    """
    safe_name = Path(filename or "upload").name or "upload"
    try:
        text = extract_text(safe_name, mime, data)
    except Exception as exc:  # noqa: BLE001 — unsupported, empty, OR corrupt/unparseable
        raise DocumentTextError(str(exc)) from exc
    if not (text or "").strip():
        raise DocumentTextError("no extractable text")

    candidates = list(
        session.scalars(
            select(KBEntity)
            .where(KBEntity.status != "archived")
            .order_by(KBEntity.created_at)
        )
    )
    prompt = (
        prompts.get_prompt("kb_document_ingest", session)
        .replace("$entity_list", _entity_list_lines(candidates))
        .replace("$document_text", text[:MINT_INPUT_CAP])
    )
    result = llm.call_openai(
        prompt=prompt,
        model=model_settings.get_smart_model(session),
        response_format="json",
        trace_name="kb-doc-ingest",
    )
    if not isinstance(result, dict):
        raise ValueError("document ingest LLM returned a non-object")

    created = False
    raw_id = result.get("entity_id")
    new_entity = result.get("new_entity")
    if raw_id:
        try:
            target = session.get(KBEntity, uuid.UUID(str(raw_id)))
        except (ValueError, TypeError):
            target = None
        # Archived entities were never offered as candidates; an id that
        # resolves to one came from hallucination or the untrusted document
        # text itself — reject rather than silently file points there.
        if target is None or target.status == "archived":
            raise ValueError(f"document ingest chose unknown entity id {raw_id!r}")
    elif isinstance(new_entity, dict):
        target = _build_entity_from_doc(
            new_entity, origin=origin, origin_detail=origin_detail
        )
        session.add(target)
        session.flush()
        created = True
    else:
        # The LLM may refuse a no-signal document (e.g. text is only a person's
        # name) instead of inventing an entity; surface that as unreadable (422).
        reason = result.get("insufficient")
        if isinstance(reason, str) and reason.strip():
            raise DocumentTextError(reason.strip())
        raise ValueError("document ingest returned neither an entity_id nor a new_entity")

    document = store_document(
        session,
        target.id,
        safe_name,
        mime,
        data,
        text=text,
        ingest_status="extracted",
        write_bytes=False,  # written after all DB work below, see store_document
    )

    existing = [p.text for p in target.points if p.state != "retired"]
    seen = {_normalize(t) for t in existing}
    points: list[KBPoint] = []
    skipped = 0
    for raw in (result.get("points") or [])[:10]:
        body = raw.strip() if isinstance(raw, str) else ""
        if not body:
            continue
        if _normalize(body) in seen:
            skipped += 1
            continue
        seen.add(_normalize(body))
        point = KBPoint(
            entity_id=target.id,
            text=body,
            state="draft",
            origin="ingested",
            provenance="user_authored",
            source_document_id=document.id,
        )
        session.add(point)
        points.append(point)
    document.ingest_status = "minted"
    document.ingest_summary = f"{len(points)} points minted, {skipped} skipped as duplicates"
    session.flush()
    # Bytes last: every DB statement has now succeeded, so only a failed
    # router commit can still orphan the file (narrowest achievable window).
    write_document_bytes(document, data)
    return target, document, points, created


def _entity_list_lines(entities: list[KBEntity]) -> str:
    return "\n".join(f"{e.id} | {e.kind} | {e.title} | {e.org or ''}" for e in entities) or "(none)"


def capture(
    session: Session,
    text: str,
    entity_id=None,
    origin: str = "manual",
    origin_detail: str | None = None,
):
    """Free-text dump -> draft points on an existing or newly-proposed entity.

    Returns (entity, [points]). origin is 'manual' (KB page), 'chat' (chat tool)
    or 'mcp' (an MCP session); origin_detail names the client for the last of
    these. Raises LookupError for a missing hinted entity (router -> 404) and
    ValueError for bad LLM output (router -> 400).
    """
    if entity_id is not None:
        hinted = session.get(KBEntity, entity_id)
        if hinted is None:
            raise LookupError(f"entity {entity_id} not found")  # router -> 404
        candidates = [hinted]
    else:
        candidates = list(
            session.scalars(
                select(KBEntity)
                .where(KBEntity.status != "archived")
                .order_by(KBEntity.created_at)
            )
        )

    prompt = (
        prompts.get_prompt("kb_capture", session)
        .replace("$entity_list", _entity_list_lines(candidates))
        .replace("$dump_text", text)
    )
    result = llm.call_openai(
        prompt=prompt,
        model=model_settings.get_fast_model(session),
        response_format="json",
        trace_name="kb-capture",
    )
    if not isinstance(result, dict):
        raise ValueError("capture LLM returned a non-object")

    if entity_id is not None:
        target = hinted  # hint forces placement
    else:
        raw_id = result.get("entity_id")
        new_entity = result.get("new_entity")
        if raw_id:
            try:
                target = session.get(KBEntity, uuid.UUID(str(raw_id)))
            except (ValueError, TypeError):
                target = None
            if target is None:
                raise ValueError(f"capture chose unknown entity id {raw_id!r}")
        elif isinstance(new_entity, dict):
            title = new_entity.get("title")
            if not isinstance(title, str) or not title.strip():
                raise ValueError("capture proposed an entity without a valid title")
            kind = new_entity.get("kind")
            detail_raw = new_entity.get("detail")
            extra_identity = None
            detail: dict = {}
            if kind == "extra":
                extra_identity = _clean_extra_identity(new_entity, detail_raw)
                if extra_identity is None:
                    kind = "project"
                else:
                    detail["section_key"], detail["section_type"], detail["section_title"] = extra_identity
            elif kind not in KB_KINDS:  # untrusted LLM output; fall back rather than persist junk
                kind = "project"
            org = new_entity.get("org")
            org = org.strip() if isinstance(org, str) and org.strip() else None
            target = KBEntity(
                kind=kind,
                title=title.strip(),
                org=org,
                status="ongoing",
                detail_json=detail,
                origin=origin if origin != "manual" else None,
                origin_detail=origin_detail,
            )
            session.add(target)
            session.flush()
        else:
            raise ValueError("capture returned neither an entity_id nor a new_entity")

    points = []
    for raw in result.get("points") or []:
        body = raw.strip() if isinstance(raw, str) else ""
        if not body:
            continue
        p = KBPoint(
            entity_id=target.id,
            text=body,
            state="draft",
            origin=origin,
            origin_detail=origin_detail,
            provenance="user_stated",
        )
        session.add(p)
        points.append(p)
    session.flush()
    return target, points
