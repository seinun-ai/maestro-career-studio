"""The golden record: what every tool set answers over HTTP today, word for word.

Per set it holds the initialize result, the tool list (in full on /mcp, names in order on
the others) and the prompts; then one tool call per answer shape and one per refusal kind.
The SDK move (Phase 4) must keep every entry. An entry changed on purpose is listed in
_golden_cases.EXPECTED_CHANGES under its full entry name, with the whole entry as the record
holds it (normalised). With MAESTRO_WIRE_GOLDEN_WRITE=1 the test writes the fixture from this
run, with the Python, mcp and pydantic versions that made it, instead of comparing.

No call reaches a backend: each case patches the one client method its tool calls, and a
request that still gets as far as the network fails the test instead of being recorded.

The same calls also pin the server log: no refusal's words in it (1.x logged none), only the
crash, with its traceback.
"""

import difflib
import json
import logging
import os
import platform
import re
from importlib import metadata
from typing import Any

import pytest
from starlette.testclient import TestClient

from app.services import automations
from mcp_server import http as mcp_http
from mcp_server import server as srv
from mcp_server.tests._golden_cases import (
    CALLS, EXPECTED_CHANGES, FIXTURE, VERSIONS, call_case, expected_record, recorded,
)
from mcp_server.tests._wire import (
    HDR, INIT, asgi_app, normalise_record, normalise_response, rpc, session,
)

SET_PATHS = (
    "/mcp", "/mcp/profile", "/mcp/hunt", "/mcp/tailor", "/mcp/apply", "/mcp/track",
    "/mcp/templates",
)
HOW_TO_ACT = (
    "A deliberate change on mcp 1.x: regenerate with MAESTRO_WIRE_GOLDEN_WRITE=1 in a commit "
    "of its own. After the SDK 2.x bump: list the entry in _golden_cases.EXPECTED_CHANGES; "
    "never regenerate."
)

_HUNK_LINES = 40


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
    """One set's initialize, tool list (in full on /mcp, names in order elsewhere) and prompts.
    A response without a result is kept whole, so it shows up as a difference."""
    response = wire.client.post(path, json=INIT, headers=HDR)
    assert response.status_code == 200, (path, response.text)
    init = response.json()
    server_info = (init.get("result") or {}).get("serverInfo") or {}
    server_info.pop("version", None)  # the app version, not the wire's
    tools = wire.ask(path, "tools/list")
    listed = (tools.get("result") or {}).get("tools")
    return {
        f"initialize {path}": init,
        f"tools/list {path}": (
            tools if path == "/mcp" or listed is None else [t.get("name") for t in listed]
        ),
        f"prompts/list {path}": wire.ask(path, "prompts/list"),
    }


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
        for call in CALLS:
            entries[f"tools/call {call.entry}"] = call_case(wire, call)
    assert not reached, (
        "these requests reached the network (a case's client call is unpatched, or a refusal "
        f"no longer refuses): {reached}"
    )
    return entries


def _versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "mcp": metadata.version("mcp"),
        "pydantic": metadata.version("pydantic"),
    }


def _said(versions: dict[str, str]) -> str:
    return ", ".join(f"{name} {versions.get(name, '?')}" for name in ("python", "mcp", "pydantic"))


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=1, ensure_ascii=False)


def _diff(before: list[str], after: list[str], label: str) -> list[str]:
    """A unified diff, cut after _HUNK_LINES lines of hunks with a marker saying how many more."""
    lines = list(difflib.unified_diff(before, after, label, "now", n=1, lineterm=""))
    cut = 2 + _HUNK_LINES  # the two file-label lines, then the hunks
    if len(lines) > cut:
        lines = [*lines[:cut], f"… {len(lines) - cut} more lines"]
    return lines


def _tools_by_name(entry: Any) -> dict[str, Any]:
    result = entry.get("result") if isinstance(entry, dict) else None
    return {t.get("name"): t for t in (result or {}).get("tools") or []}


