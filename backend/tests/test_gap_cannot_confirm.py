"""Task 10 (Phase C): the "I can't confirm this" gap outcome.

A `cannot_confirm` resolution behaves like `skip` for the document but writes a
durable suppression record: a retired KBPoint with
provenance="user_cannot_confirm". That provenance NEVER decays back to a
trusted value by any code path (`inv-provenance-no-decay` — this file carries
the behavioral enforcement pin `test_nothing_upgrades_user_cannot_confirm`).
"""
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.career_kb import KBEntity, KBPoint
from app.models.job import Job
from app.models.tailoring_session import TailoringSession
from app.services import kb_base_sync, kb_resolver, tailoring_session
from app.services.career_kb import compose_resume_data
from app.services.kb_consolidation import consolidate_deterministic
from app.services.tailoring_session import CANNOT_CONFIRM_HOLDER_TITLE
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME


def _seed_job(db_session):
    job = Job(raw_text="jd", raw_text_hash="cc-hash", extracted_json=SAMPLE_JD)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _seed_base(db_session, tmp_path, monkeypatch, slug="cc_base", resume_json=None):
    from app.models.base_resume import BaseResume

    resume_json = resume_json or SAMPLE_RESUME
    monkeypatch.setattr(settings, "base_resumes_dir", tmp_path)
    (tmp_path / f"{slug}.json").write_text(json.dumps(resume_json))
    db_session.add(BaseResume(slug=slug, data_json=resume_json))
    db_session.commit()
    return slug


def _open_session(db_session, tmp_path, monkeypatch, *, gaps=None):
    """An open session with hand-frozen gaps (mirrors the router-test helper)."""
    resume = json.loads(json.dumps(SAMPLE_RESUME))
    resume["projects"] = [
        {
            "name": "Ingestion Pipeline",
            "enabled": False,
            "bullets": ["Streamed events with Kafka"],
            "tech": "Kafka",
        },
        {
            "name": "Churn Model",
            "enabled": True,
            "bullets": ["Trained XGBoost model"],
            "tech": "",
        },
    ]
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, resume_json=resume)
    gaps = gaps or [
        {
            "gap_id": "skill:kafka",
            "kind": "skill",
            "jd_skill": "Kafka",
            "diagnostic": {"fix_hint": "absent"},
            "actions": ["add_keyword", "user_input", "cannot_confirm", "skip"],
        },
        {
            "gap_id": "skill:mlflow",
            "kind": "skill",
            "jd_skill": "MLflow",
            "diagnostic": {"fix_hint": "absent"},
            "actions": ["add_keyword", "user_input", "cannot_confirm", "skip"],
        },
    ]
    tailoring = TailoringSession(
        job_id=job.id,
        base_resume=slug,
        status="open",
        gaps_json={"categories": [{"key": "missing_skills", "gaps": gaps}]},
        resolutions_json=[],
    )
    db_session.add(tailoring)
    db_session.commit()
    db_session.refresh(tailoring)
    return tailoring


def _save_cannot_confirm(tailoring, db_session, gap_id="skill:kafka", payload=None):
    return tailoring_session.save_resolutions(
        tailoring.id,
        [{"gap_id": gap_id, "action": "cannot_confirm", "payload": payload or {}}],
        session=db_session,
    )


def _cc_points(db_session):
    return db_session.scalars(
        select(KBPoint).where(KBPoint.provenance == "user_cannot_confirm")
    ).all()


# --- storing the claim ------------------------------------------------------


