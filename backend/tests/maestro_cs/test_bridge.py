"""`maestro mcp`: one test per case of mcpb/tests/bridge.test.js, against httpx.MockTransport."""
import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from maestro_cs import bridge, cli, control
from maestro_cs.bridge import FAILED_MESSAGE, TIMEOUT_MESSAGE, Bridge

BACKEND = Path(__file__).resolve().parents[2]
BASE = "http://localhost:8001"
INITIALIZE = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-03-26", "capabilities": {},
               "clientInfo": {"name": "bridge-test-client", "version": "1"}},
}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
NOT_RUNNING = ("Maestro Career Studio is not running at {url}. "
               "Start it with `maestro start` and try again.")


def compact(message):
    return json.dumps(message, separators=(",", ":"))


class Seen:
    """A request as the fake backend received it."""

    def __init__(self, request: httpx.Request):
        self.method, self.url, self.headers = request.method, request.url, request.headers
        self.line = request.content.decode("utf-8")
        self.body = json.loads(self.line)

    @property
    def path(self):
        return self.url.path

    @property
    def session(self):
        return self.headers.get("mcp-session-id")


class Run:
    def __init__(self, out: bytes, err: str, requests: list[Seen]):
        self.out, self.err, self.requests = out, err, requests

    def messages(self):
        if not self.out:
            return []
        assert self.out.endswith(b"\n"), "each JSON-RPC output ends in a newline"
        assert b"\r" not in self.out
        return [json.loads(line) for line in self.out.decode("utf-8").rstrip("\n").split("\n")]


def reply(body, status=200, **headers):
    return httpx.Response(status, json=body, headers=headers)


def run_lines(lines, respond=None, *, url=BASE, timeout=5.0, client=None, profile="full"):
    requests: list[Seen] = []

    def handler(request):
        seen = Seen(request)
        requests.append(seen)
        return respond(seen)

    if client is None and respond is not None:
        client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    out, err = io.BytesIO(), io.StringIO()
    code = Bridge(url, profile, client=client, stdout=out, stderr=err, timeout=timeout).serve(
        io.BytesIO("".join(line + "\n" for line in lines).encode("utf-8")))
    assert code == 0
    return Run(out.getvalue(), err.getvalue(), requests)


def run_messages(messages, respond=None, **kwargs):
    return run_lines([compact(m) for m in messages], respond, **kwargs)


def raising(error):
    def respond(_seen):
        raise error
    return respond


def test_initialize_adopts_the_session_id_and_forwards_the_clients_exact_request():
    def respond(seen):
        if seen.body["method"] == "initialize":
            return reply({"jsonrpc": "2.0", "id": 1, "result": {}}, **{"mcp-session-id": "session-1"})
        return reply({"jsonrpc": "2.0", "id": 2, "result": {"tools": []}})

    result = run_messages([INITIALIZE, LIST], respond)
    assert result.messages() == [
        {"jsonrpc": "2.0", "id": 1, "result": {}},
        {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}},
    ]
    assert result.err == ""
    assert result.requests[0].line == compact(INITIALIZE)
    assert result.requests[0].session is None
    assert result.requests[1].session == "session-1"
    for seen in result.requests:
        assert seen.method == "POST"
        assert seen.path == "/mcp"
        assert seen.headers["accept"] == "application/json, text/event-stream"
        assert seen.headers["content-type"] == "application/json"


def test_a_notification_accepted_with_202_writes_nothing_to_stdout():
    result = run_messages([INITIALIZED], lambda _seen: httpx.Response(202))
    assert result.out == b""
    assert result.err == ""
    assert len(result.requests) == 1


