from decimal import Decimal

from app.schemas.job_extraction import JobExtraction


def test_job_extraction_normalizes_salary_and_period():
    extraction = JobExtraction.model_validate(
        {
            "salary_min": "$55",
            "salary_max": "45",
            "salary_period": "hourly",
            "salary_currency": "usd",
        }
    )

    assert extraction.salary_min == Decimal("45")
    assert extraction.salary_max == Decimal("55")
    assert extraction.salary_period == "hour"
    assert extraction.salary_currency == "USD"


def test_job_extraction_day_and_week_periods():
    day = JobExtraction.model_validate({"salary_period": "daily", "salary_min": "500"})
    week = JobExtraction.model_validate({"salary_period": "per week", "salary_min": "2000"})
    assert day.salary_period == "day"
    assert week.salary_period == "week"


def test_job_extraction_currency_symbols_and_pay_page():
    gbp = JobExtraction.model_validate({"salary_currency": "£", "salary_min": "400"})
    assert gbp.salary_currency == "GBP"
    linked = JobExtraction.model_validate(
        {"salary_source_url": "https://example.com/pay", "salary_min": None}
    )
    assert linked.salary_source_url == "https://example.com/pay"
    assert linked.salary_min is None
    assert linked.salary_currency is None


def test_job_extraction_dedupes_skills_and_cleans_lists():
    extraction = JobExtraction.model_validate(
        {
            "skills": [
                {
                    "skill_name": "Python",
                    "skill_category": "language",
                    "requirement_level": "required",
                },
                {
                    "skill_name": "python",
                    "skill_category": "language",
                    "requirement_level": "required",
                },
            ],
            "responsibilities": [" Build dashboards ", ""],
            "qualifications": "SQL experience",
        }
    )

    assert len(extraction.skills) == 1
    assert extraction.responsibilities == ["Build dashboards"]
    assert extraction.qualifications == ["SQL experience"]


def test_job_extraction_blank_strings_become_none():
    extraction = JobExtraction.model_validate({"company": "unknown", "title": ""})

    assert extraction.company is None
    assert extraction.title is None


def test_apply_extraction_maps_currency_and_home_fallback(monkeypatch):
    from app.models.job import Job
    from app.routers.jobs import _apply_extraction

    job = Job(raw_text="x", raw_text_hash="h" * 64, source="user")
    _apply_extraction(
        job,
        {
            "title": "Engineer",
            "salary_min": "90000",
            "salary_max": "110000",
            "salary_period": "year",
            "salary_currency": "gbp",
            "country": "GB",
        },
    )
    assert job.salary_currency == "GBP"
    assert job.country == "GB"

    bare = Job(raw_text="y", raw_text_hash="i" * 64, source="user")
    _apply_extraction(
        bare,
        {"salary_min": "50", "salary_max": "60", "salary_period": "hour"},
    )
    assert bare.salary_currency == "USD"  # HOME_CURRENCY default

    none = Job(raw_text="z", raw_text_hash="j" * 64, source="user")
    _apply_extraction(none, {"title": "No pay stated"})
    assert none.salary_min is None
    assert none.salary_currency is None


def test_apply_extraction_salary_source_url_without_numbers():
    from app.models.job import Job
    from app.routers.jobs import _apply_extraction

    job = Job(raw_text="x", raw_text_hash="k" * 64, source="user")
    _apply_extraction(
        job,
        {"salary_source_url": "https://careers.example.com/pay"},
    )
    assert job.salary_source_url == "https://careers.example.com/pay"
    assert job.salary_currency is None


def test_apply_extraction_requisition_id_falsy_is_none():
    """G11 dedup key: falsy requisition_id must stay None, not str(0)=='0'."""
    from app.models.job import Job
    from app.routers.jobs import _apply_extraction

    for falsy in (0, False, "", None):
        job = Job(raw_text="x", raw_text_hash="r" * 64, source="user")
        _apply_extraction(job, {"company": "Acme", "requisition_id": falsy})
        assert job.requisition_id is None, falsy

    kept = Job(raw_text="y", raw_text_hash="s" * 64, source="user")
    _apply_extraction(kept, {"company": "Acme", "requisition_id": " R-123 "})
    assert kept.requisition_id == "R-123"
