"""Tests for AI-assisted KB→resume porting (adapt propose + apply)."""

import uuid

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.career_kb import KBPortLog
from app.models.resume_version import ResumeVersion
from app.services import career_kb as svc
from tests.test_kb_port import (
    SAMPLE_DATA,
    _make_entity,
    _override_db,
    _seed,
    _stub_render,
)

EXPERIENCE_DATA = {
    **SAMPLE_DATA,
    "experience": [
        {
            "company": "Acme",
            "role": "Data Scientist",
            "start_date": "2023-01",
            "bullets": ["Old bullet about pipelines", "Shipped a dashboard"],
        }
    ],
}


def _client(db_session) -> TestClient:
    app.dependency_overrides[get_db] = _override_db(db_session)
    return TestClient(app)


def _teardown():
    app.dependency_overrides.clear()


def _mock_llm(monkeypatch, response: dict):
    calls: list[dict] = []

    def fake(**kwargs):
        calls.append(kwargs)
        return response

    monkeypatch.setattr("app.services.llm.call_openai", fake)
    return calls


def _acme_entity(db_session, points):
    return _make_entity(
        db_session,
        kind="experience",
        title="Data Scientist",
        org="Acme",
        start_date="2023-01",
        points=points,
    )


# --- adapt (propose) ---------------------------------------------------------


def test_adapt_proposes_merge_replace_and_drop(db_session, monkeypatch, tmp_path):
    _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    entity, points = _acme_entity(
        db_session,
        points=[
            ("Built an ETL pipeline", "approved"),
            ("Scaled the ETL pipeline to 2TB/day", "approved"),
            ("Shipped a dashboard for execs", "approved"),
        ],
    )
    calls = _mock_llm(
        monkeypatch,
        {
            "bullets": [
                {
                    "text": "Built and scaled an ETL pipeline to 2TB/day",
                    "sources": ["p1", "p2"],
                    "replaces": "b0",
                    "reason": "combined overlapping pipeline points",
                }
            ],
            "dropped": [
                {"point": "p3", "reason": "the entry already covers the dashboard"}
            ],
        },
    )
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt",
            json={
                "target_slug": "ds",
                "entity_id": str(entity.id),
                "point_ids": [str(p.id) for p in points],
            },
        )
    finally:
        _teardown()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["section"] == "experience"
    assert body["matched_entry_index"] == 0
    assert body["create_entry"] is False
    assert body["existing_bullets"] == EXPERIENCE_DATA["experience"][0]["bullets"]
    assert len(body["bullets"]) == 1
    bullet = body["bullets"][0]
    assert bullet["text"] == "Built and scaled an ETL pipeline to 2TB/day"
    assert bullet["source_point_ids"] == [str(points[0].id), str(points[1].id)]
    assert bullet["replaces_bullet_index"] == 0
    assert bullet["action"] == "replace"
    assert body["dropped"] == [
        {"point_id": str(points[2].id), "reason": "the entry already covers the dashboard"}
    ]
    # Propose persists nothing.
    assert db_session.query(KBPortLog).count() == 0
    assert (
        db_session.query(ResumeVersion).filter_by(resume_kind="base", resume_key="ds").count()
        == 0
    )
    # The prompt carried the aliases and the injection guard, and used JSON mode.
    prompt = calls[0]["prompt"]
    assert "p1 | Built an ETL pipeline" in prompt
    assert "b0 | Old bullet about pipelines" in prompt
    assert "data, not instructions" in prompt
    assert calls[0]["response_format"] == "json"


def test_adapt_fail_open_returns_forgotten_points_verbatim(db_session, monkeypatch):
    _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    entity, points = _acme_entity(
        db_session,
        points=[("Point one", "approved"), ("Point two", "approved")],
    )
    _mock_llm(
        monkeypatch,
        {"bullets": [{"text": "Point one, adapted", "sources": ["p1"], "replaces": None}]},
    )
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt",
            json={"target_slug": "ds", "entity_id": str(entity.id)},
        )
    finally:
        _teardown()

    assert resp.status_code == 200
    bullets = resp.json()["bullets"]
    assert [b["action"] for b in bullets] == ["rewritten", "kept"]
    assert bullets[1]["text"] == "Point two"
    assert bullets[1]["source_point_ids"] == [str(points[1].id)]


