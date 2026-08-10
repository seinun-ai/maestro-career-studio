# backend/tests/test_health_zones.py
from app.services.health_zones import (
    compute_tier,
    cost,
    hot_locations,
    parse_ym,
    severity,
    total_experience_months,
)

EXPERIENCED = {
    "summary": "Engineer.",
    "experience": [
        {"company": "A", "role": "SWE", "start_date": "Jan 2021", "end_date": "Present",
         "bullets": ["b1", "b2", "b3", "b4"]},
        {"company": "B", "role": "SWE", "start_date": "2018", "end_date": "2021",
         "bullets": ["c1"]},
    ],
    "projects": [{"name": "P", "bullets": ["p1"]}],
}


def test_parse_ym_formats():
    assert parse_ym("Jan 2021") == (2021, 1)
    assert parse_ym("2021-03") == (2021, 3)
    assert parse_ym("03/2021") == (2021, 3)
    assert parse_ym("2021") == (2021, 1)          # bare year → January
    assert parse_ym("Present") == "present"
    assert parse_ym("current") == "present"
    assert parse_ym("garbage") is None
    assert parse_ym("") is None
    # out-of-range months must fail closed (unparseable)
    assert parse_ym("2021-13") is None
    assert parse_ym("00/2021") is None
    assert parse_ym("13/2021") is None
    assert parse_ym("2021-00") is None
    # valid boundaries still parse
    assert parse_ym("2021-12") == (2021, 12)
    assert parse_ym("12/2021") == (2021, 12)


def test_total_months_merges_overlaps():
    resume = {"experience": [
        {"start_date": "Jan 2020", "end_date": "Jan 2022", "bullets": []},
        {"start_date": "Jan 2021", "end_date": "Jan 2023", "bullets": []},  # overlaps
    ]}
    # Jan 2020 → Jan 2023 = 36 months, not 48
    assert total_experience_months(resume, now=(2026, 7)) == 36


def test_tier_boundary():
    early = {"experience": [{"start_date": "Jan 2025", "end_date": "Present", "bullets": []}]}
    assert compute_tier(early, now=(2026, 7)) == "early"          # 18 months
    assert compute_tier(EXPERIENCED, now=(2026, 7)) == "experienced"
    assert compute_tier({"experience": []}, now=(2026, 7)) == "unknown"


def test_hot_locations_experienced_is_summary_and_most_recent_role():
    hot = hot_locations(EXPERIENCED, "experienced")
    assert ("summary", None, None) in hot
    # The whole first role, not a three-bullet slice.
    assert {("experience", 0, i) for i in range(4)} <= hot
    # Older roles stay cold — the weighting needs something to rank against.
    assert ("experience", 1, 0) not in hot
    # Experienced candidates are not read on projects.
    assert ("projects", 0, 0) not in hot


def test_hot_locations_early_is_summary_and_projects_only():
    hot = hot_locations(EXPERIENCED, "early")
    assert ("summary", None, None) in hot
    assert ("projects", 0, 0) in hot
    # The one that changed: early-career resumes used to get their first role
    # hot AS WELL, which made most of a junior document hot.
    assert not any(loc[0] == "experience" for loc in hot)


def test_hot_locations_early_uses_first_enabled_project_only():
    resume = {
        "summary": "x",
        "projects": [
            {"name": "A", "enabled": False, "bullets": ["a1"]},
            {"name": "B", "bullets": ["b1", "b2"]},
            {"name": "C", "bullets": ["c1"]},
        ],
    }
    hot = hot_locations(resume, "early")
    assert ("projects", 1, 0) in hot
    assert ("projects", 1, 1) in hot
    assert ("projects", 0, 0) not in hot       # disabled
    assert ("projects", 2, 0) not in hot       # not the first enabled


def test_hot_skips_disabled_first_role():
    resume = {
        "summary": "x",
        "experience": [
            {"company": "A", "enabled": False, "bullets": ["a1"]},
            {"company": "B", "bullets": ["b1"]},
        ],
    }
    hot = hot_locations(resume, "experienced")
    assert ("experience", 1, 0) in hot
    assert ("experience", 0, 0) not in hot


def test_hot_locations_unknown_tier_is_treated_as_experienced():
    """'unknown' must never silently pick the harsher tier (design escape #3)."""
    assert hot_locations(EXPERIENCED, "unknown") == hot_locations(
        EXPERIENCED, "experienced"
    )


def test_a_resume_always_has_cold_content_to_rank_against():
    """cost() can only order a fix list if the hot set is a proper subset."""
    for tier in ("experienced", "early"):
        hot = hot_locations(EXPERIENCED, tier)
        every_bullet = {
            (section, i, bi)
            for section in ("experience", "projects")
            for i, entry in enumerate(EXPERIENCED.get(section) or [])
            for bi in range(len(entry.get("bullets") or []))
        }
        assert every_bullet - {loc for loc in hot if loc[0] != "summary"}


def test_severity_and_cost():
    assert severity(0.3, hot=True) == "critical"
    assert severity(0.3, hot=False) == "minor"
    assert severity(0.5, hot=True) == "minor"
    assert cost(0.5, hot=True) == 0.5          # 1.0 × (1 − 0.5)
    assert cost(0.5, hot=False) == 0.25        # 0.5 × (1 − 0.5)
