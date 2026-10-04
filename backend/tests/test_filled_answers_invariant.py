"""SYSTEM.md {#inv-filled-answers-local}: what was filled into a form lives only in the local
`filled_answers` table. The value-free channels (telemetry, run traces, Langfuse) and the
exports never read it, and the receipt module touches no tracing or model client. Source pins
catch a channel that learns to name the receipt; the export test posts a receipt and reads what
each export serves. The endpoint, serializer and MCP halves are pinned by
`test_filled_answers_api.py`, `test_filled_answers_agent.py` and
`mcp_server/tests/test_client_filled_answers.py` (which also pins that no MCP path GETs the
receipt)."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.schemas.eeo_consent import EeoConsent
from app.services import eeo_consent
from app.services import exports as career_exports
from tests.extension_harness import js_code
from tests.test_proposals_models import _mk_job

ROOT = Path(__file__).resolve().parents[2]
_RECEIPT = re.compile(r"filled[_-]answers?|FilledAnswer|receipt", re.IGNORECASE)

_VALUE_FREE_BACKEND = [
    "backend/app/routers/autofill.py",
    "backend/app/services/autofill_telemetry.py",
    "backend/app/services/autofill_trace.py",
    "backend/app/schemas/autofill_telemetry.py",
    "backend/app/schemas/autofill_trace.py",
    "backend/app/services/tracing.py",
    "backend/app/services/exports.py",
    "backend/app/routers/exports.py",
]

_ANSWER = "Zanzibar-receipt-value-7731"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    return source[source.index(start):source.index(end, source.index(start))]


@pytest.mark.parametrize("rel", _VALUE_FREE_BACKEND)
def test_no_value_free_channel_or_export_reads_the_receipt(rel):
    assert not _RECEIPT.search(_read(rel)), f"{rel} names the receipt"


def test_telemetry_and_trace_never_read_the_receipt():
    """The extension's two value-free builders and the service worker's two posts."""
    loop = js_code(_read("extension/shared/fill-loop.js"))
    builders = _between(loop, "const buildLoopObservations", "const sectionLines")
    worker = js_code(_read("extension/sw.js"))
    posts = _between(worker, "async telemetry(msg)", "async attach_pdf(")
    scrubs = _between(worker, "function scrubObservation", "function assertBackendPath")
    for name, code in (("loop builders", builders), ("sw posts", posts), ("sw scrubs", scrubs)):
        assert not _RECEIPT.search(code), f"{name} name the receipt"


def test_the_receipt_service_reaches_no_tracing_or_model_client():
    service = _read("backend/app/services/filled_answers.py")
    imports = [line for line in service.splitlines() if line.startswith(("import ", "from "))]
    assert not [line for line in imports if re.search(r"\b(tracing|llm|langfuse|telemetry)\b", line)]


def test_no_export_serves_a_recorded_answer(db_session, tmp_path, monkeypatch):
    """The jobs export (`GET /api/jobs/export`, MCP `export_jobs`) and the career export
    (`career.md`) are the two exports; a recorded answer, EEO or not, is in neither."""
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    monkeypatch.setattr(career_exports.settings, "exports_dir", tmp_path)
    eeo_consent.set_consent(EeoConsent(enabled=True), db_session)
    job = _mk_job(db_session, company="Acme")
    client = TestClient(app)
    posted = client.post(f"/api/jobs/{job.id}/filled-answers", json={"channel": "companion", "fields": [
        {"question": "First name", "answer": _ANSWER, "source": "profile"},
        {"question": "Gender", "answer": _ANSWER, "source": "profile", "eeo": True},
    ]})
    assert posted.status_code == 201
    assert _ANSWER in client.get(f"/api/jobs/{job.id}/filled-answers").text
    jobs_export = client.get("/api/jobs/export")
    assert jobs_export.status_code == 200 and str(job.id) in jobs_export.text
    assert _ANSWER not in jobs_export.text
    assert _ANSWER not in career_exports.get_career_export(db_session, force=True).markdown


def test_the_companion_posts_the_receipt_through_the_api_door_only():
    """The Companion's half: the builder names no value-free channel, and the post is the
    generic `api` door, never `telemetry` or `fill_trace` (and so not gated by the telemetry
    setting: `test_the_receipt_goes_through_the_api_door_even_with_telemetry_off` runs it)."""
    receipt = js_code(_read("extension/shared/receipt.js"))
    assert not re.search(r"\b(telemetry|fill_trace|trace)\b", receipt)
    record = _between(js_code(_read("extension/panel/actions/fill.js")),
                      "async function recordReceipt", "const flagRows")
    assert "store.api(" in record
    assert not re.search(r"store\.(telemetry|trace)\(|telemetryEnabled", record)
