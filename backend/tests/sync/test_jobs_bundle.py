"""One job travels as a bundle: export, apply onto a second database, delete what is gone."""

import copy
import json
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import sessionmaker

from app import models
from app.config import settings
from app.db import Base, make_engine
from app.services.sync import files, jobs_bundle, registry, status
from app.services.sync.hooks import NotOwnedHere

SENTINEL = "SENTINEL-BODY-7731"
MODELS = [
    models.Job, models.JobSkill, models.Application, models.ApplicationProposal,
    models.ConsentEvent, models.AtsScore, models.TailoringSession, models.QAEntry,
    models.FilledAnswer, models.ResumeVersion, models.ResumeLintReport,
    models.HealthAskAnswer, models.HealthGateWaiver, models.KBPortLog,
]
IGNORED = {"sync_rev", "owner_machine", "handover"}
PATHS = {
    models.Application: ("artifact_dir", "pdf_path", "tex_path"),
    models.QAEntry: ("pdf_path",),
}
WHEN = datetime(2026, 10, 1, 12, 30, 5, 123456, tzinfo=UTC)


@pytest.fixture(autouse=True)
def sync_off(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path / "settings")
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    monkeypatch.setattr(settings, "sync_remote_url", "")


@pytest.fixture
def roots(tmp_path, monkeypatch):
    paths = {}
    for side in ("home", "recv"):
        for name in ("applications", "base_resumes", "kb_documents"):
            path = tmp_path / side / name
            path.mkdir(parents=True)
            paths[side, name] = path

    def use(side):
        for name in ("applications", "base_resumes", "kb_documents"):
            monkeypatch.setattr(settings, f"{name}_dir", paths[side, name])

    use("home")
    return SimpleNamespace(home=paths["home", "applications"],
                           recv=paths["recv", "applications"], use=use)


@pytest.fixture
def home(db_session):
    return db_session


@pytest.fixture
def recv(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'recv.sqlite3'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, autoflush=False)() as session:
        yield session
    engine.dispose()


