"""Tests for the chat interaction upgrade: propose_edits, kind-tagged
selections, analytics tools, and the card-state resolution endpoint."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.base_resume import BaseResume
from app.models.chat import ChatMessage, ChatSession
from app.schemas.resume_edit import ResumeEditRequest
from app.services.chat_agent import _context_block
from app.services.chat_tools import (
    ToolContext,
    check_ops_in_scope,
    execute_tool,
    openai_tool_specs,
)

SAMPLE_DATA = {
    "contact": {"name": "Sample", "email": "a@example.com"},
    "summary": "Summary",
    "skills": [{"category": "Core", "items": ["Python"]}],
    "experience": [
        {
            "company": "Acme",
            "role": "DS",
            "start_date": "2020",
            "enabled": True,
            "bullets": ["Built pipeline.", "Shipped model."],
        }
    ],
    "projects": [],
    "education": [],
    "certifications": [],
}


def _seed_base(db_session, slug="ds"):
    row = BaseResume(slug=slug, display_name="DS", data_json=deepcopy(SAMPLE_DATA))
    db_session.add(row)
    db_session.commit()
    return row


def _ops(*raw):
    return ResumeEditRequest.model_validate({"ops": list(raw)}).ops


# --- propose_edits ----------------------------------------------------------


def test_propose_edits_stages_without_writing(db_session):
    _seed_base(db_session)
    result = execute_tool(
        ToolContext(db=db_session),
        "propose_edits",
        {
            "target_kind": "base",
            "target_key": "ds",
            "ops": [
                {
                    "kind": "replace_bullet",
                    "section": "experience",
                    "index": 0,
                    "bullet_index": 0,
                    "value": "Built an ETL pipeline processing 2TB/day.",
                }
            ],
            "summary": "Tighten the pipeline bullet",
        },
    )
    proposal = result["proposal_ops"]
    assert proposal["target_kind"] == "base"
    assert proposal["target_key"] == "ds"
    assert proposal["ops_count"] == 1
    assert proposal["summary"] == "Tighten the pipeline bullet"
    assert proposal["ops"][0]["kind"] == "replace_bullet"
    # Nothing written: resume unchanged.
    row = db_session.get(BaseResume, "ds")
    assert row.data_json["experience"][0]["bullets"][0] == "Built pipeline."


def test_propose_edits_invalid_ops_and_unknown_target(db_session):
    _seed_base(db_session)
    bad = execute_tool(
        ToolContext(db=db_session),
        "propose_edits",
        {"target_kind": "base", "target_key": "ds", "ops": [{"kind": "nope"}]},
    )
    assert "error" in bad and "Invalid ops" in bad["error"]

    missing = execute_tool(
        ToolContext(db=db_session),
        "propose_edits",
        {
            "target_kind": "base",
            "target_key": "ghost",
            "ops": [{"kind": "replace_summary", "value": "x"}],
        },
    )
    assert "error" in missing and "not found" in missing["error"]


def test_propose_edits_respects_scope_guard(db_session):
    _seed_base(db_session)
    result = execute_tool(
        ToolContext(
            db=db_session,
            selections=[{"kind": "resume", "section": "experience", "index": 0}],
        ),
        "propose_edits",
        {
            "target_kind": "base",
            "target_key": "ds",
            "ops": [{"kind": "replace_summary", "value": "New summary"}],
        },
    )
    assert "error" in result and "outside the user's selected scope" in result["error"]


def test_propose_edits_dry_run_catches_apply_time_errors(db_session):
    """Out-of-range indices and invalid entry payloads fail at PROPOSE time."""
    _seed_base(db_session)
    out_of_range = execute_tool(
        ToolContext(db=db_session),
        "propose_edits",
        {
            "target_kind": "base",
            "target_key": "ds",
            "ops": [
                {
                    "kind": "replace_bullet",
                    "section": "experience",
                    "index": 9,
                    "bullet_index": 0,
                    "value": "x",
                }
            ],
        },
    )
    assert "error" in out_of_range
    assert "do not apply to the current resume" in out_of_range["error"]

    bad_entry = execute_tool(
        ToolContext(db=db_session),
        "propose_edits",
        {
            "target_kind": "base",
            "target_key": "ds",
            "ops": [{"kind": "add_entry", "section": "experience", "value": {"nope": 1}}],
        },
    )
    assert "error" in bad_entry


def test_analytics_gap_frequency_rejects_unknown_role_category(db_session):
    result = execute_tool(
        ToolContext(db=db_session),
        "analytics_gap_frequency",
        {"role_category": "Data Scientist"},
    )
    assert "error" in result and "data_scientist" in result["error"]


# --- kind-tagged selections -------------------------------------------------


def test_kb_entity_selection_does_not_block_resume_edits():
    ops = _ops({"kind": "replace_summary", "value": "x"})
    # A KB pin alone = no resume scope restriction.
    check_ops_in_scope(ops, [{"kind": "kb_entity", "entity_id": str(uuid4())}])


def test_legacy_kindless_selection_still_enforces():
    ops = _ops({"kind": "replace_summary", "value": "x"})
    try:
        check_ops_in_scope(ops, [{"section": "experience", "index": 0}])
    except Exception as e:
        assert "outside the user's selected scope" in str(e)
    else:
        raise AssertionError("expected scope rejection")


def test_context_block_describes_kb_entity_chips(db_session):
    entity_id = str(uuid4())
    block = _context_block(
        db_session,
        {
            "target_kind": "base",
            "target_key": "ds",
            "selections": [
                {"kind": "kb_entity", "entity_id": entity_id, "label": "Sample Project"},
                {"section": "experience", "index": 0, "label": "Acme"},
            ],
        },
    )
    assert "Pinned Career KB entity: Sample Project" in block
    assert entity_id in block
    assert "kb_get_entity" in block
    # Resume chip still produces the scope sentence, without the KB chip in it.
    assert "edit ONLY within these paths" in block
    assert "experience[0]" in block


# --- analytics tools --------------------------------------------------------


def test_analytics_tools_registered_and_return_service_output(db_session):
    names = {spec["name"] for spec in (s["function"] for s in openai_tool_specs())}
    assert {
        "analytics_activity",
        "analytics_gap_frequency",
        "analytics_base_summaries",
        "propose_edits",
    } <= names

    activity = execute_tool(
        ToolContext(db=db_session), "analytics_activity", {"granularity": "week", "weeks": 4}
    )
    assert activity["granularity"] == "week"
    assert len(activity["series"]) == 4

    gaps = execute_tool(ToolContext(db=db_session), "analytics_gap_frequency", {})
    assert gaps == {"common_gaps": [], "build_areas": []}

    _seed_base(db_session)
    summaries = execute_tool(ToolContext(db=db_session), "analytics_base_summaries", {})
    assert [row["slug"] for row in summaries] == ["ds"]


def test_analytics_activity_clamps_bad_weeks(db_session):
    result = execute_tool(
        ToolContext(db=db_session), "analytics_activity", {"weeks": 9999}
    )
    assert len(result["series"]) == 52 * 7


# --- card-state endpoint ----------------------------------------------------


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _client(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    return TestClient(app)


def _teardown():
    app.dependency_overrides.clear()


def _seed_tool_message(db_session, meta):
    session = ChatSession(title="t")
    db_session.add(session)
    db_session.flush()
    row = ChatMessage(
        session_id=session.id,
        role="tool",
        content="{}",
        tool_call_id="call_1",
        meta_json=meta,
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_card_state_stamps_proposal_ops(db_session):
    row = _seed_tool_message(
        db_session,
        {"proposal_ops": {"target_kind": "base", "target_key": "ds", "ops": [], "ops_count": 0, "summary": None}},
    )
    try:
        resp = _client(db_session).patch(
            f"/api/chat/messages/{row.id}/card-state", json={"status": "applied"}
        )
    finally:
        _teardown()
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta_json"]["card_state"]["status"] == "applied"
    # Original card payload untouched.
    assert "proposal_ops" in body["meta_json"]
    # Idempotent re-stamp with the same status is fine.
    try:
        again = _client(db_session).patch(
            f"/api/chat/messages/{row.id}/card-state", json={"status": "applied"}
        )
    finally:
        _teardown()
    assert again.status_code == 200

    # Conflicting re-stamp is rejected.
    try:
        conflict = _client(db_session).patch(
            f"/api/chat/messages/{row.id}/card-state", json={"status": "discarded"}
        )
    finally:
        _teardown()
    assert conflict.status_code == 409


def test_card_state_validates_role_meta_and_status(db_session):
    session = ChatSession(title="t")
    db_session.add(session)
    db_session.flush()
    user_row = ChatMessage(session_id=session.id, role="user", content="hi")
    plain_tool = ChatMessage(
        session_id=session.id, role="tool", content="{}", tool_call_id="c", meta_json=None
    )
    db_session.add_all([user_row, plain_tool])
    db_session.commit()

    client = _client(db_session)
    try:
        assert (
            client.patch(
                f"/api/chat/messages/{user_row.id}/card-state", json={"status": "applied"}
            ).status_code
            == 400
        )
        assert (
            client.patch(
                f"/api/chat/messages/{plain_tool.id}/card-state", json={"status": "applied"}
            ).status_code
            == 400
        )
        assert (
            client.patch(
                f"/api/chat/messages/{uuid4()}/card-state", json={"status": "applied"}
            ).status_code
            == 404
        )
        assert (
            client.patch(
                f"/api/chat/messages/{plain_tool.id}/card-state", json={"status": "bogus"}
            ).status_code
            == 422
        )
    finally:
        _teardown()


def test_card_state_accepts_legacy_proposal_cards(db_session):
    row = _seed_tool_message(
        db_session,
        {"proposal": {"target_kind": "base", "target_key": "ds", "project": {"name": "X", "bullets": []}}},
    )
    try:
        resp = _client(db_session).patch(
            f"/api/chat/messages/{row.id}/card-state", json={"status": "discarded"}
        )
    finally:
        _teardown()
    assert resp.status_code == 200
    assert resp.json()["meta_json"]["card_state"]["status"] == "discarded"
    assert resp.json()["meta_json"]["card_state"]["at"] <= datetime.now(UTC).isoformat()
