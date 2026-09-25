"""POST /api/autofill/map, /pick and /step — what the routes decide before the services run."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.job import Job
from app.schemas.autofill_fill import Mapped, Picked, StepResponse
from app.schemas.eeo_consent import EeoConsent
from app.services import (
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


def _spy_map(monkeypatch):
    seen = {}

    def map_fields(fields, facts, session, **kw):
        seen.update(facts=facts, kw=kw)
        return {f.fid: Mapped(route="none") for f in fields}

    monkeypatch.setattr(autofill_map, "map_fields", map_fields)
    return seen


def _spy_pick(monkeypatch):
    seen = {}

    def pick(fields, facts, session, hint):
        seen.update(facts=facts, hint=hint)
        return {f.fid: Picked(oids=[], reason="abstained") for f in fields}

    monkeypatch.setattr(autofill_pick, "pick", pick)
    return seen


@pytest.mark.usefixtures("profile")
def test_map_builds_facts_from_the_consent_gated_profile(db_session, monkeypatch):
    seen = _spy_map(monkeypatch)
    r = _post(db_session, "/api/autofill/map", {"fields": [MAP_FIELD]})
    assert r.status_code == 200
    assert r.json() == {"fields": {"a": {"route": "none", "slot": None, "value": None}}}
    assert "personal.city" in seen["facts"]
    assert not [slot for slot in seen["facts"] if slot.startswith("eeo")]
    assert seen["kw"] == {"eeo_consented": False, "low_stakes": False}


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


@pytest.mark.usefixtures("profile")
def test_map_reads_low_stakes_from_the_setting_not_the_client(db_session, monkeypatch):
    seen = _spy_map(monkeypatch)
    model_settings.set_autofill_low_stakes(db_session, True)
    assert _post(db_session, "/api/autofill/map", {"fields": [MAP_FIELD]}).status_code == 200
    assert seen["kw"]["low_stakes"] is True
    assert _post(db_session, "/api/autofill/map",
                 {"fields": [MAP_FIELD], "low_stakes": False}).status_code == 422


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
    assert r.json() == {"picks": {"g": {"oids": [], "reason": "abstained"}}}
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
    assert r.json() == {"picks": {"g": {"oids": [], "reason": "abstained"}}}
    assert asked == []


@pytest.mark.usefixtures("profile")
def test_the_real_map_returns_the_value_but_never_sends_it(db_session, monkeypatch):
    prompts = []

    def call_openai(**kw):
        prompts.append(kw["prompt"])
        return {"map": {"a": {"key": "personal.city", "confidence": 0.9}}}

    monkeypatch.setattr(autofill_map.llm, "call_openai", call_openai)
    r = _post(db_session, "/api/autofill/map", {"fields": [MAP_FIELD]})
    assert r.json() == {"fields": {"a": {"route": "slot", "slot": "personal.city", "value": "Springfield"}}}
    assert "Springfield" not in prompts[0] and "female" not in prompts[0].lower()


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

    def step(req, facts, session, hint):
        seen.update(req=req, facts=facts, hint=hint)
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
    assert r.status_code == 200 and r.json() == {"mid": None, "reason": "abstained"}
    assert "personal.city" in seen["facts"] and "eeo.gender" not in seen["facts"]
    assert seen["hint"] == autofill_pick.JobHint(title="Data Scientist", company="Acme", source="indeed")


@pytest.mark.usefixtures("profile")
def test_an_eeo_step_without_consent_reaches_no_model(db_session, monkeypatch):
    asked = []
    monkeypatch.setattr(autofill_step.llm, "call_openai", lambda **kw: asked.append(kw) or {})
    monkeypatch.setattr(autofill_step.jev, "decide", lambda *a, **k: asked.append(a) or {})
    r = _post(db_session, "/api/autofill/step", STEP)
    assert r.json() == {"mid": None, "reason": "abstained"} and asked == []


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
