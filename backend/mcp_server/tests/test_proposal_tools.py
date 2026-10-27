
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import Implementation

import mcp_server.server as srv


def test_proposal_tools_registered():
    names = set(srv.list_registered_tool_names())
    expected = {
        "propose_application",
        "list_proposals",
        "get_proposal",
        "record_decision",
        "record_consent",
        "attach_evidence",
        "mark_submitted",
        "report_failure",
        "request_decision",
        "resume_proposal",
        "get_final_review",
        "record_triage",
    }
    assert expected <= names


def test_propose_application_tool_calls_client(monkeypatch):
    seen = {}
    monkeypatch.delenv("MAESTRO_CS_MCP_CLIENT", raising=False)
    monkeypatch.setattr(
        srv._client,
        "propose_application",
        lambda job_id, base_resume=None, fit=None, plan=None, application_id=None, referral_id=None,
        origin_detail=None: seen.update(
            j=job_id, f=fit, p=plan, a=application_id, r=referral_id, o=origin_detail
        ) or {"id": "p1"},
    )
    res = srv.propose_application("j1", fit={"chosen_base": "hybrid"}, plan={"summary": "p"})
    assert res == {"id": "p1"}
    assert seen == {
        "j": "j1", "f": {"chosen_base": "hybrid"}, "p": {"summary": "p"}, "a": None, "r": None,
        "o": None,
    }


def test_propose_application_passes_the_client_label(monkeypatch):
    seen = {}
    monkeypatch.setenv("MAESTRO_CS_MCP_CLIENT", "codex-mcp-client")
    monkeypatch.setattr(
        srv._client, "propose_application", lambda job_id, **kw: seen.update(kw) or {"id": "p1"}
    )
    srv.propose_application("j1")
    assert seen["origin_detail"] == "codex-mcp-client"


async def test_propose_application_keeps_ctx_out_of_its_schema():
    tools = {tool.name: tool for tool in await srv.mcp.list_tools()}
    assert "ctx" not in tools["propose_application"].inputSchema["properties"]


async def test_propose_application_names_the_client_its_session_declared(monkeypatch):
    """End to end through the installed mcp package: the name a client sends
    in `initialize` (clientInfo.name) reaches the backend call as the filer,
    with no env fallback set. This is the plumbing _client_label assumes."""
    seen = {}
    monkeypatch.delenv("MAESTRO_CS_MCP_CLIENT", raising=False)
    monkeypatch.setattr(
        srv._client, "propose_application", lambda job_id, **kw: seen.update(kw) or {"id": "p1"}
    )
    async with create_connected_server_and_client_session(
        srv.mcp, client_info=Implementation(name="claude-ai", version="0.1.0")
    ) as session:
        result = await session.call_tool("propose_application", {"job_id": "j1"})
    assert not result.isError, result.content
    assert seen["origin_detail"] == "claude-ai"


def test_record_decision_tool_calls_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "record_decision",
        lambda proposal_id, fit, application_id=None: seen.update(
            pid=proposal_id, fit=fit, app=application_id
        ) or {"id": proposal_id, "status": "pending_review"},
    )
    res = srv.record_decision("p1", fit={"chosen_base": "ml_eng"}, application_id="a1")
    assert res["status"] == "pending_review"
    assert seen == {"pid": "p1", "fit": {"chosen_base": "ml_eng"}, "app": "a1"}


def test_record_consent_tool_calls_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "transition_proposal",
        lambda proposal_id, status, consent=None, reason=None, fit=None, application_id=None: seen.update(
            pid=proposal_id, st=status, consent=consent
        ) or {"id": proposal_id, "status": status},
    )
    res = srv.record_consent("p1", action="approved", channel="chat", note="user approved")
    assert res["status"] == "approved"
    assert seen == {"pid": "p1", "st": "approved", "consent": {"channel": "chat", "note": "user approved"}}


def test_mark_submitted_tool_calls_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "transition_proposal",
        lambda proposal_id, status, consent=None, reason=None, fit=None, application_id=None,
        origin_detail=None: seen.update(pid=proposal_id, st=status)
        or {"id": proposal_id, "status": status},
    )
    res = srv.mark_submitted("p1")
    assert res["status"] == "submitted"
    assert seen == {"pid": "p1", "st": "submitted"}


