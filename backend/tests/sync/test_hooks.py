"""Local revision tracking works on every session, with ownership guards disabled."""

import uuid

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services.sync import hooks, status, wire


@pytest.fixture(autouse=True)
def sync_off(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path / "settings")
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    monkeypatch.setattr(settings, "sync_remote_url", "")


def _state(session, name):
    return session.scalar(select(models.SyncState.value).where(models.SyncState.name == name))


def _job(session, **kwargs):
    row = models.Job(raw_text="A saved role", raw_text_hash=uuid.uuid4().hex, **kwargs)
    session.add(row)
    session.flush()
    return row


def _application(session, job):
    row = models.Application(id=uuid.uuid4(), job_id=job.id, base_resume="base")
    session.add(row)
    session.flush()
    return row


def test_pending_job_gets_id_and_clock_stamp(db_session):
    job = models.Job(raw_text="A new role", raw_text_hash="new-role")
    assert job.id is None and job.sync_rev is None
    db_session.add(job)
    db_session.flush()
    assert isinstance(job.id, uuid.UUID)
    assert job.sync_rev == _state(db_session, "clock") == 1


def test_pending_job_and_children_share_one_clock_stamp_before_insert(db_session):
    from app.services.sync import hooks, registry

    job = models.Job(id=uuid.uuid4(), raw_text="A role", raw_text_hash="with-children")
    application = models.Application(id=uuid.uuid4(), job_id=job.id, base_resume="base")
    qa = models.QAEntry(application_id=application.id, kind="answer")
    db_session.add_all([job, application, qa])
    # These models have FK columns without an ORM parent relationship ordering INSERTs.
    hooks._before_flush(db_session, None, None)
    assert job.sync_rev == _state(db_session, "clock") == 1
    assert registry.job_id_of(db_session, qa) == job.id
    assert job in db_session.new and application in db_session.new and qa in db_session.new


@pytest.mark.parametrize("child", ["skill", "application", "proposal", "consent", "qa", "filled"])
def test_child_inserts_raise_job_revision(db_session, child):
    job = _job(db_session)
    application = _application(db_session, job)
    proposal = models.ApplicationProposal(job_id=job.id)
    db_session.add(proposal)
    db_session.flush()
    rows = {
        "skill": models.JobSkill(job_id=job.id, skill_name="Python", skill_category="tool",
                                 requirement_level="required"),
        "application": models.Application(job_id=job.id, base_resume="another-base"),
        "proposal": models.ApplicationProposal(job_id=job.id),
        "consent": models.ConsentEvent(proposal_id=proposal.id, action="approved", channel="web"),
        "qa": models.QAEntry(application_id=application.id, kind="answer"),
        "filled": models.FilledAnswer(job_id=job.id, channel="agent", fields=[]),
    }
    before = job.sync_rev
    db_session.add(rows[child])
    db_session.flush()
    assert job.sync_rev == before + 1 == _state(db_session, "clock")


def test_proposal_transition_raises_job_revision(db_session):
    job = _job(db_session)
    proposal = models.ApplicationProposal(job_id=job.id)
    db_session.add(proposal)
    db_session.flush()
    before = job.sync_rev
    proposal.status = "accepted"
    db_session.flush()
    assert job.sync_rev > before


def test_base_resume_edit_and_autofill_setting_only_raise_profile_revision(db_session):
    job = _job(db_session)
    before_job = job.sync_rev
    base = models.BaseResume(slug="base", data_json={})
    db_session.add(base)
    db_session.flush()
    first = _state(db_session, "profile_rev")
    assert first > before_job
    base.display_name = "Updated base"
    db_session.flush()
    assert _state(db_session, "profile_rev") > first
    second = _state(db_session, "profile_rev")
    db_session.add(models.Setting(key="autofill_profile", value="{}"))
    db_session.flush()
    assert _state(db_session, "profile_rev") > second
    assert job.sync_rev == before_job


@pytest.mark.parametrize("key", ["sync.machine_id", "llm.capabilities.fast", "kb.seeded"])
def test_local_settings_raise_no_revision(db_session, key):
    job = _job(db_session)
    before = _state(db_session, "clock")
    db_session.add(models.Setting(key=key, value="local"))
    db_session.flush()
    assert _state(db_session, "clock") == before
    assert _state(db_session, "profile_rev") is None
    assert job.sync_rev == before


def test_delete_job_leaves_tombstone(db_session):
    job = _job(db_session)
    job_id, before = job.id, job.sync_rev
    db_session.delete(job)
    db_session.flush()
    tombstone = db_session.get(models.SyncTombstone, job_id)
    assert tombstone is not None
    assert tombstone.rev == _state(db_session, "clock") > before
    assert db_session.get(models.Job, job_id) is None


