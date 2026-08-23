"""Knock-out pre-scan: JD-stated hard requirements vs the user's own profile.

The scan compares what the posting states (work authorization, OPT policy,
salary) against what the profile answers (work_auth, desired salary) BEFORE
any tailoring or filling effort is spent. Two honesty rules are pinned here:

- An unstated JD requirement is never a pass — "the posting states no
  blockers" and "you clear the stated blockers" are different verdicts.
- A stated requirement the profile cannot answer is never a pass either —
  that is an incomplete profile, not a green light.
"""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.application_proposal import ApplicationProposal
from app.models.job import Job
from app.schemas.autofill_profile import WorkAuth
from app.schemas.job_preferences import JobPreferences
from app.services import autofill_profile, job_preferences
from app.services.knockout import scan_job
from tests.test_proposals_models import _mk_job

client = TestClient(app)


def _job(**kwargs) -> Job:
    """Unsaved Job carrying only the fields the scan reads."""
    return Job(raw_text="jd", raw_text_hash="h" * 8, **kwargs)


def _check(result: dict, kind: str) -> dict:
    matches = [c for c in result["checks"] if c["kind"] == kind]
    assert len(matches) == 1, f"expected exactly one {kind!r} check, got {result['checks']}"
    return matches[0]


# --- work authorization -----------------------------------------------------

def test_citizen_clears_a_citizen_or_gc_required_posting():
    result = scan_job(
        _job(work_authorization="citizen_or_gc_required"),
        WorkAuth(status="citizen"),
        preferences=None,
    )
    assert _check(result, "work_authorization")["result"] == "pass"
    assert result["status"] == "clear"


def test_visa_status_conflicts_with_citizen_or_gc_required():
    result = scan_job(
        _job(work_authorization="citizen_or_gc_required"),
        WorkAuth(status="h1b"),
        preferences=None,
    )
    assert _check(result, "work_authorization")["result"] == "conflict"
    assert result["status"] == "conflict"


def test_opt_holder_conflicts_with_no_sponsorship():
    """OPT needs sponsorship later; "no sponsorship" postings screen on that."""
    result = scan_job(
        _job(work_authorization="no_sponsorship"),
        WorkAuth(status="opt"),
        preferences=None,
    )
    assert _check(result, "work_authorization")["result"] == "conflict"
    assert result["status"] == "conflict"


def test_citizen_passes_a_no_sponsorship_posting():
    result = scan_job(
        _job(work_authorization="no_sponsorship"),
        WorkAuth(status="citizen"),
        preferences=None,
    )
    assert _check(result, "work_authorization")["result"] == "pass"
    assert result["status"] == "clear"


def test_explicit_sponsorship_answers_beat_status_inference():
    """The typed booleans are the user's literal answers; status only infers."""
    result = scan_job(
        _job(work_authorization="no_sponsorship"),
        WorkAuth(sponsorship_now=False, sponsorship_future=True),
        preferences=None,
    )
    assert _check(result, "work_authorization")["result"] == "conflict"


def test_sponsorship_available_is_a_pass_for_a_visa_holder():
    result = scan_job(
        _job(work_authorization="sponsorship_available"),
        WorkAuth(status="h1b"),
        preferences=None,
    )
    assert _check(result, "work_authorization")["result"] == "pass"


# --- the two honesty rules ---------------------------------------------------

def test_a_fully_unstated_jd_is_unstated_not_clear():
    result = scan_job(_job(), WorkAuth(status="citizen"), preferences=None)
    assert result["status"] == "unstated"
    assert _check(result, "work_authorization")["result"] == "job_unstated"


def test_a_stated_requirement_with_an_empty_profile_is_incomplete_not_clear():
    result = scan_job(
        _job(work_authorization="citizen_or_gc_required"),
        WorkAuth(),
        preferences=None,
    )
    assert _check(result, "work_authorization")["result"] == "profile_missing"
    assert result["status"] == "incomplete_profile"


# --- OPT --------------------------------------------------------------------

def test_opt_holder_conflicts_when_posting_rejects_opt():
    result = scan_job(
        _job(opt_accepted="no"),
        WorkAuth(status="opt"),
        preferences=None,
    )
    assert _check(result, "opt")["result"] == "conflict"
    assert result["status"] == "conflict"


def test_stem_opt_ok_passes_stem_but_conflicts_plain_opt():
    stem = scan_job(_job(opt_accepted="stem_opt_ok"), WorkAuth(status="stem_opt"), None)
    plain = scan_job(_job(opt_accepted="stem_opt_ok"), WorkAuth(status="opt"), None)
    assert _check(stem, "opt")["result"] == "pass"
    assert _check(plain, "opt")["result"] == "conflict"


