"""One writer per job/profile, with sync-off behavior preserved."""

import ast
import json
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.config import settings
from app.db import get_db
from app.main import app
from app.models.types import utcnow
from app.services import pdf_render, tailoring_session
from app.services.sync import hooks, registry, status

RESUME = {
    "contact": {"name": "Example Applicant", "email": "applicant@example.test"},
    "summary": "Original summary",
    "skills": [{"category": "Tools", "items": ["Python"]}],
    "projects": [{"name": "Example project", "bullets": ["Built a data pipeline"]}],
}
JD = {"title": "Engineer", "company": "Example employer", "role_category": "other",
      "skills": [{"skill_name": "Python", "skill_category": "tool",
                  "requirement_level": "required"}]}
OPS = [{"kind": "replace_summary", "value": "Updated summary"}]
PROFILE_MESSAGE = "Your laptop keeps your profile. Change it there."
UNRESOLVED_MESSAGE = "Maestro couldn't tell which job this change belongs to, so it wasn't saved."


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    for name in ("base_resumes_dir", "applications_dir", "kb_documents_dir", "settings_dir"):
        path = tmp_path / name
        path.mkdir()
        monkeypatch.setattr(settings, name, path)
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    monkeypatch.setattr(settings, "sync_remote_url", "")


def _fake_compiler(tmp_path):
    def compile_document(doc, out_dir, **kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        source, pdf = out_dir / "resume.tex", out_dir / "resume.pdf"
        source.write_text(doc.source_text)
        pdf.write_bytes(b"test pdf")
        return source, pdf
    return compile_document


@pytest.fixture
def external_fakes(tmp_path, monkeypatch):
    from app.services import bullet_classify, health_verify, jd_extraction, llm, pdf_preview

    monkeypatch.setattr(llm, "call_openai", lambda **kwargs: {"ops": [], "answers": ["Example answer"]})
    monkeypatch.setattr(jd_extraction, "extract_jd", lambda *args: dict(JD))
    monkeypatch.setattr(bullet_classify, "classify_items", lambda *args: {})
    monkeypatch.setattr(health_verify, "verify_detections", lambda db, resume, gaps, c2, **kwargs: (gaps, c2, {}))
    monkeypatch.setattr(pdf_render, "compile_document", _fake_compiler(tmp_path))
    monkeypatch.setattr(pdf_render, "compile_cover_letter_pdf", lambda *args, **kwargs: tmp_path / "letter.pdf")
    monkeypatch.setattr(pdf_preview, "ensure_page_images", lambda *args: [tmp_path / "page.png"])


def _seed_job(db, owner="other-machine", handover=None):
    job = models.Job(id=uuid.uuid4(), raw_text="Example role", raw_text_hash=uuid.uuid4().hex,
                     extracted_json=JD, title="Engineer", company="Example employer",
                     owner_machine=owner, handover=handover)
    db.add(job)
    db.flush()
    return job


def _seed_children(db, job):
    application = models.Application(job_id=job.id, base_resume="guard_base", customized_json=RESUME)
    db.add(application)
    db.flush()
    qa = models.QAEntry(application_id=application.id, kind="cover_letter", answer="Example letter")
    proposal = models.ApplicationProposal(job_id=job.id, application_id=application.id, status="accepted")
    version = models.ResumeVersion(resume_kind="application", resume_key=str(application.id),
                                   version_number=1, snapshot={**RESUME, "summary": "Saved older summary"}, source="create")
    db.add_all([qa, proposal, version])
    db.commit()
    return {"job": str(job.id), "app": str(application.id), "qa": str(qa.id), "prop": str(proposal.id)}


@pytest.fixture
def seeded(db_session, external_fakes):
    from app.services import auto_apply_settings, template_registry

    (settings.base_resumes_dir / "guard_base.json").write_text(json.dumps(RESUME))
    db_session.add(models.BaseResume(slug="guard_base", data_json=RESUME))
    db_session.commit()
    template_registry.ensure_seed_templates(db_session, validate=False)
    cfg = auto_apply_settings.get_settings(db_session)
    cfg.full_automation = True
    auto_apply_settings.set_settings(cfg, db_session)
    return _seed_children(db_session, _seed_job(db_session))


@pytest.fixture
def client(db_session):
    def override():
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise
    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


# Explicit Task 5 inventory; the design's separate inventory reference is absent.
WRITE_PATHS = [
    ("PATCH", "/api/jobs/{job}", {"source_url": "https://example.test/updated"}),
    ("POST", "/api/jobs/{job}/re-extract", None),
    ("POST", "/api/jobs/{job}/quick-tailor", {"base_resume": "guard_base"}),
    ("POST", "/api/applications/from-base", {"job_id": "{job}", "base_resume": "guard_base", "ops": OPS}),
    ("PATCH", "/api/applications/{app}/edits", {"ops": OPS}),
    ("POST", "/api/applications/{app}/render", None),
    ("POST", "/api/qa", {"application_id": "{app}", "questions": ["Example screening question"]}),
    ("PATCH", "/api/qa/{qa}", {"answer": "Updated letter"}),
    ("DELETE", "/api/qa/{qa}", None),
    ("POST", "/api/qa/{qa}/render", None),
    ("POST", "/api/jobs/{job}/filled-answers", {"channel": "agent", "fields": [{"question": "Example field", "answer": "Example answer", "source": "you"}]}),
    ("POST", "/api/ats-scores", {"job_id": "{job}", "target_type": "base_resume", "target_id": "guard_base"}),
    ("POST", "/api/tailoring-sessions", {"job_id": "{job}", "base_resume": "guard_base", "enrich": False}),
    ("POST", "/api/resume-versions/application/{app}/1/restore", None),
    ("POST", "/api/resume-lint/application/{app}/run", None),
    ("POST", "/api/resume-lint/application/{app}/gates/S1/waive", {"reason": "Example reason"}),
]


def _payload(value, ids):
    if isinstance(value, dict):
        return {key: _payload(item, ids) for key, item in value.items()}
    if isinstance(value, str):
        return value.format(**ids)
    return value


@pytest.mark.parametrize("case", WRITE_PATHS)
@pytest.mark.parametrize("enabled", [False, True], ids=["sync-off", "sync-on"])
def test_write_paths(client, seeded, enabled, case):
    method, path, payload = case
    if enabled:
        status.create_key()
    response = client.request(method, path.format(**seeded), json=_payload(payload, seeded))
    if enabled:
        assert response.status_code == 409, response.text
        assert response.json()["owner"] == "bot"
    else:
        assert response.status_code in (200, 201, 204), response.text


@pytest.mark.parametrize("enabled", [False, True])
def test_evidence_and_login(client, seeded, enabled, monkeypatch):
    from app.services import job_site_login

    monkeypatch.setattr(job_site_login, "read", lambda: ("example@example.test", "synthetic-password"))
    if enabled:
        status.create_key()
    before = set(settings.applications_dir.rglob("*"))
    evidence = client.post(f"/api/proposals/{seeded['prop']}/evidence",
                           files={"file": ("shot.png", b"synthetic image", "image/png")},
                           data={"step": "1", "label": "Example page", "kind": "step"})
    login = client.post(f"/api/proposals/{seeded['prop']}/job-site-login", headers={"X-Maestro-CS-Origin": "mcp"})
    assert evidence.status_code == (409 if enabled else 201), evidence.text
    assert login.status_code == (409 if enabled else 200)  # Never echo a login response.
    if enabled:
        assert set(settings.applications_dir.rglob("*")) == before
        assert login.json()["owner"] == "bot"


@pytest.mark.parametrize("enabled", [False, True])
def test_assistant_edit(db_session, seeded, enabled):
    from app.services.chat_tools import ToolContext, tool_edit_resume

    if enabled:
        status.create_key()
        with pytest.raises(hooks.NotOwnedHere):
            tool_edit_resume(ToolContext(db_session), "application", seeded["app"], OPS)
    else:
        result = tool_edit_resume(ToolContext(db_session), "application", seeded["app"], OPS)
        assert result["change_card"]["resume_kind"] == "application"


@pytest.mark.parametrize("method", ["PATCH", "DELETE", "POST"])
def test_refused_qa_keeps_pdf(client, seeded, tmp_path, db_session, method):
    pdf = tmp_path / "replica.pdf"
    pdf.write_bytes(b"replica pdf")
    row = db_session.get(models.QAEntry, uuid.UUID(seeded["qa"]))
    row.pdf_path = str(pdf)
    db_session.commit()
    status.create_key()
    path = f"/api/qa/{row.id}" + ("/render" if method == "POST" else "")
    response = client.request(method, path, json={"answer": "Updated"} if method == "PATCH" else None)
    assert response.status_code == 409
    assert pdf.read_bytes() == b"replica pdf"
    db_session.refresh(row)
    assert row.pdf_path == str(pdf)


@pytest.mark.parametrize("change", ["edit", "delete", "child", "move", "offered", "cancel-and-edit"])
def test_guard_blocks_flush(db_session, change):
    replica, owned = _seed_job(db_session), _seed_job(db_session, owner=None)
    child = models.Application(job_id=replica.id, base_resume="base")
    db_session.add(child)
    if change in ("offered", "cancel-and-edit"):
        replica.owner_machine, replica.handover = None, "offered"
    db_session.commit()
    status.create_key()
    if change == "delete":
        db_session.delete(replica)
    elif change == "child":
        db_session.add(models.QAEntry(application_id=child.id, kind="answer"))
    elif change == "move":
        child.job_id = owned.id
    else:
        replica.title = "Changed title"
        if change == "cancel-and-edit":
            replica.handover = None
    with pytest.raises(hooks.NotOwnedHere):
        db_session.flush()


def test_keep_here_only_and_sync_apply_pass(db_session):
    job = _seed_job(db_session, owner=None, handover="offered")
    db_session.commit()
    status.create_key()
    job.handover = None
    db_session.commit()
    job.owner_machine = "other-machine"
    db_session.info["sync_apply"] = True
    try:
        db_session.commit()
        job.title = "Imported title"
        db_session.commit()
    finally:
        db_session.info.pop("sync_apply", None)
    assert job.title == "Imported title"


@pytest.mark.parametrize("kind", ["application", "unknown"])
def test_unresolved_rows_fail_closed(db_session, kind):
    status.create_key()
    row = models.ResumeVersion(resume_kind=kind, resume_key=str(uuid.uuid4()),
                               version_number=1, snapshot={}, source="create")
    db_session.add(row)
    with pytest.raises(hooks.NotOwnedHere, match="couldn't tell") as error:
        db_session.flush()
    assert str(error.value) == UNRESOLVED_MESSAGE
    assert row in db_session.info["sync_unresolved"]


def test_close_and_reuse_clears_transaction_state(db_session):
    job = _seed_job(db_session)
    job_id = job.id
    db_session.commit()
    hooks.touch_job(db_session, job_id)
    hooks.touch_profile(db_session)
    db_session.info["sync_unresolved"] = [object()]
    db_session.info["sync_guard_additions"] = {object()}
    db_session.close()
    assert not any(key.startswith(("sync_touch_", "sync_guard_")) or key == "sync_unresolved"
                   for key in db_session.info)
    db_session.add(models.Setting(key="sync.reused", value="local"))
    db_session.commit()
    assert db_session.get(models.SyncState, "profile_rev") is None


def test_stale_proposal_read_skips_replicas(client, seeded, db_session):
    prop = db_session.get(models.ApplicationProposal, uuid.UUID(seeded["prop"]))
    prop.status, prop.expires_at = "pending_review", utcnow() - timedelta(days=1)
    db_session.commit()
    status.create_key()
    assert client.get("/api/proposals").status_code == 200
    db_session.refresh(prop)
    assert prop.status == "pending_review"


def test_eeo_withdrawal_only_clears_owned_jobs(db_session):
    from app.services import eeo_consent

    replica, owned = _seed_job(db_session), _seed_job(db_session, owner=None)
    rows = [models.FilledAnswer(job_id=job.id, channel="agent", fields=[
        {"question": "Example demographic field", "answer": "synthetic answer", "eeo": True}
    ]) for job in (replica, owned)]
    db_session.add_all(rows)
    db_session.commit()
    status.create_key()
    eeo_consent.set_consent(eeo_consent.EeoConsent(enabled=False), db_session)
    db_session.refresh(rows[0])
    db_session.refresh(rows[1])
    assert rows[0].fields[0]["answer"] == "synthetic answer"
    assert rows[1].fields[0]["answer"] is None


@pytest.mark.parametrize("change", ["insert", "update", "delete"])
def test_remote_profile_refused(db_session, seeded, change, monkeypatch):
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    base = db_session.get(models.BaseResume, "guard_base")
    if change == "insert":
        db_session.add(models.Setting(key="never_seeded", value="changed"))
    elif change == "delete":
        db_session.delete(base)
    else:
        base.display_name = "Changed name"
    with pytest.raises(hooks.NotOwnedHere) as error:
        db_session.flush()
    assert str(error.value) == PROFILE_MESSAGE


@pytest.mark.parametrize("existing_holder", [False, True])
def test_remote_cannot_confirm_queues_one_addition(db_session, seeded, existing_holder, monkeypatch):
    job = db_session.get(models.Job, uuid.UUID(seeded["job"]))
    job.owner_machine = None
    gap = {"gap_id": "skill:streaming", "kind": "skill", "jd_skill": "Stream processing",
           "actions": ["user_input", "cannot_confirm", "skip"]}
    tailoring = models.TailoringSession(job_id=job.id, base_resume="guard_base", status="open",
        gaps_json={"categories": [{"gaps": [gap]}]}, resolutions_json=[])
    db_session.add(tailoring)
    if existing_holder:
        tailoring_session._cannot_confirm_holder(db_session)
    db_session.commit()
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    for _ in range(2):
        tailoring_session.save_resolutions(tailoring.id, [
            {"gap_id": gap["gap_id"], "action": "cannot_confirm", "payload": {}}
        ], session=db_session)
    points = db_session.scalars(select(models.KBPoint)).all()
    requests = db_session.scalars(select(models.SyncRequest)).all()
    assert len(points) == len(requests) == 1
    assert points[0].provenance == "user_cannot_confirm"
    assert requests[0].kind == "profile_addition" and requests[0].origin == "local"
    assert requests[0].payload_json["claim"] == "Stream processing"
    assert requests[0].payload_json["holder"]["title"] == "Unconfirmed claims"


def test_remote_tailor_reports_profile_skip(client, seeded, db_session, monkeypatch):
    job = db_session.get(models.Job, uuid.UUID(seeded["job"]))
    job.owner_machine = None
    entity = models.KBEntity(kind="project", title="Example project")
    gap = {"gap_id": "skill:streaming", "kind": "skill", "jd_skill": "Stream processing"}
    tailoring = models.TailoringSession(job_id=job.id, base_resume="guard_base", status="open",
        gaps_json={"categories": [{"gaps": [gap]}]}, resolutions_json=[
            {"gap_id": gap["gap_id"], "action": "user_input", "payload": {
                "text": "Built stream processors that reduced event delay from nine seconds to two",
                "placement_target": {"section": "projects", "index_or_category": 0}}}])
    db_session.add_all([entity, tailoring])
    db_session.commit()
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    response = client.post(f"/api/tailoring-sessions/{tailoring.id}/tailor", json={"ops": OPS})
    assert response.status_code == 200, response.text
    skip = response.json()["kb_writeback_skips"][0]
    assert skip["reason"] == "profile_owned_elsewhere"
    assert skip["detail"] == "Your laptop keeps your career history, so this wasn't added to it here."
    assert not db_session.scalars(select(models.KBPoint)).all()


def test_remote_boot_and_lazy_defaults(db_session, external_fakes, monkeypatch, capfd):
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    capfd.readouterr()
    with TestClient(app) as booted:
        assert booted.get("/health").status_code == 200
        assert booted.get("/api/templates").status_code == 200
    # Logging during boot goes to stderr, which caplog does not see.
    output = capfd.readouterr()
    assert "eager refresh failed" not in output.err + output.out
    assert "NotOwnedHere" not in output.err + output.out
    assert db_session.get(models.Setting, "kb.seeded") is None
    # The boot flush seeds the empty profile but never commits it.
    assert db_session.get(models.KBProfile, 1) is None
    _check_lazy_defaults(db_session)


@pytest.mark.parametrize("row", [
    models.KBProfile(id=2),
    models.KBProfile(id=1, summary="Not empty"),
    models.KBProfile(id=1, notes="Not empty"),
    models.KBProfile(id=1, skills_json=[{"category": "Tools"}]),
    models.KBProfile(id=1, contact_json={"name": "Example"}),
    object(),
])
def test_seed_profile_refuses_anything_but_the_empty_singleton(db_session, row):
    status.create_key()
    with pytest.raises(ValueError):
        hooks.seed_profile(db_session, row)
    assert "sync_guard_profile_seed" not in db_session.info
    assert db_session.get(models.KBProfile, 1) is None


def test_seed_profile_accepts_the_empty_singleton(db_session):
    status.create_key()
    row = models.KBProfile(id=1)
    hooks.seed_profile(db_session, row)
    assert db_session.get(models.KBProfile, 1) is row
    assert "sync_guard_profile_seed" not in db_session.info


def _check_lazy_defaults(db_session):
    from app.services import prompts, text_settings

    assert text_settings.get_text("never_seeded", "example.md", db_session) == ""
    db_session.delete(db_session.get(models.Setting, "prompt.qa"))
    db_session.info["sync_apply"] = True
    try:
        db_session.commit()
    finally:
        db_session.info.pop("sync_apply", None)
    assert prompts.get_prompt("qa", db_session)
    assert "setting_seed" not in db_session.info and "sync_apply" not in db_session.info
    with pytest.raises(hooks.NotOwnedHere):
        text_settings.set_text("new_write", "new.md", "Changed", db_session)


# Audited Core sites must explicitly touch the affected subtree in that function.
CORE_ALLOWLIST = {
    ("routers/jobs.py", "re_extract_job", "JobSkill"): "touch_job",
    ("services/tailoring_session.py", "create_session", "TailoringSession"): "touch_job",
    ("services/template_registry.py", "set_default", "Template"): "touch_profile",
    ("services/career_kb.py", "merge_entities", "KBPoint"): "touch_profile",
    ("services/career_kb.py", "merge_entities", "KBDocument"): "touch_profile",
}


def _core_imports(tree):
    names, modules = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "sqlalchemy":
            names.update(alias.asname or alias.name for alias in node.names
                         if alias.name in ("update", "delete", "insert"))
        if isinstance(node, ast.Import):
            modules.update(alias.asname or alias.name for alias in node.names
                           if alias.name == "sqlalchemy")
    return names, modules


def _is_core_call(call, names, modules):
    function = call.func
    if isinstance(function, ast.Name):
        return function.id in names
    if not isinstance(function, ast.Attribute) or function.attr not in ("update", "delete", "insert"):
        return False
    receiver = function.value
    if isinstance(receiver, ast.Name):
        return receiver.id in modules
    return isinstance(receiver, ast.Attribute) and receiver.attr == "__table__"


def _core_calls(tree):
    names, modules = _core_imports(tree)
    return (node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and _is_core_call(node, names, modules))


def _enclosing_function(tree, call):
    functions = [node for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.lineno <= call.lineno <= node.end_lineno]
    return min(functions, key=lambda fn: fn.end_lineno - fn.lineno)


def _core_targets(call, function):
    if not call.args:  # MappedModel.__table__.update/delete/insert()
        return [ast.unparse(call.func.value.value)]
    target = ast.unparse(call.args[0])
    for node in ast.walk(function):
        if isinstance(node, ast.For) and ast.unparse(node.target) == target:
            if isinstance(node.iter, ast.Tuple):
                return [ast.unparse(item) for item in node.iter.elts]
    return [target]


def _audit_core_call(path, tree, call, classes):
    function = _enclosing_function(tree, call)
    for target in _core_targets(call, function):
        if classes.get(target) in (registry.LOCAL, registry.RUN_LOG, registry.SYNC):
            continue
        site = (path, function.name, target)
        assert site in CORE_ALLOWLIST, f"Unaudited Core write: {site}"
        touches = [node.lineno for node in ast.walk(function)
                   if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr == CORE_ALLOWLIST[site]]
        assert any(0 <= call.lineno - line <= 20 for line in touches), site
        yield site


def test_core_writers_have_explicit_touches():
    from app.db import Base

    namespace = ast.parse("import sqlalchemy as sa\nsa.update(Job)\nsa.delete(Job)\nsa.insert(Job)")
    assert len(list(_core_calls(namespace))) == 3
    app_dir = Path(hooks.__file__).resolve().parents[2]
    classes = {mapper.class_.__name__: registry.TABLES[mapper.local_table.name]
               for mapper in Base.registry.mappers}
    seen = set()
    for path in app_dir.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for call in _core_calls(tree):
            seen.update(_audit_core_call(str(path.relative_to(app_dir)), tree, call, classes))
    assert seen == set(CORE_ALLOWLIST)


PROFILE_PATHS = [
    ("POST", "/api/base-resumes", {"slug": "new_base", "data": RESUME}),
    ("PUT", "/api/base-resumes/guard_base", {"data": RESUME}),
    ("PATCH", "/api/base-resumes/guard_base/edits", {"ops": OPS}),
    ("POST", "/api/base-resumes/from-kb", {"slug": "new_base", "entity_ids": []}),
    ("POST", "/api/base-resumes/guard_base/duplicate", {"new_slug": "new_base"}),
    ("POST", "/api/base-resumes/guard_base/render", None),
    ("POST", "/api/resume-versions/base/guard_base/1/restore", None),
]


@pytest.mark.parametrize("case", PROFILE_PATHS)
def test_remote_profile_file_routes(client, seeded, db_session, monkeypatch, case):
    db_session.add(models.ResumeVersion(resume_kind="base", resume_key="guard_base",
        version_number=1, snapshot=RESUME, source="create"))
    db_session.commit()
    before = {str(path): path.read_bytes() for path in settings.base_resumes_dir.rglob("*") if path.is_file()}
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    method, path, payload = case
    response = client.request(method, path, json=payload)
    assert response.status_code == 409, response.text
    assert response.json() == {"detail": PROFILE_MESSAGE, "owner": "laptop"}
    assert {str(path): path.read_bytes() for path in settings.base_resumes_dir.rglob("*") if path.is_file()} == before


def test_remote_profile_uploads_leave_no_files(client, seeded, db_session, monkeypatch):
    entity = models.KBEntity(kind="project", title="Example project")
    db_session.add(entity)
    db_session.commit()
    entity_id = entity.id
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    response = client.post("/api/base-resumes/import", files={
        "file": ("resume.json", json.dumps(RESUME).encode(), "application/json")})
    document = client.post(f"/api/kb/entities/{entity_id}/documents", files={
        "file": ("example.txt", b"Example document", "text/plain")})
    assert response.status_code == document.status_code == 409
    assert not list(settings.kb_documents_dir.rglob("*"))
    assert not (settings.base_resumes_dir / "resume.json").exists()


def test_remote_base_row_cannot_move_into_job_scope(db_session, seeded, monkeypatch):
    db_session.get(models.Job, uuid.UUID(seeded["job"])).owner_machine = None
    row = models.ResumeVersion(resume_kind="base", resume_key="guard_base", version_number=1,
                               snapshot=RESUME, source="create")
    db_session.add(row)
    db_session.commit()
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    row.resume_kind, row.resume_key = "application", seeded["app"]
    with pytest.raises(hooks.NotOwnedHere):
        db_session.flush()


def test_lazy_seed_does_not_allow_an_unrelated_setting_insert(db_session, monkeypatch):
    from app.services import text_settings

    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    db_session.add(models.Setting(key="unrelated_write", value="Changed"))
    with pytest.raises(hooks.NotOwnedHere):
        text_settings.get_text("lazy_default", "default.md", db_session)
    assert "setting_seed" not in db_session.info


def test_remote_document_delete_keeps_files(client, seeded, db_session, monkeypatch):
    entity = models.KBEntity(kind="project", title="Example project")
    db_session.add(entity)
    db_session.flush()
    document = models.KBDocument(entity_id=entity.id, filename="example.txt")
    db_session.add(document)
    db_session.commit()
    document_id = document.id
    directory = settings.kb_documents_dir / str(document_id)
    directory.mkdir()
    artifact = directory / "example.txt"
    artifact.write_bytes(b"Example document")
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    response = client.delete(f"/api/kb/documents/{document_id}")
    assert response.status_code == 409
    assert artifact.is_file()
    assert artifact.read_bytes() == b"Example document"
    assert db_session.get(models.KBDocument, document_id) is not None


def test_remote_template_validation_keeps_preview(client, seeded, db_session, monkeypatch):
    from app.services import template_validation

    row = models.Template(id="guard_preview", source="Example source", engine="typst")
    db_session.add(row)
    db_session.commit()
    preview = template_validation._preview_path(row.id)
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"replica preview")

    def compile_sample(source, *, keep_pdf_at, **kwargs):
        keep_pdf_at.write_bytes(b"changed preview")
        return "Synthetic compiler failure"

    monkeypatch.setattr(template_validation, "compile_against_sample", compile_sample)
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    response = client.post(f"/api/templates/{row.id}/validate")
    assert response.status_code == 409
    assert preview.read_bytes() == b"replica preview"


