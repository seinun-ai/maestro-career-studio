"""Tool registry for the chat agent.

Every mutating tool funnels through the same services the REST endpoints use
(`apply_edits`, template registry) and records a resume version with
source='chat' + source_ref=<user message id>, returning a change-card payload
the frontend renders in the transcript.

Scope guard: when the triggering user message carries selection chips,
`edit_resume` rejects ops outside the selected paths with a tool error string —
the model reads it and self-corrects. No selections = whole-resume scope.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity
from app.models.chat import ChatAttachment

from app.schemas.career_kb import KBCaptureRequest
from app.services import role_categories
from app.services import exports as career_exports
from app.schemas.resume import CORE_SECTION_KEYS, ProjectEntry
from app.schemas.resume_edit import ResumeEditRequest, op_scope, render_ops_brief
from app.services.resume_edit import apply_edits
from app.services import (
    base_resume_data,
    career_kb,
    explore_activity,
    explore_base_summaries,
    explore_build_areas,
    explore_gaps,
    kb_ingest,
    resume_ops,
    template_registry,
)
from app.services.template_validation import validate_template as _validate_template


class ToolError(Exception):
    """Recoverable tool failure — returned to the model as the tool result."""


@dataclass
class ToolContext:
    db: Session
    message_id: str | None = None
    # Selection chips from the triggering user message:
    # [{"section": "experience", "index": 1, "bullet_index": 2}, ...]
    selections: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scope guard

# Core scope sections derive from the schema's CORE_SECTION_KEYS (minus the
# extra_sections container itself): any scope section outside this set is a
# custom-section KEY, which the whole-block "extra_sections" chip covers.
_CORE_SCOPE_SECTIONS = frozenset(CORE_SECTION_KEYS) - {"extra_sections"}

def _selection_covers(
    sel: dict[str, Any], scope: tuple[str | None, int | None, int | None]
) -> bool:
    section, index, bullet = scope
    # Whole custom-sections chip: covers any custom-section op, whose scope
    # section is the section's own key (never a core section name).
    if (
        sel.get("section") == "extra_sections"
        and section is not None
        and section not in _CORE_SCOPE_SECTIONS
    ):
        return True
    if sel.get("section") != section:
        return False
    if sel.get("index") is None:
        return True  # whole-section chip (incl. an exact custom-section key match)
    if index is None:
        return False  # section-level op (e.g. add_entry) needs a section chip
    if sel["index"] != index:
        return False
    if sel.get("bullet_index") is None:
        return True  # whole-item chip
    return bullet is not None and sel["bullet_index"] == bullet


def check_ops_in_scope(ops, selections: list[dict[str, Any]]) -> None:
    # Only resume-path chips constrain resume edits. Other reference kinds
    # (e.g. a pinned Career KB entity) are context, not scope — a KB pin
    # alone must not silently block every resume op. Missing kind = legacy
    # resume chip.
    selections = [s for s in selections if s.get("kind") in (None, "resume")]
    if not selections:
        return
    for op in ops:
        scope = op_scope(op)
        if not any(_selection_covers(sel, scope) for sel in selections):
            where = f"{scope[0]}" + (f"[{scope[1]}]" if scope[1] is not None else "")
            raise ToolError(
                f"Op {op.kind!r} targets {where}, which is outside the user's selected scope "
                f"{selections}. Only edit within the selection, or tell the user the change "
                "requires widening the scope."
            )


# ---------------------------------------------------------------------------
# Resume tools


def _load_target(db: Session, kind: str, key: str):
    if kind == "base":
        row = db.get(BaseResume, key)
        if row is None or row.deleted_at is not None:
            raise ToolError(f"Base resume {key!r} not found")
        return row, row.data_json
    if kind == "application":
        try:
            row = db.get(Application, UUID(key))
        except ValueError:
            raise ToolError(f"Invalid application id {key!r}") from None
        if row is None:
            raise ToolError(f"Application {key!r} not found")
        if row.customized_json is None:
            raise ToolError(
                f"Application {key!r} has no tailored resume yet — materialize it first"
            )
        return row, row.customized_json
    raise ToolError(f"kind must be 'base' or 'application', got {kind!r}")


def tool_list_base_resumes(ctx: ToolContext) -> list[dict[str, Any]]:
    rows = ctx.db.scalars(
        select(BaseResume)
        .where(base_resume_data.selectable_filter())
        .order_by(BaseResume.slug)
    )
    return [{"slug": r.slug, "display_name": r.display_name} for r in rows]


def tool_get_resume(ctx: ToolContext, kind: str, key: str) -> dict[str, Any]:
    _, data = _load_target(ctx.db, kind, key)
    return data


def tool_edit_resume(ctx: ToolContext, kind: str, key: str, ops: list[dict]) -> dict[str, Any]:
    try:
        parsed = ResumeEditRequest.model_validate({"ops": ops}).ops
    except Exception as e:
        raise ToolError(f"Invalid ops: {e}") from e
    check_ops_in_scope(parsed, ctx.selections)

    row, current = _load_target(ctx.db, kind, key)
    # Shared pipeline (services/resume_ops.py): the same persist/version/render
    # tail as the REST endpoints — chat is no longer a third implementation.
    # Base renders degrade to a persisted render_error (previously chat
    # swallowed render failures with no signal at all).
    try:
        if kind == "base":
            _, version, _, _ = resume_ops.edit_base(
                ctx.db, row, parsed, source="chat", source_ref=ctx.message_id
            )
        else:
            _, version, _ = resume_ops.edit_application(
                ctx.db,
                row,
                parsed,
                baseline=current,
                source="chat",
                source_ref=ctx.message_id,
            )
    except LookupError as e:
        raise ToolError(str(e)) from e
    except ValueError as e:
        raise ToolError(str(e)) from e

    return {
        "change_card": {
            "resume_kind": kind,
            "resume_key": key if kind == "base" else str(row.id),
            "version_number": version.version_number,
            "summary": version.summary,
            "ops_count": len(parsed),
        }
    }


def tool_propose_edits(
    ctx: ToolContext,
    target_kind: str,
    target_key: str,
    ops: list[dict],
    summary: str | None = None,
) -> dict[str, Any]:
    """Stage typed edit ops for user approval — never writes.

    Validation mirrors edit_resume exactly (ops schema, target existence,
    scope guard) so an approved proposal cannot fail for reasons the model
    could have known at propose time.
    """
    try:
        parsed = ResumeEditRequest.model_validate({"ops": ops}).ops
    except Exception as e:
        raise ToolError(f"Invalid ops: {e}") from e
    check_ops_in_scope(parsed, ctx.selections)
    _, current = _load_target(ctx.db, target_kind, target_key)
    # Dry-run against the live document (apply_edits is pure): index bounds and
    # entry/extra-section payload errors surface NOW as a ToolError the model
    # can fix, instead of a 400 when the user clicks Apply.
    try:
        apply_edits(current, parsed)
    except ValueError as e:
        raise ToolError(f"Ops do not apply to the current resume: {e}") from e
    return {
        "proposal_ops": {
            "target_kind": target_kind,
            "target_key": target_key,
            "ops": [op.model_dump(mode="json") for op in parsed],
            "ops_count": len(parsed),
            "summary": (summary or "").strip() or None,
        }
    }


def tool_propose_project(
    ctx: ToolContext, target_kind: str, target_key: str, project: dict[str, Any]
) -> dict[str, Any]:
    """Stage a new project entry for user review — never writes."""
    _load_target(ctx.db, target_kind, target_key)  # validate the target exists
    try:
        entry = ProjectEntry.model_validate(project).model_dump(mode="json")
    except Exception as e:
        raise ToolError(f"Invalid project entry: {e}") from e
    return {
        "proposal": {
            "target_kind": target_kind,
            "target_key": target_key,
            "project": entry,
        }
    }


def tool_read_attachment(ctx: ToolContext, attachment_id: str) -> str:
    try:
        row = ctx.db.get(ChatAttachment, UUID(attachment_id))
    except ValueError:
        raise ToolError(f"Invalid attachment id {attachment_id!r}") from None
    if row is None:
        raise ToolError(f"Attachment {attachment_id!r} not found")
    return row.text_content


# ---------------------------------------------------------------------------
# Career KB tools


def _kb_entity_uuid(entity_id: str | UUID) -> UUID:
    try:
        return entity_id if isinstance(entity_id, UUID) else UUID(str(entity_id))
    except (TypeError, ValueError, AttributeError):
        raise ToolError(f"Invalid KB entity id {entity_id!r}") from None


def tool_kb_list_entities(ctx: ToolContext) -> list[dict[str, Any]]:
    rows = ctx.db.scalars(select(KBEntity).order_by(KBEntity.created_at, KBEntity.id)).all()
    return [
        {
            "id": str(entity.id),
            "kind": entity.kind,
            "title": entity.title,
            "org": entity.org,
            "status": entity.status,
        }
        for entity in rows
    ]


def tool_kb_get_entity(ctx: ToolContext, entity_id: str) -> dict[str, Any]:
    parsed_id = _kb_entity_uuid(entity_id)
    entity = ctx.db.get(KBEntity, parsed_id)
    if entity is None:
        raise ToolError(f"KB entity {entity_id!r} not found")
    return career_kb.entity_detail(ctx.db, entity).model_dump(mode="json")


def tool_kb_capture(ctx: ToolContext, text: str, entity_id: str | None = None) -> dict[str, Any]:
    try:
        payload = KBCaptureRequest.model_validate({"text": text, "entity_id": entity_id})
    except Exception as e:
        raise ToolError(f"Invalid KB capture: {e}") from e

    try:
        entity, points = kb_ingest.capture(
            ctx.db,
            payload.text,
            entity_id=payload.entity_id,
            origin="chat",
        )
        result = {
            "kb_capture": {
                "entity_id": str(entity.id),
                "entity_title": entity.title,
                "point_count": len(points),
            }
        }
        ctx.db.commit()
        career_exports.best_effort_refresh(ctx.db)
    except (LookupError, ValueError) as e:
        ctx.db.rollback()
        raise ToolError(str(e)) from e
    except Exception:
        ctx.db.rollback()
        raise
    return result


def tool_get_career_context(ctx: ToolContext) -> dict[str, Any]:
    """Full composed career grounding: approved-points resume + KB memory.

    compose_resume_data already returns a validated JSON-safe dict (it
    model_dumps internally), so this is a plain-dict return — no card
    wiring in chat_agent.py needed.
    """
    return {
        "resume": career_kb.compose_resume_data(ctx.db),
        "memory": career_kb.compose_context(ctx.db),
    }


# ---------------------------------------------------------------------------
# Analytics tools (read-only wrappers over the explore services)


def _clamp(value, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def tool_analytics_activity(
    ctx: ToolContext, granularity: str = "day", weeks: int = 8
) -> dict[str, Any]:
    return explore_activity.activity(
        ctx.db, granularity=granularity, weeks=_clamp(weeks, 1, 52, 8)
    )


def tool_analytics_gap_frequency(
    ctx: ToolContext, role_category: str | None = None, limit: int = 15
) -> dict[str, Any]:
    if role_category is not None and role_category not in role_categories.all_keys():
        raise ToolError(
            f"Unknown role_category {role_category!r}; valid values: "
            f"{', '.join(role_categories.all_keys())} (or omit for all roles)"
        )
    limit = _clamp(limit, 1, 50, 15)
    return {
        "common_gaps": explore_gaps.gap_frequency(ctx.db, role_category, limit=limit),
        "build_areas": explore_build_areas.build_areas(
            ctx.db, role_category, limit=limit
        ),
    }


def tool_analytics_base_summaries(ctx: ToolContext) -> list[dict[str, Any]]:
    return explore_base_summaries.base_summaries(ctx.db)


# ---------------------------------------------------------------------------
# Template tools


def tool_list_templates(ctx: ToolContext) -> list[dict[str, Any]]:
    return [
        {
            "id": t.id,
            "display_name": t.display_name,
            "status": t.status,
            "is_default": t.is_default,
        }
        for t in template_registry.list_all(ctx.db)
    ]


def tool_get_template(ctx: ToolContext, template_id: str) -> dict[str, Any]:
    t = template_registry.get(ctx.db, template_id)
    if t is None:
        raise ToolError(f"Template {template_id!r} not found")
    return {
        "id": t.id,
        "display_name": t.display_name,
        "status": t.status,
        "source": t.source,
        "supported_fmt_keys": template_registry.supported_fmt_keys(t.source or "", t.engine),
    }


def tool_create_template_draft(
    ctx: ToolContext,
    template_id: str,
    display_name: str,
    engine: str = "latex",
    source: str | None = None,
) -> dict:
    if engine not in {"latex", "typst"}:
        raise ToolError("engine must be 'latex' or 'typst'")
    # Keep chat parity with the API schema: Typst rows must be created from an
    # explicit .typ source, never from the LaTeX starter.
    if engine == "typst" and source is None:
        raise ToolError("engine='typst' requires explicit source")
    try:
        t = template_registry.create_draft(
            ctx.db,
            id=template_id,
            display_name=display_name,
            source=source,
            origin="chat",
            engine=engine,
        )
    except ValueError as e:
        raise ToolError(str(e)) from e
    return {"id": t.id, "status": t.status}


def tool_update_template_draft(ctx: ToolContext, template_id: str, source: str) -> dict:
    try:
        t = template_registry.update_draft(ctx.db, template_id, source=source)
    except (ValueError, LookupError) as e:
        raise ToolError(str(e)) from e
    return {"id": t.id, "status": t.status}


def tool_validate_template(ctx: ToolContext, template_id: str) -> dict:
    try:
        return _validate_template(template_id, ctx.db)
    except (ValueError, LookupError) as e:
        raise ToolError(str(e)) from e


def tool_set_default_template(ctx: ToolContext, template_id: str) -> dict:
    try:
        t = template_registry.set_default(ctx.db, template_id)
    except (ValueError, LookupError) as e:
        raise ToolError(str(e)) from e
    return {"id": t.id, "is_default": t.is_default}


def tool_duplicate_template(
    ctx: ToolContext, template_id: str, new_template_id: str, display_name: str | None = None
) -> dict:
    try:
        t = template_registry.duplicate(
            ctx.db, template_id, new_template_id, display_name=display_name, origin="chat"
        )
    except (ValueError, LookupError) as e:
        raise ToolError(str(e)) from e
    return {"id": t.id, "status": t.status}


def tool_delete_template(ctx: ToolContext, template_id: str) -> dict:
    try:
        template_registry.delete(ctx.db, template_id)
    except (ValueError, LookupError) as e:
        raise ToolError(str(e)) from e
    return {"deleted": template_id}


# ---------------------------------------------------------------------------
# Registry

_RESUME_KIND_SCHEMA = {"type": "string", "enum": ["base", "application"]}

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "list_base_resumes",
        "description": "List all base resumes (slug + display name).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_resume",
        "description": "Get the full structured JSON of a base resume (key=slug) or an application's tailored resume (key=application id).",
        "parameters": {
            "type": "object",
            "properties": {"kind": _RESUME_KIND_SCHEMA, "key": {"type": "string"}},
            "required": ["kind", "key"],
        },
    },
    {
        "name": "edit_resume",
        "description": (
            "Apply typed edit ops to a resume. Auto-applies and records a restorable version. "
            # Rendered from the schema-side registry so this spec can never
            # miss or invent an op kind (SYSTEM.md §11 item 1).
            f"Op kinds: {render_ops_brief()}. "
            "Sections: experience|projects|education (skills/summary/contact/certifications via their own ops). "
            "Custom (extra) sections — Publications/Awards/Volunteer — are edited whole via the "
            "extra_section ops; section_key resolves the stored ExtraSection.key. value is a full "
            "ExtraSection {key,title,type:'entries'|'bullets',enabled,...} carrying entries OR bullets."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": _RESUME_KIND_SCHEMA,
                "key": {"type": "string"},
                "ops": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["kind", "key", "ops"],
        },
    },
    {
        "name": "propose_edits",
        "description": (
            "Stage resume edit ops for the user's approval (does NOT write). Use this when "
            "the user asks for suggestions, feedback, or a review — they see the staged "
            "rewrite as a card and apply it with one click. Same op kinds and shapes as "
            "edit_resume. Include a one-sentence summary of the intent."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target_kind": _RESUME_KIND_SCHEMA,
                "target_key": {"type": "string"},
                "ops": {"type": "array", "items": {"type": "object"}},
                "summary": {"type": "string"},
            },
            "required": ["target_kind", "target_key", "ops"],
        },
    },
    {
        "name": "propose_project",
        "description": (
            "Stage a NEW project entry for user review (does not write). Use after reading an "
            "uploaded document to draft resume project points. The user merges or discards it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target_kind": _RESUME_KIND_SCHEMA,
                "target_key": {"type": "string"},
                "project": {
                    "type": "object",
                    "description": "ProjectEntry: {name, tech?, link?, date?, bullets: [str]}",
                },
            },
            "required": ["target_kind", "target_key", "project"],
        },
    },
    {
        "name": "read_attachment",
        "description": "Read the extracted text of an uploaded attachment by id.",
        "parameters": {
            "type": "object",
            "properties": {"attachment_id": {"type": "string"}},
            "required": ["attachment_id"],
        },
    },
    {
        "name": "kb_list_entities",
        "description": "List Career KB entities with their kind, title, organization, and status.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "kb_get_entity",
        "description": "Get one Career KB entity, including its notes and resume points.",
        "parameters": {
            "type": "object",
            "properties": {"entity_id": {"type": "string", "format": "uuid"}},
            "required": ["entity_id"],
        },
    },
    {
        "name": "kb_capture",
        "description": (
            "Capture reported work into the Career KB as draft points for later review. "
            "Optionally force placement on a known entity."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "entity_id": {"type": "string", "format": "uuid"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "get_career_context",
        "description": (
            "Read the full composed career context: the approved-points resume "
            "view assembled from the Career KB (profile + non-archived entities + "
            "APPROVED points only) plus a beyond-the-resume memory string "
            "(identity facts and entity notes). Use this to ground social posts, "
            "outreach drafts, or any writing about the user's whole career."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "analytics_activity",
        "description": (
            "Job-search activity numbers: drafted/submitted applications per day or week, "
            "pipeline status counts, in-flight total, and the share currently at interview "
            "stage or beyond. Use for 'how is my search going' questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "granularity": {"type": "string", "enum": ["day", "week"]},
                "weeks": {"type": "integer", "minimum": 1, "maximum": 52},
            },
            "required": [],
        },
    },
    {
        "name": "analytics_gap_frequency",
        "description": (
            "Skills that recur as gaps across scored jobs (common_gaps) — recurring "
            "DEMAND, not skills the user lacks: evidence may sit on another base "
            "resume, be stale, or just be mis-placed, and hygiene wording gaps "
            "(already matched at full credit) are excluded from these counts. Plus "
            "build_areas, whose rows carry a tier saying what would actually fix "
            "each: build (no resume evidence AND nothing in the Career KB — the only "
            "skill to genuinely go learn), surface (the material exists in the KB, on "
            "another resume, or mis-placed/stale on this one — port or strengthen it, "
            "never call it a skill the user lacks), wording (a literal-token mismatch "
            "already matched at full credit; tailoring mirrors it and it moves no "
            "score — a footnote, so these rows report n_jobs 0 and count under "
            "wording_jobs). status is the raw KB-evidence label (missing/in_kb/ported) "
            "and does NOT on its own mean 'learn it' — read tier for that. category is "
            "the gap category driving the row. "
            "role_category filters by the job's slug; omit it for all roles."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                # Closed slug vocabulary: a free-typed "Data Scientist" would
                # silently match nothing and read as "no gaps".
                "role_category": {"type": "string", "enum": role_categories.all_keys()},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": [],
        },
    },
    {
        "name": "analytics_base_summaries",
        "description": (
            "Per-base-resume performance: health grade, average base ATS, average "
            "tailoring lift, application counts, in-flight, last activity."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_templates",
        "description": "List resume templates (LaTeX and Typst).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_template",
        "description": (
            "Get a template including its source (Jinja2+LaTeX or Typst, "
            "depending on engine) and its supported_fmt_keys — the fmt.* "
            "formatting knobs the template consumes."
        ),
        "parameters": {
            "type": "object",
            "properties": {"template_id": {"type": "string"}},
            "required": ["template_id"],
        },
    },
    {
        "name": "create_template_draft",
        "description": (
            "Create a new draft template. engine defaults to latex; typst requires explicit source."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "template_id": {"type": "string", "description": "lowercase slug"},
                "display_name": {"type": "string"},
                "engine": {"type": "string", "enum": ["latex", "typst"]},
                "source": {
                    "type": "string",
                    "description": "Full template source. Required when engine='typst'.",
                },
            },
            "required": ["template_id", "display_name"],
        },
    },
    {
        "name": "update_template_draft",
        "description": "Replace a draft template's source.",
        "parameters": {
            "type": "object",
            "properties": {"template_id": {"type": "string"}, "source": {"type": "string"}},
            "required": ["template_id", "source"],
        },
    },
    {
        "name": "validate_template",
        "description": "Test-compile a template against sample data; marks it ready on success.",
        "parameters": {
            "type": "object",
            "properties": {"template_id": {"type": "string"}},
            "required": ["template_id"],
        },
    },
    {
        "name": "set_default_template",
        "description": (
            "Make a template the default used when no template is chosen. "
            "The template must already be 'ready' (validate it first)."
        ),
        "parameters": {
            "type": "object",
            "properties": {"template_id": {"type": "string"}},
            "required": ["template_id"],
        },
    },
    {
        "name": "duplicate_template",
        "description": (
            "Copy an existing template's source + default formatting into a new draft "
            "(new_template_id must be an unused lowercase slug). The copy starts as a "
            "draft and must be validated before use."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "template_id": {"type": "string", "description": "id of the template to copy"},
                "new_template_id": {"type": "string", "description": "unused lowercase slug"},
                "display_name": {"type": "string"},
            },
            "required": ["template_id", "new_template_id"],
        },
    },
    {
        "name": "delete_template",
        "description": "Delete a template. The default template cannot be deleted.",
        "parameters": {
            "type": "object",
            "properties": {"template_id": {"type": "string"}},
            "required": ["template_id"],
        },
    },
]

_EXECUTORS = {
    "list_base_resumes": tool_list_base_resumes,
    "get_resume": tool_get_resume,
    "edit_resume": tool_edit_resume,
    "propose_edits": tool_propose_edits,
    "propose_project": tool_propose_project,
    "analytics_activity": tool_analytics_activity,
    "analytics_gap_frequency": tool_analytics_gap_frequency,
    "analytics_base_summaries": tool_analytics_base_summaries,
    "read_attachment": tool_read_attachment,
    "kb_list_entities": tool_kb_list_entities,
    "kb_get_entity": tool_kb_get_entity,
    "kb_capture": tool_kb_capture,
    "get_career_context": tool_get_career_context,
    "list_templates": tool_list_templates,
    "get_template": tool_get_template,
    "create_template_draft": tool_create_template_draft,
    "update_template_draft": tool_update_template_draft,
    "validate_template": tool_validate_template,
    "set_default_template": tool_set_default_template,
    "duplicate_template": tool_duplicate_template,
    "delete_template": tool_delete_template,
}


def openai_tool_specs() -> list[dict[str, Any]]:
    return [{"type": "function", "function": spec} for spec in TOOL_SPECS]


def execute_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> Any:
    """Run a tool; ToolError (and bad args) become an error payload for the model."""
    executor = _EXECUTORS.get(name)
    if executor is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return executor(ctx, **arguments)
    except ToolError as e:
        return {"error": str(e)}
    except TypeError as e:
        return {"error": f"Bad arguments for {name}: {e}"}
