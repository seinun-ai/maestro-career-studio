"""One job as a bundle: export it, apply it onto another database (split-ownership design, Part B).

A bundle is JSON: this job's rows per table, its files (base64, paths relative to a root), and the
sender's ``owner``, ``sync_rev`` and ``handover`` as fields. Ownership, revisions and handovers are
never row data: the receiver sets ``owner_machine`` to the sender and stamps its own clock.

Applying is upsert by primary key, then delete what the bundle no longer lists inside this job's
subtree, including the rows keyed by an application's id with no foreign key (``by_kind`` tables).
The whole bundle is validated before the first write, and nothing here logs or echoes row or file
contents: errors name a table or a column, never a value.
"""

import json
import math
import os
import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import delete, inspect, or_, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app import models
from app.db import Base
from app.models.sync import SyncTombstone
from app.services.sync import bundle_rows, files, folders, hooks, status
from app.services.sync.bundle_rows import obj_pk, row_pk

DEFAULT_MAX_BYTES = 25 * 1024 * 1024
_APPLICATIONS = "applications:"
_JOB_COLUMNS_NOT_DATA = ("owner_machine", "sync_rev", "handover")


class DuplicateJob(Exception):
    """The bundle's job text already belongs to a different local job (Task 10 decides what to do)."""

    def __init__(self, local_id: uuid.UUID):
        super().__init__("a different local job already holds this job's text")
        self.local_id = local_id


@dataclass(frozen=True)
class Table:
    """How one table hangs off a job. ``link`` is the column that ties a row to the job subtree and
    ``scope`` names the set of ids it must fall in: the job, its applications, its proposals, or
    its applications' ids as text (``by_kind`` rows, which have no foreign key)."""

    name: str
    model: type[Base]
    link: str
    scope: str
    by_kind: bool = False
    paths: tuple[str, ...] = ()
    hidden: tuple[str, ...] = ()
    order: str | None = None


# Parents before children: the order rows are written in; deletes run in reverse.
TABLES: tuple[Table, ...] = (
    Table("jobs", models.Job, "id", "job", hidden=_JOB_COLUMNS_NOT_DATA),
    Table("job_skills", models.JobSkill, "job_id", "job"),
    Table("applications", models.Application, "job_id", "job",
          paths=("artifact_dir", "pdf_path", "tex_path")),
    Table("application_proposals", models.ApplicationProposal, "job_id", "job"),
    Table("consent_events", models.ConsentEvent, "proposal_id", "proposal"),
    Table("ats_scores", models.AtsScore, "job_id", "job"),
    Table("tailoring_sessions", models.TailoringSession, "job_id", "job"),
    Table("qa_entries", models.QAEntry, "application_id", "app", paths=("pdf_path",)),
    Table("filled_answers", models.FilledAnswer, "job_id", "job"),
    Table("resume_versions", models.ResumeVersion, "resume_key", "key", by_kind=True,
          order="version_number"),
    Table("resume_lint_reports", models.ResumeLintReport, "resume_key", "key", by_kind=True),
    Table("health_ask_answers", models.HealthAskAnswer, "resume_key", "key", by_kind=True),
    Table("health_gate_waivers", models.HealthGateWaiver, "resume_key", "key", by_kind=True),
    Table("kb_port_log", models.KBPortLog, "resume_key", "key", by_kind=True),
)
_BY_NAME = {spec.name: spec for spec in TABLES}


@dataclass
class Scope:
    """The ids that make up one job's subtree."""

    job_id: uuid.UUID
    apps: set
    proposals: set

    def members(self, kind: str) -> set:
        if kind == "job":
            return {self.job_id}
        if kind == "app":
            return self.apps
        if kind == "proposal":
            return self.proposals
        return {str(app_id) for app_id in self.apps}

    def clause(self, spec: Table):
        clause = getattr(spec.model, spec.link).in_(list(self.members(spec.scope)))
        if spec.by_kind:
            clause = sa.and_(clause, spec.model.resume_kind == "application")
        return clause


def _db_scope(db: Session, job_id: uuid.UUID) -> Scope:
    apps = set(db.scalars(select(models.Application.id).where(models.Application.job_id == job_id)))
    proposals = set(db.scalars(select(models.ApplicationProposal.id).where(
        models.ApplicationProposal.job_id == job_id)))
    return Scope(job_id, apps, proposals)