def test_remote_set_default_refuses_before_core_write(db_session, monkeypatch):
    from app.services import template_registry

    current = models.Template(id="guard_current", source="Example source", status="ready", is_default=True)
    candidate = models.Template(id="guard_candidate", source="Example source", status="ready", is_default=False)
    db_session.add_all([current, candidate])
    db_session.commit()
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    with pytest.raises(hooks.NotOwnedHere):
        template_registry.set_default(db_session, candidate.id)
    assert db_session.scalar(select(models.Template.is_default).where(models.Template.id == current.id)) is True


def test_deleted_previous_application_can_be_repaired(db_session, seeded):
    old = db_session.get(models.Application, uuid.UUID(seeded["app"]))
    version = db_session.scalar(select(models.ResumeVersion).where(
        models.ResumeVersion.resume_key == str(old.id)))
    db_session.delete(old)
    db_session.commit()
    assert db_session.get(models.Application, old.id) is None
    owned = _seed_job(db_session, owner=None)
    replacement = models.Application(job_id=owned.id, base_resume="guard_base", customized_json=RESUME)
    db_session.add(replacement)
    db_session.commit()
    previous_rev = owned.sync_rev
    status.create_key()
    version.resume_key = str(replacement.id)
    db_session.commit()
    assert version.resume_key == str(replacement.id)
    assert owned.sync_rev > previous_rev
    assert not db_session.info.get("sync_unresolved")