def test_cannot_confirm_stores_retired_point_on_holder(db_session, tmp_path, monkeypatch):
    """No entity matches the gap → the claim lands on the archived holder
    entity, retired, so it is queryable but invisible to compose/snapshot."""
    tailoring = _open_session(db_session, tmp_path, monkeypatch)

    _save_cannot_confirm(tailoring, db_session)

    points = _cc_points(db_session)
    assert len(points) == 1
    point = points[0]
    assert point.state == "retired"
    assert point.origin == "gap_elicitation"
    assert point.text == "Kafka"
    assert point.origin_detail == f"tailoring_session:{tailoring.id}"
    holder = db_session.get(KBEntity, point.entity_id)
    assert holder.title == CANNOT_CONFIRM_HOLDER_TITLE
    assert holder.status == "archived"
    # Invisible to every trusted read path: composed resumes and the resolver
    # snapshot must never see the holder or its retired points.
    composed = compose_resume_data(db_session)
    assert "Kafka" not in json.dumps(composed.get("extra_sections") or [])
    snapshot = kb_resolver.load_kb_snapshot(db_session)
    assert all(
        e["title"] != CANNOT_CONFIRM_HOLDER_TITLE for e in snapshot["entities"]
    )


def test_cannot_confirm_binds_to_matched_entity_when_placement_names_one(
    db_session, tmp_path, monkeypatch
):
    tailoring = _open_session(db_session, tmp_path, monkeypatch)
    entity = KBEntity(kind="project", title="Churn Model", status="completed")
    db_session.add(entity)
    db_session.commit()

    _save_cannot_confirm(
        tailoring,
        db_session,
        payload={
            "placement_target": {"section": "projects", "index_or_category": 1}
        },
    )

    points = _cc_points(db_session)
    assert len(points) == 1
    assert points[0].entity_id == entity.id
    assert points[0].state == "retired"


def test_cannot_confirm_is_idempotent_across_saves(db_session, tmp_path, monkeypatch):
    tailoring = _open_session(db_session, tmp_path, monkeypatch)

    _save_cannot_confirm(tailoring, db_session)
    _save_cannot_confirm(tailoring, db_session)  # autosave re-sends the list
    tailoring_session.save_resolutions(
        tailoring.id,
        [{"gap_id": "skill:kafka", "action": "cannot_confirm", "payload": {}}],
        session=db_session,
        replace=True,
    )

    assert len(_cc_points(db_session)) == 1


