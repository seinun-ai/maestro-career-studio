from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from sqlalchemy.orm import Session

from app.config import settings
from app.services import career_kb

logger = logging.getLogger(__name__)

CAREER_FILENAME = "career.md"
META_FILENAME = ".meta.json"
# The cache is keyed by the source data AND the renderer that shaped it. BUMP
# THIS whenever _render_markdown changes: without it an install whose KB has not
# changed keeps serving a career.md built by the previous renderer forever,
# because the data hash alone still matches.
RENDERER_VERSION = "2"
# CommonMark ATX: only `#`-runs followed by a space are headings, so a bare
# `#tag` or a `#` comment inside a note is left alone. Capped at 5 so demoting
# cannot produce a 7-hash non-heading.
_HEADING = re.compile(r"^(#{1,5}) ")
_cache_lock = RLock()


@dataclass(frozen=True)
class CareerExportResult:
    markdown: str
    content_hash: str
    generated_at: datetime
    cached: bool


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _source(session: Session) -> tuple[dict, str, str]:
    resume = career_kb.compose_resume_data(session)
    memory = career_kb.compose_context(session)
    canonical = json.dumps(
        {"renderer": RENDERER_VERSION, "resume": resume, "memory": memory},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return resume, memory, content_hash


def _one_line(value: object) -> str:
    return " ".join(str(value or "").split())


def _dates(start: object, end: object) -> str:
    start_text, end_text = _one_line(start), _one_line(end)
    if start_text and end_text:
        return f"{start_text} – {end_text}"
    if start_text:
        return f"{start_text} – present"
    return end_text


def _bullets(lines: list[str], values: list[object]) -> None:
    for value in values:
        text = _one_line(value)
        if text:
            lines.append(f"- {text}")


def _nested(memory: str) -> str:
    """Push the memory block's headings one level down.

    compose_context is written as a standalone prompt block, so its per-entity
    headers are `##` — the same level as this document's own sections. Spliced
    in verbatim they stop being children of "Beyond the Resume" and flatten the
    outline instead. Demote here rather than in compose_context: the QA, cover
    letter and cold-outreach prompts read that text and must not change.
    """
    return "\n".join(_HEADING.sub(r"#\1 ", line) for line in memory.splitlines())


def _render_markdown(
    resume: dict,
    memory: str,
    content_hash: str,
    generated_at: datetime,
) -> str:
    lines = ["# Career Profile", ""]
    contact = resume.get("contact") or {}
    lines.extend(["## Contact", ""])
    for key, label in (
        ("name", "Name"), ("email", "Email"), ("phone", "Phone"),
        ("location", "Location"), ("linkedin", "LinkedIn"),
        ("github", "GitHub"), ("website", "Website"),
    ):
        value = _one_line(contact.get(key))
        if value:
            lines.append(f"- **{label}:** {value}")

    summary = _one_line(resume.get("summary"))
    if summary:
        lines.extend(["", "## Summary", "", summary])

    skills = resume.get("skills") or []
    if skills:
        lines.extend(["", "## Skills", ""])
        for group in skills:
            items = ", ".join(_one_line(item) for item in group.get("items", []) if _one_line(item))
            if items:
                lines.append(f"- **{_one_line(group.get('category'))}:** {items}")

    experience = resume.get("experience") or []
    if experience:
        lines.extend(["", "## Experience", ""])
        for entry in experience:
            lines.append(f"### {_one_line(entry.get('role'))} — {_one_line(entry.get('company'))}".rstrip(" —"))
            details = " · ".join(filter(None, [_dates(entry.get("start_date"), entry.get("end_date")), _one_line(entry.get("location"))]))
            if details:
                lines.extend(["", details])
            _bullets(lines, entry.get("bullets") or [])
            lines.append("")

    projects = resume.get("projects") or []
    if projects:
        lines.extend(["## Projects", ""])
        for entry in projects:
            lines.append(f"### {_one_line(entry.get('name'))}")
            details = " · ".join(filter(None, [_one_line(entry.get("date")), _one_line(entry.get("tech")), _one_line(entry.get("link"))]))
            if details:
                lines.extend(["", details])
            _bullets(lines, entry.get("bullets") or [])
            lines.append("")

    education = resume.get("education") or []
    if education:
        lines.extend(["## Education", ""])
        for entry in education:
            degree = " in ".join(filter(None, [_one_line(entry.get("degree")), _one_line(entry.get("field"))]))
            lines.append(f"### {degree} — {_one_line(entry.get('institution'))}".rstrip(" —"))
            details = " · ".join(filter(None, [_dates(entry.get("start_date"), entry.get("end_date") or entry.get("graduation_date")), _one_line(entry.get("location"))]))
            if details:
                lines.extend(["", details])
            _bullets(lines, entry.get("bullets") or [])
            lines.append("")

    certifications = resume.get("certifications") or []
    if certifications:
        lines.extend(["## Certifications", ""])
        _bullets(lines, certifications)

    if memory.strip():
        lines.extend(["", "## Beyond the Resume", "", _nested(memory.strip())])

    generated = generated_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    lines.extend([
        "", "---", "", f"Generated: {generated}",
        f"Content SHA-256: `{content_hash}`", "",
        "_Derived export — edit in Maestro CS._",
    ])
    return "\n".join(lines).strip() + "\n"


def _path(name: str) -> Path:
    return Path(settings.exports_dir) / name


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _cached(content_hash: str) -> CareerExportResult | None:
    try:
        meta = json.loads(_path(META_FILENAME).read_text(encoding="utf-8"))["career"]
        if meta["hash"] != content_hash:
            return None
        markdown = _path(CAREER_FILENAME).read_text(encoding="utf-8")
        generated_at = datetime.fromisoformat(meta["generated_at"].replace("Z", "+00:00"))
        return CareerExportResult(markdown, content_hash, generated_at, True)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _persist(result: CareerExportResult) -> None:
    generated = result.generated_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    meta = json.dumps(
        {"career": {"hash": result.content_hash, "generated_at": generated}},
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ) + "\n"
    # Body first, metadata second: a crash cannot mark an old body as current.
    _atomic_write(_path(CAREER_FILENAME), result.markdown)
    _atomic_write(_path(META_FILENAME), meta)


def get_career_export(session: Session, *, force: bool = False) -> CareerExportResult:
    resume, memory, content_hash = _source(session)  # composition errors intentionally propagate
    with _cache_lock:
        if not force:
            cached = _cached(content_hash)
            if cached is not None:
                return cached
        generated_at = _utc_now()
        result = CareerExportResult(
            markdown=_render_markdown(resume, memory, content_hash, generated_at),
            content_hash=content_hash,
            generated_at=generated_at,
            cached=False,
        )
        try:
            _persist(result)
        except OSError as exc:
            logger.warning("Career export cache unavailable at %s: %s", settings.exports_dir, exc)
        return result


def best_effort_refresh(session: Session) -> None:
    try:
        get_career_export(session, force=True)
    except Exception:
        logger.warning("Career export eager refresh failed", exc_info=True)
        # Callers hook this in AFTER their commit but still build their response
        # off this session. A composition query that failed at the DB level
        # leaves the transaction unusable, so swallowing the error is not enough
        # — without the rollback the caller's own response query raises and a
        # committed KB write reports 500. The rollback is itself guarded: this
        # helper's whole contract is that it never propagates.
        try:
            session.rollback()
        except Exception:
            logger.warning("Career export refresh could not roll back", exc_info=True)