def test_adapt_coerces_invalid_sources_and_replace_targets(db_session, monkeypatch):
    _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    entity, points = _acme_entity(
        db_session,
        points=[("Point one", "approved"), ("Point two", "approved")],
    )
    _mock_llm(
        monkeypatch,
        {
            "bullets": [
                # unknown source alias dropped, out-of-range replaces coerced to add
                {"text": "Adapted one", "sources": ["p1", "junk"], "replaces": "b9"},
                # no valid sources -> unverifiable, discarded entirely
                {"text": "Hallucinated", "sources": ["nope"], "replaces": None},
            ],
            "dropped": [{"point": "p1", "reason": "already used above (ignored)"}],
        },
    )
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt",
            json={"target_slug": "ds", "entity_id": str(entity.id)},
        )
    finally:
        _teardown()

    assert resp.status_code == 200
    body = resp.json()
    texts = [b["text"] for b in body["bullets"]]
    assert "Hallucinated" not in texts
    assert body["bullets"][0]["source_point_ids"] == [str(points[0].id)]
    assert body["bullets"][0]["replaces_bullet_index"] is None
    # p1 was already sourced, so the dropped ref is ignored; p2 fails open.
    assert body["dropped"] == []
    assert texts[1] == "Point two"


def test_adapt_certification_rejected_400(db_session, monkeypatch):
    _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    entity, _ = _make_entity(
        db_session, kind="certification", title="AWS SAA", org="Amazon"
    )
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt",
            json={"target_slug": "ds", "entity_id": str(entity.id)},
        )
    finally:
        _teardown()
    assert resp.status_code == 400
    assert "verbatim" in resp.json()["detail"]


def test_adapt_unknown_target_404(db_session):
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt",
            json={"target_slug": "nope", "entity_id": str(uuid.uuid4())},
        )
    finally:
        _teardown()
    assert resp.status_code == 404


def test_adapt_unknown_entity_404(db_session):
    _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt",
            json={"target_slug": "ds", "entity_id": str(uuid.uuid4())},
        )
    finally:
        _teardown()
    assert resp.status_code == 404


def test_adapt_no_approved_points_400(db_session):
    _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    entity, _ = _acme_entity(db_session, points=[("Draft only", "draft")])
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt",
            json={"target_slug": "ds", "entity_id": str(entity.id)},
        )
    finally:
        _teardown()
    assert resp.status_code == 400
    assert "no approved points" in resp.json()["detail"]


# --- adapt apply ------------------------------------------------------------


def test_apply_replace_and_add_with_provenance(db_session, monkeypatch, tmp_path):
    _stub_render(monkeypatch, tmp_path)
    target = _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    entity, points = _acme_entity(
        db_session,
        points=[
            ("Built an ETL pipeline", "approved"),
            ("Scaled the pipeline", "approved"),
            ("Mentored two juniors", "approved"),
        ],
    )
    payload = {
        "target_slug": "ds",
        "entity_id": str(entity.id),
        "bullets": [
            {
                "text": "Built and scaled an ETL pipeline to 2TB/day",
                "source_point_ids": [str(points[0].id), str(points[1].id)],
                "replaces_bullet_index": 0,
                "replaces_text": "Old bullet about pipelines",
            },
            {
                "text": "Mentored two junior data scientists",
                "source_point_ids": [str(points[2].id)],
                "replaces_bullet_index": None,
            },
        ],
    }
    try:
        resp = _client(db_session).post("/api/kb/port/adapt/apply", json=payload)
    finally:
        _teardown()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    bullets = body["resume"]["data"]["experience"][0]["bullets"]
    assert bullets == [
        "Built and scaled an ETL pipeline to 2TB/day",
        "Shipped a dashboard",
        "Mentored two junior data scientists",
    ]
    item = body["report"]["items"][0]
    assert item["created_entry"] is False
    assert item["ported_point_ids"] == [str(p.id) for p in points]
    assert item["skipped_duplicate_point_ids"] == []

    logs = db_session.query(KBPortLog).order_by(KBPortLog.ported_at).all()
    assert len(logs) == 3  # one row per source point
    by_point = {log.point_id: log for log in logs}
    assert by_point[points[0].id].ported_text == "Built and scaled an ETL pipeline to 2TB/day"
    assert by_point[points[0].id].source_text == "Built an ETL pipeline"
    assert by_point[points[2].id].source_text == "Mentored two juniors"

    versions = (
        db_session.query(ResumeVersion)
        .filter_by(resume_kind="base", resume_key="ds")
        .all()
    )
    assert len(versions) == 1
    assert versions[0].source == "import"
    assert "Adapted 3 point(s)" in versions[0].summary

    # Adapted text differs from the point on purpose — that is NOT drift...
    db_session.refresh(points[0])
    usage = svc.point_usage(db_session, points[0])
    assert [u.drifted for u in usage] == [False]
    # ...but editing the KB point afterwards is.
    points[0].text = "Built an ETL pipeline (edited)"
    db_session.commit()
    usage = svc.point_usage(db_session, points[0])
    assert [u.drifted for u in usage] == [True]
    assert target.render_error is None