def test_version_move_checks_resolvable_previous_job(db_session, seeded):
    version = db_session.scalar(select(models.ResumeVersion).where(
        models.ResumeVersion.resume_key == seeded["app"]))
    owned = _seed_job(db_session, owner=None)
    replacement = models.Application(job_id=owned.id, base_resume="guard_base", customized_json=RESUME)
    db_session.add(replacement)
    db_session.commit()
    status.create_key()
    version.resume_key = str(replacement.id)
    with pytest.raises(hooks.NotOwnedHere):
        db_session.flush()


@pytest.mark.parametrize("enabled", [False, True], ids=["sync-off", "sync-on"])
def test_template_formatting_preview_guard(client, db_session, monkeypatch, enabled):
    from app.services import template_validation

    row = models.Template(id="guard_formatting", source="Example source", engine="typst")
    db_session.add(row)
    db_session.commit()
    preview = template_validation._preview_path(row.id)
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"replica preview")

    def compile_sample(source, *, keep_pdf_at, **kwargs):
        keep_pdf_at.write_bytes(b"changed preview")
        return None

    monkeypatch.setattr(template_validation, "compile_against_sample", compile_sample)
    if enabled:
        status.create_key()
        monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    response = client.put(f"/api/templates/{row.id}/default-formatting",
                          json={"formatting": {"font_size": 12}})
    assert response.status_code == (409 if enabled else 200)
    assert preview.read_bytes() == (b"replica preview" if enabled else b"changed preview")