def test_clean_and_unchanged_flushes_bump_nothing(db_session):
    job = _job(db_session, title="A role")
    before = job.sync_rev
    db_session.flush()
    job.title = "A role"
    db_session.flush()
    assert job.sync_rev == _state(db_session, "clock") == before


def test_application_move_bumps_both_jobs(db_session):
    first, second = _job(db_session), _job(db_session)
    application = _application(db_session, first)
    before_first, before_second = first.sync_rev, second.sync_rev
    application.job_id = second.id
    db_session.flush()
    assert first.sync_rev > before_first
    assert second.sync_rev > before_second
    assert first.sync_rev == second.sync_rev == _state(db_session, "clock")


def test_move_with_expired_link_bumps_old_job(db_session):
    first, second = _job(db_session), _job(db_session)
    application = _application(db_session, first)
    first_id, second_id = first.id, second.id
    before_first, before_second = first.sync_rev, second.sync_rev
    db_session.commit()
    application.job_id = second_id  # The previous job_id is not loaded after commit.
    db_session.flush()
    assert db_session.get(models.Job, first_id).sync_rev > before_first
    assert db_session.get(models.Job, second_id).sync_rev > before_second


def test_import_restamps_from_local_clock(db_session):
    job = _job(db_session)
    before = _state(db_session, "clock")
    db_session.info["sync_apply"] = True
    job.title, job.sync_rev = "Imported role", 100_000
    db_session.flush()
    assert job.sync_rev == _state(db_session, "clock") == before + 1


def _park_at_zero(session, *job_ids, owner=None):
    """Back at the server default. The flush hook stamps even with sync off, so a Core write is
    what a row the hook never stamped looks like."""
    values = {"sync_rev": 0}
    if owner is not None:
        values["owner_machine"] = owner
    session.execute(update(models.Job).where(models.Job.id.in_(job_ids)).values(**values))
    session.commit()
    session.expire_all()


def _rev_zero_sample(db_session):
    first, second = _job(db_session), _job(db_session)
    replica = _job(db_session)
    kept = _job(db_session)
    kept_rev = kept.sync_rev
    _park_at_zero(db_session, first.id, second.id)
    _park_at_zero(db_session, replica.id, owner="f" * 32)
    return first, second, replica, kept, kept_rev


def _revs_of(db_session, *jobs):
    return {db_session.get(models.Job, job.id).sync_rev for job in jobs}


def test_stamp_unsynced_jobs_gives_owned_revision_zero_jobs_distinct_revs(db_session):
    first, second, replica, kept, kept_rev = _rev_zero_sample(db_session)
    assert kept_rev > 0
    clock_before = _state(db_session, "clock")

    stamped = hooks.stamp_unsynced_jobs(db_session)
    db_session.commit()
    db_session.expire_all()

    revs = _revs_of(db_session, first, second)
    assert stamped == 2
    assert revs == {clock_before + 1, clock_before + 2}
    assert min(revs) > kept_rev
    assert db_session.get(models.Job, kept.id).sync_rev == kept_rev
    assert db_session.get(models.Job, replica.id).sync_rev == 0


def test_a_replica_at_revision_zero_is_left_alone_and_a_second_stamp_is_a_noop(db_session):
    first, second, replica, kept, kept_rev = _rev_zero_sample(db_session)
    hooks.stamp_unsynced_jobs(db_session)
    db_session.commit()
    db_session.expire_all()
    revs = _revs_of(db_session, first, second)

    assert db_session.get(models.Job, replica.id).owner_machine == "f" * 32
    assert hooks.stamp_unsynced_jobs(db_session) == 0
    db_session.expire_all()
    assert _revs_of(db_session, first, second) == revs
    assert db_session.get(models.Job, kept.id).sync_rev == kept_rev
    assert db_session.get(models.Job, replica.id).sync_rev == 0


def test_stamping_revision_zero_jobs_does_not_touch_profile_or_requests(db_session):
    _first, _second, *_rest = _rev_zero_sample(db_session)
    profile_before = _state(db_session, "profile_rev")
    clock_before = _state(db_session, "clock")
    requests_before = db_session.scalar(select(models.SyncRequest.id))

    hooks.stamp_unsynced_jobs(db_session)
    db_session.commit()

    assert _state(db_session, "profile_rev") == profile_before
    assert _state(db_session, "clock") == clock_before + 2
    assert db_session.scalar(select(models.SyncRequest.id)) == requests_before


