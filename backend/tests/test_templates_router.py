import os
import shutil

import pytest
from app.db import get_db
from app.main import app
from fastapi.testclient import TestClient

_HAS_LATEX = shutil.which("pdflatex") is not None


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def test_list_seeds_default(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).get("/api/templates")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert "default" in ids


def test_list_templates_exposes_updated_at(db_session):
    """The gallery marks a thumbnail stale when the source changed after the
    last validation, so the list must carry both timestamps."""
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).get("/api/templates")
    finally:
        app.dependency_overrides.clear()
    body = r.json()
    assert body, "expected at least the seeded templates"
    assert "updated_at" in body[0]
    assert "validated_at" in body[0]


def test_create_draft_and_get(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        cr = c.post("/api/templates", json={"id": "minimal", "display_name": "Minimal", "source": "X"})
        assert cr.status_code == 200
        body = cr.json()
        assert body["status"] == "draft"
        assert body["origin"] == "frontend"
        assert body["is_default"] is False
        g = c.get("/api/templates/minimal")
        assert g.status_code == 200
        assert g.json()["source"] == "X"
    finally:
        app.dependency_overrides.clear()


def test_engine_in_responses_and_typst_create(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        cr = c.post("/api/templates", json={"id": "lat", "display_name": "L", "source": "X"})
        assert cr.status_code == 200 and cr.json()["engine"] == "latex"
        ct = c.post(
            "/api/templates",
            json={"id": "typ", "display_name": "T", "source": "#x", "engine": "typst"},
        )
        assert ct.status_code == 200 and ct.json()["engine"] == "typst"
        assert c.get("/api/templates/typ").json()["engine"] == "typst"
    finally:
        app.dependency_overrides.clear()


def test_typst_create_without_source_rejected(db_session):
    # Phase 1: STARTER_SOURCE stays LaTeX — it cannot seed a typst draft.
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/templates", json={"id": "typ2", "display_name": "T", "engine": "typst"}
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 422


def test_engine_immutable_after_creation(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.post("/api/templates", json={"id": "imm", "display_name": "I", "source": "X"})
        bad = c.put("/api/templates/imm", json={"engine": "typst"})
        same = c.put("/api/templates/imm", json={"engine": "latex", "display_name": "I2"})
    finally:
        app.dependency_overrides.clear()
    assert bad.status_code == 400
    assert same.status_code == 200  # same-value no-op is allowed


def test_create_without_source_uses_starter(db_session):
    from app.services import template_registry as reg

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        cr = c.post("/api/templates", json={"id": "fresh", "display_name": "Fresh"})
        assert cr.status_code == 200
        assert cr.json()["source"] == reg.STARTER_SOURCE
        assert cr.json()["status"] == "draft"
    finally:
        app.dependency_overrides.clear()


def test_update_with_validate_flag_runs_validation(db_session, monkeypatch):
    from app.routers import templates as templates_router

    calls = {}

    def fake_validate(template_id, session):
        calls["id"] = template_id
        return {"ok": True, "error": None}

    monkeypatch.setattr(templates_router.tv, "validate_template", fake_validate)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.post("/api/templates", json={"id": "vt", "display_name": "VT", "source": "X"})
        saved = c.put("/api/templates/vt?validate=true", json={"source": "Y"})
        saved_plain = c.put("/api/templates/vt", json={"source": "Z"})
    finally:
        app.dependency_overrides.clear()

    assert saved.status_code == 200
    assert calls["id"] == "vt"
    assert saved_plain.status_code == 200
    # Without the flag the row simply stays a draft; validation ran only once.
    assert saved_plain.json()["status"] == "draft"


def test_create_duplicate_conflicts(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.post("/api/templates", json={"id": "dup", "display_name": "D", "source": "X"})
        again = c.post("/api/templates", json={"id": "dup", "display_name": "D", "source": "Y"})
        assert again.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_get_unknown_404(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).get("/api/templates/nope")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 404


def test_update_resets_to_draft_and_default_guard(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.get("/api/templates")  # seed default (status ready)
        # editing the default without the flag is forbidden
        forbidden = c.put("/api/templates/default", json={"source": "Y"})
        assert forbidden.status_code == 403
        # with the flag it's allowed and resets to draft
        ok = c.put("/api/templates/default?allow_default_edit=true", json={"source": "Y"})
        assert ok.status_code == 200
        assert ok.json()["status"] == "draft"
    finally:
        app.dependency_overrides.clear()


def test_update_unknown_404(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).put("/api/templates/nope", json={"display_name": "X"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 404


def test_create_rejects_bad_id(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        for bad in ["../etc", "Has Space", "UPPER", "dir/sub", ""]:
            r = c.post("/api/templates", json={"id": bad, "display_name": "X", "source": "Y"})
            assert r.status_code == 422, f"{bad!r} should be rejected"
    finally:
        app.dependency_overrides.clear()


def test_set_default_requires_ready(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.get("/api/templates")  # seed default
        c.post("/api/templates", json={"id": "t2", "display_name": "T2", "source": "X"})
        assert c.post("/api/templates/t2/set-default").status_code == 400  # draft can't be default
    finally:
        app.dependency_overrides.clear()


def test_delete_refuses_default(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.get("/api/templates")
        assert c.delete("/api/templates/default").status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_delete_removes_nondefault(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.post("/api/templates", json={"id": "gone", "display_name": "G", "source": "X"})
        assert c.delete("/api/templates/gone").status_code == 204
        assert c.get("/api/templates/gone").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_validate_unknown_404(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        assert TestClient(app).post("/api/templates/nope/validate").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_preview_requires_ready(db_session):
    # a draft (never validated) has no ready preview -> 404
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.post("/api/templates", json={"id": "d", "display_name": "D", "source": "X"})
        assert c.get("/api/templates/d/preview.pdf").status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not _HAS_LATEX, reason="pdflatex not installed")
def test_validate_then_preview_and_set_default(db_session, tmp_path, monkeypatch):
    import app.services.pdf_render as pr
    import app.services.template_validation as tv
    monkeypatch.setattr(tv.settings, "base_resumes_dir", tmp_path)
    src = (pr.TEMPLATE_DIR / pr.RESUME_TEMPLATE).read_text(encoding="utf-8")
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.get("/api/templates")  # seed default
        c.post("/api/templates", json={"id": "g", "display_name": "G", "source": src})
        v = c.post("/api/templates/g/validate")
        assert v.status_code == 200 and v.json()["ok"] is True
        p = c.get("/api/templates/g/preview.pdf")
        assert p.status_code == 200
        assert p.headers["content-type"] == "application/pdf"
        # now g is ready -> can become default
        sd = c.post("/api/templates/g/set-default")
        assert sd.status_code == 200
        assert sd.json()["is_default"] is True
    finally:
        app.dependency_overrides.clear()


def test_supported_fmt_keys_default_and_starter(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        # the seeded Classic default parameterizes fmt.* -> keys are detected
        lst = c.get("/api/templates")
        assert lst.status_code == 200
        default_row = next(t for t in lst.json() if t["id"] == "default")
        keys = set(default_row["supported_fmt_keys"])
        assert {"font_size", "side_margins"}.issubset(keys)
        # header_align is referenced only in the included _header.tex.j2 partial;
        # supported_fmt_keys must follow includes or the panel greys the control.
        assert "header_align" in keys
        # GET one exposes the same list
        one = c.get("/api/templates/default")
        assert {"font_size", "side_margins"}.issubset(set(one.json()["supported_fmt_keys"]))
        # a plain starter-source draft opts into nothing
        c.post("/api/templates", json={"id": "starter", "display_name": "S"})
        draft = c.get("/api/templates/starter")
        assert draft.status_code == 200
        assert draft.json()["supported_fmt_keys"] == []
    finally:
        app.dependency_overrides.clear()


def test_mutating_responses_include_engine_aware_supported_fmt_keys(db_session):
    from app.services import template_registry as reg

    source = "#set text(size: fmt.font_size * 1pt)\n// fmt.header_align\n"
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        created = c.post(
            "/api/templates",
            json={
                "id": "fmt-response",
                "display_name": "Formatting response",
                "source": source,
                "engine": "typst",
            },
        )
        assert created.status_code == 200
        assert created.json()["supported_fmt_keys"] == ["date_format", "font_size"]

        updated = c.put("/api/templates/fmt-response", json={"source": source})
        assert updated.status_code == 200
        assert updated.json()["supported_fmt_keys"] == ["date_format", "font_size"]

        row = reg.get(db_session, "fmt-response")
        row.status = "ready"
        db_session.commit()
        made_default = c.post("/api/templates/fmt-response/set-default")
        assert made_default.status_code == 200
        assert made_default.json()["supported_fmt_keys"] == ["date_format", "font_size"]
    finally:
        app.dependency_overrides.clear()


def test_default_formatting_round_trip(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.post("/api/templates", json={"id": "df", "display_name": "DF", "source": "X"})
        # a fresh draft has no default_formatting
        assert c.get("/api/templates/df").json()["default_formatting"] is None
        # PUT persists a partial override without resetting status
        put = c.put(
            "/api/templates/df/default-formatting",
            json={"formatting": {"font_size": 12, "header_align": "left"}},
        )
        assert put.status_code == 200
        assert put.json()["default_formatting"] == {"font_size": 12, "header_align": "left"}
        assert put.json()["status"] == "draft"  # unchanged
        # round-trips on GET detail and list summary
        assert c.get("/api/templates/df").json()["default_formatting"] == {
            "font_size": 12,
            "header_align": "left",
        }
        row = next(t for t in c.get("/api/templates").json() if t["id"] == "df")
        assert row["default_formatting"] == {"font_size": 12, "header_align": "left"}
        # clearing back to null
        clr = c.put("/api/templates/df/default-formatting", json={"formatting": None})
        assert clr.status_code == 200
        assert clr.json()["default_formatting"] is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not _HAS_LATEX, reason="pdflatex not installed")
def test_default_formatting_refreshes_preview(db_session, tmp_path, monkeypatch):
    pytest.importorskip("pdfplumber")
    import app.services.template_validation as tv

    monkeypatch.setattr(tv.settings, "base_resumes_dir", tmp_path)
    src = (
        r"\documentclass{article}\begin{document}"
        r"FONTSIZE((( fmt.font_size )))MARK\end{document}"
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.post("/api/templates", json={"id": "rp", "display_name": "RP", "source": src})
        v = c.post("/api/templates/rp/validate")
        assert v.status_code == 200 and v.json()["ok"] is True

        # PUT default-formatting must persist AND re-render the stored preview so
        # it reflects the new defaults (font_size 12), with no source-endpoint
        # recompile and status left ready.
        put = c.put(
            "/api/templates/rp/default-formatting",
            json={"formatting": {"font_size": 12}},
        )
        assert put.status_code == 200
        assert put.json()["default_formatting"] == {"font_size": 12}
        assert put.json()["status"] == "ready"  # status untouched
        # Successful preview refresh stamps validated_at so the gallery does
        # not show "needs re-validation" for a formatting-only edit.
        from datetime import datetime

        detail = c.get("/api/templates/rp").json()
        assert detail["validated_at"] is not None
        validated = datetime.fromisoformat(detail["validated_at"].replace("Z", "+00:00"))
        updated = datetime.fromisoformat(detail["updated_at"].replace("Z", "+00:00"))
        # validated_at must not lag updated_at by more than the gallery's 1s slack
        assert (updated - validated).total_seconds() <= 1.0

        import pdfplumber

        with pdfplumber.open(tv._preview_path("rp")) as doc:
            text = " ".join((page.extract_text() or "") for page in doc.pages)
        normalized = " ".join(text.split())
        assert "FONTSIZE12MARK" in normalized
    finally:
        app.dependency_overrides.clear()


def test_default_formatting_refresh_passes_row_engine(db_session, monkeypatch):
    from app.routers import templates as tr

    seen = {}

    def fake_compile(source, keep_pdf_at=None, default_formatting=None, engine="latex"):
        seen["engine"] = engine
        return None

    monkeypatch.setattr(tr.tv, "compile_against_sample", fake_compile)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.post("/api/templates", json={"id": "te", "display_name": "TE", "source": "#x", "engine": "typst"})
        r = c.put("/api/templates/te/default-formatting", json={"formatting": {"font_size": 12}})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert seen["engine"] == "typst"


def test_default_formatting_invalid_rejected(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.post("/api/templates", json={"id": "dfx", "display_name": "DFX", "source": "X"})
        r = c.put(
            "/api/templates/dfx/default-formatting",
            json={"formatting": {"font_size": 99}},
        )
        assert r.status_code == 400
        # unknown key also rejected
        r2 = c.put(
            "/api/templates/dfx/default-formatting",
            json={"formatting": {"bogus_key": 1}},
        )
        assert r2.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_default_formatting_unknown_template_404(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).put(
            "/api/templates/nope/default-formatting", json={"formatting": None}
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_preview_pages_404_before_validate(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.post("/api/templates", json={"id": "pp", "display_name": "PP", "source": "X"})
        assert c.get("/api/templates/pp/preview/pages").status_code == 404
        assert c.get("/api/templates/pp/preview/page/1").status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(not _HAS_LATEX, reason="pdflatex not installed")
def test_preview_pages_after_validate(db_session, tmp_path, monkeypatch):
    import app.services.pdf_render as pr
    import app.services.template_validation as tv
    monkeypatch.setattr(tv.settings, "base_resumes_dir", tmp_path)
    src = (pr.TEMPLATE_DIR / pr.RESUME_TEMPLATE).read_text(encoding="utf-8")
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        c = TestClient(app)
        c.get("/api/templates")  # seed default
        c.post("/api/templates", json={"id": "pg", "display_name": "PG", "source": src})
        v = c.post("/api/templates/pg/validate")
        assert v.status_code == 200 and v.json()["ok"] is True
        preview = tv._preview_path("pg")
        os.utime(preview, (1_700_000_000, 1_700_000_000))
        man = c.get("/api/templates/pg/preview/pages")
        assert man.status_code == 200
        assert man.json()["page_count"] >= 1
        assert man.json()["rendered_at"] == "2023-11-14T22:13:20+00:00"
        img = c.get("/api/templates/pg/preview/page/1")
        assert img.status_code == 200
        assert img.headers["content-type"] == "image/png"
    finally:
        app.dependency_overrides.clear()
