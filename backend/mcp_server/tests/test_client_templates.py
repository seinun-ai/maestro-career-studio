import json as _json
from pathlib import Path

import httpx
import respx

from mcp_server.client import BackendClient

BASE = "http://test-backend"


@respx.mock
def test_list_and_get_templates():
    respx.get(f"{BASE}/api/templates").mock(return_value=httpx.Response(200, json=[{"id": "default"}]))
    respx.get(f"{BASE}/api/templates/x").mock(return_value=httpx.Response(200, json={"id": "x", "source": "S"}))
    c = BackendClient(BASE)
    assert c.list_templates() == [{"id": "default"}]
    assert c.get_template("x")["source"] == "S"


@respx.mock
def test_create_template_draft_sends_origin_mcp():
    route = respx.post(f"{BASE}/api/templates").mock(return_value=httpx.Response(200, json={"id": "x", "status": "draft"}))
    c = BackendClient(BASE)
    out = c.create_template_draft("x", "X disp", "SRC")
    assert out["status"] == "draft"
    assert _json.loads(route.calls.last.request.read()) == {
        "id": "x", "display_name": "X disp", "source": "SRC", "origin": "mcp",
        "engine": "latex",
    }


@respx.mock
def test_create_template_draft_passes_engine():
    route = respx.post(f"{BASE}/api/templates").mock(
        return_value=httpx.Response(200, json={"id": "t", "status": "draft", "engine": "typst"})
    )
    c = BackendClient(BASE)
    c.create_template_draft("t", "T", "#let r = json(bytes(sys.inputs.resume))", engine="typst")
    assert _json.loads(route.calls.last.request.read())["engine"] == "typst"


@respx.mock
def test_update_template_draft_no_default_flag():
    route = respx.put(f"{BASE}/api/templates/x").mock(return_value=httpx.Response(200, json={"id": "x"}))
    c = BackendClient(BASE)
    c.update_template_draft("x", source="Y", display_name="N")
    # must NOT send allow_default_edit (so backend rejects editing the default)
    assert "allow_default_edit" not in route.calls.last.request.url.params
    assert _json.loads(route.calls.last.request.read()) == {"source": "Y", "display_name": "N"}


@respx.mock
def test_update_template_draft_omits_none():
    route = respx.put(f"{BASE}/api/templates/x").mock(return_value=httpx.Response(200, json={"id": "x"}))
    c = BackendClient(BASE)
    c.update_template_draft("x", source="Y")
    assert _json.loads(route.calls.last.request.read()) == {"source": "Y"}


@respx.mock
def test_validate_template():
    respx.post(f"{BASE}/api/templates/x/validate").mock(return_value=httpx.Response(200, json={"ok": True, "error": None}))
    assert BackendClient(BASE).validate_template("x")["ok"] is True


@respx.mock
def test_render_base_resume_passes_template_id():
    route = respx.post(f"{BASE}/api/base-resumes/master/render").mock(return_value=httpx.Response(200, json={"slug": "master"}))
    BackendClient(BASE).render_base_resume("master", template_id="modern")
    assert route.calls.last.request.url.params["template_id"] == "modern"


@respx.mock
def test_render_base_resume_no_template_id_omits_param():
    route = respx.post(f"{BASE}/api/base-resumes/master/render").mock(return_value=httpx.Response(200, json={"slug": "master"}))
    BackendClient(BASE).render_base_resume("master")
    assert "template_id" not in route.calls.last.request.url.params


@respx.mock
def test_render_application_passes_template_id():
    route = respx.post(f"{BASE}/api/applications/a1/render").mock(return_value=httpx.Response(200, json={"id": "a1"}))
    BackendClient(BASE).render_application("a1", template_id="modern")
    assert route.calls.last.request.url.params["template_id"] == "modern"


@respx.mock
def test_get_rendered_pdf_base_resume_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    pdf = b"%PDF-1.4 fake-bytes"
    respx.get(f"{BASE}/api/base-resumes/master/pdf").mock(
        return_value=httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})
    )
    out = BackendClient(BASE).get_rendered_pdf("base_resume", "master")
    assert out["filename"] == "master.pdf"
    assert out["mime_type"] == "application/pdf"
    assert out["size_bytes"] == len(pdf)
    assert "base64" not in out  # no oversized inline payload
    from pathlib import Path

    assert Path(out["path"]).read_bytes() == pdf
    assert Path(out["path"]).parent == tmp_path


@respx.mock
def test_get_rendered_pdf_template_preview_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    pdf = b"%PDF-preview"
    respx.get(f"{BASE}/api/templates/modern/preview.pdf").mock(
        return_value=httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})
    )
    out = BackendClient(BASE).get_rendered_pdf("template", "modern")
    from pathlib import Path

    assert Path(out["path"]).read_bytes() == pdf


@respx.mock
def test_get_rendered_pdf_application_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    pdf = b"%PDF-app"
    respx.get(f"{BASE}/api/applications/a1/pdf").mock(
        return_value=httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})
    )
    respx.get(f"{BASE}/api/applications/a1").mock(
        return_value=httpx.Response(200, json={"id": "a1", "artifact_dir": None})
    )
    out = BackendClient(BASE).get_rendered_pdf("application", "a1")
    from pathlib import Path

    assert Path(out["path"]).read_bytes() == pdf
    assert "artifact_dir" not in out


