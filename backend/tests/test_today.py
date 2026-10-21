"""Today (GET /api/today): the one next-up item in a fixed order, the counts behind it and this week,
every number from a reader that already exists, and nothing written."""

from datetime import UTC, datetime, timedelta, timezone
import uuid

import pytest

from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.application_status_event import ApplicationStatusEvent
from app.models.ats_score import AtsScore
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.models.resume_lint_report import ResumeLintReport
from app.models.tailoring_session import TailoringSession
from app.services import resume_versions, today

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)  # a Wednesday
DRAFT = {"basics": {"name": "Sample Person"}}


def _job(db, title="Product Designer", company="Northwind", **fields) -> Job:
    job = Job(raw_text=f"JD {uuid.uuid4().hex}", raw_text_hash=uuid.uuid4().hex, title=title,
              company=company, created_at=NOW - timedelta(days=5), **fields)
    db.add(job)
    db.flush()
    return job


def _app(db, job: Job, *, status="draft", base="alpha", **fields) -> Application:
    row = Application(job_id=job.id, base_resume=base, status=status, **fields)
    db.add(row)
    db.flush()
    return row


def _event(db, app_row, to_status, at, *, from_status=None, backfilled=False):
    db.add(ApplicationStatusEvent(application_id=app_row.id, from_status=from_status,
                                  to_status=to_status, at=at, backfilled=backfilled,
                                  source="backfill" if backfilled else "you"))
    db.flush()


def _tailored_score(db, app_row, composite):
    db.add(AtsScore(job_id=app_row.job_id, target_type="application", target_id=str(app_row.id),
                    application_id=app_row.id, phase="tailored", composite=composite,
                    subscores_json={}, skill_table_json=[], config_version="c1", engine_version="e1"))
    db.flush()


def _pdf_ready(db, score: float, title="Product Designer") -> Application:
    row = _app(db, _job(db, title=title), customized_json=DRAFT, pdf_path=f"/tmp/{uuid.uuid4().hex}.pdf")
    _tailored_score(db, row, score)
    return row


def _offer(db) -> Application:
    applied = NOW - timedelta(days=20)
    row = _app(db, _job(db, title="Design Lead"), status="offered", applied_at=applied)
    _event(db, row, "applied", applied, from_status="draft")
    _event(db, row, "interviewing", applied + timedelta(days=6), from_status="applied")
    _event(db, row, "offered", applied + timedelta(days=15), from_status="interviewing")
    return row


def _needs_you(db, **fields) -> ApplicationProposal:
    prop = ApplicationProposal(job_id=_job(db, title="UX Researcher").id, status="needs_decision",
                               fit_json={"chosen_base": "alpha", "scores": {"alpha": 72}},
                               reason="Which start date should I give?", proposed_by="claude-ai",
                               **fields)
    db.add(prop)
    db.flush()
    return prop


def _build(db, **kwargs):
    db.commit()
    return today.build(db, now=NOW, **kwargs)


# ---------------------------------------------------------------------------- next up


def test_nothing_to_do_means_no_next_up(db_session):
    body = _build(db_session)
    assert body["next_up"] is None
    assert body["also"] == [] and body["more"] == []
    assert [d["applied"] for d in body["week"]["days"]] == [0] * 7
    assert body["week"]["days"][-1]["date"] == "2026-10-21"
    assert (body["week"]["applied"], body["week"]["replies"], body["week"]["interviews"]) == (0, 0, 0)
    assert body["week"]["applied_all_time"] == 0
    assert body["time_zone"] == "UTC" and body["today"] == "2026-10-21"


def test_the_order_rule_is_a_named_constant():
    assert today.NEXT_UP_ORDER == ("offer", "pdf_ready", "needs_you")
    assert today.QUIET_FOLLOW_UP_DAYS == 14


def test_an_offer_awaiting_a_response_wins_over_a_ready_pdf_and_a_question(db_session):
    db_session.add(BaseResume(slug="alpha", display_name="Product Designer", color_hue=230, data_json={}))
    offer = _offer(db_session)
    _tailored_score(db_session, offer, 77.0)
    _pdf_ready(db_session, 90.0)
    _needs_you(db_session)

    item = _build(db_session)["next_up"]
    assert item["kind"] == "offer"
    assert item["application_id"] == str(offer.id) and item["proposal_id"] is None
    assert (item["title"], item["company"], item["status"]) == ("Design Lead", "Northwind", "offered")
    assert item["base_resume"] == {"slug": "alpha", "name": "Product Designer", "color_hue": 230}
    assert item["score"] == 77.0
    keys = [step["key"] for step in item["steps"]]
    assert keys == ["saved", "applied", "interviewing", "offered"]
    assert item["steps"][-1]["at"] == (NOW - timedelta(days=5)).isoformat()


