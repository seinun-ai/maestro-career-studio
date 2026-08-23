"""Onboarding import: uploaded resumes become base resumes AND Career KB content.

`POST /api/kb/consolidate` already turned uploads into KB entities, but minted
no base resumes — so a new user uploading three resumes got a knowledge base and
nothing to tailor from. This closes that gap in one action.

## Resumable, NOT atomic — deliberately

Minting a base resume is three writes and only one is transactional:
  * `routers/base_resumes.py` commits, THEN writes `base_resumes/<slug>.json`,
    THEN renders,
  * `base_resume_render.render_base_resume` commits internally,
  * `prompts.get_prompt` INSERTs its file default and commits on first use.
The disk file is never transactional at all.

So "one transaction; a failure leaves neither" is unimplementable here. Worse,
rolling back would mean deleting rendered artifacts inside a transaction that
can still roll back — which SYSTEM.md §6 explicitly forbids and says must not be
reintroduced.

The contract instead: **each base is committed as it is minted; render is
best-effort; a failure leaves every already-minted base valid and re-importable.**
Never a DB row without its disk file, never a disk file without its row. The
import removes no artifacts, so re-running the same file is a merge, not a
409 storm.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base_resume import BaseResume
from app.models.career_kb import KBPortLog
from app.models.setting import Setting
from app.schemas.career_kb import ConsolidationReport
from app.schemas.resume import ResumeData
from app.services import (
    base_resume_data,
    base_resume_render,
    kb_consolidation,
    pdf_render,
    role_categories,
)
from app.services.attachment_extract import extract_text
from app.services.resume_versions import record_version

logger = logging.getLogger(__name__)

MAX_FILES = 10
MAX_BYTES = 10 * 1024 * 1024
KB_SEEDED_FLAG = "kb.seeded"

_JSON_SUFFIXES = {".json"}
_JSON_MIMES = {"application/json", "text/json"}


@dataclass
class ImportedBase:
    slug: str
    display_name: str
    role_category: str
    proposed: bool          # True = the system guessed; the UI must ask to confirm
    role_label: str | None = None
    render_error: str | None = None
    parse_warnings: list[str] = field(default_factory=list)


@dataclass
class SkippedFile:
    filename: str
    reason: str


@dataclass
class ImportResult:
    bases: list[ImportedBase] = field(default_factory=list)
    skipped: list[SkippedFile] = field(default_factory=list)
    kb: Any = None


def _is_json(filename: str, mime: str | None) -> bool:
    return (
        Path(filename).suffix.lower() in _JSON_SUFFIXES
        or (mime or "").lower().split(";")[0].strip() in _JSON_MIMES
    )


def _slugify(name: str) -> str:
    stem = Path(name).stem.lower()
    out = "".join(ch if ch.isalnum() else "_" for ch in stem).strip("_")
    while "__" in out:
        out = out.replace("__", "_")
    if not out or not out[0].isalnum():
        out = f"resume_{out}".strip("_")
    return out[:60] or "resume"


def _free_slug(session: Session, desired: str) -> str:
    """Find an unused slug.

    Three collision classes, all of which 409 or 400 through the REST create:
    the slug pattern, an existing row, and a SOFT-DELETED row whose slug is
    blocked permanently to preserve history. Import must never fail on any of
    them — it appends a counter instead.
    """
    candidate = desired
    n = 2
    while session.get(BaseResume, candidate) is not None:  # includes soft-deleted
        candidate = f"{desired}_{n}"
        n += 1
    return candidate


def _alias_label_for(proposed: str, display_name: str, data: dict) -> str | None:
    """Keep the user's own words when the winning guess was an alias hit."""
    if proposed == role_categories.UNKNOWN:
        return None
    for text in role_categories.signal_texts(data, display_name):
        match = role_categories.match_free_text(text)
        if match["category"] == proposed and match["confidence"] == "alias":
            return match["label"] or None
    return None


def _mint_base(
    session: Session,
    *,
    slug: str,
    display_name: str,
    data: dict,
    parse_warnings: list[str],
) -> ImportedBase:
    """Create one base resume. Commits before touching the filesystem."""
    proposed_role = role_categories.propose_from_resume(data, display_name=display_name)
    role_label = _alias_label_for(proposed_role, display_name, data)
    row = BaseResume(
        slug=slug,
        display_name=display_name,
        data_json=data,
        role_category=proposed_role,
        role_label=role_label,
    )
    session.add(row)
    record_version(session, "base", slug, data, source="import")
    session.commit()

    # Disk file AFTER the commit — a row without its file is recoverable, a file
    # without its row is an orphan the seeder would resurrect.
    base_resume_data.write_base_resume_json(slug, data)

    imported = ImportedBase(
        slug=slug,
        display_name=display_name,
        role_category=proposed_role,
        role_label=role_label,
        # An unambiguous proposal still needs confirming; "unknown" is not a
        # proposal at all, it is the visible undeclared state.
        proposed=proposed_role != role_categories.UNKNOWN,
        parse_warnings=parse_warnings,
    )

    # Render is best-effort: a pdflatex failure must not lose the base.
    try:
        base_resume_render.render_base_resume(slug, session)
    except Exception as exc:  # noqa: BLE001 — any renderer failure degrades
        logger.warning("import: render failed for %s: %s", slug, exc)
        imported.render_error = pdf_render.extract_render_error(str(exc))
    return imported


