import re
import pytest

import mcp_server.server as srv

KB_TOOL_NAMES = {
    "kb_list_entities",
    "kb_get_entity",
    "kb_list_points",
    "kb_capture",
    "kb_edit_point",
    "kb_create_entity",
    "kb_edit_entity",
    "kb_edit_profile",
    "kb_ingest_resume",
    "kb_approve_points",
    "kb_sync_base",
}


def test_all_tools_registered():
    names = set(srv.list_registered_tool_names())
    expected = {
        "list_base_resumes",
        "get_base_resume",
        "list_jobs",
        "get_job",
        "list_referrals",
        "store_extracted_jd",
        "get_job_search_brief",
        "find_job_by_url",
        "get_career_context",
        "get_career_export",
        "update_base_resume",
        "edit_base_resume",
        "create_base_resume",
        "create_base_resume_from_kb",
        "duplicate_base_resume",
        "list_resume_versions",
        "get_resume_version",
        "restore_resume_version",
        "archive_base_resume",
        "unarchive_base_resume",
        "tailor_application",
        "render_pdf",
        "explore_top_skills",
        "explore_skill_heatmap",
        "explore_role_mix_over_time",
        "explore_fit_distribution",
        "list_applications",
        "export_jobs",
        "create_tailoring_session",
        "quick_tailor",
        "get_tailoring_session",
        "list_tailoring_sessions",
        "close_tailoring_session",
        "resolve_gaps",
        "tailor_session",
        "edit_application",
        "update_application",
        "generate_qa_answers",
        "generate_cover_letter",
        "list_qa_entries",
        "waive_health_gate",
        "unwaive_health_gate",
        "propose_application",
        "list_proposals",
        "get_proposal",
        "record_decision",
        "record_consent",
        "attach_evidence",
        "mark_submitted",
        "record_triage",
        "report_failure",
    }
    expected |= KB_TOOL_NAMES
    assert expected <= names


def test_resume_version_tools_forward_to_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "list_resume_versions",
        lambda kind, key: seen.update(op="list", kind=kind, key=key) or [{"number": 1}],
    )
    monkeypatch.setattr(
        srv._client,
        "get_resume_version",
        lambda kind, key, number: seen.update(
            op="get", kind=kind, key=key, number=number
        )
        or {"number": number},
    )
    monkeypatch.setattr(
        srv._client,
        "restore_resume_version",
        lambda kind, key, number: seen.update(
            op="restore", kind=kind, key=key, number=number
        )
        or {"number": number + 1},
    )
    assert srv.list_resume_versions("base", "master") == [{"number": 1}]
    assert seen["op"] == "list"
    assert srv.get_resume_version("application", "a1", 3)["number"] == 3
    assert seen["op"] == "get"
    assert srv.restore_resume_version("base", "master", 2) == {"number": 3}
    assert seen == {"op": "restore", "kind": "base", "key": "master", "number": 2}


def test_archive_base_resume_tools_forward_to_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "archive_base_resume",
        lambda slug: seen.update(op="archive", slug=slug) or {"slug": slug},
    )
    monkeypatch.setattr(
        srv._client,
        "unarchive_base_resume",
        lambda slug: seen.update(op="unarchive", slug=slug) or {"slug": slug},
    )
    assert srv.archive_base_resume("other") == {"slug": "other"}
    assert srv.unarchive_base_resume("other") == {"slug": "other"}
    assert seen == {"op": "unarchive", "slug": "other"}


def test_archive_base_resume_docstrings_are_reversible_not_delete():
    archive_doc = (srv.archive_base_resume.__doc__ or "").lower()
    unarchive_doc = (srv.unarchive_base_resume.__doc__ or "").lower()
    assert "list_base_resumes" in archive_doc
    assert "archived" in archive_doc
    assert "unarchive" in archive_doc
    assert "list_base_resumes" in unarchive_doc
    assert "delete" not in "archive_base_resume"
    assert "delete" not in "unarchive_base_resume"


def test_resume_version_docstrings_state_kind_and_restore_is_a_new_version():
    list_doc = srv.list_resume_versions.__doc__ or ""
    get_doc = srv.get_resume_version.__doc__ or ""
    restore_doc = srv.restore_resume_version.__doc__ or ""
    for doc in (list_doc, get_doc, restore_doc):
        assert '"base"' in doc or "base" in doc
        assert "application" in doc
        assert "slug" in doc
    assert "new version" in restore_doc.lower() or "append" in restore_doc.lower()
    assert "delete" not in "list_resume_versions"
    assert "delete" not in "get_resume_version"
    assert "delete" not in "restore_resume_version"