def test_an_offer_with_only_a_backfilled_event_keeps_its_status_but_no_dates(db_session):
    row = _app(db_session, _job(db_session), status="offered", applied_at=NOW - timedelta(days=30))
    _event(db_session, row, "offered", NOW - timedelta(days=2), backfilled=True)
    item = _build(db_session)["next_up"]
    assert item["kind"] == "offer"
    assert [step["key"] for step in item["steps"]] == ["saved", "applied"]


def test_a_ready_pdf_with_the_best_match_wins_over_a_question(db_session):
    _pdf_ready(db_session, 61.0, title="Weaker match")
    best = _pdf_ready(db_session, 84.0, title="Best match")
    session = TailoringSession(job_id=best.job_id, base_resume="alpha", status="tailored",
                               gaps_json={"categories": []}, application_id=best.id,
                               updated_at=NOW - timedelta(days=3))
    db_session.add(session)
    db_session.flush()
    version = resume_versions.record_version(db_session, "application", str(best.id), DRAFT,
                                             source="tailor", summary="Tailored")
    version.created_at = NOW - timedelta(days=3)
    # Not a ready PDF: sent already, closed, or only a draft.
    _app(db_session, _job(db_session), status="applied", applied_at=NOW, customized_json=DRAFT,
         pdf_path="/tmp/sent.pdf")
    _app(db_session, _job(db_session), status="withdrawn", customized_json=DRAFT, pdf_path="/tmp/w.pdf")
    _needs_you(db_session)

    item = _build(db_session)["next_up"]
    assert item["kind"] == "pdf_ready"
    assert (item["application_id"], item["title"], item["score"]) == (str(best.id), "Best match", 84.0)
    assert item["base_resume"] == {"slug": "alpha", "name": None, "color_hue": None}
    assert [step["key"] for step in item["steps"]] == ["saved", "gaps_closed", "tailored"]


def test_a_question_from_an_agent_comes_last(db_session):
    prop = _needs_you(db_session)
    item = _build(db_session)["next_up"]
    assert item["kind"] == "needs_you"
    assert item["proposal_id"] == str(prop.id) and item["application_id"] is None
    assert (item["title"], item["status"], item["proposed_by"]) == ("UX Researcher", "needs_decision", "claude-ai")
    assert item["reason"] == "Which start date should I give?"
    assert item["base_resume"]["slug"] == "alpha" and item["score"] == 72
    assert [step["key"] for step in item["steps"]] == ["saved", "proposed"]


def test_a_question_past_its_expiry_is_not_next_and_nothing_is_written(db_session, client):
    stale = _needs_you(db_session, expires_at=NOW - timedelta(days=1))
    db_session.commit()
    assert today.build(db_session, now=NOW)["next_up"] is None

    assert client.get("/api/today").status_code == 200
    db_session.expire_all()
    # Reads never write: the Agent inbox's own read expires it, not Today.
    assert db_session.get(ApplicationProposal, stale.id).status == "needs_decision"


# ---------------------------------------------------------------------------- the counts


def test_also_and_more_counts_come_from_the_existing_readers(db_session):
    # Agent jobs to approve: the inbox's To review count.
    for _ in range(3):
        db_session.add(ApplicationProposal(job_id=_job(db_session).id, status="pending_review"))
    # Tailored resumes to check: the "tailored" rung (a draft, no PDF yet).
    for _ in range(2):
        _app(db_session, _job(db_session), customized_json=DRAFT)
    # Quiet 14 days: sent 14+ days ago with nothing since; a newer one and a rejected one are not.
    for days in (15, 20):
        row = _app(db_session, _job(db_session), status="applied", applied_at=NOW - timedelta(days=days))
        _event(db_session, row, "applied", row.applied_at, from_status="draft")
    _app(db_session, _job(db_session), status="applied", applied_at=NOW - timedelta(days=10))
    rejected = _app(db_session, _job(db_session), status="rejected", applied_at=NOW - timedelta(days=25))
    _event(db_session, rejected, "rejected", NOW - timedelta(days=5), from_status="applied")
    # Gaps to close: a job with an open gap analysis, two of its three gaps still open.
    gaps = {"categories": [{"key": "missing", "gaps": [{"gap_id": "g1"}, {"gap_id": "g2"}, {"gap_id": "g3"}]}]}
    db_session.add(TailoringSession(job_id=_job(db_session).id, base_resume="alpha", status="open",
                                    gaps_json=gaps, resolutions_json=[{"gap_id": "g1"}]))
    # Resumes to health check: never checked, or changed since; a checked one is not counted.
    db_session.add_all([
        BaseResume(slug="fresh", display_name="Fresh", data_json={}),
        BaseResume(slug="checked", display_name="Checked", data_json={}),
        BaseResume(slug="gone", display_name="Archived", data_json={}, archived_at=NOW),
    ])
    db_session.flush()
    db_session.add(ResumeLintReport(resume_kind="base", resume_key="checked", report_json={}))

    body = _build(db_session)
    assert body["also"] == [
        {"key": "to_approve", "count": 3, "href": "/proposals"},
        {"key": "to_check", "count": 2, "href": "/applications?stage=tailored"},
        {"key": "quiet", "count": 2, "days": 14, "href": "/applications?status=applied"},
    ]
    assert body["more"] == [
        {"key": "gaps_to_close", "count": 1, "gaps": 2, "href": "/applications?stage=gaps"},
        {"key": "health_check", "count": 1, "href": "/base-resumes/fresh/health"},
    ]

    resume_versions.record_version(db_session, "base", "checked", {"basics": {}}, source="form_edit")
    more = _build(db_session)["more"]
    assert more[-1] == {"key": "health_check", "count": 2, "href": "/base-resumes"}


