from app.services.health_gates import (
    detect_claim_overstatement,
    detect_gaps,
    gate_dates,
    gate_placeholders,
)

OK = {
    "summary": "Data scientist with 2+ years of production experience.",
    "experience": [
        {"company": "A", "role": "DS", "start_date": "Jan 2024", "end_date": "Present",
         "bullets": ["Shipped a model serving 200k users."]},
    ],
    "projects": [],
    "education": [],
}


def test_gate_dates_passes_clean_resume():
    assert gate_dates(OK)["status"] == "pass"


def test_gate_dates_fails_on_missing_or_garbage():
    bad = {"experience": [{"company": "A", "start_date": "", "end_date": "Present", "bullets": []}]}
    g = gate_dates(bad)
    assert g["status"] == "fail" and g["id"] == "S3"
    garbage = {"experience": [{"company": "A", "start_date": "whenever", "end_date": "Present", "bullets": []}]}
    assert gate_dates(garbage)["status"] == "fail"


def test_gate_dates_ignores_disabled_entries():
    resume = {"experience": [{"company": "A", "enabled": False, "start_date": "", "bullets": []}]}
    assert gate_dates(resume)["status"] == "pass"


def test_gate_placeholders_catches_brackets_todo_xx():
    for text in ("Improved by [X]%", "TODO tighten this", "cut costs XX%"):
        resume = {"summary": "s", "experience": [
            {"company": "A", "start_date": "2020", "end_date": "2021", "bullets": [text]}]}
        g = gate_placeholders(resume)
        assert g["status"] == "fail" and g["id"] == "S5", text


def test_gate_placeholders_checks_summary_too():
    resume = {"summary": "Engineer with [N] years.", "experience": []}
    assert gate_placeholders(resume)["status"] == "fail"


def test_gate_placeholders_passes_clean():
    assert gate_placeholders(OK)["status"] == "pass"


def test_claim_overstatement_fires_beyond_slack():
    resume = {
        "summary": "Engineer with 8+ years of experience.",
        "experience": [{"start_date": "Jan 2023", "end_date": "Present", "bullets": []}],
    }
    hit = detect_claim_overstatement(resume, now=(2026, 7))
    assert hit is not None
    assert hit["claimed_years"] == 8
    assert hit["actual_years"] < 4


def test_claim_overstatement_respects_one_year_slack():
    resume = {
        "summary": "Engineer with 4 years of experience.",
        "experience": [{"start_date": "Jan 2023", "end_date": "Present", "bullets": []}],
    }
    # actual 3.5y, claimed 4 → within slack
    assert detect_claim_overstatement(resume, now=(2026, 7)) is None


def test_claim_overstatement_not_assessed_without_dates():
    resume = {"summary": "Engineer with 8 years of experience.", "experience": []}
    assert detect_claim_overstatement(resume, now=(2026, 7)) is None


def test_detect_gaps_finds_uncovered_gap_over_6_months():
    resume = {
        "experience": [
            {"company": "B", "start_date": "Jan 2024", "end_date": "Present", "bullets": []},
            {"company": "A", "start_date": "Jan 2020", "end_date": "Jan 2023", "bullets": []},
        ],
        "education": [],
    }
    gaps = detect_gaps(resume, now=(2026, 7))
    assert len(gaps) == 1
    assert gaps[0]["months"] == 12


def test_detect_gaps_covered_by_education_does_not_fire():
    resume = {
        "experience": [
            {"company": "B", "start_date": "Jan 2024", "end_date": "Present", "bullets": []},
            {"company": "A", "start_date": "Jan 2020", "end_date": "Jan 2023", "bullets": []},
        ],
        "education": [
            {"institution": "U", "start_date": "Jan 2023", "end_date": "Jan 2024"},
        ],
    }
    assert detect_gaps(resume, now=(2026, 7)) == []


def test_detect_gaps_overlapping_tenure_no_phantom_gap():
    # Acme spans the whole window; SideCo and NewCo overlap it → no real gap.
    resume = {
        "experience": [
            {"company": "Acme", "start_date": "Jan 2020", "end_date": "Jan 2024", "bullets": []},
            {"company": "SideCo", "start_date": "Jan 2021", "end_date": "Apr 2021", "bullets": []},
            {"company": "NewCo", "start_date": "Jan 2023", "end_date": "Present", "bullets": []},
        ],
        "education": [],
    }
    assert detect_gaps(resume, now=(2026, 7)) == []


def test_detect_gaps_covered_by_merged_two_degree_education():
    # BS ends Jun 2022, MS Jun 2022–Jun 2024. Merged, they cover a gap ending
    # inside the MS; neither degree alone covers it.
    resume = {
        "experience": [
            {"company": "Role1", "start_date": "Jan 2020", "end_date": "Jan 2022", "bullets": []},
            {"company": "Role2", "start_date": "Jan 2024", "end_date": "Present", "bullets": []},
        ],
        "education": [
            {"institution": "BS", "start_date": "Jan 2018", "end_date": "Jun 2022"},
            {"institution": "MS", "start_date": "Jun 2022", "end_date": "Jun 2024"},
        ],
    }
    assert detect_gaps(resume, now=(2026, 7)) == []


def test_detect_gaps_mostly_covered_remainder_under_threshold_does_not_fire():
    # A synthetic 24-month employment gap is mostly covered by a degree.
    # Only about three edge months remain uncovered, below the six-month
    # threshold, so the rule must not report a gap.
    resume = {
        "experience": [
            {"company": "Fictional Employer 3", "start_date": "Jun 2026", "end_date": "Present",
             "bullets": []},
            {"company": "Fictional Employer Legacy", "start_date": "Jul 2022", "end_date": "Jun 2024",
             "bullets": []},
        ],
        "education": [
            {"institution": "U", "degree": "M.S.",
             "start_date": "Aug 2024", "end_date": "May 2026"},
        ],
    }
    assert detect_gaps(resume, now=(2026, 7)) == []


