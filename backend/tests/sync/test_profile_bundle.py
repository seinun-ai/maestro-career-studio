"""The profile travels as a bundle: export at home, apply onto the always-on copy."""

import copy
import gc
import json
import logging
import os
import stat
import traceback
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import sessionmaker

from app import models
from app.config import settings
from app.db import Base, make_engine
from app.services import base_resume_data, job_site_login
from app.services.json_settings import JsonSetting
from app.services.sync import bundle_rows, files, profile_bundle, registry

PASSWORD = "SENTINEL-PASSWORD-5521"
WHEN = datetime(2026, 10, 1, 12, 30, 5, 123456, tzinfo=UTC)
SIDES = ("home", "recv")
ROOT_NAMES = ("applications", "base_resumes", "kb_documents")
PROFILE_MODELS = [spec.model for spec in profile_bundle.TABLES]
PATHS = {models.BaseResume: ("pdf_path", "tex_path"), models.KBDocument: ("file_path",)}


@pytest.fixture(autouse=True)
def sync_off(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path / "settings")
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    monkeypatch.setattr(settings, "sync_remote_url", "")


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """Per-side directories; ``use`` points the process-global roots and settings dir at one side."""
    paths = {}
    for side in SIDES:
        for name in (*ROOT_NAMES, "settings"):
            paths[side, name] = tmp_path / side / name
            paths[side, name].mkdir(parents=True)

    def use(side):
        for name in ROOT_NAMES:
            monkeypatch.setattr(settings, f"{name}_dir", paths[side, name])
        monkeypatch.setattr(settings, "settings_dir", paths[side, "settings"])

    use("home")
    elsewhere = tmp_path / "elsewhere.pdf"
    return SimpleNamespace(use=use, at=lambda side, name: paths[side, name], elsewhere=elsewhere)


@pytest.fixture
def remote(tmp_path, monkeypatch):
    """Switch this process between home (sync off) and the always-on copy."""
    key = tmp_path / "key"
    key.write_text("k" * 40, encoding="utf-8")
    key.chmod(0o600)

    def on():
        monkeypatch.setattr(settings, "sync_key_file", key)
        monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")

    def off():
        monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
        monkeypatch.setattr(settings, "sync_remote_url", "")

    def as_home():
        """A key but no remote url: sync is on and this copy is home."""
        monkeypatch.setattr(settings, "sync_key_file", key)
        monkeypatch.setattr(settings, "sync_remote_url", "")

    return SimpleNamespace(on=on, off=off, as_home=as_home)


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


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def _setting(db, key, value):
    db.add(models.Setting(key=key, value=value))


def build_profile(db, roots):
    """One of everything the profile owns, plus rows and files that must NOT travel."""
    base, kbd = roots.at("home", "base_resumes"), roots.at("home", "kb_documents")
    ids = SimpleNamespace(entity=uuid.uuid4(), doc=uuid.uuid4(), point=uuid.uuid4(),
                          referral=uuid.uuid4(), v1=uuid.uuid4(), v2=uuid.uuid4())
    _write(base / "data_scientist.json", json.dumps({"name": "HOME CONTENT"}))
    _write(base / "pdfs" / "data_scientist.pdf", b"%PDF home")
    _write(base / "tex" / "data_scientist.tex", b"tex home")
    _write(base / "pdfs" / "data_scientist.pages" / "page-1.png", b"regenerated")
    _write(kbd / str(ids.doc) / "cv.pdf", b"%PDF kb")
    db.add_all([
        models.BaseResume(slug="data_scientist", display_name="DS", data_json={"name": "db copy"},
                          pdf_path=str(base / "pdfs" / "data_scientist.pdf"),
                          tex_path=str(base / "tex" / "data_scientist.tex"),
                          pdf_rendered_at=WHEN, created_at=WHEN, updated_at=WHEN),
        models.BaseResume(slug="outside", data_json={}, pdf_path="/somewhere/else.pdf",
                          created_at=WHEN, updated_at=WHEN),
        models.Template(id="mine", source="TEMPLATE SOURCE", created_at=WHEN, updated_at=WHEN),
        models.Referral(id=ids.referral, company="Acme", careers_url="https://x.test",
                        created_at=WHEN, updated_at=WHEN),
        models.KBEntity(id=ids.entity, kind="project", title="Proj", created_at=WHEN,
                        updated_at=WHEN),
        models.KBProfile(id=1, contact_json={"name": "Home"}, summary="s", skills_json=["a"],
                         updated_at=WHEN),
    ])
    db.flush()
    db.add(models.KBDocument(id=ids.doc, entity_id=ids.entity, filename="cv.pdf",
                             file_path=str(kbd / str(ids.doc) / "cv.pdf"), created_at=WHEN))
    db.flush()
    db.add(models.KBPoint(id=ids.point, entity_id=ids.entity, text="point", origin="manual",
                          source_document_id=ids.doc, created_at=WHEN, updated_at=WHEN))
    db.flush()
    _add_by_kind(db, ids)
    _add_settings(db)
    db.commit()
    return ids


