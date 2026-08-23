import base64
import hashlib
from pathlib import Path

import httpx
import pytest
import respx

import mcp_server.client as client_module
from mcp_server.client import BackendClient, BackendError
from tests.pdf_fixtures import multipage_text_pdf_bytes


BASE = "http://test-backend"

def _mock_assert_open_proposal(application_id: str = "a1"):
    respx.post(f"{BASE}/api/applications/{application_id}/assert-open-proposal").mock(
        return_value=httpx.Response(200, json={"ok": True, "proposal_id": None, "op": "prepare"})
    )



def _pdf_response(
    content: bytes,
    filename: str = "260501_Quill_Riley_DataAnalyst_TechCorp_Resume.pdf",
) -> httpx.Response:
    return httpx.Response(
        200,
        content=content,
        headers={
            "content-type": "application/pdf",
            "content-disposition": f'inline; filename="{filename}"',
        },
    )


def _mock_application_detail(application_id: str = "a1", artifact_dir: str | None = None):
    payload = {"id": application_id, "artifact_dir": artifact_dir}
    respx.get(f"{BASE}/api/applications/{application_id}").mock(
        return_value=httpx.Response(200, json=payload)
    )


@respx.mock
def test_get_rendered_pdf_is_slim_but_keeps_preview_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    pdf = multipage_text_pdf_bytes(["Page one", "Page two — review"])
    respx.get(f"{BASE}/api/applications/a1/pdf").mock(return_value=_pdf_response(pdf))
    _mock_application_detail(artifact_dir="/apps/Acme_Role_20260730_abcd1234")

    out = BackendClient(BASE).get_rendered_pdf("application", "a1")

    assert "page_images_b64" not in out
    assert out["page_count"] == 2
    assert [Path(path).name for path in out["page_images"]] == ["a1.p1.png", "a1.p2.png"]
    assert all(Path(path).is_file() for path in out["page_images"])
    assert out["em_dash_found"] is True
    assert out["em_dash_pages"] == [2]
    assert out["artifact_dir"] == "/apps/Acme_Role_20260730_abcd1234"


@respx.mock
def test_get_rendered_pdf_omits_empty_artifact_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    pdf = multipage_text_pdf_bytes(["Page one"])
    respx.get(f"{BASE}/api/applications/a1/pdf").mock(return_value=_pdf_response(pdf))
    _mock_application_detail(artifact_dir=None)

    out = BackendClient(BASE).get_rendered_pdf("application", "a1")

    assert "artifact_dir" not in out
    assert "page_images_b64" not in out


