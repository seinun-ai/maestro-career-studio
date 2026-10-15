"""POST /api/autofill/map, /pick and /step — what the routes decide before the services run."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.application_proposal import ApplicationProposal
from app.models.job import Job
from app.schemas.autofill_fill import Mapped, Picked, StepResponse
from app.schemas.eeo_consent import EeoConsent
from app.services import (
    autofill_choose,
    autofill_map,
    autofill_pick,
    autofill_profile,
    autofill_step,
    eeo_consent,
    llm,
    model_settings,
)
from tests.ats.fixtures import SAMPLE_RESUME
from tests.test_autofill_router import _override_db, _seed_application, _seed_base

PROFILE = {"personal": {"city": "Springfield"}, "eeo": {"gender": "female"}}
MAP_FIELD = {"fid": "a", "question": "City", "shape": "text"}
PICK_FIELD = {"fid": "g", "question": "Gender", "route": "slot", "slot": "eeo.gender",
              "options": [{"oid": "o1", "text": "Female"}, {"oid": "o2", "text": "Male"}]}


@pytest.fixture
def profile(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile(PROFILE, db_session)


def _post(db_session, path, payload):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        return TestClient(app).post(path, json=payload)
    finally:
        app.dependency_overrides.clear()


def _answer(got):
    """An answer without its decision trace and polarity (both serialize as None until a
    model decides) and a /step `term` nothing wrote: these pins are about what the route
    answered, not how it was decided."""
    return {k: v for k, v in got.items() if k not in ("trace", "polarity") and not (k == "term" and v is None)}


def _spy_map(monkeypatch):
    seen = {}

    def map_fields(fields, facts, session, **kw):
        seen.update(facts=facts, kw=kw)
        return {f.fid: Mapped(route="none") for f in fields}

    monkeypatch.setattr(autofill_map, "map_fields", map_fields)
    return seen


def _spy_pick(monkeypatch):
    seen = {}

    def pick(fields, facts, session, hint, **kw):
        seen.update(facts=facts, hint=hint, kw=kw)
        return {f.fid: Picked(oids=[], reason="abstained") for f in fields}

    monkeypatch.setattr(autofill_pick, "pick", pick)
    return seen


@pytest.mark.usefixtures("profile")
def test_map_builds_facts_from_the_consent_gated_profile(db_session, monkeypatch):
    seen = _spy_map(monkeypatch)
    r = _post(db_session, "/api/autofill/map", {"fields": [MAP_FIELD]})
    assert r.status_code == 200
    assert set(r.json()) == {"fields"}
    assert {k: _answer(v) for k, v in r.json()["fields"].items()} == {
        "a": {"route": "none", "slot": None, "value": None, "format": None, "why": None, "years": False, "draft": False}}
    assert "personal.city" in seen["facts"]
    assert not [slot for slot in seen["facts"] if slot.startswith("eeo")]
    # No answer-level row reads the default level, "history", which has low-stakes answers on.
    assert seen["kw"] == {"eeo_consented": False, "low_stakes": True, "level": "history", "queued": False}


@pytest.mark.usefixtures("profile")
def test_map_with_standing_consent_has_eeo_facts_and_says_so(db_session, monkeypatch):
    eeo_consent.set_consent(EeoConsent(enabled=True, policy_version="1"), db_session)
    seen = _spy_map(monkeypatch)
    assert _post(db_session, "/api/autofill/map", {"fields": [MAP_FIELD]}).status_code == 200
    assert seen["facts"]["eeo.gender"].value == "Female"
    assert seen["kw"]["eeo_consented"] is True


@pytest.mark.usefixtures("profile")
def test_unreadable_consent_fails_closed(db_session, monkeypatch):
    eeo_consent.set_consent(EeoConsent(enabled=True, policy_version="1"), db_session)
    monkeypatch.setattr(eeo_consent, "get_consent",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    seen = _spy_map(monkeypatch)
    assert _post(db_session, "/api/autofill/map", {"fields": [MAP_FIELD]}).status_code == 200
    assert "eeo.gender" not in seen["facts"] and seen["kw"]["eeo_consented"] is False


AGREES = "derived.agrees_to_terms"


@pytest.mark.usefixtures("profile")
@pytest.mark.parametrize("stored, present", [
    (None, False),                                                   # never given
    (EeoConsent(consent_forms=False), False),                        # off
    (EeoConsent(consent_forms=True, policy_version="1"), False),     # lapsed: agreed under policy 1
    (EeoConsent(consent_forms=True, policy_version="2"), True),      # on, under policy 2
])
def test_agreeing_to_terms_is_a_fact_only_while_the_agreement_permission_is_on(db_session, monkeypatch,
                                                                               stored, present):
    if stored is not None:
        eeo_consent.EEO_CONSENT.set(stored, db_session)
    for path, body, spy in (("/api/autofill/map", {"fields": [MAP_FIELD]}, _spy_map),
                            ("/api/autofill/pick", {"fields": [PICK_FIELD]}, _spy_pick)):
        seen = spy(monkeypatch)
        assert _post(db_session, path, body).status_code == 200
        assert (AGREES in seen["facts"]) is present, path


@pytest.mark.usefixtures("profile")
def test_an_unreadable_agreement_permission_is_no_agreement(db_session, monkeypatch):
    eeo_consent.EEO_CONSENT.set(EeoConsent(consent_forms=True, policy_version="2"), db_session)
    monkeypatch.setattr(eeo_consent, "get_consent",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    seen = _spy_map(monkeypatch)
    assert _post(db_session, "/api/autofill/map", {"fields": [MAP_FIELD]}).status_code == 200
    assert AGREES not in seen["facts"]


@pytest.mark.usefixtures("profile")
def test_map_reads_low_stakes_from_the_setting_not_the_client(db_session, monkeypatch):
    seen = _spy_map(monkeypatch)
    model_settings.set_answer_level(db_session, "history")
    assert _post(db_session, "/api/autofill/map", {"fields": [MAP_FIELD]}).status_code == 200
    assert seen["kw"]["low_stakes"] is True
    assert _post(db_session, "/api/autofill/map",
                 {"fields": [MAP_FIELD], "low_stakes": False}).status_code == 422


ACME_URL = "https://careers.acme.example/jobs/7/apply"


def _queued_job(db_session, tmp_path, monkeypatch, *, apply_url=None, source_url=None, status="accepted"):
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = _seed_application(db_session, slug)
    job = db_session.get(Job, application.job_id)
    job.apply_url, job.source_url = apply_url, source_url
    db_session.add(ApplicationProposal(job_id=job.id, application_id=application.id, status=status))
    db_session.commit()
    return application


POSTING = "https://careers.acme.example/jobs/7"
GREENHOUSE = "https://job-boards.greenhouse.io/acme/jobs/4001"


@pytest.mark.usefixtures("profile")
@pytest.mark.parametrize("urls, page_url, queued", [
    ({"apply_url": POSTING}, POSTING, True),  # the apply link
    ({"apply_url": POSTING}, f"{POSTING}/apply", True),  # its apply sub-path is the same posting
    ({"apply_url": POSTING}, f"{POSTING}/apply?utm_source=x#top", True),
    ({"source_url": "https://jobs.example.test/acme/7"}, "https://jobs.example.test/acme/7/apply", True),  # the source link
    ({"apply_url": "https://elsewhere.example/a", "source_url": POSTING}, POSTING, True),  # either one
    # One host, one tenant, many employers' postings: the restored application is not this page's job.
    ({"apply_url": GREENHOUSE}, "https://job-boards.greenhouse.io/acme/jobs/4002/apply", False),
    ({"apply_url": GREENHOUSE}, "https://job-boards.greenhouse.io/acme/jobs/4001/apply", True),
    ({"apply_url": "https://careers.acme.example/jobs/8"}, f"{POSTING}/apply", False),  # a sibling posting
    ({"apply_url": POSTING}, "https://careers.globex.example/jobs/7", False),  # another host
    ({"apply_url": POSTING}, "https://careers.acme.example.evil.test/jobs/7", False),
    ({"apply_url": POSTING}, None, False),  # no page address
    ({}, POSTING, False),  # the job has no link to match
])
def test_a_job_is_queued_only_on_its_own_posting(db_session, monkeypatch, tmp_path, urls, page_url, queued):
    application = _queued_job(db_session, tmp_path, monkeypatch, **urls)
    model_settings.set_answer_level(db_session, "queued")
    seen = _spy_map(monkeypatch)
    body = {"application_id": str(application.id), "fields": [MAP_FIELD]}
    assert _post(db_session, "/api/autofill/map", {**body, **({"page_url": page_url} if page_url else {})}
                 ).status_code == 200
    assert seen["kw"]["queued"] is queued


@pytest.mark.usefixtures("profile")
def test_a_matching_site_without_an_accepted_proposal_is_not_queued(db_session, monkeypatch, tmp_path):
    application = _queued_job(db_session, tmp_path, monkeypatch, apply_url="https://careers.acme.example/jobs/7",
                              status="pending_review")
    seen = _spy_map(monkeypatch)
    _post(db_session, "/api/autofill/map",
          {"application_id": str(application.id), "fields": [MAP_FIELD], "page_url": ACME_URL})
    assert seen["kw"]["queued"] is False


@pytest.mark.usefixtures("profile")
def test_map_and_pick_pass_the_answer_level_and_whether_the_job_is_queued(db_session, monkeypatch, tmp_path):
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = _seed_application(db_session, slug)
    db_session.get(Job, application.job_id).apply_url = "https://careers.acme.example/jobs/7"
    db_session.commit()
    model_settings.set_answer_level(db_session, "queued")
    seen_map, seen_pick = _spy_map(monkeypatch), _spy_pick(monkeypatch)
    body = {"application_id": str(application.id), "fields": [MAP_FIELD], "page_url": ACME_URL}
    pick_body = {"application_id": str(application.id), "fields": [PICK_FIELD], "page_url": ACME_URL}

    def asked():
        assert _post(db_session, "/api/autofill/map", body).status_code == 200
        assert _post(db_session, "/api/autofill/pick", pick_body).status_code == 200
        return seen_map["kw"]["queued"], seen_pick["kw"]["queued"]

    assert asked() == (False, False)  # no proposal: not a Queued job
    proposal = ApplicationProposal(job_id=application.job_id, application_id=application.id, status="pending_review")
    db_session.add(proposal)
    db_session.commit()
    assert asked() == (False, False)  # still waiting for the user's yes
    for status in ("accepted", "approved"):
        proposal.status = status
        db_session.commit()
        assert asked() == (True, True), status
        assert seen_map["kw"]["level"] == "queued"
    proposal.status = "rejected"
    db_session.commit()
    assert asked() == (False, False)


@pytest.mark.usefixtures("profile")
def test_step_passes_whether_the_job_is_queued(db_session, monkeypatch, tmp_path):
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = _seed_application(db_session, slug)
    db_session.get(Job, application.job_id).apply_url = "https://careers.acme.example/jobs/7"
    db_session.commit()
    seen = _spy_step(monkeypatch)
    body = {**STEP, "application_id": str(application.id), "page_url": ACME_URL}
    assert _post(db_session, "/api/autofill/step", body).status_code == 200
    assert seen["kw"]["queued"] is False
    db_session.add(ApplicationProposal(job_id=application.job_id, application_id=application.id, status="accepted"))
    db_session.commit()
    assert _post(db_session, "/api/autofill/step", body).status_code == 200
    assert seen["kw"]["queued"] is True


@pytest.mark.usefixtures("profile")
def test_a_request_with_no_application_is_never_queued(db_session, monkeypatch):
    model_settings.set_answer_level(db_session, "queued")
    seen = _spy_map(monkeypatch)
    assert _post(db_session, "/api/autofill/map", {"fields": [MAP_FIELD]}).status_code == 200
    assert seen["kw"]["queued"] is False


@pytest.mark.usefixtures("profile")
def test_facts_include_the_selected_resume(db_session, monkeypatch, tmp_path):
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    seen = _spy_map(monkeypatch)
    assert _post(db_session, "/api/autofill/map", {"base": slug, "fields": [MAP_FIELD]}).status_code == 200
    first_job = next(e for e in SAMPLE_RESUME["experience"] if e.get("enabled", True))
    assert seen["facts"]["experience.0.employer"].value == first_job["company"]
    assert seen["facts"]["skills"].value[0] == SAMPLE_RESUME["skills"][0]["items"][0]


@pytest.mark.usefixtures("profile")
def test_pick_passes_the_source_hint_and_the_job(db_session, monkeypatch, tmp_path):
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = _seed_application(db_session, slug)
    job = db_session.get(Job, application.job_id)
    job.title, job.company = "Data Scientist", "Acme"
    db_session.commit()
    seen = _spy_pick(monkeypatch)
    r = _post(db_session, "/api/autofill/pick", {"application_id": str(application.id),
                                                 "source_hint": "REC_LinkedIn", "fields": [PICK_FIELD]})
    assert r.status_code == 200
    assert set(r.json()) == {"picks"}
    assert {k: _answer(v) for k, v in r.json()["picks"].items()} == {"g": {"oids": [], "reason": "abstained"}}
    assert seen["hint"] == autofill_pick.JobHint(title="Data Scientist", company="Acme", source="rec_linkedin")


@pytest.mark.usefixtures("profile")
def test_pick_reads_the_source_off_the_job_url_when_the_page_sends_none(db_session, monkeypatch, tmp_path):
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = _seed_application(db_session, slug)
    db_session.get(Job, application.job_id).source_url = "https://jobs.example.com/apply?id=7&utm_source=LinkedIn"
    db_session.commit()
    seen = _spy_pick(monkeypatch)
    assert _post(db_session, "/api/autofill/pick", {"application_id": str(application.id),
                                                    "fields": [PICK_FIELD]}).status_code == 200
    assert seen["hint"].source == "linkedin"


@pytest.mark.usefixtures("profile")
def test_pick_without_a_job_or_a_source_has_no_hint(db_session, monkeypatch):
    seen = _spy_pick(monkeypatch)
    assert _post(db_session, "/api/autofill/pick", {"fields": [PICK_FIELD]}).status_code == 200
    assert seen["hint"] is None
    _post(db_session, "/api/autofill/pick", {"source_hint": "indeed", "fields": [PICK_FIELD]})
    assert seen["hint"] == autofill_pick.JobHint(title=None, company=None, source="indeed")


@pytest.mark.usefixtures("profile")
def test_an_eeo_pick_without_consent_reaches_no_model(db_session, monkeypatch):
    """End to end through the real /pick: no consent → no eeo fact → no value to
    pick against → abstained, with neither engine asked."""
    asked = []
    monkeypatch.setattr(autofill_pick.llm, "call_openai", lambda **kw: asked.append(kw) or {})
    monkeypatch.setattr(autofill_pick.jev, "decide", lambda *a, **k: asked.append(a) or {})
    r = _post(db_session, "/api/autofill/pick", {"fields": [PICK_FIELD]})
    assert set(r.json()) == {"picks"}
    assert {k: _answer(v) for k, v in r.json()["picks"].items()} == {"g": {"oids": [], "reason": "abstained"}}
    assert asked == []


@pytest.mark.usefixtures("profile")
def test_the_real_map_returns_the_value_but_never_sends_it(db_session, monkeypatch):
    prompts = []

    def call_openai(**kw):
        prompts.append(kw["prompt"])
        return {"map": {"a": {"key": "personal.city", "confidence": 0.9}}}

    monkeypatch.setattr(autofill_map.llm, "call_openai", call_openai)
    r = _post(db_session, "/api/autofill/map", {"fields": [MAP_FIELD]})
    assert set(r.json()) == {"fields"}
    assert {k: _answer(v) for k, v in r.json()["fields"].items()} == {
        "a": {"route": "slot", "slot": "personal.city", "value": "Springfield", "format": None, "why": None, "years": False, "draft": False}}
    assert "Springfield" not in prompts[0] and "female" not in prompts[0].lower()


@pytest.mark.usefixtures("profile")
def test_the_map_response_carries_the_decision_trace(db_session, monkeypatch):
    """The trace is part of the wire shape, not just of the service's return value."""
    from tests.test_autofill_map import fake_jev

    model_settings.set_jev_api_key(db_session, "sk-or-test")
    model_settings.set_autofill_engine(db_session, "jev")
    fake_jev(monkeypatch, {"a": ("personal.city", 0.97)})
    r = _post(db_session, "/api/autofill/map", {"fields": [MAP_FIELD]})
    assert r.status_code == 200
    trace = r.json()["fields"]["a"]["trace"]
    assert trace["engine"] == "jev" and trace["p"] == 0.97
    assert set(trace) == {"engine", "p", "floor", "second", "first_p", "first_same", "chose_none", "sentinel"}


