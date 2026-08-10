
from app.models.career_kb import KBDocument, KBEntity, KBPoint, KBPortLog, KBProfile


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