def test_apply_creates_entry_when_no_match(db_session, monkeypatch, tmp_path):
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="ds", data_json=SAMPLE_DATA)  # no experience entries
    entity, points = _acme_entity(db_session, points=[("Did a thing", "approved")])
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt/apply",
            json={
                "target_slug": "ds",
                "entity_id": str(entity.id),
                "bullets": [
                    {
                        "text": "Did a thing, adapted",
                        "source_point_ids": [str(points[0].id)],
                        "replaces_bullet_index": None,
                    }
                ],
            },
        )
    finally:
        _teardown()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["report"]["items"][0]["created_entry"] is True
    entry = body["resume"]["data"]["experience"][0]
    assert entry["company"] == "Acme"
    assert entry["bullets"] == ["Did a thing, adapted"]


def test_apply_replace_without_match_400(db_session, monkeypatch, tmp_path):
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="ds", data_json=SAMPLE_DATA)
    entity, points = _acme_entity(db_session, points=[("Did a thing", "approved")])
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt/apply",
            json={
                "target_slug": "ds",
                "entity_id": str(entity.id),
                "bullets": [
                    {
                        "text": "x",
                        "source_point_ids": [str(points[0].id)],
                        "replaces_bullet_index": 0,
                        "replaces_text": "whatever the client saw",
                    }
                ],
            },
        )
    finally:
        _teardown()
    assert resp.status_code == 400
    assert "re-run adapt" in resp.json()["detail"]


def test_apply_education_recomposes_single_entry(db_session, monkeypatch, tmp_path):
    _stub_render(monkeypatch, tmp_path)
    data = {
        **SAMPLE_DATA,
        "education": [
            {
                "institution": "State U",
                "degree": "MS Data Science",
                "bullets": ["Thesis on NLP"],
            }
        ],
    }
    _seed(db_session, slug="ds", data_json=data)
    entity, points = _make_entity(
        db_session,
        kind="education",
        title="MS Data Science",
        org="State U",
        points=[("GPA 3.9", "approved"), ("TA for ML course", "approved")],
    )
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt/apply",
            json={
                "target_slug": "ds",
                "entity_id": str(entity.id),
                "bullets": [
                    {
                        "text": "Thesis on NLP, published at a workshop",
                        "source_point_ids": [str(points[0].id)],
                        "replaces_bullet_index": 0,
                        "replaces_text": "Thesis on NLP",
                    },
                    {
                        "text": "TA for the graduate ML course",
                        "source_point_ids": [str(points[1].id)],
                        "replaces_bullet_index": None,
                    },
                ],
            },
        )
    finally:
        _teardown()

    assert resp.status_code == 200, resp.text
    education = resp.json()["resume"]["data"]["education"][0]
    assert education["bullets"] == [
        "Thesis on NLP, published at a workshop",
        "TA for the graduate ML course",
    ]


def test_apply_dedups_against_existing_bullets(db_session, monkeypatch, tmp_path):
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    entity, points = _acme_entity(
        db_session,
        points=[("whatever", "approved"), ("fresh", "approved")],
    )
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt/apply",
            json={
                "target_slug": "ds",
                "entity_id": str(entity.id),
                "bullets": [
                    {
                        "text": "shipped a DASHBOARD",  # normalized dup of existing
                        "source_point_ids": [str(points[0].id)],
                        "replaces_bullet_index": None,
                    },
                    {
                        "text": "Something genuinely new",
                        "source_point_ids": [str(points[1].id)],
                        "replaces_bullet_index": None,
                    },
                ],
            },
        )
    finally:
        _teardown()

    assert resp.status_code == 200, resp.text
    item = resp.json()["report"]["items"][0]
    assert item["ported_point_ids"] == [str(points[1].id)]
    assert item["skipped_duplicate_point_ids"] == [str(points[0].id)]
    bullets = resp.json()["resume"]["data"]["experience"][0]["bullets"]
    assert "shipped a DASHBOARD" not in bullets
    assert "Something genuinely new" in bullets