def _add_by_kind(db, ids):
    db.add(models.KBPortLog(id=uuid.uuid4(), entity_id=ids.entity, point_id=ids.point,
                            resume_kind="base", resume_key="data_scientist", section="exp",
                            ported_text="t", ported_at=WHEN))
    db.add(models.KBPortLog(id=uuid.uuid4(), entity_id=ids.entity, resume_kind="application",
                            resume_key=str(uuid.uuid4()), section="exp", ported_text="job-side",
                            ported_at=WHEN))
    db.add(models.ResumeVersion(id=ids.v1, resume_kind="base", resume_key="data_scientist",
                                version_number=1, snapshot={"v": 1}, source="create",
                                created_at=WHEN))
    db.flush()
    db.add(models.ResumeVersion(id=ids.v2, resume_kind="base", resume_key="data_scientist",
                                version_number=2, parent_version_id=ids.v1, snapshot={"v": 2},
                                source="form_edit", created_at=WHEN))
    db.add(models.ResumeVersion(id=uuid.uuid4(), resume_kind="application",
                                resume_key=str(uuid.uuid4()), version_number=1, snapshot={},
                                source="create", created_at=WHEN))
    db.add(models.ResumeLintReport(id=uuid.uuid4(), resume_kind="base",
                                   resume_key="data_scientist", report_json={"ok": True},
                                   created_at=WHEN))
    db.add(models.HealthAskAnswer(id=uuid.uuid4(), resume_kind="base", resume_key="data_scientist",
                                  finding_id="f1", content_hash="h", answer="a", created_at=WHEN))
    db.add(models.HealthGateWaiver(id=uuid.uuid4(), resume_kind="base",
                                   resume_key="data_scientist", gate_id="S1", reason="r",
                                   created_at=WHEN))


def _add_settings(db):
    _setting(db, "persona", "home persona\n")
    _setting(db, "auto_apply", '{"mode": "home"}')
    _setting(db, "prompts.tailor", "home prompt")
    _setting(db, "sync.machine_id", "home-machine")
    _setting(db, "llm.capabilities.m", "home-cache")
    _setting(db, "kb.seeded", "home-flag")


def build_seeds(db, roots):
    """What startup seeding and first-read defaults leave on a fresh always-on copy, plus local data."""
    base, kbd = roots.at("recv", "base_resumes"), roots.at("recv", "kb_documents")
    ids = SimpleNamespace(referral=uuid.uuid4(), app=uuid.uuid4(), entity=uuid.uuid4())
    _write(base / "example.json", json.dumps({"name": "SEED"}))
    _write(base / "pdfs" / "example.pdf", b"%PDF seed")
    _write(base / "tex" / "example.tex", b"tex seed")
    _write(base / "pdfs" / "example.pages" / "page-1.png", b"seed preview")
    _write(kbd / "old.pdf", b"%PDF old kb")
    _write(roots.elsewhere, b"%PDF not ours")
    _write(roots.at("recv", "settings") / "persona.md", "seed persona")
    _write(roots.at("recv", "settings") / "market.json", '{"seed": true}')
    db.add_all([
        models.BaseResume(slug="example", data_json={"seed": 1}, created_at=WHEN, updated_at=WHEN,
                          pdf_path=str(base / "pdfs" / "example.pdf"),
                          tex_path=str(base / "tex" / "example.tex")),
        models.BaseResume(slug="stray", data_json={}, pdf_path=str(roots.elsewhere),
                          created_at=WHEN, updated_at=WHEN),
        models.Template(id="seed-template", source="seed", created_at=WHEN, updated_at=WHEN),
        models.Referral(id=ids.referral, company="Stale", careers_url="https://s.test",
                        created_at=WHEN, updated_at=WHEN),
        models.KBEntity(id=ids.entity, kind="project", title="Stale", created_at=WHEN,
                        updated_at=WHEN),
        models.KBProfile(id=1, updated_at=WHEN),
    ])
    db.flush()
    _add_seed_children(db, ids, kbd)
    for key, value in (("persona", "seed persona"), ("market", '{"seed": true}'),
                       ("prompts.stale", "gone"), ("sync.machine_id", "recv-id"),
                       ("llm.capabilities.m", "recv-cache"), ("kb.seeded", "recv-flag")):
        _setting(db, key, value)
    db.commit()
    return ids