def test_a_backend_restart_replays_initialize_and_initialized_before_retrying_once():
    state = {"session": "session-1", "initialized": False}

    def respond(seen):
        body = seen.body
        if body["method"] == "initialize":
            return reply({"jsonrpc": "2.0", "id": 1, "result": {}},
                         **{"mcp-session-id": state["session"]})
        if seen.session != state["session"]:
            return httpx.Response(404, text="Session not found")
        if body["method"] == "notifications/initialized":
            state["initialized"] = True
            return httpx.Response(202)
        if body["id"] == "before-restart":
            state.update(session="session-2", initialized=False)
            return reply({"jsonrpc": "2.0", "id": body["id"], "result": {}})
        if state["initialized"]:
            return reply({"jsonrpc": "2.0", "id": 2, "result": {"tools": []}})
        return httpx.Response(400, text="Not initialized")

    result = run_messages([INITIALIZE, INITIALIZED, {**LIST, "id": "before-restart"}, LIST], respond)
    assert result.messages() == [
        {"jsonrpc": "2.0", "id": 1, "result": {}},
        {"jsonrpc": "2.0", "id": "before-restart", "result": {}},
        {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}},
    ]
    assert [seen.body["method"] for seen in result.requests] == [
        "initialize", "notifications/initialized", "tools/list", "tools/list",
        "initialize", "notifications/initialized", "tools/list",
    ]
    assert result.requests[4].session is None
    assert result.requests[4].line == compact(INITIALIZE)
    assert result.requests[5].line == compact(INITIALIZED)
    assert result.requests[5].session == "session-2"
    assert result.requests[6].session == "session-2"


def test_connection_refusal_prints_the_start_sentence_and_preserves_the_request_id():
    message = NOT_RUNNING.format(url=BASE)
    result = run_messages([{**LIST, "id": "refused"}], raising(httpx.ConnectError("refused")))
    assert result.err == message + "\n"
    assert result.messages() == [
        {"jsonrpc": "2.0", "id": "refused", "error": {"code": -32000, "message": message}},
    ]


def test_connection_refusal_for_a_notification_produces_only_stderr():
    result = run_messages([INITIALIZED], raising(httpx.ConnectError("refused")))
    assert result.out == b""
    assert result.err.startswith("Maestro Career Studio is not running at ")


def test_an_unanswered_request_times_out_without_saying_the_app_is_stopped_or_retrying():
    result = run_messages([LIST], raising(httpx.ReadTimeout("no answer")), timeout=0.05)
    assert result.messages() == [
        {"jsonrpc": "2.0", "id": 2, "error": {"code": -32000, "message": TIMEOUT_MESSAGE}},
    ]
    assert result.err == TIMEOUT_MESSAGE + "\n"
    assert len(result.requests) == 1, "a timeout never retries work that may still finish"


def test_the_overall_deadline_includes_a_response_body_that_keeps_sending_data():
    def trickle():
        for _ in range(500):  # 5 s of whitespace; the 80 ms deadline must cut it short
            time.sleep(0.01)
            yield b" "

    started = time.monotonic()
    result = run_messages([LIST], lambda _seen: httpx.Response(
        200, headers={"content-type": "application/json"}, content=trickle()), timeout=0.08)
    assert time.monotonic() - started < 2
    assert result.messages()[0]["error"]["message"] == TIMEOUT_MESSAGE
    assert result.err == TIMEOUT_MESSAGE + "\n"
    assert len(result.requests) == 1


def test_a_dropped_connection_does_not_claim_that_maestro_is_not_running():
    result = run_messages([LIST], raising(httpx.RemoteProtocolError("closed")))
    [message] = result.messages()
    assert message["id"] == 2
    assert message["error"]["code"] == -32000
    assert "not running" not in message["error"]["message"]
    assert "request may still finish" in message["error"]["message"]
    assert message["error"]["message"] == FAILED_MESSAGE
    assert result.err == message["error"]["message"] + "\n"
    assert len(result.requests) == 1


@pytest.mark.parametrize("url", ["not a URL", "ftp://localhost:8001"])
def test_an_invalid_backend_url_keeps_the_connection_failure_sentence(url):
    result = run_messages([LIST], url=url)  # the real client refuses before any socket opens
    message = NOT_RUNNING.format(url=url)
    assert result.messages() == [
        {"jsonrpc": "2.0", "id": 2, "error": {"code": -32000, "message": message}},
    ]
    assert result.err == message + "\n"


def test_json_null_and_primitive_lines_are_ignored_with_one_sentence_each_then_processing_continues():
    result = run_messages([None, True, False, 42, "text", LIST], url="not a URL")
    messages = result.messages()
    assert len(messages) == 1
    assert messages[0]["id"] == 2
    assert messages[0]["error"]["code"] == -32000
    stderr = result.err.rstrip("\n").split("\n")
    assert len(stderr) == 6
    assert stderr[:5] == ["The MCP message must be a JSON object or array."] * 5


