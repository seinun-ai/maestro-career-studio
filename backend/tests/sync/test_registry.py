"""The registry covers every table and resolves rows without writing anything."""

import uuid

import pytest
from sqlalchemy import event

from app import models
from app.db import Base


BY_KIND_MODELS = (
    models.ResumeVersion,
    models.ResumeLintReport,
    models.HealthAskAnswer,
    models.HealthGateWaiver,
    models.KBPortLog,
)
DIRECT_JOB_MODELS = (
    models.JobSkill,
    models.Application,
    models.ApplicationProposal,
    models.AtsScore,
    models.TailoringSession,
    models.FilledAnswer,
)
PROFILE_MODELS = (
    models.BaseResume,
    models.Template,
    models.Referral,
    models.KBEntity,
    models.KBPoint,
    models.KBDocument,
    models.KBProfile,
)
LOCAL_MODELS = (
    models.BulletClassification,
    models.BulletRewrite,
    models.BulletDispute,
    models.ChatSession,
    models.ChatMessage,
    models.ChatAttachment,
    models.AutofillRun,
    models.AutofillFieldObservation,
    models.AutofillMechanismStat,
)
SYNC_MODELS = (models.SyncState, models.SyncTombstone, models.SyncRequest)
INDIRECT_JOB_MODELS = (models.ConsentEvent, models.QAEntry, *BY_KIND_MODELS)


@pytest.fixture
def job_parents(db_session):
    job = models.Job(id=uuid.uuid4(), raw_text="A saved role", raw_text_hash="registry-job")
    db_session.add(job)
    db_session.flush()
    application = models.Application(id=uuid.uuid4(), job_id=job.id, base_resume="base")
    proposal = models.ApplicationProposal(id=uuid.uuid4(), job_id=job.id)
    db_session.add_all([application, proposal])
    db_session.flush()
    return job, application, proposal


def _child_of(model, application, proposal):
    if model is models.ConsentEvent:
        return model(proposal_id=proposal.id)
    if model is models.QAEntry:
        return model(application_id=application.id)
    return model(resume_kind="application", resume_key=str(application.id))


def test_every_table_is_classified():
    from app.services.sync import registry

    assert {table.name for table in Base.metadata.sorted_tables} <= registry.TABLES.keys()
    assert registry.TABLES["alembic_version"] == registry.SYNC
    assert set(registry.TABLES.values()) == {"profile", "job", "run_log", "local", "sync", "by_kind"}


@pytest.mark.parametrize("model", (models.Job, *DIRECT_JOB_MODELS, models.ConsentEvent, models.QAEntry))
def test_job_tables_are_job_class(model):
    from app.services.sync import registry

    assert registry.TABLES[model.__tablename__] == registry.JOB


@pytest.mark.parametrize("model", (*PROFILE_MODELS, models.Setting))
def test_profile_tables_are_profile_class(model):
    from app.services.sync import registry

    assert registry.TABLES[model.__tablename__] == registry.PROFILE


@pytest.mark.parametrize("model", BY_KIND_MODELS)
def test_resume_tables_split_by_kind(model):
    from app.services.sync import registry

    assert registry.TABLES[model.__tablename__] == "by_kind"


@pytest.mark.parametrize("model", LOCAL_MODELS)
def test_local_tables_stay_local(model):
    from app.services.sync import registry

    assert registry.TABLES[model.__tablename__] == registry.LOCAL


@pytest.mark.parametrize("model", SYNC_MODELS)
def test_sync_tables_are_sync_class(model):
    from app.services.sync import registry

    assert registry.TABLES[model.__tablename__] == registry.SYNC


def test_agent_runs_are_add_only_run_log():
    from app.services.sync import registry

    assert registry.TABLES["agent_runs"] == registry.RUN_LOG


def test_job_id_of_job(db_session):
    from app.services.sync import registry

    job_id = uuid.uuid4()
    assert registry.job_id_of(db_session, models.Job(id=job_id)) == job_id


@pytest.mark.parametrize("model", DIRECT_JOB_MODELS)
def test_job_id_of_direct_job_rows(db_session, model):
    from app.services.sync import registry

    job_id = uuid.uuid4()
    assert registry.job_id_of(db_session, model(job_id=job_id)) == job_id


@pytest.mark.parametrize("model", INDIRECT_JOB_MODELS)
def test_job_id_of_indirect_job_rows(db_session, job_parents, model):
    from app.services.sync import registry

    job, application, proposal = job_parents
    assert registry.job_id_of(db_session, _child_of(model, application, proposal)) == job.id


@pytest.mark.parametrize("model", BY_KIND_MODELS)
def test_base_resume_rows_belong_to_profile(db_session, model):
    from app.services.sync import registry

    row = model(resume_kind="base", resume_key="base-slug")
    assert registry.is_profile_row(row) is True
    assert registry.job_id_of(db_session, row) is None


