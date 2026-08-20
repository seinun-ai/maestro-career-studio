import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.routers import autofill as autofill_router
from app.services import autofill_profile
from tests.ats.fixtures import SAMPLE_RESUME


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _seed_base(db_session, tmp_path, monkeypatch, slug="data_scientist", resume_json=None):
    resume_json = resume_json or SAMPLE_RESUME
    monkeypatch.setattr(settings, "base_resumes_dir", tmp_path)
    (tmp_path / f"{slug}.json").write_text(json.dumps(resume_json))
    db_session.add(BaseResume(slug=slug, data_json=resume_json))
    db_session.commit()
    return slug


def _seed_application(db_session, slug, customized_json=None):
    job = Job(raw_text="jd", raw_text_hash="autofill-hash", extracted_json={"title": "DS"})
    db_session.add(job)
    db_session.flush()
    application = Application(
        job_id=job.id, base_resume=slug, status="draft", customized_json=customized_json
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


def test_context_bundles_profile_employment_skills_and_eeo(
    db_session, tmp_path, monkeypatch
):
    """The one payload a fill consumes: profile + employment + skills + eeo.

    Asserted against the seeded resume directly — the three single-feed
    endpoints this consolidated are deleted (SYSTEM.md §13 autofill-three-feeds),
    so /context is now the sole contract for this payload.
    """
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile(
        {"personal": {"first_name": "Sample", "email": "a@example.com"}}, db_session
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        combined = TestClient(app).get(f"/api/autofill/context?base={slug}")
    finally:
        app.dependency_overrides.clear()

    assert combined.status_code == 200
    body = combined.json()
    assert set(body) == {"profile", "employment", "skills", "eeo_consent"}
    assert body["profile"]["personal"]["first_name"] == "Sample"
    employers = {block["employer"] for block in body["employment"]}
    assert employers == {
        e["company"] for e in SAMPLE_RESUME["experience"] if e.get("enabled", True)
    }
    flat_skills = [i for g in SAMPLE_RESUME["skills"] for i in g["items"]]
    assert body["skills"] == flat_skills
    assert body["eeo_consent"] == {
        "enabled": False,
        "consent_forms": False,
        "acknowledged_at": None,
        "policy_version": "1",
    }


def test_context_without_a_selector_serves_the_profile_only_fill(
    db_session, tmp_path, monkeypatch
):
    """Neither selector is a REQUEST here, not an error.

    The panel does a profile-only fill whenever both selects are empty, and that
    is a state a real account reaches rather than a malformed call: the base
    dropdown renders `<option value=''>` both when the account has no base
    resumes and when the list fails to load, and the application dropdown does
    the same on a failed load. 400ing this would leave the widget keeping a
    separate /api/settings/autofill round-trip for exactly the case this
    endpoint exists to remove.

    The two resume sections are simply unavailable, which `None` already means —
    no new vocabulary, and the widget reports them as skipped either way. A base
    resume IS seeded here but not selected, so the nulls prove "you did not ask"
    rather than "there was nothing to find".
    """
    _seed_base(db_session, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile(
        {"personal": {"first_name": "Sample", "email": "a@example.com"}}, db_session
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/autofill/context")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"profile", "employment", "skills", "eeo_consent"}
    assert body["profile"]["personal"]["first_name"] == "Sample"
    assert body["employment"] is None
    assert body["skills"] is None
    assert body["eeo_consent"]["enabled"] is False


def test_context_nulls_only_the_section_that_failed(db_session, tmp_path, monkeypatch):
    """One dead feed must not take the other two down with it.

    The three endpoints this replaces degraded independently — a 404 on skills
    still let an employment fill proceed — so combining them must not turn a
    partial outage into a total one. A null section means "this feed is
    unavailable", which the widget reports as skipped, never as filled.
    """
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "settings_dir", tmp_path)

    def _explode(_resume_json):
        raise RuntimeError("skills feed exploded")

    monkeypatch.setattr(autofill_router, "_resume_skills", _explode)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(f"/api/autofill/context?base={slug}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["skills"] is None
    assert [b["employer"] for b in body["employment"]] == ["DataCo", "OldCo"]
    assert body["profile"] is not None


def test_context_degradation_does_not_depend_on_section_order(
    db_session, tmp_path, monkeypatch
):
    """The FIRST section can fail and the other two still return.

    Companion to the skills case above, which fails the last one. What buys the
    independent degradation is one guard per section, not the order they are
    computed in — an earlier version of this handler carried a comment claiming
    the profile was placed first so its failure "cannot take the two in-memory
    computations with it", which was a rationalisation of an ordering that does
    nothing. Pinned from both ends so the claim is the tested one.

    Profile is the section worth naming here anyway: it is the only one that
    touches the DB, so it is the one most likely to fail on its own.
    """
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "settings_dir", tmp_path)

    def _explode(_session):
        raise RuntimeError("profile store exploded")

    monkeypatch.setattr(autofill_router.autofill_profile, "get_profile", _explode)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(f"/api/autofill/context?base={slug}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["profile"] is None
    assert [b["employer"] for b in body["employment"]] == ["DataCo", "OldCo"]
    assert body["skills"][:2] == ["Python", "SQL"]


def test_context_selection_errors_are_not_degraded_to_nulls(
    db_session, tmp_path, monkeypatch
):
    """The degradation stops at the resume SELECTION.

    Both selectors at once, an unknown slug, a missing application: each is a
    caller error about WHICH resume, not an outage in a feed. Answering them 200
    with three nulls would report "all three feeds are down" for what is really
    a bad query string, and hide the one fault the caller can actually fix.

    NEITHER selector is deliberately absent from this list — it is a valid
    profile-only request, pinned by the test below.
    """
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = _seed_application(db_session, slug)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        both = client.get(
            f"/api/autofill/context?application_id={application.id}&base={slug}"
        )
        missing_app = client.get(f"/api/autofill/context?application_id={uuid4()}")
        missing_base = client.get("/api/autofill/context?base=no_such_slug")
    finally:
        app.dependency_overrides.clear()

    assert both.status_code == 400
    assert missing_app.status_code == 404
    assert missing_base.status_code == 404


def test_context_includes_eeo_consent_metadata_and_keeps_profile_eeo_values(
    db_session, tmp_path, monkeypatch
):
    """REST context serves consent metadata + EEO values WHEN CONSENT IS ON.

    The consented half. Its opposite —
    `test_context_withholds_eeo_values_without_consent` — is the one that
    matters for privacy, and the two must be read together: this endpoint is
    what the Companion reads to fill.
    """
    from app.services import eeo_consent
    from app.schemas.eeo_consent import EeoConsent

    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile(
        {
            "personal": {"first_name": "Sample"},
            "eeo": {"gender": "female", "veteran_status": "not_veteran"},
        },
        db_session,
    )
    eeo_consent.set_consent(
        EeoConsent(
            enabled=True,
            acknowledged_at="2026-07-30T12:00:00+00:00",
            policy_version="1",
        ),
        db_session,
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        body = TestClient(app).get("/api/autofill/context").json()
    finally:
        app.dependency_overrides.clear()

    assert body["eeo_consent"] == {
        "enabled": True,
        "consent_forms": False,
        "acknowledged_at": "2026-07-30T12:00:00+00:00",
        "policy_version": "1",
    }
    assert body["profile"]["eeo"]["gender"] == "female"
    assert "gender" not in body["eeo_consent"]



def test_context_withholds_eeo_values_without_consent(db_session, tmp_path, monkeypatch):
    """Protected-class answers leave the server only under standing consent.

    Enforced in the ROUTER since 2026-08-04 (MCP audit, M1). It used to live only
    in `mcp_server/client.py`, so the endpoint answered with race, gender,
    veteran and disability values while `eeo_consent.enabled` was false — and the
    apply lane drives a real browser, which can simply navigate to this URL.
    Which client asks must not decide whether the data is served.

    `eeo_consent` metadata still comes back: the caller has to know the answer is
    "not consented" rather than "no answers stored".
    """
    from app.services import eeo_consent
    from app.schemas.eeo_consent import EeoConsent

    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile(
        {
            "personal": {"first_name": "Sample"},
            "eeo": {"gender": "female", "veteran_status": "not_veteran"},
        },
        db_session,
    )
    eeo_consent.set_consent(EeoConsent(enabled=False, policy_version="1"), db_session)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        body = TestClient(app).get("/api/autofill/context").json()
    finally:
        app.dependency_overrides.clear()

    assert "eeo" not in body["profile"], "EEO answers served without consent"
    assert body["profile"]["personal"]["first_name"] == "Sample"
    assert body["eeo_consent"]["enabled"] is False


def test_context_withholds_eeo_when_the_consent_section_fails(db_session, tmp_path, monkeypatch):
    """Fails closed. A consent section that could not be computed is not consent."""
    from app.services import eeo_consent

    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile(
        {"personal": {"first_name": "Sample"}, "eeo": {"gender": "female"}}, db_session
    )
    monkeypatch.setattr(
        eeo_consent, "get_consent", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        body = TestClient(app).get("/api/autofill/context").json()
    finally:
        app.dependency_overrides.clear()

    assert body["eeo_consent"] is None
    assert "eeo" not in body["profile"]


# ---------- POST /choose — the second fill pass's one model ask ----------


def _post_choose(db_session, payload):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        return TestClient(app).post("/api/autofill/choose", json=payload)
    finally:
        app.dependency_overrides.clear()


def test_choose_returns_a_choice_for_every_qid(db_session, monkeypatch):
    from app.schemas.autofill_choose import Choice
    from app.services import autofill_choose

    monkeypatch.setattr(
        autofill_choose, "choose",
        lambda fields, application_id, session: {
            "a-0": Choice(answer="Yes", reason="matched")
        },
    )
    response = _post_choose(db_session, {
        "fields": [{"qid": "a-0", "label": "Relocate?", "kind": "radio",
                    "options": ["Yes", "No"]}]})
    assert response.status_code == 200
    assert response.json()["choices"]["a-0"] == {"answer": "Yes", "reason": "matched"}


def test_choose_works_with_no_application(db_session, monkeypatch):
    """An untracked form is exactly when you most want this, so application_id
    stays optional — unlike /api/qa, which refuses without one."""
    from app.services import autofill_choose

    monkeypatch.setattr(
        autofill_choose, "choose", lambda fields, application_id, session: {}
    )
    response = _post_choose(db_session, {
        "fields": [{"qid": "a-0", "label": "x", "kind": "text"}]})
    assert response.status_code == 200


def test_an_unknown_application_is_a_404_not_a_silent_ungrounded_answer(db_session):
    from uuid import uuid4

    response = _post_choose(db_session, {
        "fields": [{"qid": "a-0", "label": "x", "kind": "text"}],
        "application_id": str(uuid4())})
    assert response.status_code == 404


def test_an_empty_field_list_is_a_422(db_session):
    assert _post_choose(db_session, {"fields": []}).status_code == 422
