"""The audited login POST and its MCP result keep credentials out of logs and errors."""

import json
import logging
import traceback

import httpx
import pytest
import respx
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import Implementation

import mcp_server.server as srv
from app.write_origin import decode_detail
from mcp_server.client import BackendClient, BackendError
from mcp_server.profiles import allowed_tools

BASE = "http://test-backend"
URL = f"{BASE}/api/proposals/p1/job-site-login"
SECRET = "synthetic-job-site-password"
LOGIN = {"email": "ada@example.com", "password": SECRET}


@pytest.mark.parametrize("agent", [None, "claude-ai", "Café Agent"])
@respx.mock
def test_login_posts_the_proposal_path_and_mcp_origin(agent, caplog):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=LOGIN))
    # LiteLLM's import raises the HTTPX logger level independently of the root.
    caplog.set_level(logging.DEBUG, logger="httpx")
    with caplog.at_level(logging.DEBUG):
        result = BackendClient(BASE).get_job_site_login("p1", origin_detail=agent)
    assert result == LOGIN
    request = route.calls.last.request
    assert request.headers["X-Maestro-CS-Origin"] == "mcp"
    assert decode_detail(request.headers.get("X-Maestro-CS-Origin-Detail")) == agent
    assert request.content == b""
    assert caplog.records
    assert SECRET not in caplog.text


@pytest.mark.parametrize("profile", ["full", "apply", "hunt", "career", "explore", "templates"])
def test_login_is_available_in_the_apply_and_full_profiles(profile):
    tools = allowed_tools(profile)
    if profile == "full":
        assert "get_job_site_login" in srv.list_registered_tool_names()
    else:
        assert ("get_job_site_login" in tools) == (profile == "apply")


async def test_the_mcp_session_hands_over_the_login_and_attributes_it_without_logging(
    monkeypatch, caplog,
):
    monkeypatch.setattr(srv, "_client", BackendClient(BASE))
    with respx.mock:
        route = respx.post(URL).mock(return_value=httpx.Response(200, json=LOGIN))
        with caplog.at_level(logging.DEBUG):
            async with create_connected_server_and_client_session(
                srv.mcp, client_info=Implementation(name="Café Agent", version="0.1.0")
            ) as session:
                result = await session.call_tool("get_job_site_login", {"proposal_id": "p1"})
    assert not result.isError, result.content
    assert json.loads(result.content[0].text) == LOGIN
    assert decode_detail(route.calls.last.request.headers["X-Maestro-CS-Origin-Detail"]) == (
        "Café Agent"
    )
    assert SECRET not in caplog.text


_ERROR_RESPONSES = [
    httpx.Response(409, json={"detail": "full automation is off"}),
    httpx.Response(422, json={"detail": [{"loc": ["body"], "msg": SECRET, "input": LOGIN}]}),
    httpx.Response(500, json={"detail": LOGIN}),
    httpx.Response(502, text=SECRET),
    httpx.Response(200, text=f'{{"password": "{SECRET}"'),
]


@pytest.mark.parametrize(("status", "message"), [
    (None, "Maestro is not reachable; try again later."),
    (403, "Only the connected agent can ask for the job-site login."),
    (404, "No such proposal or no job-site login is saved in Settings."),
    (409, "Full automation is off, the job is not queued or approved, or its company is on the skip list."),
    (422, "The proposal ID is malformed."),
    (500, "The job-site login could not be retrieved; try again later."),
])
@respx.mock
def test_login_failure_uses_a_fixed_status_message_without_response_body(status, message):
    route = respx.post(URL)
    if status is None:
        route.mock(side_effect=httpx.ConnectError(SECRET))
    else:
        route.mock(return_value=httpx.Response(status, json={"detail": SECRET}))

    with pytest.raises(BackendError) as error:
        BackendClient(BASE).get_job_site_login("p1")

    assert str(error.value) == message
    assert error.value.status_code == status
    assert error.value.body is None
    assert SECRET not in str(error.value)


@pytest.mark.parametrize("response", _ERROR_RESPONSES)
@respx.mock
def test_login_errors_never_retain_or_report_a_response_body(response, caplog):
    respx.post(URL).mock(return_value=response)
    with caplog.at_level(logging.DEBUG), pytest.raises(BackendError) as error:
        BackendClient(BASE).get_job_site_login("p1")
    assert error.value.status_code == (response.status_code if response.is_error else None)
    assert error.value.body is None
    assert SECRET not in str(error.value)
    assert SECRET not in "".join(traceback.format_exception(error.value))
    assert SECRET not in caplog.text


@pytest.mark.parametrize("response", _ERROR_RESPONSES)
async def test_guard_errors_never_log_the_password_from_an_error_response(
    monkeypatch, caplog, response,
):
    monkeypatch.setattr(srv, "_client", BackendClient(BASE))
    with respx.mock:
        route = respx.post(URL).mock(return_value=response)
        with caplog.at_level(logging.DEBUG):
            async with create_connected_server_and_client_session(srv.mcp) as session:
                result = await session.call_tool("get_job_site_login", {"proposal_id": "p1"})
    assert result.isError
    assert route.call_count == 1
    assert SECRET not in repr(result.content)
    assert SECRET not in caplog.text


@pytest.mark.parametrize("error_type", [
    httpx.ConnectError, httpx.ReadTimeout, httpx.ReadError, httpx.RemoteProtocolError,
])
@respx.mock
def test_transport_errors_cannot_expose_a_password_in_their_message(error_type, caplog):
    respx.post(URL).mock(side_effect=error_type(SECRET))
    with caplog.at_level(logging.DEBUG), pytest.raises(BackendError) as error:
        BackendClient(BASE).get_job_site_login("p1")
    assert error.value.body is None
    assert SECRET not in "".join(traceback.format_exception(error.value))
    assert SECRET not in caplog.text


async def test_login_tool_has_a_proposal_argument_and_write_hints():
    tool = next(tool for tool in await srv.mcp.list_tools() if tool.name == "get_job_site_login")
    assert tool.inputSchema["required"] == ["proposal_id"]
    assert "ctx" not in tool.inputSchema["properties"]
    ann = tool.annotations
    assert (ann.readOnlyHint, ann.destructiveHint, ann.idempotentHint, ann.openWorldHint) == (
        False, False, True, False,
    )