def _add_seed_children(db, ids, kbd):
    point, job = uuid.uuid4(), uuid.uuid4()
    db.add(models.KBDocument(id=uuid.uuid4(), entity_id=ids.entity, filename="old.pdf",
                             file_path=str(kbd / "old.pdf"), created_at=WHEN))
    db.add(models.KBPoint(id=point, entity_id=ids.entity, text="stale", origin="manual",
                          created_at=WHEN, updated_at=WHEN))
    db.add(models.Job(id=job, raw_text="job", raw_text_hash="h-seed", created_at=WHEN))
    db.flush()
    db.add(models.KBPortLog(id=uuid.uuid4(), entity_id=ids.entity, point_id=point,
                            resume_kind="base", resume_key="example", section="s",
                            ported_text="t", ported_at=WHEN))
    db.add(models.ResumeVersion(id=uuid.uuid4(), resume_kind="base", resume_key="example",
                                version_number=1, snapshot={}, source="create", created_at=WHEN))
    db.add(models.ResumeVersion(id=uuid.uuid4(), resume_kind="application", resume_key="job-key",
                                version_number=1, snapshot={}, source="create", created_at=WHEN))
    db.add(models.Application(id=ids.app, job_id=job, base_resume="example", status="saved",
                              referral_id=ids.referral, created_at=WHEN, updated_at=WHEN))


def snapshot(db, kind="profile"):
    """Every profile row, local settings left out, paths in portable form (call with roots set)."""
    db.expire_all()
    out = {}
    for model in PROFILE_MODELS:
        rows = {}
        for obj in db.scalars(select(model)):
            if not _in_scope(model, obj):
                continue
            row = {p.key: getattr(obj, p.key) for p in inspect(model).column_attrs}
            for key in PATHS.get(model, ()):
                row[key] = files.to_portable(row[key])
            pk = tuple(getattr(obj, inspect(model).get_property_by_column(c).key)
                       for c in inspect(model).primary_key)
            rows[pk] = row
        out[model.__tablename__] = rows
    return out


def _in_scope(model, obj):
    if model is models.Setting:
        return not obj.key.startswith(registry.LOCAL_SETTING_PREFIXES)
    return getattr(obj, "resume_kind", "base") == "base"


def tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def ship(home, recv, roots, remote):
    """Export at home, apply at the receiver (as the always-on copy)."""
    roots.use("home")
    bundle = json.loads(json.dumps(profile_bundle.export_profile(home)))
    apply_bundle(recv, roots, remote, bundle)
    return bundle


def apply_bundle(recv, roots, remote, bundle):
    roots.use("recv")
    remote.on()
    try:
        profile_bundle.apply_profile(recv, bundle)
    finally:
        remote.off()
        roots.use("home")


def disk_state(roots):
    return {(side, name): tree(roots.at(side, name)) for side in SIDES
            for name in (*ROOT_NAMES, "settings")}


@pytest.fixture
def world(home, recv, roots, remote):
    """Home with a full profile and login; the receiver with seeds; the login secret in place."""
    ids = build_profile(home, roots)
    job_site_login.write("me@example.test", PASSWORD)
    roots.use("recv")
    seeds = build_seeds(recv, roots)
    roots.use("home")
    return SimpleNamespace(ids=ids, seeds=seeds)


# ---------------------------------------------------------------------------- coverage


def test_every_profile_and_by_kind_table_is_covered():
    wanted = {name for name, kind in registry.TABLES.items()
              if kind in (registry.PROFILE, "by_kind")}
    assert {spec.name for spec in profile_bundle.TABLES} == wanted


def test_every_file_mirrored_setting_is_listed():
    import app.main  # noqa: F401  (imports every service that defines a setting)

    found = {(obj.key, obj.filename) for obj in gc.get_objects() if isinstance(obj, JsonSetting)}
    assert found and found <= set(profile_bundle.MIRRORS.items())
    assert {"persona", "autofill_profile"} <= set(profile_bundle.MIRRORS)


def test_templates_keep_their_content_in_the_database_not_in_a_root():
    assert "source" in {key for key in inspect(models.Template).columns.keys()}
    assert set(files.ROOTS) == set(ROOT_NAMES)  # no template root to pack


# ---------------------------------------------------------------------------- export


