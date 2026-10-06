"""The profile as a bundle: export it at home, apply it onto the always-on copy (design Part B).

A bundle is JSON: every profile row per table (paths relative to their root), the files those rows
point at and no others (a base resume's JSON, PDF and TeX; a career document's upload; a template's
preview PDF), the job-site login and home's profile revision. Applying is the always-on copy's job only: it makes its profile equal
the bundle, so seeds that exist only there (startup seeding, first-read defaults, the empty
career-profile row) are replaced or removed.

The whole bundle is validated before the first write. Settings that are machine-local (see
``registry.LOCAL_SETTING_PREFIXES``) are neither exported nor touched. The login is a secret: it
travels only here, is written through ``job_site_login`` (0600), and nothing in this module logs or
echoes row, file or login contents; errors name a table or a field, never a value.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.db import Base
from app.models.sync import SyncState
from app.services import (
    artifacts,
    auto_apply_settings,
    autofill_profile,
    base_resume_data,
    eeo_consent,
    job_preferences,
    job_site_login,
    market_settings,
    mcp_workflow,
    persona,
    quick_tailor,
    text_settings,
)
from app.services.sync import bundle_rows, files, jobs_bundle, registry, status
from app.services.sync.bundle_rows import obj_pk, row_pk

DEFAULT_MAX_BYTES = 100 * 1024 * 1024
FILE_ROOTS = ("base_resumes", "kb_documents")
PREVIEWS = "template_previews"  # under the base-resumes root: <template id>.pdf
REFUSED = "Only the always-on copy applies a profile."

# Settings that keep a file mirror under settings_dir, written through text_settings so the mirror
# stays in step with the row. A new file-mirrored setting MUST be added here.
MIRRORS: dict[str, str] = {
    auto_apply_settings.AUTO_APPLY_KEY: auto_apply_settings.AUTO_APPLY_FILE,
    quick_tailor.QUICK_TAILOR_KEY: quick_tailor.QUICK_TAILOR_FILE,
    job_preferences.JOB_PREFERENCES_KEY: job_preferences.JOB_PREFERENCES_FILE,
    market_settings.MARKET_KEY: market_settings.MARKET_FILE,
    mcp_workflow.MCP_WORKFLOW_KEY: mcp_workflow.MCP_WORKFLOW_FILE,
    eeo_consent.EEO_CONSENT_KEY: eeo_consent.EEO_CONSENT_FILE,
    persona.PERSONA_KEY: persona.PERSONA_FILE,
    autofill_profile.AUTOFILL_KEY: autofill_profile.AUTOFILL_FILE,
}


@dataclass(frozen=True)
class Table:
    """One profile table. ``paths`` maps a path column to the root it must stay inside;
    ``base_only`` limits a ``by_kind`` table to its ``resume_kind == 'base'`` rows."""

    name: str
    model: type[Base]
    base_only: bool = False
    paths: dict[str, str] = field(default_factory=dict)
    order: str | None = None
    hidden: tuple[str, ...] = ()


# Parents before children: the order rows are written in; deletes run in reverse.
TABLES: tuple[Table, ...] = (
    Table("base_resumes", models.BaseResume,
          paths={"pdf_path": "base_resumes", "tex_path": "base_resumes"}),
    Table("templates", models.Template),
    Table("referrals", models.Referral),
    Table("kb_entities", models.KBEntity),
    Table("kb_documents", models.KBDocument, paths={"file_path": "kb_documents"}),
    Table("kb_points", models.KBPoint),
    Table("kb_port_log", models.KBPortLog, base_only=True),
    Table("kb_profile", models.KBProfile),
    Table("settings", models.Setting),
    Table("resume_versions", models.ResumeVersion, base_only=True, order="version_number"),
    Table("resume_lint_reports", models.ResumeLintReport, base_only=True),
    Table("health_ask_answers", models.HealthAskAnswer, base_only=True),
    Table("health_gate_waivers", models.HealthGateWaiver, base_only=True),
)
_BY_NAME = {spec.name: spec for spec in TABLES}


def _filters(spec: Table) -> list:
    """The rows of this table that belong to the profile."""
    if spec.base_only:
        return [spec.model.resume_kind == "base"]
    if spec.name == "settings":
        return [sa.not_(spec.model.key.startswith(prefix, autoescape=True))
                for prefix in registry.LOCAL_SETTING_PREFIXES]
    return []


# ---------------------------------------------------------------------------- export


def _export_rows(db: Session) -> list[dict]:
    return bundle_rows.export_rows(db, TABLES, _filters, jobs_bundle._export_row)


def _row_files(table: str, row: dict) -> set[str | None]:
    """The portable paths one exported row points at."""
    if table == "base_resumes":
        return {f"base_resumes:{row['slug']}.json", row["pdf_path"], row["tex_path"]}
    if table == "kb_documents":
        return {row["file_path"]}
    if table == "templates":
        return {f"base_resumes:{PREVIEWS}/{row['id']}.pdf"}
    return set()


def _referenced(rows: list[dict]) -> list[str]:
    found: set[str | None] = set()
    for item in rows:
        found |= _row_files(item["table"], item["row"])
    return sorted(path for path in found
                  if path and not path.lower().endswith(bundle_rows.LATEX_LEFTOVERS))


def _pack_file(portable: str, remaining: int) -> tuple[dict, int] | None:
    """One referenced file and the bytes it used; None when it is missing or cannot be sent."""
    name, _, rel = portable.partition(":")
    try:
        files._split(rel, allow_empty=False)
    except ValueError:
        return None  # a name no file could have
    path = files._checked(name, rel, allow_empty=False)  # a symlink raises
    return files._entry(name, files._root(name), path, remaining)


def _pack(rows: list[dict], max_bytes: int) -> tuple[list[dict], int]:
    """The files the rows point at, not the roots' whole contents. A missing or unsendable file is
    skipped and counted; going over ``max_bytes`` raises ValueError."""
    packed: list[dict] = []
    skipped = 0
    remaining = max_bytes
    for portable in _referenced(rows):
        result = _pack_file(portable, remaining)
        if result is None:
            skipped += 1
            continue
        packed.append(result[0])
        remaining -= result[1]
    return packed, skipped


def _login() -> dict | None:
    email, password = job_site_login.read()
    return None if email is None and password is None else {"email": email, "password": password}


def export_profile(db: Session, *, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    """The profile, its files and the job-site login, JSON-safe. ValueError over ``max_bytes`` or
    for a symlink among the files. The revision is read first: a save during the export then ships
    newer content under the older revision, which only costs a repeat, never a stale remote."""
    revision = db.scalar(select(SyncState.value).where(SyncState.name == "profile_rev"))
    rows = _export_rows(db)
    packed, skipped = _pack(rows, max_bytes)
    return {
        "rows": rows,
        "files": packed,
        "files_skipped": skipped,
        "job_site_login": _login(),
        "profile_rev": revision or 0,
    }


# ---------------------------------------------------------------------------- parse and validate


@dataclass
class Parsed:
    rows: dict[str, list[dict]] = field(repr=False)  # settings rows can hold AI keys
    files: list = field(repr=False)
    login: dict | None = field(repr=False)
    rev: int


def _decode_path(spec: Table, key: str, value):
    root = spec.paths[key]
    if value is not None and not (isinstance(value, str) and value.startswith(f"{root}:")):
        raise ValueError(f"{spec.name} path is outside its root")
    return files.from_portable(value)


def _decode_value(spec: Table, column: sa.Column, key: str, value):
    if key in spec.paths:
        return _decode_path(spec, key, value)
    decoded = jobs_bundle._decode(spec.name, column, value)  # names the table, never the value
    if isinstance(decoded, datetime) and decoded.tzinfo is None:
        raise ValueError(f"malformed {spec.name} row")  # a naive time fails at bind, echoing it
    return decoded


def _decode_row(spec: Table, raw: object) -> dict:
    columns = dict(jobs_bundle._columns(spec.model))
    if not isinstance(raw, dict) or set(raw) != set(columns):
        raise ValueError(f"malformed {spec.name} row")
    return {key: _decode_value(spec, columns[key], key, value) for key, value in raw.items()}


def _plain_name(slug: str) -> bool:
    """A slug names a file under the base-resumes root: no folders, nothing hidden."""
    return bool(slug) and Path(slug).name == slug and not slug.startswith(".")


def _is_profile_row(spec: Table, row: dict) -> bool:
    if spec.base_only:
        return row["resume_kind"] == "base"
    if spec.name == "base_resumes":
        return _plain_name(row["slug"])
    if spec.name == "settings":
        return isinstance(row["key"], str) and not row["key"].startswith(
            registry.LOCAL_SETTING_PREFIXES)
    return True


def _check_rows(rows: dict[str, list[dict]]) -> None:
    for spec in TABLES:
        seen = set()
        for row in rows[spec.name]:
            pk = row_pk(spec, row)
            if pk in seen or not _is_profile_row(spec, row):
                raise ValueError(f"{spec.name} row is not profile data")
            seen.add(pk)


def _check_files(entries: object) -> list:
    if not isinstance(entries, list):
        raise ValueError("files must be a list")
    prefixes = tuple(f"{root}:" for root in FILE_ROOTS)
    for entry in entries:
        path = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(path, str) or not path.startswith(prefixes):
            raise ValueError("file is outside the profile's roots")
    return entries


def _check_login(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"email", "password"}:
        raise ValueError("malformed job-site login")
    for item in value.values():
        if item is not None and not (isinstance(item, str) and bundle_rows.encodable(item)):
            raise ValueError("malformed job-site login")
    return value


def _check_rev(value: object) -> int:
    if (not isinstance(value, int) or isinstance(value, bool) or value < 0
            or not bundle_rows.fits_int64(value)):
        raise ValueError("malformed profile revision")
    return value


def _parse(bundle: object) -> Parsed:
    if not isinstance(bundle, dict) or not isinstance(bundle.get("rows"), list):
        raise ValueError("malformed bundle")
    try:
        rows = bundle_rows.decode_rows(bundle, _BY_NAME, _decode_row)
        _check_rows(rows)
        return Parsed(rows, _check_files(bundle["files"]), _check_login(bundle["job_site_login"]),
                      _check_rev(bundle["profile_rev"]))
    except (KeyError, TypeError, AttributeError):
        raise ValueError("malformed bundle") from None


# ---------------------------------------------------------------------------- apply


@dataclass
class Removed:
    """Settings the apply deleted here, for their mirror files."""

    keys: list[str]


def _load_existing(db: Session) -> dict[str, dict[tuple, Base]]:
    return {spec.name: {obj_pk(spec, obj): obj for obj in db.scalars(
        select(spec.model).where(*_filters(spec)))} for spec in TABLES}


def _apply_rows(db: Session, parsed: Parsed) -> Removed:
    existing = _load_existing(db)
    doomed = bundle_rows.missing(TABLES, existing, parsed.rows)
    removed = Removed([obj.key for obj in doomed["settings"]])
    # Deleting a career-history entity cascades, in the database, to the job-side kb_port_log rows
    # keyed to it on remote-owned jobs, without bumping those jobs' revs. That is fine: home's own
    # delete cascades the same rows off its replica, and a round pulls the profile before it pushes.
    bundle_rows.delete_rows(db, TABLES, doomed)
    for spec in TABLES:
        jobs_bundle._upsert(db, spec, existing[spec.name], parsed.rows[spec.name])
        # These models have no relationship() between them, so the unit of work does not order
        # their inserts by foreign key: flush each table before its children.
        db.flush()
    return removed


def _apply_login(login: dict | None) -> None:
    """Replace the receiver's login with home's: a half-filled one must not merge with an old one."""
    email, password = (login["email"], login["password"]) if login else (None, None)
    if email is None or password is None:
        job_site_login.clear()
    if email is not None or password is not None:
        job_site_login.write(email, password)


def _write_mirrors(db: Session, parsed: Parsed) -> None:
    """Rewrite each mirror file from its row, through the setting's service."""
    for row in parsed.rows["settings"]:
        if row["key"] in MIRRORS and row["value"] is not None:
            text_settings.set_text(row["key"], MIRRORS[row["key"]], row["value"], db)