@pytest.mark.parametrize("enabled", [False, True], ids=["sync-off", "sync-on"])
def test_document_ingest_checks_before_llm_and_disk(client, db_session, monkeypatch, enabled):
    from app.services import llm, prompts

    prompts.get_prompt("kb_document_ingest", db_session)
    calls = []

    def ingest_llm(**kwargs):
        calls.append(True)
        return {"new_entity": {"kind": "project", "title": "Example project"}, "points": []}

    monkeypatch.setattr(llm, "call_openai", ingest_llm)
    if enabled:
        status.create_key()
        monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    response = client.post("/api/kb/documents/ingest", files={
        "file": ("example.txt", b"Example project description", "text/plain")})
    assert response.status_code == (409 if enabled else 200)
    assert calls == ([] if enabled else [True])
    files = [path for path in settings.kb_documents_dir.rglob("*") if path.is_file()]
    assert len(files) == (0 if enabled else 1)


PROFILE_READS = ["/api/kb/profile", "/api/kb/compose", "/api/kb/context", "/api/exports",
                 "/api/exports/career"]


def test_remote_first_read_seeds_the_empty_profile(client, seeded, db_session, monkeypatch):
    db_session.get(models.Job, uuid.UUID(seeded["job"])).owner_machine = None
    db_session.commit()
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    assert db_session.get(models.KBProfile, 1) is None
    for path in PROFILE_READS:
        assert client.get(path).status_code == 200, path
    created = client.post("/api/qa", json={"application_id": seeded["app"],
                                           "questions": ["Example screening question"]})
    assert created.status_code in (200, 201), created.text
    regenerated = client.post(f"/api/qa/{seeded['qa']}/regenerate")
    assert regenerated.status_code == 200, regenerated.text
    assert db_session.get(models.KBProfile, 1) is not None


