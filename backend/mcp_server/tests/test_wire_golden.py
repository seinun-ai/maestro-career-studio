"""The golden record: what every tool set answers over HTTP today, word for word.

Per set it holds the initialize result, the tool list (in full on /mcp, names in order on
the others) and the prompts; then one tool call per answer shape and one per refusal kind.
The SDK move (Phase 4) must keep every entry; an entry changed on purpose is named in
EXPECTED_CHANGES with what it reads after the change. With MAESTRO_WIRE_GOLDEN_WRITE=1 the
test writes the fixture from this run instead of comparing.

No call reaches a backend: each case patches the one client method its tool calls, and a
request that still gets as far as the network fails the test instead of being recorded.
"""

import difflib
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from app.services import automations
from mcp_server import http as mcp_http
from mcp_server import server as srv
from mcp_server.client import BackendError
from mcp_server.tests._wire import HDR, INIT, app, rpc, session

FIXTURE = Path(__file__).parent / "fixtures" / "wire_golden.json"
SET_PATHS = (
    "/mcp", "/mcp/profile", "/mcp/hunt", "/mcp/tailor", "/mcp/apply", "/mcp/track",
    "/mcp/templates",
)

# Entry name -> what it reads after a deliberate change (empty while nothing is meant to).
EXPECTED_CHANGES: dict[str, Any] = {}

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

# (entry, path, tool, arguments, the client method the tool calls, what that method returns
# or raises). None: the call is refused before the tool body runs, so a refusal that stopped
# refusing reaches the network and fails the test.
CALLS: list[tuple[str, str, str, dict[str, Any], str | None, Any]] = [
    ("get_job answers a dict", "/mcp", "get_job", {"job_id": "job-1"}, "get_job", _JOB),
    ("list_referrals answers a list", "/mcp", "list_referrals", {}, "list_referrals", _REFERRALS),
    ("list_templates answers an empty list", "/mcp", "list_templates", {}, "list_templates", []),
    (
        "get_career_context answers a string", "/mcp", "get_career_context",
        {"format": "markdown"}, "get_career_context", _CAREER_MD,
    ),
    ("quick_tailor is a removed tool", "/mcp", "quick_tailor", {}, None, None),
    (
        "explore_top_skills is a removed tool, its replacement in another set", "/mcp/hunt",
        "explore_top_skills", {}, None, None,
    ),
    (
        "kb_approve_points refuses the removed state argument", "/mcp/profile",
        "kb_approve_points", {"point_ids": ["p1"], "state": "retired"}, None, None,
    ),
    ("render_pdf is outside the hunt set", "/mcp/hunt", "render_pdf", {}, None, None),
    ("no_such_tool is never served", "/mcp", "no_such_tool", {}, None, None),
    ("get_job without job_id fails the schema", "/mcp/hunt", "get_job", {}, None, None),
    (
        "generate_cover_letter carries the backend's refusal", "/mcp/apply",
        "generate_cover_letter", {"application_id": "app-1", "tone": "warm"},
        "generate_cover_letter", BackendError(_AGENT_WRITES_409, status_code=409),
    ),
    (
        "update_application refuses a bare clear string", "/mcp/track", "update_application",
        {"application_id": "app-1", "clear": "notes"}, None, None,
    ),
    (
        "get_base_resume crashes on a KeyError", "/mcp", "get_base_resume", {"slug": "main"},
        "get_base_resume", KeyError("slug"),
    ),
]

_REVISION_KEYS = frozenset({"resultType", "ttlMs", "cacheScope", "_meta"})
# pydantic links each validation error to its docs for the installed minor version, and CI
# installs the newest one, so the version in that link is not part of what is recorded.
_PYDANTIC_DOCS = re.compile(r"errors\.pydantic\.dev/[0-9.]+/")


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k not in _REVISION_KEYS}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    if isinstance(value, str):
        return _PYDANTIC_DOCS.sub("errors.pydantic.dev/<version>/", value)
    return value


def normalise(entries: dict[str, Any]) -> dict[str, Any]:
    """Each entry without its JSON-RPC envelope's jsonrpc and id, and without, at any depth,
    the keys the 2026-07-28 revision adds (absent on 1.30): what an agent reads, either side."""
    return {
        name: _strip(
            {k: v for k, v in entry.items() if k not in ("jsonrpc", "id")}
            if isinstance(entry, dict) else entry
        )
        for name, entry in entries.items()
    }


def _answering(value: Any):
    def call(*_args: Any, **_kwargs: Any) -> Any:
        if isinstance(value, BaseException):
            raise value
        return value

    return call


