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
    assert job.salary_currency_assumed is False  # the posting said it
    assert job.country == "GB"

    bare = Job(raw_text="y", raw_text_hash="i" * 64, source="user")
    _apply_extraction(
        bare,
        {"salary_min": "50", "salary_max": "60", "salary_period": "hour"},
    )
    assert bare.salary_currency == "USD"  # no country: the home currency (HOME_CURRENCY default)
    assert bare.salary_currency_assumed is True

    none = Job(raw_text="z", raw_text_hash="j" * 64, source="user")
    _apply_extraction(none, {"title": "No pay stated"})
    assert none.salary_min is None
    assert none.salary_currency is None
    assert none.salary_currency_assumed is False


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


def test_work_mode_is_stored_as_one_key():
    from app.schemas.job_extraction import work_mode_key

    for text in ("On-site", "onsite", "on site", " On Site ", "In office", "in-person", "ONSITE"):
        assert JobExtraction.model_validate({"work_mode": text}).work_mode == "on_site", text
    for text in ("Hybrid", "hybrid ", "Hybrid (3 days in office)"):
        assert JobExtraction.model_validate({"work_mode": text}).work_mode == "hybrid", text
    for text in ("Remote", "REMOTE", "Fully remote", "Remote (US)", "work from home"):
        assert JobExtraction.model_validate({"work_mode": text}).work_mode == "remote", text
    for text in (None, "", "unknown", "N/A"):
        assert JobExtraction.model_validate({"work_mode": text}).work_mode is None, text
    # A value naming no mode, or two, keeps its own words as one key: never a guess.
    assert work_mode_key("Field-based") == "field_based"
    assert work_mode_key("Remote or on-site") == "remote_or_on_site"
    # Already a key: unchanged.
    for key in ("on_site", "hybrid", "remote"):
        assert work_mode_key(key) == key


def test_level_maps_to_the_extraction_vocabulary():
    from app.schemas.job_extraction import level_key

    cases = {
        "Senior": "senior", "senior ": "senior", "Sr.": "senior", "Senior level": "senior",
        "Junior": "entry", "Entry-level": "entry", "Entry": "entry", "New grad": "entry",
        "Mid-level": "mid", "Intermediate": "mid", "MID": "mid",
        "Internship": "intern", "Intern": "intern",
        "Lead": "lead", "Staff": "lead", "Principal": "lead",
    }
    for text, key in cases.items():
        assert JobExtraction.model_validate({"level": text}).level == key, text
    assert JobExtraction.model_validate({"level": "unknown"}).level is None
    # A level outside the vocabulary keeps its own words, as one spelling.
    assert level_key("Director") == "director"
    assert level_key(" director") == "director"
    assert level_key("Mid-Senior level") == "mid_senior_level"


def test_apply_extraction_writes_the_country_code():
    from app.models.job import Job
    from app.routers.jobs import _apply_extraction

    named = Job(raw_text="x", raw_text_hash="cc1" * 21 + "x", source="user")
    _apply_extraction(named, {"title": "Engineer", "country": "United States"})
    assert named.country == "United States"  # kept as written
    assert named.country_code == "US"

    from_place = Job(raw_text="y", raw_text_hash="cc2" * 21 + "y", source="user")
    _apply_extraction(from_place, {"title": "Engineer", "location_raw": "Toronto, ON, Canada"})
    assert from_place.country_code == "CA"

    unknown = Job(raw_text="z", raw_text_hash="cc3" * 21 + "z", source="user")
    _apply_extraction(unknown, {"title": "Engineer", "location_raw": "Remote"})
    assert unknown.country_code is None


def test_a_bare_dollar_sign_is_not_us_dollars():
    for text in ("$", " $ ", "dollars"):
        assert JobExtraction.model_validate({"salary_currency": text}).salary_currency is None, text
    for text in ("US$", "us$", "USD", "usd", "$USD", "USD $"):
        assert JobExtraction.model_validate({"salary_currency": text}).salary_currency == "USD", text
    assert JobExtraction.model_validate({"salary_currency": "CAD"}).salary_currency == "CAD"


def test_a_bare_dollar_in_toronto_is_canadian_and_assumed():
    from app.models.job import Job
    from app.routers.jobs import _apply_extraction

    extraction = JobExtraction.model_validate({
        "title": "Analyst", "salary_min": "80000", "salary_max": "95000", "salary_period": "year",
        "salary_currency": "$", "city": "Toronto", "state": "ON", "location_raw": "Toronto, ON, Canada",
    }).model_dump(mode="json")
    job = Job(raw_text="t", raw_text_hash="t" * 64, source="user")
    _apply_extraction(job, extraction)
    assert job.country_code == "CA"
    assert job.salary_currency == "CAD"
    assert job.salary_currency_assumed is True


def test_a_country_with_no_currency_falls_back_to_home_and_is_assumed():
    from app.models.job import Job
    from app.routers.jobs import _apply_extraction

    job = Job(raw_text="a", raw_text_hash="a" * 64, source="user")
    _apply_extraction(job, {"salary_min": "10", "salary_period": "hour", "country": "AQ"})
    assert job.country_code == "AQ"
    assert job.salary_currency == "USD"  # HOME_CURRENCY default: Antarctica has no currency entry
    assert job.salary_currency_assumed is True