@pytest.mark.usefixtures("profile")
def test_the_pick_response_carries_the_decision_trace_and_the_polarity(db_session, monkeypatch):
    """Both are part of the wire shape, and neither holds the answer's value."""
    from tests.test_autofill_pick import fake_jev

    autofill_profile.set_profile({"eligibility": {"over_18": True}}, db_session)
    model_settings.set_jev_api_key(db_session, "sk-or-test")
    model_settings.set_autofill_engine(db_session, "jev")
    fake_jev(monkeypatch, {"g": ("o1", 0.97)}, ways={"g": ("same", 0.97)})
    field = {"fid": "g", "question": "Are you over 18?", "route": "slot", "slot": "eligibility.over_18",
             "options": [{"oid": "o1", "text": "Yes"}, {"oid": "o2", "text": "No"}]}
    r = _post(db_session, "/api/autofill/pick", {"fields": [field]})
    assert r.status_code == 200
    got = r.json()["picks"]["g"]
    assert (got["oids"], got["reason"]) == (["o1"], "matched")
    assert got["trace"]["engine"] == "jev" and got["trace"]["p"] == 0.97
    assert set(got["trace"]) == {"engine", "p", "floor", "second", "first_p", "first_same", "chose_none", "sentinel"}
    assert got["polarity"] == {"way": "same", "engine": "jev", "p": 0.97, "remembered": None}