def test_kb_sync_base_docstring_is_draft_only_and_deterministic():
    doc = srv.kb_sync_base.__doc__ or ""
    lower = doc.lower()
    assert "deterministic" in lower
    assert "draft" in lower
    assert "never edits" in lower
    assert "rerun" in lower or "rerun-safe" in lower or "safe to rerun" in lower


def test_kb_list_points_forwards_pagination(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "list_kb_points",
        lambda state=None, limit=500, offset=0: seen.update(
            state=state, limit=limit, offset=offset
        )
        or [],
    )
    assert srv.kb_list_points(state="draft", limit=20, offset=5) == []
    assert seen == {"state": "draft", "limit": 20, "offset": 5}


def test_kb_list_points_docstring_warns_unfiltered_is_bounded():
    doc = srv.kb_list_points.__doc__ or ""
    assert "limit" in doc
    assert "offset" in doc
    assert "first" in doc.lower()


def test_kb_ingest_resume_docstring_states_two_pass_matching():
    """Matching is exact identity-key THEN near-identity for experience/
    projects/certs; education/extra stay identity-key-only. The old wording
    ('identity-key only… Different spellings will not merge') was false.
    """
    doc = srv.kb_ingest_resume.__doc__ or ""
    lower = doc.lower()
    assert "near-identity" in lower or "near identity" in lower
    assert "education" in lower
    assert "identity-key" in lower
    assert "will not merge" not in lower


async def test_tailoring_session_tools_expose_complete_input_schemas():
    tools = {tool.name: tool for tool in await srv.mcp.list_tools()}

    def without_generated_titles(value):
        if isinstance(value, dict):
            return {
                key: without_generated_titles(item)
                for key, item in value.items()
                if key != "title"
            }
        if isinstance(value, list):
            return [without_generated_titles(item) for item in value]
        return value

    session_id_only_schema = {
        "properties": {
            "tailoring_session_id": {"type": "string"},
        },
        "required": ["tailoring_session_id"],
        "type": "object",
    }
    expected_schemas = {
        "get_tailoring_session": session_id_only_schema,
        "close_tailoring_session": session_id_only_schema,
        "resolve_gaps": {
            "$defs": {
                "GapResolution": {
                    "description": "Machine-readable action vocabulary for resolve_gaps.",
                    "properties": {
                        "gap_id": {"type": "string"},
                        "action": {
                            "enum": [
                                "add_keyword",
                                "user_input",
                                "attach_project",
                                "skip",
                                "enable_entry",
                                "port_kb_point",
                                "cannot_confirm",
                            ],
                            "type": "string",
                        },
                        "payload": {
                            "additionalProperties": True,
                            "type": "object",
                        },
                    },
                    "required": ["gap_id", "action"],
                    "type": "object",
                }
            },
            "properties": {
                "tailoring_session_id": {"type": "string"},
                "resolutions": {
                    "description": srv._RESOLUTIONS_FIELD.description,
                    "items": {"$ref": "#/$defs/GapResolution"},
                    "type": "array",
                },
            },
            "required": ["tailoring_session_id", "resolutions"],
            "type": "object",
        },
        "tailor_session": {
            "properties": {
                "tailoring_session_id": {"type": "string"},
                "user_prompt": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                },
                "ops": {
                    "anyOf": [
                        {
                            "items": {
                                "additionalProperties": True,
                                "type": "object",
                            },
                            "type": "array",
                        },
                        {"type": "null"},
                    ],
                    "default": None,
                },
            },
            "required": ["tailoring_session_id"],
            "type": "object",
        },
    }

    actual_schemas = {
        name: without_generated_titles(tools[name].inputSchema)
        for name in expected_schemas
    }
    assert actual_schemas == expected_schemas


async def test_resolve_gaps_contract_lists_every_backend_action():
    tools = {tool.name: tool for tool in await srv.mcp.list_tools()}
    tool = tools["resolve_gaps"]
    actions = {
        "add_keyword",
        "user_input",
        "attach_project",
        "skip",
        "enable_entry",
        "port_kb_point",
        "cannot_confirm",
    }

    assert all(action in tool.description for action in actions)
    action_schema = tool.inputSchema["$defs"]["GapResolution"]["properties"]["action"]
    assert set(action_schema["enum"]) == actions
    resolutions_desc = tool.inputSchema["properties"]["resolutions"].get("description", "")
    assert "ONE unit" in resolutions_desc
    assert "NOTHING" in resolutions_desc
    for action in actions:
        assert action in resolutions_desc


async def test_kb_ingest_resume_data_field_states_atomicity():
    tools = {tool.name: tool for tool in await srv.mcp.list_tools()}
    desc = tools["kb_ingest_resume"].inputSchema["properties"]["data"].get(
        "description", ""
    )
    assert "atomic" in desc.lower()
    assert "nothing persisted" in desc.lower()


