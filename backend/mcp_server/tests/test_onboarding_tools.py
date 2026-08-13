"""Onboarding MCP tools: the tool→client seam, and envelope wrapping.

Lambdas that swallow their arguments make this whole file vacuous — every
client stub here CAPTURES what the tool passed and the test asserts on it.
"""

import pytest
from mcp.server.fastmcp.exceptions import ToolError

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


@pytest.mark.parametrize("state", ["approved", "retired"])
def test_kb_approve_points_passes_the_requested_state_through(monkeypatch, hints_on, state):
    """A hardcoded state="approved" here would APPROVE points the user asked
    to RETIRE — the one mutation this tool must never survive."""
    capture = _stub(
        monkeypatch, "kb_approve_points",
        {"results": [{"id": "p1", "ok": True, "state": state, "detail": None}]},
    )

    out = srv.kb_approve_points(["p1"], state=state)

    args, kwargs = capture.last
    assert args == (["p1"],)
    assert kwargs == {"state": state}
    assert out["results"][0]["state"] == state


def test_kb_approve_points_hint_reflects_the_requested_state(monkeypatch, hints_on):
    _stub(monkeypatch, "kb_approve_points",
          {"results": [{"id": "p1", "ok": True, "state": "approved", "detail": None}]})
    out = srv.kb_approve_points(["p1"])
    assert any(o["tool"] == "create_base_resume_from_kb" for o in out["next"]["options"])

    _stub(monkeypatch, "kb_approve_points",
          {"results": [{"id": "p1", "ok": True, "state": "retired", "detail": None}]})
    out = srv.kb_approve_points(["p1"], state="retired")
    assert out["next"]["options"] == []


def test_kb_approve_points_survives_a_non_dict_body(monkeypatch, hints_on):
    """Spreading a bare list would raise TypeError straight at the agent."""
    _stub(monkeypatch, "kb_approve_points", ["not", "a", "dict"])
    out = srv.kb_approve_points(["p1"])
    assert out["results"] == []
    assert "next" in out


# ---- create_base_resume_from_kb ---------------------------------------------


def test_create_base_resume_from_kb_forwards_every_argument(monkeypatch, hints_on):
    capture = _stub(monkeypatch, "create_base_resume_from_kb", {"slug": "ds"})

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
    """Without @_guard the agent gets a raw BackendError traceback."""
    def _raise(*_a, **_k):
        raise BackendError("backend said 422")

    monkeypatch.setattr(srv._client, client_method, _raise)
    with pytest.raises(ToolError, match="backend said 422"):
        call()
