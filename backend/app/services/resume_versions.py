"""Append-only snapshot versioning for resume content.

Every write path (form saves, typed edit ops, chat tool calls, the tailor
pipeline, imports, restores) records a full-snapshot version through
`record_version`. Diffs are computed on read from snapshots — nothing is ever
reconstructed from patches. Restores append a new version on top; history is
never rewritten.
"""

from collections import defaultdict
from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.resume_version import ResumeVersion

VALID_KINDS = {"base", "application"}

# Sections whose entries are lists of dicts, with the fields that identify an
# entry across versions (used to pair old/new entries in diffs).
_ENTRY_SECTIONS: dict[str, tuple[str, ...]] = {
    "experience": ("company", "role"),
    "projects": ("name",),
    "education": ("institution", "degree"),
}


def latest_version(db: Session, kind: str, key: str) -> ResumeVersion | None:
    return db.scalars(
        select(ResumeVersion)
        .where(ResumeVersion.resume_kind == kind, ResumeVersion.resume_key == key)
        .order_by(ResumeVersion.version_number.desc())
        .limit(1)
    ).first()


def get_versions(db: Session, kind: str, key: str) -> list[ResumeVersion]:
    """All versions for a resume, newest first."""
    return list(
        db.scalars(
            select(ResumeVersion)
            .where(ResumeVersion.resume_kind == kind, ResumeVersion.resume_key == key)
            .order_by(ResumeVersion.version_number.desc())
        )
    )


def get_version(db: Session, kind: str, key: str, number: int) -> ResumeVersion | None:
    return db.scalars(
        select(ResumeVersion).where(
            ResumeVersion.resume_kind == kind,
            ResumeVersion.resume_key == key,
            ResumeVersion.version_number == number,
        )
    ).first()