def _write(path, data=b"bytes"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def build_job(db, root, *, tag="a", qa_count=2, referral_id=None, raw_text=None):
    """A job with one of everything, its files on disk under ``root``."""
    ids = SimpleNamespace(job=uuid.uuid4(), app=uuid.uuid4(), app2=uuid.uuid4(),
                          proposal=uuid.uuid4(), score=uuid.uuid4(), qa=[])
    folder = root / f"Co_Role_{tag}"
    _write(folder / "resume.pdf", b"%PDF " + tag.encode())
    _write(folder / "resume.tex", b"tex " + tag.encode())
    _write(folder / "evidence" / "shot.png", b"png " + tag.encode())
    _write(folder / "resume.pages" / "page-1.png", b"regenerated")
    db.add(models.Job(
        id=ids.job, raw_text=raw_text or f"Role {tag} {SENTINEL}", raw_text_hash=f"hash-{tag}-{ids.job}",
        title=f"Title {tag}", salary_min=Decimal("120000.50"), extracted_json={"skills": ["a", "b"]},
        created_at=WHEN,
    ))
    db.flush()
    db.add(models.JobSkill(job_id=ids.job, skill_name="sql", skill_category="tool",
                           requirement_level="required"))
    db.add(models.Application(
        id=ids.app, job_id=ids.job, base_resume="base", status="saved", referral_id=referral_id,
        artifact_dir=str(folder), pdf_path=str(folder / "resume.pdf"),
        tex_path=str(folder / "resume.tex"), customized_json={"summary": "x"}, created_at=WHEN,
        updated_at=WHEN,
    ))
    db.add(models.Application(id=ids.app2, job_id=ids.job, base_resume="other", created_at=WHEN,
                              updated_at=WHEN))
    db.flush()
    _add_children(db, ids, folder, referral_id, qa_count)
    db.commit()
    return ids


def _add_children(db, ids, folder, referral_id, qa_count):
    db.add(models.ApplicationProposal(
        id=ids.proposal, job_id=ids.job, application_id=ids.app, referral_id=referral_id,
        status="accepted", evidence_json=["evidence/shot.png"], created_at=WHEN, updated_at=WHEN))
    db.add(models.AtsScore(
        id=ids.score, job_id=ids.job, target_type="application", target_id=str(ids.app),
        application_id=ids.app, phase="tailored", composite=Decimal("81.5"),
        subscores_json={"a": 1}, skill_table_json=[], gaps_json=None, config_version="c",
        engine_version="e", created_at=WHEN))
    db.add(models.TailoringSession(
        id=uuid.uuid4(), job_id=ids.job, base_resume="base", gaps_json={}, application_id=ids.app,
        base_ats_score_id=ids.score, created_at=WHEN, updated_at=WHEN))
    db.add(models.FilledAnswer(id=uuid.uuid4(), job_id=ids.job, channel="agent",
                               application_id=ids.app, fields=[{"q": "x"}], captured_at=WHEN))
    db.flush()
    db.add(models.ConsentEvent(id=uuid.uuid4(), proposal_id=ids.proposal, action="accept",
                               channel="web", evidence_manifest_json=["a"], created_at=WHEN))
    for index in range(qa_count):
        qid = uuid.uuid4()
        ids.qa.append(qid)
        db.add(models.QAEntry(id=qid, application_id=ids.app, kind="answer", answer=f"a{index}",
                              pdf_path=str(folder / "resume.pdf") if index == 0 else None,
                              created_at=WHEN))
    _add_by_kind(db, ids)


def _add_by_kind(db, ids):
    key = str(ids.app)
    first, second = uuid.uuid4(), uuid.uuid4()
    entity = models.KBEntity(id=uuid.uuid4(), kind="project", title="p")
    db.add(entity)
    db.flush()
    db.add(models.ResumeVersion(id=first, resume_kind="application", resume_key=key,
                                version_number=1, snapshot={"v": 1}, source="create",
                                created_at=WHEN))
    db.flush()
    db.add(models.ResumeVersion(id=second, resume_kind="application", resume_key=key,
                                version_number=2, parent_version_id=first, snapshot={"v": 2},
                                source="tailor", created_at=WHEN))
    db.add(models.ResumeLintReport(id=uuid.uuid4(), resume_kind="application", resume_key=key,
                                   report_json={"ok": True}, created_at=WHEN))
    db.add(models.HealthAskAnswer(id=uuid.uuid4(), resume_kind="application", resume_key=key,
                                  finding_id="f1", content_hash="h", answer="a", created_at=WHEN))
    db.add(models.HealthGateWaiver(id=uuid.uuid4(), resume_kind="application", resume_key=key,
                                   gate_id="S1", reason="r", created_at=WHEN))
    db.add(models.KBPortLog(id=uuid.uuid4(), entity_id=entity.id, resume_kind="application",
                            resume_key=key, section="projects", ported_text="t", ported_at=WHEN))
    ids.entity = entity.id


def copy_profile(src, dst, ids):
    """What a profile pull does before jobs arrive: the entity and referral exist at both ends."""
    for row in src.scalars(select(models.KBEntity)):
        dst.add(models.KBEntity(id=row.id, kind=row.kind, title=row.title))
    dst.commit()


def snapshot(db):
    db.expire_all()
    out = {}
    for model in MODELS:
        rows = {}
        for obj in db.scalars(select(model)):
            row = {p.key: getattr(obj, p.key) for p in inspect(model).column_attrs
                   if p.key not in IGNORED}
            for key in PATHS.get(model, ()):
                row[key] = files.to_portable(row[key])
            pk = tuple(getattr(obj, inspect(model).get_property_by_column(c).key)
                       for c in inspect(model).primary_key)
            rows[pk] = row
        out[model.__tablename__] = rows
    return out


def ship(home, recv, roots, job_id, **kwargs):
    """Export at home, apply at the receiver."""
    roots.use("home")
    bundle = jobs_bundle.export_job(home, job_id)
    bundle = json.loads(json.dumps(bundle))
    roots.use("recv")
    jobs_bundle.apply_job(recv, bundle, sender_machine=kwargs.pop("sender", "home-machine"))
    roots.use("home")
    return bundle


def tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_every_job_and_by_kind_table_is_covered():
    wanted = {name for name, kind in registry.TABLES.items() if kind in (registry.JOB, "by_kind")}
    assert {spec.name for spec in jobs_bundle.TABLES} == wanted


def test_round_trip_is_row_for_row_and_files_arrive(home, recv, roots):
    ids = build_job(home, roots.home)
    copy_profile(home, recv, ids)
    expected = snapshot(home)
    bundle = ship(home, recv, roots, ids.job)
    roots.use("recv")
    assert snapshot(recv) == expected
    assert expected["qa_entries"] and expected["resume_versions"] and expected["kb_port_log"]
    received = tree(roots.recv)
    assert received == {
        "Co_Role_a/resume.pdf": b"%PDF a", "Co_Role_a/resume.tex": b"tex a",
        "Co_Role_a/evidence/shot.png": b"png a",
    }
    application = recv.get(models.Application, ids.app)
    assert application.pdf_path == str(roots.recv / "Co_Role_a" / "resume.pdf")
    assert (roots.recv / "Co_Role_a" / "resume.pdf").is_file()
    assert bundle["files"] and bundle["files_skipped"] == 0


def test_bundle_is_json_safe_and_carries_ownership_as_fields_not_rows(home, recv, roots):
    ids = build_job(home, roots.home)
    bundle = jobs_bundle.export_job(home, ids.job)
    json.dumps(bundle)
    assert bundle["owner"] == status.machine_id(home)
    assert bundle["handover"] is None and isinstance(bundle["sync_rev"], int)
    job_row = next(item["row"] for item in bundle["rows"] if item["table"] == "jobs")
    assert not IGNORED & set(job_row)
    assert job_row["id"] == ids.job.hex and job_row["created_at"] == WHEN.isoformat()
    assert Decimal(job_row["salary_min"]) == Decimal("120000.5")
    app_row = next(item["row"] for item in bundle["rows"]
                   if item["table"] == "applications" and item["row"]["id"] == ids.app.hex)
    assert app_row["artifact_dir"] == "applications:Co_Role_a"
    assert app_row["pdf_path"] == "applications:Co_Role_a/resume.pdf"
    assert str(roots.home) not in json.dumps(bundle)


def test_export_names_the_current_owner_of_a_replica(home, roots):
    ids = build_job(home, roots.home)
    home.get(models.Job, ids.job).owner_machine = "someone-else"
    home.commit()
    assert jobs_bundle.export_job(home, ids.job)["owner"] == "someone-else"


def test_apply_makes_the_sender_the_owner(home, recv, roots):
    ids = build_job(home, roots.home)
    copy_profile(home, recv, ids)
    ship(home, recv, roots, ids.job, sender="laptop-1")
    assert recv.get(models.Job, ids.job).owner_machine == "laptop-1"
    assert recv.get(models.Job, ids.job).sync_rev > 0


def test_reapplying_the_same_bundle_changes_nothing(home, recv, roots):
    ids = build_job(home, roots.home)
    copy_profile(home, recv, ids)
    bundle = ship(home, recv, roots, ids.job)
    roots.use("recv")
    first, files_first = snapshot(recv), tree(roots.recv)
    jobs_bundle.apply_job(recv, copy.deepcopy(bundle), sender_machine="home-machine")
    assert snapshot(recv) == first and tree(roots.recv) == files_first


def test_a_changed_job_updates_the_replica(home, recv, roots):
    ids = build_job(home, roots.home)
    copy_profile(home, recv, ids)
    ship(home, recv, roots, ids.job)
    job = home.get(models.Job, ids.job)
    job.title = "Renamed"
    home.get(models.Application, ids.app).status = "applied"
    home.commit()
    ship(home, recv, roots, ids.job)
    assert recv.get(models.Job, ids.job).title == "Renamed"
    assert recv.get(models.Application, ids.app).status == "applied"
    roots.use("recv")
    received = snapshot(recv)
    roots.use("home")
    assert received == snapshot(home)


def test_rows_removed_at_the_sender_are_removed_at_the_receiver(home, recv, roots):
    ids = build_job(home, roots.home)
    copy_profile(home, recv, ids)
    ship(home, recv, roots, ids.job)
    home.delete(home.get(models.QAEntry, ids.qa[1]))
    home.query(models.ResumeVersion).filter_by(version_number=2).delete()
    home.query(models.HealthGateWaiver).delete()
    home.query(models.KBPortLog).delete()
    home.delete(home.get(models.Application, ids.app2))
    home.commit()
    ship(home, recv, roots, ids.job)
    roots.use("recv")
    received = snapshot(recv)
    roots.use("home")
    assert received == snapshot(home)
    assert not received["health_gate_waivers"] and not received["kb_port_log"]
    assert len(received["qa_entries"]) == 1 and len(received["resume_versions"]) == 1


def test_removing_an_application_removes_its_keyed_rows_which_have_no_fk(home, recv, roots):
    ids = build_job(home, roots.home)
    copy_profile(home, recv, ids)
    ship(home, recv, roots, ids.job)
    assert recv.query(models.ResumeVersion).count() == 2
    for model in (models.ResumeVersion, models.ResumeLintReport, models.HealthAskAnswer):
        home.query(model).delete()
    home.query(models.HealthGateWaiver).delete()
    home.query(models.KBPortLog).delete()
    home.query(models.QAEntry).delete()
    home.query(models.ConsentEvent).delete()
    home.query(models.TailoringSession).delete()
    home.query(models.AtsScore).delete()
    home.query(models.FilledAnswer).delete()
    home.query(models.ApplicationProposal).delete()
    home.query(models.Application).delete()
    home.commit()
    ship(home, recv, roots, ids.job)
    for model in (models.Application, models.ResumeVersion, models.ResumeLintReport,
                  models.HealthAskAnswer, models.HealthGateWaiver, models.KBPortLog):
        assert recv.query(model).count() == 0
    assert recv.get(models.Job, ids.job) is not None


def test_keyed_rows_of_a_deleted_application_are_not_exported(home, roots):
    ids = build_job(home, roots.home)
    home.add(models.ResumeVersion(id=uuid.uuid4(), resume_kind="application",
                                  resume_key=str(uuid.uuid4()), version_number=1, snapshot={},
                                  source="create"))
    home.add(models.ResumeVersion(id=uuid.uuid4(), resume_kind="base", resume_key=str(ids.app),
                                  version_number=9, snapshot={}, source="create"))
    home.commit()
    bundle = jobs_bundle.export_job(home, ids.job)
    versions = [i["row"] for i in bundle["rows"] if i["table"] == "resume_versions"]
    assert {row["version_number"] for row in versions} == {1, 2}


def test_base_rows_and_other_jobs_on_the_receiver_survive(home, recv, roots):
    ids = build_job(home, roots.home)
    copy_profile(home, recv, ids)
    other = build_job(recv, roots.recv, tag="b")
    recv.add(models.ResumeVersion(id=uuid.uuid4(), resume_kind="base", resume_key="base",
                                  version_number=1, snapshot={}, source="create"))
    recv.commit()
    before_other = recv.query(models.ResumeVersion).count()
    ship(home, recv, roots, ids.job)
    roots.use("recv")
    assert recv.get(models.Job, other.job) is not None
    assert recv.query(models.QAEntry).count() == 4
    assert recv.query(models.ResumeVersion).count() == before_other + 2
    assert recv.query(models.ResumeVersion).filter_by(resume_kind="base").count() == 1
    assert (roots.recv / "Co_Role_b" / "resume.pdf").is_file()


def test_a_missing_referral_becomes_null_not_a_failure(home, recv, roots):
    referral = uuid.uuid4()
    home.add(models.Referral(id=referral, company="Acme", careers_url="https://example.test"))
    home.commit()
    ids = build_job(home, roots.home, referral_id=referral)
    copy_profile(home, recv, ids)
    ship(home, recv, roots, ids.job)
    assert recv.get(models.Application, ids.app).referral_id is None
    assert recv.get(models.ApplicationProposal, ids.proposal).referral_id is None


def test_a_present_referral_is_kept(home, recv, roots):
    referral = uuid.uuid4()
    for db in (home, recv):
        db.add(models.Referral(id=referral, company="Acme", careers_url="https://example.test"))
        db.commit()
    ids = build_job(home, roots.home, referral_id=referral)
    copy_profile(home, recv, ids)
    ship(home, recv, roots, ids.job)
    assert recv.get(models.Application, ids.app).referral_id == referral


def test_a_port_log_row_whose_entity_the_receiver_lacks_is_skipped(home, recv, roots):
    ids = build_job(home, roots.home)
    ship(home, recv, roots, ids.job)
    assert recv.query(models.KBPortLog).count() == 0
    assert recv.query(models.ResumeVersion).count() == 2


def test_duplicate_text_on_another_local_job_raises(home, recv, roots):
    ids = build_job(home, roots.home)
    clash = uuid.uuid4()
    home_hash = home.get(models.Job, ids.job).raw_text_hash
    recv.add(models.Job(id=clash, raw_text="same", raw_text_hash=home_hash))
    recv.commit()
    roots.use("home")
    bundle = jobs_bundle.export_job(home, ids.job)
    roots.use("recv")
    with pytest.raises(jobs_bundle.DuplicateJob) as caught:
        jobs_bundle.apply_job(recv, bundle, sender_machine="m")
    assert caught.value.local_id == clash
    assert recv.get(models.Job, ids.job) is None
    assert SENTINEL not in str(caught.value)


def test_a_job_with_no_application_round_trips(home, recv, roots):
    job_id = uuid.uuid4()
    home.add(models.Job(id=job_id, raw_text="bare", raw_text_hash="bare"))
    home.add(models.JobSkill(job_id=job_id, skill_name="s", skill_category="c",
                             requirement_level="r"))
    home.commit()
    bundle = ship(home, recv, roots, job_id)
    assert bundle["files"] == []
    assert recv.get(models.Job, job_id).raw_text == "bare"
    assert recv.query(models.JobSkill).count() == 1


def test_an_application_whose_folder_is_missing_still_travels(home, recv, roots):
    ids = build_job(home, roots.home)
    import shutil
    shutil.rmtree(roots.home / "Co_Role_a")
    bundle = ship(home, recv, roots, ids.job)
    assert bundle["files"] == []
    application = recv.get(models.Application, ids.app)
    assert application.artifact_dir == str(roots.recv / "Co_Role_a")
    assert not (roots.recv / "Co_Role_a").exists()


def test_paths_outside_every_root_are_dropped(home, recv, roots, tmp_path):
    ids = build_job(home, roots.home)
    home.get(models.Application, ids.app).pdf_path = str(tmp_path / "elsewhere" / "x.pdf")
    home.commit()
    bundle = ship(home, recv, roots, ids.job)
    assert str(tmp_path) not in json.dumps(bundle)
    assert recv.get(models.Application, ids.app).pdf_path is None


def test_a_null_json_column_stays_sql_null(home, recv, roots):
    ids = build_job(home, roots.home)
    ship(home, recv, roots, ids.job)
    raw = recv.connection().exec_driver_sql(
        "SELECT gaps_json FROM ats_scores WHERE gaps_json IS NULL").fetchall()
    assert len(raw) == 1
    ship(home, recv, roots, ids.job)
    assert len(recv.connection().exec_driver_sql(
        "SELECT gaps_json FROM ats_scores WHERE gaps_json IS NULL").fetchall()) == 1


def test_a_stale_unique_row_with_another_id_is_replaced(home, recv, roots):
    ids = build_job(home, roots.home)
    copy_profile(home, recv, ids)
    ship(home, recv, roots, ids.job)
    stale = recv.query(models.ResumeVersion).filter_by(version_number=1).one()
    recv.query(models.ResumeVersion).filter_by(version_number=2).delete()
    recv.execute(models.ResumeVersion.__table__.update().where(
        models.ResumeVersion.id == stale.id).values(id=uuid.uuid4()))
    recv.commit()
    ship(home, recv, roots, ids.job)
    roots.use("recv")
    assert sorted(v.version_number for v in recv.query(models.ResumeVersion)) == [1, 2]


def test_a_primary_key_clash_with_another_job_fails_cleanly(home, recv, roots):
    ids = build_job(home, roots.home)
    other = build_job(recv, roots.recv, tag="b")
    recv.execute(models.QAEntry.__table__.update().where(
        models.QAEntry.id == other.qa[0]).values(id=ids.qa[0]))
    recv.commit()
    roots.use("home")
    bundle = jobs_bundle.export_job(home, ids.job)
    roots.use("recv")
    with pytest.raises(ValueError) as caught:
        jobs_bundle.apply_job(recv, bundle, sender_machine="m")
    assert SENTINEL not in str(caught.value) and "INSERT" not in str(caught.value)
    assert recv.get(models.Job, ids.job) is None
    assert not (roots.recv / "Co_Role_a").exists()


def _bundle(home, roots):
    ids = build_job(home, roots.home)
    roots.use("home")
    return ids, json.loads(json.dumps(jobs_bundle.export_job(home, ids.job)))


def _row(bundle, table, index=0):
    return [i["row"] for i in bundle["rows"] if i["table"] == table][index]


def _refused(recv, roots, bundle):
    roots.use("recv")
    before = (recv.query(models.Job).count(), tree(roots.recv))
    with pytest.raises(ValueError) as caught:
        jobs_bundle.apply_job(recv, bundle, sender_machine="m")
    assert SENTINEL not in str(caught.value)
    assert (recv.query(models.Job).count(), tree(roots.recv)) == before


def test_hostile_bundles_are_refused_whole(home, recv, roots):
    _, good = _bundle(home, roots)

    unknown = copy.deepcopy(good)
    unknown["rows"].append({"table": "settings", "row": {"key": "k", "value": "v"}})
    extra = copy.deepcopy(good)
    _row(extra, "jobs")["owner_machine"] = "me"
    foreign = copy.deepcopy(good)
    _row(foreign, "qa_entries")["application_id"] = uuid.uuid4().hex
    other_job = copy.deepcopy(good)
    _row(other_job, "job_skills")["job_id"] = uuid.uuid4().hex
    keyed = copy.deepcopy(good)
    _row(keyed, "resume_versions")["resume_key"] = uuid.uuid4().hex
    base_kind = copy.deepcopy(good)
    _row(base_kind, "resume_versions")["resume_kind"] = "base"
    escape = copy.deepcopy(good)
    _row(escape, "applications")["artifact_dir"] = "applications:../outside"
    other_root = copy.deepcopy(good)
    _row(other_root, "applications")["artifact_dir"] = "base_resumes:x"
    bad_value = copy.deepcopy(good)
    _row(bad_value, "jobs")["created_at"] = "not a date"
    two_jobs = copy.deepcopy(good)
    two_jobs["rows"].append(copy.deepcopy(next(i for i in good["rows"] if i["table"] == "jobs")))
    two_jobs["rows"][-1]["row"]["id"] = uuid.uuid4().hex
    for bundle in (unknown, extra, foreign, other_job, keyed, base_kind, escape, other_root,
                   bad_value, two_jobs):
        _refused(recv, roots, bundle)


@pytest.mark.parametrize("shape", ["none", "empty", "no-rows", "row-not-dict", "bad-id", "files-not-list"])
def test_malformed_bundles_raise_value_error(home, recv, roots, shape):
    _, good = _bundle(home, roots)
    broken = {
        "none": None, "empty": {}, "no-rows": {"job_id": good["job_id"]},
        "row-not-dict": {**good, "rows": ["x"]},
        "bad-id": {**good, "job_id": 5},
        "files-not-list": {**good, "files": "x"},
    }[shape]
    roots.use("recv")
    with pytest.raises(ValueError):
        jobs_bundle.apply_job(recv, broken, sender_machine="m")
    assert recv.query(models.Job).count() == 0


def test_files_outside_the_jobs_artifact_folders_are_refused(home, recv, roots):
    _, good = _bundle(home, roots)
    for path in ("base_resumes:evil.json", "applications:Elsewhere/x.pdf",
                 "applications:Co_Role_a/../Other/x.pdf", "applications:Co_Role_a_prefix/x"):
        bad = copy.deepcopy(good)
        bad["files"][0]["path"] = path
        _refused(recv, roots, bad)


def test_a_bad_file_digest_rolls_the_rows_back(home, recv, roots):
    _, good = _bundle(home, roots)
    good["files"][0]["sha256"] = "0" * 64
    _refused(recv, roots, good)
    assert recv.query(models.Application).count() == 0


def test_the_size_limit_applies_on_export_and_apply(home, recv, roots):
    ids = build_job(home, roots.home)
    with pytest.raises(ValueError):
        jobs_bundle.export_job(home, ids.job, max_bytes=5)
    bundle = jobs_bundle.export_job(home, ids.job)
    roots.use("recv")
    with pytest.raises(ValueError):
        jobs_bundle.apply_job(recv, bundle, sender_machine="m", max_bytes=5)
    assert recv.get(models.Job, ids.job) is None


def test_nested_artifact_folders_do_not_duplicate_files(home, roots):
    ids = build_job(home, roots.home)
    nested = roots.home / "Co_Role_a" / "evidence"
    home.get(models.Application, ids.app2).artifact_dir = str(nested)
    home.commit()
    paths = [entry["path"] for entry in jobs_bundle.export_job(home, ids.job)["files"]]
    assert len(paths) == len(set(paths)) == 3


def test_apply_works_on_a_guarded_replica_and_the_guard_still_refuses_user_writes(
        home, recv, roots, request):
    ids = build_job(home, roots.home)
    copy_profile(home, recv, ids)
    bundle = json.loads(json.dumps(jobs_bundle.export_job(home, ids.job)))
    request.getfixturevalue("sync_remote")  # from here this process is the always-on copy
    roots.use("recv")
    for _ in range(2):
        jobs_bundle.apply_job(recv, copy.deepcopy(bundle), sender_machine="laptop-1")
    assert "sync_apply" not in recv.info
    assert recv.get(models.Job, ids.job).owner_machine == "laptop-1"
    recv.add(models.QAEntry(application_id=ids.app, kind="answer"))
    with pytest.raises(NotOwnedHere):
        recv.commit()
    recv.rollback()


def test_apply_does_not_log_or_echo_the_bundle(home, recv, roots, caplog):
    _, good = _bundle(home, roots)
    caplog.set_level(logging.DEBUG)
    _row(good, "jobs")["created_at"] = "bogus"
    _refused(recv, roots, good)
    caplog.clear()
    _, fine = _bundle(home, roots)
    roots.use("recv")
    jobs_bundle.apply_job(recv, fine, sender_machine="m")
    assert SENTINEL not in caplog.text


def _selects(engine):
    seen = []

    def count(conn, cursor, statement, *rest):
        if statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    return seen, lambda: event.remove(engine, "before_cursor_execute", count)


@pytest.mark.parametrize("pass_number", [1, 2])
def test_apply_cost_does_not_grow_with_row_count(tmp_path, roots, home, pass_number):
    counts = {}
    for qa_count in (2, 40):
        engine = make_engine(f"sqlite:///{tmp_path / f'r{qa_count}-{pass_number}.sqlite3'}")
        Base.metadata.create_all(engine)
        with sessionmaker(bind=engine, autoflush=False)() as recv:
            ids = build_job(home, roots.home, tag=f"n{qa_count}", qa_count=qa_count)
            roots.use("home")
            bundle = json.loads(json.dumps(jobs_bundle.export_job(home, ids.job)))
            roots.use("recv")
            if pass_number == 2:
                jobs_bundle.apply_job(recv, copy.deepcopy(bundle), sender_machine="m")
            seen, stop = _selects(engine)
            jobs_bundle.apply_job(recv, bundle, sender_machine="m")
            stop()
            counts[qa_count] = len(seen)
            assert recv.query(models.QAEntry).count() == qa_count
        engine.dispose()
        roots.use("home")
    assert counts[40] <= counts[2] + 2, counts


def test_tombstone_removes_the_replica_its_subtree_and_its_folders(home, recv, roots):
    ids = build_job(home, roots.home)
    copy_profile(home, recv, ids)
    other = build_job(recv, roots.recv, tag="b")
    ship(home, recv, roots, ids.job)
    roots.use("recv")
    jobs_bundle.apply_tombstone(recv, ids.job)
    assert recv.get(models.Job, ids.job) is None
    assert recv.query(models.Application).filter_by(job_id=ids.job).count() == 0
    assert recv.query(models.ResumeVersion).filter_by(resume_key=str(ids.app)).count() == 0
    assert recv.query(models.KBPortLog).filter_by(resume_key=str(ids.app)).count() == 0
    assert not (roots.recv / "Co_Role_a").exists()
    assert (roots.recv / "Co_Role_b" / "resume.pdf").is_file()
    assert recv.get(models.Job, other.job) is not None
    assert recv.query(models.QAEntry).count() == 2
    assert recv.query(models.SyncTombstone).count() == 0


def test_tombstone_of_an_unknown_job_is_a_no_op(recv, roots):
    jobs_bundle.apply_tombstone(recv, uuid.uuid4())


def test_tombstone_keeps_a_folder_another_application_still_uses(home, recv, roots):
    ids = build_job(home, roots.home)
    copy_profile(home, recv, ids)
    other = build_job(recv, roots.recv, tag="b")
    ship(home, recv, roots, ids.job)
    shared = roots.recv / "Co_Role_a"
    recv.get(models.Application, other.app).artifact_dir = str(shared)
    recv.commit()
    roots.use("recv")
    jobs_bundle.apply_tombstone(recv, ids.job)
    assert shared.is_dir()
