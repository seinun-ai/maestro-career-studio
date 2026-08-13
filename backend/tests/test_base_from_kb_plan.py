import pytest

from app.models.career_kb import KBEntity, KBPoint
from app.services import base_from_kb_plan


def _entity(db_session, kind, title, *, points=1, status="active", org=None):
    entity = KBEntity(kind=kind, title=title, org=org, status=status, detail_json={})
    db_session.add(entity)
    db_session.flush()
    for i in range(points):
        db_session.add(
            KBPoint(
                entity_id=entity.id,
                text=f"{title} point {i}",
                state="approved",
                origin="manual",
            )
        )
    db_session.flush()
    return entity


def _llm(payload):
    def fake(*, prompt, model, response_format="json", **kw):
        fake.prompt = prompt
        return payload

    return fake


def test_plan_returns_include_exclude_and_summary(db_session, monkeypatch):
    keep = _entity(db_session, "experience", "Data Scientist", org="Acme")
    drop = _entity(db_session, "experience", "Barista", org="Cafe")
    db_session.commit()

    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _llm({
            "include": [str(keep.id)],
            "exclude": [{"id": str(drop.id), "reason": "not relevant to the role"}],
            "summary": "Data scientist with production ML experience.",
        }),
    )

    plan = base_from_kb_plan.plan(db_session, "data_scientist", "focus on ML")

    assert [str(i) for i in plan.include] == [str(keep.id)]
    assert plan.exclude[0].reason == "not relevant to the role"
    assert plan.summary.startswith("Data scientist")


def test_plan_ignores_ids_the_model_invented(db_session, monkeypatch):
    """A hallucinated id must not reach the compose call as a real selection."""
    keep = _entity(db_session, "project", "Orbit")
    db_session.commit()

    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _llm({
            "include": [str(keep.id), "11111111-1111-1111-1111-111111111111"],
            "exclude": [],
            "summary": "",
        }),
    )

    plan = base_from_kb_plan.plan(db_session, "data_scientist", "")

    assert [str(i) for i in plan.include] == [str(keep.id)]


def test_plan_never_includes_a_bulletless_experience_or_project(db_session, monkeypatch):
    """Those two sections render FROM bullets, so a point-less one is empty."""
    empty = _entity(db_session, "project", "Placeholder", points=0)
    db_session.commit()

    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _llm({"include": [str(empty.id)], "exclude": [], "summary": ""}),
    )

    plan = base_from_kb_plan.plan(db_session, "data_scientist", "")

    assert plan.include == []


def test_plan_keeps_certifications_and_education_that_have_no_points(
    db_session, monkeypatch
):
    """Regression: certifications compose to a bare title string and education
    to institution/degree/dates, so neither needs bullets. Requiring points
    silently dropped EVERY certification the candidate held — seen on real
    data before this distinction existed."""
    cert = _entity(db_session, "certification", "AWS Solutions Architect", points=0)
    edu = _entity(db_session, "education", "MS Business Analytics", points=0)
    db_session.commit()

    fake = _llm({
        "include": [str(cert.id), str(edu.id)],
        "exclude": [],
        "summary": "",
    })
    monkeypatch.setattr("app.services.llm.call_openai", fake)

    plan = base_from_kb_plan.plan(db_session, "data_scientist", "")

    assert {str(i) for i in plan.include} == {str(cert.id), str(edu.id)}
    # They must also be offered to the model in the first place.
    assert "AWS Solutions Architect" in fake.prompt


def test_plan_hides_bulletless_experience_from_the_model_entirely(
    db_session, monkeypatch
):
    """Unselectable entries must not appear as 'left off' noise either."""
    ok = _entity(db_session, "experience", "Data Engineer")
    empty = _entity(db_session, "experience", "Ghost Role", points=0)
    db_session.commit()

    fake = _llm({
        "include": [str(ok.id)],
        "exclude": [{"id": str(empty.id), "reason": "no points"}],
        "summary": "",
    })
    monkeypatch.setattr("app.services.llm.call_openai", fake)

    plan = base_from_kb_plan.plan(db_session, "data_scientist", "")

    assert "Ghost Role" not in fake.prompt
    assert plan.exclude == []


def test_plan_excludes_archived_entities_from_the_prompt(db_session, monkeypatch):
    live = _entity(db_session, "experience", "Current Role")
    _entity(db_session, "experience", "Old Role", status="archived")
    db_session.commit()

    fake = _llm({"include": [str(live.id)], "exclude": [], "summary": ""})
    monkeypatch.setattr("app.services.llm.call_openai", fake)

    base_from_kb_plan.plan(db_session, "data_scientist", "")

    assert "Current Role" in fake.prompt
    assert "Old Role" not in fake.prompt


def test_plan_prompt_includes_one_line_of_context_for_a_described_role(
    db_session, monkeypatch
):
    _entity(db_session, "experience", "Forward Deployed Engineer")
    db_session.commit()
    fake = _llm({"include": [], "exclude": [], "summary": ""})
    monkeypatch.setattr("app.services.llm.call_openai", fake)
    monkeypatch.setattr(
        base_from_kb_plan.prompts,
        "get_prompt",
        lambda *args: "TARGET ROLE: $role_label\nUSER INSTRUCTION: $instruction\n$entities",
    )

    base_from_kb_plan.plan(db_session, "forward_deployed_engineer", "")

    assert (
        "TARGET ROLE: Forward Deployed Engineer\n"
        "ROLE DESCRIPTION: Embeds with customers to adapt and deploy software or AI "
        "solutions in real operating environments.\n"
        "USER INSTRUCTION"
    ) in fake.prompt


