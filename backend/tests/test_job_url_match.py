from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.job import Job
from app.services.job_url_match import is_same_posting


LEVER = "https://jobs.lever.co/acme/abc"
GREENHOUSE = "https://boards.greenhouse.io/acme/jobs/123"


@pytest.mark.parametrize(
    ("saved", "current", "expected"),
    [
        # --- the same posting ---
        # Identical link: the unambiguous case.
        (LEVER, LEVER, True),
        # Referral/tracking params and fragments name the SAME posting. The
        # browser version compared raw pathnames and would have called these
        # new postings, which is how a library accumulates duplicate saves.
        (LEVER, "https://jobs.lever.co/acme/abc?gh_src=x", True),
        (LEVER, "https://jobs.lever.co/acme/abc#apply", True),
        (LEVER, "https://jobs.lever.co/acme/abc/", True),
        # Scheme is not identity: an http->https upgrade is the same posting.
        ("http://jobs.lever.co/acme/abc", LEVER, True),
        # Hostnames compare case-insensitively.
        ("https://Jobs.Lever.CO/acme/abc", LEVER, True),
        # --- the four ATS shapes this redesign exists for ---
        # Applying navigates DOWN from the posting. Under the old scoring both
        # of these apply pages scored 12 and 13, indistinguishable from the
        # sibling postings below them; containment separates them by direction.
        (LEVER, f"{LEVER}/apply", True),
        (GREENHOUSE, f"{GREENHOUSE}/application", True),
        # Siblings share a prefix but neither contains the other. The
        # greenhouse sibling also scored 12 — the same integer as the lever
        # apply page, which is the collision that made a threshold impossible.
        (GREENHOUSE, "https://boards.greenhouse.io/acme/jobs/456", False),
        (LEVER, "https://jobs.lever.co/acme/xyz", False),
        # --- reverse direction: saved is more specific than current ---
        # The employer index is an ANCESTOR of the saved posting. Matching the
        # reverse direction would claim a search listing is the job.
        (LEVER, "https://jobs.lever.co/acme", False),
        (f"{LEVER}/apply", LEVER, False),
        # --- rejected outright ---
        # Same employer and posting slug on a different ATS is not this posting.
        (LEVER, "https://boards.greenhouse.io/acme/abc", False),
        # Nothing below the employer slug in common.
        (LEVER, "https://jobs.lever.co/other/xyz", False),
        # A pathless saved link is a prefix of every page on the host under
        # naive prefix logic. Multi-tenant ATS hosts front thousands of
        # unrelated employers, so this must match nothing at all.
        ("https://jobs.lever.co", LEVER, False),
        ("https://jobs.lever.co/", LEVER, False),
        # Malformed and missing input does not match, and does not raise:
        # source_url is user-supplied and the caller is a hot path with no
        # error channel. None is included explicitly because jobs may have no
        # source_url and the signature admits it.
        (None, LEVER, False),
        (LEVER, None, False),
        ("not a url", LEVER, False),
        (LEVER, "not a url", False),
        ("", LEVER, False),
        (LEVER, "", False),
        ("http://[", LEVER, False),
        (LEVER, "http://[", False),
    ],
)
def test_is_same_posting(saved, current, expected):
    assert is_same_posting(saved, current) is expected


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _job(source_url: str | None, tag: str) -> Job:
    return Job(
        raw_text=f"JD {tag}",
        raw_text_hash=f"url-match-{tag}",
        source_url=source_url,
        company="Acme",
        title="Data Scientist",
        location="Dallas, TX",
        extracted_at=datetime.now(UTC),
    )


def test_match_exact_url_returns_job_and_newest_application(db_session):
    job = _job(LEVER, "exact")
    db_session.add(job)
    db_session.flush()
    # created_at is set explicitly: its server_default is now(), which in
    # Postgres is the TRANSACTION timestamp, so rows inserted together would
    # tie and "newest" would be decided by nothing.
    older = Application(
        job_id=job.id, base_resume="ds", status="draft",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = Application(
        job_id=job.id, base_resume="ds", status="applied",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    db_session.add_all([older, newer])
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(
            "/api/jobs/match", params={"url": f"{LEVER}?gh_src=x"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["match"] == "exact"
    assert body["job"]["id"] == str(job.id)
    assert body["job"]["source_url"] == LEVER
    # The newest application wins, not merely any application.
    assert body["application"]["id"] == str(newer.id)
    assert body["application"]["status"] == "applied"
    # ApplicationSummary carries flat joined job fields, not a nested job.
    assert body["application"]["job_company"] == "Acme"
    assert body["application"]["job_title"] == "Data Scientist"


def test_match_unknown_page_returns_none(db_session):
    # The NULL-source_url row is here to show a link-less job is harmless, not
    # to guard anything: is_same_posting(None, ...) returns False rather than
    # raising. The router's .is_not(None) filter narrows the scan; it has no
    # correctness role, and removing it leaves this test green.
    db_session.add_all([_job(LEVER, "unknown"), _job(None, "no-link")])
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(
            "/api/jobs/match", params={"url": "https://news.example.com/article/1"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["match"] == "none"
    assert body["job"] is None
    assert body["application"] is None


def test_match_sibling_posting_is_none(db_session):
    """The case the two-state redesign exists for. Under the old scoring this
    sibling scored 12 — the same integer as a saved posting's own apply page —
    and surfaced as `likely`, a job the user could accept. Neither path
    contains the other, so containment rejects it outright."""
    db_session.add(_job(GREENHOUSE, "sibling"))
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(
            "/api/jobs/match",
            params={"url": "https://boards.greenhouse.io/acme/jobs/456"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["match"] == "none"
    assert body["job"] is None
    assert body["application"] is None


def test_match_apply_page_is_exact(db_session):
    # The other side of that collision: applying navigates DOWN from the saved
    # posting, so the apply page IS the posting. The job has no application, so
    # a hit must still serialize application: null.
    job = _job(GREENHOUSE, "apply-page")
    db_session.add(job)
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(
            "/api/jobs/match", params={"url": f"{GREENHOUSE}/application"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["match"] == "exact"
    assert body["job"]["id"] == str(job.id)
    assert body["application"] is None


def test_match_employer_index_page_is_none(db_session):
    # Navigating UP to the employer's listing must not claim to be the job.
    # The saved path is longer, so it is not a prefix of the current path.
    db_session.add(_job(LEVER, "ancestor"))
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(
            "/api/jobs/match", params={"url": "https://jobs.lever.co/acme"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["match"] == "none"


def test_match_empty_url_is_none_not_422(db_session):
    # The endpoint fires on navigation rather than on user intent, so a blank
    # tab URL is an ordinary event. Answer "none" instead of raising a client
    # error the extension would have to special-case. Pinned because the route
    # deliberately omits Query(min_length=1).
    db_session.add(_job(LEVER, "empty-url"))
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/jobs/match", params={"url": ""})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["match"] == "none"


def test_match_ties_resolve_to_the_newest_capture(db_session):
    # Job boards reuse a URL across successive postings, so two rows sharing a
    # source_url is a reachable state and both match. Without an explicit scan
    # order the winner would be whatever Postgres happened to return.
    older = _job(LEVER, "tie-old")
    older.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    newer = _job(LEVER, "tie-new")
    newer.created_at = datetime(2026, 6, 1, tzinfo=UTC)
    db_session.add_all([older, newer])
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/jobs/match", params={"url": LEVER})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["match"] == "exact"
    assert body["job"]["id"] == str(newer.id)