def test_failed_http_posts_of_client_responses_never_echo_an_error_with_the_response_id():
    responses = [
        {"jsonrpc": "2.0", "id": "client-result", "result": {}},
        {"jsonrpc": "2.0", "id": "client-error", "error": {"code": -32601, "message": "Unknown method"}},
    ]
    result = run_messages(responses, lambda _seen: httpx.Response(500, text="Backend error"))
    assert result.out == b""
    assert [seen.body for seen in result.requests] == responses


def test_connection_failures_answer_only_requests_with_a_method_and_id_including_batches():
    responses = [
        {"jsonrpc": "2.0", "id": "client-result", "result": {}},
        {"jsonrpc": "2.0", "id": "client-error", "error": {"code": -32601, "message": "Unknown method"}},
    ]
    result = run_messages(
        [*responses, [*responses, INITIALIZED, None, {**LIST, "id": 0}]], url="not a URL")
    [batch] = result.messages()
    assert isinstance(batch, list)
    assert len(batch) == 1
    assert batch[0]["id"] == 0
    assert batch[0]["error"]["code"] == -32000


def test_unparseable_input_returns_parse_error_with_id_null_and_continues_to_the_next_line():
    result = run_lines(["{", compact(LIST)], url="not a URL")
    messages = result.messages()
    assert messages[0] == {"jsonrpc": "2.0", "id": None,
                           "error": {"code": -32700, "message": "Parse error"}}
    assert len(messages) == 2
    assert messages[1]["id"] == 2


def test_hunt_selects_mcp_hunt_and_full_selects_mcp():
    def respond(_seen):
        return reply({"jsonrpc": "2.0", "id": 2, "result": {}})

    paths = []
    for profile in ("hunt", "full"):
        paths.append(run_messages([LIST], respond, url=BASE + "/", profile=profile).requests[0].path)
    assert paths == ["/mcp/hunt", "/mcp"]


def test_the_bridge_dials_the_ipv4_loopback_address_not_localhost(tmp_path):
    # `localhost` can resolve to ::1 first on Windows, where the refusal costs about two seconds.
    url = bridge.backend_url_from({"MAESTRO_HOME": str(tmp_path / "home")})
    assert url == "http://127.0.0.1:8001" and "localhost" not in url


def test_the_backend_port_comes_from_the_process_env_then_maestro_env_then_the_default(tmp_path):
    home = tmp_path / "home"
    environ = {"MAESTRO_HOME": str(home)}
    assert bridge.backend_url_from(environ) == "http://127.0.0.1:8001"
    assert not home.exists(), "reading the port never creates the install folder"
    home.mkdir()
    (home / "maestro.env").write_text("MAESTRO_PORT=18123\n", encoding="utf-8")
    assert bridge.backend_url_from(environ) == "http://127.0.0.1:18123"
    assert bridge.backend_url_from({**environ, "MAESTRO_PORT": "18124"}) == "http://127.0.0.1:18124"


def test_http_failures_and_non_json_bodies_emit_json_rpc_errors_never_raw_text():
    def respond(seen):
        return httpx.Response(
            200 if seen.body.get("id") == "non-json" else 500,
            text="<html>Backend error\nwith a second line</html>")

    result = run_messages([{**LIST, "id": 0}, {**LIST, "id": "non-json"}, INITIALIZED], respond)
    messages = result.messages()
    assert len(messages) == 2, "a failed notification has no JSON-RPC response"
    assert [m["id"] for m in messages] == [0, "non-json"]
    for message in messages:
        assert message["jsonrpc"] == "2.0"
        assert message["error"]["code"] == -32000
        assert "\n" not in message["error"]["message"]
        assert message["error"]["message"].endswith(".")
        assert "<html>" not in message["error"]["message"]
        assert "second line" not in message["error"]["message"]


def test_404_without_a_session_returns_an_error_without_replaying():
    result = run_messages([LIST], lambda _seen: httpx.Response(404))
    assert result.messages()[0]["error"]["code"] == -32000
    assert len(result.requests) == 1


def test_404_on_the_retry_returns_an_error_and_never_loops():
    initializes = []

    def respond(seen):
        if seen.body["method"] == "initialize":
            initializes.append(1)
            return reply({"jsonrpc": "2.0", "id": 1, "result": {}},
                         **{"mcp-session-id": f"session-{len(initializes)}"})
        return httpx.Response(202 if seen.body["method"] == "notifications/initialized" else 404)

    result = run_messages([INITIALIZE, INITIALIZED, LIST], respond)
    messages = result.messages()
    assert len(messages) == 2
    assert messages[1]["id"] == 2
    assert messages[1]["error"]["code"] == -32000
    assert len(initializes) == 2
    assert len(result.requests) == 6


