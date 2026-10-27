"""An agent's own input that the server cannot use reads as a refusal naming what to change,
never as SDK 2.x's bare "Error executing tool <name>" (the text a crash gets)."""

import os

import httpx
import pytest
import respx
from mcp.server.mcpserver.exceptions import ToolError

import mcp_server.server as srv
from mcp_server.client import BackendClient
from tests.pdf_fixtures import multipage_text_pdf_bytes

BASE = "http://test-backend"
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.fixture
def backend(monkeypatch):
    """A real BackendClient with no backend behind it: a request that is never sent is the
    point of most cases here, and one that is sent must match a mocked route."""
    monkeypatch.setattr(srv, "_client", BackendClient(BASE))
    with respx.mock(assert_all_called=False) as mock:
        yield mock


async def _answer(tool: str, arguments: dict) -> str:
    """What the agent reads: the text of the refusal the call raises."""
    with pytest.raises(ToolError) as refused:
        await srv.mcp.call_tool(tool, arguments)
    return str(refused.value)


def _evidence(**source) -> dict:
    return {"proposal_id": "p1", "step": 1, "label": "Review", **source}


async def test_invalid_base64_is_refused_in_words(backend):
    upload = backend.post(f"{BASE}/api/proposals/p1/evidence")
    assert await _answer("attach_evidence", _evidence(image_base64="a")) == (
        "Error executing tool attach_evidence: image_base64 is not valid base64; send the raw "
        "base64 text, without a data: URL prefix."
    )
    assert not upload.called


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root reads a file whatever its mode"
)
async def test_an_unreadable_evidence_file_is_refused_in_words(backend, tmp_path):
    shot = tmp_path / "shot.png"
    shot.write_bytes(_PNG)
    shot.chmod(0)
    try:
        text = await _answer("attach_evidence", _evidence(file_path=str(shot)))
    finally:
        shot.chmod(0o600)
    assert text == (
        f"Error executing tool attach_evidence: evidence file could not be read: {shot} "
        "(Permission denied)"
    )


async def test_an_evidence_path_that_cannot_be_resolved_is_refused_in_words(backend, tmp_path):
    loop = tmp_path / "loop.png"
    loop.symlink_to(loop)
    text = await _answer("attach_evidence", _evidence(file_path=str(loop)))
    # Python 3.12 cannot resolve a symlink loop (RuntimeError); later versions report no file.
    assert text.startswith("Error executing tool attach_evidence: evidence file "), text
    assert str(loop) in text


async def test_an_evidence_file_over_the_limit_is_refused_before_it_is_read(
    backend, tmp_path, monkeypatch
):
    big = tmp_path / "big.png"
    with big.open("wb") as handle:
        handle.write(_PNG)
        handle.truncate(5 * 1024 * 1024 + 1)

    def never(_path):
        raise AssertionError("read a file over the limit")

    monkeypatch.setattr(type(big), "read_bytes", never)
    assert await _answer("attach_evidence", _evidence(file_path=str(big))) == (
        "Error executing tool attach_evidence: evidence file exceeds 5 MB"
    )


async def test_arguments_that_are_not_json_are_refused_in_words(backend):
    transition = backend.patch(f"{BASE}/api/proposals/p1")
    text = await _answer("record_decision", {"proposal_id": "p1", "fit": {"score": float("nan")}})
    assert text.startswith(
        "Error executing tool record_decision: the arguments could not be sent as JSON: "
    ), text
    assert "nan" in text
    assert not transition.called


async def test_a_pdf_folder_that_cannot_be_written_names_its_setting(backend, tmp_path, monkeypatch):
    not_a_folder = tmp_path / "pdfs"
    not_a_folder.write_text("a file where the folder should be")
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(not_a_folder))
    backend.get(f"{BASE}/api/base-resumes/main/pdf").mock(
        return_value=httpx.Response(200, content=multipage_text_pdf_bytes(["Page one"]))
    )
    text = await _answer("get_rendered_pdf", {"target_type": "base_resume", "target_id": "main"})
    assert text.startswith(
        f"Error executing tool get_rendered_pdf: could not write the PDF to {not_a_folder} ("
    ), text
    assert text.endswith("); MAESTRO_CS_PDF_DIR sets this folder."), text


async def test_an_upload_folder_that_cannot_be_written_names_its_setting(
    backend, tmp_path, monkeypatch
):
    not_a_folder = tmp_path / "uploads"
    not_a_folder.write_text("a file where the folder should be")
    monkeypatch.setenv("MAESTRO_CS_UPLOAD_DIR", str(not_a_folder))
    backend.post(f"{BASE}/api/applications/a1/assert-open-proposal").mock(
        return_value=httpx.Response(200, json={"ok": True, "proposal_id": None, "op": "prepare"})
    )
    backend.get(f"{BASE}/api/applications/a1/pdf").mock(
        return_value=httpx.Response(200, content=multipage_text_pdf_bytes(["Page one"]))
    )
    text = await _answer("prepare_application_pdf_upload", {"application_id": "a1"})
    assert text.startswith(
        "Error executing tool prepare_application_pdf_upload: could not stage the PDF in "
        f"{not_a_folder} ("
    ), text
    assert text.endswith("); MAESTRO_CS_UPLOAD_DIR sets this folder."), text