def test_export_is_json_safe_portable_and_leaves_out_local_and_application_rows(home, roots, world):
    bundle = profile_bundle.export_profile(home)
    text = json.dumps(bundle)
    for side_root in ROOT_NAMES:
        assert str(roots.at("home", side_root)) not in text
    tables = {}
    for item in bundle["rows"]:
        tables.setdefault(item["table"], []).append(item["row"])
    keys = {row["key"] for row in tables["settings"]}
    assert keys == {"persona", "auto_apply", "prompts.tailor"}
    assert {row["resume_kind"] for name in ("resume_versions", "kb_port_log")
            for row in tables[name]} == {"base"}
    base = {row["slug"]: row for row in tables["base_resumes"]}
    assert base["data_scientist"]["pdf_path"] == "base_resumes:pdfs/data_scientist.pdf"
    assert base["data_scientist"]["tex_path"] == "base_resumes:tex/data_scientist.tex"
    assert base["outside"]["pdf_path"] is None
    assert tables["kb_documents"][0]["file_path"] == f"kb_documents:{world.ids.doc}/cv.pdf"
    assert tables["templates"][0]["source"] == "TEMPLATE SOURCE"
    assert isinstance(bundle["profile_rev"], int)


def test_export_carries_the_files_and_the_login_and_reports_skips(home, roots, world):
    _write(roots.at("home", "base_resumes") / "template_previews" / "mine.pdf", b"%PDF preview")
    bundle = profile_bundle.export_profile(home)
    assert {entry["path"] for entry in bundle["files"]} == {
        "base_resumes:data_scientist.json", "base_resumes:pdfs/data_scientist.pdf",
        "base_resumes:tex/data_scientist.tex", f"kb_documents:{world.ids.doc}/cv.pdf",
        "base_resumes:template_previews/mine.pdf"}
    assert bundle["files_skipped"] == 1  # the "outside" resume has no JSON file
    assert bundle["job_site_login"] == {"email": "me@example.test", "password": PASSWORD}


def _exported_paths(bundle):
    return {entry["path"] for entry in bundle["files"]}


def test_stray_files_in_the_roots_do_not_travel_or_count(home, roots, world):
    base, kbd = roots.at("home", "base_resumes"), roots.at("home", "kb_documents")
    _write(base / "template_previews" / "mine.pdf", b"%PDF preview")
    clean = profile_bundle.export_profile(home)
    for stray in (base / "stray.json", base / "pdfs" / "old.pdf", base / "tex" / "old.tex",
                  base / "template_previews" / "ghost.pdf", kbd / "loose" / "x.pdf"):
        _write(stray, b"S" * 1000)
    os.mkfifo(base / "pipe")
    bundle = profile_bundle.export_profile(home)
    assert _exported_paths(bundle) == _exported_paths(clean)
    assert bundle["files_skipped"] == clean["files_skipped"]
    total = sum(bundle_rows.decoded_size(entry) for entry in clean["files"])
    assert profile_bundle.export_profile(home, max_bytes=total)["files"] == clean["files"]


def test_every_referenced_file_is_exported(home, roots, world):
    base = roots.at("home", "base_resumes")
    _write(base / "template_previews" / "mine.pdf", b"%PDF preview")
    assert _exported_paths(profile_bundle.export_profile(home)) == {
        "base_resumes:data_scientist.json", "base_resumes:pdfs/data_scientist.pdf",
        "base_resumes:tex/data_scientist.tex", f"kb_documents:{world.ids.doc}/cv.pdf",
        "base_resumes:template_previews/mine.pdf"}


def test_a_missing_referenced_file_is_skipped_and_counted_never_fatal(home, roots, world):
    before = profile_bundle.export_profile(home)
    (roots.at("home", "kb_documents") / str(world.ids.doc) / "cv.pdf").unlink()
    after = profile_bundle.export_profile(home)
    assert _exported_paths(before) - _exported_paths(after) == {
        f"kb_documents:{world.ids.doc}/cv.pdf"}
    assert after["files_skipped"] == before["files_skipped"] + 1


def test_a_referenced_file_that_is_not_regular_is_skipped_and_counted(home, roots, world):
    before = profile_bundle.export_profile(home)
    tex = roots.at("home", "base_resumes") / "tex" / "data_scientist.tex"
    tex.unlink()
    os.mkfifo(tex)
    after = profile_bundle.export_profile(home)
    assert _exported_paths(before) - _exported_paths(after) == {
        "base_resumes:tex/data_scientist.tex"}
    assert after["files_skipped"] == before["files_skipped"] + 1