def import_resumes(
    session: Session,
    uploads: list[tuple[str, str | None, bytes]],
    *,
    consolidate: bool = True,
) -> ImportResult:
    """Mint a base resume per file, then optionally consolidate them into the KB.

    `uploads` is (filename, mime, bytes). Partial success is normal: a file that
    cannot be parsed is skipped and reported, never fatal to the batch.

    ``consolidate=False`` skips the final ``kb_consolidation.consolidate`` pass
    of THIS same function — not a second import implementation. Call
    ``consolidate_imported`` later over the minted slugs. Default True keeps
    the batched contract for MCP and any external caller.
    """
    result = ImportResult()
    sources: list[tuple[str, dict]] = []

    # Resolve every prompt and the model BEFORE adding rows to the session.
    # `get_prompt` INSERTs its file default and COMMITS on first use, which would
    # otherwise commit a half-built base mid-flight. The consolidation pipeline
    # pre-fetches for exactly this reason.
    kb_consolidation.prefetch_prompts(session)

    for filename, mime, blob in uploads[:MAX_FILES]:
        safe = Path(filename or "upload").name or "upload"
        try:
            if len(blob) > MAX_BYTES:
                raise ValueError("file exceeds the 10 MB limit")

            parse_warnings: list[str] = []
            if _is_json(safe, mime):
                # The README's own file-drop format. No extraction, no LLM call.
                parsed = ResumeData.model_validate(json.loads(blob)).model_dump(mode="json")
            else:
                text = extract_text(safe, mime, blob)
                parsed, parse_warnings = kb_consolidation.parse_resume_text(session, text)

            slug = _free_slug(session, _slugify(safe))
            display = Path(safe).stem.replace("_", " ").strip() or slug
            result.bases.append(
                _mint_base(
                    session,
                    slug=slug,
                    display_name=display,
                    data=parsed,
                    parse_warnings=parse_warnings,
                )
            )
            # Provenance key is the MINTED SLUG, not the filename: KBPortLog and
            # KBEntity.merge_sources_json store this as `resume_key`, and
            # everywhere else that means a slug. A filename there points at
            # nothing.
            sources.append((slug, parsed))
        except Exception as exc:  # noqa: BLE001 — one bad file must not fail the batch
            session.rollback()
            logger.info("import: skipping %s: %s", safe, exc)
            result.skipped.append(SkippedFile(filename=safe, reason=str(exc)[:300]))

    if len(uploads) > MAX_FILES:
        for filename, _, _ in uploads[MAX_FILES:]:
            result.skipped.append(
                SkippedFile(
                    filename=Path(filename or "upload").name,
                    reason=f"only the first {MAX_FILES} files are imported at once",
                )
            )

    if sources and consolidate:
        result.kb = kb_consolidation.consolidate(session, sources)
        _mark_kb_seeded(session)

    return result


def _mark_kb_seeded(session: Session) -> None:
    # Without this an import that yields no entities leaves the flag unset and
    # the next restart re-consolidates every base, including the ones just
    # imported.
    if session.get(Setting, KB_SEEDED_FLAG) is None:
        session.add(Setting(key=KB_SEEDED_FLAG, value="1"))
        session.commit()


def _sources_pending_consolidation(
    session: Session, slugs: list[str] | None = None
) -> list[tuple[str, dict]]:
    """Minted bases that have not yet produced a port-log row.

    ``consolidate()`` is NOT safe to re-run on experience/projects when the
    LLM fails to return existing ids (it would mint duplicate entities and
    points). Filtering to slugs with no port log is what makes a retry of
    ``POST /api/kb/import/consolidate`` equivalent to a no-op after success.
    """
    logged = set(session.scalars(select(KBPortLog.resume_key)).all())
    wanted = slugs if slugs is not None else list(base_resume_data.active_base_resume_slugs(session))
    sources: list[tuple[str, dict]] = []
    for slug in wanted:
        if slug in logged:
            continue
        row = session.get(BaseResume, slug)
        if row is None or row.deleted_at is not None:
            continue
        sources.append((slug, row.data_json))
    return sources


def consolidate_imported(
    session: Session, slugs: list[str] | None = None
) -> ConsolidationReport:
    """Run the same consolidate pass import_resumes would have, over pending sources."""
    kb_consolidation.prefetch_prompts(session)
    sources = _sources_pending_consolidation(session, slugs)
    if not sources:
        return ConsolidationReport()
    report = kb_consolidation.consolidate(session, sources)
    _mark_kb_seeded(session)
    return report
