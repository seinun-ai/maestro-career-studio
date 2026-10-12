from datetime import UTC, datetime

import pytest

from app.models.application import Application
from app.models.job import Job
from app.services.job_url_match import is_same_posting, posting_id, strip_tracking_params


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


# --- posting identity carried in the QUERY STRING -------------------------
#
# LinkedIn's job list is one path for every job: clicking a result rewrites
# `?currentJobId=` via pushState and nothing else moves. Under the prefix rule
# every job on that page was the first one saved, so the panel registered one
# application for the whole session (reported 2026-09-01). The same shape
# exists on Indeed (`viewjob?jk=`, search `vjk=`) and on Greenhouse boards
# embedded in a company site (`careers?gh_jid=`).

LI_SEARCH = "https://www.linkedin.com/jobs/search/?currentJobId=4001&keywords=data"
LI_VIEW = "https://www.linkedin.com/jobs/view/4001/"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (LI_SEARCH, ("www.linkedin.com", "4001")),
        ("https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4001",
         ("www.linkedin.com", "4001")),
        # The permalink carries the same id in its PATH; a slugged permalink
        # ends in the id too.
        (LI_VIEW, ("www.linkedin.com", "4001")),
        ("https://www.linkedin.com/jobs/view/data-engineer-at-acme-4001", ("www.linkedin.com", "4001")),
        ("https://www.linkedin.com/jobs/view/4001/?refId=abc&trk=x", ("www.linkedin.com", "4001")),
        ("https://www.indeed.com/viewjob?jk=abc123&from=serp", ("www.indeed.com", "abc123")),
        ("https://www.indeed.com/jobs?q=data&vjk=abc123", ("www.indeed.com", "abc123")),
        ("https://acme.example/careers?gh_jid=555", ("acme.example", "555")),
        # No identity in the query: an ordinary posting URL, a tracking param,
        # an empty id, and the LinkedIn list with nothing selected.
        (LEVER, None),
        ("https://jobs.lever.co/acme/abc?gh_src=x", None),
        ("https://www.linkedin.com/jobs/search/?currentJobId=&keywords=data", None),
        ("https://www.linkedin.com/jobs/search/?keywords=data", None),
        # Only LinkedIn's /jobs/view/ path is an id carrier; a look-alike path
        # on another host is not.
        ("https://example.com/jobs/view/4001/", None),
        (None, None),
        ("http://[", None),
    ],
)
def test_posting_id(url, expected):
    assert posting_id(url) == expected


@pytest.mark.parametrize(
    ("saved", "current", "expected"),
    [
        # The bug: two jobs on LinkedIn's one-path search page.
        (LI_SEARCH, "https://www.linkedin.com/jobs/search/?currentJobId=4002&keywords=data", False),
        # The same job, reached three ways.
        (LI_SEARCH, LI_VIEW, True),
        (LI_VIEW, LI_SEARCH, True),
        (LI_VIEW, "https://www.linkedin.com/jobs/view/4001/?refId=abc", True),
        # Saved from the permalink, viewing a different permalink: siblings.
        (LI_VIEW, "https://www.linkedin.com/jobs/view/4002/", False),
        # A saved id, a current page with none: the list with nothing
        # selected is not the posting.
        (LI_SEARCH, "https://www.linkedin.com/jobs/search/?keywords=data", False),
        # Greenhouse embed: the careers page with no id is the INDEX, not the job.
        ("https://acme.example/careers?gh_jid=555", "https://acme.example/careers", False),
        ("https://acme.example/careers?gh_jid=555", "https://acme.example/careers?gh_jid=556", False),
        ("https://acme.example/careers?gh_jid=555", "https://acme.example/careers?gh_jid=555&utm=x", True),
        # Indeed: the search page with the same job selected IS the job.
        ("https://www.indeed.com/viewjob?jk=abc123", "https://www.indeed.com/jobs?q=data&vjk=abc123", True),
        # Ids belong to a host: the same number on another site is nothing.
        (LI_VIEW, "https://www.indeed.com/viewjob?jk=4001", False),
        # No id on the SAVED side keeps the prefix rule exactly as before —
        # an apply page that adds an id param still descends from its posting.
        (LEVER, f"{LEVER}/apply?jobId=9", True),
    ],
)
def test_is_same_posting_with_query_identity(saved, current, expected):
    assert is_same_posting(saved, current) is expected


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