def test_latex_build_leftovers_are_not_exported_or_counted(home, roots, world):
    before = profile_bundle.export_profile(home)
    tex_dir = roots.at("home", "base_resumes") / "tex"
    _write(tex_dir / "data_scientist.aux", b"leftover")
    home.get(models.BaseResume, "data_scientist").tex_path = str(tex_dir / "data_scientist.aux")
    home.commit()
    after = profile_bundle.export_profile(home)
    assert _exported_paths(before) - _exported_paths(after) == {
        "base_resumes:tex/data_scientist.tex"}
    assert after["files_skipped"] == before["files_skipped"]


def _set_rev(db, value):
    db.execute(text("INSERT INTO sync_state (name, value) VALUES ('profile_rev', :v) "
                    "ON CONFLICT(name) DO UPDATE SET value=excluded.value"), {"v": value})
    db.commit()


def test_the_revision_is_read_before_the_files_are_packed(home, roots, world, monkeypatch):
    _set_rev(home, 5)
    real = profile_bundle._pack

    def write_during_the_export(*args, **kwargs):
        _set_rev(home, 9)  # a base-resume save lands between the two steps
        return real(*args, **kwargs)

    monkeypatch.setattr(profile_bundle, "_pack", write_during_the_export)
    assert profile_bundle.export_profile(home)["profile_rev"] == 5


def test_export_without_a_login_says_none(home, roots):
    assert profile_bundle.export_profile(home)["job_site_login"] is None


def test_export_refuses_a_bundle_over_the_size_limit(home, roots, world):
    with pytest.raises(ValueError):
        profile_bundle.export_profile(home, max_bytes=5)


# ---------------------------------------------------------------------------- apply


def test_round_trip_is_row_for_row_and_files_arrive(home, recv, roots, remote, world):
    expected = snapshot(home)
    bundle = ship(home, recv, roots, remote)
    roots.use("recv")
    assert snapshot(recv) == expected
    assert expected["settings"] and expected["resume_versions"] and expected["kb_port_log"]
    base = roots.at("recv", "base_resumes")
    assert (base / "pdfs" / "data_scientist.pdf").read_bytes() == b"%PDF home"
    assert (roots.at("recv", "kb_documents") / str(world.ids.doc) / "cv.pdf").read_bytes() == b"%PDF kb"
    pdf = recv.get(models.BaseResume, "data_scientist").pdf_path
    assert pdf == str(base / "pdfs" / "data_scientist.pdf")
    assert bundle["files"]


def test_the_base_resume_file_arrives_and_load_returns_the_new_content(home, recv, roots, remote, world):
    ship(home, recv, roots, remote)
    roots.use("recv")
    assert base_resume_data.load_base_resume("data_scientist", recv) == {"name": "HOME CONTENT"}


def test_a_settings_mirror_file_is_rewritten_through_its_service(home, recv, roots, remote, world):
    ship(home, recv, roots, remote)
    mirrors = roots.at("recv", "settings")
    assert (mirrors / "persona.md").read_text(encoding="utf-8") == "home persona\n"
    assert (mirrors / "auto_apply.json").read_text(encoding="utf-8") == '{"mode": "home"}'
    assert recv.get(models.Setting, "persona").value == "home persona\n"


def test_seeds_that_exist_only_here_are_replaced_or_removed(home, recv, roots, remote, world):
    ship(home, recv, roots, remote)
    recv.expire_all()
    assert recv.get(models.BaseResume, "example") is None
    assert not (roots.at("recv", "base_resumes") / "example.json").exists()
    assert recv.get(models.Template, "seed-template") is None
    assert recv.get(models.Referral, world.seeds.referral) is None
    assert recv.get(models.KBEntity, world.seeds.entity) is None
    assert recv.get(models.Setting, "prompts.stale") is None
    assert recv.get(models.Setting, "market") is None
    assert not (roots.at("recv", "settings") / "market.json").exists()
    assert recv.get(models.KBProfile, 1).contact_json == {"name": "Home"}
    assert recv.query(models.KBPoint).count() == 1 and recv.query(models.KBDocument).count() == 1


def test_files_of_removed_rows_are_removed_and_nothing_outside_the_roots_is(
        home, recv, roots, remote, world):
    ship(home, recv, roots, remote)
    base, kbd = roots.at("recv", "base_resumes"), roots.at("recv", "kb_documents")
    assert not (base / "pdfs" / "example.pdf").exists() and not (base / "tex").joinpath(
        "example.tex").exists()
    assert not (base / "pdfs" / "example.pages").exists()
    assert not (kbd / "old.pdf").exists()
    assert roots.elsewhere.read_bytes() == b"%PDF not ours"
    assert (base / "pdfs" / "data_scientist.pdf").is_file()
    assert (kbd / str(world.ids.doc) / "cv.pdf").is_file()