@pytest.mark.parametrize("path, field", [("/api/autofill/map", MAP_FIELD), ("/api/autofill/pick", PICK_FIELD)])
def test_an_unknown_application_is_404(db_session, path, field):
    r = _post(db_session, path, {"application_id": str(uuid4()), "fields": [field]})
    assert r.status_code == 404


@pytest.mark.parametrize("path, field", [("/api/autofill/map", MAP_FIELD), ("/api/autofill/pick", PICK_FIELD)])
def test_a_malformed_application_id_is_422(db_session, path, field):
    assert _post(db_session, path, {"application_id": "not-a-uuid", "fields": [field]}).status_code == 422


@pytest.mark.usefixtures("profile")
@pytest.mark.parametrize("path, field, target", [
    ("/api/autofill/map", MAP_FIELD, autofill_map), ("/api/autofill/pick", PICK_FIELD, autofill_pick)])
def test_a_provider_failure_is_502(db_session, monkeypatch, path, field, target):
    def down(*a, **k):
        raise llm.LLMProviderError("The AI model didn't answer.")

    monkeypatch.setattr(target, "map_fields" if target is autofill_map else "pick", down)
    r = _post(db_session, path, {"fields": [field]})
    assert r.status_code == 502 and r.json()["detail"] == "The AI model didn't answer."


