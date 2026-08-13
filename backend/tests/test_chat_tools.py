from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint
from app.schemas.resume_edit import ResumeEditRequest
from app.services import base_resume_render, llm
from app.services.chat_tools import (
    ToolContext,
    ToolError,
    check_ops_in_scope,
    execute_tool,
    openai_tool_specs,
    tool_edit_resume,
    tool_kb_get_entity,
    tool_propose_project,
)
from app.services.resume_versions import get_versions

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
        },
        {
            "company": "Beta",
            "role": "MLE",
            "start_date": "2022",
            "enabled": True,
            "bullets": ["Did infra."],
        },
    ],
    "projects": [],
    "education": [],
    "certifications": [],
}


def _ops(*raw):
    return ResumeEditRequest.model_validate({"ops": list(raw)}).ops


def _seed(db_session, monkeypatch, tmp_path):
    # The edit pipeline lives in resume_ops now (SYSTEM.md §11 #2) — patch the
    # render + data-dir seams there.
    from app.services import resume_ops

    monkeypatch.setattr(base_resume_render, "render_base_resume", lambda *a, **k: None)
    monkeypatch.setattr(
        resume_ops.base_resume_render, "render_base_resume", lambda *a, **k: None
    )
    monkeypatch.setattr(resume_ops.settings, "base_resumes_dir", tmp_path)
    row = BaseResume(slug="ds", display_name="DS", data_json=deepcopy(SAMPLE_DATA))
    db_session.add(row)
    db_session.commit()
    return row


# --- scope guard -----------------------------------------------------------


def test_no_selection_allows_everything():
    ops = _ops({"kind": "replace_summary", "value": "x"})
    check_ops_in_scope(ops, [])  # no raise


def test_item_selection_allows_ops_on_that_item_only():
    selections = [{"section": "experience", "index": 0}]
    ok = _ops({"kind": "add_bullet", "section": "experience", "index": 0, "text": "Y."})
    check_ops_in_scope(ok, selections)

    other_item = _ops({"kind": "add_bullet", "section": "experience", "index": 1, "text": "Y."})
    with pytest.raises(ToolError, match="outside the user's selected scope"):
        check_ops_in_scope(other_item, selections)

    other_section = _ops({"kind": "replace_summary", "value": "x"})
    with pytest.raises(ToolError):
        check_ops_in_scope(other_section, selections)


def test_bullet_selection_is_narrowest():
    selections = [{"section": "experience", "index": 0, "bullet_index": 1}]
    ok = _ops(
        {
            "kind": "replace_bullet",
            "section": "experience",
            "index": 0,
            "bullet_index": 1,
            "value": "New.",
        }
    )
    check_ops_in_scope(ok, selections)
    with pytest.raises(ToolError):
        check_ops_in_scope(
            _ops(
                {
                    "kind": "replace_bullet",
                    "section": "experience",
                    "index": 0,
                    "bullet_index": 0,
                    "value": "New.",
                }
            ),
            selections,
        )


def test_section_selection_allows_add_entry():
    selections = [{"section": "projects"}]
    ops = _ops({"kind": "add_entry", "section": "projects", "value": {"name": "P"}})
    check_ops_in_scope(ops, selections)
    with pytest.raises(ToolError):
        check_ops_in_scope(ops, [{"section": "projects", "index": 0}])


def test_extra_section_op_scopes_to_its_own_key():
    # A custom-section op scopes to the section's own KEY (matching the per-key
    # chips the scope picker emits), NOT a fixed "extra_sections" block.
    op = _ops({"kind": "add_extra_section",
               "value": {"key": "awards", "title": "Awards", "type": "bullets", "bullets": ["x"]}})
    # whole-resume scope: allowed.
    check_ops_in_scope(op, [])
    # a fixed core-section selection does not cover a custom-section op -> rejected.
    with pytest.raises(ToolError, match="awards"):
        check_ops_in_scope(op, [{"section": "experience", "index": 0}])
    # an exact per-key chip covers it.
    check_ops_in_scope(op, [{"section": "awards"}])
    # a mismatched per-key chip does NOT.
    with pytest.raises(ToolError):
        check_ops_in_scope(op, [{"section": "publications"}])
    # the whole-block "extra_sections" chip (if the picker emits it) covers it too.
    check_ops_in_scope(op, [{"section": "extra_sections"}])