def test_detect_gaps_partial_coverage_over_threshold_fires_with_remainder():
    # 24-month gap; education covers only the first 6 months → 18 uncovered.
    resume = {
        "experience": [
            {"company": "B", "start_date": "Jan 2022", "end_date": "Present", "bullets": []},
            {"company": "A", "start_date": "Jan 2018", "end_date": "Jan 2020", "bullets": []},
        ],
        "education": [
            {"institution": "U", "start_date": "Jan 2020", "end_date": "Jul 2020"},
        ],
    }
    gaps = detect_gaps(resume, now=(2026, 7))
    assert len(gaps) == 1
    assert gaps[0]["months"] == 24
    assert gaps[0]["covered_months"] == 6
    assert gaps[0]["uncovered_months"] == 18


def test_detect_gaps_no_education_reports_full_gap_as_uncovered():
    resume = {
        "experience": [
            {"company": "B", "start_date": "Jan 2024", "end_date": "Present", "bullets": []},
            {"company": "A", "start_date": "Jan 2020", "end_date": "Jan 2023", "bullets": []},
        ],
        "education": [],
    }
    gaps = detect_gaps(resume, now=(2026, 7))
    assert len(gaps) == 1
    assert gaps[0]["covered_months"] == 0
    assert gaps[0]["uncovered_months"] == gaps[0]["months"] == 12


def test_claim_overstatement_parses_decimal_years():
    # "2.5 years" must not misparse as "5 years"; actual ≈2.5y → within slack.
    resume = {
        "summary": "Data scientist with 2.5 years of experience.",
        "experience": [{"start_date": "Jan 2024", "end_date": "Present", "bullets": []}],
    }
    assert detect_claim_overstatement(resume, now=(2026, 7)) is None


def test_gate_placeholders_ignores_technical_bracket_notation():
    for text in (
        "Built typed pipeline with Dict[str, Any] contracts",
        "Aggregated df[revenue] by cohort",
        "Configured Optional[int] flag",
    ):
        resume = {"summary": "s", "experience": [
            {"company": "A", "start_date": "2020", "end_date": "2021", "bullets": [text]}]}
        assert gate_placeholders(resume)["status"] == "pass", text


def test_gate_placeholders_scans_structural_fields():
    resume = {"summary": "s", "experience": [
        {"company": "[Company Name]", "role": "DS",
         "start_date": "2020", "end_date": "2021", "bullets": []}]}
    assert gate_placeholders(resume)["status"] == "fail"


# --- extra (custom) section traversal (phase-1 placeholder gate) --------------


def test_gate_placeholders_scans_extra_bullets_section():
    resume = {"summary": "s", "experience": [], "extra_sections": [
        {"key": "awards", "title": "Awards", "type": "bullets", "enabled": True,
         "bullets": ["First place, [YEAR]"]}]}
    g = gate_placeholders(resume)
    assert g["status"] == "fail" and g["id"] == "S5"
    assert "awards" in g["detail"]


def test_gate_placeholders_scans_extra_entry_metadata_and_bullets():
    for entry in (
        {"heading": "[Paper title]", "enabled": True, "bullets": []},
        {"heading": "Real paper", "date": "[TBD]", "enabled": True, "bullets": []},
        {"heading": "Real paper", "enabled": True, "bullets": ["Cut latency by XX%"]},
    ):
        resume = {"summary": "s", "experience": [], "extra_sections": [
            {"key": "pubs", "title": "Publications", "type": "entries",
             "enabled": True, "entries": [entry]}]}
        assert gate_placeholders(resume)["status"] == "fail", entry


def test_gate_placeholders_ignores_disabled_extra_section():
    resume = {"summary": "s", "experience": [], "extra_sections": [
        {"key": "awards", "title": "Awards", "type": "bullets", "enabled": False,
         "bullets": ["Draft [TODO]"]}]}
    assert gate_placeholders(resume)["status"] == "pass"


def test_gate_placeholders_ignores_disabled_extra_entry():
    resume = {"summary": "s", "experience": [], "extra_sections": [
        {"key": "pubs", "title": "Publications", "type": "entries", "enabled": True,
         "entries": [{"heading": "[Draft]", "enabled": False, "bullets": []}]}]}
    assert gate_placeholders(resume)["status"] == "pass"


def test_gate_placeholders_passes_clean_extras():
    resume = {"summary": "Data scientist.", "experience": [], "extra_sections": [
        {"key": "awards", "title": "Awards", "type": "bullets", "enabled": True,
         "bullets": ["First place, 2025"]},
        {"key": "pubs", "title": "Publications", "type": "entries", "enabled": True,
         "entries": [{"heading": "Paper A", "subheading": "NeurIPS 2025",
                      "enabled": True, "bullets": ["Proposed a method."]}]}]}
    assert gate_placeholders(resume)["status"] == "pass"


def test_gate_placeholders_survives_malformed_extra_sections():
    # Not-a-list, non-dict members, and missing content fields must never crash.
    for bad in ({"extra_sections": "oops"},
                {"extra_sections": [None, 42]},
                {"extra_sections": [{"type": "entries", "entries": [None, "x"]}]},
                {"extra_sections": [{"key": "k", "title": "T"}]}):  # no type/content
        resume = {"summary": "s", "experience": [], **bad}
        assert gate_placeholders(resume)["status"] in ("pass", "fail")
