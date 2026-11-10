"""The base-to-tailored diff the frontend's Undo and Redo test replays
(frontend/components/resume-editor/diff-review.test.mjs): tests/fixtures/resume_diff/review-changes.json
holds a base resume, its tailored copy and exactly the hunks GET /applications/{id}/resume-diff
would serve for the pair (`resume_diff.diff_resume`, attributed with no session). A change to the
diff that alters a hunk fails here. To regenerate, from backend/:

    MAESTRO_RESUME_DIFF_WRITE=1 .venv/bin/python -m pytest tests/test_resume_diff_fixture.py

then rerun without the variable and commit the file.

The pair holds every kind of hunk, three siblings wherever a list grows or shrinks (so every order
of undoing and redoing them is a case), and one entry that is both hidden and reworded (the two
rows whose places overlap).
"""

import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

from app.schemas.resume import ResumeData
from app.services import resume_diff

FIXTURE = Path(__file__).parent / "fixtures" / "resume_diff" / "review-changes.json"
REGENERATE = (
    "regenerate from backend/ with MAESTRO_RESUME_DIFF_WRITE=1 .venv/bin/python -m pytest "
    "tests/test_resume_diff_fixture.py, rerun without it, and commit the file"
)

BASE = {
    "contact": {"name": "Sam Rivera", "email": "sam.rivera@example.com", "location": "Lisbon, Portugal"},
    "summary": "Operations coordinator with five years in warehouse logistics.",
    "skills": [
        {"category": "Planning", "items": ["Route planning", "Forecasting"]},
        {"category": "Tools", "items": ["Spreadsheets", "Stock software"]},
    ],
    "experience": [
        {
            "company": "Harbor Freight Co-op",
            "role": "Operations Coordinator",
            "start_date": "2021-03",
            "bullets": ["Scheduled 40 weekly deliveries across three depots.", "Trained six new dispatchers."],
        },
        {
            "company": "Northside Market",
            "role": "Stock Assistant",
            "start_date": "2018-06",
            "end_date": "2021-02",
            "bullets": [
                "Counted stock each week.",
                "Reported shortages to the floor manager.",
                "Kept the loading bay clear.",
                "Closed the stockroom on Fridays.",
            ],
        },
        {
            "company": "City Library",
            "role": "Volunteer Shelver",
            "bullets": ["Shelved returned books twice a week."],
        },
    ],
    "projects": [
        {"name": "Depot handbook", "bullets": ["Wrote a 20-page handbook for new dispatchers."]},
    ],
    "education": [
        {"institution": "Lisbon Polytechnic", "degree": "BSc", "field": "Logistics"},
        {"institution": "Coastal Evening School", "degree": "Certificate", "field": "Bookkeeping"},
        {"institution": "Harbor Training Centre", "field": "Warehouse safety"},
        {"institution": "Riverside Adult College", "field": "Spanish"},
    ],
    "certifications": ["Forklift licence", "First aid"],
    "extra_sections": [
        {"key": "volunteering", "title": "Volunteering", "type": "bullets", "bullets": ["Food bank driver, weekends."]},
        {"key": "languages", "title": "Languages", "type": "bullets", "bullets": ["Portuguese, English"]},
        {"key": "interests", "title": "Interests", "type": "bullets", "bullets": ["Cycling, chess"]},
    ],
}


def _tailored() -> dict:
    doc = deepcopy(BASE)
    doc["contact"]["location"] = "Porto, Portugal"
    doc["summary"] = "Operations coordinator who cut late deliveries by a third across three depots."
    doc["skills"][0]["items"].append("Capacity planning")
    doc["skills"] += [
        {"category": "Safety", "items": ["Risk assessments"]},
        {"category": "People", "items": ["Rota planning", "Onboarding"]},
        {"category": "Reporting", "items": ["Weekly delivery reports"]},
    ]
    first = doc["experience"][0]
    first["bullets"][0] = "Scheduled 40 weekly deliveries across three depots and cut late arrivals by a third."
    first["bullets"] += [
        "Planned routes for a fleet of 12 vans.",
        "Ran the weekly depot safety walk.",
        "Wrote the handover notes each shift.",
    ]
    doc["experience"][1]["bullets"] = doc["experience"][1]["bullets"][:1]
    doc["experience"][2]["enabled"] = False
    doc["experience"][2]["bullets"][0] = "Shelved and catalogued returned books twice a week."
    doc["projects"][0]["enabled"] = False
    doc["projects"] += [
        {"name": "Route board", "bullets": ["Built a wall board that shows every van's day."]},
        {"name": "Returns log", "bullets": ["Set up a shared log for returned parcels."]},
        {"name": "Depot map", "bullets": ["Drew a floor map of the main depot."]},
    ]
    doc["education"] = doc["education"][:1]
    doc["certifications"][0] = "Forklift licence (2024)"
    doc["certifications"] += ["Dangerous goods handling", "Fire warden", "Manual handling"]
    volunteering, _languages, interests = doc["extra_sections"]
    volunteering["bullets"] = ["Food bank driver and route planner, weekends."]
    interests["enabled"] = False
    doc["extra_sections"] = [
        volunteering,
        interests,
        {"key": "awards", "title": "Awards", "type": "bullets", "bullets": ["Depot of the year, 2023."]},
        {"key": "memberships", "title": "Memberships", "type": "bullets", "bullets": ["Logistics guild."]},
    ]
    return doc


def _stored(doc: dict) -> dict:
    """A resume as the database holds it: every field, in the model's order."""
    return ResumeData.model_validate(doc).model_dump(mode="json")


def served() -> dict:
    base, tailored = _stored(BASE), _stored(_tailored())
    return {
        "base": base,
        "tailored": tailored,
        "hunks": resume_diff.attribute(resume_diff.diff_resume(base, tailored), None),
    }


def test_the_fixture_is_what_the_diff_serves():
    if os.environ.get("MAESTRO_RESUME_DIFF_WRITE") == "1":
        FIXTURE.parent.mkdir(exist_ok=True)
        FIXTURE.write_text(json.dumps(served(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        pytest.fail("fixture written; rerun without the variable", pytrace=False)
    assert FIXTURE.is_file(), f"no fixture: {REGENERATE}"
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == served(), f"the fixture differs from the diff: {REGENERATE}"


def test_the_fixture_holds_every_kind_of_change():
    kinds = {hunk["kind"] for hunk in served()["hunks"]}
    assert kinds == {
        "summary_changed", "contact_changed", "skills_group_changed",
        "bullet_added", "bullet_removed", "bullet_edited",
        "entry_added", "entry_removed", "entry_disabled",
        "extra_section_added", "extra_section_removed", "extra_section_changed", "extra_section_disabled",
    }