def test_replace_extra_section_scoped_by_section_key():
    # F3 regression: scoping chat to a custom section must ALLOW ops targeting
    # that key and BLOCK ops targeting a different one — the old fixed-block scope
    # rejected both.
    op = _ops({"kind": "replace_extra_section", "section_key": "publications",
               "value": {"key": "publications", "title": "Publications",
                         "type": "bullets", "bullets": ["y"]}})
    check_ops_in_scope(op, [{"section": "publications"}])  # allowed
    with pytest.raises(ToolError):
        check_ops_in_scope(op, [{"section": "awards"}])  # blocked


# --- edit_resume tool ------------------------------------------------------


def test_edit_resume_applies_persists_and_versions(db_session, monkeypatch, tmp_path):
    row = _seed(db_session, monkeypatch, tmp_path)
    ctx = ToolContext(db=db_session, message_id="msg-1")

    result = tool_edit_resume(
        ctx,
        "base",
        "ds",
        [{"kind": "replace_summary", "value": "Sharper summary."}],
    )

    card = result["change_card"]
    assert card["resume_kind"] == "base" and card["resume_key"] == "ds"
    assert card["version_number"] == 1
    db_session.refresh(row)
    assert row.data_json["summary"] == "Sharper summary."
    versions = get_versions(db_session, "base", "ds")
    assert versions[0].source == "chat"
    assert versions[0].source_ref == "msg-1"
    assert (tmp_path / "ds.json").exists()


def test_edit_resume_accepts_and_applies_extra_section_ops(db_session, monkeypatch, tmp_path):
    row = _seed(db_session, monkeypatch, tmp_path)
    ctx = ToolContext(db=db_session, message_id="msg-x")

    result = tool_edit_resume(
        ctx, "base", "ds",
        [{"kind": "add_extra_section",
          "value": {"key": "publications", "title": "Publications", "type": "entries",
                    "entries": [{"heading": "A paper", "date": "2025"}]}}],
    )
    assert result["change_card"]["ops_count"] == 1
    db_session.refresh(row)
    assert row.data_json["extra_sections"][0]["key"] == "publications"
    assert row.data_json["extra_sections"][0]["entries"][0]["heading"] == "A paper"


def test_edit_resume_extra_section_spec_lists_the_ops():
    specs = {spec["function"]["name"]: spec["function"] for spec in openai_tool_specs()}
    desc = specs["edit_resume"]["description"]
    for kind in (
        "add_extra_section",
        "replace_extra_section",
        "remove_extra_section",
        "move_extra_section",
    ):
        assert kind in desc


def test_edit_resume_out_of_scope_returns_error_payload(db_session, monkeypatch, tmp_path):
    _seed(db_session, monkeypatch, tmp_path)
    ctx = ToolContext(
        db=db_session, message_id="m", selections=[{"section": "experience", "index": 0}]
    )
    result = execute_tool(
        ctx, "edit_resume", {"kind": "base", "key": "ds", "ops": [{"kind": "replace_summary", "value": "x"}]}
    )
    assert "outside the user's selected scope" in result["error"]
    assert get_versions(db_session, "base", "ds") == []


def test_edit_resume_bad_op_is_tool_error_not_crash(db_session, monkeypatch, tmp_path):
    _seed(db_session, monkeypatch, tmp_path)
    ctx = ToolContext(db=db_session)
    result = execute_tool(
        ctx,
        "edit_resume",
        {
            "kind": "base",
            "key": "ds",
            "ops": [{"kind": "replace_bullet", "section": "experience", "index": 9, "bullet_index": 0, "value": "x"}],
        },
    )
    assert "error" in result


def test_propose_project_validates_without_writing(db_session, monkeypatch, tmp_path):
    row = _seed(db_session, monkeypatch, tmp_path)
    ctx = ToolContext(db=db_session)
    result = tool_propose_project(
        ctx, "base", "ds", {"name": "Churn Model", "bullets": ["Cut churn 12%."]}
    )
    assert result["proposal"]["project"]["name"] == "Churn Model"
    db_session.refresh(row)
    assert row.data_json["projects"] == []  # nothing written

    with pytest.raises(ToolError, match="Invalid project entry"):
        tool_propose_project(ctx, "base", "ds", {"bullets": []})


def test_unknown_tool_returns_error():
    assert "error" in execute_tool(ToolContext(db=None), "nope", {})