def test_requests_wait_for_preceding_responses_and_batch_json_passes_through_as_an_array():
    state = {"busy": False, "overlapped": False}

    def respond(seen):
        state["overlapped"] |= state["busy"]
        state["busy"] = True
        time.sleep(0.03)
        state["busy"] = False
        body = seen.body
        if isinstance(body, list):
            return reply([{"jsonrpc": "2.0", "id": "batch", "result": {}}])
        return reply({"jsonrpc": "2.0", "id": body["id"], "result": {}})

    result = run_messages([LIST, [{**LIST, "id": "batch"}]], respond)
    assert state["overlapped"] is False
    assert result.messages() == [
        {"jsonrpc": "2.0", "id": 2, "result": {}},
        [{"jsonrpc": "2.0", "id": "batch", "result": {}}],
    ]


# --- 2026-07-28 clients send no initialize: each message names its revision in params._meta ----

MODERN_VERSION = "2026-07-28"
ENVELOPE = {
    "io.modelcontextprotocol/protocolVersion": MODERN_VERSION,
    "io.modelcontextprotocol/clientInfo": {"name": "bridge-test-client", "version": "1"},
    "io.modelcontextprotocol/clientCapabilities": {},
}
ROUTING_HEADERS = ("mcp-protocol-version", "mcp-method", "mcp-name")
HANDSHAKE_VERSIONS = ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]
# Expected values are the SDK's own encode_header_value output for each name.
ENCODED_NAMES = [
    ("notes://café/résumé ✓", "=?base64?bm90ZXM6Ly9jYWbDqS9yw6lzdW3DqSDinJM=?="),
    (" padded ", "=?base64?IHBhZGRlZCA=?="),
    ("tab\there", "=?base64?dGFiCWhlcmU=?="),
    ("=?base64?bGlzdA==?=", "=?base64?PT9iYXNlNjQ/YkdsemRBPT0/PQ==?="),
]


def modern(message):
    return {**message, "params": {**message.get("params", {}), "_meta": ENVELOPE}}


def routing(seen):
    return {name: seen.headers[name] for name in ROUTING_HEADERS if name in seen.headers}


def answer_by_id(seen):
    if isinstance(seen.body, dict) and "id" in seen.body:
        return reply({"jsonrpc": "2.0", "id": seen.body["id"], "result": {}})
    return httpx.Response(202)


def session_then(respond):
    """initialize gets session-1; everything else goes to `respond`."""
    def handler(seen):
        if isinstance(seen.body, dict) and seen.body.get("method") == "initialize":
            return reply({"jsonrpc": "2.0", "id": 1, "result": {}}, **{"mcp-session-id": "session-1"})
        return respond(seen)
    return handler


def sentence(id_, status=400):
    return {"jsonrpc": "2.0", "id": id_,
            "error": {"code": -32000, "message": f"Maestro Career Studio returned HTTP {status}."}}


@pytest.mark.parametrize(("message", "headers"), [
    ({"jsonrpc": "2.0", "id": "discover", "method": "server/discover"},
     {"mcp-method": "server/discover"}),
    ({**LIST, "id": "list"}, {"mcp-method": "tools/list"}),
    ({"jsonrpc": "2.0", "id": "call", "method": "tools/call",
      "params": {"name": "list_jobs", "arguments": {"limit": 5}}},
     {"mcp-method": "tools/call", "mcp-name": "list_jobs"}),
    ({"jsonrpc": "2.0", "id": "prompt", "method": "prompts/get", "params": {"name": "start_here"}},
     {"mcp-method": "prompts/get", "mcp-name": "start_here"}),
    ({"jsonrpc": "2.0", "id": "read", "method": "resources/read", "params": {"uri": "notes://setup"}},
     {"mcp-method": "resources/read", "mcp-name": "notes://setup"}),
], ids=["server-discover", "tools-list", "tools-call", "prompts-get", "resources-read"])
def test_a_2026_07_28_request_carries_its_version_method_and_name_as_headers(message, headers):
    message = modern(message)
    result = run_messages([message], answer_by_id)
    assert result.messages() == [{"jsonrpc": "2.0", "id": message["id"], "result": {}}]
    assert result.err == ""
    [seen] = result.requests
    assert routing(seen) == {"mcp-protocol-version": MODERN_VERSION, **headers}
    assert seen.line == compact(message), "the body is forwarded untouched"
    assert seen.session is None
    assert seen.headers["accept"] == "application/json, text/event-stream"