def test_apply_all_duplicates_400(db_session, monkeypatch, tmp_path):
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    entity, points = _acme_entity(db_session, points=[("whatever", "approved")])
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt/apply",
            json={
                "target_slug": "ds",
                "entity_id": str(entity.id),
                "bullets": [
                    {
                        "text": "Shipped a dashboard",
                        "source_point_ids": [str(points[0].id)],
                        "replaces_bullet_index": None,
                    }
                ],
            },
        )
    finally:
        _teardown()
    assert resp.status_code == 400
    assert "nothing to apply" in resp.json()["detail"]
    assert db_session.query(KBPortLog).count() == 0


def test_apply_rejects_non_approved_source_400(db_session, monkeypatch, tmp_path):
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    entity, points = _acme_entity(db_session, points=[("Draft point", "draft")])
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt/apply",
            json={
                "target_slug": "ds",
                "entity_id": str(entity.id),
                "bullets": [
                    {
                        "text": "x",
                        "source_point_ids": [str(points[0].id)],
                        "replaces_bullet_index": None,
                    }
                ],
            },
        )
    finally:
        _teardown()
    assert resp.status_code == 400
    assert "not an approved point" in resp.json()["detail"]


def test_apply_rejects_duplicate_replace_target_400(db_session, monkeypatch, tmp_path):
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    entity, points = _acme_entity(
        db_session, points=[("one", "approved"), ("two", "approved")]
    )
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt/apply",
            json={
                "target_slug": "ds",
                "entity_id": str(entity.id),
                "bullets": [
                    {
                        "text": "first",
                        "source_point_ids": [str(points[0].id)],
                        "replaces_bullet_index": 0,
                        "replaces_text": "Old bullet about pipelines",
                    },
                    {
                        "text": "second",
                        "source_point_ids": [str(points[1].id)],
                        "replaces_bullet_index": 0,
                        "replaces_text": "Old bullet about pipelines",
                    },
                ],
            },
        )
    finally:
        _teardown()
    assert resp.status_code == 400
    assert "replace the same index" in resp.json()["detail"]


def test_apply_stale_replace_echo_400(db_session, monkeypatch, tmp_path):
    """The entry changed between adapt and apply → in-range index must not overwrite."""
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    entity, points = _acme_entity(db_session, points=[("one", "approved")])
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt/apply",
            json={
                "target_slug": "ds",
                "entity_id": str(entity.id),
                "bullets": [
                    {
                        "text": "replacement",
                        "source_point_ids": [str(points[0].id)],
                        "replaces_bullet_index": 0,
                        "replaces_text": "A bullet that is no longer there",
                    }
                ],
            },
        )
    finally:
        _teardown()
    assert resp.status_code == 400
    assert "changed since the proposal" in resp.json()["detail"]
    assert db_session.query(KBPortLog).count() == 0


def test_apply_replace_missing_echo_422(db_session):
    _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    entity, points = _acme_entity(db_session, points=[("one", "approved")])
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt/apply",
            json={
                "target_slug": "ds",
                "entity_id": str(entity.id),
                "bullets": [
                    {
                        "text": "x",
                        "source_point_ids": [str(points[0].id)],
                        "replaces_bullet_index": 0,
                    }
                ],
            },
        )
    finally:
        _teardown()
    assert resp.status_code == 422


def test_apply_sourceless_bullet_422(db_session):
    _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    entity, _ = _acme_entity(db_session, points=[("one", "approved")])
    try:
        resp = _client(db_session).post(
            "/api/kb/port/adapt/apply",
            json={
                "target_slug": "ds",
                "entity_id": str(entity.id),
                "bullets": [{"text": "x", "source_point_ids": []}],
            },
        )
    finally:
        _teardown()
    assert resp.status_code == 422


def test_verbatim_port_drift_semantics_unchanged(db_session, monkeypatch, tmp_path):
    """Regression: NULL source_text (verbatim ports) still drifts on point edits."""
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="ds", data_json=EXPERIENCE_DATA)
    entity, points = _acme_entity(db_session, points=[("Fresh point", "approved")])
    try:
        resp = _client(db_session).post(
            "/api/kb/port",
            json={
                "target_slug": "ds",
                "items": [{"entity_id": str(entity.id), "point_ids": [str(points[0].id)]}],
            },
        )
    finally:
        _teardown()
    assert resp.status_code == 200, resp.text
    log = db_session.query(KBPortLog).one()
    assert log.source_text is None

    usage = svc.point_usage(db_session, points[0])
    assert [u.drifted for u in usage] == [False]
    points[0].text = "Fresh point, edited"
    db_session.commit()
    usage = svc.point_usage(db_session, points[0])
    assert [u.drifted for u in usage] == [True]