@pytest.mark.usefixtures("profile")
@pytest.mark.parametrize("path, field, target", [
    ("/api/autofill/map", MAP_FIELD, autofill_map),
    ("/api/autofill/pick", {**PICK_FIELD, "slot": "personal.city"}, autofill_pick)])
def test_malformed_fast_model_json_is_a_502_with_a_detail(db_session, monkeypatch, path, field, target):
    def unreadable(**kw):
        raise ValueError("OpenAI response was not valid JSON after retries")

    monkeypatch.setattr(target.llm, "call_openai", unreadable)
    r = _post(db_session, path, {"fields": [field]})
    assert r.status_code == 502 and r.json()["detail"] == "The AI model sent an answer we couldn't read."


# ---------- /step


STEP = {"fid": "g", "question": "Gender", "route": "slot", "slot": "eeo.gender",
        "candidates": [{"mid": "click:o1", "describe": 'Click the option "Female"'},
                       {"mid": "give_up", "describe": "Stop"}]}


def _spy_step(monkeypatch):
    seen = {}

    def step(req, facts, session, hint, **kw):
        seen.update(req=req, facts=facts, hint=hint, kw=kw)
        return StepResponse(mid=None, reason="abstained")

    monkeypatch.setattr(autofill_step, "step", step)
    return seen