def test_a_name_outside_plain_printable_ascii_travels_in_the_sdks_base64_form():
    result = run_messages([modern({"jsonrpc": "2.0", "id": id_, "method": "resources/read",
                                   "params": {"uri": uri}})
                           for id_, (uri, _header) in enumerate(ENCODED_NAMES)], answer_by_id)
    assert [seen.headers["mcp-name"] for seen in result.requests] == [
        header for _uri, header in ENCODED_NAMES]


def test_a_name_or_method_that_is_not_a_string_sends_no_header_for_it():
    result = run_messages([
        modern({"jsonrpc": "2.0", "id": "number", "method": "tools/call", "params": {"name": 7}}),
        modern({"jsonrpc": "2.0", "id": "missing", "method": "resources/read"}),
        modern({"jsonrpc": "2.0", "id": "list", "method": ["tools/call"],
                "params": {"name": "list_jobs"}}),
    ], answer_by_id)
    version = {"mcp-protocol-version": MODERN_VERSION}
    assert [routing(seen) for seen in result.requests] == [
        {**version, "mcp-method": "tools/call"},
        {**version, "mcp-method": "resources/read"},
        version,
    ]
    assert [m["id"] for m in result.messages()] == ["number", "missing", "list"]


def test_2025_traffic_carries_none_of_the_routing_headers_and_keeps_its_session():
    result = run_messages([
        INITIALIZE, INITIALIZED, LIST,
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "list_jobs", "arguments": {}}},
        {**LIST, "id": 4, "params": {"_meta": {"progressToken": "progress-1"}}},
    ], session_then(answer_by_id))
    assert [routing(seen) for seen in result.requests] == [{}] * 5
    assert [seen.session for seen in result.requests] == [None] + ["session-1"] * 4


def test_a_2025_revision_named_in_meta_stays_on_its_session_with_no_routing_headers():
    # The SDK sends a header naming a handshake revision down the 2025 path, which needs the session.
    result = run_messages([INITIALIZE, *({
        "jsonrpc": "2.0", "id": id_, "method": "tools/call",
        "params": {"name": "list_jobs", "arguments": {},
                   "_meta": {**ENVELOPE, "io.modelcontextprotocol/protocolVersion": version}},
    } for id_, version in enumerate(HANDSHAKE_VERSIONS))], session_then(answer_by_id))
    assert len(result.messages()) == 1 + len(HANDSHAKE_VERSIONS)
    assert [routing(seen) for seen in result.requests[1:]] == [{}] * len(HANDSHAKE_VERSIONS)
    assert [seen.session for seen in result.requests[1:]] == ["session-1"] * len(HANDSHAKE_VERSIONS)


def test_a_2026_07_28_request_neither_sends_adopts_nor_clears_the_2025_session():
    def respond(seen):
        headers = {"mcp-session-id": "rogue"} if seen.body["id"] == "modern" else {}
        return reply({"jsonrpc": "2.0", "id": seen.body["id"], "result": {}}, **headers)

    result = run_messages([INITIALIZE, modern({**LIST, "id": "modern"}), LIST],
                          session_then(respond))
    assert [seen.session for seen in result.requests] == [None, None, "session-1"]
    assert [seen.headers.get("mcp-protocol-version") for seen in result.requests] == [
        None, MODERN_VERSION, None]


def test_a_404_to_a_2026_07_28_request_is_not_a_lost_session_so_nothing_is_replayed():
    def respond(seen):
        if seen.body["method"] == "notifications/initialized":
            return httpx.Response(202)
        return reply({"jsonrpc": "2.0", "id": seen.body["id"],
                      "error": {"code": -32601, "message": "Method not found"}}, 404)

    result = run_messages([
        INITIALIZE, INITIALIZED,
        modern({"jsonrpc": "2.0", "id": "listen", "method": "subscriptions/listen"}),
    ], session_then(respond))
    assert [seen.body["method"] for seen in result.requests] == [
        "initialize", "notifications/initialized", "subscriptions/listen"]
    assert result.messages()[1] == {
        "jsonrpc": "2.0", "id": "listen", "error": {"code": -32601, "message": "Method not found"}}


