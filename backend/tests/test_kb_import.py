"""Slice 3: POST /api/kb/import — resumes become base resumes AND KB content.

The contract under test is RESUMABLE, not atomic. Minting a base is three
writes and two of them commit independently (the render helper commits
internally; get_prompt commits its file default on first use), and rolling back
would mean deleting rendered artifacts inside a live transaction — which
SYSTEM.md §6 forbids. So a mid-batch failure must leave every already-minted
base valid, never a row without its disk file.
"""

import io
import json

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.base_resume import BaseResume
from app.models.setting import Setting
from app.services import kb_import, seeding

RESUME = {
    "contact": {"name": "Jordan Sample", "email": "jordan@example.com"},
    "summary": "Data scientist.",
    "skills": [{"category": "Core", "items": ["Python"]}],
    "experience": [
        {
            "company": "Acme",
            "role": "Senior Data Scientist",
            "start_date": "2021-03",
            "bullets": ["Built models."],
        }
    ],
    "projects": [],
    "education": [],
    "certifications": [],
}


def _client(db_session) -> TestClient:
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def _stub_pipeline(monkeypatch, tmp_path):
    """No LLM, no pdflatex — this suite tests the import contract, not either."""
    monkeypatch.setattr(kb_import.base_resume_data.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(kb_import.kb_consolidation, "prefetch_prompts", lambda s: None)
    monkeypatch.setattr(
        kb_import.base_resume_render, "render_base_resume", lambda slug, db, **kw: None
    )
    from app.schemas.career_kb import ConsolidationReport

    seen: list[list[str]] = []

    def fake_consolidate(session, sources, **kw):
        seen.append([key for key, _ in sources])
        return ConsolidationReport(entities_created=len(sources), points_approved=3)

    monkeypatch.setattr(kb_import.kb_consolidation, "consolidate", fake_consolidate)
    return seen


def _json_upload(name: str, payload=None):
    return ("files", (name, io.BytesIO(json.dumps(payload or RESUME).encode()), "application/json"))


# --- the headline behaviour ----------------------------------------------

def test_import_mints_a_base_and_feeds_the_kb(db_session, tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch, tmp_path)
    body = _client(db_session).post(
        "/api/kb/import", files=[_json_upload("my_resume.json")]
    ).json()

    assert [b["slug"] for b in body["bases"]] == ["my_resume"]
    assert body["kb"]["entities_created"] == 1
    # BOTH happened from one action — the disclosure the UI must make.
    assert db_session.get(BaseResume, "my_resume") is not None
    assert (tmp_path / "my_resume.json").exists()


def test_json_upload_needs_no_llm(db_session, tmp_path, monkeypatch):
    """The README's own file-drop format must not 400.

    attachment_extract has no application/json handler, so without a
    short-circuit a user following the documented format is rejected.
    """
    _stub_pipeline(monkeypatch, tmp_path)

    def explode(*a, **kw):  # any LLM/extraction call is a failure here
        raise AssertionError("json upload must not reach the parser")

    monkeypatch.setattr(kb_import, "extract_text", explode)
    monkeypatch.setattr(kb_import.kb_consolidation, "parse_resume_text", explode)

    resp = _client(db_session).post("/api/kb/import", files=[_json_upload("plain.json")])
    assert resp.status_code == 200


def test_consolidation_source_key_is_the_slug_not_the_filename(db_session, tmp_path, monkeypatch):
    """KBPortLog.resume_key and merge_sources_json store this; everywhere else it
    is a slug, so a filename there points at nothing."""
    seen = _stub_pipeline(monkeypatch, tmp_path)
    _client(db_session).post(
        "/api/kb/import", files=[_json_upload("Resume final v3.json")]
    )
    assert seen == [["resume_final_v3"]]


# --- partial success, not rollback ---------------------------------------

def test_one_bad_file_does_not_fail_the_batch(db_session, tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch, tmp_path)
    bad = ("files", ("broken.json", io.BytesIO(b"{not json"), "application/json"))
    body = _client(db_session).post(
        "/api/kb/import", files=[_json_upload("good.json"), bad]
    ).json()

    assert [b["slug"] for b in body["bases"]] == ["good"]
    assert [s["filename"] for s in body["skipped"]] == ["broken.json"]
    assert db_session.get(BaseResume, "good") is not None


def test_render_failure_keeps_the_base(db_session, tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch, tmp_path)

    def boom(slug, db, **kw):
        raise RuntimeError("pdflatex exited 1")

    monkeypatch.setattr(kb_import.base_resume_render, "render_base_resume", boom)
    body = _client(db_session).post(
        "/api/kb/import", files=[_json_upload("rendered.json")]
    ).json()

    assert body["bases"][0]["slug"] == "rendered"
    assert "pdflatex" in body["bases"][0]["render_error"]
    assert db_session.get(BaseResume, "rendered") is not None  # survived


def test_no_row_without_its_disk_file(db_session, tmp_path, monkeypatch):
    """The invariant that replaces atomicity."""
    _stub_pipeline(monkeypatch, tmp_path)
    _client(db_session).post(
        "/api/kb/import", files=[_json_upload("a.json"), _json_upload("b.json")]
    )
    for slug in ("a", "b"):
        assert db_session.get(BaseResume, slug) is not None
        assert (tmp_path / f"{slug}.json").exists()


def test_all_files_bad_is_422_not_a_silent_200(db_session, tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch, tmp_path)
    bad = ("files", ("x.json", io.BytesIO(b"nope"), "application/json"))
    assert _client(db_session).post("/api/kb/import", files=[bad]).status_code == 422


# --- slug collisions ------------------------------------------------------

def test_slug_collision_appends_instead_of_409(db_session, tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch, tmp_path)
    db_session.add(BaseResume(slug="taken", data_json=RESUME, role_category="unknown"))
    db_session.commit()
    body = _client(db_session).post(
        "/api/kb/import", files=[_json_upload("taken.json")]
    ).json()
    assert body["bases"][0]["slug"] == "taken_2"


def test_soft_deleted_slug_does_not_block_import(db_session, tmp_path, monkeypatch):
    """REST create 409s permanently on a soft-deleted slug; import must not."""
    from datetime import UTC, datetime

    _stub_pipeline(monkeypatch, tmp_path)
    db_session.add(
        BaseResume(
            slug="gone", data_json=RESUME, role_category="unknown",
            deleted_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    body = _client(db_session).post("/api/kb/import", files=[_json_upload("gone.json")]).json()
    assert body["bases"][0]["slug"] == "gone_2"


# --- role proposal --------------------------------------------------------

def test_unambiguous_role_is_proposed_and_flagged_for_confirmation(db_session, tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch, tmp_path)
    body = _client(db_session).post("/api/kb/import", files=[_json_upload("ds.json")]).json()
    assert body["bases"][0]["role_category"] == "data_scientist"
    assert body["bases"][0]["proposed"] is True  # UI must ask


def test_ambiguous_role_stays_unknown_and_is_not_a_proposal(db_session, tmp_path, monkeypatch):
    """"data engineer" sits in two families — never tie-break on YAML order."""
    _stub_pipeline(monkeypatch, tmp_path)
    doc = json.loads(json.dumps(RESUME))
    doc["experience"][0]["role"] = "Data Engineer"
    body = _client(db_session).post(
        "/api/kb/import", files=[_json_upload("de.json", doc)]
    ).json()
    assert body["bases"][0]["role_category"] == "unknown"
    assert body["bases"][0]["proposed"] is False


# --- the kb.seeded flag ---------------------------------------------------

def test_import_sets_kb_seeded(db_session, tmp_path, monkeypatch):
    """Otherwise the next restart re-consolidates what was just imported."""
    _stub_pipeline(monkeypatch, tmp_path)
    assert db_session.get(Setting, kb_import.KB_SEEDED_FLAG) is None
    _client(db_session).post("/api/kb/import", files=[_json_upload("seed.json")])
    assert db_session.get(Setting, kb_import.KB_SEEDED_FLAG).value == "1"


# --- the demo resume must not become the user's identity ------------------

def test_demo_resume_is_excluded_from_the_kb_seed(db_session, tmp_path, monkeypatch):
    """A3: `_seed_profile` is non-clobbering, so seeding `example` would make the
    demo person the user's permanent KBProfile contact."""
    monkeypatch.setattr(seeding.settings, "base_resumes_dir", tmp_path)
    db_session.add(BaseResume(slug=seeding.DEMO_SLUG, data_json=RESUME, role_category="unknown"))
    db_session.commit()

    captured: list[list[str]] = []
    monkeypatch.setattr(
        seeding.kb_consolidation, "consolidate",
        lambda s, sources, **kw: captured.append([k for k, _ in sources]),
    )
    seeding.seed_career_kb(db_session)

    assert captured == [] or seeding.DEMO_SLUG not in (captured[0] if captured else [])