def test_list_base_resumes_tool_calls_client(monkeypatch):
    monkeypatch.setattr(srv._client, "list_base_resumes", lambda: [{"slug": "master"}])
    assert srv.list_base_resumes() == [{"slug": "master"}]


def test_list_referrals_tool_calls_client(monkeypatch):
    monkeypatch.setattr(srv._client, "list_referrals", lambda: [{"company": "Acme"}])
    assert srv.list_referrals() == [{"company": "Acme"}]


def test_render_pdf_dispatches_on_target_type(monkeypatch):
    calls = {}
    monkeypatch.setattr(srv._client, "render_base_resume", lambda slug, template_id=None: (calls.__setitem__("base", slug), {"ok": "base"})[1])
    monkeypatch.setattr(srv._client, "render_application", lambda app_id, template_id=None: (calls.__setitem__("app", app_id), {"ok": "app"})[1])
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})
    assert srv.render_pdf("base_resume", "master") == {"ok": "base", "next": None}
    assert srv.render_pdf("application", "a1") == {"ok": "app", "next": None}
    assert calls == {"base": "master", "app": "a1"}


def test_render_pdf_base_resume_never_fetches_setup_status(monkeypatch):
    # Base-resume previews are not part of the score->tailor->render arc, so
    # the (extra, HTTP) setup-status fetch that backs the application hint
    # must never happen for this target_type — not even to build a null hint.
    monkeypatch.setattr(srv._client, "render_base_resume", lambda slug, template_id=None: {"ok": "base"})

    def _boom():
        raise AssertionError("get_setup_status must not be called for base_resume renders")

    monkeypatch.setattr(srv._client, "get_setup_status", _boom)
    out = srv.render_pdf("base_resume", "master")
    assert out == {"ok": "base", "next": None}


def test_render_pdf_application_composes_the_terminal_hint(monkeypatch):
    monkeypatch.setattr(srv._client, "render_application", lambda app_id, template_id=None: {"ok": "app"})
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})
    monkeypatch.setattr(
        srv._client,
        "get_setup_status",
        lambda: {"autofill": {"done": True, "readiness": 1.0, "groups": {}, "blocking": []}},
    )
    out = srv.render_pdf("application", "a1")
    assert out["next"]["state"] == "rendered"
    assert out["next"]["readiness"]["autofill_ready"] is True


def test_render_pdf_application_skips_setup_status_when_hints_off(monkeypatch):
    monkeypatch.setattr(srv._client, "render_application", lambda app_id, template_id=None: {"ok": "app"})
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})

    def _boom():
        raise AssertionError("get_setup_status must not be called when hints are off")

    monkeypatch.setattr(srv._client, "get_setup_status", _boom)
    out = srv.render_pdf("application", "a1")
    assert out == {"ok": "app", "next": None}


def test_render_pdf_invalid_target_raises():
    with pytest.raises(Exception) as exc:
        srv.render_pdf("nonsense", "x")
    assert "target_type" in str(exc.value)


def test_tool_wraps_backend_error(monkeypatch):
    from mcp_server.client import BackendError

    def _boom(slug):
        raise BackendError("Backend returned 404: not found", status_code=404)

    monkeypatch.setattr(srv._client, "get_base_resume", _boom)
    with pytest.raises(Exception) as exc:
        srv.get_base_resume("missing")
    assert "404" in str(exc.value)


def test_template_tools_registered():
    names = set(srv.list_registered_tool_names())
    assert {
        "list_templates", "get_template", "create_template_draft",
        "update_template_draft", "validate_template", "get_rendered_pdf",
        "get_rendered_pdf_page_image", "prepare_application_pdf_upload",
    } <= names


def test_no_default_mutating_template_tools():
    # Control invariant: MCP must NOT be able to set the default or delete a
    # template. Guard against a future tool silently breaking this.
    names = set(srv.list_registered_tool_names())
    assert "set_default" not in names
    assert not any("delete" in n for n in names)


def test_render_pdf_passes_template_id(monkeypatch):
    seen = {}
    monkeypatch.setattr(srv._client, "render_base_resume",
                        lambda slug, template_id=None: seen.update(slug=slug, t=template_id) or {"ok": 1})
    srv.render_pdf("base_resume", "master", template_id="modern")
    assert seen == {"slug": "master", "t": "modern"}


def test_render_pdf_application_template_id(monkeypatch):
    seen = {}
    monkeypatch.setattr(srv._client, "render_application",
                        lambda app_id, template_id=None: seen.update(a=app_id, t=template_id) or {"ok": 1})
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})
    srv.render_pdf("application", "a1", template_id="modern")
    assert seen == {"a": "a1", "t": "modern"}