def test_a_revision_zero_job_owned_by_this_machine_is_stamped(db_session):
    job = _job(db_session)
    mine = status.machine_id(db_session)
    db_session.commit()
    _park_at_zero(db_session, job.id, owner=mine)

    assert hooks.stamp_unsynced_jobs(db_session) == 1
    db_session.expire_all()
    assert db_session.get(models.Job, job.id).sync_rev > 0


def test_stamping_shows_the_new_revision_on_a_loaded_job(db_session):
    job = _job(db_session)
    _park_at_zero(db_session, job.id)
    loaded = db_session.get(models.Job, job.id)
    assert loaded.sync_rev == 0

    hooks.stamp_unsynced_jobs(db_session)

    assert loaded.sync_rev > 0


def test_stamping_does_not_move_a_job_already_past_revision_zero(db_session, monkeypatch):
    job = _job(db_session)
    rev = job.sync_rev
    assert rev > 0
    monkeypatch.setattr(hooks, "_zero_owned_ids", lambda session: [job.id])

    hooks.stamp_unsynced_jobs(db_session)
    db_session.commit()
    db_session.expire_all()

    assert db_session.get(models.Job, job.id).sync_rev == rev


def test_sync_off_allows_other_owner_and_handover(db_session):
    job = _job(db_session, owner_machine="other-machine", handover="offered")
    before = job.sync_rev
    job.title = "Edited here"
    db_session.flush()
    assert job.title == "Edited here" and job.sync_rev > before


def test_relationship_child_is_reported_unresolved_without_refusing_flush(db_session):
    job = _job(db_session)
    application = _application(db_session, job)
    qa = models.QAEntry(kind="answer")
    application.qa_entries.append(qa)
    assert qa.application_id is None
    db_session.flush()
    assert qa.application_id == application.id
    assert qa in db_session.info.get("sync_unresolved", [])


def test_missing_application_and_unknown_kind_are_reported_unresolved(db_session):
    rows = [models.ResumeVersion(resume_kind=kind, resume_key=str(uuid.uuid4()),
                                 version_number=1, snapshot={}, source="create")
            for kind in ("application", "unknown")]
    db_session.add_all(rows)
    db_session.flush()
    assert all(row in db_session.info.get("sync_unresolved", []) for row in rows)
    assert _state(db_session, "clock") is None


def test_kb_port_log_insert_default_is_profile(db_session):
    entity = models.KBEntity(kind="experience", title="Experience")
    db_session.add(entity)
    db_session.flush()
    before = _state(db_session, "profile_rev")
    log = models.KBPortLog(entity_id=entity.id, resume_key="base", section="experience")
    assert log.resume_kind is None
    db_session.add(log)
    db_session.flush()
    assert log.resume_kind == "base"
    assert _state(db_session, "profile_rev") > before
    assert log not in db_session.info.get("sync_unresolved", [])


def test_explicit_profile_touch_without_orm_writes_flushes(db_session):
    from app.services.sync import hooks

    hooks.touch_profile(db_session)
    db_session.flush()
    assert _state(db_session, "profile_rev") == _state(db_session, "clock") == 1
    db_session.flush()
    assert _state(db_session, "clock") == 1


def test_explicit_job_touch_without_orm_writes_flushes(db_session):
    from app.services.sync import hooks

    job = _job(db_session)
    before = job.sync_rev
    hooks.touch_job(db_session, job.id)
    db_session.flush()
    assert job.sync_rev == _state(db_session, "clock") > before


def test_rolled_back_touch_does_not_leak_into_next_transaction(db_session):
    from app.services.sync import hooks

    job = _job(db_session)
    db_session.commit()
    hooks.touch_profile(db_session)
    db_session.rollback()
    job.title = "After rollback"
    db_session.flush()
    assert _state(db_session, "profile_rev") is None


def test_all_session_instances_have_hook(db_session):
    db_session.commit()
    with Session(db_session.bind, autoflush=False) as other:
        job = _job(other)
        assert job.sync_rev == _state(other, "clock") > 0
        other.rollback()


def test_pending_parents_are_indexed_once_for_a_flush(db_session, monkeypatch):
    from app.services.sync import registry

    job = _job(db_session)
    application = models.Application(id=uuid.uuid4(), job_id=job.id, base_resume="base")
    db_session.add(application)
    db_session.add_all([models.QAEntry(application_id=application.id, kind="answer")
                        for _ in range(40)])
    builds = []
    original = registry.pending_parents

    def counted(session):
        builds.append(1)
        return original(session)

    monkeypatch.setattr(registry, "pending_parents", counted)
    before = job.sync_rev
    db_session.flush()
    assert job.sync_rev > before
    assert len(builds) == 1


