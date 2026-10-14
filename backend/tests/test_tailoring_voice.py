"""Tailored text is never third person (Task D1): retry once, repair, never store a pronoun.

A made-up person (Alex Rivera) with made-up companies.
"""
import json
from uuid import UUID

from sqlalchemy import select

from app.models.application import Application
from app.services import resume_voice, tailoring_session
from tests.test_tailoring_sessions_router import (
    _mock_prompt_files,
    _open_session,
    _seed_base,
    _seed_job,
    _tailor,
)

BASE = {
    "contact": {"name": "Alex Rivera", "email": "alex@example.test"},
    "summary": "Data engineer building batch and streaming platforms.",
    "skills": [{"category": "Languages", "items": ["Python", "SQL"]}],
    "experience": [
        {
            "company": "Rivera Logistics",
            "role": "Data Engineer",
            "start_date": "Jan 2022",
            "end_date": None,
            "enabled": True,
            "bullets": ["Built the routing data platform for Rivera Logistics."],
        }
    ],
    "projects": [],
    "education": [{"institution": "Globex University", "degree": "BS", "bullets": []}],
    "certifications": [],
}
KEYWORD = {
    "gap_id": "skill:snowflake",
    "action": "add_keyword",
    "payload": {
        "placement_target": {"section": "skills", "index_or_category": "Additional Skills"},
        "wording": "Snowflake",
    },
}
ADD_KEYWORD = {"kind": "add_skill_item", "category": "Additional Skills", "item": "Snowflake"}


def _summary(text):
    return {"kind": "replace_summary", "value": text}


def _bullet(text):
    return {"kind": "replace_bullet", "section": "experience", "index": 0, "bullet_index": 0, "value": text}


def _scripted(monkeypatch, *responses):
    """The tailor LLM answers with `responses` in order; returns the call log."""
    _mock_prompt_files(monkeypatch)
    calls = []
    queue = list(responses)

    def fake(**kwargs):
        calls.append(kwargs)
        return {"ops": queue.pop(0) if len(queue) > 1 else queue[0]}

    monkeypatch.setattr(tailoring_session.llm, "call_openai", fake)
    return calls