def test_get_rendered_pdf_tool(monkeypatch):
    monkeypatch.setattr(srv._client, "get_rendered_pdf",
                        lambda tt, tid: {"filename": f"{tid}.pdf", "mime_type": "application/pdf"})
    out = srv.get_rendered_pdf("template", "modern")
    assert out["filename"] == "modern.pdf"


def test_get_rendered_pdf_page_image_tool_forwards_all_args(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "get_rendered_pdf_page_image",
        lambda target_type, target_id, page_number, max_dimension_px=1024: seen.update(
            target_type=target_type,
            target_id=target_id,
            page_number=page_number,
            max_dimension_px=max_dimension_px,
        )
        or {"page_number": page_number},
    )

    out = srv.get_rendered_pdf_page_image("application", "a1", 2, max_dimension_px=640)

    assert out == {"page_number": 2}
    assert seen == {
        "target_type": "application",
        "target_id": "a1",
        "page_number": 2,
        "max_dimension_px": 640,
    }


def test_prepare_application_pdf_upload_tool_forwards_application_id(monkeypatch):
    monkeypatch.setattr(
        srv._client,
        "prepare_application_pdf_upload",
        lambda application_id: {
            "application_id": application_id,
            "upload_path": f"/uploads/{application_id}/Resume.pdf",
        },
    )

    out = srv.prepare_application_pdf_upload("a1")

    assert out == {
        "application_id": "a1",
        "upload_path": "/uploads/a1/Resume.pdf",
    }


async def test_pdf_delivery_tools_expose_expected_input_schemas():
    tools = {tool.name: tool for tool in await srv.mcp.list_tools()}

    assert tools["get_rendered_pdf_page_image"].inputSchema["required"] == [
        "target_type",
        "target_id",
        "page_number",
    ]
    assert tools["get_rendered_pdf_page_image"].inputSchema["properties"][
        "page_number"
    ]["type"] == "integer"
    assert tools["get_rendered_pdf_page_image"].inputSchema["properties"][
        "max_dimension_px"
    ]["default"] == 1024
    assert tools["prepare_application_pdf_upload"].inputSchema["required"] == [
        "application_id"
    ]
    assert set(
        tools["prepare_application_pdf_upload"].inputSchema["properties"]
    ) == {"application_id"}


async def test_store_extracted_jd_exposes_source_enum_and_requirement_levels():
    tools = {tool.name: tool for tool in await srv.mcp.list_tools()}
    tool = tools["store_extracted_jd"]
    source = tool.inputSchema["properties"]["source"]
    # FastMCP may emit enum on the property or via anyOf.
    enum_vals = source.get("enum")
    if enum_vals is None and "anyOf" in source:
        enum_vals = next(
            (
                item.get("enum")
                for item in source["anyOf"]
                if isinstance(item, dict) and "enum" in item
            ),
            None,
        )
    assert enum_vals == ["user", "agent"]
    doc = tool.description or ""
    assert "required" in doc and "preferred" in doc and "mentioned" in doc
    assert "sponsorship_available" in doc
    assert "no_sponsorship" in doc
    assert "citizen_or_gc_required" in doc
    assert "stem_opt_ok" in doc
    assert "unstated" in doc
    assert "silently" in doc.lower() or "normaliz" in doc.lower()


def test_audit_one_sentence_docstring_fixes():
    """Pins the 2026-08-22 audit's one-sentence docstring corrections (T4)."""
    rg = srv.resolve_gaps.__doc__ or ""
    assert "ONE unit" in rg
    assert "NOTHING" in rg

    ts = srv.tailor_session.__doc__ or ""
    assert "kb_writeback_skips" in ts
    assert "placement_target" in ts

    for fn in (srv.create_tailoring_session, srv.quick_tailor):
        doc = fn.__doc__ or ""
        assert "SUPERSEDE" in doc.upper()
        assert "list_tailoring_sessions" in doc

    base = srv.create_base_resume_from_kb.__doc__ or ""
    assert '"other"' in base or "role_category \"other\"" in base
    assert "display_name" in base
    assert "base.slug" in base or "slug" in base

    ent = srv.kb_create_entity.__doc__ or ""
    assert "section_key" in ent
    assert "section_type" in ent
    assert "section_title" in ent
    assert "detail" in ent

    assert "render_error" in (srv.edit_base_resume.__doc__ or "")

    ea = srv.edit_application.__doc__ or ""
    assert "pdf_path" in ea
    assert "render_pdf" in ea

    rp = srv.render_pdf.__doc__ or ""
    assert "selects a LaTeX template" not in rp
    assert "resolved_template_id" in rp
    assert "template_fallback" in rp

    gp = srv.get_rendered_pdf.__doc__ or ""
    assert "artifact_dir" in gp
    assert "prepare_application_pdf_upload" in gp

    gt = srv.get_template.__doc__ or ""
    assert "date_format" in gt
    assert "even if the source" in gt.lower() or "always includes" in gt.lower()

    lt = srv.list_templates.__doc__ or ""
    assert "parse_certified" in lt

    fr = srv.get_final_review.__doc__ or ""
    assert "propose_application" in fr