def test_mark_submitted_attested_passes_consent(monkeypatch):
    from types import SimpleNamespace

    seen = {}
    monkeypatch.setattr(
        srv._client,
        "transition_proposal",
        lambda proposal_id, status, consent=None, reason=None, fit=None, application_id=None,
        attested=False, origin_detail=None: seen.update(
            pid=proposal_id, st=status, consent=consent, attested=attested,
            origin_detail=origin_detail,
        ) or {"id": proposal_id, "status": status},
    )
    ctx = SimpleNamespace(session=SimpleNamespace(
        client_params=SimpleNamespace(clientInfo=SimpleNamespace(name="claude-ai"))))
    res = srv.mark_submitted("p1", user_attested=True, channel="chat", note="user said submitted",
                             ctx=ctx)
    assert res["status"] == "submitted"
    # the client's name rides along for the application's status log
    assert seen == {
        "pid": "p1", "st": "submitted", "attested": True,
        "consent": {"channel": "chat", "note": "user said submitted"}, "origin_detail": "claude-ai",
    }


def test_record_triage_maps_action_to_bulk_transition(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "bulk_transition_proposals",
        lambda proposal_ids, status, channel, note=None, reason=None: seen.update(
            ids=proposal_ids, st=status, ch=channel, note=note, reason=reason
        ) or {"results": [{"id": i, "ok": True, "status": status} for i in proposal_ids]},
    )
    res = srv.record_triage(["p1", "p2"], action="accept", channel="mcp",
                            note="user criteria: score>=50")
    assert all(r["ok"] for r in res["results"])
    assert seen == {"ids": ["p1", "p2"], "st": "accepted", "ch": "mcp",
                    "note": "user criteria: score>=50", "reason": None}


def test_record_triage_decline_maps_to_rejected(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "bulk_transition_proposals",
        lambda proposal_ids, status, channel, note=None, reason=None: seen.update(st=status, reason=reason)
        or {"results": []},
    )
    srv.record_triage(["p1"], action="decline", reason="low fit")
    assert seen == {"st": "rejected", "reason": "low fit"}


def test_report_failure_tool_calls_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "report_failure",
        lambda proposal_id, reason: seen.update(
            pid=proposal_id, reason=reason
        ) or {"id": proposal_id, "status": "needs_human" if reason != "submission_uncertain" else "submission_uncertain"},
    )
    res = srv.report_failure("p1", reason="captcha wall")
    assert res["status"] == "needs_human"
    assert seen == {"pid": "p1", "reason": "captcha wall"}


def test_request_decision_tool_calls_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "request_decision",
        lambda proposal_id, reason: seen.update(pid=proposal_id, reason=reason)
        or {"id": proposal_id, "status": "needs_decision"},
    )
    res = srv.request_decision("p1", reason="ambiguous")
    assert res["status"] == "needs_decision"
    assert seen == {"pid": "p1", "reason": "ambiguous"}


def test_resume_proposal_tool_calls_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "resume_proposal",
        lambda proposal_id: seen.update(pid=proposal_id) or {"id": proposal_id, "status": "pending_review"},
    )
    res = srv.resume_proposal("p1")
    assert res["status"] == "pending_review"
    assert seen == {"pid": "p1"}


def test_get_final_review_tool_calls_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "get_final_review",
        lambda proposal_id: seen.update(pid=proposal_id) or {"proposal_id": proposal_id},
    )
    res = srv.get_final_review("p1")
    assert res == {"proposal_id": "p1"}
    assert seen == {"pid": "p1"}


_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _capture_upload(monkeypatch):
    seen = {}

    def fake_request(method, path, files=None, data=None, **kw):
        seen.update(method=method, path=path, name=files["file"][0],
                    mime=files["file"][2], body=files["file"][1], step=data["step"],
                    label=data["label"], kind=data.get("kind"))
        return {"ok": True}

    monkeypatch.setattr(srv._client, "_request", fake_request)
    return seen