def _columns(model: type[Base]) -> list[tuple[str, sa.Column]]:
    return [(prop.key, prop.columns[0]) for prop in inspect(model).column_attrs]


# ---------------------------------------------------------------------------- encoding


def _encode(value):
    if isinstance(value, uuid.UUID):
        return value.hex
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _base_type(column: sa.Column):
    return getattr(column.type, "impl", column.type)  # a TypeDecorator names its base type


def _accepts(kind, value) -> bool:
    """Whether a JSON scalar has the shape this column stores. A bool is an int in Python, so it is
    named first and kept out of every other kind. A value the database cannot hold (an int past 64
    bits, a lone surrogate) is refused here, before it fails at bind with the value in the error."""
    if isinstance(kind, sa.JSON):
        return True
    if isinstance(kind, sa.Boolean):
        return isinstance(value, bool)
    if isinstance(value, bool):
        return False
    if isinstance(kind, sa.Numeric) and not kind.asdecimal:
        return _finite(value)
    if isinstance(kind, sa.Integer):
        return isinstance(value, int) and bundle_rows.fits_int64(value)
    return (isinstance(kind, sa.String | sa.DateTime | sa.Uuid | sa.Numeric)
            and isinstance(value, str) and bundle_rows.encodable(value))


def _finite(value) -> bool:
    try:
        return isinstance(value, int | float) and math.isfinite(value)
    except OverflowError:  # an int too big for a float
        return False


def _convert(kind, value):
    if isinstance(kind, sa.Uuid):
        return uuid.UUID(value)
    if isinstance(kind, sa.DateTime):
        return datetime.fromisoformat(value)
    if isinstance(kind, sa.Numeric) and kind.asdecimal:
        number = Decimal(value)
        if not math.isfinite(float(number)):  # a database stores it as a float: 1E+999999999 is inf
            raise ValueError
        return number
    return value


def _decode(table: str, column: sa.Column, value):
    """The column's Python value; a value of the wrong shape or one that will not convert raises a
    ValueError that names the table and never the value."""
    if value is None and column.nullable:
        return None
    kind = _base_type(column)
    try:
        if value is None or not _accepts(kind, value):
            raise ValueError
        return _convert(kind, value)
    except (ValueError, ArithmeticError):
        raise ValueError(f"malformed {table} row") from None


def _is_json(column: sa.Column) -> bool:
    return isinstance(column.type, sa.JSON)


# ---------------------------------------------------------------------------- export


def _export_row(spec: Table, obj: Base) -> dict:
    row = {}
    for key, _ in _columns(spec.model):
        if key in spec.hidden:
            continue
        value = getattr(obj, key)
        row[key] = files.to_portable(value) if key in spec.paths else _encode(value)
    return {"table": spec.name, "row": row}


def _export_rows(db: Session, scope: Scope) -> list[dict]:
    return bundle_rows.export_rows(db, TABLES, lambda spec: [scope.clause(spec)], _export_row)


def _artifact_dirs(rows: list[dict]) -> list[str]:
    """Folders (relative to the applications root) to pack; a folder inside another is skipped."""
    found = {item["row"]["artifact_dir"][len(_APPLICATIONS):] for item in rows
             if item["table"] == "applications"
             and (item["row"]["artifact_dir"] or "").startswith(_APPLICATIONS)}
    return sorted(rel for rel in found if not any(rel.startswith(other + "/") for other in found))


def _pack(dirs: list[str], max_bytes: int) -> tuple[list[dict], int]:
    packed: list[dict] = []
    skipped = 0
    remaining = max_bytes
    for rel in dirs:
        entries, left_out = files.pack_dir_with_skips("applications", rel, max_bytes=remaining)
        entries = [entry for entry in entries if not entry["path"].lower().endswith(bundle_rows.LATEX_LEFTOVERS)]
        packed.extend(entries)
        skipped += left_out
        remaining -= sum(bundle_rows.decoded_size(entry) for entry in entries)
    return packed, skipped


