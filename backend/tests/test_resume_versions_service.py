from copy import deepcopy

from app.models.resume_version import ResumeVersion
from app.services.resume_versions import diff_versions, get_versions, record_version, restore

BASE = {
    "contact": {"name": "Sample", "email": "a@example.com"},
    "summary": "Original summary.",
    "skills": [
        {"category": "Languages", "items": ["Python"]},
        {"category": "Cloud", "items": ["AWS"]},
    ],
    "experience": [
        {
            "company": "Acme",
            "role": "DS",
            "start_date": "2020",
            "enabled": True,
            "bullets": ["Built pipeline.", "Shipped model."],
        }
    ],
    "projects": [{"name": "Proj", "enabled": True, "bullets": ["Did a thing."]}],
    "education": [{"institution": "Uni", "degree": "BS", "bullets": ["Graduated."]}],
    "certifications": [],
}


def test_record_version_appends_monotonic_numbers(db_session):
    v1 = record_version(db_session, "base", "test_slug", BASE, source="create")
    db_session.commit()
    changed = deepcopy(BASE)
    changed["summary"] = "New summary."
    v2 = record_version(db_session, "base", "test_slug", changed, source="form_edit")
    db_session.commit()

    assert (v1.version_number, v2.version_number) == (1, 2)
    assert v2.parent_version_id == v1.id
    assert v1.parent_version_id is None
    rows = get_versions(db_session, "base", "test_slug")
    assert [r.version_number for r in rows] == [2, 1]


def test_record_version_dedupes_identical_snapshot(db_session):
    v1 = record_version(db_session, "base", "test_slug", BASE, source="create")
    db_session.commit()
    again = record_version(db_session, "base", "test_slug", deepcopy(BASE), source="form_edit")
    db_session.commit()
    assert again.id == v1.id
    assert len(get_versions(db_session, "base", "test_slug")) == 1


def test_record_version_isolated_per_key_and_kind(db_session):
    record_version(db_session, "base", "a", BASE, source="create")
    v = record_version(db_session, "application", "a", BASE, source="create")
    db_session.commit()
    assert v.version_number == 1


def test_auto_summary_mentions_changed_entry(db_session):
    record_version(db_session, "base", "s", BASE, source="create")
    changed = deepcopy(BASE)
    changed["experience"][0]["bullets"][1] = "Deployed RAG service."
    v2 = record_version(db_session, "base", "s", changed, source="edit_ops")
    db_session.commit()
    assert "Acme" in v2.summary


def test_diff_versions_detects_modified_added_removed():
    new = deepcopy(BASE)
    new["summary"] = "New."
    new["experience"][0]["bullets"][0] = "Rewrote."
    new["projects"].append({"name": "P2", "enabled": True, "bullets": []})
    new["skills"] = [g for g in new["skills"] if g["category"] != "Cloud"]

    changes = diff_versions(BASE, new)
    by = {(c["section"], c["kind"]): c for c in changes}
    assert ("summary", "modified") in by
    assert by[("experience", "modified")]["label"] == "Acme — DS"
    assert by[("projects", "added")]["label"] == "P2"
    assert by[("skills", "removed")]["label"] == "Cloud"


def test_diff_versions_identical_is_empty():
    assert diff_versions(BASE, deepcopy(BASE)) == []


# --------------------------------------------------------------------------- #
# extra (custom) section diffs

AWARDS = {
    "key": "awards",
    "title": "Awards",
    "type": "bullets",
    "enabled": True,
    "bullets": ["First place, Example Competition, 2025"],
}
PUBS = {
    "key": "publications",
    "title": "Publications",
    "type": "entries",
    "enabled": True,
    "entries": [
        {
            "heading": "Paper A",
            "subheading": "NeurIPS",
            "date": "2025",
            "enabled": True,
            "bullets": ["Proposed a method."],
        }
    ],
}


def _with_extras(*sections):
    d = deepcopy(BASE)
    d["extra_sections"] = [deepcopy(s) for s in sections]
    return d


def _extra_changes(old, new):
    return [c for c in diff_versions(old, new) if c["section"] == "extra"]