class _Wire:
    """One session per set path, opened on first use; every request gets its own id."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.sessions: dict[str, str] = {}
        self.next_id = 1

    def ask(self, path: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path not in self.sessions:
            self.sessions[path] = session(self.client, path)
        self.next_id += 1
        response = rpc(self.client, path, self.sessions[path], method, params, self.next_id)
        assert response.status_code == 200, (path, method, response.text)
        return response.json()


def _set_entries(wire: _Wire, path: str) -> dict[str, Any]:
    """One set's initialize, tool list (in full on /mcp, names in order elsewhere) and prompts."""
    response = wire.client.post(path, json=INIT, headers=HDR)
    assert response.status_code == 200, (path, response.text)
    init = response.json()
    init["result"]["serverInfo"].pop("version")  # the app version, not the wire's
    tools = wire.ask(path, "tools/list")
    return {
        f"initialize {path}": init,
        f"tools/list {path}": (
            tools if path == "/mcp" else [t["name"] for t in tools["result"]["tools"]]
        ),
        f"prompts/list {path}": wire.ask(path, "prompts/list"),
    }


def _called(wire: _Wire, call: tuple[str, str, dict[str, Any], str | None, Any]) -> dict[str, Any]:
    path, tool, arguments, method, answer = call
    with pytest.MonkeyPatch.context() as case:
        if method is not None:
            case.setattr(srv._client, method, _answering(answer))
        return wire.ask(path, "tools/call", {"name": tool, "arguments": arguments})


def record(client: TestClient) -> dict[str, Any]:
    """Every entry by name: the JSON-RPC response as the wire carries it."""
    reached: list[str] = []

    def offline(method: str, path: str, **_kwargs: Any) -> Any:
        reached.append(f"{method} {path}")
        raise AssertionError(f"{method} {path} reached the network")

    cards = automations.catalog().model_dump(mode="json")
    wire = _Wire(client)
    entries: dict[str, Any] = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(srv._client, "_send", offline)
        mp.setattr(srv._client, "get_automations", lambda: cards)
        for path in SET_PATHS:
            entries.update(_set_entries(wire, path))
        for name in ("tailor-run", "job-hunt"):
            entries[f"prompts/get {name} on /mcp/tailor"] = wire.ask(
                "/mcp/tailor", "prompts/get", {"name": name}
            )
        for entry, *call in CALLS:
            entries[f"tools/call {entry}"] = _called(wire, tuple(call))
    assert not reached, (
        "these requests reached the network (a case's client call is unpatched, or a refusal "
        f"no longer refuses): {reached}"
    )
    return entries


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=1, ensure_ascii=False)


def _tools_by_name(entry: Any) -> dict[str, Any]:
    tools = entry.get("result", {}).get("tools") if isinstance(entry, dict) else None
    return {t["name"]: t for t in tools or []}


def _changed_tools(want: Any, got: Any) -> list[str]:
    """For the full tool list, each changed tool by name with the keys that changed: the
    hunks after it are capped, and a change to every description would fill them."""
    before, after = _tools_by_name(want), _tools_by_name(got)
    lines = []
    for name in sorted(before.keys() & after.keys()):
        keys = before[name].keys() | after[name].keys()
        changed = sorted(k for k in keys if before[name].get(k) != after[name].get(k))
        if changed:
            lines.append(f"  {name}: {', '.join(changed)}")
    if list(before) != list(after):
        lines.append(f"  names or order: recorded {list(before)}, now {list(after)}")
    return lines


def _differences(want: dict[str, Any], got: dict[str, Any]) -> str:
    lines = []
    for name in sorted(want.keys() | got.keys()):
        if name not in got:
            lines.append(f"--- {name}: in the record, not answered now")
        elif name not in want:
            lines.append(f"--- {name}: answered now, not in the record")
        elif want[name] != got[name]:
            diff = difflib.unified_diff(
                _dump(want[name]).splitlines(), _dump(got[name]).splitlines(),
                "recorded", "now", n=1, lineterm="",
            )
            lines.append(f"--- {name}:")
            lines.extend(_changed_tools(want[name], got[name]))
            lines.extend(list(diff)[2:42])  # the hunks, capped
    return "\n".join(lines)


def test_wire_answers_match_the_golden_record():
    with TestClient(app(mcp_http.McpEndpoint())) as client:
        got = normalise(record(client))
    if os.environ.get("MAESTRO_WIRE_GOLDEN_WRITE") == "1":
        FIXTURE.parent.mkdir(exist_ok=True)
        FIXTURE.write_text(_dump(got) + "\n", encoding="utf-8")
        pytest.fail("fixture written; rerun without the variable")
    recorded = normalise(json.loads(FIXTURE.read_text(encoding="utf-8")))
    want = {**recorded, **normalise(EXPECTED_CHANGES)}
    differing = _differences(want, got)
    assert not differing, "these entries differ from the golden record:\n" + differing