def test_cannot_confirm_accepted_over_http_where_user_input_is_allowed(
    db_session, tmp_path, monkeypatch
):
    """The API enum accepts the action, and legality piggybacks on user_input
    (frozen pre-Phase-C sessions never list cannot_confirm in gap actions)."""
    gaps = [
        {
            "gap_id": "skill:kafka",
            "kind": "skill",
            "jd_skill": "Kafka",
            "diagnostic": {"fix_hint": "absent"},
            # Deliberately NO cannot_confirm: a frozen pre-Phase-C gap.
            "actions": ["add_keyword", "user_input", "skip"],
        },
        {
            "gap_id": "gate:0",
            "kind": "gate",
            "detail": "Experience gate",
            "diagnostic": {},
            "actions": ["skip"],
        },
    ]
    tailoring = _open_session(db_session, tmp_path, monkeypatch, gaps=gaps)

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    try:
        client = TestClient(app)
        accepted = client.patch(
            f"/api/tailoring-sessions/{tailoring.id}",
            json={
                "resolutions": [
                    {"gap_id": "skill:kafka", "action": "cannot_confirm", "payload": {}}
                ]
            },
        )
        # A skip-only gap never asked a question — cannot_confirm is illegal there.
        rejected = client.patch(
            f"/api/tailoring-sessions/{tailoring.id}",
            json={
                "resolutions": [
                    {"gap_id": "gate:0", "action": "cannot_confirm", "payload": {}}
                ]
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert accepted.status_code == 200
    assert rejected.status_code == 400
    assert len(_cc_points(db_session)) == 1


# --- document behavior: like skip -------------------------------------------


def test_cannot_confirm_behaves_like_skip_for_the_document(
    db_session, tmp_path, monkeypatch
):
    tailoring = _open_session(db_session, tmp_path, monkeypatch)
    _save_cannot_confirm(tailoring, db_session)

    # Alone, it gives the tailor nothing to do — exactly like skip.
    with pytest.raises(ValueError, match="No actionable resolutions"):
        tailoring_session.tailor(tailoring.id, session=db_session)

    # In a bundle it lands on the do-not-touch list, never the LLM mandate.
    db_session.refresh(tailoring)
    tailoring.resolutions_json = tailoring.resolutions_json + [
        {
            "gap_id": "skill:mlflow",
            "action": "user_input",
            "payload": {"text": "Tracked runs in MLflow for two years."},
        }
    ]
    actionable, skipped, _ = tailoring_session._resolution_bundle(tailoring, [])
    assert [item["gap_id"] for item in actionable] == ["skill:mlflow"]
    assert "Kafka" in skipped


# --- suppression: never re-asked --------------------------------------------


def test_future_session_arrives_preresolved_cannot_confirm(
    db_session, tmp_path, monkeypatch
):
    """A stored user_cannot_confirm point matching a gap's skill pre-resolves
    that gap as cannot_confirm in every future session (session-independent,
    matched by normalized skill text)."""
    holder = KBEntity(kind="extra", title=CANNOT_CONFIRM_HOLDER_TITLE, status="archived")
    db_session.add(holder)
    db_session.flush()
    db_session.add(
        KBPoint(
            entity_id=holder.id,
            # Snowflake is required by SAMPLE_JD and evidenced NOWHERE on
            # SAMPLE_RESUME (Salesforce would be auto-resolved from the
            # disabled HiddenCo entry — evidence beats suppression).
            text="Snowflake",
            state="retired",
            origin="gap_elicitation",
            provenance="user_cannot_confirm",
        )
    )
    db_session.commit()
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    created = tailoring_session.create_session(
        job.id, slug, enrich=False, session=db_session
    )

    by_gap = {r["gap_id"]: r for r in created.resolutions_json}
    resolution = by_gap.get("skill:snowflake")
    assert resolution is not None
    assert resolution["action"] == "cannot_confirm"
    assert resolution["payload"]["provenance"]["source"] == "cannot_confirm_auto"


def test_suppression_never_overrides_real_evidence_autos(
    db_session, tmp_path, monkeypatch
):
    """A cannot_confirm point for a skill the resolver ALSO auto-resolved from
    real evidence must not clobber the evidence-backed resolution (here: the
    wording_auto for AWS, which SAMPLE fixtures always produce)."""
    holder = KBEntity(kind="extra", title=CANNOT_CONFIRM_HOLDER_TITLE, status="archived")
    db_session.add(holder)
    db_session.flush()
    db_session.add(
        KBPoint(
            entity_id=holder.id,
            text="AWS",
            state="retired",
            origin="gap_elicitation",
            provenance="user_cannot_confirm",
        )
    )
    db_session.commit()
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    created = tailoring_session.create_session(
        job.id, slug, enrich=False, session=db_session
    )

    by_gap = {r["gap_id"]: r for r in created.resolutions_json}
    aws = by_gap.get("skill:aws")
    assert aws is not None
    assert aws["action"] == "add_keyword"  # the wording_auto survived


# --- the invariant: user_cannot_confirm never upgrades -----------------------


def test_nothing_upgrades_user_cannot_confirm(db_session, tmp_path, monkeypatch):
    """Enforcement pin for inv-provenance-no-decay (behavioral half).

    Grep level: no writer in backend/app ever REASSIGNS `.provenance` on an
    existing row — every provenance is stamped once at KBPoint(...) creation,
    so there is no code path that could flip user_cannot_confirm to anything.

    Behavior: re-running elicitation write-back, deterministic consolidation,
    and base-sync over a resume carrying the exact claim text never changes the
    point's provenance, state, or text.
    """
    # -- grep level ----------------------------------------------------------
    app_root = Path(tailoring_session.__file__).resolve().parents[1]
    mutation = re.compile(r"\.provenance\s*=[^=]")
    offenders = [
        str(path)
        for path in app_root.rglob("*.py")
        for line in path.read_text(encoding="utf-8").splitlines()
        if mutation.search(line)
    ]
    assert offenders == [], (
        "a writer reassigns .provenance on an existing row — "
        "user_cannot_confirm must never be upgraded: " + ", ".join(offenders)
    )

    # -- behavioral ----------------------------------------------------------
    claim = "Cut churn 40% with a Kafka-backed feature store"
    entity = KBEntity(kind="project", title="Churn Model", status="completed")
    db_session.add(entity)
    db_session.flush()
    point = KBPoint(
        entity_id=entity.id,
        text=claim,
        state="retired",
        origin="gap_elicitation",
        provenance="user_cannot_confirm",
    )
    db_session.add(point)
    db_session.commit()
    point_id = point.id

    def _assert_untouched():
        refreshed = db_session.get(KBPoint, point_id)
        assert refreshed.provenance == "user_cannot_confirm"
        assert refreshed.state == "retired"
        assert refreshed.text == claim

    # 1. Elicitation write-back of the same claim (tailor's flywheel).
    tailoring = _open_session(db_session, tmp_path, monkeypatch)
    tailoring_session.save_resolutions(
        tailoring.id,
        [
            {
                "gap_id": "skill:kafka",
                "action": "user_input",
                "payload": {
                    "text": claim,
                    "placement_target": {
                        "section": "projects",
                        "index_or_category": 1,  # "Churn Model"
                    },
                },
            }
        ],
        session=db_session,
    )
    monkeypatch.setattr(
        tailoring_session.llm, "call_openai", lambda **kwargs: {"ops": []}
    )
    tailoring_session.tailor(tailoring.id, session=db_session)
    _assert_untouched()

    # 2. Deterministic consolidation over a resume carrying the claim verbatim.
    resume = json.loads(json.dumps(SAMPLE_RESUME))
    resume["projects"] = [{"name": "Churn Model", "enabled": True, "bullets": [claim]}]
    consolidate_deterministic(db_session, [("cc", resume)], commit=False)
    db_session.flush()
    _assert_untouched()

    # 3. Base-sync over a base carrying the claim (see the companion test for
    # what base-sync IS allowed to do: a NEW separate draft).
    slug = "cc_nodecay_base"
    from app.models.base_resume import BaseResume

    (tmp_path / f"{slug}.json").write_text(json.dumps(resume))
    db_session.add(BaseResume(slug=slug, data_json=resume))
    db_session.commit()
    kb_base_sync.apply(db_session, slug)
    _assert_untouched()


def test_base_sync_drafts_new_point_and_leaves_cannot_confirm_untouched(
    db_session, tmp_path, monkeypatch
):
    """Deliberate interaction: the user writes the SAME claim on a base resume
    and syncs — new first-party evidence beats an old "don't know", so a NEW
    user_authored draft is created (the draft queue is where the user
    reconciles) and the original cannot_confirm point is untouched."""
    from app.models.base_resume import BaseResume

    claim = "Cut churn 40% with a Kafka-backed feature store"
    entity = KBEntity(kind="project", title="Churn Model", status="completed")
    db_session.add(entity)
    db_session.flush()
    cc_point = KBPoint(
        entity_id=entity.id,
        text=claim,
        state="retired",
        origin="gap_elicitation",
        provenance="user_cannot_confirm",
    )
    db_session.add(cc_point)
    db_session.commit()

    resume = json.loads(json.dumps(SAMPLE_RESUME))
    resume["projects"] = [{"name": "Churn Model", "enabled": True, "bullets": [claim]}]
    slug = "cc_sync_base"
    monkeypatch.setattr(settings, "base_resumes_dir", tmp_path)
    (tmp_path / f"{slug}.json").write_text(json.dumps(resume))
    db_session.add(BaseResume(slug=slug, data_json=resume))
    db_session.commit()

    result = kb_base_sync.apply(db_session, slug)

    # Other SAMPLE_RESUME sections sync too; assert on the Churn Model entity.
    assert result["created"] >= 1
    points = db_session.scalars(
        select(KBPoint).where(KBPoint.entity_id == entity.id)
    ).all()
    drafts = [p for p in points if p.state == "draft"]
    assert len(drafts) == 1
    assert drafts[0].provenance == "user_authored"
    assert drafts[0].origin == "base_sync"
    assert drafts[0].id != cc_point.id
    refreshed = db_session.get(KBPoint, cc_point.id)
    assert refreshed.provenance == "user_cannot_confirm"
    assert refreshed.state == "retired"