@pytest.mark.parametrize(("method", "status", "error"), [
    ("nope/method", 404, {"code": -32601, "message": "Method not found"}),
    ("tools/list", 400, {"code": -32022, "message": "Unsupported protocol version",
                         "data": {"supported": [MODERN_VERSION], "requested": "2099-01-01"}}),
    # Number.isInteger, which the Node twin checks, takes a whole float.
    ("nope/method", 404, {"code": -32601.0, "message": "Method not found"}),
], ids=["unknown-method", "unsupported-version", "whole-float-code"])
def test_a_2026_07_28_refusal_reaches_the_client_as_the_servers_json_rpc_error(method, status, error):
    result = run_messages(
        [modern({"jsonrpc": "2.0", "id": "refused", "method": method})],
        lambda seen: reply({"jsonrpc": "2.0", "id": seen.body["id"], "error": error}, status))
    assert result.messages() == [{"jsonrpc": "2.0", "id": "refused", "error": error}]
    assert result.err == ""


NO = {"code": -32602, "message": "No"}


# Each answer is not this request's JSON-RPC refusal, so the request gets the -32000 sentence.
@pytest.mark.parametrize(("id_", "status", "answer"), [
    ("other-id", 400, {"jsonrpc": "2.0", "id": "someone-else", "error": NO}),
    ("no-id", 400, {"jsonrpc": "2.0", "error": NO}),
    ("string-code", 400, {"jsonrpc": "2.0", "id": "string-code",
                          "error": {"code": "-32602", "message": "No"}}),
    ("fraction-code", 400, {"jsonrpc": "2.0", "id": "fraction-code",
                            "error": {"code": -32602.5, "message": "No"}}),
    ("no-jsonrpc", 400, {"id": "no-jsonrpc", "error": NO}),
    ("no-message", 400, {"jsonrpc": "2.0", "id": "no-message", "error": {"code": -32602}}),
    ("server-error", 500, {"jsonrpc": "2.0", "id": "server-error",
                           "error": {"code": -32603, "message": "Internal error"}}),
    ("html", 400, "<html>Bad request</html>"),
    ("null-body", 400, "null"),
    # JavaScript's === and Number.isInteger, as the Node twin compares, tell true from 1, a
    # missing id from null, and true from an integer; Python's == and isinstance(…, int) do not.
    (1, 400, {"jsonrpc": "2.0", "id": True, "error": NO}),
    (None, 400, {"jsonrpc": "2.0", "error": NO}),
    ("bool-code", 400, {"jsonrpc": "2.0", "id": "bool-code",
                        "error": {"code": True, "message": "No"}}),
], ids=["other-id", "no-id", "string-code", "fraction-code", "no-jsonrpc", "no-message",
        "server-error", "html", "null-body", "true-is-not-1", "missing-id-is-not-null",
        "bool-code"])
def test_any_other_answer_to_a_2026_07_28_request_keeps_the_http_sentence(id_, status, answer):
    text = answer if isinstance(answer, str) else json.dumps(answer)
    result = run_messages([modern({**LIST, "id": id_})],
                          lambda _seen: httpx.Response(status, text=text))
    assert result.messages() == [sentence(id_, status)]
    assert result.err == ""


def test_a_2026_07_28_notification_refused_with_a_json_rpc_error_writes_nothing():
    # A notification is owed no answer, so its fallback writes nothing.
    refusal = {"jsonrpc": "2.0", "id": None,
               "error": {"code": -32022, "message": "Unsupported protocol version"}}
    result = run_messages([modern({"jsonrpc": "2.0", "method": "notifications/cancelled",
                                   "params": {"requestId": "unknown"}})],
                          lambda _seen: reply(refusal, 400))
    assert result.out == b""
    assert result.err == ""
    assert [seen.body["method"] for seen in result.requests] == ["notifications/cancelled"]


def test_a_2026_07_28_notification_carries_version_and_method_responses_and_batches_go_as_before():
    result = run_messages([
        modern({"jsonrpc": "2.0", "method": "notifications/cancelled",
                "params": {"requestId": "call"}}),
        {"jsonrpc": "2.0", "id": "server-request", "result": {"_meta": ENVELOPE}},
        [modern({**LIST, "id": "batch"})],
    ], lambda _seen: httpx.Response(202))
    assert result.out == b""
    assert [routing(seen) for seen in result.requests] == [
        {"mcp-protocol-version": MODERN_VERSION, "mcp-method": "notifications/cancelled"}, {}, {},
    ]