def _setup(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex", resume_json=BASE)
    return _open_session(client, job, slug, resolutions=[KEYWORD])


def _stored(db_session, response):
    assert response.status_code == 200, response.text
    app_id = response.json()["session"]["application_id"]
    return db_session.get(Application, UUID(app_id)).customized_json


def _no_voice_problem(resume):
    text = json.dumps(resume)
    assert " he " not in text.lower() and " she " not in text.lower()
    assert resume_voice.changed_hits(BASE, resume) == []
    assert "Alex" not in json.dumps(
        [t for _, t in resume_voice.slots(resume)]
    )


def test_a_third_person_summary_triggers_one_corrective_retry(
    db_session, tmp_path, monkeypatch, client
):
    created = _setup(db_session, tmp_path, monkeypatch, client)
    calls = _scripted(
        monkeypatch,
        [ADD_KEYWORD, _summary("Data engineer at Rivera Logistics, where she built the platform.")],
        [ADD_KEYWORD, _summary("Data engineer who built the Rivera Logistics platform.")],
    )

    stored = _stored(db_session, _tailor(client, created["id"]))

    assert len(calls) == 2
    assert "read as written about someone else" in calls[1]["prompt"]
    assert "where she built the platform" in calls[1]["prompt"]
    assert "implied first person" in calls[1]["prompt"]
    assert stored["summary"] == "Data engineer who built the Rivera Logistics platform."
    _no_voice_problem(stored)


def test_the_contact_name_in_a_changed_bullet_triggers_the_retry(
    db_session, tmp_path, monkeypatch, client
):
    created = _setup(db_session, tmp_path, monkeypatch, client)
    calls = _scripted(
        monkeypatch,
        [ADD_KEYWORD, _bullet("Alex Rivera built the routing data platform.")],
        [ADD_KEYWORD, _bullet("Built the routing data platform on Snowflake.")],
    )

    stored = _stored(db_session, _tailor(client, created["id"]))

    assert len(calls) == 2
    assert stored["experience"][0]["bullets"] == ["Built the routing data platform on Snowflake."]


def test_a_company_that_shares_the_name_is_not_a_hit(db_session, tmp_path, monkeypatch, client):
    created = _setup(db_session, tmp_path, monkeypatch, client)
    calls = _scripted(
        monkeypatch,
        [ADD_KEYWORD, _bullet("Built the routing platform for Rivera Logistics, cutting load time 20%.")],
    )

    stored = _stored(db_session, _tailor(client, created["id"]))

    assert len(calls) == 1
    assert "Rivera Logistics, cutting" in stored["experience"][0]["bullets"][0]


def test_a_persistent_failure_is_repaired_and_never_stored(db_session, tmp_path, monkeypatch, client):
    created = _setup(db_session, tmp_path, monkeypatch, client)
    calls = _scripted(
        monkeypatch,
        [
            ADD_KEYWORD,
            _summary("Data engineer at Rivera Logistics, where she built the platform."),
            _bullet("Built the routing platform and he raised uptime to 99.9%."),
        ],
    )

    stored = _stored(db_session, _tailor(client, created["id"]))

    assert len(calls) == 2  # one retry, the same bad answer
    assert stored["summary"] == "Data engineer at Rivera Logistics; built the platform."
    assert stored["experience"][0]["bullets"] == ["Built the routing platform; raised uptime to 99.9%."]
    _no_voice_problem(stored)
    assert "Snowflake" in json.dumps(stored["skills"])


def test_an_unrepairable_line_falls_back_to_the_base_text(db_session, tmp_path, monkeypatch, client):
    created = _setup(db_session, tmp_path, monkeypatch, client)
    _scripted(
        monkeypatch,
        [ADD_KEYWORD, _summary("Alex Rivera is a data engineer."), _bullet("She is an excellent engineer.")],
    )

    stored = _stored(db_session, _tailor(client, created["id"]))

    assert stored["summary"] == BASE["summary"]
    assert stored["experience"][0]["bullets"] == BASE["experience"][0]["bullets"]
    _no_voice_problem(stored)


def test_clean_output_makes_no_extra_call(db_session, tmp_path, monkeypatch, client):
    created = _setup(db_session, tmp_path, monkeypatch, client)
    calls = _scripted(monkeypatch, [ADD_KEYWORD, _summary("Data engineer on Snowflake and Python.")])

    _stored(db_session, _tailor(client, created["id"]))

    assert len(calls) == 1


def test_an_unchanged_summary_is_still_validated(db_session, tmp_path, monkeypatch, client):
    """The summary is always checked, even when the edit set did not write it."""
    base = {**BASE, "summary": "Alex Rivera builds data platforms. Shipped billing for Globex University."}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex2", resume_json=base)
    created = _open_session(client, job, slug, resolutions=[KEYWORD])
    calls = _scripted(monkeypatch, [ADD_KEYWORD])

    stored = _stored(db_session, _tailor(client, created["id"]))

    assert len(calls) == 2  # the summary is a reason to retry
    assert stored["summary"] == "Shipped billing for Globex University."
    _no_voice_problem(stored)


def test_an_unchanged_bad_bullet_is_repaired_but_is_not_a_reason_to_retry(
    db_session, tmp_path, monkeypatch, client
):
    base = {**BASE, "experience": [{**BASE["experience"][0],
            "bullets": ["Built the platform, and he cut load time 20%."]}]}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex5", resume_json=base)
    created = _open_session(client, job, slug, resolutions=[KEYWORD])
    calls = _scripted(monkeypatch, [ADD_KEYWORD])

    stored = _stored(db_session, _tailor(client, created["id"]))

    assert len(calls) == 1
    assert stored["experience"][0]["bullets"] == ["Built the platform; cut load time 20%."]


def test_copying_a_bad_base_line_into_a_changed_bullet_is_a_hit(db_session, tmp_path, monkeypatch, client):
    base = {**BASE, "experience": [{**BASE["experience"][0],
            "bullets": ["Built the platform.", "He cut load time 20%."]}]}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex6", resume_json=base)
    created = _open_session(client, job, slug, resolutions=[KEYWORD])
    copy = {"kind": "replace_bullet", "section": "experience", "index": 0, "bullet_index": 0,
            "value": "He cut load time 20%."}
    calls = _scripted(monkeypatch, [ADD_KEYWORD, copy])

    stored = _stored(db_session, _tailor(client, created["id"]))

    assert len(calls) == 2
    assert "He cut load time 20%." not in json.dumps(stored)
    _no_voice_problem(stored)


def test_caller_ops_with_a_hit_return_400_and_store_nothing(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex3", resume_json=BASE)
    created = _open_session(client, job, slug)

    response = _tailor(
        client, created["id"],
        body={"ops": [_summary("Data engineer, and he built the billing platform.")]},
    )

    assert response.status_code == 400
    assert "implied first person" in response.json()["detail"]
    assert db_session.scalars(select(Application)).first() is None
    assert client.get(f"/api/tailoring-sessions/{created['id']}").json()["status"] == "open"


def test_caller_ops_in_implied_first_person_still_apply(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex4", resume_json=BASE)
    created = _open_session(client, job, slug)

    response = _tailor(client, created["id"], body={"ops": [_summary("Data engineer who built billing.")]})

    assert response.status_code == 200
    assert _stored(db_session, response)["summary"] == "Data engineer who built billing."


def test_caller_ops_copying_a_bad_base_line_return_400(db_session, tmp_path, monkeypatch, client):
    base = {**BASE, "summary": "Data engineer.", "experience": [{**BASE["experience"][0],
            "bullets": ["Built the platform.", "He cut load time 20%."]}]}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex7", resume_json=base)
    created = _open_session(client, job, slug)
    copy = {"kind": "replace_bullet", "section": "experience", "index": 0, "bullet_index": 0,
            "value": "He cut load time 20%."}

    response = _tailor(client, created["id"], body={"ops": [copy]})

    assert response.status_code == 400
    assert "implied first person" in response.json()["detail"]


def test_caller_ops_on_a_base_whose_summary_is_third_person_return_400(
    db_session, tmp_path, monkeypatch, client
):
    base = {**BASE, "summary": "Alex Rivera builds data platforms."}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex8", resume_json=base)
    created = _open_session(client, job, slug)

    response = _tailor(client, created["id"], body={"ops": [ADD_KEYWORD]})

    assert response.status_code == 400