@pytest.mark.usefixtures("profile")
def test_step_builds_facts_from_the_consent_gated_profile_and_passes_the_hint(db_session, monkeypatch, tmp_path):
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = _seed_application(db_session, slug)
    job = db_session.get(Job, application.job_id)
    job.title, job.company = "Data Scientist", "Acme"
    db_session.commit()
    seen = _spy_step(monkeypatch)
    r = _post(db_session, "/api/autofill/step", {**STEP, "application_id": str(application.id), "source_hint": "Indeed"})
    assert r.status_code == 200 and _answer(r.json()) == {"mid": None, "reason": "abstained"}
    assert "personal.city" in seen["facts"] and "eeo.gender" not in seen["facts"]
    assert seen["hint"] == autofill_pick.JobHint(title="Data Scientist", company="Acme", source="indeed")


@pytest.mark.usefixtures("profile")
def test_the_step_response_carries_the_decision_trace_and_the_polarity(db_session, monkeypatch):
    """Both are part of the wire shape, and neither holds the answer's value."""
    from tests.test_autofill_step import fake_jev

    autofill_profile.set_profile({"eligibility": {"over_18": True}}, db_session)
    model_settings.set_jev_api_key(db_session, "sk-or-test")
    model_settings.set_autofill_engine(db_session, "jev")
    fake_jev(monkeypatch, ("click:o1", 0.97), way=("same", 0.97))
    step = {"fid": "g", "question": "Are you over 18?", "route": "slot", "slot": "eligibility.over_18",
            "candidates": [{"mid": "click:o1", "describe": 'Click the option "Yes"'},
                           {"mid": "give_up", "describe": "Stop"}]}
    r = _post(db_session, "/api/autofill/step", step)
    assert r.status_code == 200
    got = r.json()
    assert (got["mid"], got["reason"]) == ("click:o1", "matched")
    assert got["trace"]["engine"] == "jev" and got["trace"]["p"] == 0.97
    assert set(got["trace"]) == {"engine", "p", "floor", "second", "first_p", "first_same", "chose_none", "sentinel"}
    assert got["polarity"] == {"way": "same", "engine": "jev", "p": 0.97, "remembered": None}


@pytest.mark.usefixtures("profile")
def test_an_eeo_step_without_consent_reaches_no_model(db_session, monkeypatch):
    asked = []
    monkeypatch.setattr(autofill_step.llm, "call_openai", lambda **kw: asked.append(kw) or {})
    monkeypatch.setattr(autofill_step.jev, "decide", lambda *a, **k: asked.append(a) or {})
    r = _post(db_session, "/api/autofill/step", STEP)
    assert _answer(r.json()) == {"mid": None, "reason": "abstained"} and asked == []


def test_step_refuses_a_value_or_a_move_id_the_page_could_not_have_made(db_session):
    assert _post(db_session, "/api/autofill/step", {**STEP, "value": "Female"}).status_code == 422
    bad = {**STEP, "candidates": [{"mid": "click:Female", "describe": "x"}]}
    assert _post(db_session, "/api/autofill/step", bad).status_code == 422


def test_step_on_an_unknown_application_is_404(db_session):
    assert _post(db_session, "/api/autofill/step", {**STEP, "application_id": str(uuid4())}).status_code == 404


@pytest.mark.usefixtures("profile")
def test_step_provider_failures_are_502(db_session, monkeypatch):
    def unreadable(**kw):
        raise ValueError("OpenAI response was not valid JSON after retries")

    monkeypatch.setattr(autofill_step.llm, "call_openai", unreadable)
    r = _post(db_session, "/api/autofill/step", {**STEP, "slot": "personal.city"})
    assert r.status_code == 502 and r.json()["detail"] == "The AI model sent an answer we couldn't read."


# ---------- today's date is the applicant's, not the server's (a container runs on UTC)


@pytest.mark.usefixtures("profile")
@pytest.mark.parametrize("shift, kept", [(-1, True), (0, True), (1, True), (-2, False), (400, False)])
def test_the_browsers_date_is_today_within_a_day_of_the_servers(db_session, monkeypatch, shift, kept):
    """An evening in the US is already tomorrow in UTC: a date signed "today"
    is the applicant's. A date further off than any time zone is not taken."""
    from datetime import date, timedelta

    seen = _spy_map(monkeypatch)
    theirs = date.today() + timedelta(days=shift)
    r = _post(db_session, "/api/autofill/map", {"today": theirs.isoformat(), "fields": [MAP_FIELD]})
    assert r.status_code == 200
    assert seen["facts"]["derived.today"].value == (theirs if kept else date.today()).isoformat()