def test_diff_detects_extra_section_added():
    changes = _extra_changes(deepcopy(BASE), _with_extras(AWARDS))
    assert changes == [{"section": "extra", "kind": "added", "label": "Awards"}]


def test_diff_detects_extra_section_removed():
    changes = _extra_changes(_with_extras(AWARDS), deepcopy(BASE))
    assert changes == [{"section": "extra", "kind": "removed", "label": "Awards"}]


def test_diff_detects_extra_section_rename_by_key():
    renamed = deepcopy(AWARDS)
    renamed["title"] = "Honors"  # same key, new title -> one modified line
    change = _extra_changes(_with_extras(AWARDS), _with_extras(renamed))[0]
    assert change["kind"] == "modified"
    assert change["label"] == "Honors"
    assert any("renamed from 'Awards'" in d for d in change["details"])


def test_diff_detects_extra_entry_count_change():
    grown = deepcopy(PUBS)
    grown["entries"].append(
        {"heading": "Paper B", "subheading": "ICML", "enabled": True, "bullets": []}
    )
    change = _extra_changes(_with_extras(PUBS), _with_extras(grown))[0]
    assert change["kind"] == "modified"
    assert any("Paper B" in d and "added" in d for d in change["details"])


def test_diff_detects_extra_entry_removed():
    change = _extra_changes(_with_extras(PUBS), _with_extras({**deepcopy(PUBS), "entries": []}))[0]
    assert any("Paper A" in d and "removed" in d for d in change["details"])


def test_diff_detects_extra_entry_bullet_rewrite():
    edited = deepcopy(PUBS)
    edited["entries"][0]["bullets"][0] = "Proposed a better method."
    change = _extra_changes(_with_extras(PUBS), _with_extras(edited))[0]
    assert any("Paper A" in d and "updated" in d for d in change["details"])


def test_diff_detects_extra_bullets_content_change():
    edited = deepcopy(AWARDS)
    edited["bullets"] = edited["bullets"] + ["Dean's list, 2024"]
    change = _extra_changes(_with_extras(AWARDS), _with_extras(edited))[0]
    assert change["kind"] == "modified"
    assert any("bullet 2 added" in d for d in change["details"])


def test_diff_detects_extra_section_reorder():
    changes = _extra_changes(_with_extras(AWARDS, PUBS), _with_extras(PUBS, AWARDS))
    assert any(c["label"] == "Section order" for c in changes)


def test_diff_missing_and_empty_extras_are_equivalent():
    new = deepcopy(BASE)
    new["extra_sections"] = []
    assert diff_versions(deepcopy(BASE), new) == []  # missing == empty -> no noise


def test_diff_disabled_extra_section_reported_as_modified():
    disabled = deepcopy(AWARDS)
    disabled["enabled"] = False
    change = _extra_changes(_with_extras(AWARDS), _with_extras(disabled))[0]
    assert change["kind"] == "modified"
    assert "disabled" in change["details"]


def test_extra_only_change_records_version_with_human_summary(db_session):
    record_version(db_session, "base", "xk", BASE, source="create")
    db_session.commit()
    v2 = record_version(db_session, "base", "xk", _with_extras(AWARDS), source="form_edit")
    db_session.commit()
    # Previously an extra-only change produced no diff; now it is a real version.
    assert v2.version_number == 2
    assert "Awards" in v2.summary and "extra" in v2.summary


def test_restore_returns_snapshot_and_appends_new_version(db_session):
    record_version(db_session, "base", "s", BASE, source="create")
    changed = deepcopy(BASE)
    changed["summary"] = "v2"
    record_version(db_session, "base", "s", changed, source="form_edit")
    db_session.commit()

    snapshot, version = restore(db_session, "base", "s", 1)
    db_session.commit()

    assert snapshot == BASE
    assert version.version_number == 3
    assert version.source == "restore"
    parent = db_session.get(ResumeVersion, version.parent_version_id)
    assert parent.version_number == 1
    # History is append-only: all three versions remain.
    assert len(get_versions(db_session, "base", "s")) == 3
