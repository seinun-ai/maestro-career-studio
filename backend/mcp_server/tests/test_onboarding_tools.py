"""Onboarding MCP tools: the tool→client seam, and envelope wrapping.

Lambdas that swallow their arguments make this whole file vacuous — every
client stub here CAPTURES what the tool passed and the test asserts on it.
"""

import pytest
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

import mcp_server.server as srv
from mcp_server.client import BackendError

_INGEST_BODY = {
    "entities": [{"id": "e1", "kind": "project", "title": "Orbit", "org": None, "created": True}],
    "points": [{"id": "p1", "entity_id": "e1", "text": "Built Orbit"}],
    "entities_created": 1,
    "points_created": 1,
}


class _Capture:
    """Records every call's args/kwargs and returns a canned body."""

    def __init__(self, result):
        self.result = result
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result

    @property
    def last(self) -> tuple[tuple, dict]:
        assert self.calls, "the tool never called the client"
        return self.calls[-1]


@pytest.fixture
def hints_on(monkeypatch):
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})


def _stub(monkeypatch, name, result):
    capture = _Capture(result)
    monkeypatch.setattr(srv._client, name, capture)
    return capture


# ---- kb_ingest_resume -------------------------------------------------------


def test_kb_ingest_resume_passes_key_data_and_client_label(monkeypatch, hints_on):
    capture = _stub(monkeypatch, "kb_ingest_resume", _INGEST_BODY)
    monkeypatch.setenv("MAESTRO_CS_MCP_CLIENT", "Claude Desktop")
    data = {"contact": {"name": "A", "email": "a@x.com"}}

    out = srv.kb_ingest_resume("ds_resume", data)

    args, kwargs = capture.last
    assert args == ("ds_resume", data)
    assert kwargs == {"origin_detail": "Claude Desktop"}
    assert out["report"] == _INGEST_BODY


def test_kb_ingest_resume_hint_carries_the_returned_point_ids(monkeypatch, hints_on):
    _stub(monkeypatch, "kb_ingest_resume", _INGEST_BODY)
    out = srv.kb_ingest_resume("ds", {"contact": {"name": "A", "email": "a@x.com"}})
    assert out["next"]["ask_user"] is None
    approve = [o for o in out["next"]["options"] if o["tool"] == "kb_approve_points"]
    assert approve and approve[0]["args"] == {"point_ids": ["p1"]}


def test_kb_ingest_resume_brief_never_reads_settings(monkeypatch):
    _stub(monkeypatch, "kb_ingest_resume", _INGEST_BODY)

    def _boom():
        raise AssertionError("get_mcp_workflow_settings must not be called when brief=True")

    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", _boom)
    out = srv.kb_ingest_resume("ds", {"contact": {"name": "A", "email": "a@x.com"}}, brief=True)
    assert out["report"] == _INGEST_BODY
    assert out["next"] is None


def test_kb_ingest_resume_wraps_even_when_hints_are_off(monkeypatch):
    _stub(monkeypatch, "kb_ingest_resume", _INGEST_BODY)
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})
    out = srv.kb_ingest_resume("ds", {"contact": {"name": "A", "email": "a@x.com"}})
    assert "next" in out
    assert out["next"] is None


# ---- kb_approve_points ------------------------------------------------------


def test_kb_approve_points_only_approves(monkeypatch, hints_on):
    """Retiring is kb_retire_points: this tool sends state="approved" and nothing else."""
    capture = _stub(
        monkeypatch, "kb_approve_points",
        {"results": [{"id": "p1", "ok": True, "state": "approved", "detail": None}]},
    )

    out = srv.kb_approve_points(["p1"])

    args, kwargs = capture.last
    assert args == (["p1"],)
    assert kwargs == {"state": "approved"}
    assert out["results"][0]["state"] == "approved"
    assert any(o["tool"] == "create_base_resume_from_kb" for o in out["next"]["options"])


async def test_kb_approve_points_takes_no_state_and_is_not_destructive():
    tools = {tool.name: tool for tool in await srv.mcp.list_tools()}
    tool = tools["kb_approve_points"]
    assert set(tool.input_schema["properties"]) == {"point_ids"}
    assert tool.title == "Approve Career Points"
    assert tool.annotations.destructive_hint is False
    assert tools["kb_retire_points"].annotations.destructive_hint is False
    assert "kb_retire_points" in " ".join((srv.kb_approve_points.__doc__ or "").split())


@pytest.mark.parametrize("state", ["retired", "draft"])
async def test_an_old_state_argument_is_refused_not_dropped_and_approved(
    monkeypatch, hints_on, state
):
    """MCPServer drops an argument a tool does not declare, so an old call asking to retire
    would approve: any state but approved is refused, and nothing is written."""
    capture = _stub(monkeypatch, "kb_approve_points", {"results": []})
    async with Client(srv.mcp) as client:
        result = await client.call_tool(
            "kb_approve_points", {"point_ids": ["p1"], "state": state}
        )
    assert result.is_error
    assert result.content[0].text == (
        "kb_approve_points only approves; kb_retire_points retires points."
    )
    assert capture.calls == []