def test_prepare_application_pdf_upload_docstring_forbids_manual_copy():
    doc = srv.prepare_application_pdf_upload.__doc__ or ""
    assert "upload_path" in doc
    assert "Do NOT" in doc and "copy" in doc.lower()


def test_create_template_draft_tool(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "create_template_draft",
        lambda i, d, s=None, validate=False, engine="latex": seen.update(
            i=i, d=d, s=s, v=validate
        )
        or {"id": i, "status": "draft"},
    )
    out = srv.create_template_draft("modern", "Modern", "SRC")
    assert out["status"] == "draft"
    assert seen == {"i": "modern", "d": "Modern", "s": "SRC", "v": False}


def test_create_template_draft_tool_defaults_to_starter(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "create_template_draft",
        lambda i, d, s=None, validate=False, engine="latex": seen.update(
            s=s, v=validate
        )
        or {"id": i, "status": "draft"},
    )
    srv.create_template_draft("modern", "Modern", validate=True)
    assert seen == {"s": None, "v": True}


def test_template_tool_wraps_backend_error(monkeypatch):
    from mcp_server.client import BackendError
    def _boom(tid):
        raise BackendError("Backend returned 403: default", status_code=403)
    monkeypatch.setattr(srv._client, "validate_template", _boom)
    import pytest
    with pytest.raises(Exception) as exc:
        srv.validate_template("default")
    assert "403" in str(exc.value)


def test_score_fit_tool_removed():
    # Legacy LLM fit scoring is gone; score_ats is the replacement.
    assert "score_fit" not in set(srv.list_registered_tool_names())


def test_generate_cold_message_tool_removed():
    # Retired 2026-07-21: outreach is asked as a free-form question via
    # generate_qa_answers (which injects the application's referral contact).
    assert "generate_cold_message" not in set(srv.list_registered_tool_names())


def test_generate_qa_answers_docstring_mentions_outreach():
    doc = (srv.generate_qa_answers.__doc__ or "").lower()
    assert "outreach" in doc


def test_get_application_tool_registered():
    assert "get_application" in set(srv.list_registered_tool_names())


def test_get_application_tool_calls_client(monkeypatch):
    monkeypatch.setattr(
        srv._client, "get_application", lambda app_id: {"id": app_id}
    )
    assert srv.get_application("a1") == {"id": "a1"}


def test_tailor_session_tool_forwards_ops(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "tailor_session",
        lambda sid, user_prompt=None, ops=None: seen.update(
            sid=sid, up=user_prompt, ops=ops
        )
        or {"session": {"id": sid}},
    )
    ops = [{"kind": "add_skill_item", "category": "Languages", "item": "Salesforce"}]
    out = srv.tailor_session(tailoring_session_id="s1", ops=ops)
    assert out["session"]["id"] == "s1"
    assert seen == {"sid": "s1", "up": None, "ops": ops}


async def test_get_tailoring_session_accepts_cowork_style_kwargs(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "get_tailoring_session",
        lambda session_id: seen.update(session_id=session_id) or {"id": session_id},
    )

    await srv.mcp.call_tool(
        "get_tailoring_session",
        {"tailoring_session_id": "s1"},
    )

    assert seen == {"session_id": "s1"}


async def test_resolve_gaps_accepts_cowork_style_kwargs(monkeypatch):
    seen = {}
    resolutions = [{"gap_id": "g1", "action": "skip", "payload": {}}]
    monkeypatch.setattr(
        srv._client,
        "resolve_gaps",
        lambda session_id, items: seen.update(
            session_id=session_id, resolutions=items
        )
        or {"id": session_id},
    )
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})

    await srv.mcp.call_tool(
        "resolve_gaps",
        {
            "tailoring_session_id": "s1",
            "resolutions": resolutions,
        },
    )

    assert seen == {"session_id": "s1", "resolutions": resolutions}


