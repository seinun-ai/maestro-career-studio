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
            _bullet("Built the routing platform, where he raised uptime to 99.9%."),
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
    base = {**BASE, "summary": "Alex Rivera led billing for Globex University."}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex2", resume_json=base)
    created = _open_session(client, job, slug, resolutions=[KEYWORD])
    calls = _scripted(monkeypatch, [ADD_KEYWORD])

    stored = _stored(db_session, _tailor(client, created["id"]))

    assert len(calls) == 2  # the summary is a reason to retry
    assert stored["summary"] == "Led billing for Globex University."
    _no_voice_problem(stored)


def test_an_unchanged_summary_that_cannot_be_repaired_cleanly_is_kept(
    db_session, tmp_path, monkeypatch, client
):
    base = {**BASE, "summary": "Alex Rivera builds data platforms. Shipped billing for Globex University."}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex2b", resume_json=base)
    created = _open_session(client, job, slug, resolutions=[KEYWORD])
    _scripted(monkeypatch, [ADD_KEYWORD])

    stored = _stored(db_session, _tailor(client, created["id"]))

    assert stored["summary"] == base["summary"]  # the owner's words, left to the health check


def test_an_unchanged_bad_bullet_is_repaired_but_is_not_a_reason_to_retry(
    db_session, tmp_path, monkeypatch, client
):
    base = {**BASE, "experience": [{**BASE["experience"][0],
            "bullets": ["Built the platform, where he cut load time 20%."]}]}
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


