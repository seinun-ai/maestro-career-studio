"""The search summary behind Analytics' lead and tiles (GET /api/explore/search-summary): what
happened to the applications you sent, read from the dated status-event log
(docs/entities/application.md, "Status-event log"), with rates only from 20 (owner decision D7)."""

from datetime import UTC, datetime, timedelta
import uuid

import pytest

from app.models.application import Application
from app.models.application_status_event import ApplicationStatusEvent
from app.models.ats_score import AtsScore
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.services import rates, search_summary
from app.services.explore_activity import week_start

# A Wednesday noon, so "this week" started two and a half days before.
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def test_wilson_range_matches_the_textbook_and_hides_below_twenty():
    low, high = rates.wilson(12, 64)
    assert round(low, 3) == 0.111 and round(high, 3) == 0.300
    assert rates.rate(12, 64) == {"count": 12, "of": 64, "rate": 0.1875, "low": low, "high": high}
    assert rates.rate(5, 12) == {"count": 5, "of": 12, "rate": None, "low": None, "high": None}


def test_wilson_stays_inside_zero_and_one_at_the_edges():
    assert rates.wilson(0, 0) == (0.0, 0.0)
    low, high = rates.wilson(0, 25)
    assert low == pytest.approx(0.0, abs=1e-12) and 0.0 < high < 0.2
    low, high = rates.wilson(25, 25)
    assert 0.8 < low < 1.0 and high == pytest.approx(1.0, abs=1e-12)
    assert 0.0 <= low and high <= 1.0
    # The minimum itself shows a rate: "from 20", not "above 20".
    assert rates.rate(rates.MIN_RATE_N, rates.MIN_RATE_N)["rate"] == 1.0
    assert rates.rate(3, rates.MIN_RATE_N - 1)["rate"] is None


# ---------------------------------------------------------------------------- seeding


def _job(db, title: str = "Analyst") -> Job:
    job = Job(raw_text=f"JD {uuid.uuid4().hex}", raw_text_hash=uuid.uuid4().hex, title=title,
              company="Acme")
    db.add(job)
    db.flush()
    return job


def _applied(db, *, at: datetime, base: str = "alpha", source: str = "user",
             status: str = "applied", record_applied: bool = True) -> Application:
    """An application sent at `at`, with the event saying so (as set_status writes it)."""
    app_row = Application(job_id=_job(db).id, base_resume=base, source=source, status=status,
                          applied_at=at, created_at=at - timedelta(hours=2))
    db.add(app_row)
    db.flush()
    if record_applied:
        _event(db, app_row, "applied", at, from_status="draft")
    return app_row


def _event(db, app_row: Application, to_status: str, at: datetime, *, from_status: str | None = None,
           backfilled: bool = False) -> None:
    db.add(ApplicationStatusEvent(application_id=app_row.id, from_status=from_status,
                                  to_status=to_status, at=at,
                                  source="backfill" if backfilled else "you",
                                  backfilled=backfilled))
    db.flush()


def _reply(db, app_row: Application, to_status: str, days_after: float, *,
           from_status: str = "applied") -> None:
    app_row.status = to_status
    _event(db, app_row, to_status, app_row.applied_at + timedelta(days=days_after),
           from_status=from_status)


def _seed_twenty_five(db) -> list[Application]:
    """25 applications sent over seven weeks, every other one with resume alpha. Six real replies
    (3, 5, 7, 9, 11, 13 days after applying: four rejections and two interviews, one of which became
    an offer) and three applications whose only event is a backfilled one (rejected, applied,
    interviewing): those count for status, never for timing."""
    db.add(BaseResume(slug="alpha", display_name="Product Designer", color_hue=230, data_json={}))
    apps = [_applied(db, at=NOW - timedelta(days=2 * i, hours=1), base="alpha" if i % 2 == 0 else "beta")
            for i in range(25)]
    _reply(db, apps[10], "rejected", 3)
    _reply(db, apps[11], "rejected", 5)
    _reply(db, apps[12], "interviewing", 7)
    _reply(db, apps[13], "interviewing", 9)
    _reply(db, apps[13], "offered", 20, from_status="interviewing")
    _reply(db, apps[14], "rejected", 11)
    _reply(db, apps[15], "rejected", 13)
    for i, status in ((20, "rejected"), (21, "applied"), (22, "interviewing")):
        db.query(ApplicationStatusEvent).filter_by(application_id=apps[i].id).delete()
        apps[i].status = status
        _event(db, apps[i], status, NOW - timedelta(days=1), backfilled=True)
    db.commit()
    return apps


# ---------------------------------------------------------------------------- the summary