def _db_files(db: Session) -> set[str]:
    """Every file the profile rows here point at, and each base resume's JSON."""
    found = set(db.scalars(select(models.KBDocument.file_path)))
    for slug, pdf, tex in db.execute(select(
            models.BaseResume.slug, models.BaseResume.pdf_path, models.BaseResume.tex_path)):
        found |= {str(base_resume_data.base_resume_path(slug)), pdf, tex}
    return {path for path in found if path}


def _bundle_files(parsed: Parsed) -> set[str]:
    """What the profile will point at after the apply, and the files arriving with it."""
    found = {row["file_path"] for row in parsed.rows["kb_documents"]}
    for row in parsed.rows["base_resumes"]:
        found |= {str(base_resume_data.base_resume_path(row["slug"])),
                  row["pdf_path"], row["tex_path"]}
    found |= {files.from_portable(entry["path"]) for entry in parsed.files}
    return {path for path in found if path}


def _inside_a_root(path: str) -> bool:
    try:
        portable = files.to_portable(path)
    except ValueError:
        return False
    return portable is not None and portable.startswith(tuple(f"{root}:" for root in FILE_ROOTS))


def _stale_files(before: set[str], kept: set[str]) -> list[Path]:
    """Files only a replaced row held (a removed base resume's JSON, PDF and TeX, a removed
    career document) or that a row no longer names. Never a file outside the profile's roots."""
    kept = {os.path.abspath(path) for path in kept}
    return [Path(path) for path in sorted(before)
            if os.path.abspath(path) not in kept and _inside_a_root(path)]


