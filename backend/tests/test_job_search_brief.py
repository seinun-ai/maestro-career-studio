from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.job import Job
from app.models.referral import Referral
from app.services import autofill_profile, persona, text_settings


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _get_brief(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        return TestClient(app).get("/api/jobs/search-brief")
    finally:
        app.dependency_overrides.clear()


def test_search_brief_not_captured_by_job_id_route(db_session, tmp_path, monkeypatch):
    # Route-ordering guard: /search-brief must be registered before /{job_id}
    # (job_id is UUID-typed; losing the ordering turns this into a 422).
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    assert _get_brief(db_session).status_code == 200


def test_search_brief_aggregation_shape(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    autofill_profile.set_profile(
        {
            "personal": {"city": "Sampleton", "state": "Texas", "country": "United States"},
            "preferences": {"willing_to_relocate": "yes"},
            "work_auth": {"authorized_to_work": "yes", "requires_sponsorship": "yes"},
        },
        db_session,
    )
    persona.set_persona("Analytics engineer who ships.", db_session)
    db_session.add_all(
        [
            Job(raw_text="recent JD", raw_text_hash="brief-h1",
                role_category="data_analyst", company="Acme"),
            Job(raw_text="old JD", raw_text_hash="brief-h2",
                role_category="data_engineer", company="Beta",
                created_at=datetime.now(UTC) - timedelta(days=40)),
            Job(raw_text="uncategorized JD", raw_text_hash="brief-h3"),
        ]
    )
    db_session.add_all(
        [
            Referral(company="Acme", careers_url="https://acme.test/careers",
                     contact_name="Dana R."),
            Referral(company="Beta", careers_url="https://beta.test/jobs"),
        ]
    )
    db_session.commit()

    response = _get_brief(db_session)
    assert response.status_code == 200
    body = response.json()

    assert body["profile"] == {
        "city": "Sampleton",
        "state": "Texas",
        "country": "United States",
        "willing_to_relocate": "yes",
        "work_auth": {"authorized_to_work": "yes", "requires_sponsorship": "yes"},
    }
    assert body["persona"] == "Analytics engineer who ships."
    assert body["warnings"] == []  # yes/yes is a valid combo (OPT now, sponsorship later)
    assert isinstance(body["base_resumes"], list)
    assert {"key": "data_analyst", "count": 1} in body["role_mix"]
    assert isinstance(body["top_skills"], list)
    assert isinstance(body["build_areas"], list)
    assert body["referrals"] == [
        {"company": "Acme", "careers_url": "https://acme.test/careers", "has_contact": True},
        {"company": "Beta", "careers_url": "https://beta.test/jobs", "has_contact": False},
    ]
    # Ledger: only the two jobs captured in the last 30 days; the 40-day-old
    # data_engineer row must NOT appear; null role_category coalesces to "unknown".
    assert sorted(body["captured_last_30_days"], key=lambda r: r["role_category"]) == [
        {"role_category": "data_analyst", "count": 1},
        {"role_category": "unknown", "count": 1},
    ]


def test_search_brief_carries_provenance_labels(db_session, tmp_path, monkeypatch):
    # The brief mixes all-time aggregations with a 30-day capture ledger; a
    # top-level generated_at and per-block window labels stop an agent from
    # misreading them as equally current.
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    body = _get_brief(db_session).json()

    assert "generated_at" in body
    parsed = datetime.fromisoformat(body["generated_at"])
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)  # timezone-aware UTC

    # A window string on each aggregation block, matching what the service
    # actually computes (build_overview/build_areas are unfiltered = all-time;
    # only the capture ledger is date-bounded).
    assert body["windows"] == {
        "role_mix": "all_time",
        "top_skills": "all_time",
        "build_areas": "all_time",
        "captured_last_30_days": "last_30_days",
    }


def test_search_brief_contradictory_work_auth_warns(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    autofill_profile.set_profile(
        {"work_auth": {"authorized_to_work": "no", "requires_sponsorship": "no"}},
        db_session,
    )
    body = _get_brief(db_session).json()
    # Values are carried verbatim — never corrected or guessed.
    assert body["profile"]["work_auth"] == {
        "authorized_to_work": "no",
        "requires_sponsorship": "no",
    }
    assert any("contradictory" in w for w in body["warnings"])


def test_search_brief_projects_typed_work_auth_to_public_yes_no_shape(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    autofill_profile.set_profile(
        {
            "work_auth": {
                "status": "opt",
                "authorized_now": True,
                "sponsorship_now": True,
                "sponsorship_future": False,
            }
        },
        db_session,
    )

    body = _get_brief(db_session).json()

    assert body["profile"]["work_auth"] == {
        "authorized_to_work": "yes",
        "requires_sponsorship": "no",
    }
    assert body["warnings"] == []


def test_search_brief_keeps_unknown_typed_work_auth_unknown(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    autofill_profile.set_profile(
        {
            "work_auth": {
                "status": "h1b",
                "authorized_now": False,
                "sponsorship_now": True,
                # sponsorship_future deliberately unanswered: neither current
                # sponsorship nor status may be substituted for it.
            }
        },
        db_session,
    )

    body = _get_brief(db_session).json()

    assert body["profile"]["work_auth"] == {
        "authorized_to_work": "no",
        "requires_sponsorship": None,
    }
    assert any("incomplete" in warning for warning in body["warnings"])
    assert not any("contradictory" in warning for warning in body["warnings"])


def test_search_brief_warns_for_typed_no_no_contradiction(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    autofill_profile.set_profile(
        {
            "work_auth": {
                "authorized_now": False,
                "sponsorship_future": False,
            }
        },
        db_session,
    )

    body = _get_brief(db_session).json()

    assert body["profile"]["work_auth"] == {
        "authorized_to_work": "no",
        "requires_sponsorship": "no",
    }
    assert any("contradictory" in warning for warning in body["warnings"])


def test_search_brief_carries_preferences_and_auto_apply_guardrails(
    db_session, tmp_path, monkeypatch
):
    # G1: the typed job_preferences ride the brief verbatim; G2: the hunt sees
    # the blocklist and caps up front instead of discovering them by 409.
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    from app.schemas.job_preferences import JobPreferences
    from app.services import auto_apply_settings, job_preferences

    job_preferences.set_preferences(
        JobPreferences.model_validate(
            {"role_categories": ["data_scientist"], "min_salary": "120000"}
        ),
        db_session,
    )
    cfg = auto_apply_settings.get_settings(db_session)
    cfg.company_blocklist = ["BadCo"]
    auto_apply_settings.set_settings(cfg, db_session)

    body = _get_brief(db_session).json()
    prefs = body["job_preferences"]
    assert prefs["role_categories"] == ["data_scientist"]
    assert prefs["min_salary"] == "120000"

    auto = body["auto_apply"]
    assert auto["company_blocklist"] == ["BadCo"]
    assert auto["max_proposals_per_run"] >= 1
    assert set(auto["cap"]) == {"max_per_day", "reserved_last_24h", "remaining"}


def test_search_brief_tolerates_empty_everything(db_session, tmp_path, monkeypatch):
    # No autofill profile, no persona, no jobs, no bases, no referrals.
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    response = _get_brief(db_session)
    assert response.status_code == 200
    body = response.json()
    assert body["persona"] == ""
    assert body["base_resumes"] == []
    assert body["referrals"] == []
    assert body["captured_last_30_days"] == []
    # Missing work-auth values are a warning, not a guess.
    assert any("incomplete" in w for w in body["warnings"])
