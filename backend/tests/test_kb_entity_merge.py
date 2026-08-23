"""Manual entity merge: POST /api/kb/entities/{id}/merge.

The CURE for wording-variant duplicates ("Data Analyst" vs "Data Analyst,
British Airways Account"). Web-only by design — no MCP tool.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.career_kb import KBDocument, KBEntity, KBPoint, KBPortLog


@pytest.fixture
def client(db_session):
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _entity(db_session, **kwargs) -> KBEntity:
    entity = KBEntity(**{"kind": "experience", "title": "Analyst", **kwargs})
    db_session.add(entity)
    db_session.commit()
    return entity


def _point(db_session, entity_id, text: str, state: str = "approved") -> KBPoint:
    point = KBPoint(entity_id=entity_id, text=text, state=state, origin="manual")
    db_session.add(point)
    db_session.commit()
    return point


def test_merge_moves_points_documents_and_portlogs(client, db_session):
    source = _entity(db_session, title="Data Analyst, British Airways Account")
    target = _entity(db_session, title="Data Analyst")
    point = _point(db_session, source.id, "Built the pipeline")
    document = KBDocument(entity_id=source.id, filename="jd.pdf")
    db_session.add(document)
    db_session.flush()
    log = KBPortLog(
        entity_id=source.id,
        point_id=point.id,
        resume_key="base-a",
        section="experience",
        ported_text="Built the pipeline",
    )
    db_session.add(log)
    db_session.commit()
    point_id, document_id, log_id = point.id, document.id, log.id
    # Load the source's cascading collections the way a detail read would: with
    # them in the identity map, `delete(source)` would delete-orphan the very
    # rows the merge just re-pointed unless the merge defuses the cascade.
    assert len(source.points) == 1 and len(source.documents) == 1

    response = client.post(f"/api/kb/entities/{source.id}/merge", json={"target_id": str(target.id)})
    assert response.status_code == 200, response.text

    db_session.expire_all()
    assert db_session.get(KBPoint, point_id).entity_id == target.id
    assert db_session.get(KBDocument, document_id).entity_id == target.id
    assert db_session.get(KBPortLog, log_id).entity_id == target.id


def test_merge_absorbs_only_empty_target_fields(client, db_session):
    source = _entity(
        db_session,
        title="Data Analyst, British Airways Account",
        org="Fictional Airline Group",
        start_date="2021-01",
        end_date="2023-06",
        notes="Contract via the airline account",
        detail_json={"tech": "python", "team": "analytics"},
    )
    target = _entity(
        db_session,
        title="Data Analyst",
        org="",  # blank -> absorbs
        start_date="2020-11",  # non-empty -> untouched
        end_date=None,  # blank -> absorbs (target is 'completed', not 'ongoing')
        notes="   ",  # whitespace-only is blank -> absorbs
        detail_json={"tech": "sql"},  # existing key -> untouched
    )

    body = client.post(
        f"/api/kb/entities/{source.id}/merge", json={"target_id": str(target.id)}
    ).json()

    assert body["org"] == "Fictional Airline Group"
    assert body["notes"] == "Contract via the airline account"
    assert body["start_date"] == "2020-11"
    assert body["end_date"] == "2023-06"
    assert body["detail"] == {"tech": "sql", "team": "analytics"}


def test_merge_keeps_ongoing_target_end_date_blank(client, db_session):
    """A blank end_date on an ongoing entity IS the "present" value — see
    _end_sort_key (blank sorts newest) and _fmt_dates (renders "start–present").
    Absorbing a dated source end_date there would silently end a current role."""
    source = _entity(
        db_session,
        title="Data Analyst, BA Account",
        org="Fictional Airline Group",
        start_date="2021-01",
        end_date="2023-06",
        status="completed",
    )
    target = _entity(
        db_session, title="Data Analyst", start_date="2021-01", end_date=None, status="ongoing"
    )

    body = client.post(
        f"/api/kb/entities/{source.id}/merge", json={"target_id": str(target.id)}
    ).json()

    assert body["end_date"] is None
    assert body["status"] == "ongoing"
    assert body["org"] == "Fictional Airline Group"  # other blanks still absorb


def test_merge_extra_requires_same_section_key(client, db_session):
    """`extra` entities are section-scoped; folding one section into another
    would relabel its points, so section_key must match (case-folded)."""
    a = _entity(
        db_session, kind="extra", title="Talks", detail_json={"section_key": "speaking"}
    )
    b = _entity(
        db_session, kind="extra", title="Awards", detail_json={"section_key": "awards"}
    )

    mismatch = client.post(f"/api/kb/entities/{a.id}/merge", json={"target_id": str(b.id)})
    assert mismatch.status_code == 400
    assert "speaking" in mismatch.json()["detail"]
    assert "awards" in mismatch.json()["detail"]

    same_key_other_case = _entity(
        db_session, kind="extra", title="More talks", detail_json={"section_key": "SPEAKING"}
    )
    ok = client.post(
        f"/api/kb/entities/{same_key_other_case.id}/merge", json={"target_id": str(a.id)}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["section_key"] == "speaking"  # target keeps its own casing


def test_merge_lost_race_is_409(client, db_session, monkeypatch):
    """Pins the exception→409 mapping only — merge_entities is monkeypatched
    to raise; no real concurrency here. The genuine two-session race was
    verified out-of-suite in review (loser 409, data consistent)."""
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy.orm.exc import ObjectDeletedError

    from app.routers import career_kb as router

    source = _entity(db_session, title="Data Analyst, BA Account")
    target = _entity(db_session, title="Data Analyst")
    state = sa_inspect(source)

    def _raise(*args, **kwargs):
        raise ObjectDeletedError(state)

    monkeypatch.setattr(router.svc, "merge_entities", _raise)

    response = client.post(
        f"/api/kb/entities/{source.id}/merge", json={"target_id": str(target.id)}
    )

    assert response.status_code == 409
    assert "refresh and retry" in response.json()["detail"].lower()


def test_merge_does_not_absorb_origin_or_nonblank_notes(client, db_session):
    """origin/origin_detail describe how the SURVIVING row was created and are a
    rendered pair in entity_timeline; created_at is target-wins."""
    source = _entity(
        db_session,
        title="Data Analyst, BA Account",
        notes="source note",
        origin="mcp",
        origin_detail="Claude Desktop",
    )
    target = _entity(
        db_session, title="Data Analyst", notes="target note", origin=None, origin_detail=None
    )
    target_created_at = target.created_at

    client.post(f"/api/kb/entities/{source.id}/merge", json={"target_id": str(target.id)})

    db_session.expire_all()
    merged = db_session.get(KBEntity, target.id)
    assert merged.notes == "target note"  # non-blank -> untouched
    assert merged.origin is None and merged.origin_detail is None
    assert merged.created_at == target_created_at


def test_merge_deletes_source_and_keeps_target_title(client, db_session):
    source = _entity(db_session, title="Data Analyst, British Airways Account")
    target = _entity(db_session, title="Data Analyst")
    source_id, target_id = source.id, target.id

    body = client.post(
        f"/api/kb/entities/{source_id}/merge", json={"target_id": str(target_id)}
    ).json()

    assert body["id"] == str(target_id)
    assert body["title"] == "Data Analyst"
    db_session.expire_all()
    assert db_session.get(KBEntity, source_id) is None
    assert db_session.get(KBEntity, target_id) is not None


def test_merge_same_id_is_400(client, db_session):
    entity = _entity(db_session, title="Data Analyst")

    response = client.post(
        f"/api/kb/entities/{entity.id}/merge", json={"target_id": str(entity.id)}
    )

    assert response.status_code == 400
    assert "itself" in response.json()["detail"]


def test_merge_cross_kind_is_400(client, db_session):
    source = _entity(db_session, kind="experience", title="Data Analyst")
    target = _entity(db_session, kind="certification", title="AWS AI Practitioner")

    response = client.post(
        f"/api/kb/entities/{source.id}/merge", json={"target_id": str(target.id)}
    )

    assert response.status_code == 400
    assert "experience" in response.json()["detail"]
    assert "certification" in response.json()["detail"]
    db_session.expire_all()
    assert db_session.get(KBEntity, source.id) is not None


def test_merge_unknown_ids_are_404(client, db_session):
    live = _entity(db_session, title="Data Analyst")
    missing = str(uuid.uuid4())

    unknown_source = client.post(f"/api/kb/entities/{missing}/merge", json={"target_id": str(live.id)})
    assert unknown_source.status_code == 404
    assert "Source" in unknown_source.json()["detail"]

    unknown_target = client.post(f"/api/kb/entities/{live.id}/merge", json={"target_id": missing})
    assert unknown_target.status_code == 404
    assert "Target" in unknown_target.json()["detail"]


def test_merge_into_archived_target_is_400_but_archived_source_is_allowed(client, db_session):
    archived_target = _entity(db_session, title="Data Analyst", status="archived")
    source = _entity(db_session, title="Data Analyst, BA Account")

    blocked = client.post(
        f"/api/kb/entities/{source.id}/merge", json={"target_id": str(archived_target.id)}
    )
    assert blocked.status_code == 400
    assert "unarchive" in blocked.json()["detail"].lower()

    # The reverse is how a duplicate holder is retired: archived source -> live target.
    allowed = client.post(
        f"/api/kb/entities/{archived_target.id}/merge", json={"target_id": str(source.id)}
    )
    assert allowed.status_code == 200, allowed.text
    db_session.expire_all()
    assert db_session.get(KBEntity, archived_target.id) is None


def test_merge_does_not_collapse_duplicate_points(client, db_session):
    source = _entity(db_session, title="Data Analyst, BA Account")
    target = _entity(db_session, title="Data Analyst")
    a = _point(db_session, source.id, "Same exact bullet")
    b = _point(db_session, target.id, "Same exact bullet")

    body = client.post(
        f"/api/kb/entities/{source.id}/merge", json={"target_id": str(target.id)}
    ).json()

    assert len(body["points"]) == 2
    assert {p["id"] for p in body["points"]} == {str(a.id), str(b.id)}
    assert [p["text"] for p in body["points"]] == ["Same exact bullet"] * 2


def test_merge_returns_target_detail(client, db_session):
    source = _entity(db_session, title="Data Analyst, BA Account")
    target = _entity(db_session, title="Data Analyst")
    _point(db_session, source.id, "Moved bullet")
    db_session.add(KBDocument(entity_id=source.id, filename="jd.pdf"))
    db_session.commit()

    merged = client.post(
        f"/api/kb/entities/{source.id}/merge", json={"target_id": str(target.id)}
    ).json()
    fetched = client.get(f"/api/kb/entities/{target.id}").json()

    assert merged.keys() == fetched.keys()
    assert merged["points"] == fetched["points"]
    assert merged["documents"] == fetched["documents"]
    assert merged["point_count"] == 1 and merged["document_count"] == 1