# The bridge copies the codec and the lists below rather than import `mcp`, which would add
# ~200 ms to every start; these two tests hold them to the SDK's own.
@pytest.mark.parametrize("value", [
    *(name for name, _header in ENCODED_NAMES), "list_jobs", "notes://setup", MODERN_VERSION,
    "", " ", "end\n", "del\x7f", "nbsp\xa0", "\U0001f3af target", "=?base64??=", "=?base64?x",
    "~!@#$%^&*()"])
def test_the_header_codec_matches_the_sdks(value):
    from mcp.shared.inbound import decode_header_value, encode_header_value

    assert bridge.header_value(value) == encode_header_value(value)
    assert decode_header_value(bridge.header_value(value)) == value


def test_the_revision_lists_and_the_name_bearing_methods_match_the_sdks():
    from mcp.shared.inbound import NAME_BEARING_METHODS
    from mcp_types import PROTOCOL_VERSION_META_KEY
    from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS

    assert bridge.HANDSHAKE_VERSIONS == frozenset(HANDSHAKE_PROTOCOL_VERSIONS)
    assert bridge.HANDSHAKE_VERSIONS == frozenset(HANDSHAKE_VERSIONS)
    assert bridge.NAME_PARAMS == dict(NAME_BEARING_METHODS)
    assert bridge.PROTOCOL_VERSION_KEY == PROTOCOL_VERSION_META_KEY


def test_empty_stdin_exits_successfully():
    result = run_lines([], url="http://127.0.0.1:1")
    assert result.out == b""
    assert result.err == ""


def test_blank_lines_are_skipped():
    result = run_lines(["", "   "], url="http://127.0.0.1:1")
    assert result.out == b"" and result.err == ""


def test_text_content_blocks_pass_through_untouched():
    body = {"jsonrpc": "2.0", "id": 2,
            "result": {"content": [{"type": "text", "text": "[] ✓"}], "isError": False}}
    result = run_messages([{**LIST, "method": "tools/call"}], lambda _seen: reply(body))
    assert result.messages() == [body]


def test_the_replayed_handshake_failing_reports_the_http_status():
    state = {"first": True}

    def respond(seen):
        if seen.body["method"] == "initialize":
            if state["first"]:
                state["first"] = False
                return reply({"jsonrpc": "2.0", "id": 1, "result": {}}, **{"mcp-session-id": "s1"})
            return httpx.Response(503)
        return httpx.Response(404)

    result = run_messages([INITIALIZE, LIST], respond)
    assert result.messages()[1]["error"]["message"] == "Maestro Career Studio returned HTTP 503."


# --- the command ------------------------------------------------------------------------------

