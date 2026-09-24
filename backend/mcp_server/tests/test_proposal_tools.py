
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
        "attach_evidence_file",
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
    monkeypatch.delenv("CAREER_STUDIO_MCP_CLIENT", raising=False)
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
    monkeypatch.delenv("CAREER_STUDIO_MCP_CLIENT", raising=False)
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
        lambda proposal_id, status, consent=None, reason=None, fit=None, application_id=None: seen.update(
            pid=proposal_id, st=status
        ) or {"id": proposal_id, "status": status},
    )
    res = srv.mark_submitted("p1")
    assert res["status"] == "submitted"
    assert seen == {"pid": "p1", "st": "submitted"}


def test_mark_submitted_attested_passes_consent(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "transition_proposal",
        lambda proposal_id, status, consent=None, reason=None, fit=None, application_id=None, attested=False: seen.update(
            pid=proposal_id, st=status, consent=consent, attested=attested
        ) or {"id": proposal_id, "status": status},
    )
    res = srv.mark_submitted("p1", user_attested=True, channel="chat", note="user said submitted")
    assert res["status"] == "submitted"
    assert seen == {
        "pid": "p1", "st": "submitted", "attested": True,
        "consent": {"channel": "chat", "note": "user said submitted"},
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


def test_attach_evidence_file_reads_and_uploads(monkeypatch, tmp_path):
    png = tmp_path / "step-01.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    seen = {}

    def fake_request(method, path, files=None, data=None, **kw):
        seen.update(method=method, path=path, name=files["file"][0],
                    mime=files["file"][2], step=data["step"], kind=data.get("kind"))
        return {"ok": True}

    monkeypatch.setattr(srv._client, "_request", fake_request)
    res = srv.attach_evidence_file("p1", 1, "My Information", str(png), kind="step")
    assert res == {"ok": True}
    assert seen == {"method": "POST", "path": "/api/proposals/p1/evidence",
                    "name": "step-01.png", "mime": "image/png", "step": "1", "kind": "step"}


def test_attach_evidence_file_rejects_non_image(monkeypatch, tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_bytes(b"ssh-rsa AAAA fake key material")
    monkeypatch.setattr(srv._client, "_request",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not upload")))
    import pytest as _pytest
    from mcp.server.fastmcp.exceptions import ToolError
    with _pytest.raises(ToolError):
        srv.attach_evidence_file("p1", 1, "x", str(bad), kind="step")
