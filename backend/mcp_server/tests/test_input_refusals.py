"""An agent's own input that the server cannot use reads as a refusal naming what to change,
never as SDK 2.x's bare "Error executing tool <name>" (the text a crash gets)."""

import logging
import os
from pathlib import Path

import httpx
import pytest
import respx
from mcp import Client
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


# One stray character; a string an LLM shortened with an ellipsis (not ASCII at all).
@pytest.mark.parametrize("image_base64", ["a", "iVBORw0KGgo…"])
async def test_invalid_base64_is_refused_in_words(backend, image_base64):
    upload = backend.post(f"{BASE}/api/proposals/p1/evidence")
    assert await _answer("attach_evidence", _evidence(image_base64=image_base64)) == (
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


async def test_a_loop_inside_the_playwright_mount_is_not_found(backend, tmp_path, monkeypatch):
    mount = tmp_path / "app" / ".playwright-mcp"
    (mount / "uploads").mkdir(parents=True)
    monkeypatch.setenv("MAESTRO_CS_UPLOAD_DIR", str(mount / "uploads"))
    (mount / "loop.png").symlink_to(mount / "loop.png")
    text = await _answer(
        "attach_evidence", _evidence(file_path="/Users/u/repo/.playwright-mcp/loop.png")
    )
    assert text.startswith("Error executing tool attach_evidence: evidence file not found: "), text


async def test_a_file_that_grew_past_the_limit_after_its_size_was_checked_is_refused(
    backend, tmp_path, monkeypatch
):
    big = tmp_path / "grew.png"
    with big.open("wb") as handle:
        handle.write(_PNG)
        handle.truncate(5 * 1024 * 1024 + 1)
    real_stat = Path.stat

    def as_it_was(self, *args, **kwargs):  # the size it had when it was checked
        result = real_stat(self, *args, **kwargs)
        return os.stat_result((*result[:6], len(_PNG), *result[7:10])) if self == big else result

    monkeypatch.setattr(type(big), "stat", as_it_was)
    assert await _answer("attach_evidence", _evidence(file_path=str(big))) == (
        "Error executing tool attach_evidence: evidence file exceeds 5 MB"
    )


async def test_an_evidence_file_over_the_limit_is_refused_before_it_is_read(
    backend, tmp_path, monkeypatch
):
    big = tmp_path / "big.png"
    with big.open("wb") as handle:
        handle.write(_PNG)
        handle.truncate(5 * 1024 * 1024 + 1)

    def never(*_args, **_kwargs):
        raise AssertionError("read a file over the limit")

    monkeypatch.setattr(type(big), "read_bytes", never)
    monkeypatch.setattr(type(big), "open", never)
    assert await _answer("attach_evidence", _evidence(file_path=str(big))) == (
        "Error executing tool attach_evidence: evidence file exceeds 5 MB"
    )


@pytest.mark.parametrize("number", [float("nan"), float("inf")])
async def test_a_number_json_cannot_carry_is_refused_in_words(backend, number):
    transition = backend.patch(f"{BASE}/api/proposals/p1")
    assert await _answer("record_decision", {"proposal_id": "p1", "fit": {"score": number}}) == (
        "Error executing tool record_decision: a number in the arguments is NaN or Infinity, "
        "which JSON can't carry; send a finite number or null."
    )
    assert not transition.called


async def test_a_lone_surrogate_is_refused_in_words(backend):
    transition = backend.patch(f"{BASE}/api/proposals/p1")
    fit = {"note": "ok \ud800"}
    assert await _answer("record_decision", {"proposal_id": "p1", "fit": fit}) == (
        "Error executing tool record_decision: a text in the arguments holds half of a character "
        "(an unpaired surrogate such as \\ud800), which JSON can't carry; send the text without it."
    )
    assert not transition.called


async def test_a_bug_in_the_request_path_stays_a_crash_with_its_traceback(
    backend, monkeypatch, caplog
):
    """Only the agent's own input becomes a refusal; our mistake keeps the generic text."""

    def misspelt(*_args, **_kwargs):
        raise TypeError("request() got an unexpected keyword argument 'jsn'")

    monkeypatch.setattr(httpx.Client, "request", misspelt)
    with caplog.at_level(logging.ERROR):
        async with Client(srv.mcp, mode="legacy") as client:
            result = await client.call_tool(
                "record_decision", {"proposal_id": "p1", "fit": {"score": 1}}
            )
    assert result.is_error
    assert result.content[0].text == "Error executing tool record_decision"
    assert "unexpected keyword argument 'jsn'" in caplog.text


async def test_a_pdf_folder_that_cannot_be_written_names_its_setting(backend, tmp_path, monkeypatch):
    not_a_folder = tmp_path / "pdfs"
    not_a_folder.write_text("a file where the folder should be")
    monkeypatch.setenv("MAESTRO_CS_PDF_DIR", str(not_a_folder))
    backend.get(f"{BASE}/api/base-resumes/main/pdf").mock(
        return_value=httpx.Response(200, content=multipage_text_pdf_bytes(["Page one"]))
    )
    text = await _answer("get_rendered_pdf", {"target_type": "base_resume", "target_id": "main"})
    assert text == (
        f"Error executing tool get_rendered_pdf: could not write the PDF to {not_a_folder} "
        "(it is a file, not a folder); MAESTRO_CS_PDF_DIR sets this folder."
    )


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
    assert text == (
        "Error executing tool prepare_application_pdf_upload: could not stage the PDF in "
        f"{not_a_folder} (it is a file, not a folder); MAESTRO_CS_UPLOAD_DIR sets this folder."
    )
