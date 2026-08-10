"""Base-resume slug gating + disk data loading.

Extracted from the (removed) legacy fit_score service: these helpers are the
canonical way to resolve which base resumes exist and to load their JSON data.
"""
import json
from pathlib import Path
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.config import settings
from app.db import SessionLocal
from app.models.base_resume import BaseResume


def active_filter() -> ColumnElement[bool]:
    """SQL predicate for ACTIVE (not soft-deleted) rows — the RESOLUTION gate.

    Compose into any select over BaseResume (``.where(active_filter())``, or
    ``not_(active_filter())`` for the inverse). This is the ONE definition of
    the policy; the slug helpers below and every direct-table query share it,
    so a policy change (or a third axis) is one edit here."""
    return BaseResume.deleted_at.is_(None)


def selectable_filter() -> ColumnElement[bool]:
    """SQL predicate for SELECTABLE rows (active AND not archived) — the
    CHOICE set. Deliberately a SEPARATE predicate from active_filter, never to
    be merged: archive removes a base from MENUS, never from the SYSTEM, so
    anything answering "does this slug exist?" wants active_filter and
    anything answering "what can I pick?" wants this (SYSTEM.md §4)."""
    return and_(BaseResume.deleted_at.is_(None), BaseResume.archived_at.is_(None))


def active_base_resume_slugs(session: Session) -> list[str]:
    """Return the active (non-soft-deleted) base resume slugs.

    The slug SET is derived from the ``base_resumes`` table so it stays in
    sync with reality (e.g. hard-deleted ``hybrid`` disappears, newly added
    rows like ``business_analyst`` appear). Resume DATA still loads from disk.
    """
    return list(
        session.scalars(
            select(BaseResume.slug).where(active_filter()).order_by(BaseResume.slug)
        )
    )


def selectable_base_resume_slugs(session: Session) -> list[str]:
    """Slugs a user or agent may CHOOSE from — active and not archived.

    The counterpart to active_base_resume_slugs, which stays the RESOLUTION
    gate; see the two filter helpers above for why the axes never merge.
    """
    return list(
        session.scalars(
            select(BaseResume.slug).where(selectable_filter()).order_by(BaseResume.slug)
        )
    )


def write_base_resume_json(slug: str, data: dict) -> None:
    """Mirror a base resume's JSON data to disk (canonical write helper).

    Creates the base-resumes dir if absent and writes ``<slug>.json`` with
    2-space indentation, matching the historical on-disk format.
    """
    base_dir = Path(settings.base_resumes_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / f"{slug}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def base_resume_path(slug: str) -> Path:
    return Path(settings.base_resumes_dir) / f"{slug}.json"


def _read_base_resume_data(slug: str) -> dict[str, Any]:
    """Load base resume DATA from disk (unchanged data source, no gating)."""
    return json.loads(base_resume_path(slug).read_text(encoding="utf-8"))


def load_base_resume(slug: str, session: Session | None = None) -> dict[str, Any]:
    """Validate ``slug`` against the ``base_resumes`` table, then load from disk.

    The validation gate (which slugs are allowed) is table-derived, but the
    resume DATA is still read from disk via ``_read_base_resume_data`` to
    preserve existing behavior.
    """
    owns_session = session is None
    session = session or SessionLocal()
    try:
        if slug not in active_base_resume_slugs(session):
            raise ValueError(f"Unknown base resume: {slug}")
    finally:
        if owns_session:
            session.close()

    try:
        return _read_base_resume_data(slug)
    except FileNotFoundError as e:
        # Active table row but no on-disk data file: convert to the same clean
        # ValueError contract callers expect, without leaking the filesystem path.
        raise ValueError(f"Base resume '{slug}' is active but has no data file") from e


def declared_role(session, slug: str | None) -> str | None:
    """The base resume's declared role_category, or None if it has none.

    Artifact naming needs this as its last-resort label. Returns None for a
    missing or soft-deleted row and for the undeclared "unknown" state, so the
    caller falls through to its own default rather than filing a PDF under a
    placeholder.
    """
    from app.models.base_resume import BaseResume

    if not slug:
        return None
    row = session.get(BaseResume, slug)
    if row is None or row.role_category in (None, "unknown", "other"):
        return None
    return row.role_category