def record_version(
    db: Session,
    kind: str,
    key: str,
    snapshot: dict[str, Any],
    *,
    source: str,
    summary: str | None = None,
    source_ref: str | None = None,
    parent_id: Any = None,
) -> ResumeVersion:
    """Append the next version; no-op (returns latest) if the snapshot is unchanged.

    Does not commit — the caller owns the transaction, so the version lands
    atomically with the resume write it describes.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"invalid resume kind {kind!r}")
    latest = latest_version(db, kind, key)
    if latest is not None and latest.snapshot == snapshot:
        return latest

    if summary is None:
        changes = diff_versions(latest.snapshot if latest else None, snapshot)
        summary = summarize_changes(changes)

    row = ResumeVersion(
        resume_kind=kind,
        resume_key=key,
        version_number=(latest.version_number + 1) if latest else 1,
        parent_version_id=parent_id if parent_id is not None else (latest.id if latest else None),
        snapshot=deepcopy(snapshot),
        summary=summary,
        source=source,
        source_ref=source_ref,
    )
    db.add(row)
    db.flush()
    return row


def restore(db: Session, kind: str, key: str, number: int) -> tuple[dict[str, Any], ResumeVersion]:
    """Return the snapshot of version `number` and append a restore version.

    The caller persists the snapshot into the live row (and re-renders); this
    function only manages history. Append-only: nothing is deleted.
    """
    target = get_version(db, kind, key, number)
    if target is None:
        raise LookupError(f"version {number} not found for {kind}/{key}")
    snapshot = deepcopy(target.snapshot)
    version = record_version(
        db,
        kind,
        key,
        snapshot,
        source="restore",
        summary=f"Restored version {number}",
        parent_id=target.id,
    )
    return snapshot, version


# ---------------------------------------------------------------------------
# Structural diff


def _entry_label(section: str, entry: dict[str, Any]) -> str:
    parts = [str(entry.get(f, "")).strip() for f in _ENTRY_SECTIONS[section]]
    return " — ".join(p for p in parts if p) or "(untitled)"


def _entry_identity(section: str, entry: dict[str, Any]) -> tuple:
    return tuple(str(entry.get(f, "")).casefold() for f in _ENTRY_SECTIONS[section])


def _bullet_details(old: list, new: list) -> list[str]:
    details = []
    for i in range(max(len(old), len(new))):
        if i >= len(old):
            details.append(f"bullet {i + 1} added")
        elif i >= len(new):
            details.append(f"bullet {i + 1} removed")
        elif old[i] != new[i]:
            details.append(f"bullet {i + 1} rewritten")
    return details


def _diff_entries(section: str, old: list, new: list, changes: list[dict[str, Any]]) -> None:
    old_by_id: dict[tuple, dict] = {}
    for e in old:
        old_by_id.setdefault(_entry_identity(section, e), e)
    matched_old_ids: set[tuple] = set()

    for entry in new:
        ident = _entry_identity(section, entry)
        prev = old_by_id.get(ident)
        if prev is None or ident in matched_old_ids:
            changes.append(
                {"section": section, "kind": "added", "label": _entry_label(section, entry)}
            )
            continue
        matched_old_ids.add(ident)
        if prev == entry:
            continue
        details = _bullet_details(prev.get("bullets") or [], entry.get("bullets") or [])
        prev_rest = {k: v for k, v in prev.items() if k != "bullets"}
        new_rest = {k: v for k, v in entry.items() if k != "bullets"}
        if prev_rest != new_rest:
            changed_fields = sorted(
                k
                for k in set(prev_rest) | set(new_rest)
                if prev_rest.get(k) != new_rest.get(k)
            )
            details.append("changed " + ", ".join(changed_fields))
        changes.append(
            {
                "section": section,
                "kind": "modified",
                "label": _entry_label(section, entry),
                "details": details,
            }
        )

    for ident, prev in old_by_id.items():
        if ident not in matched_old_ids:
            changes.append(
                {"section": section, "kind": "removed", "label": _entry_label(section, prev)}
            )


# --- extra (custom) sections ------------------------------------------------
#
# Custom sections are paired by their stable `key` (never title or list order),
# so a rename is one `modified` line with a "renamed from …" detail, not a
# remove+add. The human `title` drives the display label; the key drives
# identity. Missing and empty `extra_sections` are equivalent (an old core-only
# snapshot vs. a normalized one that added `[]`) and produce no change — this is
# the upgrade-noise suppression the design calls for. Entries inside an
# `entries` section are paired without collapsing duplicates so an added/removed
# duplicate is reported rather than hidden. `kind` stays within
# added|removed|modified so the generic frontend diff renderer needs no change.

_EXTRA_ENTRY_ID_FIELDS = ("heading", "subheading")


def _extra_section_title(section: dict[str, Any]) -> str:
    return str(section.get("title") or section.get("key") or "").strip() or "(untitled)"


def _extra_entry_label(entry: dict[str, Any]) -> str:
    parts = [str(entry.get(f, "")).strip() for f in _EXTRA_ENTRY_ID_FIELDS]
    return " — ".join(p for p in parts if p) or "(untitled)"


def _extra_entry_identity(entry: dict[str, Any]) -> tuple:
    return tuple(str(entry.get(f, "")).casefold() for f in _EXTRA_ENTRY_ID_FIELDS)


def _extra_entry_field_changes(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    details = _bullet_details(old.get("bullets") or [], new.get("bullets") or [])
    old_rest = {k: v for k, v in old.items() if k != "bullets"}
    new_rest = {k: v for k, v in new.items() if k != "bullets"}
    if old_rest != new_rest:
        changed = sorted(
            k for k in set(old_rest) | set(new_rest) if old_rest.get(k) != new_rest.get(k)
        )
        details.append("changed " + ", ".join(changed))
    return details


def _diff_extra_entries(old_entries: list, new_entries: list) -> list[str]:
    """Detail lines for entry add/remove/modify in an ``entries`` section.

    Pairs by (heading, subheading) identity using per-identity buckets so two
    entries that share a heading are matched one-for-one, not collapsed.
    """
    details: list[str] = []
    remaining: dict[tuple, list[dict]] = defaultdict(list)
    for entry in old_entries:
        if isinstance(entry, dict):
            remaining[_extra_entry_identity(entry)].append(entry)
    for entry in new_entries:
        if not isinstance(entry, dict):
            continue
        bucket = remaining.get(_extra_entry_identity(entry))
        if bucket:
            prev = bucket.pop(0)
            if prev != entry:
                sub = _extra_entry_field_changes(prev, entry)
                suffix = f" ({'; '.join(sub)})" if sub else ""
                details.append(f"entry '{_extra_entry_label(entry)}' updated{suffix}")
        else:
            details.append(f"entry '{_extra_entry_label(entry)}' added")
    for bucket in remaining.values():
        for prev in bucket:
            details.append(f"entry '{_extra_entry_label(prev)}' removed")
    return details


def _diff_one_extra_section(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Detail lines for a section present in both versions (matched by key)."""
    details: list[str] = []
    old_title, new_title = _extra_section_title(old), _extra_section_title(new)
    if old_title != new_title:
        details.append(f"renamed from '{old_title}'")
    old_enabled = old.get("enabled", True) is not False
    new_enabled = new.get("enabled", True) is not False
    if old_enabled != new_enabled:
        details.append("enabled" if new_enabled else "disabled")
    old_type, new_type = old.get("type"), new.get("type")
    if old_type != new_type:
        details.append(f"changed type from '{old_type}' to '{new_type}'")
    elif new_type == "bullets":
        details.extend(_bullet_details(old.get("bullets") or [], new.get("bullets") or []))
    else:  # entries (the default discriminator)
        details.extend(_diff_extra_entries(old.get("entries") or [], new.get("entries") or []))
    if not details:
        details.append("updated")
    return details