def _mirror_files(removed: list[str]) -> list[Path]:
    """The mirror of a setting this apply removed: a stale file would seed the row back."""
    return [Path(settings.settings_dir) / MIRRORS[key] for key in removed if key in MIRRORS]


def _require_clean(db: Session) -> None:
    """Pending changes would be flushed with the ownership guard off and committed with the apply."""
    if db.new or db.deleted or any(db.is_modified(obj) for obj in db.dirty):
        raise ValueError("commit or roll back pending changes before applying a profile")


def apply_profile(db: Session, bundle: dict, *, max_bytes: int = DEFAULT_MAX_BYTES) -> int:
    """Make this machine's profile equal the bundle and return the bundle's checked ``profile_rev``
    for the caller to store. Only the always-on copy may call it.

    One transaction under ``sync_apply``: rows, then files, then the login, then commit; any failure
    rolls the rows back. After the commit, files the replaced rows no longer name are removed
    (``inv-staged-artifact-removal``) and file mirrors are rewritten. Raises ValueError for a copy
    that is home, a session with pending changes, a malformed or hostile bundle, or one that
    conflicts with rows here (never with a value in the message).
    """
    if not status.is_remote():
        raise ValueError(REFUSED)
    _require_clean(db)
    parsed = _parse(bundle)
    before, kept = _db_files(db), _bundle_files(parsed)
    try:
        with jobs_bundle.applying(db):
            removed = _apply_rows(db, parsed)
            files.unpack(parsed.files, max_bytes=max_bytes)
            _apply_login(parsed.login)
    except IntegrityError:
        raise ValueError("bundle conflicts with rows already here") from None
    except (StatementError, TypeError):
        # SQLAlchemy's message would print the statement with its parameters.
        raise ValueError("malformed bundle") from None
    artifacts.remove_files(_stale_files(before, kept) + _mirror_files(removed.keys))
    with jobs_bundle.applying(db):
        _write_mirrors(db, parsed)
    return parsed.rev
