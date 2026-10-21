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
from uuid import UUID

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


# --- salary in one currency (plan Task 3.8) ---------------------------------------
#
# ECB reference rates are units per euro; £60,000 is about €68,415 at 0.8770.
_RATES = {"base": "EUR", "date": "2026-10-19",
          "rates": {"USD": Decimal("1.0870"), "GBP": Decimal("0.8770")}}


def _pay(ceiling, currency, desired, **kw):
    return scan_job(
        _job(salary_max=Decimal(ceiling), salary_period="year", salary_currency=currency),
        WorkAuth(), preferences={"desired_salary": desired}, **kw)


def test_salary_converts_to_one_currency_before_comparing():
    below = _check(_pay(60000, "GBP", "€70,000", home_currency="EUR", rates=_RATES), "salary")
    assert below["result"] == "warning"
    assert below["message"] == "The posted pay tops out below your desired salary."
    assert below["job_value"] == "60000 GBP" and below["profile_value"] == "70000 EUR"
    above = _check(_pay(62000, "GBP", "€70,000", home_currency="EUR", rates=_RATES), "salary")
    assert above["result"] == "pass"   # £62,000 is about €70,695


def test_an_unmarked_desired_salary_is_in_your_home_currency():
    assert _check(_pay(60000, "GBP", "70000", home_currency="EUR", rates=_RATES), "salary")["result"] == "warning"
    # A bare "$" is the dollar of a dozen countries: it names no currency, so the home one stands.
    assert _check(_pay(80000, "USD", "$70k", home_currency="USD", rates=None), "salary")["result"] == "pass"
    assert _check(_pay(80000, "USD", "70000 EUR", home_currency="USD", rates=_RATES),
                  "salary")["result"] == "pass"   # $80,000 is about €73,597


def test_with_no_rate_the_salary_check_cannot_compare_and_never_passes_or_fails():
    for rates, currency in ((None, "GBP"), (_RATES, "ARS")):
        result = _pay(60000, currency, "€70,000", home_currency="EUR", rates=rates)
        check = _check(result, "salary")
        assert check["result"] == "cant_compare"
        assert check["message"] == (f"There's no exchange rate for {currency} yet, so this pay can't be "
                                    "compared with your desired salary.")
        assert result["status"] == "unstated"   # not a pass: nothing was compared


def test_a_job_with_no_currency_cannot_be_compared_with_one_that_has_one():
    check = _check(_pay(60000, None, "70000", home_currency="EUR", rates=_RATES), "salary")
    assert check["result"] == "cant_compare"
    assert check["message"] == "This job's pay names no currency, so it can't be compared with your desired salary."


def test_the_scan_reads_your_home_currency_and_the_rates(db_session, tmp_path, monkeypatch):
    from app.services import fx_rates, knockout, money_settings

    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    monkeypatch.setattr(money_settings, "home_currency", lambda session=None: "EUR")
    monkeypatch.setattr(fx_rates, "current", lambda session: _RATES)
    args = knockout.scan_args(db_session)
    assert args["home_currency"] == "EUR" and args["rates"] == _RATES


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


# --- the words (D §9.3) --------------------------------------------------------
#
# Every message the job page's knock-out card prints (and MCP `get_job`
# relays). The answers these point at live on Profile › Autofill, not Settings
# (D §10.20), and none of them joins two clauses with a semicolon.

_MESSAGES = [
    (dict(work_authorization="citizen_or_gc_required"), WorkAuth(), {},
     "work_authorization",
     "This job requires US citizenship or a green card. Add your work "
     "authorization in Profile › Autofill."),
    (dict(work_authorization="citizen_or_gc_required"), WorkAuth(status="h1b"), {},
     "work_authorization", "This job requires US citizenship or a green card."),
    (dict(work_authorization="no_sponsorship"), WorkAuth(status="h1b"), {},
     "work_authorization",
     "This job doesn't sponsor visas, and you need sponsorship now."),
    (dict(work_authorization="no_sponsorship"), WorkAuth(status="opt"), {},
     "work_authorization",
     "This job doesn't sponsor visas, and you need sponsorship in the future."),
    (dict(work_authorization="no_sponsorship"), WorkAuth(), {},
     "work_authorization",
     "This job doesn't sponsor visas. Answer the sponsorship questions in "
     "Profile › Autofill."),
    (dict(work_authorization="sponsorship_available"), WorkAuth(status="h1b"), {},
     "work_authorization", "This job sponsors visas."),
    (dict(opt_accepted="yes"), WorkAuth(), {}, "opt",
     "This job states an OPT policy. Add your work authorization in Profile › Autofill."),
    (dict(opt_accepted="no"), WorkAuth(status="opt"), {}, "opt",
     "This job doesn't accept OPT."),
    (dict(opt_accepted="stem_opt_ok"), WorkAuth(status="opt"), {}, "opt",
     "This job accepts STEM OPT only."),
    (dict(salary_max=Decimal(120000), salary_period="year"), WorkAuth(),
     {"preferences": {"desired_salary": "$150k"}}, "salary",
     "The posted pay tops out below your desired salary."),
    (dict(years_experience_min=5), WorkAuth(), {"years_experience": 2}, "experience",
     "This job asks for 5+ years. Your profile says 2."),
]


def _scanned_messages() -> list[str]:
    """What `scan_job` actually says for each row of `_MESSAGES`."""
    out = []
    for job_fields, work_auth, extra, kind, _expected in _MESSAGES:
        result = scan_job(_job(**job_fields), work_auth, **{"preferences": None, **extra})
        out.append(_check(result, kind)["message"])
    return out


def test_knockout_messages_read_as_plain_sentences():
    assert _scanned_messages() == [expected for *_rest, expected in _MESSAGES]


def test_knockout_points_to_profile_autofill():
    """Every message that names a place names Profile › Autofill, where the
    work-authorization answers live; none sends the user to Settings."""
    messages = _scanned_messages()
    places = [m for m in messages if " in Profile" in m or " in Settings" in m]
    assert len(places) == 3
    assert [m for m in places if not m.endswith("in Profile › Autofill.")] == []


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
    assert db_session.get(ApplicationProposal, UUID(pid)) is not None


def test_the_job_page_says_it_cannot_compare():
    """The card words the new result itself: a chip and its message row, never a pass."""
    from pathlib import Path

    card = (Path(__file__).resolve().parents[2] / "frontend/components/job-knockout-card.tsx").read_text()
    assert "cant_compare: { icon: NotRunIcon, word: \"Can't compare\"" in card
    assert '"profile_missing", "cant_compare"]' in card   # its message gets a row
