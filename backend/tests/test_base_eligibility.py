from datetime import datetime, timezone

from app.models.base_resume import BaseResume
from app.models.job import Job
from app.services.base_eligibility import (
    candidates,
    candidates_for_country,
    country_eligible,
    is_eligible,
)


def _bases(db_session, **by_slug):
    for slug, countries in by_slug.items():
        db_session.add(BaseResume(slug=slug, data_json={}, countries=countries))
    db_session.flush()


def _job(db_session, country):
    job = Job(raw_text="jd", raw_text_hash=f"elig-{country}", country=country)
    db_session.add(job)
    db_session.flush()
    return job


def test_country_eligible_table():
    assert country_eligible(["IN"], None) and country_eligible([], "US")
    assert country_eligible(["US", "CA"], "US") and not country_eligible(["IN"], "US")


def test_candidates_filters_and_falls_back(db_session):
    _bases(db_session, india=["IN"], us=["US"], anywhere=[])

    got = candidates_for_country(db_session, "US")
    assert (got.slugs, got.skipped, got.fallback, got.job_country) == (
        ["anywhere", "us"], ["india"], False, "US")

    # the job's own free text goes through the normalizer
    assert candidates(db_session, _job(db_session, "us")).skipped == ["india"]

    # unknown country: nothing is filtered
    got = candidates(db_session, _job(db_session, "Remote"))
    assert (got.slugs, got.skipped, got.fallback, got.job_country) == (
        ["anywhere", "india", "us"], [], False, None)

    # the user asked for every base
    got = candidates_for_country(db_session, "US", include_other_countries=True)
    assert (got.slugs, got.skipped, got.fallback) == (["anywhere", "india", "us"], [], False)


def test_candidates_fall_back_when_the_filter_leaves_nothing(db_session):
    _bases(db_session, india=["IN"])
    got = candidates_for_country(db_session, "US")
    assert (got.slugs, got.skipped, got.fallback, got.job_country) == (["india"], [], True, "US")


def test_candidates_ignore_archived_and_deleted_bases(db_session):
    _bases(db_session, kept=[])
    t = datetime(2026, 8, 4, tzinfo=timezone.utc)
    db_session.add_all([
        BaseResume(slug="archived", data_json={}, countries=["IN"], archived_at=t),
        BaseResume(slug="deleted", data_json={}, countries=["IN"], deleted_at=t),
    ])
    db_session.flush()
    got = candidates_for_country(db_session, "US")
    assert (got.slugs, got.skipped, got.fallback) == (["kept"], [], False)


def test_candidates_for_country_reads_the_countries_in_one_query(db_session):
    from sqlalchemy import event

    _bases(db_session, a=["IN"], b=["US"], c=[])
    statements = []
    engine = db_session.get_bind()

    def count(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        candidates_for_country(db_session, "US")
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert len(statements) == 1


def test_is_eligible_uses_the_base_own_countries_even_when_archived(db_session):
    _bases(db_session, us=["US"], anywhere=[])
    db_session.add(BaseResume(
        slug="old_india", data_json={}, countries=["IN"],
        archived_at=datetime(2026, 8, 4, tzinfo=timezone.utc)))
    db_session.add(BaseResume(
        slug="old_us", data_json={}, countries=["US"],
        archived_at=datetime(2026, 8, 4, tzinfo=timezone.utc)))
    db_session.flush()
    job = _job(db_session, "US")

    assert is_eligible(db_session, job, "us") and is_eligible(db_session, job, "anywhere")
    assert is_eligible(db_session, job, "old_us")
    assert not is_eligible(db_session, job, "old_india")
    assert not is_eligible(db_session, job, "no_such_base")


def test_is_eligible_is_true_for_every_base_in_fallback(db_session):
    _bases(db_session, india=["IN"])
    assert is_eligible(db_session, _job(db_session, "US"), "india")