def test_caller_ops_error_quotes_the_offending_line(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alexq", resume_json=BASE)
    created = _open_session(client, job, slug)

    response = _tailor(client, created["id"], body={"ops": [_summary("She builds billing.")]})

    assert response.status_code == 400
    assert '"She builds billing."' in response.json()["detail"]


def test_caller_ops_with_a_hit_return_400_and_store_nothing(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex3", resume_json=BASE)
    created = _open_session(client, job, slug)

    response = _tailor(
        client, created["id"],
        body={"ops": [_summary("Data engineer, where he built the billing platform.")]},
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


def test_caller_ops_leaving_a_third_person_base_summary_alone_are_not_refused(
    db_session, tmp_path, monkeypatch, client
):
    base = {**BASE, "summary": "Founder of Globex, which has shipped two products."}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex8", resume_json=base)
    created = _open_session(client, job, slug)

    response = _tailor(client, created["id"], body={"ops": [ADD_KEYWORD]})

    stored = _stored(db_session, response)  # 200: the summary is the owner's, not the caller's
    assert stored["summary"] == base["summary"]  # a founder clause is left to the health check
    assert "Snowflake" in json.dumps(stored["skills"])


def test_caller_ops_leaving_a_third_person_base_bullet_alone_store_it_repaired(
    db_session, tmp_path, monkeypatch, client
):
    base = {**BASE, "experience": [{**BASE["experience"][0],
            "bullets": ["Built the platform, where he cut load time 20%."]}]}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex9", resume_json=base)
    created = _open_session(client, job, slug)

    stored = _stored(db_session, _tailor(client, created["id"], body={"ops": [ADD_KEYWORD]}))

    assert stored["experience"][0]["bullets"] == ["Built the platform; cut load time 20%."]


def test_caller_ops_changing_the_summary_to_third_person_return_400(
    db_session, tmp_path, monkeypatch, client
):
    base = {**BASE, "summary": "Founder of Globex, which has shipped two products."}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex10", resume_json=base)
    created = _open_session(client, job, slug)

    response = _tailor(client, created["id"], body={"ops": [_summary("Alex Rivera builds data platforms.")]})

    assert response.status_code == 400
    assert "implied first person" in response.json()["detail"]
    assert db_session.scalars(select(Application)).first() is None


def test_a_pre_ops_only_tailor_still_repairs_what_it_stores(db_session, tmp_path, monkeypatch, client):
    """Enabling a base entry whose bullet reads "He streamed ..." is the whole edit set: no LLM
    call, no caller ops. The repair still runs before the draft is saved."""
    from app.models.job import Job  # noqa: F401
    from app.models.tailoring_session import TailoringSession

    base = {**BASE, "projects": [{
        "name": "Ingestion Pipeline", "enabled": False, "tech": "Kafka",
        "bullets": ["He streamed events with Kafka, where she cut lag 20%."],
    }]}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex11", resume_json=base)
    tailoring = TailoringSession(
        job_id=job.id, base_resume=slug, status="open", resolutions_json=[],
        gaps_json={"categories": [{"key": "missing_skills", "gaps": [{
            "gap_id": "skill:kafka", "kind": "skill", "jd_skill": "Kafka",
            "diagnostic": {"fix_hint": "absent"},
            "actions": ["add_keyword", "user_input", "attach_project", "skip", "enable_entry"],
        }]}]},
    )
    db_session.add(tailoring)
    db_session.commit()
    tailoring_session.save_resolutions(
        tailoring.id,
        [{"gap_id": "skill:kafka", "action": "enable_entry", "payload": {
            "section": "projects", "index": 0, "name": "Ingestion Pipeline",
            "provenance": {"source": "library_auto"}}}],
        session=db_session,
    )

    def no_llm(**kwargs):
        raise AssertionError("pre-ops only: the LLM must not be called")

    monkeypatch.setattr(tailoring_session.llm, "call_openai", no_llm)

    tailored = tailoring_session.tailor(tailoring.id, session=db_session)

    stored = db_session.get(Application, tailored.application_id).customized_json
    assert stored["projects"][0]["enabled"] is True
    assert stored["projects"][0]["bullets"] == ["Streamed events with Kafka; cut lag 20%."]
    _no_voice_problem(stored)


def test_a_keyword_only_the_repaired_line_carried_is_added_back(db_session, tmp_path, monkeypatch, client):
    """The model put the required keyword only in a third-person bullet. The repair drops the
    bullet back to the base, so the keyword must be added to the skills list, not lost."""
    created = _setup(db_session, tmp_path, monkeypatch, client)
    leads = _bullet("He leads the Snowflake migration for Globex.")
    calls = _scripted(monkeypatch, [leads])

    stored = _stored(db_session, _tailor(client, created["id"]))

    assert len(calls) == 2
    assert "He leads" not in json.dumps(stored)
    assert "Snowflake" in json.dumps(stored["skills"])
    _no_voice_problem(stored)


def test_a_real_employer_that_shares_a_name_token_is_left_alone(db_session, tmp_path, monkeypatch, client):
    base = {**BASE, "contact": {"name": "Sam Wells", "email": "sam@example.test"}, "experience": [{**BASE["experience"][0],
            "company": "Initech", "bullets": ["Built fraud models for Wells Ledger."]}]}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="sam", resume_json=base)
    created = _open_session(client, job, slug, resolutions=[KEYWORD])
    calls = _scripted(monkeypatch, [ADD_KEYWORD])

    stored = _stored(db_session, _tailor(client, created["id"]))

    assert len(calls) == 1
    assert stored["experience"][0]["bullets"] == ["Built fraud models for Wells Ledger."]


def test_the_response_lists_the_paths_the_repair_touched(db_session, tmp_path, monkeypatch, client):
    base = {**BASE, "experience": [{**BASE["experience"][0],
            "bullets": ["Built the platform, where he cut load time 20%."]}]}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex12", resume_json=base)
    created = _open_session(client, job, slug, resolutions=[KEYWORD])
    _scripted(monkeypatch, [ADD_KEYWORD])

    body = _tailor(client, created["id"]).json()

    assert body["voice_repairs"] == ["experience[0].bullets[0]"]


def test_a_clean_tailor_reports_no_voice_repairs(db_session, tmp_path, monkeypatch, client):
    created = _setup(db_session, tmp_path, monkeypatch, client)
    _scripted(monkeypatch, [ADD_KEYWORD])

    assert _tailor(client, created["id"]).json()["voice_repairs"] == []


def test_the_mcp_tool_description_names_the_voice_rule():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "mcp_server" / "server.py").read_text()
    doc = source[source.index("def tailor_session("):]
    doc = doc[: doc.index('return {**result, "next": next_hint}')]
    assert "implied first person" in doc


def test_unchanged_lines_about_other_people_are_stored_byte_for_byte(
    db_session, tmp_path, monkeypatch, client
):
    """"They" and "he" after a noun mean other people: the tailor must not touch them
    (a "mechanical" join once turned this into "that; used daily")."""
    lines = ["Built the dashboard that they used daily.",
             "Trained 40 nurses, and they adopted the EHR within a month.",
             "Wrote the model they trusted for fraud checks."]
    base = {**BASE, "experience": [{**BASE["experience"][0], "bullets": list(lines)}]}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex13", resume_json=base)
    created = _open_session(client, job, slug, resolutions=[KEYWORD])
    calls = _scripted(monkeypatch, [ADD_KEYWORD])

    response = _tailor(client, created["id"])

    stored = _stored(db_session, response)
    assert len(calls) == 1
    assert stored["experience"][0]["bullets"] == lines
    assert response.json()["voice_repairs"] == []


def test_base_bullets_where_the_pronoun_follows_a_semicolon_or_colon_are_stored_byte_for_byte(
    db_session, tmp_path, monkeypatch, client
):
    """"; she shipped her first feature" is about the new hire. On the owner's own line a
    he/she after ; : , is flagged for the health check, never rewritten."""
    lines = ["Mentored a new hire; she shipped her first feature in 2 weeks.",
             "Hired Marco as lead; he built the data team to 12.",
             "Onboarded the CFO: she approved the budget."]
    base = {**BASE, "summary": "Data engineer who onboarded the CFO: she approved the budget.",
            "experience": [{**BASE["experience"][0], "bullets": list(lines)}]}
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, slug="alex14", resume_json=base)
    created = _open_session(client, job, slug, resolutions=[KEYWORD])
    calls = _scripted(monkeypatch, [ADD_KEYWORD])

    response = _tailor(client, created["id"])

    stored = _stored(db_session, response)
    assert len(calls) == 1  # an unchanged base line is not a reason to ask the model again
    assert stored["experience"][0]["bullets"] == lines
    assert stored["summary"] == base["summary"]
    assert response.json()["voice_repairs"] == []


def test_the_model_writing_the_same_clause_is_still_retried(db_session, tmp_path, monkeypatch, client):
    created = _setup(db_session, tmp_path, monkeypatch, client)
    calls = _scripted(
        monkeypatch,
        [ADD_KEYWORD, _bullet("Led the routing rewrite; he shipped it to 12 teams.")],
        [ADD_KEYWORD, _bullet("Led the routing rewrite and shipped it to 12 teams.")],
    )

    stored = _stored(db_session, _tailor(client, created["id"]))

    assert len(calls) == 2
    assert stored["experience"][0]["bullets"] == ["Led the routing rewrite and shipped it to 12 teams."]