def test_remote_profile_seed_opens_nothing_else(client, db_session, monkeypatch):
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    assert client.get("/api/kb/profile").status_code == 200
    assert "sync_guard_profile_seed" not in db_session.info
    response = client.patch("/api/kb/profile", json={"summary": "Changed"})
    assert response.status_code == 409 and response.json()["detail"] == PROFILE_MESSAGE
    db_session.rollback()
    assert db_session.get(models.KBProfile, 1).summary in (None, "")
    with pytest.raises(hooks.NotOwnedHere):
        db_session.add(models.KBProfile(id=2))
        db_session.flush()


def test_remote_patch_on_a_missing_profile_is_refused(client, db_session, monkeypatch):
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    response = client.patch("/api/kb/profile", json={"summary": "Changed"})
    assert response.status_code == 409
    db_session.rollback()
    profile = db_session.get(models.KBProfile, 1)
    assert profile is None or not profile.summary


@pytest.mark.parametrize("handover", ["offered", None])
def test_offered_job_message_points_at_keep_it_here(db_session, handover):
    job = _seed_job(db_session, owner=None if handover else "other-machine", handover=handover)
    db_session.commit()
    status.create_key()
    with pytest.raises(hooks.NotOwnedHere) as error:
        hooks.require_owned(db_session, job.id)
    if handover:
        assert str(error.value) == ("This job is on its way to your bot. "
                                    "Use Keep it here to keep working on it.")
    else:
        assert str(error.value) == ("This job is with your bot; "
                                    "ask for it back with Work on it here.")