def test_get_rendered_pdf_bad_target():
    import pytest
    from mcp_server.client import BackendError
    with pytest.raises(BackendError):
        BackendClient(BASE).get_rendered_pdf("nonsense", "x")


@respx.mock
def test_get_rendered_pdf_404_maps_error():
    import pytest
    from mcp_server.client import BackendError
    respx.get(f"{BASE}/api/base-resumes/missing/pdf").mock(return_value=httpx.Response(404, json={"detail": "PDF not found"}))
    with pytest.raises(BackendError) as exc:
        BackendClient(BASE).get_rendered_pdf("base_resume", "missing")
    assert exc.value.status_code == 404


def _make_pdf(path, texts):
    """Write a real PDF, one page per string in `texts`.

    Built with typst (already a runtime dep) rather than PyMuPDF, which is
    AGPL-3.0 and no longer used anywhere in this project. Non-ASCII punctuation
    (e.g. an em dash) round-trips through text extraction.
    """
    from tests.pdf_fixtures import multipage_text_pdf_bytes

    Path(path).write_bytes(multipage_text_pdf_bytes(list(texts)))


@respx.mock
def test_get_rendered_pdf_real_pdf_renders_png_and_page_count(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    src = tmp_path / "src.pdf"
    _make_pdf(src, ["Clean resume body with an en dash 2020 – 2024 range"])
    respx.get(f"{BASE}/api/base-resumes/master/pdf").mock(
        return_value=httpx.Response(200, content=src.read_bytes(),
                                    headers={"content-type": "application/pdf"})
    )
    out = BackendClient(BASE).get_rendered_pdf("base_resume", "master")
    from pathlib import Path

    assert out["page_count"] == 1
    assert len(out["page_images"]) == 1
    png = Path(out["page_images"][0])
    assert png.is_absolute() and png.exists()
    assert png.name == "master.p1.png"
    assert png.suffix == ".png" and png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert out["em_dash_found"] is False
    assert "page_images_b64" not in out
    # original keys preserved
    assert out["filename"] == "master.pdf" and out["mime_type"] == "application/pdf"


@respx.mock
def test_get_rendered_pdf_flags_em_dash(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    src = tmp_path / "src.pdf"
    _make_pdf(src, ["Led a team — delivered results"])  # U+2014 em dash
    respx.get(f"{BASE}/api/base-resumes/master/pdf").mock(
        return_value=httpx.Response(200, content=src.read_bytes(),
                                    headers={"content-type": "application/pdf"})
    )
    out = BackendClient(BASE).get_rendered_pdf("base_resume", "master")
    assert out["em_dash_found"] is True
    assert out["em_dash_pages"] == [1]


@respx.mock
def test_get_rendered_pdf_multipage_one_png_per_page(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    src = tmp_path / "src.pdf"
    _make_pdf(src, ["Page one body", "Page two — has em dash"])
    respx.get(f"{BASE}/api/applications/a1/pdf").mock(
        return_value=httpx.Response(200, content=src.read_bytes(),
                                    headers={"content-type": "application/pdf"})
    )
    respx.get(f"{BASE}/api/applications/a1").mock(
        return_value=httpx.Response(
            200, json={"id": "a1", "artifact_dir": "/apps/Acme_Role_20260730_a1b2c3d4"}
        )
    )
    out = BackendClient(BASE).get_rendered_pdf("application", "a1")
    from pathlib import Path

    assert out["page_count"] == 2
    assert [Path(p).name for p in out["page_images"]] == ["a1.p1.png", "a1.p2.png"]
    assert out["em_dash_pages"] == [2]
    assert "page_images_b64" not in out
    assert out["artifact_dir"] == "/apps/Acme_Role_20260730_a1b2c3d4"


@respx.mock
def test_get_rendered_pdf_bad_pdf_degrades_gracefully(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    pdf = b"%PDF-1.4 fake-bytes"  # not a real PDF; pdfium raises PdfiumError
    respx.get(f"{BASE}/api/base-resumes/master/pdf").mock(
        return_value=httpx.Response(200, content=pdf,
                                    headers={"content-type": "application/pdf"})
    )
    out = BackendClient(BASE).get_rendered_pdf("base_resume", "master")
    from pathlib import Path

    # PDF still saved + base keys intact
    assert Path(out["path"]).read_bytes() == pdf
    assert out["size_bytes"] == len(pdf)
    # preview fields degrade, do not raise
    assert out["page_count"] is None
    assert out["page_images"] == []
    assert "page_images_b64" not in out
    assert out["em_dash_found"] is False
    assert out["em_dash_pages"] == []


@respx.mock
def test_get_rendered_pdf_cleans_up_stale_page_pngs(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    # A prior render of the same id produced a 3rd page; that PNG is now orphaned.
    stale = tmp_path / "master.p3.png"
    stale.write_bytes(b"\x89PNG\r\n\x1a\n stale")
    src = tmp_path / "src.pdf"
    _make_pdf(src, ["Page one body", "Page two body"])  # only 2 pages this time
    respx.get(f"{BASE}/api/base-resumes/master/pdf").mock(
        return_value=httpx.Response(200, content=src.read_bytes(),
                                    headers={"content-type": "application/pdf"})
    )
    out = BackendClient(BASE).get_rendered_pdf("base_resume", "master")
    from pathlib import Path

    assert out["page_count"] == 2
    assert [Path(p).name for p in out["page_images"]] == ["master.p1.png", "master.p2.png"]
    # the orphaned page from the previous (longer) render is gone
    assert not stale.exists()