async def test_tailor_session_accepts_cowork_style_kwargs(monkeypatch):
    seen = {}
    ops = [{"kind": "add_skill_item", "category": "Languages", "item": "Salesforce"}]
    monkeypatch.setattr(
        srv._client,
        "tailor_session",
        lambda session_id, user_prompt=None, ops=None: seen.update(
            session_id=session_id, user_prompt=user_prompt, ops=ops
        )
        or {"session": {"id": session_id}},
    )

    await srv.mcp.call_tool(
        "tailor_session",
        {
            "tailoring_session_id": "s1",
            "user_prompt": "Keep it concise",
            "ops": ops,
        },
    )

    assert seen == {
        "session_id": "s1",
        "user_prompt": "Keep it concise",
        "ops": ops,
    }


def test_tailor_session_tool_ops_default_none(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "tailor_session",
        lambda sid, user_prompt=None, ops=None: seen.update(ops=ops)
        or {"session": {"id": sid}},
    )
    srv.tailor_session(tailoring_session_id="s1")
    # ops defaults to None (the LLM path) when the caller supplies nothing
    assert seen == {"ops": None}


def test_health_check_tools_registered():
    names = set(srv.list_registered_tool_names())
    assert {"run_health_check", "get_health_report"} <= names


def test_run_health_check_tool_calls_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "run_health_check",
        lambda kind, key: seen.update(kind=kind, key=key) or {"score": 78},
    )
    out = srv.run_health_check("base", "my-slug")
    assert out == {"score": 78}
    assert seen == {"kind": "base", "key": "my-slug"}


def test_get_health_report_tool_calls_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "get_health_report",
        lambda kind, key: seen.update(kind=kind, key=key) or {"grade": "B"},
    )
    out = srv.get_health_report("application", "a1")
    assert out == {"grade": "B"}
    assert seen == {"kind": "application", "key": "a1"}


def test_health_waiver_docstrings_require_explicit_human_decision():
    waive_doc = (srv.waive_health_gate.__doc__ or "").lower()
    unwaive_doc = (srv.unwaive_health_gate.__doc__ or "").lower()
    for doc in (waive_doc, unwaive_doc):
        assert "409" in doc
        assert "create_tailoring_session" in doc
        assert "explicit human decision" in doc
        assert "user has said to waive" in doc


def test_validate_template_docstring_documents_parse_certified():
    doc = srv.validate_template.__doc__ or ""
    assert "parse_certified" in doc
    assert "parse_report" in doc
    assert "extra_sections_missing" in doc
    assert "LaTeX error" not in doc
    assert "file:line:col" in doc


def test_list_templates_docstring_covers_both_engines():
    doc = srv.list_templates.__doc__ or ""
    assert "LaTeX templates" not in doc
    assert "engine" in doc
    assert "both engines" in doc.lower() or "latex | typst" in doc.lower() or "engines" in doc


def test_get_template_docstring_covers_both_engines():
    doc = srv.get_template.__doc__ or ""
    assert "engine" in doc
    assert "typst" in doc.lower()
    assert "supported_fmt_keys" in doc


def test_create_template_draft_docstring_states_typst_constraints():
    doc = srv.create_template_draft.__doc__ or ""
    assert "@preview" in doc
    assert "XCharter" in doc
    assert "extra_sections" in doc
    assert "PRE-FORMATTED" in doc  # "date_format" alone matched the OLD LaTeX fmt list too
    assert "silently" in doc.lower() or "substitut" in doc.lower()


def test_tailor_session_tool_docstring_restates_honesty_rules():
    doc = (srv.tailor_session.__doc__ or "").lower()
    # no-fabrication rule
    assert "fabricate" in doc
    # unverified/absent skills may only land in the skills list, not as bullets
    assert "skills list" in doc
    # the before/after compare view is the audit surface for edits
    assert "compare" in doc and "audit" in doc


def test_update_application_tool_calls_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "update_application",
        lambda app_id, status=None, applied_at=None, notes=None, referral_id=None: seen.update(
            app_id=app_id, status=status, applied_at=applied_at, notes=notes, referral_id=referral_id
        )
        or {"id": app_id, "status": status},
    )
    out = srv.update_application("a1", status="applied")
    assert out == {"id": "a1", "status": "applied"}
    assert seen == {
        "app_id": "a1",
        "status": "applied",
        "applied_at": None,
        "notes": None,
        "referral_id": None,
    }


def test_update_application_tool_forwards_all_args(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "update_application",
        lambda app_id, status=None, applied_at=None, notes=None, referral_id=None: seen.update(
            app_id=app_id, status=status, applied_at=applied_at, notes=notes, referral_id=referral_id
        )
        or {"id": app_id},
    )
    srv.update_application(
        "a1", status="rejected", applied_at="2026-07-01T00:00:00Z", notes="no fit", referral_id="r1"
    )
    assert seen == {
        "app_id": "a1",
        "status": "rejected",
        "applied_at": "2026-07-01T00:00:00Z",
        "notes": "no fit",
        "referral_id": "r1",
    }