def _compare_rows(db_session, job):
    from app.services import ats_score

    application = db_session.scalar(select(models.Application).where(
        models.Application.job_id == job.id))
    return application, ats_score


@pytest.mark.parametrize("owner", ["other-machine", None], ids=["replica", "owned"])
def test_ats_compare_is_a_read_on_a_replica(client, seeded, db_session, owner):
    job = db_session.get(models.Job, uuid.UUID(seeded["job"]))
    job.owner_machine = owner
    db_session.commit()
    status.create_key()
    response = client.get(f"/api/applications/{seeded['app']}/ats-compare")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) >= {"application_id", "base", "tailored", "delta", "skill_diff"}
    assert body["base"]["phase"] == "base" and body["tailored"]["phase"] == "tailored"
    rows = db_session.scalars(select(models.AtsScore)).all()
    assert len(rows) == (0 if owner else 2)


def test_remote_lint_skips_certification_quietly(db_session, monkeypatch, caplog):
    from app.services import resume_lint

    row = models.Template(id="guard_lint", source="Example source", engine="typst", status="ready")
    db_session.add(row)
    db_session.commit()
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    with caplog.at_level("DEBUG"):
        gates = resume_lint.structure_gates(db_session, row.id, RESUME)
    assert [gate["id"] for gate in gates][:1] == ["S1"] and gates[0]["status"] == "not_assessed"
    assert not [record for record in caplog.records if record.levelname in ("ERROR", "WARNING")]
    assert db_session.get(models.Template, row.id).parse_certified is None
