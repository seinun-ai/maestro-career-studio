"""Saved add_keyword answers survive a tailor on every path.

The caller-ops path (MCP `tailor_session(ops=...)`) applied the agent's edits and
nothing else, so a saved "add Snowflake to the Cloud skills" silently missed the
tailored resume when the ops left it out. Now the keyword survival step the
app's own model path had runs after either kind of edits: a saved keyword whose
word is not on the resume goes into the skills list, never a bullet (§6
inv-honesty), and the response names it. A keyword saved with only a place
falls back to the gap's own skill. user_input and attach_project answers need
new text, so on the ops path the response lists them for the ops to carry.

`no_new_text` is the third path: Maestro writes no wording and calls no model,
in either writer mode. It applies only the answers that need none (an enabled
entry, a ported career-history bullet, saved keywords into skills) and lists
the rest the same way.

Every tailor names its `unbacked_skills`: missing skills now anywhere live on
the resume that career history and the saved answers don't back, whoever put
them there. "Backed" is read off the frozen gap, never off a caller's payload.
"""

import json
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models.application import Application
from app.models.tailoring_session import TailoringSession
from tests.agent_writer_fixtures import (
    MCP,
    forbid_model,
    key_configured,
    model_replies,
    set_writer,
)
from tests.ats.fixtures import SAMPLE_RESUME
from tests.test_tailoring_sessions_router import (
    _forbid_llm,
    _mock_prompt_files,
    _mock_tailor_llm,
    _open_library_session,
    _open_session,
    _save_library_preops,
    _seed_base,
    _seed_job,
    _seed_kb_points,
    _tailor,
)

# Snowflake is an `adjacent` gap; saved as an MCP caller may, with a place and no wording.
SNOWFLAKE_PLACE_ONLY = {
    "gap_id": "skill:snowflake",
    "action": "add_keyword",
    "payload": {"placement_target": {"section": "skills", "index_or_category": "Cloud"}},
}
SALESFORCE_WORDED = {
    "gap_id": "skill:salesforce",
    "action": "add_keyword",
    "payload": {
        "placement_target": {"section": "skills", "index_or_category": "Tools"},
        "wording": "Salesforce",
    },
}
ML_MODELS_ANSWER = {
    "gap_id": "coverage:0",
    "action": "user_input",
    "payload": {"text": "Trained churn models in scikit-learn for two years."},
}
DOCKER_PROJECT = {
    "gap_id": "skill:docker",
    "action": "attach_project",
    "payload": {"project_name": "RAG Search"},
}
# Tableau is a resurface gap: already in an old bullet, so moving it to the current
# job means a rewritten bullet, which no_new_text does not write.
TABLEAU_ON_CURRENT_JOB = {
    "gap_id": "skill:tableau",
    "action": "add_keyword",
    "payload": {
        "placement_target": {"section": "experience", "index_or_category": 0},
        "wording": "Tableau",
    },
}


def _skills(application) -> dict[str, list[str]]:
    return {g["category"]: g["items"] for g in application.customized_json["skills"]}


def _bullets(application) -> list[str]:
    return _bullets_of(application.customized_json)


def _bullets_of(resume) -> list[str]:
    return [
        bullet
        for section in ("experience", "projects")
        for entry in resume.get(section) or []
        for bullet in entry.get("bullets") or []
    ]