def _diff_extra_sections(old_sections, new_sections, changes: list[dict[str, Any]]) -> None:
    old_list = [s for s in (old_sections or []) if isinstance(s, dict)]
    new_list = [s for s in (new_sections or []) if isinstance(s, dict)]
    if not old_list and not new_list:
        return

    old_by_key: dict[str, dict] = {}
    for s in old_list:
        old_by_key.setdefault(str(s.get("key", "")), s)
    new_by_key: dict[str, dict] = {}
    for s in new_list:
        new_by_key.setdefault(str(s.get("key", "")), s)

    for s in new_list:
        if str(s.get("key", "")) not in old_by_key:
            changes.append(
                {"section": "extra", "kind": "added", "label": _extra_section_title(s)}
            )
    for s in old_list:
        if str(s.get("key", "")) not in new_by_key:
            changes.append(
                {"section": "extra", "kind": "removed", "label": _extra_section_title(s)}
            )
    for s in new_list:
        prev = old_by_key.get(str(s.get("key", "")))
        if prev is None or prev == s:
            continue
        changes.append(
            {
                "section": "extra",
                "kind": "modified",
                "label": _extra_section_title(s),
                "details": _diff_one_extra_section(prev, s),
            }
        )
    # A pure reorder of sections present in both versions (add/remove don't
    # trigger this — only common keys' relative order is compared).
    common_old = [k for s in old_list if (k := str(s.get("key", ""))) in new_by_key]
    common_new = [k for s in new_list if (k := str(s.get("key", ""))) in old_by_key]
    if len(common_old) > 1 and common_old != common_new:
        changes.append(
            {
                "section": "extra",
                "kind": "modified",
                "label": "Section order",
                "details": ["reordered custom sections"],
            }
        )


def diff_versions(
    old: dict[str, Any] | None, new: dict[str, Any]
) -> list[dict[str, Any]]:
    """Section/item-level structural diff between two ResumeData dicts.

    Each change: {section, kind: added|removed|modified, label, details?: [str]}.
    `old=None` (first version) yields a single 'created' change.
    """
    if old is None:
        return [{"section": "resume", "kind": "added", "label": "Initial version"}]
    changes: list[dict[str, Any]] = []

    if old.get("summary") != new.get("summary"):
        changes.append({"section": "summary", "kind": "modified", "label": "Summary"})
    if old.get("contact") != new.get("contact"):
        changes.append({"section": "contact", "kind": "modified", "label": "Contact"})

    old_groups = {str(g.get("category", "")): g for g in old.get("skills") or []}
    new_groups = {str(g.get("category", "")): g for g in new.get("skills") or []}
    for cat, group in new_groups.items():
        if cat not in old_groups:
            changes.append({"section": "skills", "kind": "added", "label": cat})
        elif old_groups[cat] != group:
            changes.append({"section": "skills", "kind": "modified", "label": cat})
    for cat in old_groups:
        if cat not in new_groups:
            changes.append({"section": "skills", "kind": "removed", "label": cat})

    for section in _ENTRY_SECTIONS:
        _diff_entries(section, old.get(section) or [], new.get(section) or [], changes)

    if (old.get("certifications") or []) != (new.get("certifications") or []):
        changes.append(
            {"section": "certifications", "kind": "modified", "label": "Certifications"}
        )

    _diff_extra_sections(old.get("extra_sections"), new.get("extra_sections"), changes)

    return changes


def summarize_changes(changes: list[dict[str, Any]]) -> str:
    if not changes:
        return "No content changes"
    verbs = {"added": "Added", "removed": "Removed", "modified": "Updated"}
    parts = [f"{verbs[c['kind']]} {c['section']} · {c['label']}" for c in changes[:4]]
    if len(changes) > 4:
        parts.append(f"+{len(changes) - 4} more")
    return "; ".join(parts)
