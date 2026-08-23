"""KBPortLog.direction is stamped at every writer; legacy NULL stays usage-visible."""

from sqlalchemy import select

from app.models.career_kb import KBEntity, KBPoint, KBPortLog
from app.services import career_kb as kb_svc
from app.services.kb_consolidation import consolidate, consolidate_deterministic
from app.services import tailoring_session
from tests.test_kb_port import SAMPLE_DATA, _make_entity, _post_port, _seed, _stub_render
from tests.test_tailoring_sessions_router import (
    _open_library_session,
    _save_library_preops,
    _seed_kb_points,
)


def _resume(**sections):
    base = {
        "contact": {"name": "A", "email": "a@x.com"},
        "summary": None,
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
    }
    base.update(sections)
    return base


def _entity_cluster(group_indices, title):
    return {
        "group_indices": group_indices,
        "existing_entity_id": None,
        "canonical": {
            "kind": "project",
            "title": title,
            "org": None,
            "start_date": None,
            "end_date": None,
        },
    }


def _make_llm(entity_payload, cluster_payload):
    def fake(*, prompt, model, response_format="json", **kw):
        if "group_indices" in prompt:
            return entity_payload
        if "bullet_indices" in prompt:
            return cluster_payload
        raise AssertionError("unexpected prompt")

    return fake


def test_persist_port_stamps_to_resume(db_session, tmp_path, monkeypatch):
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_DATA)
    entity, _points = _make_entity(
        db_session,
        kind="project",
        title="RAG Chatbot",
        points=[("Built a retrieval pipeline.", "approved")],
    )
    res = _post_port(
        db_session,
        {"target_slug": "data_scientist", "items": [{"entity_id": str(entity.id)}]},
    )
    assert res.status_code == 200, res.text
    logs = db_session.scalars(select(KBPortLog)).all()
    assert logs
    assert all(log.direction == "to_resume" for log in logs)


def test_tailor_port_stamps_to_resume(db_session, tmp_path, monkeypatch):
    tailoring = _open_library_session(db_session, tmp_path, monkeypatch)
    approved, _ = _seed_kb_points(db_session)
    _save_library_preops(tailoring, approved, db_session)
    monkeypatch.setattr(
        tailoring_session.llm, "call_openai", lambda **kwargs: {"ops": []}
    )
    tailoring_session.tailor(tailoring.id, session=db_session)
    row = db_session.scalar(select(KBPortLog).where(KBPortLog.point_id == approved.id))
    assert row is not None
    assert row.direction == "to_resume"


def test_consolidate_cluster_logs_stamp_from_source(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(
            entity_payload={"clusters": [_entity_cluster([0], "Orbit")]},
            cluster_payload={
                "clusters": [
                    {"bullet_indices": [0], "existing_point_id": None, "merged_text": None}
                ]
            },
        ),
    )
    r = _resume(projects=[{"name": "Orbit", "bullets": ["Built the ingestion pipeline"]}])
    consolidate(db_session, [("a", r)], commit=False)
    logs = db_session.scalars(select(KBPortLog)).all()
    assert logs
    assert all(log.direction == "from_source" for log in logs)


def test_verbatim_points_logs_stamp_from_source(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        lambda **kw: (_ for _ in ()).throw(AssertionError("no LLM")),
    )
    r = _resume(projects=[{"name": "Orbit", "bullets": ["Shipped the pipeline"]}])
    consolidate_deterministic(db_session, [("ds", r)], commit=False)
    logs = db_session.scalars(select(KBPortLog)).all()
    assert logs
    assert all(log.direction == "from_source" for log in logs)


def test_null_direction_legacy_rows_still_appear_in_usage(db_session):
    ent = KBEntity(kind="project", title="Orbit")
    db_session.add(ent)
    db_session.flush()
    point = KBPoint(
        entity_id=ent.id, text="Built it", state="approved", origin="manual"
    )
    db_session.add(point)
    db_session.flush()
    db_session.add(
        KBPortLog(
            entity_id=ent.id,
            point_id=point.id,
            resume_kind="base",
            resume_key="hybrid",
            section="projects",
            ported_text="Built it",
            direction=None,
        )
    )
    db_session.flush()
    usage = kb_svc.point_usage(db_session, point)
    assert [u.resume_key for u in usage] == ["hybrid"]


def test_usage_includes_both_directions_and_flags_sync_drift(db_session):
    ent = KBEntity(kind="project", title="Orbit")
    db_session.add(ent)
    db_session.flush()
    point = KBPoint(
        entity_id=ent.id, text="Built it", state="approved", origin="manual"
    )
    db_session.add(point)
    db_session.flush()
    db_session.add_all(
        [
            KBPortLog(
                entity_id=ent.id,
                point_id=point.id,
                resume_kind="base",
                resume_key="placed",
                section="projects",
                ported_text="Built it",
                direction="to_resume",
            ),
            KBPortLog(
                entity_id=ent.id,
                point_id=point.id,
                resume_kind="base",
                resume_key="ingest",
                section="projects",
                ported_text="Built it slightly differently",
                direction="from_source",
            ),
        ]
    )
    db_session.flush()
    usage = kb_svc.point_usage(db_session, point)
    by_key = {u.resume_key: u for u in usage}
    assert set(by_key) == {"placed", "ingest"}
    assert by_key["placed"].direction == "to_resume"
    assert by_key["placed"].drifted is False
    # The base's variant wording IS drift, visible from the point's usage —
    # this is what lights the Drifted badge for base-sync notes.
    assert by_key["ingest"].direction == "from_source"
    assert by_key["ingest"].drifted is True