def _no_upload(monkeypatch):
    monkeypatch.setattr(srv._client, "_request",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not upload")))


def test_attach_evidence_uploads_an_inline_image(monkeypatch):
    import base64

    seen = _capture_upload(monkeypatch)
    res = srv.attach_evidence("p1", 3, "Review", kind="final_review",
                              image_base64=base64.b64encode(_PNG).decode())
    assert res == {"ok": True}
    assert seen == {"method": "POST", "path": "/api/proposals/p1/evidence", "name": "evidence.png",
                    "mime": "image/png", "body": _PNG, "step": "3", "label": "Review",
                    "kind": "final_review"}


def test_attach_evidence_reads_and_uploads_a_file(monkeypatch, tmp_path):
    png = tmp_path / "step-01.png"
    png.write_bytes(_PNG)
    seen = _capture_upload(monkeypatch)
    res = srv.attach_evidence("p1", 1, "My Information", file_path=str(png), kind="step")
    assert res == {"ok": True}
    assert seen == {"method": "POST", "path": "/api/proposals/p1/evidence", "name": "step-01.png",
                    "mime": "image/png", "body": _PNG, "step": "1", "label": "My Information",
                    "kind": "step"}


def test_attach_evidence_refuses_a_file_that_is_not_an_image(monkeypatch, tmp_path):
    import pytest
    from mcp.server.fastmcp.exceptions import ToolError

    bad = tmp_path / "notes.txt"
    bad.write_bytes(b"ssh-rsa AAAA fake key material")
    _no_upload(monkeypatch)
    with pytest.raises(ToolError, match="not a PNG or JPEG"):
        srv.attach_evidence("p1", 1, "x", file_path=str(bad), kind="step")


def test_attach_evidence_takes_exactly_one_input(monkeypatch, tmp_path):
    import base64

    import pytest
    from mcp.server.fastmcp.exceptions import ToolError

    png = tmp_path / "shot.png"
    png.write_bytes(_PNG)
    _no_upload(monkeypatch)
    with pytest.raises(ToolError, match="exactly one of image_base64 or file_path.*neither"):
        srv.attach_evidence("p1", 1, "x")
    with pytest.raises(ToolError, match="exactly one of image_base64 or file_path.*both"):
        srv.attach_evidence("p1", 1, "x", image_base64=base64.b64encode(_PNG).decode(),
                            file_path=str(png))


async def test_attach_evidence_schema_takes_either_input_and_the_file_tool_is_gone():
    from mcp_server.profiles import APPLY_TOOLS, PROFILE_ALLOWLISTS

    tools = {tool.name: tool for tool in await srv.mcp.list_tools()}
    schema = tools["attach_evidence"].inputSchema
    assert set(schema["required"]) == {"proposal_id", "step", "label"}
    props = schema["properties"]
    assert {"image_base64", "file_path"} <= set(props)
    assert props["kind"]["enum"] == ["step", "final_review", "submission_receipt"]
    assert props["kind"]["default"] == "step"
    file_text = props["file_path"]["description"]
    for fact in (".playwright-mcp", "5 MB", "PNG", "JPEG"):
        assert fact in file_text, fact
    assert "attach_evidence" in APPLY_TOOLS
    assert "attach_evidence_file" not in tools
    assert all("attach_evidence_file" not in allow for allow in PROFILE_ALLOWLISTS.values() if allow)


async def test_automatic_consent_channels_are_exposed_in_tool_schemas():
    tools = {tool.name: tool for tool in await srv.mcp.list_tools()}
    for name in ("record_consent", "mark_submitted"):
        assert tools[name].inputSchema["properties"]["channel"]["enum"] == [
            "chat", "slack", "mcp", "auto",
        ]


def test_mark_submitted_auto_forwards_the_agents_attestation(monkeypatch):
    import json
    import httpx
    import respx
    from mcp_server.client import BackendClient

    monkeypatch.setattr(srv, "_client", BackendClient("http://test-backend"))
    with respx.mock() as mock:
        route = mock.patch("http://test-backend/api/proposals/p1").mock(
            return_value=httpx.Response(200, json={"id": "p1", "status": "submitted"}))
        result = srv.mark_submitted("p1", channel="auto", note="Confirmation email received")
    assert result["status"] == "submitted"
    assert json.loads(route.calls.last.request.read()) == {
        "status": "submitted", "attested": True,
        "consent": {"channel": "auto", "note": "Confirmation email received"},
    }


async def test_record_consent_accepts_auto_through_an_mcp_session(monkeypatch):
    import json
    import httpx
    import respx
    from mcp_server.client import BackendClient

    monkeypatch.setattr(srv, "_client", BackendClient("http://test-backend"))
    with respx.mock(assert_all_called=False) as mock:
        route = mock.patch("http://test-backend/api/proposals/p1").mock(
            return_value=httpx.Response(200, json={"id": "p1", "status": "approved"}))
        async with create_connected_server_and_client_session(srv.mcp) as session:
            result = await session.call_tool("record_consent", {
                "proposal_id": "p1", "action": "approved", "channel": "auto", "note": "clean review",
            })
    assert not result.isError, result.content
    assert json.loads(route.calls.last.request.read()) == {
        "status": "approved", "consent": {"channel": "auto", "note": "clean review"},
    }