@pytest.mark.parametrize("model", BY_KIND_MODELS)
def test_application_resume_rows_are_not_profile(model):
    from app.services.sync import registry

    row = model(resume_kind="application", resume_key=str(uuid.uuid4()))
    assert registry.is_profile_row(row) is False


@pytest.mark.parametrize("model", PROFILE_MODELS)
def test_profile_rows_have_no_job(db_session, model):
    from app.services.sync import registry

    row = model()
    assert registry.is_profile_row(row) is True
    assert registry.job_id_of(db_session, row) is None


@pytest.mark.parametrize("model", (models.Job, *DIRECT_JOB_MODELS, models.ConsentEvent, models.QAEntry))
def test_job_rows_are_not_profile(model):
    from app.services.sync import registry

    assert registry.is_profile_row(model()) is False


@pytest.mark.parametrize("model", (*LOCAL_MODELS, *SYNC_MODELS, models.AgentRun))
def test_local_sync_and_run_rows_have_no_job(db_session, model):
    from app.services.sync import registry

    row = model()
    if "job_id" in model.__table__.columns:
        row.job_id = uuid.uuid4()
    assert registry.job_id_of(db_session, row) is None
    assert registry.is_profile_row(row) is False


@pytest.mark.parametrize(
    ("key", "is_profile"),
    [
        ("autofill_profile", True),
        ("job_preferences", True),
        ("full_automation", True),
        ("llm.api_key", True),
        ("prompt.chat_system", True),
        ("sync.machine_id", False),
        ("sync.cursor.jobs", False),
        ("llm.capabilities.fast", False),
        ("kb.seeded", False),
        ("kb.seeded.base", False),
        ("llm_library_proposals", False),
        ("llm_library_proposals.extra", False),
        ("sync", True),
        ("llm.capabilities", True),
        ("prompt.sync.machine_id", True),
    ],
)
def test_setting_keys_split_profile_and_local(db_session, key, is_profile):
    from app.services.sync import registry

    row = models.Setting(key=key)
    assert registry.is_profile_row(row) is is_profile
    assert registry.job_id_of(db_session, row) is None


@pytest.mark.parametrize("model", INDIRECT_JOB_MODELS)
def test_pending_parent_resolves_without_flushing(db_session, model):
    from app.services.sync import registry

    job_id = uuid.uuid4()
    application = models.Application(id=uuid.uuid4(), job_id=job_id)
    proposal = models.ApplicationProposal(id=uuid.uuid4(), job_id=job_id)
    db_session.add_all([application, proposal])
    db_session.autoflush = True
    assert registry.job_id_of(db_session, _child_of(model, application, proposal)) == job_id
    assert application in db_session.new
    assert proposal in db_session.new


@pytest.mark.parametrize("model", INDIRECT_JOB_MODELS)
def test_persisted_parent_lookup_never_autoflushes(db_session, job_parents, model):
    from app.services.sync import registry

    job, application, proposal = job_parents
    db_session.expunge(application)
    db_session.expunge(proposal)  # Force a database lookup rather than an identity-map hit.
    pending = models.Application(job_id=job.id)  # Missing base_resume makes a flush fail.
    db_session.add(pending)
    db_session.autoflush = True
    assert registry.job_id_of(db_session, _child_of(model, application, proposal)) == job.id
    assert pending in db_session.new


@pytest.mark.parametrize("model", INDIRECT_JOB_MODELS)
def test_missing_parent_has_no_job(db_session, model):
    from app.services.sync import registry

    application = models.Application(id=uuid.uuid4())
    proposal = models.ApplicationProposal(id=uuid.uuid4())
    assert registry.job_id_of(db_session, _child_of(model, application, proposal)) is None


@pytest.mark.parametrize("model", BY_KIND_MODELS)
@pytest.mark.parametrize("resume_key", ["base-slug", "", None])
def test_invalid_application_resume_reference_has_no_job(db_session, model, resume_key):
    from app.services.sync import registry

    row = model(resume_kind="application", resume_key=resume_key)
    assert registry.job_id_of(db_session, row) is None
    assert registry.is_profile_row(row) is False


@pytest.mark.parametrize("model", BY_KIND_MODELS)
def test_unknown_resume_kind_has_no_owner_class(db_session, model):
    from app.services.sync import registry

    row = model(resume_kind="unknown", resume_key=str(uuid.uuid4()))
    assert registry.job_id_of(db_session, row) is None
    assert registry.is_profile_row(row) is False


@pytest.mark.parametrize("model", INDIRECT_JOB_MODELS)
def test_job_resolution_works_during_before_flush(db_session, job_parents, model):
    from app.services.sync import registry

    job, application, proposal = job_parents
    row = _child_of(model, application, proposal)
    resolved = []

    def resolve_during_flush(session, flush_context, instances):
        resolved.append(registry.job_id_of(session, row))

    event.listen(db_session, "before_flush", resolve_during_flush)
    try:
        db_session.add(models.Setting(key="registry.trigger", value="local test"))
        db_session.flush()
    finally:
        event.remove(db_session, "before_flush", resolve_during_flush)
    assert resolved == [job.id]