def test_a_file_a_row_stops_naming_is_removed_unless_the_bundle_brings_it(
        home, recv, roots, remote, world):
    ship(home, recv, roots, remote)
    base = roots.at("recv", "base_resumes")
    home.get(models.BaseResume, "data_scientist").tex_path = None
    home.commit()
    (roots.at("home", "base_resumes") / "tex" / "data_scientist.tex").unlink()
    ship(home, recv, roots, remote)
    assert not (base / "tex" / "data_scientist.tex").exists()
    assert (base / "data_scientist.json").is_file() and (base / "pdfs" / "data_scientist.pdf").is_file()


def test_a_job_row_pointing_at_a_removed_referral_gets_null(home, recv, roots, remote, world):
    ship(home, recv, roots, remote)
    recv.expire_all()
    application = recv.get(models.Application, world.seeds.app)
    assert application is not None and application.referral_id is None


def test_job_side_rows_and_local_settings_survive(home, recv, roots, remote, world):
    ship(home, recv, roots, remote)
    recv.expire_all()
    values = {row.key: row.value for row in recv.query(models.Setting)}
    assert values["sync.machine_id"] == "recv-id"
    assert values["llm.capabilities.m"] == "recv-cache"
    assert values["kb.seeded"] == "recv-flag"
    assert recv.query(models.ResumeVersion).filter_by(resume_kind="application").count() == 1
    assert recv.query(models.Job).count() == 1


def test_a_removed_row_at_home_is_removed_on_the_next_apply(home, recv, roots, remote, world):
    ship(home, recv, roots, remote)
    home.delete(home.get(models.Setting, "prompts.tailor"))
    home.delete(home.get(models.KBPoint, world.ids.point))
    home.query(models.KBPortLog).filter_by(resume_kind="base").delete()
    home.query(models.HealthGateWaiver).delete()
    home.commit()
    expected = snapshot(home)
    ship(home, recv, roots, remote)
    roots.use("recv")
    assert snapshot(recv) == expected
    assert recv.get(models.Setting, "prompts.tailor") is None


def test_reapplying_the_same_bundle_changes_nothing(home, recv, roots, remote, world):
    bundle = ship(home, recv, roots, remote)
    roots.use("recv")
    first, state = snapshot(recv), disk_state(roots)
    apply_bundle(recv, roots, remote, copy.deepcopy(bundle))
    roots.use("recv")
    assert snapshot(recv) == first and disk_state(roots) == state


# ---------------------------------------------------------------------------- the login


def test_the_login_file_arrives_private_and_the_password_is_never_logged(
        home, recv, roots, remote, world, caplog):
    caplog.set_level(logging.DEBUG)
    ship(home, recv, roots, remote)
    roots.use("recv")
    assert job_site_login.read() == ("me@example.test", PASSWORD)
    path = job_site_login.path()
    assert path.is_file() and stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert PASSWORD not in caplog.text
    assert all(PASSWORD not in str(record.args) + record.getMessage() for record in caplog.records)


def test_no_login_at_home_clears_the_one_on_the_receiver(home, recv, roots, remote, world):
    roots.use("recv")
    job_site_login.write("old@example.test", "old-pw")
    roots.use("home")
    job_site_login.clear()
    ship(home, recv, roots, remote)
    roots.use("recv")
    assert job_site_login.read() == (None, None) and not job_site_login.path().exists()


def test_a_login_missing_its_password_replaces_instead_of_merging(home, recv, roots, remote, world):
    roots.use("recv")
    job_site_login.write("old@example.test", "old-pw")
    roots.use("home")
    bundle = json.loads(json.dumps(profile_bundle.export_profile(home)))
    bundle["job_site_login"] = {"email": "new@example.test", "password": None}
    apply_bundle(recv, roots, remote, bundle)
    roots.use("recv")
    assert job_site_login.read() == ("new@example.test", None)


def test_the_parsed_bundle_prints_no_secret(home, roots, world):
    roots.use("home")
    bundle = json.loads(json.dumps(profile_bundle.export_profile(home)))
    _row(bundle, "settings", key="persona")["value"] = "SENTINEL-AI-KEY-8842"
    parsed = profile_bundle._parse(bundle)
    shown = repr(parsed) + str(parsed)
    assert PASSWORD not in shown and "SENTINEL-AI-KEY-8842" not in shown
    assert "me@example.test" not in shown