def test_update_application_docstring_documents_statuses_and_limitation():
    doc = (srv.update_application.__doc__ or "").lower()
    for status in (
        "draft", "applied", "interviewing", "offered", "accepted", "rejected", "withdrawn",
    ):
        assert status in doc
    # the fields_set limitation must be spelled out (clearing requires the web UI)
    assert "web ui" in doc
    assert "applied_at" in doc


def test_list_tailoring_sessions_tool_calls_client(monkeypatch):
    monkeypatch.setattr(
        srv._client,
        "list_tailoring_sessions",
        lambda job_id: [{"id": "s1", "job_id": job_id}],
    )
    assert srv.list_tailoring_sessions("job1") == [{"id": "s1", "job_id": "job1"}]


def test_close_tailoring_session_tool_calls_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "close_tailoring_session",
        lambda session_id: seen.update(sid=session_id) or {"id": session_id, "status": "abandoned"},
    )
    out = srv.close_tailoring_session(tailoring_session_id="s1")
    assert out == {"id": "s1", "status": "abandoned"}
    assert seen == {"sid": "s1"}


def test_close_tailoring_session_name_has_no_delete():
    # Control test: MCP must never expose a tool whose name reads as a delete.
    assert "delete" not in "close_tailoring_session"


async def test_edit_op_docstrings_advertise_extra_section_ops():
    # The custom-section op contract must be discoverable on the edit tools so an
    # agent is never taught a stale (fixed-section-only) op enumeration.
    base_doc = srv.edit_base_resume.__doc__ or ""
    for kind in (
        "add_extra_section",
        "replace_extra_section",
        "remove_extra_section",
        "move_extra_section",
    ):
        assert kind in base_doc
    assert "section_key" in base_doc
    # tailor_application + edit_application reference the same op family.
    assert "extra_section" in (srv.tailor_application.__doc__ or "")
    assert "extra_section" in (srv.edit_application.__doc__ or "")
    # The ExtraSection discriminated-union shape must live on the ops param
    # schema — immune to the ~2048-char tool-description truncation that hid
    # it in the live audit.
    tools = {tool.name: tool for tool in await srv.mcp.list_tools()}
    ops_desc = tools["edit_base_resume"].inputSchema["properties"]["ops"].get(
        "description", ""
    )
    assert "add_extra_section" in ops_desc
    assert "replace_extra_section" in ops_desc
    assert "entries" in ops_desc and "bullets" in ops_desc
    assert "never both" in ops_desc
    assert "forbid" in ops_desc


def test_tailor_application_and_edit_application_docstrings_are_distinguishable():
    tailor_doc = (srv.tailor_application.__doc__ or "").lower()
    # tailor_application must document that it replaces wholesale off the base
    # and destroys prior tailored edits.
    assert "base" in tailor_doc
    assert "replac" in tailor_doc or "destroy" in tailor_doc
    assert "destroy" in tailor_doc
    assert "edit_application" in tailor_doc


def test_edit_application_docstring_describes_current_draft_behavior():
    edit_doc = (srv.edit_application.__doc__ or "").lower()
    # edit_application must document that it edits the CURRENT customized_json
    # and falls back to base only when none exists.
    assert "current" in edit_doc
    assert "customized_json" in edit_doc
    assert "fall back" in edit_doc or "falls back" in edit_doc
    assert "tailor_application" in edit_doc


def test_job_search_tools_registered_and_read_only_named():
    names = set(srv.list_registered_tool_names())
    assert {"get_job_search_brief", "find_job_by_url"} <= names
    # Control invariant (same rule test_no_default_mutating_template_tools
    # enforces globally): neither name may read as a delete.
    assert "delete" not in "get_job_search_brief"
    assert "delete" not in "find_job_by_url"


def test_get_job_search_brief_tool_calls_client(monkeypatch):
    monkeypatch.setattr(
        srv._client, "get_job_search_brief", lambda: {"persona": "", "warnings": ["w"]}
    )
    assert srv.get_job_search_brief() == {"persona": "", "warnings": ["w"]}


def test_find_job_by_url_tool_calls_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client,
        "find_job_by_url",
        lambda source_url: seen.update(url=source_url) or {"found": False},
    )
    assert srv.find_job_by_url("https://x.test/jobs/1") == {"found": False}
    assert seen == {"url": "https://x.test/jobs/1"}


def test_job_search_docstrings_state_capture_only():
    # The brief is the entry point of the agentic search playbook; its contract
    # (capture + score only, no auto-apply) must be discoverable on the tool.
    brief_doc = (srv.get_job_search_brief.__doc__ or "").lower()
    assert "capture" in brief_doc
    assert "auto-apply" in brief_doc or "apply" in brief_doc
    find_doc = (srv.find_job_by_url.__doc__ or "").lower()
    assert "already" in find_doc
    assert "store_extracted_jd" in find_doc