def _changed_tools(want: Any, got: Any, label: str) -> list[str]:
    """For the full tool list, each changed tool by name with the keys that changed, then the
    names' own diff when they or their order moved: the JSON hunks after it are capped."""
    before, after = _tools_by_name(want), _tools_by_name(got)
    lines = []
    for name in sorted(before.keys() & after.keys()):
        keys = before[name].keys() | after[name].keys()
        changed = sorted(k for k in keys if before[name].get(k) != after[name].get(k))
        if changed:
            lines.append(f"  {name}: {', '.join(changed)}")
    if list(before) != list(after):
        lines.append("  names or order:")
        lines.extend(_diff(list(before), list(after), label))
    return lines


def _entry_lines(name: str, want: Any, got: Any, label: str) -> list[str]:
    return [
        f"== {name}",
        *_changed_tools(want, got, label),
        *_diff(_dump(want).splitlines(), _dump(got).splitlines(), label),
    ]


def _differences(want: dict[str, Any], got: dict[str, Any]) -> list[str]:
    lines = []
    for name in sorted(want.keys() | got.keys()):
        if name not in got:
            lines.append(f"== {name}: in the record, not answered now")
        elif name not in want:
            lines.append(f"== {name}: answered now, not in the record")
        elif want[name] != got[name]:
            label = "expected" if name in EXPECTED_CHANGES else "recorded"
            lines.extend(_entry_lines(name, want[name], got[name], label))
    return lines


def test_wire_answers_match_the_golden_record():
    with TestClient(asgi_app(mcp_http.McpEndpoint())) as client:
        got = normalise_record(record(client))
    if os.environ.get("MAESTRO_WIRE_GOLDEN_WRITE") == "1":
        FIXTURE.parent.mkdir(exist_ok=True)
        FIXTURE.write_text(_dump({VERSIONS: _versions(), **got}) + "\n", encoding="utf-8")
        pytest.fail("fixture written; rerun without the variable", pytrace=False)
    made_with, entries = recorded()
    unknown = sorted(EXPECTED_CHANGES.keys() - entries.keys())
    if unknown:
        pytest.fail(f"EXPECTED_CHANGES names entries the record lacks: {unknown}", pytrace=False)
    differing = _differences(expected_record(), got)
    if differing:
        pytest.fail(
            "\n".join([
                f"recorded with {_said(made_with)}; running {_said(_versions())}",
                HOW_TO_ACT,
                "these entries differ from the golden record:",
                *differing,
            ]),
            pytrace=False,
        )


def test_only_an_empty_experimental_capability_is_left_out_of_the_comparison():
    def caps(experimental):
        return {"result": {"capabilities": {"experimental": experimental, "tools": {}}}}

    assert normalise_response(caps({})) == {"result": {"capabilities": {"tools": {}}}}
    assert normalise_response(caps({"x": {}})) == {
        "result": {"capabilities": {"experimental": {"x": {}}, "tools": {}}}
    }
    # Outside capabilities, an `experimental` key is an answer's own data, compared as it is.
    answer = {"result": {"structuredContent": {"experimental": {}}}}
    assert normalise_response(answer) == answer


_CLIENT_LOGGERS = frozenset({"httpx", "httpx2"})  # the test client's own request lines
# Session managers and sessions starting and stopping, at INFO; 1.x logged the same lines.
_LIFECYCLE = {
    "mcp.server.streamable_http_manager": re.compile(
        r"StreamableHTTP session manager (started|shutting down)"
        r"|Created new transport with session ID: [0-9a-f]+"
    ),
    "mcp.server.streamable_http": re.compile(r"Terminating session: [0-9a-f]+"),
}


def _about_the_calls(r: logging.LogRecord) -> bool:
    lifecycle = _LIFECYCLE.get(r.name)
    if r.levelno == logging.INFO and lifecycle and lifecycle.fullmatch(r.getMessage()):
        return False
    return r.name not in _CLIENT_LOGGERS


def test_the_golden_calls_log_only_the_crash(caplog):
    """The app's log runs at INFO (the SDK's own logging setup). A refusal is the agent's to
    read, not the log's; a crash's traceback is the log's (the owner's call)."""
    with caplog.at_level(logging.INFO), TestClient(asgi_app(mcp_http.McpEndpoint())) as client:
        record(client)
    logged = [(r.name, r.levelname) for r in caplog.records if _about_the_calls(r)]
    assert logged == [("mcp.server.mcpserver.server", "ERROR")], caplog.text
    assert "KeyError: 'slug'" in caplog.text