def test_apply_returns_the_checked_revision(home, recv, roots, remote, world):
    roots.use("home")
    bundle = json.loads(json.dumps(profile_bundle.export_profile(home)))
    bundle["profile_rev"] = 7
    roots.use("recv")
    remote.on()
    try:
        assert profile_bundle.apply_profile(recv, bundle) == 7
    finally:
        remote.off()


# ---------------------------------------------------------------------------- refusals


def test_apply_on_home_is_refused_and_changes_nothing(home, recv, roots, remote, world):
    roots.use("home")
    bundle = json.loads(json.dumps(profile_bundle.export_profile(home)))
    roots.use("recv")
    before, state = snapshot(recv), disk_state(roots)
    with pytest.raises(ValueError):
        profile_bundle.apply_profile(recv, bundle)  # sync off
    remote.as_home()
    with pytest.raises(ValueError):
        profile_bundle.apply_profile(recv, bundle)
    assert snapshot(recv) == before and disk_state(roots) == state


def _row(bundle, table, **match):
    return next(item["row"] for item in bundle["rows"] if item["table"] == table
                and all(item["row"].get(k) == v for k, v in match.items()))


def _unknown_table(bundle):
    bundle["rows"].append({"table": "jobs", "row": {"id": uuid.uuid4().hex}})


def _local_key(bundle):
    bundle["rows"].append({"table": "settings", "row": {"key": "sync.machine_id", "value": "x"}})


def _local_key_by_prefix(bundle):
    bundle["rows"].append({"table": "settings", "row": {"key": "kb.seeded.v2", "value": "x"}})


def _foreign_root(bundle):
    _row(bundle, "base_resumes", slug="data_scientist")["pdf_path"] = "applications:X/a.pdf"


def _absolute_path(bundle):
    _row(bundle, "kb_documents")["file_path"] = "/etc/passwd"


def _dotdot_path(bundle):
    _row(bundle, "base_resumes", slug="data_scientist")["tex_path"] = "base_resumes:../x.tex"


def _file_outside_roots(bundle):
    bundle["files"].append({"path": "applications:X/a.pdf", "sha256": "0" * 64, "b64": ""})


def _file_dotdot(bundle):
    bundle["files"].append({"path": "base_resumes:../escape", "sha256": "0" * 64, "b64": ""})


def _bad_sha(bundle):
    bundle["files"][0]["sha256"] = "f" * 64


def _application_kind(bundle):
    _row(bundle, "resume_versions", version_number=1)["resume_kind"] = "application"


def _extra_column(bundle):
    _row(bundle, "templates")["surprise"] = 1


def _bad_date(bundle):
    _row(bundle, "templates")["created_at"] = f"not-a-date {PASSWORD}"


def _bad_login(bundle):
    bundle["job_site_login"] = {"email": "a", "password": 123, "x": PASSWORD}


def _login_missing(bundle):
    del bundle["job_site_login"]


def _bad_slug(bundle):
    _row(bundle, "base_resumes", slug="outside")["slug"] = "../evil"


def _duplicate_key(bundle):
    bundle["rows"].append(copy.deepcopy(next(i for i in bundle["rows"] if i["table"] == "templates")))


def _rev_string(bundle):
    bundle["profile_rev"] = "not-a-number"


def _rev_bool(bundle):
    bundle["profile_rev"] = True


def _rev_negative(bundle):
    bundle["profile_rev"] = -1


def _rev_float(bundle):
    bundle["profile_rev"] = 1.5


def _rev_huge(bundle):
    bundle["profile_rev"] = 2**63


def _rev_missing(bundle):
    del bundle["profile_rev"]


HOSTILE = [_unknown_table, _local_key, _local_key_by_prefix, _foreign_root, _absolute_path,
           _dotdot_path, _file_outside_roots, _file_dotdot, _bad_sha, _application_kind,
           _extra_column, _bad_date, _bad_slug, _bad_login, _login_missing, _duplicate_key,
           _rev_string, _rev_bool, _rev_negative, _rev_float, _rev_huge, _rev_missing]


@pytest.mark.parametrize("mutate", HOSTILE, ids=lambda fn: fn.__name__.strip("_"))
def test_a_hostile_bundle_is_refused_before_any_write(home, recv, roots, remote, world, mutate):
    roots.use("home")
    bundle = json.loads(json.dumps(profile_bundle.export_profile(home)))
    mutate(bundle)
    roots.use("recv")
    before, state = snapshot(recv), disk_state(roots)
    login_before = job_site_login.read()
    remote.on()
    try:
        with pytest.raises(ValueError) as caught:
            profile_bundle.apply_profile(recv, bundle)
    finally:
        remote.off()
    assert PASSWORD not in str(caught.value) and "/" not in str(caught.value).replace("and/or", "")
    assert snapshot(recv) == before and disk_state(roots) == state
    assert job_site_login.read() == login_before
    recv.rollback()
    assert recv.get(models.Setting, "sync.machine_id").value == "recv-id"