def test_a_saved_keyword_the_ops_left_out_goes_into_skills(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _forbid_llm(monkeypatch)
    created = _open_session(
        client, job, slug,
        resolutions=[SNOWFLAKE_PLACE_ONLY, SALESFORCE_WORDED, ML_MODELS_ANSWER, DOCKER_PROJECT],
    )

    # The agent's edits carry Salesforce and nothing about Snowflake.
    response = _tailor(
        client, created["id"],
        body={"ops": [{"kind": "add_skill_item", "category": "Tools", "item": "Salesforce"}]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["keywords_added"] == ["Snowflake"]
    application = db_session.get(Application, UUID(body["session"]["application_id"]))
    skills = _skills(application)
    assert "Snowflake" in skills["Cloud"]
    assert skills["Tools"].count("Salesforce") == 1
    assert not any("Snowflake" in bullet for bullet in _bullets(application))
    assert body["answers_left_to_ops"] == [
        {"gap_id": "coverage:0", "action": "user_input", "skill": "Build ML models"},
        {"gap_id": "skill:docker", "action": "attach_project", "skill": "Docker"},
    ]


def test_ops_that_carry_every_keyword_add_nothing(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _forbid_llm(monkeypatch)
    created = _open_session(client, job, slug, resolutions=[SNOWFLAKE_PLACE_ONLY])

    response = _tailor(
        client, created["id"],
        body={"ops": [{"kind": "add_skill_item", "category": "Cloud", "item": "Snowflake"}]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["keywords_added"] == []
    assert response.json()["answers_left_to_ops"] == []


def test_the_model_path_also_keeps_a_keyword_saved_with_only_a_place(
    db_session, tmp_path, monkeypatch, client
):
    """The app's own model leaves Snowflake out twice (the first answer and the
    corrective retry): the shared survival step adds it, and says so."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    calls = _mock_tailor_llm(monkeypatch, response={"ops": []})
    created = _open_session(client, job, slug, resolutions=[SNOWFLAKE_PLACE_ONLY])

    response = _tailor(client, created["id"])

    assert response.status_code == 200, response.text
    assert len(calls) == 2  # the first answer and the one corrective retry
    assert "Snowflake" in calls[1]["prompt"]
    body = response.json()
    assert body["keywords_added"] == ["Snowflake"]
    assert body["answers_left_to_ops"] == []  # the model path reads every answer
    application = db_session.get(Application, UUID(body["session"]["application_id"]))
    assert "Snowflake" in _skills(application)["Cloud"]


def test_no_new_text_applies_only_what_needs_no_wording(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    key_configured(monkeypatch)  # with a key configured it still must not reach the model
    forbid_model(monkeypatch)
    created = _open_session(
        client, job, slug,
        resolutions=[SNOWFLAKE_PLACE_ONLY, SALESFORCE_WORDED, ML_MODELS_ANSWER, DOCKER_PROJECT],
    )

    response = _tailor(client, created["id"], body={"no_new_text": True})

    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(body["keywords_added"]) == ["Salesforce", "Snowflake"]
    assert body["answers_left_to_ops"] == [
        {"gap_id": "coverage:0", "action": "user_input", "skill": "Build ML models"},
        {"gap_id": "skill:docker", "action": "attach_project", "skill": "Docker"},
    ]
    application = db_session.get(Application, UUID(body["session"]["application_id"]))
    assert "Snowflake" in _skills(application)["Cloud"]
    assert not any("churn" in b for b in _bullets(application))  # the typed answer needs wording


def test_no_new_text_lands_an_enabled_entry_and_a_career_history_bullet(
    db_session, tmp_path, monkeypatch, client
):
    """Over MCP with the agent app writing: refused without no_new_text, applied with it."""
    tailoring = _open_library_session(db_session, tmp_path, monkeypatch)
    approved, _ = _seed_kb_points(db_session)
    _save_library_preops(tailoring, approved, db_session)
    set_writer(client, monkeypatch, tmp_path, "agent")
    key_configured(monkeypatch)
    forbid_model(monkeypatch)

    assert _tailor(client, str(tailoring.id), body={}, headers=MCP).status_code == 409
    response = _tailor(client, str(tailoring.id), body={"no_new_text": True}, headers=MCP)

    assert response.status_code == 200, response.text
    application = db_session.get(Application, UUID(response.json()["session"]["application_id"]))
    assert application.customized_json["projects"][0]["enabled"] is True
    assert approved.text in application.customized_json["projects"][1]["bullets"]
    # Both skills now on the resume come from checked evidence, so neither is unbacked.
    assert response.json()["unbacked_skills"] == []


def test_no_new_text_lists_a_keyword_that_needs_a_rewritten_bullet(
    db_session, tmp_path, monkeypatch, client
):
    """Placed on a job: Tableau is already in an old bullet, so survival adds nothing and
    the answer is listed; Snowflake is nowhere on the resume, so survival puts it in skills."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    forbid_model(monkeypatch)
    snowflake_on_current_job = {
        "gap_id": "skill:snowflake",
        "action": "add_keyword",
        "payload": {"placement_target": {"section": "experience", "index_or_category": 0}},
    }
    created = _open_session(
        client, job, slug, resolutions=[TABLEAU_ON_CURRENT_JOB, snowflake_on_current_job]
    )

    response = _tailor(client, created["id"], body={"no_new_text": True})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["keywords_added"] == ["Snowflake"]
    assert body["answers_left_to_ops"] == [
        {"gap_id": "skill:tableau", "action": "add_keyword", "skill": "Tableau"},
    ]
    application = db_session.get(Application, UUID(body["session"]["application_id"]))
    assert application.customized_json["experience"][0]["bullets"] == (
        SAMPLE_RESUME["experience"][0]["bullets"]
    )


def test_no_new_text_puts_a_keyword_saved_into_skills_there_even_when_a_bullet_has_it(
    db_session, tmp_path, monkeypatch, client
):
    """Tableau is in an old bullet, so survival alone would add nothing; saved into
    Tools, it lands in Tools, since a skills item needs no wording. A place-only
    keyword saved into skills reads as its gap's skill, as survival does."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    forbid_model(monkeypatch)
    tableau_into_tools = {
        "gap_id": "skill:tableau",
        "action": "add_keyword",
        "payload": {"placement_target": {"section": "skills", "index_or_category": "Tools"}},
    }
    created = _open_session(client, job, slug, resolutions=[tableau_into_tools])

    response = _tailor(client, created["id"], body={"no_new_text": True})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["keywords_added"] == ["Tableau"]
    assert body["answers_left_to_ops"] == []
    application = db_session.get(Application, UUID(body["session"]["application_id"]))
    assert _skills(application)["Tools"] == ["Git", "Jira", "Tableau"]
    assert _bullets(application) == _bullets_of(SAMPLE_RESUME)


def test_no_new_text_takes_no_ops(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    forbid_model(monkeypatch)
    created = _open_session(client, job, slug, resolutions=[SALESFORCE_WORDED])

    response = _tailor(
        client, created["id"],
        body={
            "no_new_text": True,
            "ops": [{"kind": "add_skill_item", "category": "Tools", "item": "Salesforce"}],
        },
    )

    assert response.status_code == 422, response.text
    assert "no_new_text writes nothing new, so it takes no ops" in response.text
    assert db_session.get(TailoringSession, UUID(created["id"])).status == "open"
    assert db_session.scalars(select(Application)).all() == []


def test_no_new_text_with_nothing_to_apply_says_so(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    key_configured(monkeypatch)
    forbid_model(monkeypatch)
    created = _open_session(
        client, job, slug,
        resolutions=[
            ML_MODELS_ANSWER,
            {"gap_id": "skill:docker", "action": "skip"},
            TABLEAU_ON_CURRENT_JOB,  # needs a rewritten bullet, so it applies nothing either
        ],
    )

    response = _tailor(client, created["id"], body={"no_new_text": True})

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == (
        "Nothing can be applied without new wording: the saved answers need text written "
        "for them, or are already on the resume."
    )
    assert db_session.get(TailoringSession, UUID(created["id"])).status == "open"
    assert db_session.scalars(select(Application)).all() == []


def test_an_agent_app_that_writes_may_tailor_with_no_new_text(
    db_session, tmp_path, monkeypatch, client
):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    created = _open_session(client, job, slug, resolutions=[SALESFORCE_WORDED])
    set_writer(client, monkeypatch, tmp_path, "agent")
    key_configured(monkeypatch)
    forbid_model(monkeypatch)

    # Without ops or no_new_text Maestro's AI would write, so the agent app is refused.
    assert _tailor(client, created["id"], body={}, headers=MCP).status_code == 409
    response = _tailor(client, created["id"], body={"no_new_text": True}, headers=MCP)

    assert response.status_code == 200, response.text
    assert response.json()["keywords_added"] == ["Salesforce"]


def test_no_new_text_after_the_presets_fill_needs_no_model(db_session, tmp_path, monkeypatch, client):
    """apply_profile with no_new_text: the presets fill is deterministic too, so an
    agent app that writes may run both in one call and Maestro still writes nothing."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    created = _open_session(client, job, slug)
    set_writer(client, monkeypatch, tmp_path, "agent")
    key_configured(monkeypatch)
    forbid_model(monkeypatch)

    response = _tailor(
        client, created["id"], body={"apply_profile": True, "no_new_text": True}, headers=MCP
    )

    assert response.status_code == 200, response.text
    assert "Docker" in response.json()["keywords_added"]  # the presets' missing-skill add
    assert "Docker" in response.json()["unbacked_skills"]  # nothing in career history shows it


def _into_skills(gap_id, wording=None, provenance=None) -> dict:
    payload = {"placement_target": {"section": "skills", "index_or_category": "Tools"}}
    if wording is not None:
        payload["wording"] = wording
    if provenance is not None:
        payload["provenance"] = provenance
    return {"gap_id": gap_id, "action": "add_keyword", "payload": payload}


DOCKER_INTO_SKILLS = _into_skills("skill:docker", "Docker")
DOCKER_BULLET = {
    "kind": "add_bullet", "section": "experience", "index": 0,
    "text": "Containerized the forecasting service with Docker.",
}


def _gap(created, gap_id) -> dict:
    return next(
        gap for category in created["gaps_json"]["categories"]
        for gap in category["gaps"] if gap["gap_id"] == gap_id
    )


def test_a_tailor_names_the_missing_skills_it_put_in_skills(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    forbid_model(monkeypatch)
    created = _open_session(client, job, slug, resolutions=[DOCKER_INTO_SKILLS, SNOWFLAKE_PLACE_ONLY])
    # Docker is a missing skill nothing in career history shows.
    assert _gap(created, "skill:docker")["diagnostic"]["fix_hint"] == "absent"
    assert not _gap(created, "skill:docker").get("library_candidates")

    response = _tailor(client, created["id"], body={"no_new_text": True})

    assert response.status_code == 200, response.text
    assert sorted(response.json()["keywords_added"]) == ["Docker", "Snowflake"]
    # Snowflake is adjacent: the resume shows a related skill, so it is not unbacked.
    assert response.json()["unbacked_skills"] == ["Docker"]


def test_backed_is_read_off_the_gap_not_the_callers_payload(
    db_session, tmp_path, monkeypatch, client
):
    """A provenance a caller sends does not back Docker. Salesforce is backed: career
    history shows it (a hidden entry says "Salesforce admin work."), so the analysis
    plans an automatic answer for its gap."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    forbid_model(monkeypatch)
    created = _open_session(
        client, job, slug,
        resolutions=[
            _into_skills("skill:docker", "Docker", provenance={"source": "kb_profile"}),
            SALESFORCE_WORDED,
        ],
    )
    assert _gap(created, "skill:salesforce")["library_candidates"][0]["auto"] is True

    response = _tailor(client, created["id"], body={"no_new_text": True})

    assert response.status_code == 200, response.text
    assert sorted(response.json()["keywords_added"]) == ["Docker", "Salesforce"]
    assert response.json()["unbacked_skills"] == ["Docker"]


def test_a_missing_skill_the_callers_ops_put_in_a_bullet_is_named(
    db_session, tmp_path, monkeypatch, client
):
    """Saved into skills, written into a bullet by the caller: survival adds nothing,
    and the skill is still named wherever it landed."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    forbid_model(monkeypatch)
    created = _open_session(client, job, slug, resolutions=[DOCKER_INTO_SKILLS])

    response = _tailor(client, created["id"], body={"ops": [DOCKER_BULLET]})

    assert response.status_code == 200, response.text
    assert response.json()["keywords_added"] == []
    assert response.json()["unbacked_skills"] == ["Docker"]


@pytest.mark.parametrize(
    ("resolutions", "unbacked"),
    [
        ([], ["Docker"]),
        ([{"gap_id": "skill:docker", "action": "skip"}], ["Docker"]),
        ([{"gap_id": "skill:docker", "action": "user_input",
           "payload": {"text": "Ran the team's services in Docker for two years."}}], []),
    ],
    ids=["no-answer", "skipped", "the-user-said-so"],
)
def test_a_missing_skill_the_callers_ops_wrote_without_a_keyword_answer(
    db_session, tmp_path, monkeypatch, client, resolutions, unbacked
):
    """No saved keyword: named when the caller's ops write it, unless the saved answer
    shows the skill itself (the user's own words). Salesforce, written alongside, is
    backed by career history."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    forbid_model(monkeypatch)
    created = _open_session(client, job, slug, resolutions=resolutions)

    response = _tailor(
        client, created["id"],
        body={"ops": [
            DOCKER_BULLET,
            {"kind": "add_skill_item", "category": "Tools", "item": "Salesforce"},
        ]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["unbacked_skills"] == unbacked


def test_the_ops_path_names_unbacked_skills_saved_with_only_a_place(
    db_session, tmp_path, monkeypatch, client
):
    """A place-only keyword's word is the gap's own skill, as keyword survival reads it."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    forbid_model(monkeypatch)
    created = _open_session(client, job, slug, resolutions=[_into_skills("skill:docker")])

    response = _tailor(
        client, created["id"],
        body={"ops": [{"kind": "add_skill_item", "category": "Tools", "item": "Salesforce"}]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["keywords_added"] == ["Docker"]
    assert response.json()["unbacked_skills"] == ["Docker"]


def test_the_model_path_names_unbacked_skills(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_prompt_files(monkeypatch)
    created = _open_session(client, job, slug, resolutions=[DOCKER_INTO_SKILLS])
    model_replies(
        monkeypatch, tmp_path,
        json.dumps({"ops": [{"kind": "add_skill_item", "category": "Tools", "item": "Docker"}]}),
    )

    response = _tailor(client, created["id"])

    assert response.status_code == 200, response.text
    assert response.json()["keywords_added"] == []  # the model's own edit carried it
    assert response.json()["unbacked_skills"] == ["Docker"]