def test_one_clock_update_stamps_all_touched_jobs_and_profile(db_session):
    first, second = _job(db_session), _job(db_session)
    updates = []

    def capture(*args):
        statement = args[2]
        if statement.startswith("UPDATE sync_state"):
            updates.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", capture)
    try:
        first.title, second.title = "First update", "Second update"
        db_session.add(models.Setting(key="autofill_profile", value="{}"))
        db_session.flush()
    finally:
        event.remove(db_session.bind, "before_cursor_execute", capture)
    assert len(updates) == 1
    assert first.sync_rev == second.sync_rev == _state(db_session, "profile_rev")


def test_template_default_core_update_raises_profile_revision(db_session):
    from app.services import template_registry

    row = models.Template(id="sync-ready", source="source", status="ready", is_default=True)
    db_session.add(row)
    db_session.flush()
    before = _state(db_session, "profile_rev")
    template_registry.set_default(db_session, row.id)
    assert _state(db_session, "profile_rev") > before
    assert row.is_default is True


def test_merge_application_port_log_bumps_job_revision(db_session):
    from app.services import career_kb

    job = _job(db_session)
    application = _application(db_session, job)
    source = models.KBEntity(id=uuid.uuid4(), kind="experience", title="Source")
    target = models.KBEntity(id=uuid.uuid4(), kind="experience", title="Target")
    db_session.add_all([source, target])
    db_session.flush()
    log = models.KBPortLog(entity_id=source.id, resume_kind="application",
                           resume_key=str(application.id), section="experience")
    db_session.add(log)
    db_session.commit()
    before = job.sync_rev
    log_id, target_id = log.id, target.id
    career_kb.merge_entities(db_session, source.id, target_id)
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(models.KBPortLog, log_id).entity_id == target_id
    assert job.sync_rev > before


def test_explicit_profile_touch_tracks_core_only_update(db_session):
    from app.services.sync import hooks

    row = models.Setting(key="autofill_profile", value="{}")
    db_session.add(row)
    db_session.commit()
    before = _state(db_session, "profile_rev")
    hooks.touch_profile(db_session)
    db_session.execute(update(models.Setting).where(models.Setting.key == row.key)
                       .values(value="updated").execution_options(synchronize_session=False))
    db_session.commit()
    assert _state(db_session, "profile_rev") > before


def test_standing_aside_sets_the_flag_and_removes_it_after(db_session):
    with hooks.standing_aside(db_session):
        assert db_session.info["sync_apply"] is True
    assert "sync_apply" not in db_session.info


def test_standing_aside_puts_back_the_earlier_value_when_nested(db_session):
    db_session.info["sync_apply"] = "outer"
    with hooks.standing_aside(db_session):
        with hooks.standing_aside(db_session):
            assert db_session.info["sync_apply"] is True
        assert db_session.info["sync_apply"] is True
    assert db_session.info["sync_apply"] == "outer"


def test_standing_aside_restores_the_flag_when_the_block_raises(db_session):
    with pytest.raises(RuntimeError), hooks.standing_aside(db_session):
        raise RuntimeError
    assert "sync_apply" not in db_session.info


@pytest.mark.parametrize("raw, expected", [(None, None), ("nope", None), (5, None),
                                            ("0" * 31 + "1", uuid.UUID(int=1)),
                                            (uuid.UUID(int=2), uuid.UUID(int=2))])
def test_a_wire_id_is_a_uuid_or_none(raw, expected):
    assert wire.uuid_of(raw) == expected


@pytest.mark.parametrize("bundle", [None, [], {}, {"job_id": None}, {"job_id": "x"}, {"job_id": 7}])
def test_a_bundle_without_a_readable_job_id_names_no_job(bundle):
    assert wire.bundle_job_id(bundle) is None
    assert wire.bundle_job_id({"job_id": uuid.UUID(int=3).hex}) == uuid.UUID(int=3)


def test_a_request_is_shown_with_hex_ids(db_session):
    from datetime import UTC, datetime
    row = models.SyncRequest(id=uuid.UUID(int=4), kind="take_over", job_id=None,
                             payload_json={"a": 1}, created_at=datetime(2026, 10, 6, tzinfo=UTC))
    assert wire.shown(row) == {"id": uuid.UUID(int=4).hex, "kind": "take_over", "job_id": None,
                               "payload": {"a": 1}, "created_at": "2026-10-06T00:00:00+00:00"}