def test_chat_list_base_resumes_hides_soft_deleted(db_session):
    db_session.add_all(
        [
            BaseResume(slug="ds", display_name="DS", data_json=deepcopy(SAMPLE_DATA)),
            BaseResume(
                slug="gone",
                display_name="Gone",
                data_json=deepcopy(SAMPLE_DATA),
                deleted_at=datetime.now(UTC),
            ),
        ]
    )
    db_session.commit()
    ctx = ToolContext(db=db_session)

    assert execute_tool(ctx, "list_base_resumes", {}) == [
        {"slug": "ds", "display_name": "DS"}
    ]


# --- Career KB tools -------------------------------------------------------


def _seed_kb_entity(db_session):
    entity = KBEntity(
        kind="project",
        title="Orbit",
        org="Fictional Data Studio",
        status="ongoing",
        detail_json={"tech": "FastAPI"},
        notes="Shipped first to an internal cohort.",
    )
    db_session.add(entity)
    db_session.flush()
    point = KBPoint(
        entity_id=entity.id,
        text="Built the initial retrieval pipeline.",
        state="approved",
        origin="manual",
    )
    db_session.add(point)
    db_session.commit()
    return entity, point


def test_kb_tool_specs_are_registered_with_expected_arguments():
    specs = {spec["function"]["name"]: spec["function"] for spec in openai_tool_specs()}
    assert {"kb_list_entities", "kb_get_entity", "kb_capture"} <= specs.keys()
    assert specs["kb_list_entities"]["parameters"]["required"] == []
    assert specs["kb_get_entity"]["parameters"]["required"] == ["entity_id"]
    assert specs["kb_capture"]["parameters"]["required"] == ["text"]
    assert specs["kb_capture"]["parameters"]["properties"]["entity_id"] == {
        "type": "string",
        "format": "uuid",
    }


def test_kb_list_and_get_entity_return_json_detail(db_session):
    entity, point = _seed_kb_entity(db_session)
    ctx = ToolContext(db=db_session)

    listed = execute_tool(ctx, "kb_list_entities", {})
    assert listed == [
        {
            "id": str(entity.id),
            "kind": "project",
            "title": "Orbit",
            "org": "Fictional Data Studio",
            "status": "ongoing",
        }
    ]

    detail = execute_tool(ctx, "kb_get_entity", {"entity_id": str(entity.id)})
    assert detail["id"] == str(entity.id)
    assert detail["notes"] == "Shipped first to an internal cohort."
    assert detail["points"][0]["id"] == str(point.id)
    assert detail["points"][0]["text"] == "Built the initial retrieval pipeline."
    assert detail["points"][0]["state"] == "approved"


def test_kb_get_entity_rejects_malformed_and_unknown_ids(db_session):
    ctx = ToolContext(db=db_session)

    with pytest.raises(ToolError, match="Invalid KB entity id"):
        tool_kb_get_entity(ctx, "definitely-not-a-uuid")

    missing = execute_tool(ctx, "kb_get_entity", {"entity_id": str(uuid4())})
    assert "not found" in missing["error"].lower()


def test_kb_capture_persists_chat_drafts_and_returns_card_shape(db_session, monkeypatch):
    entity, _ = _seed_kb_entity(db_session)

    from app.services import chat_tools

    refresh_calls = []
    monkeypatch.setattr(
        chat_tools.career_exports,
        "best_effort_refresh",
        lambda db: refresh_calls.append(db),
    )

    def fake_call_openai(**kwargs):
        assert kwargs["response_format"] == "json"
        return {
            "entity_id": str(entity.id),
            "new_entity": None,
            "points": ["Shipped hybrid retrieval to the pilot cohort."],
        }

    monkeypatch.setattr(llm, "call_openai", fake_call_openai)
    result = execute_tool(
        ToolContext(db=db_session),
        "kb_capture",
        {
            "text": "This week I shipped hybrid retrieval to the pilot cohort.",
            "entity_id": str(entity.id),
        },
    )

    assert result == {
        "kb_capture": {
            "entity_id": str(entity.id),
            "entity_title": "Orbit",
            "point_count": 1,
        }
    }
    assert refresh_calls == [db_session]

    # A second session can see the row, proving the tool committed rather than
    # merely flushing into the chat agent's session.
    with Session(bind=db_session.get_bind()) as observer:
        point = observer.scalars(
            select(KBPoint).where(KBPoint.text == "Shipped hybrid retrieval to the pilot cohort.")
        ).one()
        assert point.state == "draft"
        assert point.origin == "chat"
        assert point.entity_id == entity.id


