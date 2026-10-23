"""Saved add_keyword answers survive a tailor on every path.

The caller-ops path (MCP `tailor_session(ops=...)`) applied the agent's edits and
nothing else, so a saved "add Snowflake to the Cloud skills" silently missed the
tailored resume when the ops left it out. Now the keyword survival step the
app's own model path had runs after either kind of edits: a saved keyword whose
word is not on the resume goes into the skills list, never a bullet (§6
inv-honesty), and the response names it. A keyword saved with only a place
falls back to the gap's own skill. user_input and attach_project answers need
new text, so on the ops path the response lists them for the ops to carry.
"""

from uuid import UUID

from app.models.application import Application
from tests.test_tailoring_sessions_router import (
    _forbid_llm,
    _mock_tailor_llm,
    _open_session,
    _seed_base,
    _seed_job,
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


def _skills(application) -> dict[str, list[str]]:
    return {g["category"]: g["items"] for g in application.customized_json["skills"]}


def _bullets(application) -> list[str]:
    return [
        bullet
        for section in ("experience", "projects")
        for entry in application.customized_json.get(section) or []
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
