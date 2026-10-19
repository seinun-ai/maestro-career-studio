
import pytest

from app.models.career_kb import (
    KBDocument,
    KBEntity,
    KBPoint,
    KBPointKeptPair,
    KBPortLog,
    KBProfile,
    kept_pair_key,
)


def test_kb_models_round_trip(db_session):
    entity = KBEntity(kind="project", title="DocCompare", org="Fictional Data Studio", status="ongoing",
                      detail_json={"tech": "FastAPI, pgvector"}, notes="RAG gap analysis")
    db_session.add(entity)
    db_session.flush()

    doc = KBDocument(entity_id=entity.id, filename="report.pdf", mime="application/pdf",
                     size_bytes=10, file_path="/tmp/x.pdf", text_content="hello",
                     ingest_status="extracted")
    point = KBPoint(entity_id=entity.id, text="Built RAG pipeline", state="approved",
                    origin="manual", tags_json=[])
    db_session.add_all([doc, point])
    db_session.flush()

    log = KBPortLog(entity_id=entity.id, point_id=point.id, resume_kind="base",
                    resume_key="data_scientist", section="projects",
                    ported_text="Built RAG pipeline")
    profile = KBProfile(id=1, contact_json={"name": "A", "email": "a@x.com"},
                        summary="", skills_json=[], notes="")
    db_session.add_all([log, profile])
    db_session.commit()

    assert db_session.get(KBEntity, entity.id).points[0].text == "Built RAG pipeline"
    assert db_session.get(KBPoint, point.id).source_document_id is None
    assert db_session.get(KBProfile, 1) is not None


def test_kb_cascade_delete_entity(db_session):
    entity = KBEntity(kind="project", title="X")
    db_session.add(entity)
    db_session.flush()
    db_session.add(KBPoint(entity_id=entity.id, text="p", state="draft", origin="ingested"))
    db_session.commit()
    db_session.delete(entity)
    db_session.commit()
    assert db_session.query(KBPoint).count() == 0


def _two_points(db_session, state_a="approved", state_b="approved"):
    entity = KBEntity(kind="project", title="Orbit")
    db_session.add(entity)
    db_session.flush()
    a = KBPoint(entity_id=entity.id, text="keeper wording", state=state_a, origin="manual")
    db_session.add(a)
    db_session.flush()
    b = KBPoint(entity_id=entity.id, text="other wording", state=state_b, origin="base_sync")
    db_session.add(b)
    db_session.flush()
    return entity, a, b


def test_merged_into_round_trips_and_nulls_when_the_keeper_goes(db_session):
    _entity, keeper, loser = _two_points(db_session)
    loser.state = "retired"
    loser.merged_into_point_id = keeper.id
    db_session.commit()
    assert db_session.get(KBPoint, loser.id).merged_into.text == "keeper wording"

    db_session.delete(keeper)
    db_session.commit()
    db_session.expire_all()
    survivor = db_session.get(KBPoint, loser.id)
    assert survivor is not None
    assert survivor.merged_into_point_id is None
    assert survivor.merged_into is None


def test_kept_pair_key_is_canonical_and_rejects_a_self_pair(db_session):
    _entity, a, b = _two_points(db_session)
    assert kept_pair_key(a.id, b.id) == kept_pair_key(b.id, a.id)
    assert kept_pair_key(a.id, b.id)[0] < kept_pair_key(a.id, b.id)[1]
    with pytest.raises(ValueError):
        kept_pair_key(a.id, a.id)


def test_kept_pairs_cascade_with_either_point(db_session):
    _entity, a, b = _two_points(db_session)
    lo, hi = kept_pair_key(a.id, b.id)
    db_session.add(KBPointKeptPair(point_a_id=lo, point_b_id=hi))
    db_session.commit()
    assert db_session.query(KBPointKeptPair).count() == 1
    db_session.delete(a)
    db_session.commit()
    assert db_session.query(KBPointKeptPair).count() == 0
