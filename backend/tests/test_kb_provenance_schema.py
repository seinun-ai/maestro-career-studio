from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint, KBPortLog


def test_provenance_direction_and_sync_columns_exist(db_session):
    ent = KBEntity(kind="experience", title="Acme")
    db_session.add(ent)
    db_session.flush()
    point = KBPoint(
        entity_id=ent.id,
        text="Did a thing",
        state="draft",
        origin="base_sync",
        provenance="user_authored",
    )
    log = KBPortLog(
        entity_id=ent.id,
        point_id=None,
        resume_kind="base",
        resume_key="hybrid",
        section="experience",
        ported_text="t",
        direction="from_source",
    )
    db_session.add_all([point, log])
    db_session.flush()
    assert point.provenance == "user_authored"
    assert log.direction == "from_source"
    assert BaseResume.last_kb_synced_at is not None  # column exists