def test_summary_counts_from_events(db_session):
    _seed_twenty_five(db_session)
    # Not sent: a draft has no applied_at and is never in the summary.
    db_session.add(Application(job_id=_job(db_session).id, base_resume="alpha", status="draft"))
    db_session.commit()

    body = search_summary.build(db_session, weeks=12, source=None, now=NOW)

    assert body["applied"] == 25
    # 6 real replies plus the backfilled rejected and interviewing ones.
    assert body["heard_back"] == rates.rate(8, 25)
    assert body["heard_back"]["rate"] == 0.32 and body["heard_back"]["low"] is not None
    assert body["interview"] == rates.rate(3, 8)  # apps 12, 13 and the backfilled interviewing one
    assert body["offer"] == rates.rate(1, 3)

    # Timing reads the six real replies only: 3, 5, 7, 9, 11, 13 days.
    timing = body["time_to_hear_back"]
    assert timing["replies"] == 6
    assert timing["median_days"] == 8.0
    assert (timing["p25_days"], timing["p75_days"]) == (5.5, 10.5)

    # Sent 30+ days ago: apps 15..24 (10). Quiet: no event after applying (16-19, 23, 24 and the
    # backfilled "applied" 21); 15 was rejected, 20 and 22 heard back.
    assert body["quiet"] == {"after_days": 30, **rates.rate(7, 10)}

    # Seven weeks of sending inside a twelve-week window: every week is a row, zero-filled.
    series = body["series"]
    assert len(series) == 12
    this_monday = week_start(NOW.date())
    assert series[-1]["week_start"] == this_monday.isoformat()
    assert series[0]["week_start"] == (this_monday - timedelta(weeks=11)).isoformat()
    assert sum(row["applied"] for row in series) == 25
    assert [row["applied"] for row in series[:4]] == [0, 0, 0, 0]
    # The six dated first replies land in their weeks; the two backfilled ones have no date.
    assert sum(row["replies"] for row in series) == 6
    assert body["undated_replies"] == 2

    assert body["applied_per_week"] == round(25 / 12, 1)
    assert body["weeks"] == 12 and body["window_start"] == series[0]["week_start"]

    by_resume = {row["slug"]: row for row in body["by_resume"]}
    assert [row["slug"] for row in body["by_resume"]] == ["alpha", "beta"]  # most sent first
    alpha = by_resume["alpha"]
    assert (alpha["name"], alpha["color_hue"], alpha["applied"]) == ("Product Designer", 230, 13)
    assert alpha["heard_back"] == rates.rate(5, 13)  # 10, 12, 14 and the backfilled 20, 22
    assert alpha["interview"] == rates.rate(2, 13)
    beta = by_resume["beta"]
    assert (beta["name"], beta["color_hue"], beta["applied"]) == (None, None, 12)
    assert beta["heard_back"] == rates.rate(3, 12)
    assert beta["interview"] == rates.rate(1, 12)

    assert body["min_rate_n"] == rates.MIN_RATE_N
    assert body["min_replies_for_timing"] == search_summary.MIN_REPLIES_FOR_TIMING == 5


def test_time_to_hear_back_waits_for_five_real_replies(db_session):
    apps = [_applied(db_session, at=NOW - timedelta(days=40 - i)) for i in range(6)]
    for i, days in enumerate((2, 4, 6, 8)):
        _reply(db_session, apps[i], "rejected", days)
    # Jumping straight from draft to interviewing stamps applied_at at that moment: the reply has no
    # real waiting time, so it counts as heard back but not for timing.
    jumped = _applied(db_session, at=NOW - timedelta(days=3), status="interviewing", record_applied=False)
    _event(db_session, jumped, "interviewing", jumped.applied_at, from_status="draft")
    db_session.commit()

    body = search_summary.build(db_session, weeks=12, source=None, now=NOW)
    assert body["heard_back"]["count"] == 5
    assert body["time_to_hear_back"] == {"replies": 4, "median_days": None, "p25_days": None,
                                         "p75_days": None}

    _reply(db_session, apps[4], "interviewing", 10)
    db_session.commit()
    timing = search_summary.build(db_session, weeks=12, source=None, now=NOW)["time_to_hear_back"]
    assert timing["replies"] == 5 and timing["median_days"] == 6.0


def test_quiet_counts_only_applications_thirty_days_old(db_session):
    _applied(db_session, at=NOW - timedelta(days=29, hours=23))  # not yet 30 days: not counted at all
    _applied(db_session, at=NOW - timedelta(days=31))
    withdrawn = _applied(db_session, at=NOW - timedelta(days=45))
    _reply(db_session, withdrawn, "withdrawn", 2)  # your own move is an event after applying
    db_session.commit()

    body = search_summary.build(db_session, weeks=12, source=None, now=NOW)
    assert body["applied"] == 3
    assert (body["quiet"]["count"], body["quiet"]["of"]) == (1, 2)