def test_plan_prompt_has_no_description_artifact_for_an_obvious_role(
    db_session, monkeypatch
):
    _entity(db_session, "experience", "QA Engineer")
    db_session.commit()
    fake = _llm({"include": [], "exclude": [], "summary": ""})
    monkeypatch.setattr("app.services.llm.call_openai", fake)
    monkeypatch.setattr(
        base_from_kb_plan.prompts,
        "get_prompt",
        lambda *args: "TARGET ROLE: $role_label\nUSER INSTRUCTION: $instruction\n$entities",
    )

    base_from_kb_plan.plan(db_session, "qa_engineer", "")

    assert "TARGET ROLE: QA / Test Engineer\nUSER INSTRUCTION" in fake.prompt
    assert "ROLE DESCRIPTION:" not in fake.prompt


@pytest.mark.parametrize(
    "template,expected",
    [
        (
            "Plan for $role_label today.",
            "Plan for Forward Deployed Engineer today.",
        ),
        (
            "TARGET ROLE: $role_label\nCompare with $role_label",
            "TARGET ROLE: Forward Deployed Engineer\n"
            "ROLE DESCRIPTION: Embeds with customers to adapt and deploy software or AI "
            "solutions in real operating environments.\n"
            "Compare with Forward Deployed Engineer",
        ),
    ],
)
def test_custom_prompt_keeps_role_label_pure_and_injects_context_once(
    db_session, monkeypatch, template, expected
):
    _entity(db_session, "experience", "Forward Deployed Engineer")
    db_session.commit()
    fake = _llm({"include": [], "exclude": [], "summary": ""})
    monkeypatch.setattr("app.services.llm.call_openai", fake)
    monkeypatch.setattr(
        base_from_kb_plan.prompts, "get_prompt", lambda *args: template
    )

    base_from_kb_plan.plan(db_session, "forward_deployed_engineer", "")

    assert fake.prompt == expected


def test_plan_on_an_empty_kb_is_a_value_error(db_session):
    with pytest.raises(ValueError, match="Career KB"):
        base_from_kb_plan.plan(db_session, "data_scientist", "")


def test_plan_surfaces_a_provider_outage_as_runtime_error(db_session, monkeypatch):
    _entity(db_session, "experience", "Data Scientist")
    db_session.commit()

    def boom(**kw):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("app.services.llm.call_openai", boom)

    with pytest.raises(RuntimeError):
        base_from_kb_plan.plan(db_session, "data_scientist", "")


def test_plan_rejects_a_non_object_response(db_session, monkeypatch):
    _entity(db_session, "experience", "Data Scientist")
    db_session.commit()
    monkeypatch.setattr("app.services.llm.call_openai", _llm(["nope"]))

    with pytest.raises(ValueError):
        base_from_kb_plan.plan(db_session, "data_scientist", "")


# --- endpoint ---------------------------------------------------------------


@pytest.fixture
def client(db_session):
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_plan_endpoint_returns_the_proposal(client, db_session, monkeypatch):
    keep = _entity(db_session, "experience", "Data Scientist")
    drop = _entity(db_session, "experience", "Barista")
    db_session.commit()
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _llm({
            "include": [str(keep.id)],
            "exclude": [{"id": str(drop.id), "reason": "not relevant"}],
            "summary": "Focused summary.",
        }),
    )

    r = client.post(
        "/api/base-resumes/from-kb/plan",
        json={"role_category": "data_scientist", "instruction": "ML focus"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["include"] == [str(keep.id)]
    assert body["exclude"][0]["title"] == "Barista"
    assert body["summary"] == "Focused summary."


def test_plan_endpoint_422s_on_an_empty_kb(client):
    r = client.post(
        "/api/base-resumes/from-kb/plan",
        json={"role_category": "data_scientist", "instruction": ""},
    )
    assert r.status_code == 422


def test_plan_endpoint_502s_when_the_provider_is_down(client, db_session, monkeypatch):
    _entity(db_session, "experience", "Data Scientist")
    db_session.commit()

    def boom(**kw):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("app.services.llm.call_openai", boom)

    r = client.post(
        "/api/base-resumes/from-kb/plan",
        json={"role_category": "data_scientist", "instruction": ""},
    )
    assert r.status_code == 502


def test_from_kb_persists_a_reviewed_summary(client, db_session, monkeypatch, tmp_path):
    """The plan's summary, once reviewed, must survive onto the created resume."""
    from app.models.base_resume import BaseResume

    monkeypatch.setattr("app.routers.base_resumes.settings.base_resumes_dir", tmp_path)
    monkeypatch.setattr(
        "app.routers.base_resumes.base_resume_render.render_base_resume",
        lambda slug, db, **kw: db.get(BaseResume, slug),
    )
    keep = _entity(db_session, "experience", "Data Scientist", org="Acme")
    db_session.commit()

    r = client.post(
        "/api/base-resumes/from-kb",
        json={
            "role_category": "data_scientist",
            "entity_ids": [str(keep.id)],
            "summary": "  Reviewed and edited.  ",
        },
    )

    assert r.status_code == 200, r.text
    assert r.json()["data"]["summary"] == "Reviewed and edited."
