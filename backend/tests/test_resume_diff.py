"""Golden-file tests for the pure resume_diff service (Task 11)."""
from copy import deepcopy

from app.services import resume_diff


def _base():
    return {
        "contact": {"name": "Riley Quill", "email": "r@example.com"},
        "summary": "Original summary.",
        "skills": [{"category": "Core", "items": ["Python"]}],
        "experience": [],
        "projects": [
            {
                "name": "RAG Search",
                "enabled": False,
                "bullets": ["Built retrieval pipeline.", "Kept bullet."],
            }
        ],
        "education": [],
        "certifications": [],
        "extra_sections": [],
    }


def test_diff_reports_bullet_and_toggle_and_skills_changes():
    base = _base()
    customized = deepcopy(base)
    customized["projects"][0]["enabled"] = True
    customized["projects"][0]["bullets"] = [
        "Built retrieval + ranking pipeline.",
        "Kept bullet.",
        "Added Kafka consumer.",
    ]
    customized["skills"][0]["items"] = ["Python", "Kafka"]

    hunks = resume_diff.diff_resume(base, customized)
    kinds = {(h["kind"], h.get("section")) for h in hunks}
    assert ("entry_enabled", "projects") in kinds
    assert ("bullet_edited", "projects") in kinds
    assert ("bullet_added", "projects") in kinds
    assert ("skills_group_changed", "skills") in kinds


def test_attribution_joins_resolutions_else_llm():
    base = _base()
    customized = deepcopy(base)
    customized["projects"][0]["enabled"] = True
    customized["projects"][0]["bullets"] = [
        "Built retrieval + ranking pipeline.",
        "Kept bullet.",
    ]

    hunks = resume_diff.diff_resume(base, customized)
    resolutions = [
        {
            "gap_id": "skill:kafka",
            "action": "enable_entry",
            "payload": {
                "section": "projects",
                "index": 0,
                "provenance": {"source": "library_auto"},
            },
        }
    ]
    out = resume_diff.attribute(hunks, resolutions)
    enabled = next(h for h in out if h["kind"] == "entry_enabled")
    assert enabled["provenance"] == "kb_auto"  # library_auto/kb_auto/kb_profile → "kb_auto"
    edited = next(h for h in out if h["kind"] == "bullet_edited")
    assert edited["provenance"] == "llm"  # unattributable default


def test_diff_summary_contact_entry_and_extra_section_kinds():
    base = _base()
    customized = deepcopy(base)
    customized["summary"] = "Tailored summary."
    customized["contact"]["phone"] = "555-0100"
    customized["experience"] = [
        {
            "company": "Acme",
            "role": "DS",
            "start_date": "2024",
            "enabled": True,
            "bullets": ["Shipped model."],
        }
    ]
    # Drop the disabled project entirely.
    customized["projects"] = []
    customized["extra_sections"] = [
        {
            "key": "publications",
            "title": "Publications",
            "type": "bullets",
            "enabled": True,
            "bullets": ["Paper A"],
        }
    ]

    hunks = resume_diff.diff_resume(base, customized)
    kinds = {h["kind"] for h in hunks}
    assert "summary_changed" in kinds
    assert "contact_changed" in kinds
    assert "entry_added" in kinds
    assert "entry_removed" in kinds
    assert "extra_section_added" in kinds


def test_attribution_user_and_kb_profile_and_wording_match():
    base = _base()
    customized = deepcopy(base)
    customized["projects"][0]["enabled"] = True
    customized["projects"][0]["bullets"] = [
        "Built retrieval pipeline.",
        "Kept bullet.",
        "Ported: designed Kafka consumers for event pipelines.",
    ]
    customized["skills"][0]["items"] = ["Python", "Kafka"]

    hunks = resume_diff.diff_resume(base, customized)
    resolutions = [
        {
            "gap_id": "skill:kafka",
            "action": "port_kb_point",
            "payload": {
                "section": "projects",
                "index": 0,
                "text": "designed Kafka consumers for event pipelines",
                "provenance": {"source": "kb_profile"},
            },
        },
        {
            "gap_id": "skill:python",
            "action": "add_keyword",
            "payload": {
                "section": "skills",
                "index": 0,
                "keyword": "Kafka",
                "provenance": {"source": "user"},
            },
        },
    ]
    out = resume_diff.attribute(hunks, resolutions)
    added = next(h for h in out if h["kind"] == "bullet_added")
    assert added["provenance"] == "kb_auto"
    skills = next(h for h in out if h["kind"] == "skills_group_changed")
    assert skills["provenance"] == "user"
    enabled = next(h for h in out if h["kind"] == "entry_enabled")
    assert enabled["provenance"] == "llm"


def test_hunk_shape_fields():
    base = _base()
    customized = deepcopy(base)
    customized["summary"] = "New."
    hunks = resume_diff.diff_resume(base, customized)
    assert len(hunks) == 1
    hunk = hunks[0]
    assert set(hunk) >= {"kind", "section", "index", "before", "after", "provenance"}
    assert hunk["kind"] == "summary_changed"
    assert hunk["section"] == "summary"
    assert hunk["before"] == "Original summary."
    assert hunk["after"] == "New."
    assert hunk["provenance"] is None