def test_the_window_and_all_time(db_session):
    _applied(db_session, at=NOW - timedelta(days=2))
    _applied(db_session, at=NOW - timedelta(days=40))
    old = _applied(db_session, at=NOW - timedelta(days=200))
    _reply(db_session, old, "rejected", 4)
    db_session.commit()

    four = search_summary.build(db_session, weeks=4, source=None, now=NOW)
    assert four["applied"] == 1 and len(four["series"]) == 4
    twelve = search_summary.build(db_session, weeks=12, source=None, now=NOW)
    assert twelve["applied"] == 2
    # The reply to the 200-day-old application came long before the window: not in its weeks.
    assert sum(row["replies"] for row in twelve["series"]) == 0

    everything = search_summary.build(db_session, weeks=None, source=None, now=NOW)
    assert everything["weeks"] is None and everything["applied"] == 3
    assert everything["window_start"] == week_start((NOW - timedelta(days=200)).date()).isoformat()
    assert everything["series"][0]["week_start"] == everything["window_start"]
    assert everything["series"][-1]["week_start"] == week_start(NOW.date()).isoformat()
    assert sum(row["applied"] for row in everything["series"]) == 3
    assert sum(row["replies"] for row in everything["series"]) == 1
    assert everything["applied_per_week"] == round(3 / len(everything["series"]), 1)
    assert everything["heard_back"]["count"] == 1


def test_all_time_with_nothing_sent_is_one_empty_week(db_session):
    body = search_summary.build(db_session, weeks=None, source=None, now=NOW)
    assert body["applied"] == 0 and body["applied_per_week"] == 0.0
    assert body["series"] == [{"week_start": week_start(NOW.date()).isoformat(), "applied": 0, "replies": 0}]
    assert body["heard_back"] == rates.rate(0, 0)
    assert body["score_gain"] == {"n": 0, "median": None, "median_base": None, "median_tailored": None}
    assert body["by_resume"] == []


def _score(db, app_row: Application, base: float, tailored: float, *, at: datetime) -> None:
    common = dict(subscores_json={}, skill_table_json=[], config_version="c1", engine_version="e1")
    db.add_all([
        AtsScore(job_id=app_row.job_id, target_type="base_resume", target_id=app_row.base_resume,
                 phase="base", composite=base, created_at=at, **common),
        AtsScore(job_id=app_row.job_id, target_type="application", target_id=str(app_row.id),
                 application_id=app_row.id, phase="tailored", composite=tailored, created_at=at,
                 **common),
    ])


def test_source_filters_every_figure_and_score_gain(db_session):
    mine = _applied(db_session, at=NOW - timedelta(days=5), source="user")
    theirs = _applied(db_session, at=NOW - timedelta(days=6), source="agent", base="beta")
    _reply(db_session, theirs, "interviewing", 1)
    _score(db_session, mine, 40.0, 50.0, at=NOW - timedelta(days=5))
    _score(db_session, theirs, 40.0, 70.0, at=NOW - timedelta(days=6))
    db_session.commit()

    everyone = search_summary.build(db_session, weeks=12, source=None, now=NOW)
    assert everyone["applied"] == 2 and everyone["heard_back"]["count"] == 1
    assert everyone["score_gain"] == {"n": 2, "median": 20.0, "median_base": 40.0, "median_tailored": 60.0}

    agents = search_summary.build(db_session, weeks=12, source="agent", now=NOW)
    assert agents["applied"] == 1 and agents["interview"]["count"] == 1
    assert agents["score_gain"] == {"n": 1, "median": 30.0, "median_base": 40.0, "median_tailored": 70.0}
    assert [row["slug"] for row in agents["by_resume"]] == ["beta"]
    assert sum(row["replies"] for row in agents["series"]) == 1

    yours = search_summary.build(db_session, weeks=12, source="user", now=NOW)
    assert yours["applied"] == 1 and yours["heard_back"]["count"] == 0
    assert yours["score_gain"]["median"] == 10.0
    assert sum(row["replies"] for row in yours["series"]) == 0


def test_score_gain_counts_tailoring_inside_the_window(db_session):
    recent = _applied(db_session, at=NOW - timedelta(days=3))
    old = _applied(db_session, at=NOW - timedelta(days=150))
    _score(db_session, recent, 50.0, 60.0, at=NOW - timedelta(days=3))
    _score(db_session, old, 30.0, 70.0, at=NOW - timedelta(days=150))
    db_session.commit()

    assert search_summary.build(db_session, weeks=12, source=None, now=NOW)["score_gain"]["n"] == 1
    assert search_summary.build(db_session, weeks=None, source=None, now=NOW)["score_gain"] == {
        "n": 2, "median": 25.0, "median_base": 40.0, "median_tailored": 65.0}


# ---------------------------------------------------------------------------- the route


def test_the_route_reads_weeks_and_source(db_session, client):
    _applied(db_session, at=datetime.now(UTC) - timedelta(days=1), source="agent")
    db_session.commit()

    body = client.get("/api/explore/search-summary").json()
    assert body["weeks"] == 12 and body["source"] == "all" and body["applied"] == 1
    assert len(body["series"]) == 12
    assert client.get("/api/explore/search-summary?weeks=4&source=user").json()["applied"] == 0
    assert client.get("/api/explore/search-summary?source=agent").json()["source"] == "agent"
    everything = client.get("/api/explore/search-summary?weeks=all")
    assert everything.status_code == 200 and everything.json()["weeks"] is None


@pytest.mark.parametrize("query", ["weeks=0", "weeks=521", "weeks=abc", "weeks=-3", "source=x"])
def test_the_route_refuses_a_bad_period_or_source(client, query):
    assert client.get(f"/api/explore/search-summary?{query}").status_code == 422