def test_kb_capture_rejects_bad_ids_and_missing_entities_without_writes(db_session):
    ctx = ToolContext(db=db_session)

    malformed = execute_tool(
        ctx,
        "kb_capture",
        {"text": "Shipped something.", "entity_id": "not-a-uuid"},
    )
    assert "invalid kb capture" in malformed["error"].lower()

    missing = execute_tool(
        ctx,
        "kb_capture",
        {"text": "Shipped something.", "entity_id": str(uuid4())},
    )
    assert "not found" in missing["error"].lower()
    assert db_session.scalars(select(KBPoint)).all() == []


def test_kb_capture_rolls_back_partial_service_writes(db_session, monkeypatch):
    from app.services import chat_tools

    def partial_failure(session, text, entity_id=None, origin="manual"):
        assert text == "This should not persist."
        assert entity_id is None
        assert origin == "chat"
        session.add(KBEntity(kind="project", title="Partial", status="ongoing"))
        session.flush()
        raise ValueError("capture output was invalid")

    monkeypatch.setattr(chat_tools.kb_ingest, "capture", partial_failure)
    result = execute_tool(
        ToolContext(db=db_session),
        "kb_capture",
        {"text": "This should not persist."},
    )

    assert "capture output was invalid" in result["error"]
    assert db_session.scalars(select(KBEntity)).all() == []


# --- career context tool ---------------------------------------------------


def test_get_career_context_spec_is_registered_read_only():
    specs = {spec["function"]["name"]: spec["function"] for spec in openai_tool_specs()}
    assert "get_career_context" in specs
    assert specs["get_career_context"]["parameters"] == {
        "type": "object",
        "properties": {},
        "required": [],
    }


def test_get_career_context_returns_approved_resume_and_memory(db_session):
    from app.schemas.resume import ResumeData
    from app.services import career_kb

    profile = career_kb.get_or_create_profile(db_session)
    profile.contact_json = {"name": "Sample", "email": "a@b.com"}
    profile.summary = "Data scientist"
    profile.notes = "OPT eligible mid-2026"
    entity, _ = _seed_kb_entity(db_session)  # ongoing project w/ one APPROVED point
    db_session.add(
        KBPoint(entity_id=entity.id, text="Draft-only claim", state="draft", origin="ingested")
    )
    db_session.commit()

    result = execute_tool(ToolContext(db=db_session), "get_career_context", {})

    # Resume half: validated compose output, approved points only.
    resume = result["resume"]
    ResumeData.model_validate(resume)
    project = resume["projects"][0]
    assert project["name"] == "Orbit"
    assert "Built the initial retrieval pipeline." in project["bullets"]
    assert "Draft-only claim" not in project["bullets"]

    # Memory half: beyond-the-resume string — identity + entity notes,
    # EXCLUDING approved point texts (those are resume-visible).
    memory = result["memory"]
    assert "IDENTITY" in memory
    assert "OPT eligible mid-2026" in memory
    assert "Shipped first to an internal cohort." in memory
    assert "Built the initial retrieval pipeline." not in memory


# --- template tools --------------------------------------------------------


def _seed_template(db_session, id, *, status="draft", is_default=False, source="x", **kw):
    from app.models.template import Template

    row = Template(id=id, display_name=id, source=source, status=status, is_default=is_default, **kw)
    db_session.add(row)
    db_session.commit()
    return row


def test_get_template_returns_engine_specific_supported_formatting_keys(db_session):
    _seed_template(
        db_session,
        "typst-knobs",
        engine="typst",
        source="#let size = fmt.font_size\n// fmt.side_margins\n",
    )

    result = execute_tool(
        ToolContext(db=db_session),
        "get_template",
        {"template_id": "typst-knobs"},
    )

    assert result["supported_fmt_keys"] == ["date_format", "font_size"]
    assert result["engine"] == "typst"


def test_validate_template_tool_spec_mentions_parse_report():
    specs = {spec["function"]["name"]: spec["function"] for spec in openai_tool_specs()}
    desc = specs["validate_template"]["description"]
    assert "parse_report" in desc
    assert "extra_sections_missing" in desc
    create_desc = specs["create_template_draft"]["description"]
    assert "parse_report" in create_desc