def export_job(db: Session, job_id: uuid.UUID, *, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    """The job, its subtree, its files and who owns it, JSON-safe. Raises LookupError, or
    ValueError over ``max_bytes`` or a symlink."""
    job = db.get(models.Job, job_id)
    if job is None:
        raise LookupError("unknown job")
    rows = _export_rows(db, _db_scope(db, job_id))
    packed, skipped = _pack(_artifact_dirs(rows), max_bytes)
    return {
        "job_id": job_id.hex,
        "owner": job.owner_machine or status.machine_id(db),
        "sync_rev": job.sync_rev,
        "handover": job.handover,
        "rows": rows,
        "files": packed,
        "files_skipped": skipped,
    }


# ---------------------------------------------------------------------------- parse and validate


@dataclass
class Parsed:
    job_id: uuid.UUID
    rows: dict[str, list[dict]] = field(repr=False)  # row values and file bytes never print
    files: list = field(repr=False)
    dirs: tuple[str, ...]


def _decode_value(spec: Table, column: sa.Column, key: str, value):
    if key not in spec.paths:
        return _decode(spec.name, column, value)
    if value is not None and not (isinstance(value, str) and value.startswith(_APPLICATIONS)):
        raise ValueError(f"{spec.name} path is outside the applications root")
    return files.from_portable(value)


def _decode_row(spec: Table, raw: object) -> dict:
    columns = dict(_columns(spec.model))
    expected = set(columns) - set(spec.hidden)
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError(f"malformed {spec.name} row")
    return {key: _decode_value(spec, columns[key], key, value) for key, value in raw.items()}


def _check_links(job_id: uuid.UUID, rows: dict[str, list[dict]]) -> None:
    if len(rows["jobs"]) != 1 or rows["jobs"][0]["id"] != job_id:
        raise ValueError("bundle must hold exactly its own job")
    scope = Scope(job_id, {row["id"] for row in rows["applications"]},
                  {row["id"] for row in rows["application_proposals"]})
    for spec in TABLES:
        allowed = scope.members(spec.scope)
        for row in rows[spec.name]:
            if row[spec.link] not in allowed or (spec.by_kind and row["resume_kind"] != "application"):
                raise ValueError(f"{spec.name} row is outside the job")


def _check_own_folders(rows: dict[str, list[dict]]) -> None:
    """A path under the applications root is not enough: each row's file sits in its own folder."""
    apps = {row["id"]: row for row in rows["applications"]}
    inside = [(row["artifact_dir"], row[key]) for row in rows["applications"]
              for key in ("pdf_path", "tex_path")]
    inside += [(apps[row["application_id"]]["artifact_dir"], row["pdf_path"])
               for row in rows["qa_entries"]]
    # a legacy row without a folder has nothing to sit in; _check_artifact_folders still guards it
    if any(path and folder and not folders.lies_below(path, folder) for folder, path in inside):
        raise ValueError("a file path is outside its application's folder")


def _artifact_prefixes(bundle: dict) -> tuple[str, ...]:
    prefixes = []
    for item in bundle["rows"]:
        value = item["row"].get("artifact_dir") if item["table"] == "applications" else None
        if value:
            prefixes.append(value + "/")
    return tuple(prefixes)


def _check_files(entries: object, prefixes: tuple[str, ...]) -> list:
    if not isinstance(entries, list):
        raise ValueError("files must be a list")
    for entry in entries:
        path = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(path, str) or not path.startswith(prefixes):
            raise ValueError("file is outside the job's artifact folders")
    return entries


def _parse(bundle: object) -> Parsed:
    if not isinstance(bundle, dict) or not isinstance(bundle.get("rows"), list):
        raise ValueError("malformed bundle")
    try:
        job_id = uuid.UUID(bundle["job_id"])
        rows = bundle_rows.decode_rows(bundle, _BY_NAME, _decode_row)
        _check_links(job_id, rows)
        _check_own_folders(rows)
        prefixes = _artifact_prefixes(bundle)
        return Parsed(job_id, rows, _check_files(bundle.get("files", []), prefixes), prefixes)
    except (KeyError, TypeError, AttributeError):
        raise ValueError("malformed bundle") from None


# ---------------------------------------------------------------------------- apply


def _check_duplicate(db: Session, parsed: Parsed) -> None:
    text_hash = parsed.rows["jobs"][0]["raw_text_hash"]
    local = db.scalar(select(models.Job.id).where(
        models.Job.raw_text_hash == text_hash, models.Job.id != parsed.job_id))
    if local is not None:
        raise DuplicateJob(local)


def _parents(*paths: str | None) -> list[str]:
    return [os.path.dirname(path) for path in paths if path]


def _claimed_folders(rows: dict[str, list[dict]]) -> list[str]:
    """The folders this job's rows write into: each application's own, or, for a legacy row that
    never recorded one, the folders its file paths sit in."""
    apps = {row["id"]: row for row in rows["applications"]}
    claimed: list[str] = []
    for row in rows["applications"]:
        claimed += [row["artifact_dir"]] if row["artifact_dir"] else _parents(row["pdf_path"], row["tex_path"])
    for row in rows["qa_entries"]:
        if not apps[row["application_id"]]["artifact_dir"]:
            claimed += _parents(row["pdf_path"])
    return claimed


def _check_artifact_folders(db: Session, parsed: Parsed) -> None:
    """A bundle's folders may not equal, contain or sit inside the folder of an application that is
    not part of this job (compared as the disk does, see ``folders``): files are written there,
    and they would overwrite another job's."""
    ours = _claimed_folders(parsed.rows)
    if not ours:
        return
    others = (value for value in db.scalars(
        select(models.Application.artifact_dir).where(
            models.Application.artifact_dir.is_not(None),
            models.Application.job_id != parsed.job_id)) if value)
    if any(folders.overlaps(first, other) for other in others for first in ours):
        raise ValueError("artifact folder belongs to another job")


def _receiver_scope(db: Session, parsed: Parsed) -> Scope:
    """Existing and incoming ids together: rows of an application that is going away still count."""
    scope = _db_scope(db, parsed.job_id)
    scope.apps |= {row["id"] for row in parsed.rows["applications"]}
    scope.proposals |= {row["id"] for row in parsed.rows["application_proposals"]}
    return scope


def _load_existing(db: Session, scope: Scope) -> dict[str, dict[tuple, Base]]:
    return {spec.name: {obj_pk(spec, obj): obj for obj in db.scalars(
        select(spec.model).where(scope.clause(spec)))} for spec in TABLES}


def _existing_ids(db: Session, model: type[Base], wanted: set) -> set:
    if not wanted:
        return set()
    return set(db.scalars(select(model.id).where(model.id.in_(list(wanted)))))


def _localize(db: Session, parsed: Parsed) -> None:
    """Make the incoming rows fit this machine's profile: a referral it lacks becomes NULL, a port
    log row whose career-history entry it lacks is skipped, a missing point is unlinked."""
    for name in ("applications", "application_proposals"):
        wanted = {row["referral_id"] for row in parsed.rows[name] if row["referral_id"]}
        present = _existing_ids(db, models.Referral, wanted)
        for row in parsed.rows[name]:
            if row["referral_id"] not in present:
                row["referral_id"] = None
    ports = parsed.rows["kb_port_log"]
    entities = _existing_ids(db, models.KBEntity, {row["entity_id"] for row in ports})
    points = _existing_ids(db, models.KBPoint, {row["point_id"] for row in ports if row["point_id"]})
    parsed.rows["kb_port_log"] = [row for row in ports if row["entity_id"] in entities]
    for row in parsed.rows["kb_port_log"]:
        if row["point_id"] not in points:
            row["point_id"] = None


def _value_for(column: sa.Column, value):
    # A JSON column would store Python None as the JSON text "null"; keep SQL NULL.
    return sa.null() if value is None and _is_json(column) else value


def _fill_new(spec: Table, row: dict) -> Base:
    columns = dict(_columns(spec.model))
    values = {key: _value_for(columns[key], value) for key, value in row.items()
              if value is not None or _is_json(columns[key])}
    return spec.model(**values)


def _fill_existing(spec: Table, obj: Base, row: dict, db: Session) -> None:
    columns = dict(_columns(spec.model))
    for key, value in row.items():
        if getattr(obj, key) != value:
            setattr(obj, key, _value_for(columns[key], value))
    if db.is_modified(obj):
        # An onupdate column (updated_at) must keep the sender's value, not this machine's clock.
        for key, column in columns.items():
            if column.onupdate is not None:
                flag_modified(obj, key)


def _upsert(db: Session, spec: Table, existing: dict, rows: list[dict]) -> list[Base]:
    if spec.order:
        rows = sorted(rows, key=lambda row: row[spec.order])
    objects = []
    for row in rows:
        obj = existing.get(row_pk(spec, row))
        if obj is None:
            obj = _fill_new(spec, row)
            db.add(obj)
        else:
            _fill_existing(spec, obj, row, db)
        objects.append(obj)
    return objects


def _apply_rows(db: Session, parsed: Parsed, sender_machine: str) -> list[str]:
    """Write the bundle's rows; returns the artifact folders of the applications it deleted."""
    _check_duplicate(db, parsed)
    _localize(db, parsed)
    existing = _load_existing(db, _receiver_scope(db, parsed))
    doomed = bundle_rows.missing(TABLES, existing, parsed.rows)
    dirs = [obj.artifact_dir for obj in doomed["applications"] if obj.artifact_dir]
    bundle_rows.delete_rows(db, TABLES, doomed)
    # The session's identity map is weak: hold every row until the end, or the hook's per-row job
    # lookup (session.get on the parent) would reload each collected parent from the database.
    held: list[Base] = []
    for spec in TABLES:
        objects = _upsert(db, spec, existing[spec.name], parsed.rows[spec.name])
        held.extend(objects)
        if spec.name == "jobs":
            objects[0].owner_machine = sender_machine
        # These models have no relationship() between them, so the unit of work does not order
        # their inserts by foreign key: flush each table before its children.
        db.flush()
    return dirs


@contextmanager
def applying(db: Session) -> Iterator[None]:
    """One transaction under ``hooks.standing_aside`` (the ownership guard stands aside); any
    failure rolls back and the flag is restored."""
    try:
        db.flush()  # whatever the caller left pending meets the guard before it stands aside
        with hooks.standing_aside(db):
            yield
            db.commit()
    except BaseException:
        db.rollback()
        raise


def weight(bundle: dict) -> int:
    """About how many bytes a bundle adds to a request: its files, base64, and its rows."""
    return sum(len(entry["b64"]) for entry in bundle["files"]) + len(json.dumps(bundle["rows"]))


def owned_clause(db: Session):
    """The jobs this copy owns: unowned, or owned by this machine."""
    return or_(models.Job.owner_machine.is_(None),
               models.Job.owner_machine == status.machine_id(db))


def apply_job(db: Session, bundle: dict, *, sender_machine: str,
              max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    """Make this machine's copy of the job equal the bundle, owned by ``sender_machine``.

    One transaction: rows, then files, then commit; any failure rolls the rows back. Raises
    DuplicateJob on a text clash and ValueError for a bundle that is malformed, reaches outside the
    job or conflicts with another job's rows (never with row contents in the message).
    """
    parsed = _parse(bundle)
    _check_artifact_folders(db, parsed)
    try:
        with applying(db):
            dirs = _apply_rows(db, parsed, sender_machine)
            files.unpack(parsed.files, max_bytes=max_bytes)
    except IntegrityError:
        raise ValueError("bundle conflicts with rows already here") from None
    except (StatementError, TypeError):
        raise ValueError("bundle could not be applied") from None
    for path in _unused_folders(db, dirs):  # staged: only after the commit that dropped the rows
        _remove_folder(path)


# ---------------------------------------------------------------------------- tombstone


def _unused_folders(db: Session, folders_gone: list[str]) -> list[str]:
    """Those of ``folders_gone`` that no remaining application's folder is, lies inside or contains."""
    if not folders_gone:
        return []
    kept = [value for value in db.scalars(select(models.Application.artifact_dir)
            .where(models.Application.artifact_dir.is_not(None))) if value]
    return [path for path in dict.fromkeys(folders_gone)
            if not any(folders.overlaps(path, other) for other in kept)]


def _remove_folder(path: str) -> None:
    try:
        portable = files.to_portable(path)
    except ValueError:
        return
    if portable is not None and portable.startswith(_APPLICATIONS):
        shutil.rmtree(path, ignore_errors=True)


def apply_tombstone(db: Session, job_id: uuid.UUID) -> None:
    """Delete a replica, its whole subtree and its artifact folders. No tombstone is left here:
    the owner already announced the deletion."""
    dirs = [value for value in db.scalars(select(models.Application.artifact_dir).where(
        models.Application.job_id == job_id)) if value]
    with applying(db):
        scope = _db_scope(db, job_id)
        bundle_rows.delete_rows(db, TABLES, {
            spec.name: list(db.scalars(select(spec.model).where(scope.clause(spec))))
            for spec in TABLES})
        db.execute(delete(SyncTombstone).where(SyncTombstone.job_id == job_id))
    for path in _unused_folders(db, dirs):
        _remove_folder(path)
