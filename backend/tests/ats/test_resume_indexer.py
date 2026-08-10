from datetime import date

from app.services.ats.resume_indexer import _merged_years, index_resume, parse_month_year
from tests.ats.fixtures import SAMPLE_RESUME

AS_OF = date(2026, 7, 6)


def _resume_with_experience(**exp):
    """Minimal resume with a single experience entry, fields overridable."""
    return {
        "experience": [
            {"company": "X Corp", "role": "Engineer", "enabled": True, "bullets": [], **exp},
        ],
    }


def test_parse_month_year():
    assert parse_month_year("Jul 2023") == date(2023, 7, 1)
    assert parse_month_year("Feb 2026") == date(2026, 2, 1)
    assert parse_month_year("Present") is None
    assert parse_month_year(None) is None
    assert parse_month_year("garbage") is None


def test_index_skips_disabled_entries():
    index = index_resume(SAMPLE_RESUME, as_of=AS_OF)
    labels = [e.label for e in index.entries]
    assert not any("HiddenCo" in label for label in labels)  # enabled: false
    assert any("DataCo" in label for label in labels)
    assert any("RAG Search" in label for label in labels)  # projects indexed too


def test_index_extra_entries_with_stable_section_key_and_original_index():
    resume = {
        "extra_sections": [{
            "key": "publications",
            "title": "Publications",
            "type": "entries",
            "enabled": True,
            "entries": [
                {
                    "heading": "Hidden",
                    "subheading": "Salesforce",
                    "enabled": False,
                    "bullets": ["Docker"],
                },
                {
                    "heading": "Warehouse Paper",
                    "subheading": "Snowflake Guild",
                    "location": "Terraform",
                    "date": "Jan 2026",
                    "enabled": True,
                    "bullets": ["Ran Docker workloads."],
                },
            ],
        }],
    }
    index = index_resume(resume, as_of=AS_OF)
    extras = [entry for entry in index.entries if entry.section == "extra"]
    assert len(extras) == 1
    assert extras[0].section_key == "publications"
    assert extras[0].index == 1  # original list index, not enabled-only index
    assert extras[0].label == "Warehouse Paper"
    assert extras[0].text == "warehouse paper snowflake guild ran docker workloads."
    assert extras[0].last_date is None and extras[0].is_current is False


def test_extra_section_enabled_none_is_treated_as_live():
    # F#6: enabled: None (or omitted) reads as LIVE, via the shared
    # resume_projects.extra_section_live / extra_entry_live predicate the gap
    # placement-target builder also uses, so the two views cannot disagree.
    resume = {
        "extra_sections": [{
            "key": "pubs", "title": "Pubs", "type": "entries", "enabled": None,
            "entries": [
                {"heading": "Live entry", "enabled": None, "bullets": ["Kafka work."]},
                {"heading": "Off entry", "enabled": False, "bullets": ["Hidden."]},
            ],
        }],
    }
    extras = [e for e in index_resume(resume, as_of=AS_OF).entries if e.section == "extra"]
    assert [e.label for e in extras] == ["Live entry"]
    assert extras[0].index == 0


def test_extra_sections_null_does_not_crash_indexer():
    # F#13: an explicit "extra_sections": null must read as empty, not raise.
    index = index_resume({"extra_sections": None}, as_of=AS_OF)
    assert [e for e in index.entries if e.section == "extra"] == []


def test_entry_dates_and_current_flag():
    index = index_resume(SAMPLE_RESUME, as_of=AS_OF)
    dataco = next(e for e in index.entries if "DataCo" in e.label)
    assert dataco.is_current is True and dataco.last_date == AS_OF
    oldco = next(e for e in index.entries if "OldCo" in e.label)
    assert oldco.is_current is False and oldco.last_date == date(2021, 6, 1)


def test_skills_items_normalized_with_category():
    index = index_resume(SAMPLE_RESUME, as_of=AS_OF)
    terms = {item.norm for item in index.skills_items}
    assert "python" in terms and "amazon web services" in terms
    aws = next(i for i in index.skills_items if i.norm == "amazon web services")
    assert aws.category == "Cloud"


def test_entry_text_is_normalized_prose():
    index = index_resume(SAMPLE_RESUME, as_of=AS_OF)
    dataco = next(e for e in index.entries if "DataCo" in e.label)
    assert "python forecasting models" in dataco.text
    assert "aws" in dataco.text


def test_experience_years_merges_overlaps():
    index = index_resume(SAMPLE_RESUME, as_of=AS_OF)
    # Jun 2019–Jun 2021 (2y) + Jul 2023–present (~3y) ≈ 5, no overlap here
    assert 4.5 < index.total_experience_years < 5.5


def test_parse_month_year_never_raises_on_malformed_input():
    assert parse_month_year("Sept 2023") == date(2023, 9, 1)
    assert parse_month_year("September 2023") == date(2023, 9, 1)
    assert parse_month_year("Jun 20233") is None  # year out of range
    assert parse_month_year("Jul 0") is None  # year below MINYEAR
    assert parse_month_year("Jul ²") is None  # non-ascii "digit": isdigit() True, int() raises
    assert parse_month_year("2019") is None  # year-only deliberately unsupported


def test_merged_years_overlapping_spans():
    spans = [
        (date(2020, 1, 1), date(2021, 1, 1)),
        (date(2020, 7, 1), date(2021, 7, 1)),
    ]
    # merged: 2020-01-01 .. 2021-07-01 ~ 1.5y, not 2.0
    assert 1.4 < _merged_years(spans) < 1.6


def test_merged_years_contained_span():
    spans = [
        (date(2020, 1, 1), date(2022, 1, 1)),
        (date(2020, 6, 1), date(2021, 1, 1)),  # fully inside the first
    ]
    assert 1.9 < _merged_years(spans) < 2.1


def test_merged_years_touching_spans_no_double_count():
    spans = [
        (date(2020, 1, 1), date(2021, 1, 1)),
        (date(2021, 1, 1), date(2022, 1, 1)),
    ]
    assert 1.9 < _merged_years(spans) < 2.1


def test_unparsable_end_date_is_not_current():
    resume = _resume_with_experience(start_date="Jun 2019", end_date="Jnue 2021")
    index = index_resume(resume, as_of=AS_OF)
    entry = index.entries[0]
    assert entry.is_current is False
    assert entry.last_date is None
    assert entry.date_parse_ok is False
    assert index.total_experience_years == 0.0  # excluded from years


def test_swapped_dates_do_not_go_negative():
    resume = _resume_with_experience(start_date="Jun 2021", end_date="Jun 2019")
    index = index_resume(resume, as_of=AS_OF)
    assert index.entries[0].date_parse_ok is False
    assert index.total_experience_years == 0.0


def test_future_end_date_clamped_at_as_of():
    resume = _resume_with_experience(start_date="Jul 2025", end_date="Jul 2030")
    index = index_resume(resume, as_of=AS_OF)
    # Jul 2025 .. as_of (2026-07-06) ~ 1.0y, not 5y
    assert 0.9 < index.total_experience_years < 1.1


def test_future_start_on_current_role_does_not_go_negative():
    resume = _resume_with_experience(start_date="Jul 2027", end_date=None)
    index = index_resume(resume, as_of=AS_OF)
    assert index.entries[0].date_parse_ok is False
    assert index.total_experience_years == 0.0