# ---------------------------------------------------------------------------- this week


def test_this_week_counts_local_days(db_session):
    # 23:30 UTC on Tuesday is 01:30 on Wednesday in Berlin (UTC+2 until the end of October).
    late = _app(db_session, _job(db_session), status="applied", applied_at=datetime(2026, 10, 20, 23, 30, tzinfo=UTC))
    _event(db_session, late, "applied", late.applied_at, from_status="draft")
    replied = _app(db_session, _job(db_session), status="interviewing", applied_at=NOW - timedelta(days=30))
    _event(db_session, replied, "applied", replied.applied_at, from_status="draft")
    _event(db_session, replied, "interviewing", NOW - timedelta(days=2), from_status="applied")
    rejected = _app(db_session, _job(db_session), status="rejected", applied_at=NOW - timedelta(days=9))
    _event(db_session, rejected, "rejected", NOW - timedelta(days=1), from_status="applied")
    # Backfilled: a status with no real date is in no day of the week.
    old = _app(db_session, _job(db_session), status="rejected", applied_at=NOW - timedelta(days=3))
    _event(db_session, old, "rejected", NOW, backfilled=True)
    db_session.commit()

    utc = today.build(db_session, now=NOW)["week"]
    assert [d["date"] for d in utc["days"]] == [f"2026-10-{n}" for n in range(15, 22)]
    assert utc["days"][-2]["applied"] == 1 and utc["days"][-1]["applied"] == 0  # Tuesday
    assert (utc["applied"], utc["replies"], utc["interviews"]) == (2, 2, 1)
    assert utc["applied_all_time"] == 4

    zone, label = today.local_zone("Europe/Berlin", None)
    berlin = today.build(db_session, now=NOW, zone=zone, zone_label=label)
    assert berlin["time_zone"] == "Europe/Berlin"
    assert berlin["week"]["days"][-1]["applied"] == 1 and berlin["week"]["days"][-2]["applied"] == 0

    zone, label = today.local_zone(None, 120)
    assert label == "UTC+02:00"
    shifted = today.build(db_session, now=NOW, zone=zone, zone_label=label)["week"]
    assert shifted["days"][-1]["applied"] == 1


def test_local_zone_validates_and_falls_back_to_the_offset():
    assert today.local_zone(None, None) == (UTC, "UTC")
    assert today.local_zone(None, -300) == (timezone(timedelta(minutes=-300)), "UTC-05:00")
    # A well-formed name this server's zone database lacks takes the offset the page also sent.
    assert today.local_zone("Mars/Olympus_Mons", 60) == (timezone(timedelta(minutes=60)), "UTC+01:00")
    for bad in ("Mars/Olympus_Mons", "../../etc/passwd", "Europe/Berlin;", ""):
        with pytest.raises(ValueError):
            today.local_zone(bad, None)


@pytest.mark.parametrize("query", ["tz=Not/AZone", "tz=..%2Fetc", "utc_offset_minutes=900",
                                   "utc_offset_minutes=-721", "utc_offset_minutes=abc"])
def test_the_route_refuses_a_bad_time_zone(client, query):
    assert client.get(f"/api/today?{query}").status_code == 422


def test_the_route_answers_with_a_time_zone(client):
    body = client.get("/api/today?tz=Asia/Kolkata&utc_offset_minutes=330").json()
    assert body["time_zone"] == "Asia/Kolkata" and body["next_up"] is None
    assert len(body["week"]["days"]) == 7
    assert client.get("/api/today?utc_offset_minutes=330").json()["time_zone"] == "UTC+05:30"