async def test_an_old_explicit_approved_state_still_approves(monkeypatch, hints_on):
    capture = _stub(
        monkeypatch, "kb_approve_points",
        {"results": [{"id": "p1", "ok": True, "state": "approved", "detail": None}]},
    )
    async with Client(srv.mcp) as client:
        result = await client.call_tool(
            "kb_approve_points", {"point_ids": ["p1"], "state": "approved"}
        )
    assert not result.is_error, result.content
    assert capture.last == ((["p1"],), {"state": "approved"})


def test_kb_approve_points_survives_a_non_dict_body(monkeypatch, hints_on):
    """Spreading a bare list would raise TypeError straight at the agent."""
    _stub(monkeypatch, "kb_approve_points", ["not", "a", "dict"])
    out = srv.kb_approve_points(["p1"])
    assert out["results"] == []
    assert "next" in out


# ---- create_base_resume_from_kb ---------------------------------------------


def test_create_base_resume_from_kb_forwards_every_argument(monkeypatch, hints_on):
    capture = _stub(monkeypatch, "create_base_resume_from_kb", {"slug": "ds"})
    _stub(monkeypatch, "get_setup_status", {"autofill": {"done": True}})

    out = srv.create_base_resume_from_kb(
        ["e1", "e2"],
        role_category="data_scientist",
        role_label="DS",
        display_name="Data Scientist",
        include_summary=True,
        summary="Reviewed summary",
    )

    args, kwargs = capture.last
    assert args == (["e1", "e2"],)
    assert kwargs == {
        "role_category": "data_scientist",
        "role_label": "DS",
        "display_name": "Data Scientist",
        "include_summary": True,
        "summary": "Reviewed summary",
    }
    assert out["base"] == {"slug": "ds"}
    assert {o["tool"] for o in out["next"]["options"]} == {"render_pdf"}


def test_create_base_resume_from_kb_hint_is_none_without_a_slug(monkeypatch, hints_on):
    _stub(monkeypatch, "create_base_resume_from_kb", ["unexpected"])
    out = srv.create_base_resume_from_kb(["e1"], role_label="DS")
    assert out["base"] == ["unexpected"]
    assert out["next"] is None


def test_create_base_resume_from_kb_offers_the_form_answers_while_setup_reads_them_open(
    monkeypatch, hints_on
):
    _stub(monkeypatch, "create_base_resume_from_kb", {"slug": "ds"})
    status = _stub(monkeypatch, "get_setup_status", {"autofill": {"done": False}})
    out = srv.create_base_resume_from_kb(["e1"], role_label="DS")
    assert status.calls
    assert "set_autofill_profile" in out["next"]["offer"]
    assert {o["tool"] for o in out["next"]["options"]} == {"render_pdf"}


def test_create_base_resume_from_kb_reads_no_setup_status_with_hints_off(monkeypatch):
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})
    _stub(monkeypatch, "create_base_resume_from_kb", {"slug": "ds"})
    status = _stub(monkeypatch, "get_setup_status", {"autofill": {"done": False}})
    out = srv.create_base_resume_from_kb(["e1"], role_label="DS")
    assert not status.calls
    assert out["next"] is None


def test_create_base_resume_from_kb_reads_no_setup_status_where_the_write_is_unregistered(
    monkeypatch, hints_on
):
    _stub(monkeypatch, "create_base_resume_from_kb", {"slug": "ds"})
    status = _stub(monkeypatch, "get_setup_status", {"autofill": {"done": False}})
    token = srv.CURRENT_PROFILE.set("templates")
    try:
        out = srv.create_base_resume_from_kb(["e1"], role_label="DS")
    finally:
        srv.CURRENT_PROFILE.reset(token)
    assert not status.calls
    assert "set_autofill_profile" not in out["next"]["offer"]


def test_create_base_resume_from_kb_keeps_its_hint_when_setup_status_fails(monkeypatch, hints_on):
    def _down():
        raise BackendError("setup status unavailable")

    _stub(monkeypatch, "create_base_resume_from_kb", {"slug": "ds"})
    monkeypatch.setattr(srv._client, "get_setup_status", _down)
    out = srv.create_base_resume_from_kb(["e1"], role_label="DS")
    assert {o["tool"] for o in out["next"]["options"]} == {"render_pdf"}
    assert "set_autofill_profile" not in out["next"]["offer"]


# ---- @_guard ----------------------------------------------------------------


@pytest.mark.parametrize(
    "tool,client_method,call",
    [
        ("kb_ingest_resume", "kb_ingest_resume", lambda: srv.kb_ingest_resume("ds", {})),
        ("kb_approve_points", "kb_approve_points", lambda: srv.kb_approve_points(["p1"])),
        ("create_base_resume_from_kb", "create_base_resume_from_kb",
         lambda: srv.create_base_resume_from_kb(["e1"], role_label="DS")),
    ],
)
def test_backend_errors_surface_as_tool_errors(monkeypatch, tool, client_method, call):
    """A direct caller gets _guard's ToolError carrying the backend's words."""
    def _raise(*_a, **_k):
        raise BackendError("backend said 422")

    monkeypatch.setattr(srv._client, client_method, _raise)
    with pytest.raises(ToolError, match="backend said 422"):
        call()