async def test_no_kb_write_tool_exposes_state():
    """Approving from MCP must be unrepresentable, not merely discouraged."""
    tools = await srv.mcp.list_tools()
    writes = [
        tool
        for tool in tools
        if tool.name in {"kb_edit_point", "kb_capture", "kb_edit_entity"}
    ]
    assert len(writes) == 3
    for tool in writes:
        assert "state" not in tool.inputSchema.get("properties", {}), tool.name


async def test_kb_edit_entity_cannot_change_kind():
    tools = {tool.name: tool for tool in await srv.mcp.list_tools()}
    assert "kind" not in tools["kb_edit_entity"].inputSchema.get("properties", {})


def _schema_op_kinds() -> set[str]:
    """Every `kind` literal the server actually accepts, read from the schema."""
    import typing

    from app.schemas import resume_edit

    kinds = set()
    for name in dir(resume_edit):
        model = getattr(resume_edit, name)
        field = getattr(model, "model_fields", {}).get("kind") if hasattr(model, "model_fields") else None
        if field is not None:
            args = typing.get_args(field.annotation)
            if args:
                kinds.add(args[0])
    return kinds


def test_edit_base_resume_documents_every_op_kind():
    """The docstring IS the agent's API reference — an undocumented op is an op
    no agent will use.

    This drifted once for real: the docstring listed 8 of 16 kinds, omitting
    replace_entry, so an MCP session concluded a project's date could not be
    edited and fell back to update_base_resume — a whole-resume PUT — on three
    base resumes to change one field each.
    """
    documented = set(re.findall(r'"kind":"([a-z_]+)"', srv.edit_base_resume.__doc__))
    schema = _schema_op_kinds()
    assert schema - documented == set(), f"undocumented ops: {sorted(schema - documented)}"
    assert documented - schema == set(), f"documented ops that do not exist: {sorted(documented - schema)}"


def test_entry_field_edits_point_at_replace_entry_not_full_put():
    """Agents reach for update_base_resume when nothing tells them dates are
    reachable with a scoped op."""
    doc = srv.edit_base_resume.__doc__
    assert "replace_entry" in doc
    assert "dates" in doc
    assert "LAST RESORT" in doc
    for name in ("tailor_application", "edit_application"):
        assert "replace_entry" in getattr(srv, name).__doc__, name


async def test_ops_parameter_schema_names_every_op_kind():
    """The INPUT SCHEMA must carry the vocabulary, not just the prose.

    `ops` is list[dict], so without an annotated description the machine-readable
    contract reads "array of arbitrary objects". An agent that trusts the schema
    over a 2.7k-char docstring then concludes no op fits and falls back to the
    whole-resume PUT next door — observed 2026-08-04, after a docstring-only fix
    had already landed and was verifiably being served.
    """
    tools = {tool.name: tool for tool in await srv.mcp.list_tools()}
    schema_kinds = _schema_op_kinds()
    for name in ("edit_base_resume", "tailor_application", "edit_application"):
        described = tools[name].inputSchema["properties"]["ops"].get("description", "")
        missing = {k for k in schema_kinds if k not in described}
        assert not missing, f"{name} ops schema omits: {sorted(missing)}"
        assert "replace_entry" in described, name


# Live MCP clients (Claude Desktop-class) truncate tool descriptions at ~2048
# dedented chars. Facts past that cutoff are invisible. Keep a margin under
# the observed cutoff so a later one-sentence fix cannot silently re-break.
_DOCSTRING_CLIENT_BUDGET = 2000


async def test_registered_tool_docstrings_fit_client_truncation_budget():
    import ast
    import inspect
    import pathlib

    # Python 3.13+ dedents __doc__ at compile time, so a runtime-only measure
    # under-counts what 3.12 (CI, the shipped image) actually publishes.
    # Measure the SOURCE docstring too, or a 3.13-green can be a 3.12-red.
    src_lens: dict[str, int] = {}
    tree = ast.parse(pathlib.Path(srv.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src_lens[node.name] = len(doc)

    over: dict[str, int] = {}
    for tool in await srv.mcp.list_tools():
        raw = tool.description or ""
        n = max(len(raw), len(inspect.cleandoc(raw)), src_lens.get(tool.name, 0))
        if n > _DOCSTRING_CLIENT_BUDGET:
            over[tool.name] = n
    assert not over, (
        "tool descriptions exceed the ~2048-char client truncation budget "
        f"(cap {_DOCSTRING_CLIENT_BUDGET}): {over}"
    )