def test_opt_check_is_omitted_for_non_opt_profiles_when_jd_silent():
    result = scan_job(_job(), WorkAuth(status="citizen"), preferences=None)
    assert not [c for c in result["checks"] if c["kind"] == "opt"]


# --- salary -------------------------------------------------------------------

def test_salary_below_target_warns_but_does_not_block():
    result = scan_job(
        _job(
            work_authorization="sponsorship_available",
            salary_min=Decimal(90000),
            salary_max=Decimal(120000),
            salary_period="year",
        ),
        WorkAuth(status="h1b"),
        preferences={"desired_salary": "$150k"},
    )
    assert _check(result, "salary")["result"] == "warning"
    assert result["status"] == "clear"


def test_salary_at_or_above_target_passes():
    result = scan_job(
        _job(salary_max=Decimal(160000), salary_period="year"),
        WorkAuth(),
        preferences={"desired_salary": "150,000"},
    )
    assert _check(result, "salary")["result"] == "pass"


def test_salary_check_omitted_without_a_parseable_target():
    result = scan_job(
        _job(salary_max=Decimal(160000), salary_period="year"),
        WorkAuth(),
        preferences={"desired_salary": "market rate"},
    )
    assert not [c for c in result["checks"] if c["kind"] == "salary"]


def test_hourly_pay_is_not_compared_to_a_yearly_target():
    result = scan_job(
        _job(salary_max=Decimal(60), salary_period="hour"),
        WorkAuth(),
        preferences={"desired_salary": "150k"},
    )
    assert not [c for c in result["checks"] if c["kind"] == "salary"]


# --- years of experience --------------------------------------------------

def test_experience_below_the_posted_minimum_warns_but_does_not_block():
    """YOE is the classic soft-hard requirement: real ATS knockouts exist, but
    people clear "N+ years" bars with less all the time — warn, never block."""
    result = scan_job(
        _job(work_authorization="sponsorship_available", years_experience_min=5),
        WorkAuth(status="h1b"),
        preferences=None,
        years_experience=2,
    )
    assert _check(result, "experience")["result"] == "warning"
    assert result["status"] == "clear"


def test_experience_meeting_the_minimum_passes():
    result = scan_job(
        _job(years_experience_min=5),
        WorkAuth(),
        preferences=None,
        years_experience=6,
    )
    assert _check(result, "experience")["result"] == "pass"
    assert result["status"] == "clear"


def test_experience_check_omitted_when_profile_years_unset():
    result = scan_job(
        _job(years_experience_min=5), WorkAuth(), preferences=None,
    )
    assert not [c for c in result["checks"] if c["kind"] == "experience"]


def test_experience_check_omitted_when_posting_states_no_minimum():
    result = scan_job(
        _job(), WorkAuth(), preferences=None, years_experience=2,
    )
    assert not [c for c in result["checks"] if c["kind"] == "experience"]


# --- surfaces -----------------------------------------------------------------

def test_job_detail_carries_the_knockout_scan(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile({"work_auth": {"status": "opt"}}, db_session)
    job_preferences.set_preferences(
        JobPreferences(years_experience=2), db_session
    )
    job = _mk_job(db_session, company="ScanCo")
    job.work_authorization = "no_sponsorship"
    job.years_experience_min = 5
    db_session.commit()

    body = client.get(f"/api/jobs/{job.id}/detail").json()
    assert body["knockout"]["status"] == "conflict"
    kinds = {c["kind"]: c["result"] for c in body["knockout"]["checks"]}
    assert kinds["work_authorization"] == "conflict"
    # Job preferences' stated years feed the experience screen on the wire.
    assert kinds["experience"] == "warning"


def test_final_review_carries_the_knockout_scan_and_drops_the_dead_warnings_key(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile({"work_auth": {"status": "citizen"}}, db_session)
    job = _mk_job(db_session, company="ReviewCo", source="agent")
    job.work_authorization = "citizen_or_gc_required"
    db_session.commit()

    pid = client.post("/api/proposals", json={"job_id": str(job.id)}).json()["id"]
    body = client.get(f"/api/proposals/{pid}/final-review").json()

    assert body["knockout"]["status"] == "clear"
    # extracted_json["warnings"] was read here but never written anywhere;
    # the knockout scan replaces that dead concept.
    assert "warnings" not in body["job"]
    assert db_session.get(ApplicationProposal, pid) is not None