def test_a_failure_after_the_rows_rolls_them_back(home, recv, roots, remote, world, monkeypatch):
    roots.use("home")
    bundle = json.loads(json.dumps(profile_bundle.export_profile(home)))
    roots.use("recv")
    before, state = snapshot(recv), disk_state(roots)

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(files, "unpack", boom)
    remote.on()
    try:
        with pytest.raises(OSError):
            profile_bundle.apply_profile(recv, bundle)
    finally:
        remote.off()
    assert snapshot(recv) == before and disk_state(roots) == state


def _text_gets_a_dict(bundle):
    _row(bundle, "templates")["source"] = {"leak": PASSWORD}


def _integer_gets_a_string(bundle):
    _row(bundle, "base_resumes", slug="outside")["pdf_pages"] = PASSWORD


def _integer_gets_a_bool(bundle):
    _row(bundle, "base_resumes", slug="outside")["pdf_pages"] = True


def _boolean_gets_a_string(bundle):
    _row(bundle, "templates")["is_default"] = PASSWORD


def _uuid_is_garbage(bundle):
    _row(bundle, "referrals")["id"] = PASSWORD


def _datetime_is_naive(bundle):
    _row(bundle, "templates")["created_at"] = "2026-10-01T12:00:00"


def _setting_gets_a_number(bundle):
    _row(bundle, "settings", key="persona")["value"] = 12345


def _setting_key_is_a_list(bundle):
    _row(bundle, "settings", key="persona")["key"] = [PASSWORD]


def _datetime_is_a_number(bundle):
    _row(bundle, "templates")["created_at"] = 20261001


def _text_has_a_lone_surrogate(bundle):
    _row(bundle, "templates")["source"] = "\ud800" + PASSWORD


def _integer_overflows_the_database(bundle):
    _row(bundle, "base_resumes", slug="outside")["pdf_pages"] = 2**63


def _login_has_a_lone_surrogate(bundle):
    bundle["job_site_login"] = {"email": "a@b.test", "password": "\ud800" + PASSWORD}


MISTYPED = [_text_gets_a_dict, _integer_gets_a_string, _integer_gets_a_bool,
            _boolean_gets_a_string, _uuid_is_garbage, _datetime_is_naive,
            _setting_gets_a_number, _setting_key_is_a_list, _datetime_is_a_number,
            _text_has_a_lone_surrogate, _integer_overflows_the_database,
            _login_has_a_lone_surrogate]


def _printed(caught):
    """Every way an exception can be shown: str, repr, the traceback. It must be a plain ValueError
    (not a UnicodeEncodeError or OverflowError, whose text and attributes carry the value)."""
    assert type(caught.value) is ValueError
    return ("".join(traceback.format_exception(caught.value)) + caught.exconly()
            + repr(caught.value) + str(caught.value))


@pytest.mark.parametrize("mutate", MISTYPED, ids=lambda fn: fn.__name__.strip("_"))
def test_a_mistyped_value_is_refused_with_a_fixed_message_and_no_value_anywhere(
        home, recv, roots, remote, world, mutate, caplog):
    caplog.set_level(logging.DEBUG)
    roots.use("home")
    bundle = json.loads(json.dumps(profile_bundle.export_profile(home)))
    mutate(bundle)
    roots.use("recv")
    before, state = snapshot(recv), disk_state(roots)
    remote.on()
    try:
        with pytest.raises(ValueError) as caught:
            profile_bundle.apply_profile(recv, bundle)
    finally:
        remote.off()
    shown = _printed(caught)
    assert PASSWORD not in shown and "[parameters" not in shown and "12345" not in shown
    assert "SELECT" not in shown and "INSERT" not in shown
    assert PASSWORD not in caplog.text
    assert snapshot(recv) == before and disk_state(roots) == state


def test_pending_changes_are_refused_not_flushed_with_the_guard_off(home, recv, roots, remote, world):
    roots.use("home")
    bundle = json.loads(json.dumps(profile_bundle.export_profile(home)))
    roots.use("recv")
    recv.add(models.Setting(key="prompts.pending", value="x"))
    remote.on()
    try:
        with pytest.raises(ValueError):
            profile_bundle.apply_profile(recv, bundle)
    finally:
        remote.off()
    recv.rollback()
    assert recv.get(models.Setting, "persona").value == "seed persona"