def test_create_template_draft_accepts_engine_and_requires_source_for_typst(db_session):
    ctx = ToolContext(db=db_session)

    missing_source = execute_tool(
        ctx,
        "create_template_draft",
        {"template_id": "typ-no-source", "display_name": "Typ No Source", "engine": "typst"},
    )
    assert "requires explicit source" in missing_source["error"]

    ok = execute_tool(
        ctx,
        "create_template_draft",
        {
            "template_id": "typ-ok",
            "display_name": "Typ OK",
            "engine": "typst",
            "source": "#set text(size: 11pt)\n= Hello",
        },
    )
    assert ok == {"id": "typ-ok", "status": "draft"}

    from app.services import template_registry

    row = template_registry.get(db_session, "typ-ok")
    assert row is not None
    assert row.engine == "typst"
    assert row.source.startswith("#set text")


def test_create_template_draft_spec_includes_engine_and_source():
    specs = {spec["function"]["name"]: spec["function"] for spec in openai_tool_specs()}
    create = specs["create_template_draft"]
    props = create["parameters"]["properties"]
    assert props["engine"] == {"type": "string", "enum": ["latex", "typst"]}
    assert "source" in props


def test_set_default_template_requires_ready(db_session):
    _seed_template(db_session, "draftt", status="draft")
    ctx = ToolContext(db=db_session)
    err = execute_tool(ctx, "set_default_template", {"template_id": "draftt"})
    assert "ready" in err["error"].lower()

    _seed_template(db_session, "readyt", status="ready")
    ok = execute_tool(ctx, "set_default_template", {"template_id": "readyt"})
    assert ok["id"] == "readyt" and ok["is_default"] is True


def test_duplicate_template_copies_and_rejects_collision(db_session):
    _seed_template(db_session, "src", status="ready", source="SRC-BODY",
                   default_formatting={"font_size": 12})
    ctx = ToolContext(db=db_session)
    ok = execute_tool(ctx, "duplicate_template", {"template_id": "src", "new_template_id": "copy"})
    assert ok["id"] == "copy" and ok["status"] == "draft"
    from app.services import template_registry
    dup = template_registry.get(db_session, "copy")
    assert dup.source == "SRC-BODY"
    assert dup.default_formatting == {"font_size": 12}

    collision = execute_tool(
        ctx, "duplicate_template", {"template_id": "src", "new_template_id": "copy"}
    )
    assert "already exists" in collision["error"].lower()

    missing = execute_tool(
        ctx, "duplicate_template", {"template_id": "nope", "new_template_id": "x"}
    )
    assert "not found" in missing["error"].lower()


def test_delete_template_guards_default(db_session):
    from app.services import template_registry

    template_registry.get_default(db_session)  # bootstraps the 'default' template
    ctx = ToolContext(db=db_session)
    guarded = execute_tool(ctx, "delete_template", {"template_id": "default"})
    assert "default" in guarded["error"].lower()
    assert template_registry.get(db_session, "default") is not None

    _seed_template(db_session, "throwaway", status="draft")
    ok = execute_tool(ctx, "delete_template", {"template_id": "throwaway"})
    assert ok["deleted"] == "throwaway"
    assert template_registry.get(db_session, "throwaway") is None


# --- chat system prompt contracts -----------------------------------------


def test_chat_system_default_has_typst_data_contract():
    from app.services import prompts

    text = (prompts.PROMPT_DIR / "chat_system.txt").read_text(encoding="utf-8")
    assert "Typst templates" in text
    assert "sys.inputs.resume" in text
    assert "@preview" in text
    assert "XCharter" in text
    assert "extra_sections" in text


def test_chat_system_default_has_social_posts_section():
    from app.services import prompts

    text = (prompts.PROMPT_DIR / "chat_system.txt").read_text(encoding="utf-8")
    assert "Writing social posts:" in text
    # Grounding must route through the read-only tools, incl. the new one.
    assert "get_career_context" in text
    assert "em dash" in text  # house style: no em dashes in posts


# --- archive filtering -------------------------------------------------------


def test_list_base_resumes_omits_archived(db_session):
    from datetime import UTC, datetime

    from app.models.base_resume import BaseResume
    from app.services import chat_tools

    db_session.add(BaseResume(slug="kept", data_json={}))
    db_session.add(
        BaseResume(slug="stale_track", data_json={}, archived_at=datetime.now(UTC))
    )
    db_session.commit()

    ctx = chat_tools.ToolContext(db=db_session)
    assert [r["slug"] for r in chat_tools.tool_list_base_resumes(ctx)] == ["kept"]