@respx.mock
def test_get_rendered_pdf_page_image_returns_only_requested_page(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    pdf = multipage_text_pdf_bytes(["Page one", "Page two"])
    respx.get(f"{BASE}/api/applications/a1/pdf").mock(return_value=_pdf_response(pdf))
    _mock_application_detail()

    out = BackendClient(BASE).get_rendered_pdf_page_image("application", "a1", 2)

    assert set(out) == {
        "target_type",
        "target_id",
        "page_number",
        "page_count",
        "filename",
        "path",
        "size_bytes",
        "mime_type",
        "page_image_b64",
    }
    assert out["target_type"] == "application"
    assert out["target_id"] == "a1"
    assert out["page_number"] == 2
    assert out["page_count"] == 2
    assert out["filename"] == "a1.p2.w1024.png"
    assert Path(out["path"]).name == "a1.p2.w1024.png"
    image = base64.b64decode(out["page_image_b64"])
    assert image == Path(out["path"]).read_bytes()
    assert out["size_bytes"] == len(image)
    assert out["mime_type"] == "image/png"
    assert "page_images" not in out
    assert "page_images_b64" not in out


@respx.mock
def test_get_rendered_pdf_page_image_defaults_to_1024px_cap(tmp_path, monkeypatch):
    from PIL import Image
    import io

    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    pdf = multipage_text_pdf_bytes(["Page one", "Dense page two"])
    respx.get(f"{BASE}/api/applications/a1/pdf").mock(return_value=_pdf_response(pdf))
    _mock_application_detail()

    out = BackendClient(BASE).get_rendered_pdf_page_image("application", "a1", 2)
    image = Image.open(io.BytesIO(base64.b64decode(out["page_image_b64"])))
    assert max(image.size) <= 1024


@respx.mock
def test_get_rendered_pdf_page_image_honors_caller_max_dimension(tmp_path, monkeypatch):
    from PIL import Image
    import io

    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    pdf = multipage_text_pdf_bytes(["Page one"])
    respx.get(f"{BASE}/api/applications/a1/pdf").mock(return_value=_pdf_response(pdf))
    _mock_application_detail()

    out = BackendClient(BASE).get_rendered_pdf_page_image(
        "application", "a1", 1, max_dimension_px=2000
    )
    image = Image.open(io.BytesIO(base64.b64decode(out["page_image_b64"])))
    assert max(image.size) == 2000


@respx.mock
def test_get_rendered_pdf_page_image_does_not_rewrite_preview_pngs(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    pdf = multipage_text_pdf_bytes(["Page one"])
    respx.get(f"{BASE}/api/applications/a1/pdf").mock(return_value=_pdf_response(pdf))
    _mock_application_detail()

    client = BackendClient(BASE)
    slim = client.get_rendered_pdf("application", "a1")
    preview = Path(slim["page_images"][0])
    before = preview.read_bytes()
    client.get_rendered_pdf_page_image("application", "a1", 1, max_dimension_px=64)
    assert preview.read_bytes() == before


@respx.mock
def test_get_rendered_pdf_page_image_hard_caps_encoded_payload(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    monkeypatch.setattr(client_module, "_PAGE_IMAGE_B64_CAP", 50)
    pdf = multipage_text_pdf_bytes(["Page one"])
    respx.get(f"{BASE}/api/applications/a1/pdf").mock(return_value=_pdf_response(pdf))
    _mock_application_detail()

    with pytest.raises(BackendError, match=r"lower max_dimension_px"):
        BackendClient(BASE).get_rendered_pdf_page_image("application", "a1", 1)


@pytest.mark.parametrize("page_number", [0, -1, 3])
@respx.mock
def test_get_rendered_pdf_page_image_rejects_out_of_bounds(
    page_number, tmp_path, monkeypatch
):
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(tmp_path))
    pdf = multipage_text_pdf_bytes(["Page one", "Page two"])
    respx.get(f"{BASE}/api/applications/a1/pdf").mock(return_value=_pdf_response(pdf))
    _mock_application_detail()

    with pytest.raises(BackendError, match=r"page_number must be between 1 and 2"):
        BackendClient(BASE).get_rendered_pdf_page_image(
            "application", "a1", page_number
        )


def test_get_rendered_pdf_page_image_rejects_unreadable_pdf(monkeypatch):
    client = BackendClient(BASE)
    monkeypatch.setattr(
        client,
        "get_rendered_pdf",
        lambda _target_type, _target_id: {
            "page_count": 1,
            "path": "/no/such/file.pdf",
            "page_images": [],
        },
    )

    with pytest.raises(BackendError):
        client.get_rendered_pdf_page_image("application", "a1", 1)


@respx.mock
def test_prepare_upload_uses_env_root_sanitizes_filename_and_copies_bytes(
    tmp_path, monkeypatch
):
    upload_root = tmp_path / "browser-uploads"
    monkeypatch.setenv("MAESTRO_CS_UPLOAD_DIR", str(upload_root))
    pdf = multipage_text_pdf_bytes(["Clean application PDF"])
    canonical_source = tmp_path / "canonical.pdf"
    canonical_source.write_bytes(pdf)
    respx.get(f"{BASE}/api/applications/a1/pdf").mock(
        return_value=_pdf_response(canonical_source.read_bytes(), "../../Resume.pdf")
    )

    _mock_assert_open_proposal()
    out = BackendClient(BASE).prepare_application_pdf_upload("a1")

    expected = upload_root / "a1" / "Resume.pdf"
    assert out == {
        "application_id": "a1",
        "canonical_filename": "Resume.pdf",
        "upload_path": str(expected),
        "size_bytes": len(pdf),
        "sha256": hashlib.sha256(pdf).hexdigest(),
        "page_count": 1,
        "em_dash_found": False,
        "em_dash_pages": [],
    }
    assert expected.read_bytes() == pdf
    assert canonical_source.read_bytes() == pdf


@respx.mock
def test_prepare_upload_default_is_repo_relative_not_cwd(tmp_path, monkeypatch):
    fake_repo = tmp_path / "repo"
    fake_module = fake_repo / "backend" / "mcp_server" / "client.py"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.delenv("MAESTRO_CS_UPLOAD_DIR", raising=False)
    monkeypatch.setattr(client_module, "__file__", str(fake_module))
    monkeypatch.chdir(elsewhere)
    pdf = multipage_text_pdf_bytes(["Application PDF"])
    respx.get(f"{BASE}/api/applications/a1/pdf").mock(
        return_value=_pdf_response(pdf, "Resume.pdf")
    )

    _mock_assert_open_proposal()
    out = BackendClient(BASE).prepare_application_pdf_upload("a1")

    assert Path(out["upload_path"]) == (
        fake_repo / ".playwright-mcp" / "uploads" / "a1" / "Resume.pdf"
    )


@respx.mock
def test_prepare_upload_atomically_replaces_existing_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_UPLOAD_DIR", str(tmp_path / "uploads"))
    first = multipage_text_pdf_bytes(["First version"])
    second = multipage_text_pdf_bytes(["Second version"])
    responses = iter(
        [_pdf_response(first, "Resume.pdf"), _pdf_response(second, "Resume.pdf")]
    )
    respx.get(f"{BASE}/api/applications/a1/pdf").mock(
        side_effect=lambda _request: next(responses)
    )
    client = BackendClient(BASE)

    _mock_assert_open_proposal()
    first_out = client.prepare_application_pdf_upload("a1")
    second_out = client.prepare_application_pdf_upload("a1")

    assert first_out["upload_path"] == second_out["upload_path"]
    assert Path(second_out["upload_path"]).read_bytes() == second
    assert second_out["sha256"] == hashlib.sha256(second).hexdigest()
    assert not list(Path(second_out["upload_path"]).parent.glob("*.tmp"))


@respx.mock
def test_prepare_upload_renders_and_retries_once_when_pdf_not_rendered(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MAESTRO_CS_UPLOAD_DIR", str(tmp_path / "uploads"))
    pdf = multipage_text_pdf_bytes(["Rendered on retry"])
    pdf_route = respx.get(f"{BASE}/api/applications/a1/pdf").mock(
        side_effect=[
            httpx.Response(404, json={"detail": "PDF not found"}),
            _pdf_response(pdf, "Resume.pdf"),
        ]
    )
    render_route = respx.post(f"{BASE}/api/applications/a1/render").mock(
        return_value=httpx.Response(200, json={"pdf_path": "/canonical/Resume.pdf"})
    )

    _mock_assert_open_proposal()
    out = BackendClient(BASE).prepare_application_pdf_upload("a1")

    assert Path(out["upload_path"]).read_bytes() == pdf
    assert pdf_route.call_count == 2
    assert render_route.call_count == 1


@respx.mock
def test_prepare_upload_does_not_render_for_missing_application(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_UPLOAD_DIR", str(tmp_path / "uploads"))
    respx.post(f"{BASE}/api/applications/missing/assert-open-proposal").mock(
        return_value=httpx.Response(404, json={"detail": "Application not found"})
    )
    respx.get(f"{BASE}/api/applications/missing/pdf").mock(
        return_value=httpx.Response(404, json={"detail": "Application not found"})
    )
    render_route = respx.post(f"{BASE}/api/applications/missing/render").mock(
        return_value=httpx.Response(200, json={})
    )

    with pytest.raises(BackendError, match="Application not found"):
        BackendClient(BASE).prepare_application_pdf_upload("missing")

    assert render_route.call_count == 0


def test_prepare_upload_rejects_unsafe_application_id(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_UPLOAD_DIR", str(tmp_path / "uploads"))

    with pytest.raises(BackendError, match="application_id"):
        BackendClient(BASE).prepare_application_pdf_upload("../a1")
