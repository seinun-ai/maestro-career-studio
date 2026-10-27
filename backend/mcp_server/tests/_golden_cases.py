"""The golden record's cases, shared by the tests that replay them: the fixture, the entries
changed on purpose since it was written, and the tools/call cases with the one client call each
case's tool body makes. test_wire_golden records and compares every entry; test_http_modern
replays the calls on the 2026-07-28 revision."""

import json
from pathlib import Path
from typing import Any, NamedTuple, Protocol

import pytest

from mcp_server import server as srv
from mcp_server.client import BackendError
from mcp_server.tests._wire import normalise_record

FIXTURE = Path(__file__).parent / "fixtures" / "wire_golden.json"
# The fixture's one key that is not an entry: the versions that wrote it, never compared.
VERSIONS = "_recorded_with"

# Full entry name -> the whole entry as the record holds it (normalised) after a deliberate
# change. Empty while nothing is meant to change.
EXPECTED_CHANGES: dict[str, Any] = {
    # The owner's call: on 2.x a crash's own text stays in the server log.
    "tools/call get_base_resume crashes on a KeyError": {
        "result": {
            "content": [{"type": "text", "text": "Error executing tool get_base_resume"}],
            "isError": True,
        }
    },
}

_JOB = {
    "job": {
        "id": "job-1", "company": "Example Corp", "title": "Data Analyst", "country_code": "GB",
    },
    "application": None,
}
# Two items: a list goes out as one content block per item.
_REFERRALS = [
    {"id": "ref-1", "company": "Example Corp", "contact_name": "Sample Contact",
     "applications_count": 1},
    {"id": "ref-2", "company": "Sample Labs", "contact_name": None, "applications_count": 0},
]
_CAREER_MD = (
    "# Career\n\n## Experience\n\n### Data Analyst, Example Corp\n\n- Built the weekly report.\n"
)
_AGENT_WRITES_409 = (
    "Backend returned 409: Your settings say your agent app writes, so Maestro's AI doesn't "
    "write for agent apps (Settings › Agent apps changes it). Write the letter yourself and "
    "save it with store_cover_letter."
)


class Call(NamedTuple):
    """One tools/call case, recorded as `tools/call <entry>`."""

    entry: str
    path: str
    tool: str
    arguments: dict[str, Any]
    client_method: str | None = None  # the one client call the tool body makes, patched
    answer: Any = None  # what client_method returns, or the exception it raises


# A case without client_method is refused before the tool body runs. A refusal that stopped
# refusing changes its text or reaches the network; both fail the test.
CALLS = [
    Call("get_job answers a dict", "/mcp", "get_job", {"job_id": "job-1"}, "get_job", _JOB),
    Call("list_referrals answers a list", "/mcp", "list_referrals", {}, "list_referrals",
         _REFERRALS),
    Call("list_templates answers an empty list", "/mcp", "list_templates", {}, "list_templates",
         []),
    Call("get_career_context answers a string", "/mcp", "get_career_context",
         {"format": "markdown"}, "get_career_context", _CAREER_MD),
    Call("quick_tailor is a removed tool", "/mcp", "quick_tailor", {}),
    Call("explore_top_skills is a removed tool, its replacement in another set", "/mcp/hunt",
         "explore_top_skills", {}),
    Call("kb_approve_points refuses the removed state argument", "/mcp/profile",
         "kb_approve_points", {"point_ids": ["p1"], "state": "retired"}),
    Call("render_pdf is outside the hunt set", "/mcp/hunt", "render_pdf", {}),
    Call("no_such_tool is never served", "/mcp", "no_such_tool", {}),
    Call("get_job without job_id fails the schema", "/mcp/hunt", "get_job", {}),
    Call("generate_cover_letter carries the backend's refusal", "/mcp/apply",
         "generate_cover_letter", {"application_id": "app-1", "tone": "warm"},
         "generate_cover_letter", BackendError(_AGENT_WRITES_409, status_code=409)),
    Call("update_application refuses a bare clear string", "/mcp/track", "update_application",
         {"application_id": "app-1", "clear": "notes"}),
    Call("get_base_resume crashes on a KeyError", "/mcp", "get_base_resume", {"slug": "main"},
         "get_base_resume", KeyError("slug")),
]


class Wire(Protocol):
    """One JSON-RPC request on a set's path, answered as the wire carries it."""

    def ask(
        self, path: str, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...


def answering(value: Any):
    """A stand-in client method: returns `value`, or raises it when it is an exception."""

    def call(*_args: Any, **_kwargs: Any) -> Any:
        if isinstance(value, BaseException):
            raise value
        return value

    return call


def call_case(wire: Wire, call: Call) -> dict[str, Any]:
    """One case's tools/call on `wire`, its client call patched for the call alone."""
    with pytest.MonkeyPatch.context() as mp:
        if call.client_method is not None:
            mp.setattr(srv._client, call.client_method, answering(call.answer))
        return wire.ask(call.path, "tools/call", {"name": call.tool, "arguments": call.arguments})


def recorded() -> tuple[dict[str, str], dict[str, Any]]:
    """The fixture as written: the versions that wrote it, and its entries by name."""
    entries = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return entries.pop(VERSIONS, {}), entries


def expected_record() -> dict[str, Any]:
    """What every entry must read now: the fixture's entries with EXPECTED_CHANGES applied,
    normalised."""
    _, entries = recorded()
    return normalise_record({**entries, **EXPECTED_CHANGES})