def test_match_exact_url_returns_job_and_newest_application(db_session, client):
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

    response = client.get(
        "/api/jobs/match", params={"url": f"{LEVER}?gh_src=x"}
    )

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


def test_match_names_the_application_base_resume_even_after_a_delete(db_session, client):
    from app.models.base_resume import BaseResume

    job = _job(LEVER, "named")
    db_session.add(job)
    db_session.add(
        BaseResume(
            slug="ds_named",
            display_name="Data science base",
            data_json={"contact": {"name": "Ada Madeup"}},
            deleted_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
    )
    db_session.flush()
    db_session.add(Application(job_id=job.id, base_resume="ds_named", status="applied"))
    db_session.commit()

    response = client.get("/api/jobs/match", params={"url": LEVER})

    # Same joined name as GET /api/applications: a soft-deleted base keeps it.
    assert response.json()["application"]["base_resume_name"] == "Data science base"


def test_match_unknown_page_returns_none(db_session, client):
    # The NULL-source_url row is here to show a link-less job is harmless, not
    # to guard anything: is_same_posting(None, ...) returns False rather than
    # raising. The router's .is_not(None) filter narrows the scan; it has no
    # correctness role, and removing it leaves this test green.
    db_session.add_all([_job(LEVER, "unknown"), _job(None, "no-link")])
    db_session.commit()

    response = client.get(
        "/api/jobs/match", params={"url": "https://news.example.com/article/1"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["match"] == "none"
    assert body["job"] is None
    assert body["application"] is None


def test_match_sibling_posting_is_none(db_session, client):
    """The case the two-state redesign exists for. Under the old scoring this
    sibling scored 12 — the same integer as a saved posting's own apply page —
    and surfaced as `likely`, a job the user could accept. Neither path
    contains the other, so containment rejects it outright."""
    db_session.add(_job(GREENHOUSE, "sibling"))
    db_session.commit()

    response = client.get(
        "/api/jobs/match",
        params={"url": "https://boards.greenhouse.io/acme/jobs/456"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["match"] == "none"
    assert body["job"] is None
    assert body["application"] is None


def test_match_apply_page_is_exact(db_session, client):
    # The other side of that collision: applying navigates DOWN from the saved
    # posting, so the apply page IS the posting. The job has no application, so
    # a hit must still serialize application: null.
    job = _job(GREENHOUSE, "apply-page")
    db_session.add(job)
    db_session.commit()

    response = client.get(
        "/api/jobs/match", params={"url": f"{GREENHOUSE}/application"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["match"] == "exact"
    assert body["job"]["id"] == str(job.id)
    assert body["application"] is None


def test_match_employer_index_page_is_none(db_session, client):
    # Navigating UP to the employer's listing must not claim to be the job.
    # The saved path is longer, so it is not a prefix of the current path.
    db_session.add(_job(LEVER, "ancestor"))
    db_session.commit()

    response = client.get(
        "/api/jobs/match", params={"url": "https://jobs.lever.co/acme"}
    )

    assert response.status_code == 200
    assert response.json()["match"] == "none"


def test_match_empty_url_is_none_not_422(db_session, client):
    # The endpoint fires on navigation rather than on user intent, so a blank
    # tab URL is an ordinary event. Answer "none" instead of raising a client
    # error the extension would have to special-case. Pinned because the route
    # deliberately omits Query(min_length=1).
    db_session.add(_job(LEVER, "empty-url"))
    db_session.commit()

    response = client.get("/api/jobs/match", params={"url": ""})

    assert response.status_code == 200
    assert response.json()["match"] == "none"


def test_match_ties_resolve_to_the_newest_capture(db_session, client):
    # Job boards reuse a URL across successive postings, so two rows sharing a
    # source_url is a reachable state and both match. Without an explicit scan
    # order the winner would be whatever Postgres happened to return.
    older = _job(LEVER, "tie-old")
    older.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    newer = _job(LEVER, "tie-new")
    newer.created_at = datetime(2026, 6, 1, tzinfo=UTC)
    db_session.add_all([older, newer])
    db_session.commit()

    response = client.get("/api/jobs/match", params={"url": LEVER})


    assert response.status_code == 200
    body = response.json()
    assert body["match"] == "exact"
    assert body["job"]["id"] == str(newer.id)


# ---------------------------------------------------------------------------
# strip_tracking_params — unit tests
# ---------------------------------------------------------------------------
#
# Specification:
#   - UTM family (any key starting with utm_) is removed.
#   - TRACKING_PARAM_KEYS entries (gh_src, refId, trk, ref, src, source, from,
#     ss, rsid) are removed.
#   - POSTING_ID_QUERY_KEYS (currentJobId, jk, vjk, gh_jid) are PRESERVED —
#     stripping them would merge two different postings into one URL.
#   - Whitespace-only or None input returns None.
#   - Unparseable URLs are returned unchanged and never raise.
#   - Fragment (#apply) is preserved; the function only touches query strings.
#   - A URL with no query string is returned unchanged.

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # --- tracking params removed ---
        # UTM family
        (
            f"{LEVER}?utm_source=linkedin&utm_medium=organic",
            LEVER,
        ),
        (
            f"{LEVER}?utm_campaign=spring&utm_content=job",
            LEVER,
        ),
        # Greenhouse referral source
        (
            f"{LEVER}?gh_src=abc123",
            LEVER,
        ),
        # LinkedIn referral / tracking
        (
            "https://www.linkedin.com/jobs/view/4001/?refId=x&trk=public_jobs_topcard",
            "https://www.linkedin.com/jobs/view/4001/",
        ),
        # Generic referral keys
        (
            f"{LEVER}?ref=indeed&src=organic&source=jobboard",
            LEVER,
        ),
        # Indeed click-tracking
        (
            "https://www.indeed.com/viewjob?jk=abc123&from=serp",
            "https://www.indeed.com/viewjob?jk=abc123",
        ),
        # Mixed: some tracking, some non-tracking
        (
            f"{LEVER}?utm_source=email&keepme=1",
            f"{LEVER}?keepme=1",
        ),
        # Compound: multiple tracking keys
        (
            f"{LEVER}?gh_src=x&utm_source=y&utm_medium=z",
            LEVER,
        ),
        # --- posting-identity keys PRESERVED ---
        # LinkedIn currentJobId must survive (it IS the posting identity)
        (
            "https://www.linkedin.com/jobs/search/?currentJobId=4001&utm_source=email",
            "https://www.linkedin.com/jobs/search/?currentJobId=4001",
        ),
        # Indeed jk must survive
        (
            "https://www.indeed.com/viewjob?jk=abc123&utm_campaign=spring",
            "https://www.indeed.com/viewjob?jk=abc123",
        ),
        # Indeed vjk must survive
        (
            "https://www.indeed.com/jobs?q=data&vjk=abc123&utm_source=x",
            "https://www.indeed.com/jobs?q=data&vjk=abc123",
        ),
        # Greenhouse gh_jid must survive (different from gh_src)
        (
            "https://acme.example/careers?gh_jid=555&gh_src=referral",
            "https://acme.example/careers?gh_jid=555",
        ),
        # --- no query string — returned as-is ---
        (LEVER, LEVER),
        (GREENHOUSE, GREENHOUSE),
        # --- fragment preserved, tracking still removed ---
        (
            f"{LEVER}?utm_source=x#apply",
            f"{LEVER}#apply",
        ),
        # --- edge cases ---
        # Whitespace stripped, no params → LEVER without trailing space
        (f"  {LEVER}  ", LEVER),
        # None → None
        (None, None),
        # Empty string → None
        ("", None),
        # Whitespace-only → None
        ("   ", None),
        # Unparseable URL returned unchanged (never raises)
        ("not a url", "not a url"),
        ("http://[", "http://["),
    ],
)
def test_strip_tracking_params(raw, expected):
    assert strip_tracking_params(raw) == expected


# ---------------------------------------------------------------------------
# Router-level integration: tracking params stripped at every write path
# ---------------------------------------------------------------------------
#
# These tests exercise the full HTTP path to confirm that strip_tracking_params
# is wired into every endpoint that stores source_url (create, ingest, patch).


def _minimal_extraction():
    return {
        "company": "Acme",
        "title": "Data Engineer",
        "role_category": "data_engineer",
        "level": "mid",
        "employment_type": "full_time",
        "work_mode": "remote",
        "location_raw": "Remote",
        "work_authorization": "unstated",
        "opt_accepted": "unstated",
        "skills": [],
        "responsibilities": [],
        "qualifications": [],
    }


def test_create_strips_tracking_params(db_session, monkeypatch, client):
    """POST /api/jobs stores source_url without tracking params."""
    from app.routers import jobs as jobs_module

    monkeypatch.setattr(
        jobs_module.jd_extraction,
        "extract_jd",
        lambda raw_text, session=None: _minimal_extraction(),
    )

    dirty = f"{LEVER}?utm_source=linkedin&gh_src=referral"
    response = client.post("/api/jobs", json={"raw_text": "JD text", "source_url": dirty})

    assert response.status_code == 200
    assert response.json()["source_url"] == LEVER


def test_ingest_strips_tracking_params(db_session, client):
    """POST /api/jobs/ingest stores source_url without tracking params."""
    dirty = f"{GREENHOUSE}?utm_campaign=spring&gh_src=abc"
    response = client.post(
        "/api/jobs/ingest",
        json={
            "extracted_json": _minimal_extraction(),
            "raw_text": "ingest JD text",
            "source_url": dirty,
        },
    )

    assert response.status_code == 200
    assert response.json()["source_url"] == GREENHOUSE


def test_patch_strips_tracking_params(db_session, client):
    """PATCH /api/jobs/{id} stores source_url without tracking params."""
    # Seed a job without a source_url, then patch in a dirty one.
    job = _job(None, "patch-strip")
    db_session.add(job)
    db_session.commit()

    dirty = f"{LEVER}?utm_source=email&trk=jobpost&ref=homepage"
    response = client.patch(f"/api/jobs/{job.id}", json={"source_url": dirty})

    assert response.status_code == 200
    assert response.json()["source_url"] == LEVER


def test_patch_preserves_posting_id_keys(db_session, client):
    """PATCH /api/jobs/{id} does NOT strip posting-identity query keys."""
    job = _job(None, "patch-preserve-id")
    db_session.add(job)
    db_session.commit()

    # gh_jid is a posting identity on Greenhouse-embedded boards — must survive.
    url_with_id = "https://acme.example/careers?gh_jid=555&utm_source=email"
    response = client.patch(f"/api/jobs/{job.id}", json={"source_url": url_with_id})

    assert response.status_code == 200
    stored = response.json()["source_url"]
    assert "gh_jid=555" in stored
    assert "utm_source" not in stored


def test_create_preserves_linkedin_currentjobid(db_session, monkeypatch, client):
    """POST /api/jobs preserves currentJobId (LinkedIn posting identity)."""
    from app.routers import jobs as jobs_module

    monkeypatch.setattr(
        jobs_module.jd_extraction,
        "extract_jd",
        lambda raw_text, session=None: _minimal_extraction(),
    )

    url = "https://www.linkedin.com/jobs/search/?currentJobId=4001&utm_source=email"
    response = client.post("/api/jobs", json={"raw_text": "LI JD", "source_url": url})

    assert response.status_code == 200
    stored = response.json()["source_url"]
    assert "currentJobId=4001" in stored
    assert "utm_source" not in stored


def test_list_jobs_filter_strips_tracking_params(db_session, client):
    """GET /api/jobs?source_url= with tracking params still finds the stored job."""
    # The job was stored without tracking params (strip happened on create/ingest).
    job = _job(LEVER, "list-filter-strip")
    db_session.add(job)
    db_session.commit()

    # Query with a dirty URL; the filter should strip before the WHERE clause.
    dirty = f"{LEVER}?utm_source=email&gh_src=ref"
    response = client.get("/api/jobs", params={"source_url": dirty})

    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert str(job.id) in ids