@pytest.mark.usefixtures("profile")
def test_every_fact_route_reads_the_browsers_date(db_session, monkeypatch):
    from datetime import date, timedelta

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    seen = _spy_pick(monkeypatch)
    _post(db_session, "/api/autofill/pick", {"today": yesterday, "fields": [PICK_FIELD]})
    assert seen["facts"]["derived.today"].value == yesterday
    r = _post(db_session, "/api/autofill/map", {"today": "not a date", "fields": [MAP_FIELD]})
    assert r.status_code == 422



@pytest.mark.usefixtures("profile")
def test_the_applications_company_reaches_the_catalog(db_session, monkeypatch, tmp_path):
    """A job at a company the resume lists: "previously employed here" is Yes
    for this application, whatever the standing answer says."""
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = _seed_application(db_session, slug)
    first_job = next(e for e in SAMPLE_RESUME["experience"] if e.get("enabled", True))
    db_session.get(Job, application.job_id).company = first_job["company"]
    db_session.commit()
    seen = _spy_map(monkeypatch)
    assert _post(db_session, "/api/autofill/map", {"application_id": str(application.id),
                                                   "fields": [MAP_FIELD]}).status_code == 200
    assert seen["facts"]["derived.previously_employed_here"].value.startswith("Yes, ")
    assert "eligibility.previously_employed_here" not in seen["facts"]
    seen = _spy_map(monkeypatch)
    assert _post(db_session, "/api/autofill/map", {"base": slug, "fields": [MAP_FIELD]}).status_code == 200
    assert "derived.previously_employed_here" not in seen["facts"]


