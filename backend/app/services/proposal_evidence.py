"""Proposal evidence files under the linked application's artifact directory."""

from __future__ import annotations

import hashlib
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings as app_settings
from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.services import application_artifacts


class EvidenceError(Exception):
    """Mapped to HTTP 409 by the proposals router."""


def _require_application(session: Session, prop: ApplicationProposal) -> Application:
    if prop.application_id is None:
        raise EvidenceError("proposal has no linked application")
    app_row = session.get(Application, prop.application_id)
    if app_row is None:
        raise EvidenceError("proposal has no linked application")
    return app_row


def get_evidence_dir(session: Session, prop: ApplicationProposal) -> Path:
    app_row = _require_application(session, prop)
    artifact_dir = application_artifacts.get_dir(session, app_row)
    evidence_dir = artifact_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    return evidence_dir


def _collision_name(dest_dir: Path, filename: str, item: dict) -> str:
    candidate = dest_dir / filename
    if not candidate.exists():
        return filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    token = str(item.get("id") or item.get("sha256") or "dup")[:12]
    alt = f"{stem}-{token}{suffix}"
    n = 2
    while (dest_dir / alt).exists():
        alt = f"{stem}-{token}-{n}{suffix}"
        n += 1
    return alt


def migrate_legacy_evidence(session: Session, prop: ApplicationProposal) -> Path:
    """Move legacy application-id / proposal-id evidence into artifact_dir/evidence."""
    evidence_dir = get_evidence_dir(session, prop)
    app_row = session.get(Application, prop.application_id)
    assert app_row is not None

    legacy_roots = [
        app_settings.applications_dir / str(app_row.id) / "evidence",
        app_settings.applications_dir / str(prop.id) / "evidence",
    ]

    manifest = [dict(item) for item in (prop.evidence_json or [])]
    pending_by_name: dict[str, list[dict]] = {}
    for item in manifest:
        name = Path(str(item.get("path") or "")).name
        if name:
            pending_by_name.setdefault(name, []).append(item)

    for legacy in legacy_roots:
        if not legacy.exists() or legacy.resolve() == evidence_dir.resolve():
            continue
        for src in sorted(p for p in legacy.iterdir() if p.is_file()):
            queue = pending_by_name.get(src.name) or []
            item = queue.pop(0) if queue else {
                "sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
            }
            dest_name = _collision_name(evidence_dir, src.name, item)
            shutil.move(str(src), str(evidence_dir / dest_name))
            if item in manifest:
                item["path"] = f"evidence/{dest_name}"
        try:
            legacy.rmdir()
            legacy.parent.rmdir()
        except OSError:
            pass

    prop.evidence_json = manifest
    flag_modified(prop, "evidence_json")
    session.flush()
    return evidence_dir


def save_evidence(
    session: Session,
    prop: ApplicationProposal,
    *,
    step: int,
    label: str,
    data: bytes,
    extension: str = ".png",
    kind: str = "step",
) -> dict:
    from app.services import proposals as proposal_svc

    if kind not in proposal_svc.EVIDENCE_KINDS:
        raise EvidenceError(f"evidence kind must be one of {sorted(proposal_svc.EVIDENCE_KINDS)}")
    proposal_svc.require_open_proposal(session, prop, op="attach_evidence")

    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40] or "screenshot"
    kind_prefix = {
        "step": f"step-{step:02d}",
        "final_review": "final-review",
        "submission_receipt": "submission-receipt",
    }[kind]
    filename = f"{kind_prefix}-{slug}{extension}"

    evidence_dir = migrate_legacy_evidence(session, prop)

    filepath = evidence_dir / filename
    if filepath.exists():
        filename = _collision_name(
            evidence_dir,
            filename,
            {"sha256": hashlib.sha256(data).hexdigest()},
        )
        filepath = evidence_dir / filename

    filepath.write_bytes(data)

    sha256_hash = hashlib.sha256(data).hexdigest()
    relative_path = f"evidence/{filename}"

    item = {
        "step": step,
        "label": label,
        "kind": kind,
        "path": relative_path,
        "sha256": sha256_hash,
        "captured_at": datetime.now(UTC).isoformat(),
    }

    manifest = list(prop.evidence_json or [])
    manifest.append(item)
    prop.evidence_json = manifest
    session.commit()
    return item


def evidence_file_path(session: Session, prop: ApplicationProposal, name: str) -> Path | None:
    try:
        evidence_dir = get_evidence_dir(session, prop).resolve()
    except EvidenceError:
        return None
    target = (evidence_dir / name).resolve()
    try:
        if target.is_file() and target.is_relative_to(evidence_dir):
            return target
    except ValueError:
        return None
    return None