def child_env(home: Path) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", ""), "MAESTRO_HOME": str(home), "PYTHONPATH": str(BACKEND)}
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
@pytest.mark.parametrize("name", ["SIGINT", "SIGTERM"])
def test_a_signal_exits_successfully_while_stdin_remains_open(tmp_path, name):
    child = subprocess.Popen(
        [sys.executable, "-m", "maestro_cs", "mcp", "--url", "http://127.0.0.1:1"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=child_env(tmp_path / "home"), cwd=tmp_path)
    try:
        child.stdin.write((compact(LIST) + "\n").encode())
        child.stdin.flush()
        first = child.stdout.readline()
        child.send_signal(getattr(signal, name))
        assert child.wait(timeout=10) == 0
        err = child.stderr.read().decode()
    finally:
        child.kill()
        for stream in (child.stdin, child.stdout, child.stderr):
            stream.close()
    assert json.loads(first)["id"] == 2
    assert "Traceback" not in err
    assert not (tmp_path / "home").exists(), "mcp never creates the install folder"


def test_importing_the_bridge_writes_nothing_and_never_loads_the_app(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys, maestro_cs.bridge; assert not any(m == 'app' or m.startswith('app.') "
         "for m in sys.modules)"],
        capture_output=True, text=True, env=child_env(tmp_path / "home"), cwd=tmp_path)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_the_cli_runs_the_bridge_without_touching_the_install_folder(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("MAESTRO_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(bridge, "run", lambda url, profile: calls.append((url, profile)) or 0)
    monkeypatch.setattr(control, "load_context", lambda: pytest.fail("mcp must not load the context"))
    assert cli.main(["mcp"]) == 0
    assert cli.main(["mcp", "--profile", "hunt", "--url", "http://localhost:9"]) == 0
    assert calls == [(None, "full"), ("http://localhost:9", "hunt")]


# --- review follow-ups -------------------------------------------------------------------------

def test_a_404_after_an_initialize_with_no_session_id_does_not_replay():
    def respond(seen):
        if seen.body["method"] == "initialize":
            return reply({"jsonrpc": "2.0", "id": 1, "result": {}})  # no mcp-session-id
        return httpx.Response(404)

    result = run_messages([INITIALIZE, LIST], respond)
    assert [seen.body["method"] for seen in result.requests] == ["initialize", "tools/list"]
    assert result.messages()[1]["error"]["code"] == -32000


def test_a_session_header_on_a_later_response_does_not_change_the_session():
    def respond(seen):
        if seen.body["method"] == "initialize":
            return reply({"jsonrpc": "2.0", "id": 1, "result": {}}, **{"mcp-session-id": "session-1"})
        return reply({"jsonrpc": "2.0", "id": seen.body["id"], "result": {}},
                     **{"mcp-session-id": "intruder"})

    result = run_messages([INITIALIZE, LIST, {**LIST, "id": 3}], respond)
    assert [seen.session for seen in result.requests] == [None, "session-1", "session-1"]


def test_the_default_client_ignores_proxy_environment_variables():
    assert Bridge(BASE).client.trust_env is False


@pytest.mark.parametrize("line", ["[" * 100000, '{"a":' * 100000], ids=["arrays", "objects"])
def test_a_deeply_nested_line_is_a_parse_error_not_a_traceback(line):
    result = run_lines([line, compact(LIST)], lambda _seen: reply({"jsonrpc": "2.0", "id": 2, "result": {}}))
    assert result.messages() == [
        {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
        {"jsonrpc": "2.0", "id": 2, "result": {}},
    ]


def test_a_deeply_nested_response_is_an_invalid_json_error():
    result = run_messages([LIST], lambda _seen: httpx.Response(200, content=b"[" * 100000))
    assert result.messages()[0]["error"]["message"] == (
        "Maestro Career Studio returned an invalid JSON response.")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX pipes")
def test_a_client_that_closes_stdout_ends_the_bridge_with_exit_zero_and_no_noise(tmp_path):
    child = subprocess.Popen(
        [sys.executable, "-m", "maestro_cs", "mcp", "--url", "http://127.0.0.1:1"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=child_env(tmp_path / "home"), cwd=tmp_path)
    try:
        child.stdout.close()  # the reader is gone: the next write is EPIPE
        child.stdin.write((compact(LIST) + "\n").encode())
        child.stdin.close()
        assert child.wait(timeout=10) == 0
        err = child.stderr.read().decode()
    finally:
        child.kill()
        child.stderr.close()
    assert "Exception ignored" not in err and "Traceback" not in err
    assert err.strip() == NOT_RUNNING.format(url="http://127.0.0.1:1")  # the one stderr sentence


def test_a_non_utf8_maestro_env_is_one_sentence_and_exit_one(monkeypatch, tmp_path, capsys):
    home = tmp_path / "home"
    home.mkdir()
    (home / "maestro.env").write_bytes(b"MAESTRO_PORT=\xff\xfe\n")
    monkeypatch.setenv("MAESTRO_HOME", str(home))
    before = signal.getsignal(signal.SIGTERM)
    assert cli.main(["mcp"]) == 1
    err = capsys.readouterr().err
    assert err.startswith(f"Cannot read {home / 'maestro.env'}: ") and err.count("\n") == 1
    assert signal.getsignal(signal.SIGTERM) is before, "no handler is left installed"


@pytest.mark.skipif(sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="needs POSIX permissions and a non-root user")
def test_an_unreadable_maestro_env_is_one_sentence_and_exit_one(monkeypatch, tmp_path, capsys):
    home = tmp_path / "home"
    home.mkdir()
    env_file = home / "maestro.env"
    env_file.write_text("MAESTRO_PORT=18123\n", encoding="utf-8")
    env_file.chmod(0)
    monkeypatch.setenv("MAESTRO_HOME", str(home))
    try:
        assert cli.main(["mcp"]) == 1
    finally:
        env_file.chmod(0o600)
    err = capsys.readouterr().err
    assert err.startswith(f"Cannot read {env_file}: ") and err.count("\n") == 1