def _scoped_profile(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile({"custom": [
        {"question": "Willing to relocate to Austin?", "answer": "Yes", "only_for": "Austin"},
        {"question": "Preferred shift", "answer": "Day"}]}, db_session)


def test_map_offers_a_scoped_saved_answer_only_for_a_job_in_its_city(db_session, tmp_path, monkeypatch):
    _scoped_profile(db_session, tmp_path, monkeypatch)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = _seed_application(db_session, slug)
    seen = _spy_map(monkeypatch)
    for where, offered in (("Austin, TX", True), ("Denver, CO", False), (None, False)):
        db_session.get(Job, application.job_id).location = where
        db_session.commit()
        assert _post(db_session, "/api/autofill/map", {
            "fields": [MAP_FIELD], "application_id": str(application.id)}).status_code == 200
        assert ("custom.0" in seen["facts"]) is offered, where
        assert seen["facts"]["custom.1"].value == "Day"


def test_context_drops_a_scoped_saved_answer_for_a_job_elsewhere(db_session, tmp_path, monkeypatch):
    _scoped_profile(db_session, tmp_path, monkeypatch)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = _seed_application(db_session, slug)
    job = db_session.get(Job, application.job_id)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        def questions(url):
            return [row["question"] for row in TestClient(app).get(url).json()["profile"]["custom"]]

        by_application = f"/api/autofill/context?application_id={application.id}"
        assert questions(by_application) == ["Preferred shift"]
        job.location = "Austin, TX"
        db_session.commit()
        assert questions(by_application) == ["Willing to relocate to Austin?", "Preferred shift"]
        assert questions(f"/api/autofill/context?base={slug}") == ["Preferred shift"]
    finally:
        app.dependency_overrides.clear()


def test_choose_does_not_offer_the_model_a_saved_answer_that_names_another_job(db_session, tmp_path, monkeypatch):
    _scoped_profile(db_session, tmp_path, monkeypatch)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = _seed_application(db_session, slug)
    job = db_session.get(Job, application.job_id)
    prompts = []

    def fake_model(**kwargs):
        prompts.append(kwargs["prompt"])
        return {"choices": {}}

    monkeypatch.setattr(autofill_choose.llm, "call_openai", fake_model)
    field = {"qid": "q1", "label": "Anything", "kind": "text"}
    for where, application_id, offered in (
            ("Austin, TX", str(application.id), True), ("Denver, CO", str(application.id), False),
            ("Austin, TX", None, False)):
        job.location = where
        db_session.commit()
        payload = {"fields": [field], **({"application_id": application_id} if application_id else {})}
        assert _post(db_session, "/api/autofill/choose", payload).status_code == 200
        assert ("Willing to relocate to Austin?" in prompts[-1]) is offered, (where, application_id)
        assert "Preferred shift" in prompts[-1]


# ---------- "Acme, Globex, or Initech": the question names companies the job's company string does not

def _acme_application(db_session, monkeypatch, tmp_path):
    """An application at Acme, whose resume (SAMPLE_RESUME) lists DataCo and OldCo but never Acme."""
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = _seed_application(db_session, slug)
    db_session.get(Job, application.job_id).company = "Acme"
    db_session.commit()
    model_settings.set_jev_api_key(db_session, "sk-or-test")
    model_settings.set_autofill_engine(db_session, "jev")
    return application


WORKED_OPTIONS = [{"oid": "o1", "text": "Yes"}, {"oid": "o2", "text": "No"}]


def test_pick_answers_yes_when_the_question_names_an_employer_of_the_history(db_session, monkeypatch, tmp_path):
    import json

    from tests.test_autofill_pick import fake_jev

    application = _acme_application(db_session, monkeypatch, tmp_path)
    calls = fake_jev(monkeypatch, {"w": ("o1", 0.95), "k": ("o2", 0.95)}, ways={"w": ("same", 0.95), "k": ("same", 0.95)})
    fields = [{"fid": "w", "question": "Have you worked for Acme, Globex or OldCo?", "route": "slot",
               "slot": "derived.previously_employed_here", "options": WORKED_OPTIONS},
              {"fid": "k", "question": "Have you worked for Acme or Globex?", "route": "slot",
               "slot": "derived.previously_employed_here", "options": WORKED_OPTIONS}]
    r = _post(db_session, "/api/autofill/pick", {"application_id": str(application.id), "fields": fields})
    assert r.status_code == 200
    instructions = {fid: q["instructions"] for fid, q in calls[0]["questions"].items()}
    assert json.dumps("Yes, previously") in instructions["w"] and json.dumps("No") not in instructions["w"]
    # A question that names no employer of the history is still the derived No.
    assert json.dumps("No") in instructions["k"] and "Yes, previously" not in instructions["k"]


def test_map_hands_back_yes_when_the_question_names_an_employer_of_the_history(db_session, monkeypatch, tmp_path):
    from tests.test_autofill_map import fake_jev

    application = _acme_application(db_session, monkeypatch, tmp_path)
    fake_jev(monkeypatch, {"w": ("derived.previously_employed_here", 0.95),
                           "k": ("derived.previously_employed_here", 0.95)})
    fields = [{"fid": "w", "question": "Previously employed by Acme, Globex, or OldCo?", "shape": "text"},
              {"fid": "k", "question": "Previously employed by Acme?", "shape": "text"}]
    r = _post(db_session, "/api/autofill/map", {"application_id": str(application.id), "fields": fields})
    assert r.status_code == 200
    got = r.json()["fields"]
    assert (got["w"]["slot"], got["w"]["value"]) == ("derived.previously_employed_here", "Yes, previously")
    assert (got["k"]["slot"], got["k"]["value"]) == ("derived.previously_employed_here", "No")


def test_step_goal_says_yes_when_the_question_names_an_employer_of_the_history(db_session, monkeypatch, tmp_path):
    import json

    from tests.test_autofill_step import fake_jev

    application = _acme_application(db_session, monkeypatch, tmp_path)
    calls = fake_jev(monkeypatch, ("click:o1", 0.95))
    goals = {}
    for fid, question in (("w", "Have you worked for Acme, Globex or OldCo?"), ("k", "Have you worked for Acme?")):
        body = {"application_id": str(application.id), "fid": fid, "question": question, "route": "slot",
                "slot": "derived.previously_employed_here",
                "candidates": [{"mid": "click:o1", "describe": 'Click the option "Yes"'},
                               {"mid": "give_up", "describe": "Stop"}]}
        assert _post(db_session, "/api/autofill/step", body).status_code == 200
        goals[fid] = calls[-1]["questions"][fid]["instructions"]
    assert f"the answer to the question is {json.dumps('Yes, previously')}" in goals["w"]
    assert f"the answer to the question is {json.dumps('No')}" in goals["k"]


def test_a_parent_or_subsidiary_of_a_listed_company_is_nobodys_answer_in_pick_map_and_step(
        db_session, monkeypatch, tmp_path):
    """The history lists "DataCo" and "OldCo". A question listing "DataCo Labs" names a subsidiary of one:
    not the derived No, and not a Yes either. /pick says "asked" (final), /map routes none, /step gives up."""
    from tests.test_autofill_map import fake_jev as map_jev
    from tests.test_autofill_pick import fake_jev as pick_jev
    from tests.test_autofill_step import fake_jev as step_jev

    application = _acme_application(db_session, monkeypatch, tmp_path)
    question = "Have you worked for DataCo Labs before?"
    pick_jev(monkeypatch, {"w": ("o2", 0.99)}, ways={"w": ("same", 0.99)})
    field = {"fid": "w", "question": question, "route": "slot", "slot": "derived.previously_employed_here",
             "options": WORKED_OPTIONS}
    picked = _post(db_session, "/api/autofill/pick", {"application_id": str(application.id), "fields": [field]})
    assert (picked.json()["picks"]["w"]["oids"], picked.json()["picks"]["w"]["reason"]) == ([], "asked")

    map_jev(monkeypatch, {"w": ("derived.previously_employed_here", 0.95)})
    mapped = _post(db_session, "/api/autofill/map", {"application_id": str(application.id),
                                                      "fields": [{"fid": "w", "question": question, "shape": "text"}]})
    assert (mapped.json()["fields"]["w"]["route"], mapped.json()["fields"]["w"]["value"]) == ("none", None)

    step_jev(monkeypatch, ("click:o1", 0.99))
    body = {"application_id": str(application.id), "fid": "w", "question": question, "route": "slot",
            "slot": "derived.previously_employed_here",
            "candidates": [{"mid": "click:o2", "describe": 'Click the option "No"'},
                           {"mid": "give_up", "describe": "Stop"}]}
    got = _post(db_session, "/api/autofill/step", body).json()
    assert (got["mid"], got["reason"]) == (None, "abstained")


def test_step_finds_the_employer_in_a_candidate_when_the_question_does_not_list_it(
        db_session, monkeypatch, tmp_path):
    import json

    from tests.test_autofill_step import fake_jev

    application = _acme_application(db_session, monkeypatch, tmp_path)
    calls = fake_jev(monkeypatch, ("click:o1", 0.95))
    body = {"application_id": str(application.id), "fid": "w", "question": "Which of these employers did you work for?",
            "route": "slot", "slot": "derived.previously_employed_here",
            "candidates": [{"mid": "click:o1", "describe": 'Click the option "OldCo"'},
                           {"mid": "click:o2", "describe": 'Click the option "Globex"'},
                           {"mid": "give_up", "describe": "Stop"}]}
    assert _post(db_session, "/api/autofill/step", body).status_code == 200
    goal = calls[-1]["questions"]["w"]["instructions"]
    assert f"the answer to the question is {json.dumps('Yes, previously')}" in goal


# ---------- the veteran fallback: /pick leaves a protected-class popup for good, and /step cannot take it over

def test_a_saved_yes_never_reaches_a_protected_class_through_pick_then_step(db_session, monkeypatch, tmp_path):
    """The loop asks /pick, and for a popup /pick left it falls back to /step. Both are real routes here, both
    models are scripted to choose the class, and the saved answer is Yes."""
    from tests.test_autofill_pick import fake_jev as pick_jev
    from tests.test_autofill_step import fake_jev as step_jev

    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile({"eeo": {"veteran_status": "yes"}}, db_session)
    eeo_consent.set_consent(EeoConsent(enabled=True, policy_version="1"), db_session)
    model_settings.set_jev_api_key(db_session, "sk-or-test")
    model_settings.set_autofill_engine(db_session, "jev")
    classes = ["I identify as one or more of the classifications of protected veterans listed above",
               "I am not a protected veteran"]
    pick_jev(monkeypatch, {"v": ("o1", 0.99)}, ways={"v": ("same", 0.99)})
    field = {"fid": "v", "question": "Protected veteran status", "route": "slot", "slot": "eeo.veteran_status",
             "options": [{"oid": f"o{i}", "text": t} for i, t in enumerate(classes, 1)]}
    picked = _post(db_session, "/api/autofill/pick", {"fields": [field]}).json()["picks"]["v"]
    # FINAL ("asked"): the loop does not fall back to /step for it.
    assert (picked["oids"], picked["reason"]) == ([], "asked")

    # A loop version that did fall back still gets nothing.
    step_jev(monkeypatch, ("click:o1", 0.99), way=("same", 0.99))
    step = {"fid": "v", "question": "Protected veteran status", "route": "slot", "slot": "eeo.veteran_status",
            "candidates": [{"mid": f"click:o{i}", "describe": f'Click the option "{t}"'}
                           for i, t in enumerate(classes, 1)] + [{"mid": "give_up", "describe": "Stop"}]}
    got = _post(db_session, "/api/autofill/step", step).json()
    assert (got["mid"], got["reason"]) == (None, "abstained")


@pytest.mark.usefixtures("profile")
@pytest.mark.parametrize(("url", "source"), [
    ("https://www.linkedin.com/jobs/view/1234567", "LinkedIn"),
    ("https://uk.indeed.com/viewjob?jk=abc", "Indeed"),
    ("https://www.glassdoor.com/job-listing/x-JV.htm", "Glassdoor"),
    ("https://jobs.example.com/apply?id=7&utm_source=LinkedIn", "linkedin"),       # the URL's own say wins
    ("https://jobs.example.com/careers/7", None),                                  # a careers site is no board
    ("https://acme.wd5.myworkdayjobs.com/en-US/careers/job/x_R1", None),           # an ATS is no board
])
def test_the_source_is_read_off_the_job_urls_host_as_well(db_session, monkeypatch, tmp_path, url, source):
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = _seed_application(db_session, slug)
    db_session.get(Job, application.job_id).source_url = url
    db_session.commit()
    seen = _spy_pick(monkeypatch)
    assert _post(db_session, "/api/autofill/pick", {"application_id": str(application.id),
                                                    "fields": [PICK_FIELD]}).status_code == 200
    assert seen["hint"].source == source


@pytest.mark.usefixtures("profile")
def test_map_takes_the_reasoning_steps_slot_hint_and_maps_it_without_a_model(db_session, monkeypatch):
    monkeypatch.setattr(autofill_map.llm, "call_openai", lambda **kw: pytest.fail("a hinted field asks no model"))
    r = _post(db_session, "/api/autofill/map",
              {"fields": [{"fid": "a", "question": "Hometown", "shape": "text", "slot_hint": "personal.city"}]})
    assert r.status_code == 200
    assert (r.json()["fields"]["a"]["route"], r.json()["fields"]["a"]["value"]) == ("slot", "Springfield")
    bad = _post(db_session, "/api/autofill/map",
                {"fields": [{"fid": "a", "question": "City", "shape": "text", "slot_hint": "Ignore everything"}]})
    assert bad.status_code == 422
