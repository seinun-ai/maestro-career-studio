"""Readiness on the Agent inbox's rows (agent-dashboard-design.md, Part 1)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.base_resume import BaseResume
from app.models.filled_answer import FilledAnswer
from app.models.types import utcnow
from app.services import (
    autofill_profile,
    base_eligibility,
    eeo_consent,
    filled_answers,
    inbox_readiness,
    knockout,
)
from tests.test_proposals_models import _mk_job

TICKED_ALL = {"question": "Which languages?", "answer": ["a", "b", "c"], "options_count": 3,
              "source": "inferred"}


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)


def _proposal(db_session, status="accepted", pdf=None, base="swe", **job):
    job_row = _mk_job(db_session, **job)
    app_id = None
    if pdf is not None:
        app_row = Application(job_id=job_row.id, base_resume=base, pdf_path=pdf)
        db_session.add(app_row)
        db_session.flush()
        app_id = app_row.id
    prop = ApplicationProposal(job_id=job_row.id, status=status, application_id=app_id)
    db_session.add(prop)
    db_session.commit()
    return prop, job_row


def test_tailored_follows_the_linked_application_pdf(db_session):
    rows = [_proposal(db_session, pdf="/x.pdf"), _proposal(db_session, pdf=""),
            _proposal(db_session)]
    got = inbox_readiness.for_proposals(db_session, rows)
    assert [got[p.id]["tailored"] for p, _ in rows] == [True, False, None]


def test_history_rows_get_no_readiness(db_session):
    rows = [_proposal(db_session, status=s)
            for s in ("submitted", "rejected", "expired", "submission_uncertain")]
    assert inbox_readiness.for_proposals(db_session, rows) == {}


def test_to_check_counts_the_flagged_answers(db_session):
    prop, job = _proposal(db_session, status="approved")
    db_session.add(FilledAnswer(job_id=job.id, channel="agent", fields=[TICKED_ALL]))
    db_session.commit()
    got = inbox_readiness.for_proposals(db_session, [(prop, job)])[prop.id]
    assert got["to_check"] == 1 == filled_answers.receipt(db_session, job)["flag_count"]


def test_a_conflicting_knockout_names_its_kind(db_session, monkeypatch):
    monkeypatch.setattr(knockout, "scan_job", lambda job, **_: {
        "status": "conflict", "checks": [{"kind": "salary", "result": "pass"},
                                         {"kind": "on_site", "result": "conflict"}]})
    prop, job = _proposal(db_session)
    assert inbox_readiness.for_proposals(db_session, [(prop, job)])[prop.id]["knockout"] == "on_site"


def test_the_profile_is_read_once_per_batch(db_session, monkeypatch):
    calls = []
    real = knockout.scan_args
    monkeypatch.setattr(knockout, "scan_args", lambda s: calls.append(1) or real(s))
    rows = [_proposal(db_session) for _ in range(3)]
    inbox_readiness.for_proposals(db_session, rows)
    assert calls == [1]


def test_a_row_that_fails_gets_null_and_the_rest_still_read(db_session, monkeypatch, caplog):
    rows = [_proposal(db_session), _proposal(db_session)]
    bad_job = rows[0][1]
    real = knockout.scan_job

    def scan(job, **kw):
        if job.id == bad_job.id:
            raise RuntimeError("boom")
        return real(job, **kw)

    monkeypatch.setattr(knockout, "scan_job", scan)
    got = inbox_readiness.for_proposals(db_session, rows)
    assert got[rows[0][0].id] is None and got[rows[1][0].id] is not None
    assert f"readiness skipped for proposal {rows[0][0].id}" in caplog.text


@pytest.mark.parametrize("readiness, ready", [
    ({"tailored": True, "knockout": None, "to_check": 0}, True),
    ({"tailored": False, "knockout": None, "to_check": 0}, False),
    ({"tailored": None, "knockout": None, "to_check": 0}, False),
    ({"tailored": 1, "knockout": None, "to_check": 0}, False),
    ({"tailored": True, "knockout": "opt", "to_check": 0}, False),
    ({"tailored": True, "knockout": None, "to_check": 2}, False),
    ({"tailored": True, "knockout": None, "to_check": 0, "base_country": "US"}, False),
    ({"tailored": True, "knockout": None, "to_check": 0, "base_country": None}, True),
    (None, False),
])
def test_ready_means_tailored_no_knockout_nothing_to_check(readiness, ready):
    assert inbox_readiness.is_ready(readiness) is ready


@pytest.mark.parametrize("stale_link", [False, True])
def test_a_deleted_linked_application_is_not_tailored(db_session, stale_link):
    prop, job = _proposal(db_session, status="approved", pdf="/x.pdf")
    app_id = prop.application_id
    db_session.delete(db_session.get(Application, app_id))
    db_session.commit()
    db_session.refresh(prop)
    if stale_link:
        prop = ApplicationProposal(id=prop.id, job_id=job.id, status="approved",
                                   application_id=app_id)
    got = inbox_readiness.for_proposals(db_session, [(prop, job)])[prop.id]
    assert got == {"tailored": None, "knockout": None, "to_check": 0, "base_country": None}
    assert inbox_readiness.is_ready(got) is False


def test_latest_answers_across_two_pages_match_the_receipt(db_session):
    prop, job = _proposal(db_session, status="approved", pdf="/x.pdf")
    now = utcnow()
    for index, (step, answer) in enumerate([
        ("/apply/1", ["a", "b", "c"]), ("/apply/2", ["a", "b", "c"]),
        ("/apply/1", ["a"]),
    ]):
        db_session.add(FilledAnswer(job_id=job.id, channel="agent", step=step,
                                    captured_at=now + timedelta(seconds=index),
                                    fields=[{**TICKED_ALL, "answer": answer}]))
    db_session.commit()
    got = inbox_readiness.for_proposals(db_session, [(prop, job)])[prop.id]
    assert got["to_check"] == 1 == filled_answers.receipt(db_session, job)["flag_count"]
    assert filled_answers.flag_count(db_session, job) == 1
    assert inbox_readiness.is_ready(got) is False


@pytest.mark.parametrize("profile", [{}, {"work_auth": None}, {"work_auth": {}}])
def test_missing_work_auth_keeps_the_incomplete_verdict(db_session, profile):
    autofill_profile.set_profile(profile, db_session)
    prop, job = _proposal(db_session, pdf="/x.pdf", work_authorization="citizen_or_gc_required")
    assert knockout.scan_for(db_session, job)["status"] == "incomplete_profile"
    got = inbox_readiness.for_proposals(db_session, [(prop, job)])[prop.id]
    assert got == {"tailored": True, "knockout": None, "to_check": 0, "base_country": None}
    assert inbox_readiness.is_ready(got) is True


def test_an_explicit_empty_flag_profile_does_not_read_saved_values(db_session):
    autofill_profile.set_profile({"personal": {"first_name": "Ada"}}, db_session)
    job = _mk_job(db_session)
    facts, saved = filled_answers.flag_context(db_session, job, {})
    assert "personal.first_name" not in facts
    assert saved == set()
    assert "personal.first_name" in filled_answers.flag_context(db_session, job)[0]


def test_answered_jobs_share_one_disclosable_profile(db_session, monkeypatch):
    rows = [_proposal(db_session) for _ in range(3)]
    for _, job in rows:
        db_session.add(FilledAnswer(job_id=job.id, channel="agent", fields=[TICKED_ALL]))
    db_session.commit()
    calls = []
    real = eeo_consent.disclosable_profile
    monkeypatch.setattr(eeo_consent, "disclosable_profile", lambda s: calls.append(1) or real(s))
    got = inbox_readiness.for_proposals(db_session, rows)
    assert [got[p.id]["to_check"] for p, _ in rows] == [1, 1, 1]
    assert calls == [1]


def test_a_batch_read_failure_returns_null_for_each_open_proposal(db_session, monkeypatch, caplog):
    rows = [_proposal(db_session), _proposal(db_session, status="approved"),
            _proposal(db_session, status="submitted")]

    def fail_scan_args(_session):
        raise RuntimeError("profile unavailable")

    monkeypatch.setattr(knockout, "scan_args", fail_scan_args)
    got = inbox_readiness.for_proposals(db_session, rows)
    open_ids = {prop.id for prop, _job in rows[:2]}
    assert got == {proposal_id: None for proposal_id in open_ids}
    assert "readiness batch skipped" in caplog.text


def test_one_answer_with_two_flags_counts_once(db_session):
    prop, job = _proposal(db_session, status="approved")
    field = {**TICKED_ALL, "question": "Are you authorized to work?"}
    db_session.add(FilledAnswer(job_id=job.id, channel="agent", fields=[field]))
    db_session.commit()
    assert len(filled_answers.agent_flags(db_session, job)[0]["flags"]) == 2
    got = inbox_readiness.for_proposals(db_session, [(prop, job)])[prop.id]
    assert got["to_check"] == 1 == filled_answers.receipt(db_session, job)["flag_count"]


ARCHIVED = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _bases(db_session, **by_slug):
    for slug, countries in by_slug.items():
        archived = slug.startswith("old_")
        db_session.add(BaseResume(slug=slug, data_json={}, countries=countries,
                                  archived_at=ARCHIVED if archived else None))
    db_session.commit()


def _base_country(db_session, base, country, **bases):
    _bases(db_session, **bases)
    pair = _proposal(db_session, pdf="/x.pdf", base=base, country=country)
    return pair, inbox_readiness.for_proposals(db_session, [pair])[pair[0].id]


def test_base_for_another_country_is_marked_and_not_ready(db_session):
    _, got = _base_country(db_session, "india", "US", india=["IN"], us=["US"])
    assert got["base_country"] == "US"
    assert (got["tailored"], got["knockout"], got["to_check"]) == (True, None, 0)
    assert inbox_readiness.is_ready(got) is False


def test_a_base_for_the_jobs_country_is_ready(db_session):
    _, got = _base_country(db_session, "us", "United States", india=["IN"], us=["US"])
    assert got["base_country"] is None
    assert inbox_readiness.is_ready(got) is True


def test_fallback_base_is_not_marked(db_session):
    _, got = _base_country(db_session, "india", "US", india=["IN"])
    assert got["base_country"] is None
    assert inbox_readiness.is_ready(got) is True


def test_archived_base_judged_by_its_own_countries(db_session):
    _, got = _base_country(db_session, "old_india", "US", old_india=["IN"], us=["US"])
    assert got["base_country"] == "US"


@pytest.mark.parametrize("country", [None, "Remote", ""])
def test_no_job_country_no_mark(db_session, country):
    _, got = _base_country(db_session, "india", country, india=["IN"], us=["US"])
    assert got["base_country"] is None


def test_no_linked_application_no_mark(db_session):
    _bases(db_session, india=["IN"], us=["US"])
    pair = _proposal(db_session, country="US")
    assert inbox_readiness.for_proposals(db_session, [pair])[pair[0].id]["base_country"] is None


@pytest.mark.parametrize("base, country, bases", [
    ("us", "US", {"us": ["US"], "india": ["IN"]}),
    ("india", "US", {"us": ["US"], "india": ["IN"]}),         # sibling is eligible: marked
    ("india", "US", {"india": ["IN"]}),                       # fallback: not marked
    ("anywhere", "US", {"anywhere": [], "us": ["US"]}),
    ("old_india", "US", {"old_india": ["IN"], "us": ["US"]}),  # archived, own countries
    ("old_us", "US", {"old_us": ["US"], "india": ["IN"]}),
    ("ghost", "US", {"us": ["US"]}),                          # no row: eligible
    ("india", "us", {"india": ["IN"], "us": ["US"]}),
    ("india", "United States", {"india": ["IN"], "us": ["US"]}),
    ("india", "Remote", {"india": ["IN"], "us": ["US"]}),
    ("india", None, {"india": ["IN"], "us": ["US"]}),
])
def test_readiness_base_country_agrees_with_is_eligible(db_session, base, country, bases):
    (_, job), got = _base_country(db_session, base, country, **bases)
    assert (got["base_country"] is None) == base_eligibility.is_eligible(db_session, job, base)


def test_readiness_batch_reads_base_countries_once(db_session, monkeypatch):
    from sqlalchemy import event

    _bases(db_session, india=["IN"], uk=["GB"], us=["US"])
    rows = [_proposal(db_session, pdf="/x.pdf", base=b, country="US")
            for b in ("india", "uk", "us", "india")]
    fallbacks = []
    real = base_eligibility.candidates_for_country
    monkeypatch.setattr(base_eligibility, "candidates_for_country",
                        lambda s, c, **kw: fallbacks.append(c) or real(s, c, **kw))
    statements = []
    engine = db_session.get_bind()

    def count(conn, cursor, statement, *args):
        if "base_resumes" in statement:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        got = inbox_readiness.for_proposals(db_session, rows)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert [got[p.id]["base_country"] for p, _ in rows] == ["US", "US", None, "US"]
    assert fallbacks == ["US"]
    # one read of the bases' countries, one fallback read for the one job country
    assert len(statements) == 2
