"""Stable per-application artifact directory allocation.

One folder per application colocates resume/source/PDF, page previews,
cover letters, and evidence. Allocated once and persisted on
``Application.artifact_dir`` (absolute path, matching ``pdf_path``).
"""

from __future__ import annotations

import re
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.models.application import Application
from app.models.job import Job
from app.models.qa_entry import QAEntry


def _safe_part(value: str | None, fallback: str) -> str:
    text = value or fallback
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text or fallback


def folder_name(
    *,
    company: str | None,
    role_label: str | None,
    when: date,
    application_id: UUID,
) -> str:
    return "_".join(
        [
            _safe_part(company, "Company"),
            _safe_part(role_label, "Role"),
            when.strftime("%Y%m%d"),
            application_id.hex[:8],
        ]
    )


def _persist_dir(application: Application, path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    resolved = path.resolve()
    application.artifact_dir = str(resolved)
    return resolved


def _apps_using_dir(session: Session, directory: Path) -> list[Application]:
    dir_resolved = directory.resolve()
    dir_str = str(dir_resolved)
    candidates = session.scalars(
        select(Application).where(
            or_(
                Application.artifact_dir == dir_str,
                Application.pdf_path.is_not(None),
                Application.tex_path.is_not(None),
            )
        )
    ).all()
    claimed: list[Application] = []
    for app in candidates:
        if app.artifact_dir and Path(app.artifact_dir).resolve() == dir_resolved:
            claimed.append(app)
            continue
        for raw in (app.pdf_path, app.tex_path):
            if raw and Path(raw).resolve().parent == dir_resolved:
                claimed.append(app)
                break
    return claimed


def _rewrite_path(raw: str | None, src: Path, dest: Path) -> str | None:
    if not raw:
        return raw
    path = Path(raw)
    try:
        rel = path.resolve().relative_to(src.resolve())
    except ValueError:
        return raw
    return str(dest / rel)


def _move_tree_contents(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if not src.exists() or src.resolve() == dest.resolve():
        return
    for child in src.iterdir():
        target = dest / child.name
        if target.exists():
            if child.is_dir():
                _move_tree_contents(child, target)
                try:
                    child.rmdir()
                except OSError:
                    pass
            continue
        shutil.move(str(child), str(target))
    try:
        src.rmdir()
    except OSError:
        pass


def _relocate_application_artifacts(
    session: Session, application: Application, src: Path, dest: Path
) -> None:
    dest = _persist_dir(application, dest)
    if src.exists():
        _move_tree_contents(src, dest)

    application.pdf_path = _rewrite_path(application.pdf_path, src, dest)
    application.tex_path = _rewrite_path(application.tex_path, src, dest)

    for entry in session.scalars(
        select(QAEntry).where(QAEntry.application_id == application.id)
    ):
        entry.pdf_path = _rewrite_path(entry.pdf_path, src, dest)


def _allocate_new(
    session: Session,
    application: Application,
    *,
    company: str | None,
    role_label: str | None,
    when: date,
) -> Path:
    name = folder_name(
        company=company,
        role_label=role_label,
        when=when,
        application_id=application.id,
    )
    dest = Path(app_settings.applications_dir) / name
    src: Path | None = None
    if application.pdf_path:
        src = Path(application.pdf_path).resolve().parent
    elif application.tex_path:
        src = Path(application.tex_path).resolve().parent

    if src is not None and src != dest.resolve() and src.exists():
        _relocate_application_artifacts(session, application, src, dest)
    else:
        _persist_dir(application, dest)
    session.flush()
    return Path(application.artifact_dir)


def _resolve_labels(
    session: Session,
    application: Application,
    *,
    company: str | None,
    role_label: str | None,
) -> tuple[str | None, str | None]:
    if company is not None and role_label is not None:
        return company, role_label
    job = session.get(Job, application.job_id)
    if job is None:
        return company, role_label
    return (
        company if company is not None else job.company,
        role_label if role_label is not None else (job.title or job.role_category),
    )


def get_dir(
    session: Session,
    application: Application,
    *,
    company: str | None = None,
    role_label: str | None = None,
    when: date | None = None,
) -> Path:
    """Return the application's stable artifact directory, allocating if needed."""
    if application.artifact_dir:
        path = Path(application.artifact_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    if application.pdf_path:
        parent = Path(application.pdf_path).resolve().parent
        claimants = _apps_using_dir(session, parent)
        ids = {a.id for a in claimants}
        if ids <= {application.id} and parent.exists():
            path = _persist_dir(application, parent)
            session.flush()
            return path

    company, role_label = _resolve_labels(
        session, application, company=company, role_label=role_label
    )
    return _allocate_new(
        session,
        application,
        company=company,
        role_label=role_label,
        when=when or datetime.now(UTC).date(),
    )
