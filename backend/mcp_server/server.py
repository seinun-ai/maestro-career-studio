from __future__ import annotations

import functools
import inspect
import logging
import os
from collections.abc import Callable
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import ConfigDict, Field, with_config

from app.schemas.resume_edit import op_kinds_ordered, render_ops_shapes
from mcp_server import workflow
from mcp_server.client import BackendClient, BackendError
from mcp_server.profiles import allowed_tools, apply_profile_filter

logger = logging.getLogger(__name__)

mcp = FastMCP("maestro-career-studio")
_client = BackendClient()

# The op vocabulary belongs in the SCHEMA, not only in a tool's prose. `ops` is
# list[dict], so without this the machine-readable contract reads "array of
# arbitrary objects" and an agent inspecting the schema concludes no op can do
# what it needs — then falls back to the wholesale-replace tool next door. That
# is not hypothetical: it happened on 2026-08-04 (three whole-resume PUTs to
# change one date each). The kind list is RENDERED from the schema-side
# registry (app/schemas/resume_edit.py) so this copy can never miss or invent
# a kind; one shared constant, because three copies of this text would be a
# duplication finding in the slop ratchet.
_EDIT_OPS_FIELD = Field(
    description=(
        "Typed edit ops. Each is an object with a `kind`, one of: "
        f"{' | '.join(op_kinds_ordered())}. "
        "To change a field ON an entry — dates, title, company, project name, link, "
        "tech — use replace_entry with that entry's index and the full edited entry "
        "object; it is scoped to that one entry (a whole-resume replace is the "
        "separate update_base_resume tool). See the tool description for each op's shape. "
        "add_extra_section/replace_extra_section `value` is "
        '{key,title,enabled,type:"entries"|"bullets"} plus EITHER '
        "entries:[{heading,subheading?,location?,date?,link?,enabled,bullets:[str]}] "
        "OR bullets:[str] — never both; unknown keys are rejected (400, extra=\"forbid\")."
    )
)
EditOps = Annotated[list[dict], _EDIT_OPS_FIELD]


class GapResolution(TypedDict):
    """Machine-readable action vocabulary for resolve_gaps."""

    gap_id: str
    action: Literal[
        "add_keyword",
        "user_input",
        "attach_project",
        "skip",
        "enable_entry",
        "port_kb_point",
        "cannot_confirm",
    ]
    payload: NotRequired[dict[str, Any]]


# Immune to the ~2048-char tool-description truncation: lives on the param schema.
_RESOLUTIONS_FIELD = Field(
    description=(
        "Batch of {gap_id, action, payload}. Actions: add_keyword | user_input | "
        "attach_project | skip | enable_entry | port_kb_point | cannot_confirm. "
        "Validated as ONE unit — one invalid item saves NOTHING (existing saved "
        "resolutions untouched). Merge-by-gap_id; omit never "
        "deletes — resend skip to retract. Payloads: add_keyword needs "
        "placement_target {section, index_or_category} (+ optional wording); "
        "a MISSING skill may use add_keyword ONLY with section=skills. "
        "user_input {text}. attach_project {project_name}. enable_entry "
        "{section: experience|projects, index}. port_kb_point {kb_point_id, "
        "kb_entity_id, placement_target, wording}. skip/cannot_confirm {} "
        "(cannot_confirm also stores a durable user_cannot_confirm KB record; "
        "only legal on gaps that ask a question, i.e. where user_input is allowed)."
    )
)
GapResolutions = Annotated[list[GapResolution], _RESOLUTIONS_FIELD]


class FilledFieldInput(TypedDict):
    """One form field as record_filled_answers stores it."""

    question: str
    source: Literal["profile", "resume", "custom", "written", "inferred", "you", "upload"]
    answer: NotRequired[str | int | float | list[str] | None]
    section: NotRequired[str | None]
    required: NotRequired[bool]
    options_count: NotRequired[int | None]
    slot: NotRequired[str | None]
    eeo: NotRequired[bool]
    edited_by_you: NotRequired[bool]


# Immune to the ~2048-char tool-description truncation: lives on the param schema.
_FILLED_FIELDS_FIELD = Field(
    description=(
        "The page's fields as filled: {question, source, answer?, section?, required?, "
        "options_count?, slot?, eeo?, edited_by_you?}. answer is a string, or for a "
        "multi-select the list of ticked options with options_count, the number offered. "
        "source: profile (the autofill profile) | resume (work history or skills) | custom (a "
        "saved answer) | written (prose composed for this form) | inferred (a choice no saved "
        "fact states) | you (typed or changed by the user) | upload (a file: slot resume or "
        "cover_letter, answer the file name). slot names the profile fact, such as "
        "preferences.willing_to_relocate. eeo marks a voluntary self-identification question."
    )
)
FilledFields = Annotated[list[FilledFieldInput], _FILLED_FIELDS_FIELD]


@with_config(ConfigDict(extra="forbid"))
class RunCounts(TypedDict, total=False):
    """What a run did, as whole numbers."""

    found: int
    proposed: int
    skipped: int
    tailored: int
    updated: int
    needs_you: int


@with_config(ConfigDict(extra="forbid"))
class RunReport(TypedDict, total=False):
    """What record_run stores beyond the automation and its outcome."""

    counts: RunCounts | None
    digest: str | None
    job_ids: list[str] | None


_RUN_REPORT_FIELD = Field(
    description=(
        "{counts?, digest?, job_ids?}. counts: whole numbers for found, proposed, skipped, "
        "tailored, updated and needs_you; other keys are refused. digest: the run's plain-text "
        "summary, kept to its first 2000 characters; it holds counts and title-and-company lines, "
        "not email text. job_ids: the jobs the run touched, the first 50 kept; unknown job ids "
        "are dropped."
    )
)
RunReportArg = Annotated[RunReport | None, _RUN_REPORT_FIELD]

_INGEST_DATA_FIELD = Field(
    description=(
        "ResumeData. Only contact.name and contact.email are required. 422 if "
        "any source fails validation or on a duplicate SOURCE key (re-running "
        "the same resume_key is a merge, not an error); atomic either way: "
        "nothing persisted on a 422."
    )
)


# Tool annotations: the spec defaults are destructive=true and openWorld=true when
# a hint is omitted, so every tool states all four through one of these two. The
# title goes in twice (Tool.title and annotations.title) because clients read
# either. open_world means the call can reach the configured LLM provider
# (services/llm.py); no MCP-reachable path fetches a URL.
def _read(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "annotations": ToolAnnotations(
            title=title,
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    }


def _write(
    title: str, *, destructive: bool, idempotent: bool, open_world: bool = False
) -> dict[str, Any]:
    return {
        "title": title,
        "annotations": ToolAnnotations(
            title=title,
            readOnlyHint=False,
            destructiveHint=destructive,
            idempotentHint=idempotent,
            openWorldHint=open_world,
        ),
    }


def _guard(fn):
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except BackendError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


def _best_effort_hint(compose: Callable[[], dict[str, Any] | None]) -> dict[str, Any] | None:
    """Compose a `next` hint AFTER a write has landed, where a failed lookup
    (the settings read, the quick-tailor profile, setup status) is no reason to
    report the whole tool as failed: the work is done, and a retry would repeat
    it (a second `<slug>_2` base, a superseded session). A failed lookup yields
    `next: null`, the same value as a suppressed hint. Only BackendError is
    absorbed; a bug in the composer still raises."""
    try:
        return compose()
    except BackendError as exc:
        logger.warning("next-step hint skipped after a completed write: %s", exc)
        return None


def _client_label(ctx: Context | None) -> str | None:
    """Name the MCP client for the KB timeline and a proposal's filer.

    clientInfo is what the peer declared at initialize, so it is a label, not an
    authenticated identity — good enough for "which session added this", not for
    anything security-bearing. Falls back to an env override, then to nothing
    (the backend still records origin='mcp').
    """
    session = getattr(ctx, "session", None)
    params = getattr(session, "client_params", None)
    info = getattr(params, "clientInfo", None)
    name = str(getattr(info, "name", "") or "").strip()
    if name:
        return name
    return (
        os.environ.get("MAESTRO_CS_MCP_CLIENT")
        or os.environ.get("CAREER_STUDIO_MCP_CLIENT")
        or ""
    ).strip() or None


# ---------- next-step hints (mcp_server/workflow.py) ----------
# The wrapped tools below (score_ats, create_tailoring_session, resolve_gaps,
# tailor_session, render_pdf, quick_tailor) all need the same two facts to
# compose a hint: which tools THIS profile registered, and whether the user's
# Settings switch allows hints at all. Centralized here so each tool reads as
# "do the work, then ask for a hint" rather than re-deriving both facts inline.


def _active_allowed_tools() -> "frozenset[str] | None":
    """The active MAESTRO_CS_MCP_PROFILE's allowlist, so a hint never names a
    tool this session did not register (workflow.py's invariant)."""
    return allowed_tools(_ACTIVE_PROFILE)


def _hints_enabled() -> bool:
    """The user's master switch (GET /api/settings/mcp-workflow). Off means no
    hint is ever composed, whatever an individual tool call asks for — this is
    the one control the server itself can hold (see workflow.py's "Who
    controls the hints")."""
    return bool(_client.get_mcp_workflow_settings().get("hints", True))


def _session_hint(
    session: dict[str, Any], *, instruction: str | None = None
) -> dict[str, Any] | None:
    """Shared by create_tailoring_session, resolve_gaps, and quick_tailor —
    all three return a session in the same shape, so the same hint composer
    applies regardless of which call produced it."""
    return _best_effort_hint(
        lambda: workflow.next_after_session(
            session,
            allowed_tools=_active_allowed_tools(),
            hints_enabled=_hints_enabled(),
            instruction=instruction,
        )
    )


def _instruction_from_profile(profile: dict[str, Any]) -> str | None:
    """Mirrors app.services.quick_tailor._instruction_fallback exactly: the
    saved quick-tailor profile's standing instruction, stripped, or None when
    blank. Kept as a literal copy rather than a shared import — the two live
    in different processes' import graphs (this module never imports
    app.services.quick_tailor), and the rule is one line long."""
    return (profile.get("instruction") or "").strip() or None


# ---------- read ----------
@mcp.tool(**_read("List Base Resumes"))
@_guard
def list_base_resumes() -> Any:
    """List all base resumes (slug, display name, summary)."""
    return _client.list_base_resumes()


@mcp.tool(**_read("Get Base Resume"))
@_guard
def get_base_resume(slug: str) -> Any:
    """Get a base resume's full data JSON, render status, and metadata."""
    return _client.get_base_resume(slug)


@mcp.tool(**_read("List Saved Jobs"))
@_guard
def list_jobs(
    limit: Annotated[int, Field(ge=1, le=500)] = 50,
    offset: Annotated[int, Field(ge=0)] = 0,
    without_application: bool | None = None,
) -> Any:
    """List stored jobs as a thin summary array, newest first, paged by limit
    (default 50, max 500) and offset; a page shorter than limit is the last.
    Each item is a slim projection (company, title, role_category, level,
    employment_type, work_mode, location, salary, work_authorization,
    opt_accepted) of roughly 0.8k characters, with no raw_text or
    extracted_json; use get_job for full detail. Optionally only jobs without
    an application."""
    return _client.list_jobs(
        limit=limit, offset=offset, without_application=without_application
    )


@mcp.tool(**_read("Get Job Details"))
@_guard
def get_job(job_id: str) -> Any:
    """Get a job with its most recent application."""
    return _client.get_job(job_id)


@mcp.tool(**_read("Get Application"))
@_guard
def get_application(application_id: str) -> Any:
    """Get one application's full detail: the tailored resume (customized_json)
    and the joined job. Use compare_ats for before/after scores."""
    return _client.get_application(application_id)


@mcp.tool(**_read("List Referral Contacts"))
@_guard
def list_referrals() -> Any:
    """List referral contacts (company, careers URL, contact name, notes, applications_count)."""
    return _client.list_referrals()


@mcp.tool(**_read("List Application Answers"))
@_guard
def list_qa_entries(application_id: str) -> Any:
    """List the generated screening answers and cover letters for an application, newest first."""
    return _client.list_qa_entries(application_id)


# ---------- health check ----------
@mcp.tool(**_write("Run Resume Health Check", destructive=False, idempotent=False, open_world=True))
@_guard
def run_health_check(kind: Literal["base", "application"], key: str) -> Any:
    """Run the JD-independent resume health check on a base resume or a tailored
    application. `kind` is 'base' (then `key` is the base-resume slug) or
    'application' (then `key` is the application id). Classifies every bullet on
    the evidence ladder, checks structure/content gates, and returns
    {score, grade, tier, next_grade, gates, counts, findings} ranked by what each defect costs.
    Concrete qualitative results can earn full credit. An ask/fix finding carries
    question, ask_kind (measure|detail|reword), measure_target, alt_question, gain
    and evidence. Notes score zero: the evidence.no_numbers flag and language.*
    wording notes. Disputes and the word bank are web-only for now.
    create_tailoring_session returns 409 when the base resume's latest, current
    report has an unwaived failing fatal gate; this call produces that report."""
    return _client.run_health_check(kind, key)


@mcp.tool(**_read("Get Resume Health Report"))
@_guard
def get_health_report(kind: Literal["base", "application"], key: str) -> Any:
    """Fetch the most recent stored health report for a base resume or application
    without re-running it. `kind` is 'base' or 'application', `key` is the slug or
    application id. Returns {score, grade, tier, next_grade, gates, counts, findings}
    (fields as in run_health_check), or an error if no report exists yet
    (run_health_check creates one)."""
    return _client.get_health_report(kind, key)


@mcp.tool(**_write("Waive Health Gate", destructive=False, idempotent=True))
@_guard
def waive_health_gate(
    kind: Literal["base", "application"], key: str, gate_id: str, reason: str
) -> Any:
    """Escape hatch for the fatal-health-gate 409 from create_tailoring_session.
    Waiving bypasses a safety gate, so the stored waiver records an explicit user
    decision: `reason` is the user's stated reason for bypassing the named gate.
    The server stores the waiver as given and does not verify who made the
    decision. `kind` is 'base' or 'application', `key` is the resume slug or
    application id. The 409 names each failing gate by its label; the `gate_id`
    to pass is that gate's `gates[].id` in get_health_report."""
    return _client.waive_health_gate(kind, key, gate_id, reason)


@mcp.tool(**_write("Remove Health Gate Waiver", destructive=True, idempotent=True))
@_guard
def unwaive_health_gate(
    kind: Literal["base", "application"], key: str, gate_id: str
) -> Any:
    """Remove a health-gate waiver and restore the gate's protection. Deletes the
    stored waiver for this gate (a no-op if none exists), so the gate blocks
    create_tailoring_session with a 409 again. The counterpart waive_health_gate
    records the user's decision to bypass a failing gate."""
    return _client.unwaive_health_gate(kind, key, gate_id)


# ---------- JD ingest ----------
@mcp.tool(**_write("Save Extracted Job", destructive=False, idempotent=True))
@_guard
def store_extracted_jd(
    extracted_json: dict,
    raw_text: str | None = None,
    source_url: str | None = None,
    source: Literal["user", "agent"] = "user",
) -> Any:
    """Store a job description the caller already extracted into JSON (the backend
    makes no LLM call).

    extracted_json must match the app's JobExtraction schema: company, title,
    role_category, level, employment_type, work_mode, city/state/country,
    location_raw, salary_min/max, salary_period,
    work_authorization: "sponsorship_available"|"no_sponsorship"|"citizen_or_gc_required"|"unstated",
    opt_accepted: "yes"|"stem_opt_ok"|"no"|"unstated",
    years_experience_min/max, skills[{skill_name, skill_category,
    requirement_level: "required"|"preferred"|"mentioned"}],
    responsibilities[], qualifications[]. ANY other work_authorization or
    opt_accepted value silently normalizes to "unstated" with no error.
    source is "user" (default) or "agent"; source="agent" marks agent-hunted jobs,
    which need an open proposal before the apply helpers act on them. A job
    stored with source="user" is not proposal-gated: the server skips the
    open-proposal check for any non-agent source. Returns the stored job.
    """
    return _client.store_extracted_jd(extracted_json, raw_text=raw_text, source_url=source_url, source=source)


# ---------- agentic job search ----------
@mcp.tool(**_read("Get Job Search Brief"))
@_guard
def get_job_search_brief() -> Any:
    """Read the server-composed job-search brief: profile constraints (location,
    relocation, work-auth VERBATIM plus warnings[] when values are contradictory
    or missing — never guessed), persona text (may be empty, in which case the
    analytics-derived targets are the stronger signal), active base-resume
    summaries, role mix, top required skills, build areas (per-skill tier plus
    category_label, the plain-words label for the raw category key), referral
    careers pages (company + careers_url + has_contact), and counts of jobs
    captured in the last 30 days by role category. It is the entry point of the
    agentic job-search workflow (playbook: docs/agentic-job-search.md), which
    covers capture, scoring and proposals; applying is outside its scope."""
    return _client.get_job_search_brief()


@mcp.tool(**_read("Get Career Context"))
@_guard
def get_career_context() -> Any:
    """Read the full composed career context from the Career KB: `resume` (the
    approved-points resume view assembled from profile + non-archived entities)
    and `memory` (the beyond-the-resume string: identity facts and entity notes
    that don't belong on a resume). Intended as grounding for writing about the
    user's career (LinkedIn posts, outreach drafts), optionally with
    get_base_resume for a specific resume's voice. `resume` carries approved
    points only; `memory` also includes the profile summary and notes and the
    non-archived entities' notes. It never invents facts, metrics, employers,
    or dates; anything absent from it (and from a fetched base resume) is not
    part of the user's recorded career. It carries no IDs: kb_list_entities / kb_get_entity / kb_list_points
    return the IDs needed to correct anything."""
    return _client.get_career_context()


@mcp.tool(**_read("Get Career Export"))
@_guard
def get_career_export() -> str:
    """Read the exact portable career.md generated from the current Career KB.

    Returns deterministic Markdown for copy-out, download-equivalent use, or
    Markdown-oriented grounding. For structured resume and memory fields, use
    get_career_context. Read-only; this does not alter tailoring behavior.
    """
    return _client.get_career_export()


# ---------- Career KB: read with IDs ----------
@mcp.tool(**_read("List Career Entities"))
@_guard
def kb_list_entities(kind: str | None = None, status: str | None = None) -> Any:
    """List Career KB entities with their IDs (get_career_context returns prose
    with no IDs; this tool returns the IDs needed to edit). Optionally filter by
    kind (experience|project|education|certification|extra) or status
    (ongoing|completed|archived). Each item carries point_count, draft_count and
    approved_count (the bullets a resume can use; retired ones are in point_count only)."""
    return _client.list_kb_entities(kind=kind, status=status)


@mcp.tool(**_read("Get Career Entity"))
@_guard
def kb_get_entity(entity_id: str) -> Any:
    """Full detail for one Career KB entity: dates, notes, its points (each with
    id, text and state), attached documents, and the activity timeline."""
    return _client.get_kb_entity(entity_id)


@mcp.tool(**_read("List Career Points"))
@_guard
def kb_list_points(
    state: str | None = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 50,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> Any:
    """List Career KB points across all entities, optionally by state
    (draft|approved|retired), oldest first. An unfiltered call returns the first
    `limit` points (default 50, max 100); `offset` pages on. Each row carries id,
    entity_id/entity_title/entity_kind, text, state, origin, tags and dates; the
    per-use port history and merge provenance are omitted (kb_get_entity)."""
    return _client.list_kb_points(state=state, limit=limit, offset=offset)


# ---------- Career KB: write ----------
# Every tool here mints DRAFT content, kb_ingest_resume included — an agent
# transcribing a resume is not the user approving it. The single way to
# approve from MCP is kb_approve_points, and it is consent-gated: call it only
# after the user has actually seen these points and said yes. Never state a
# date, employer, credential or metric the user did not give you — a fabricated
# fact written here becomes part of their permanent career record.
@mcp.tool(**_write("Capture Career Notes", destructive=False, idempotent=False, open_world=True))
@_guard
def kb_capture(
    text: str,
    entity_id: str | None = None,
    ctx: Context | None = None,
) -> Any:
    """Capture free-text career news into DRAFT points. A model matches it to an
    existing entity or proposes a new one (this call uses the configured LLM
    provider); pass entity_id to force placement. Points land as drafts for the
    user to approve at /career. The text is stored as the user's own words and
    facts; the server does not verify it."""
    return _client.kb_capture(
        text,
        entity_id=entity_id,
        origin_detail=_client_label(ctx),
    )


@mcp.tool(**_write("Edit Career Point", destructive=True, idempotent=True))
@_guard
def kb_edit_point(
    point_id: str,
    text: str | None = None,
    tags: list[str] | None = None,
    ctx: Context | None = None,
) -> Any:
    """Reword a Career KB point or retag it. Changing the text sends the point
    back to DRAFT, so it leaves the composed resume and career export until it
    is re-approved (kb_approve_points or /career). Cannot approve, retire or
    delete a point."""
    return _client.kb_edit_point(
        point_id,
        text=text,
        tags=tags,
        origin_detail=_client_label(ctx),
    )


@mcp.tool(**_write("Create Career Entity", destructive=False, idempotent=False))
@_guard
def kb_create_entity(
    kind: str,
    title: str,
    org: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    status: str | None = None,
    detail: dict[str, Any] | None = None,
    notes: str | None = None,
    ctx: Context | None = None,
) -> Any:
    """Create a Career KB entity — kind is experience|project|education|
    certification|extra. Writes immediately and is not draft-gated: the entity,
    with the dates and wording supplied, is stored as the user's own career
    record, and no duplicate is blocked (possible_duplicates hints are
    returned). `detail` is a free-form dict (conventional keys: `tech` list[str]|str,
    `link`, `field`); kind="extra" REQUIRES `section_key` (lowercase slug),
    `section_type` ("entries"|"bullets"), and `section_title` nested inside
    `detail` — no top-level params exist. A certificate PDF still has to be
    uploaded from the web UI."""
    return _client.create_kb_entity(
        kind=kind,
        title=title,
        org=org,
        start_date=start_date,
        end_date=end_date,
        status=status,
        detail=detail,
        notes=notes,
        origin_detail=_client_label(ctx),
    )


@mcp.tool(**_write("Edit Career Entity", destructive=True, idempotent=True))
@_guard
def kb_edit_entity(
    entity_id: str,
    title: str | None = None,
    org: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    status: str | None = None,
    notes: str | None = None,
    detail: dict[str, Any] | None = None,
    ctx: Context | None = None,
) -> Any:
    """Fix an entity's dates, title, org, notes or lifecycle status
    (ongoing|completed|archived). Omitted fields are left alone. Writes
    immediately with no draft gate; each supplied value replaces the stored one.
    Kind cannot be changed here — that is a rebuild, not a correction."""
    return _client.kb_edit_entity(
        entity_id,
        origin_detail=_client_label(ctx),
        title=title,
        org=org,
        start_date=start_date,
        end_date=end_date,
        status=status,
        notes=notes,
        detail=detail,
    )


@mcp.tool(**_write("Edit Career Profile", destructive=True, idempotent=True))
@_guard
def kb_edit_profile(
    contact: dict[str, Any] | None = None,
    summary: str | None = None,
    skills: list[Any] | None = None,
    notes: str | None = None,
    ctx: Context | None = None,
) -> Any:
    """Update the Career KB profile: contact block, career summary, skill groups,
    notes. Omitted fields are left alone; a supplied field REPLACES its stored
    value wholesale (current values are in get_career_context), so changing one
    list item means sending the full merged field. Writes immediately with no
    draft gate."""
    return _client.kb_edit_profile(
        contact=contact,
        summary=summary,
        skills=skills,
        notes=notes,
        origin_detail=_client_label(ctx),
    )


@mcp.tool(**_write("Import Parsed Resume", destructive=False, idempotent=True))
@_guard
def kb_ingest_resume(
    resume_key: str,
    data: Annotated[dict[str, Any], _INGEST_DATA_FIELD],
    brief: bool = False,
    ctx: Context | None = None,
) -> Any:
    """Persist one caller-parsed resume into the Career KB. No in-house LLM.

    Points land as DRAFTS and appear on no resume until approved with
    kb_approve_points (or at /career), which records the user's approval.

    HONESTY: `data` is stored as the user's own resume content, so a faithful
    transcription is expected. The server does not detect embellishment,
    rewording or invented metrics (same trust model as caller-authored tailor
    ops); approved points become part of the career record.

    ENTITY NAMES: matching is two-pass. Exact identity-key first (experience:
    company+role+start_date; projects: name; education: institution+degree;
    certs: the string), then a near-identity pass for experience/projects/certs
    (token-subset; projects allow ≤2 extra tokens). Education and extra are
    identity-key-only. Different spellings can merge on the second pass;
    names outside its coverage still fork.

    Re-running the same resume_key is a merge: no duplicate entities; a bullet
    already on the entity (even retired) is not re-created. resume_key must
    match ^[a-z0-9][a-z0-9_]*$.

    `data` is ResumeData (only contact.name and contact.email required).
    Sections: contact, summary, skills[{category, items}], experience, projects,
    education, certifications[str], extra_sections. Experience:
    {company, role, location?, start_date?, end_date?, bullets[str]}.
    extra_sections are NOT stored in the KB (report warns); they can be added to
    a base resume after it exists. skills/contact/summary go to the KB profile
    (no draft state). Profile seeding is first-write-wins, so the first resume
    ingested determines the profile.

    Response {report, next}. report: created/matched entity ids, DRAFT point
    ids, counts, warnings. next is a hint (null when suppressed/unavailable); brief=True
    (multi-resume loops) suppresses it before any settings read. 422 on a
    ResumeData validation failure or duplicate source key (atomic).
    """
    report = _client.kb_ingest_resume(
        resume_key, data, origin_detail=_client_label(ctx),
    )
    if brief:
        return {"report": report, "next": None}
    return {
        "report": report,
        "next": _best_effort_hint(
            lambda: workflow.next_after_kb_ingest(
                report,
                allowed_tools=_active_allowed_tools(),
                hints_enabled=_hints_enabled(),
            )
        ),
    }


@mcp.tool(**_write("Approve or Retire Career Points", destructive=True, idempotent=True))
@_guard
def kb_approve_points(
    point_ids: list[str],
    state: Literal["approved", "retired"] = "approved",
) -> Any:
    """Batch-set Career KB point state to approved or retired. Approved points are
    the only ones that appear on composed resumes and the career export; this is
    the single approval path available over MCP. The state written is the user's
    decision about the listed points; the server does not check that the user
    reviewed them (a convention, not enforcement, as with record_consent).

    state is approved|retired only; bulk-to-draft is impossible. 1-500 ids;
    repeats collapse to one result row. Per-id results are honest: unknown ids
    return ok=false detail="not found" and the rest still proceed; a failed id
    fails the same way until corrected (kb_list_points returns the current ids).

    Response is {results: [{id, ok, state, detail}], next}. next is a hint
    (null when suppressed or unavailable).
    """
    body = _client.kb_approve_points(point_ids, state=state)
    results = body.get("results") or [] if isinstance(body, dict) else []
    return {
        "results": results,
        "next": _best_effort_hint(
            lambda: workflow.next_after_bulk_state(
                results,
                requested_state=state,
                allowed_tools=_active_allowed_tools(),
                hints_enabled=_hints_enabled(),
            )
        ),
    }


@mcp.tool(**_write("Sync Resume to Career KB", destructive=False, idempotent=True))
@_guard
def kb_sync_base(slug: str) -> Any:
    """Sync one base resume into the Career KB.

    Deterministic: zero LLM calls. New material lands as DRAFT points
    (origin=base_sync) for the user to approve at /career. Never edits
    resumes. Safe to rerun — a second call is a no-op when already in sync.
    """
    return _client.kb_sync_base(slug)


@mcp.tool(**_write("Create Resume from Career KB", destructive=False, idempotent=False))
@_guard
def create_base_resume_from_kb(
    entity_ids: list[str],
    role_category: str | None = None,
    role_label: str | None = None,
    display_name: str | None = None,
    include_summary: bool = False,
    summary: str | None = None,
) -> Any:
    """Compose a new base resume from selected Career KB entities. LLM-free.

    entity_ids is REQUIRED. An empty list composes nothing and 422s — that is
    deliberate; omitting the argument is not allowed because it would have to
    mean "the whole KB". A role_label or role_category is required (no slug
    argument). role_category is strict: an unknown value 422s, no
    normalization. An unmatched role_label maps to role_category "other" and
    slug `other`/`other_2`…; display_name never affects the slug, which is
    `base.slug` in the response. Only APPROVED points under the selected entities compose —
    points from kb_ingest_resume are DRAFTS and contribute nothing until
    kb_approve_points (or the user, at /career) approves them.
    skills and contact arrive in full from the KB profile regardless of entity
    selection (the KB has no per-entity skill data), so skills may need trimming
    on the resulting base. The
    whole-career summary is dropped unless include_summary, or pass a reviewed
    summary. A 422 "no resume content" means the selected entities have no
    approved points.

    Response is {base, next}. next is a hint (null when suppressed or when its
    settings read fails; the base is created either way, and repeating the call
    mints a second slug, <slug>_2).
    """
    base = _client.create_base_resume_from_kb(
        entity_ids,
        role_category=role_category,
        role_label=role_label,
        display_name=display_name,
        include_summary=include_summary,
        summary=summary,
    )
    return {
        "base": base,
        "next": _best_effort_hint(
            lambda: workflow.next_after_base_from_kb(
                base if isinstance(base, dict) else {},
                allowed_tools=_active_allowed_tools(),
                hints_enabled=_hints_enabled(),
            )
        ),
    }


@mcp.tool(**_read("Get Autofill Profile"))
@_guard
def get_autofill_profile(application_id: str | None = None, base: str | None = None) -> Any:
    """Read the user's application-form autofill data: `profile` (personal
    contact + address, typed work-authorization answers, preferences like
    salary/notice/relocation, education, `languages` — each a language with
    read/speak/write level Basic/Intermediate/Fluent and separate `native`
    and `fluent` booleans — custom Q&A presets), plus `employment`
    blocks and `skills` from the selected resume when application_id or base is
    given. Response is labeled `source: "profile"` and includes
    `canonical_identity` (`legal_first`, `legal_last`, `preferred`) mapped only
    from stored autofill personal fields; it is the source of truth for form
    identity fields and takes precedence over ATS-parsed values. This is the
    same feed the Chrome extension's deterministic fill uses, so it supplies
    real stored values for ATS forms. EEO/demographic answer values
    (`profile.eeo`) are returned ONLY when Profile standing consent is active
    (`eeo_consent.enabled`) and are stripped otherwise; when returned they are
    the user's stored answers, intended for Playwright/agent fill verbatim with
    no inference or model-authored values. `eeo.gender` is male, female,
    non_binary, self_describe or decline; with self_describe,
    `eeo.gender_self_describe` is the user's own words for a form's
    self-describe box. A form lacking a matching option is left to the user.
    Missing EEO values are completed by the user in Profile or in the browser;
    consented answers are not pasted or re-dictated through chat. A value absent
    here (e.g. an unstored county) is not in the profile and is not guessable.
    WOTC, signatures and terms are human-only."""
    return _client.get_autofill_context(application_id=application_id, base=base)


@mcp.tool(**_read("Find Job by URL"))
@_guard
def find_job_by_url(source_url: str) -> Any:
    """Answer "is this posting already captured?", so an extraction can be
    skipped: posting-equality source_url lookup returning {found, job,
    application_exists, application_id}. Matching ignores query strings and
    fragments (?utm_*, ?gh_src=, #apply) and treats the posting's own
    sub-paths (/apply, /application) as the same posting, so tracking
    parameters need not be stripped from the input. A search-results or
    employer-index URL still matches nothing. found=False means the posting
    is new; store_extracted_jd still dedupes authoritatively via
    already_existed."""
    return _client.find_job_by_url(source_url)


# ---------- base resume writes ----------
@mcp.tool(**_write("Replace Base Resume Data", destructive=True, idempotent=True))
@_guard
def update_base_resume(slug: str, data: dict, display_name: str | None = None) -> Any:
    """Replace a base resume's data (the full ResumeData object, required).
    Optionally also update display_name. PUT replaces the whole resume body."""
    return _client.update_base_resume(slug, data=data, display_name=display_name)


@mcp.tool(**_write("Set resume target", destructive=False, idempotent=True))
@_guard
def set_base_resume_identity(
    slug: str,
    display_name: str | None = None,
    role_category: str | None = None,
    role_label: str | None = None,
    countries: list[str] | None = None,
    company: str | None = None,
    focus: str | None = None,
) -> Any:
    """Set what a base resume is written for. Only the fields passed change.
    `countries` (ISO codes) restricts which jobs the resume is scored and
    recommended for: a job in another country skips it, and a resume sent to
    one is flagged. `role_category`/`role_label` name the role, `company` and
    `focus` are free-text emphasis hints for tailoring (at most 80 characters
    each), and `display_name` renames the resume. `[]` clears countries and
    `""` clears company or focus. An unknown country or an over-long value is a
    422 that saves none of the fields. Resume content, versions and the PDF
    are never touched."""
    return _client.set_base_resume_identity(
        slug,
        display_name=display_name,
        role_category=role_category,
        role_label=role_label,
        countries=countries,
        company=company,
        focus=focus,
    )


# The docstring IS the agent's API reference, so its op block is RENDERED from
# the schema-side registry (a hand-copied block once listed 8 of 16 kinds).
# Set via __doc__ before decoration: _guard's functools.wraps propagates it to
# what FastMCP registers; an f-string literal would not be a docstring at all.
_EDIT_BASE_RESUME_DOC = f"""Apply typed edit ops to a base resume. replace_entry changes a field on one
    entry (dates, title, company, project name, link, tech) given that entry's
    index and the full edited entry; update_base_resume instead replaces the
    whole resume body (PUT). ExtraSection shape is on `ops` (ATS-neutral).

    Indices are 0-based into the FULL array (incl. enabled:false), as returned by
    get_base_resume, never PDF order. Response `applied` echoes each op. Kinds:
{render_ops_shapes()}
    <sec>=experience|projects|education (toggle_entry/add_bullet: experience|projects).
    section_key is ExtraSection.key. Bad index/category/key → error. Re-renders PDF.
    Every response carries `render_error`: non-null means the automatic re-render
    failed and the existing PDF is stale."""


def _doc(text: str):
    """Attach a generated docstring before _guard/mcp.tool() read it."""

    def deco(fn):
        fn.__doc__ = inspect.cleandoc(text)
        return fn

    return deco


@mcp.tool(**_write("Edit Base Resume", destructive=True, idempotent=False))
@_guard
@_doc(_EDIT_BASE_RESUME_DOC)
def edit_base_resume(slug: str, ops: EditOps) -> Any:
    return _client.edit_base_resume(slug, ops)


@mcp.tool(**_write("Create Base Resume", destructive=False, idempotent=False))
@_guard
def create_base_resume(slug: str, display_name: str, data: dict) -> Any:
    """Create a new base resume. Slug must be lowercase alphanumeric/underscores, not 'master'."""
    return _client.create_base_resume(slug, display_name, data)


@mcp.tool(**_write("Duplicate Base Resume", destructive=False, idempotent=False))
@_guard
def duplicate_base_resume(slug: str, new_slug: str, new_display_name: str | None = None) -> Any:
    """Clone an existing base resume into a new slug."""
    return _client.duplicate_base_resume(slug, new_slug, new_display_name=new_display_name)


@mcp.tool(**_read("List Resume Versions"))
@_guard
def list_resume_versions(kind: Literal["base", "application"], key: str) -> Any:
    """List append-only resume snapshots for one target, newest last.

    kind is "base" (key = base-resume slug) or "application" (key = application
    id). This is NOT render_pdf's target_type vocabulary — there is no
    "base_resume" kind here. Each row is a version summary (number, label,
    created_at); use get_resume_version for the snapshot and diff.
    """
    return _client.list_resume_versions(kind, key)


@mcp.tool(**_read("Get Resume Version"))
@_guard
def get_resume_version(
    kind: Literal["base", "application"], key: str, number: int
) -> Any:
    """Fetch one resume version including its snapshot and the diff vs its parent.

    kind/key as on list_resume_versions: "base"+slug or "application"+id.
    number is the version number from that list.
    """
    return _client.get_resume_version(kind, key, number)


@mcp.tool(**_write("Restore Resume Version", destructive=True, idempotent=False))
@_guard
def restore_resume_version(
    kind: Literal["base", "application"], key: str, number: int
) -> Any:
    """Copy a past version's snapshot into the live resume.

    Restore goes through the standard versioned write path — it is itself a
    new version (history is append-only; nothing is deleted). kind/key as on
    list_resume_versions: "base"+slug or "application"+id. For applications,
    the old PDF is cleared; render_pdf produces a new one. A "base" restore
    re-renders, so the response carries render_note (see render_pdf: non-null
    only when a TeX-less backend rendered a LaTeX template through a Typst
    one) and, if that render failed, render_error — the restore landed either
    way, only the PDF is stale.
    """
    return _client.restore_resume_version(kind, key, number)


@mcp.tool(**_write("Archive Base Resume", destructive=False, idempotent=True))
@_guard
def archive_base_resume(slug: str) -> Any:
    """Hide a base resume from pickers without deleting it.

    Sets archived_at (reversible timestamp, not a delete). Archived bases drop
    out of list_base_resumes' default view; JSON, PDF, TEX and version history
    stay. Undo with unarchive_base_resume.
    """
    return _client.archive_base_resume(slug)


@mcp.tool(**_write("Unarchive Base Resume", destructive=False, idempotent=True))
@_guard
def unarchive_base_resume(slug: str) -> Any:
    """Restore an archived base resume to list_base_resumes' default view.

    Clears archived_at. The resume is again selectable; nothing else changes.
    """
    return _client.unarchive_base_resume(slug)


# ---------- tailor + render ----------
@mcp.tool(**_write("Rebuild Tailored Resume", destructive=True, idempotent=False))
@_guard
def tailor_application(
    job_id: str, base_resume: str, ops: EditOps, application_id: str | None = None
) -> Any:
    """REBUILD FROM SCRATCH: apply typed edit ops to the BASE resume and store the
    result as customized_json, REPLACING whatever was there before wholesale.

    `ops` carry only the changed fields (same op shapes as edit_base_resume; the
    base is in get_base_resume) — the server starts from the stored base and
    inherits every untouched field from IT, not from any prior tailored draft.
    If an application already has tailored edits (from a previous tailor_application
    or edit_application call), calling this again DESTROYS them — the new result is
    computed fresh from the base, not layered on top. edit_application is the
    in-place alternative that preserves the current tailored draft (refining
    wording, swapping a bullet, retrying after a PDF preview).
    Does NOT trigger AI suggestions. With no application_id, the job's newest
    application for this base resume is updated in place (still replaced wholesale);
    pass application_id to target a specific application explicitly. `ops` accepts
    the FULL vocabulary documented on edit_base_resume — every kind, not just
    the bullet/summary ones: replace_entry is how you change an entry's dates, title,
    company or tech list, and add/replace/remove/move_extra_section handle custom
    sections, which are ATS-neutral.
    """
    return _client.tailor_application(job_id, base_resume, ops, application_id=application_id)


@mcp.tool(**_write("Edit Tailored Resume", destructive=True, idempotent=False))
@_guard
def edit_application(application_id: str, ops: EditOps) -> Any:
    """INCREMENTAL FIX: apply typed edit ops on top of an existing application's
    CURRENT tailored resume (customized_json), preserving every prior edit.

    Falls back to the base resume only when the application has no customized_json
    yet (nothing to preserve). Suited to refining or retrying a tailored resume
    after inspecting PDF previews — swap a bullet, tweak wording, fix one thing —
    without losing the rest of what's already been tailored and without creating
    duplicate applications. tailor_application is the from-scratch alternative:
    it recomputes customized_json off the BASE resume and discards any tailored
    edits already on the application.
    Accepts the FULL op vocabulary documented on edit_base_resume — every
    kind. replace_entry changes an entry's dates, title, company, project name
    or tech list; add/replace/remove/move_extra_section handle the custom
    Publications/Awards/Volunteer sections.

    Op field names (these exact keys, no synonyms):
    {"kind": "replace_bullet", "section": "experience", "index": 0,
     "bullet_index": 2, "value": "New bullet text"} — `kind` (not op/type),
    `index` (not entry_index; 0-based into the FULL array incl. disabled rows),
    `value` (not text).
    Index is 0-based into the full customized_json array (including enabled:false),
    as shown by get_application, not PDF ordinals. Response `applied[].name`
    echoes the entry each op touched.
    Clears pdf_path/tex_path (the old PDF is stale); render_pdf produces a new one.
    """
    return _client.edit_application(application_id, ops)


@mcp.tool(**_write("Update Application Tracking", destructive=True, idempotent=True))
@_guard
def update_application(
    application_id: str,
    status: str | None = None,
    applied_at: str | None = None,
    notes: str | None = None,
    referral_id: str | None = None,
) -> Any:
    """Update an application's tracking fields (status, applied_at, notes, referral_id).

    Only the arguments passed are sent to the backend — the PATCH endpoint is
    driven by which fields were actually set on the request, so omitting an
    argument leaves that field untouched. This tool cannot clear a field back to
    null/empty (e.g. remove notes or unlink a referral): omitting an arg skips it
    entirely rather than sending an explicit null, and clearing a field requires
    the web UI.

    Allowed statuses: draft, applied, interviewing, offered, accepted, rejected,
    withdrawn (anything else is rejected). Setting status to applied,
    interviewing, offered or accepted also closes any open proposal on the job,
    recorded as a declined "applied manually" consent event.

    applied_at sync rule: if you change `status` without also passing `applied_at`,
    the backend keeps applied_at in sync automatically — entering "applied" stamps
    it with the current time (only if not already set), moving back to "draft"
    clears it, and every later stage (interviewing/offered/accepted/rejected/
    withdrawn) preserves whatever applied_at already holds. An explicit
    `applied_at` overrides that sync and must carry a UTC offset
    (e.g. `2026-08-18T14:32:11+00:00`) — a naive value is a 422.
    """
    return _client.update_application(
        application_id,
        status=status,
        applied_at=applied_at,
        notes=notes,
        referral_id=referral_id,
    )


# ---------- apply package ----------
@mcp.tool(**_write("Generate Screening Answers", destructive=False, idempotent=False, open_world=True))
@_guard
def generate_qa_answers(application_id: str, questions: list[str]) -> Any:
    """Generate a batch of screening-question answers for an application.
    `questions` is the complete list of questions to answer in this batch.
    Outreach/cold messages are asked as free-form questions here (e.g. "Write a
    short LinkedIn DM to the hiring manager") — answers are grounded in the
    resume and the application's linked referral contact when one exists."""
    return _client.generate_qa_answers(application_id, questions)


@mcp.tool(**_write("Generate Cover Letter", destructive=True, idempotent=False, open_world=True))
@_guard
def generate_cover_letter(application_id: str, tone: str) -> Any:
    """Generate a cover letter for an application in the requested tone. This
    replaces the application's prior generated cover-letter entry."""
    return _client.generate_cover_letter(application_id, tone)


@mcp.tool(**_write("Render Resume PDF", destructive=False, idempotent=True))
@_guard
def render_pdf(target_type: Literal["base_resume", "application"], target_id: str,
               template_id: str | None = None) -> Any:
    """Render a PDF. target_type is 'base_resume' (target_id=slug) or 'application'
    (target_id=application id). Optional template_id selects a template (either
    engine; must be 'ready'; omit for the default). Response reports
    resolved_template_id / resolved_engine (the template actually used);
    template_fallback=true only when an explicit template_id was passed and the
    resolved id differs — a substitution of the persisted choice is reported
    by render_note, never by the flag. render_note is non-null only when the
    backend has no TeX and a LaTeX template was rendered through a Typst
    template instead; it names both. Returns the render result incl.
    pdf_path, plus a `next` key: for an 'application' render this is the terminal
    apply-readiness hint (autofill_ready, incomplete/blocking groups, a conditional
    browser-handoff offer); for a 'base_resume' render it is always null — a
    base-resume preview isn't part of the score->tailor->render arc, so there is
    nothing to offer."""
    if target_type == "base_resume":
        result = _client.render_base_resume(target_id, template_id=template_id)
        return {**result, "next": None}
    if target_type == "application":
        result = _client.render_application(target_id, template_id=template_id)
        # Only fetch setup status (an extra HTTP call) when a hint could
        # actually use it — the same no-wasted-round-trip rule score_ats's
        # `brief` applies, just without a separate agent-facing switch since
        # there is no batch-rendering loop analogous to triage scoring.
        def compose() -> dict[str, Any] | None:
            if not _hints_enabled():
                return None
            return workflow.next_after_render(
                setup_status=_client.get_setup_status(),
                allowed_tools=_active_allowed_tools(),
                hints_enabled=True,
            )

        return {**result, "next": _best_effort_hint(compose)}
    raise ToolError("target_type must be 'base_resume' or 'application'")


@mcp.tool(**_read("Get Rendered PDF"))
@_guard
def get_rendered_pdf(target_type: Literal["base_resume", "application", "template"], target_id: str) -> Any:
    """Save a rendered PDF locally and render one PNG per page without inlining images.
    target_type 'base_resume'(slug)/'application'(id) returns the last rendered resume
    PDF; 'template'(id) returns the sample preview PDF. Returns {filename, path,
    size_bytes, mime_type, page_count, page_images, em_dash_found, em_dash_pages,
artifact_dir?}. Requires an existing render (render_pdf, or validate_template
    for a template preview). Paths are local to where the backend/MCP server run;
    browser uploads use the copy staged by prepare_application_pdf_upload. The
    PDF and per-page PNGs ({id}.pN.png, ~120 dpi) are written under
    $MAESTRO_CS_PDF_DIR (or a temp dir). This slim response never includes image
    base64; get_rendered_pdf_page_image returns the visual bytes of exactly one
    page. em_dash_found reports whether the PDF contains an em dash (U+2014),
    which rendered resumes in this product are required not to contain;
    em_dash_pages lists the page numbers. (page_count is None / page_images empty
    if the PDF can't be read.)"""
    return _client.get_rendered_pdf(target_type, target_id)


@mcp.tool(**_read("Get PDF Page Image"))
@_guard
def get_rendered_pdf_page_image(
    target_type: Literal["base_resume", "application", "template"],
    target_id: str,
    page_number: int,
    max_dimension_px: int = 1024,
) -> Any:
    """Return one rendered PDF page as an explicit opt-in visual payload.
    page_number is 1-based. max_dimension_px (default 1024) is the longest
    side of the re-rendered PNG; larger values grow the payload, and encoded
    payloads over ~1MB are rejected (a smaller max_dimension_px fits).
    Returns target_type, target_id, page_number, page_count, filename/path/
    size/mime metadata, and page_image_b64 for only the requested PNG.
    Out-of-range page numbers are rejected. Does not change get_rendered_pdf's
    pre-rendered preview PNGs."""
    return _client.get_rendered_pdf_page_image(
        target_type, target_id, page_number, max_dimension_px=max_dimension_px
    )


@mcp.tool(**_write("Stage PDF for Upload", destructive=False, idempotent=True))
@_guard
def prepare_application_pdf_upload(application_id: str) -> Any:
    """Stage a disposable copy of an application's canonical rendered PDF for
    direct Playwright upload. If the PDF has not been rendered, render it and
    retry once. Writes atomically under
    $MAESTRO_CS_UPLOAD_DIR/<application_id>/<canonical filename>, defaulting
    to the repository's .playwright-mcp/uploads directory (pair Playwright
    --output-dir with the parent .playwright-mcp tree). Returns upload_path, an
    absolute path usable directly by Playwright's file chooser. The staged copy
    is the only location intended for browser file uploads; the canonical server
    artifact (under applications/artifact_dir) is preserved and is not an upload
    source. Also returns filename/path integrity and PDF
    lint metadata. This preparation tool does not authorize or submit an
    application."""
    return _client.prepare_application_pdf_upload(application_id)


# ---------- resume templates (latex | typst) ----------
@mcp.tool(**_read("List Resume Templates"))
@_guard
def list_templates() -> Any:
    """List resume templates — both engines (id, display_name, status['draft'|'ready'],
    engine, is_default, last_error). parse_certified false = a 'ready' template that
    still loses word boundaries under strict extraction — see validate_template.
    engine_available=false marks a LaTeX template on a backend with no TeX: still
    pickable, renders through Typst with a render_note."""
    return _client.list_templates()


@mcp.tool(**_read("Get Resume Template"))
@_guard
def get_template(template_id: str) -> Any:
    """Get a template incl. its full source (Jinja2+LaTeX for engine='latex';
    raw .typ text for engine='typst') plus engine, engine_available (see
    list_templates), and supported_fmt_keys.
    A template of either engine opts into look knobs by referencing `fmt.*`
    (LaTeX via the Jinja namespace, Typst via sys.inputs.fmt; defaults
    reproduce Classic): font_size (11), side_margins (0.4in),
    top_bottom_margin (0.3in), line_spacing (1.0), section_spacing (6pt),
    entry_spacing (0pt), justify (false), hide_divider (false), bullet_icon
    ("bullet"|"dash"), header_align ("center"|"left"|"right"), skills_layout
    ("inline"|"bulleted"), education_order ("degree_first"|"institution_first"),
    date_format ("verbatim"; feeds |format_date). For engine='typst',
    supported_fmt_keys always includes date_format (applied server-side) even
    if the source never names it."""
    return _client.get_template(template_id)


@mcp.tool(**_write("Create Template Draft", destructive=False, idempotent=False))
@_guard
def create_template_draft(
    id: str,
    display_name: str,
    source: str | None = None,
    validate: bool = False,
    engine: str = "latex",
) -> Any:
    """Create a DRAFT template. `engine` defaults to 'latex'. Pass
    `engine='typst'` for Typst — then `source` is REQUIRED: raw `.typ` text
    (no Jinja, no escape filters; read via `json(bytes(sys.inputs.resume))` /
    `json(bytes(sys.inputs.fmt))`; engine is immutable after creation).

    Both engines consume the same resume JSON (contact, summary,
    skills[].{category,items}, experience/projects/education, certifications,
    extra_sections). Typst reads r.contact.name etc.; optional fields arrive
    as `none` — guard with `!= none`. LaTeX uses resume.* with |latex_escape
    on every value.

    Typst constraints: dates arrive PRE-FORMATTED server-side (fmt.date_format
    is not read). Package imports (`#import "@preview/..."` or any `@...`
    import) are REJECTED (no external packages). Fonts: only
    vendored XCharter plus typst's embedded defaults (e.g. Libertinus Serif);
    any other family compiles WITHOUT error and silently substitutes. A template
    that does not render r.extra_sections (both `entries` and `bullets` shapes)
    hard-fails on resumes with custom sections; get_template('typst-classic')
    shows the block.

    LaTeX: omit `source` to start from the canonical starter. Given source
    must be a complete compilable document (\\documentclass + preamble) as
    Jinja2 with blocks ((* *)), variables ((( ))), comments ((# #)). The source
    is raw LaTeX: bare `&` for tabular cells, `\\&` for a literal ampersand;
    HTML entities such as `&amp;` are not decoded. Includable:
    ((* include '_header.tex.j2' *)). Spacing and look can be wired to `fmt.*`
    (full knob list on get_template) instead of hard-coded values;
    get_template('default') is a starting point.

    validate=True test-compiles in the same call (status/last_error). A LaTeX
    draft cannot validate on a backend with no TeX (list_templates →
    engine_available); engine='typst' works there. Not usable until validation
    succeeds. `id` is a slug: [a-z0-9_-]."""
    return _client.create_template_draft(
        id, display_name, source, validate=validate, engine=engine
    )


@mcp.tool(**_write("Edit Template Draft", destructive=True, idempotent=True))
@_guard
def update_template_draft(
    template_id: str,
    source: str | None = None,
    display_name: str | None = None,
    validate: bool = False,
) -> Any:
    """Edit a draft template; changing the source resets it to 'draft'. Pass
    validate=True to save + test-compile in one call (returned status/last_error
    show the result); otherwise re-validate separately. The active default
    template cannot be edited through these tools (the backend rejects it)."""
    return _client.update_template_draft(
        template_id, source=source, display_name=display_name, validate=validate
    )


@mcp.tool(**_write("Validate Template", destructive=False, idempotent=True))
@_guard
def validate_template(template_id: str) -> Any:
    """Test-compile a template against a built-in sample resume. On success it becomes
    'ready' (usable via render_pdf template_id) and a preview is available via
    get_rendered_pdf('template', id). On failure returns {ok: false, error} with the
    engine's compile error (Typst errors carry file:line:col). Returns {ok, error, parse_certified} — parse_certified is true when
    the template's compiled PDF round-trips through a strict text extractor with word
    boundaries intact, false when it drops text, null when not assessed.
    Also returns parse_report: {missing, headers_missing, extra_sections_supported,
    extra_sections_missing} — missing lists the exact sample phrases the PDF dropped;
    extra_sections_missing non-empty means the template
    will hard-fail rendering any resume that has custom sections."""
    return _client.validate_template(template_id)


# ---------- profile coach ----------
@mcp.tool(**_read("Top In-Demand Skills"))
@_guard
def explore_top_skills(
    role_category: str | None = None,
    level: str | None = None,
    employment_type: str | None = None,
    limit: int | None = None,
) -> Any:
    """Most in-demand skills across stored JDs, optionally filtered by role/level/type."""
    return _client.explore_top_skills(
        role_category=role_category, level=level, employment_type=employment_type, limit=limit
    )


@mcp.tool(**_read("Skill Demand Heatmap"))
@_guard
def explore_skill_heatmap(limit: int | None = None) -> Any:
    """Skill demand by role category (pct of jobs per skill x role)."""
    return _client.explore_skill_heatmap(limit=limit)


@mcp.tool(**_read("Role Mix Over Time"))
@_guard
def explore_role_mix_over_time() -> Any:
    """Counts of jobs by role category per week."""
    return _client.explore_role_mix_over_time()


@mcp.tool(**_read("Resume Fit Distribution"))
@_guard
def explore_fit_distribution() -> Any:
    """How each base resume's ATS composites (deterministic engine) are
    distributed across jobs. Each row's `display_name` is the resume's own name
    (null for a slug with no row); the slug is an internal identifier."""
    return _client.explore_fit_distribution()


@mcp.tool(**_read("Recurring Skill Gaps"))
@_guard
def explore_gap_frequency(
    role_category: str | None = None,
    level: str | None = None,
    employment_type: str | None = None,
    limit: int | None = None,
) -> Any:
    """Skills that recur as gaps across saved JDs (best-scoring base resume vs JD,
    before tailoring), ranked by how many jobs want them and their ATS point
    headroom. This is RECURRING DEMAND, not a "you lack this" or learn-next list:
    a skill can recur because the evidence lives on a different base resume, is
    stale, or is merely mis-placed on this one. The learn-vs-move
    distinction is the per-skill `tier` on build_areas (`build` = no resume
    evidence AND nothing in the Career KB, the only genuinely learn-it rows;
    `surface` = the material exists, port or strengthen it) — get_job_search_brief
    carries build_areas, or GET /api/explore/build-areas. Hygiene mirror_wording
    gaps are excluded here: the resume already matches those at full keyword
    credit, so the literal JD token moves no score and is not demand.
    Each row also carries category_label, the plain-words form of category
    (e.g. "Add an example in a job or project"); the raw keys (dual_place,
    missing_skills) and the build_areas tier values are internal identifiers,
    and category_label / the tier word is their user-facing wording.
    Optionally filtered by role/level/type; limit caps the number of skills
    returned."""
    return _client.explore_gap_frequency(
        role_category=role_category,
        level=level,
        employment_type=employment_type,
        limit=limit,
    )


@mcp.tool(**_read("ATS Score Trend"))
@_guard
def explore_ats_over_time(
    role_category: str | None = None,
    level: str | None = None,
    employment_type: str | None = None,
) -> Any:
    """Average ATS composite over time (weekly), split by phase (base vs tailored)
    and role category. Optionally filtered by role/level/type."""
    return _client.explore_ats_over_time(
        role_category=role_category, level=level, employment_type=employment_type
    )


@mcp.tool(**_read("Tailoring Score Lift"))
@_guard
def explore_tailoring_lift(
    role_category: str | None = None,
    level: str | None = None,
    employment_type: str | None = None,
) -> Any:
    """How much tailoring lifts the ATS score (base->tailored), averaged per role
    category, plus an overall row. Optionally filtered by role/level/type."""
    return _client.explore_tailoring_lift(
        role_category=role_category, level=level, employment_type=employment_type
    )


@mcp.tool(**_read("List Applications"))
@_guard
def list_applications(
    status: str | None = None,
    role_category: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> Any:
    """List your applications as a thin paginated summary array. Filter by
    status/role_category; page with limit/offset. Rows name their base resume
    (`base_resume_name`). Use get_application(id) for the full record and
    compare_ats for scores."""
    return _client.list_applications(
        status=status, role_category=role_category, limit=limit, offset=offset
    )


@mcp.tool(**_write("Score Resume Against Job", destructive=False, idempotent=False))
@_guard
def score_ats(
    job_id: str,
    target_type: Literal["base_resume", "application"] | None = None,
    target_id: str | None = None,
    brief: bool = False,
    include_other_countries: bool = False,
) -> Any:
    """Deterministic hybrid ATS score (no LLM): deterministic lexical layers +
    anchored pinned-model semantic matching + section-level semantic_fit. Omit
    target to score ALL base resumes (fast).

    target_type "base_resume" (target_id = slug) or "application" (target_id = id).
    Same inputs always give the same score; use it to compare bases and to
    verify an edit actually moved the number.

    Response is {scores, recommendation, countries, next}. `scores` is the raw per-target
    list: composite (0-100), per-layer subscores (incl. semantic_fit), gate
    warnings, and a per-skill diagnostic table with fix_hints. `recommendation`
    is a deterministic ranking of the base-resume rows (order, recommended slug,
    margin, close_call, reasons, coverage_warning) — always present, cheap, and
    useful during triage even with hints off. Bases set for other countries are
    not scored for this job unless `include_other_countries` is true; the
    `countries` block ({job_country, fallback, skipped}) names them and is
    omitted when a target_id is given. `next` is an optional next-step
    hint (null when suppressed or unavailable) naming quick_tailor / create_tailoring_session
    against the recommended base.

    brief=True suits scoring many jobs in a triage/mass-capture loop: it
    suppresses ONLY `next` (never `recommendation`) and is checked before any
    settings lookup, so a twenty-posting triage loop pays no extra HTTP
    round-trip for a hint nobody will read."""
    scores = _client.score_ats(
        job_id,
        target_type=target_type,
        target_id=target_id,
        include_other_countries=include_other_countries,
    )
    recommendation = workflow.rank_bases(scores)
    # With a target_id the caller named the resume, so the country rule did not
    # choose anything and there is nothing to report. The lookup is read-only
    # and follows scores that already landed, so a failure is `null`, not an error.
    countries: dict[str, Any] = (
        {}
        if target_id
        else {
            "countries": _best_effort_hint(
                lambda: _client.ats_candidates(
                    job_id, include_other_countries=include_other_countries
                )
            )
        }
    )
    if brief:
        return {"scores": scores, "recommendation": recommendation, **countries, "next": None}
    # Fetch the quick-tailor profile ONLY when it can actually be shown. It fills
    # exactly one thing — the quick_tailor option's `detail` — so fetching it with
    # hints off, or under a profile that never registers quick_tailor (hunt), is a
    # round-trip whose result is discarded. As keyword ARGUMENTS both reads would
    # be evaluated unconditionally, which is the trap this avoids: a twenty-posting
    # hunt loop would have paid 20 wasted calls even with hints switched off.
    def compose() -> dict[str, Any] | None:
        allowed = _active_allowed_tools()
        hints_enabled = _hints_enabled()
        show_quick = hints_enabled and (allowed is None or "quick_tailor" in allowed)
        return workflow.next_after_scores(
            recommendation,
            job_id=job_id,
            quick_profile=_client.get_quick_tailor_profile() if show_quick else {},
            allowed_tools=allowed,
            hints_enabled=hints_enabled,
        )

    return {
        "scores": scores,
        "recommendation": recommendation,
        **countries,
        "next": _best_effort_hint(compose),
    }


@mcp.tool(**_read("Compare ATS Scores"))
@_guard
def compare_ats(application_id: str) -> Any:
    """Before/after ATS comparison for an application: composite and per-layer deltas
    plus a per-skill diff (absent→matched, skills-list-only→dual, decayed→recent).
    Computes any missing phase row on demand."""
    return _client.compare_ats(application_id)


@mcp.tool(**_write("Start Tailoring Session", destructive=True, idempotent=False, open_world=True))
@_guard
def create_tailoring_session(job_id: str, base_resume: str, enrich: bool = False) -> Any:
    """Start the gap-analysis tailoring workflow for a job + base resume.

    Calling again for the same job+base SUPERSEDES the open session (saved
    resolutions become unreachable); list_tailoring_sessions shows existing
    sessions.

    Scores the base (deterministic ATS engine, persisted as the 'before' score) and
    returns a session whose gaps_json.categories list every gap in fix-cost order:
    missing skills, wording mismatches, placement upgrades, stale evidence, adjacent
    skills, title/structure. The intended flow is: gather the user's answer for each
    gap, save them with resolve_gaps, then tailor_session. Each gap carries its
    allowed actions. A missing skill MAY use add_keyword ONLY to add the keyword to
    a skills category (placement_target.section="skills"): that inserts an
    unverified skills-list item, never a fabricated bullet. The evidence-backed
    alternatives are a user_input resolution (the user's answer to
    enrichment.elicitation_question), attach_project, or skip.

    enrich=False (default) skips the backend's fast-model enrichment pass — no
    in-house LLM call — so gaps carry only their deterministic fields (no
    enrichment.elicitation_question / suggested_wording / suggested_placement).
    KB coverage detection does NOT depend on it: the deterministic self-nomination
    and evidence-verification pass that used to sit downstream of the LLM call now
    runs unconditionally, so KB autos still get stamped with enrich=False, and
    even during a provider outage. enrich=True pays for one fast-model call
    adding those display-only explanations and elicitation questions per gap —
    it never changes scores or which gaps exist.

    Response is the session plus a `next` next-step hint (null when hints are off
    or unavailable). `base_anchors` are the base's emphasis hints (countries,
    role, company, focus), not evidence; the anchor company is not this
    application's employer."""
    session = _client.create_tailoring_session(job_id, base_resume, enrich=enrich)
    return {**session, "next": _session_hint(session)}


@mcp.tool(**_write("Quick Tailor", destructive=True, idempotent=False))
@_guard
def quick_tailor(job_id: str, base_resume: str) -> Any:
    """Start Quick Tailor over MCP: the fast path that fills gaps from the
    user's saved quick-tailor profile instead of walking them one by one.

    Calling again for the same job+base SUPERSEDES the open session (saved
    resolutions become unreachable); list_tailoring_sessions shows existing
    sessions.

    Composes create_tailoring_session(enrich=False) with POST .../apply-profile
    (deterministic, same honesty-gated save path as resolve_gaps) and returns
    the filled session.

    This tool makes NO in-house LLM call of its own. Sessions rely on the
    CALLING agent's own model, not the backend's. The saved profile only plans
    mechanical, evidence-respecting moves — it does NOT write resume prose.
    The returned resolutions_json may already resolve every gap, including
    system-planned entries (payload.provenance). Resume text comes from
    caller-authored typed edit ops passed to
    tailor_session(tailoring_session_id=..., ops=[...]), which skips the backend
    LLM pass.

    Honesty: the server does not gate caller-authored ops against fabricated
    skills, experience, metrics, or dates. An unverified or absent skill can only
    enter a skills category (add_skill_item), never as an experience or project
    bullet asserting the candidate did the work.

    A session whose resolutions_json contains no planned action beyond
    "skip" means the profile was not ALLOWED to add anything to THIS
    session — it is not an error; the gaps can then be resolved with
    resolve_gaps.

    Raises (409, message says which): a failing fatal health gate on the
    base blocks session creation; a stale or no-longer-open session blocks
    the profile fill. Response is the filled session plus a `next` hint
    suggesting tailor_session (profile standing instruction as user_prompt
    when the session has no note of its own)."""
    session = _client.create_tailoring_session(job_id, base_resume, enrich=False)
    filled = _client.apply_quick_tailor_profile(session["id"])

    def compose() -> dict[str, Any] | None:
        if not _hints_enabled():
            return None
        profile = _client.get_quick_tailor_profile()
        return workflow.next_after_session(
            filled,
            allowed_tools=_active_allowed_tools(),
            hints_enabled=True,
            instruction=_instruction_from_profile(profile),
        )

    return {**filled, "next": _best_effort_hint(compose)}


@mcp.tool(**_read("List Tailoring Sessions"))
@_guard
def list_tailoring_sessions(job_id: str) -> Any:
    """List all tailoring sessions for a job, newest first.

    A lost session id can be rediscovered here (create_tailoring_session would
    supersede the open one). Each item is a summary (id, job_id, base_resume,
    status, application_id, timestamps, gap_count, resolution_count); the gap
    list and saved resolutions are on get_tailoring_session. Status is one of:
    open (in-progress gap walkthrough, resumable via get_tailoring_session),
    tailored (finished — tailor_session already ran), superseded (a newer
    session for the same job+base replaced it), or abandoned (explicitly closed
    via close_tailoring_session without tailoring)."""
    return _client.list_tailoring_sessions(job_id)


@mcp.tool(**_read("Get Tailoring Session"))
@_guard
def get_tailoring_session(tailoring_session_id: str) -> Any:
    """Fetch a tailoring session to resume a half-done gap walkthrough.

    `tailoring_session_id` is the id returned by create_tailoring_session. Returns
    the session with its frozen gap list (gaps_json), any resolutions saved so far
    (resolutions_json), and status (open/tailored). resolutions_json may already
    contain SYSTEM-PLANNED auto-resolutions stamped at creation (their payload
    carries `provenance`, e.g. library_auto/kb_auto/kb_profile/wording_auto —
    hand-made resolutions never do): verified evidence the resolver pre-applied.
    To retract one, resend its gap_id with action "skip" via resolve_gaps.
    Unresolved gaps are those in gaps_json with no entry in resolutions_json;
    tailor_session consumes the saved resolutions. `base_anchors` are the base's
    emphasis hints (countries, role, company, focus), not evidence; the anchor
    company is not this application's employer."""
    return _client.get_tailoring_session(tailoring_session_id)


@mcp.tool(**_write("Close Tailoring Session", destructive=False, idempotent=False))
@_guard
def close_tailoring_session(tailoring_session_id: str) -> Any:
    """Abandon an OPEN tailoring session without tailoring it.

    `tailoring_session_id` is the id returned by create_tailoring_session. This is
    the explicit exit for a "changed my mind" flow — e.g. the user walks through
    some gaps, then decides to use the base resume as-is and does not run
    tailor_session. Marks the session's status "abandoned" so it stops looking like
    unfinished work. Errors (409) if the session isn't currently open (already
    tailored, already superseded, or already abandoned)."""
    return _client.close_tailoring_session(tailoring_session_id)


@mcp.tool(**_write("Save Gap Resolutions", destructive=True, idempotent=True))
@_guard
def resolve_gaps(
    tailoring_session_id: str, resolutions: GapResolutions
) -> Any:
    """Save gap resolutions on a tailoring session (merge by gap_id, idempotent).
    The batch is validated as ONE unit — one invalid item saves NOTHING
    (existing saved resolutions untouched).

    `tailoring_session_id` is the id from create_tailoring_session. Each item
    is {gap_id, action, payload}. Actions: add_keyword, user_input,
    attach_project, skip, enable_entry, port_kb_point, cannot_confirm.
    Payload shapes live on the `resolutions` parameter schema.

    enable_entry and port_kb_point carry verified evidence and are exempt
    from the add_keyword missing-skill rule (unverified additions stay in
    skills). Re-sending a gap_id overwrites that gap; other saved resolutions
    stay — including system-planned autos (payload.provenance; see
    get_tailoring_session). May be called repeatedly; tailor_session consumes
    the saved resolutions. Merge-only: omitting a gap_id never removes its saved resolution — resend
    that gap_id with action "skip" to retract.

    Response is the session plus a `next` hint (null when hints are off or unavailable)."""
    session = _client.resolve_gaps(tailoring_session_id, resolutions)
    return {**session, "next": _session_hint(session)}


@mcp.tool(**_write("Tailor Resume Session", destructive=True, idempotent=False, open_world=True))
@_guard
def tailor_session(
    tailoring_session_id: str,
    user_prompt: str | None = None,
    ops: list[dict] | None = None,
) -> Any:
    """Run the tailor pipeline for a session: resolutions -> edit ops ->
    tailored application, auto-scored.

    `tailoring_session_id` is the id returned by create_tailoring_session.
    Two ways to produce the edit ops:
    - Default (ops omitted): the backend builds the tailor prompt from the saved
      resolutions and calls the LLM to generate the ops.
    - Caller-supplied (ops given): the caller has already produced the typed edit
      ops (same op shapes as tailor_application/edit_application). The backend
      skips its own LLM pass and applies them directly — the caller's judgment
      IS the tailor. `ops` carry only the changed fields (the base is in
      get_base_resume).

    Caller-supplied ops are applied as authored: the server validates structure
    only, so nothing gates fabricated skills, experience, metrics, or dates
    (keyword-survival checks run only on the backend-LLM path). A skill the
    candidate cannot evidence can only be added to the skills list (an
    add_skill_item op into a skills category), not as an experience or project
    bullet; the compare view audits any edit beyond the saved resolutions.

    Optional user_prompt adds free-form tailoring guidance. Creates the application
    from the base resume plus the ops, scores the result, and returns
    {session, compare, compare_error, next}. compare holds the before/after ATS
    deltas; it may be null with compare_error set if the scores weren't comparable
    — the tailor still succeeded in that case and the application exists, so no
    retry is needed. `kb_writeback_skips` derives from each user_input
    resolution's STORED placement_target from resolve_gaps, not from the ops, so
    ops that disagree with the stored target produce a spurious wrong_section
    skip. `next` is a next-step hint naming render_pdf for the new application
    (null when suppressed or unavailable)."""
    result = _client.tailor_session(tailoring_session_id, user_prompt=user_prompt, ops=ops)
    application_id = (result.get("session") or {}).get("application_id")
    next_hint = (
        _best_effort_hint(
            lambda: workflow.next_after_tailor(
                application_id=application_id,
                allowed_tools=_active_allowed_tools(),
                hints_enabled=_hints_enabled(),
            )
        )
        if application_id
        else None
    )
    return {**result, "next": next_hint}


@mcp.tool(**_read("Export Jobs"))
@_guard
def export_jobs(
    role_category: str | None = None,
    level: str | None = None,
    since: str | None = None,
    skill: str | None = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> Any:
    """Export jobs, newest first, with extracted fields and nested skills, for
    open-ended analysis. Paged by limit (default 10, max 50) and offset; a page
    shorter than limit is the last. Rows run a few thousand characters (the
    skills list is most of it) and omit raw_text and extracted_json, which
    get_job returns for one posting. since is an ISO date (YYYY-MM-DD); skill is
    a case-insensitive substring."""
    return _client.export_jobs(
        role_category=role_category, level=level, since=since, skill=skill,
        limit=limit, offset=offset,
    )


# ---------- proposal ledger tools ----------
@mcp.tool(**_write("Propose Application", destructive=False, idempotent=True))
@_guard
def propose_application(
    job_id: str,
    fit: dict | None = None,
    plan: dict | None = None,
    application_id: str | None = None,
    referral_id: str | None = None,
    ctx: Context | None = None,
) -> Any:
    """File an agent-hunted application proposal for user review.

    If an open proposal already exists for the job, returns that proposal (idempotent)
    instead of 409. Pass application_id after tailoring to late-link when the open
    proposal is still unlinked (409 if already linked to a different application).
    Refused (409) when the company is blocklisted or when THIS posting was
    previously declined (declines are posting-scoped and permanent; other roles
    at the same company are unaffected).
    plan may include "company_note" (1-2 sentences: what the company is/does,
    direct employer vs staffing, any legitimacy doubt) — the proposals page
    shows it as "About the company" for triage.
    """
    return _client.propose_application(
        job_id=job_id,
        fit=fit,
        plan=plan,
        application_id=application_id,
        referral_id=referral_id,
        origin_detail=_client_label(ctx),
    )


@mcp.tool(**_read("List Application Proposals"))
@_guard
def list_proposals(
    status: str | None = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 20,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> Any:
    """List application proposals, newest first, as {items, total}. `status` is
    one status or a comma-separated set; limit (default 20, max 50) and offset
    page through `total`. A row is a couple of thousand characters (fit and job).

    status 'accepted' means the user queued the proposal for an apply run (via
    the /proposals page or record_triage); 'pending_review' proposals are awaiting
    the user's triage. Batch apply runs work 'accepted' proposals by convention
    (the agent-apply playbook); the server also permits preparation, evidence and
    consent from 'pending_review'. Each item's proposed_by names who filed it: an
    MCP client's name, "you" for the web app's queue, or null. Reading expires
    overdue pending_review and needs_decision proposals (terminal 'expired')."""
    return _client.list_proposals(status=status, limit=limit, offset=offset)


@mcp.tool(**_read("Get Proposal"))
@_guard
def get_proposal(proposal_id: str) -> Any:
    """Get proposal detail including job facts, application summary, QA entries, and evidence manifest.
    Reading expires an overdue pending_review or needs_decision proposal (terminal 'expired')."""
    return _client.get_proposal(proposal_id)


@mcp.tool(**_write("Record Proposal Decision", destructive=False, idempotent=False))
@_guard
def record_decision(proposal_id: str, fit: dict, application_id: str | None = None) -> Any:
    """Record user decision when proposal is in needs_decision state. Resolves back to
    pending_review. application_id may be omitted; the backend then links the newest
    application matching the proposal job and fit.chosen_base (409 if none)."""
    return _client.record_decision(
        proposal_id, fit=fit, application_id=application_id
    )


@mcp.tool(**_write("Request Proposal Decision", destructive=False, idempotent=True))
@_guard
def request_decision(proposal_id: str, reason: str) -> Any:
    """Escalate an unlinked/ambiguous proposal to needs_decision. Idempotent if already
    needs_decision."""
    return _client.request_decision(proposal_id, reason=reason)


@mcp.tool(**_write("Resume Proposal", destructive=False, idempotent=False))
@_guard
def resume_proposal(proposal_id: str) -> Any:
    """Return a needs_human proposal to pending_review so preparation can continue.
    Releases any pre-click daily-cap reservation. Refused for submission_uncertain."""
    return _client.resume_proposal(proposal_id)


@mcp.tool(**_read("Get Final Review"))
@_guard
def get_final_review(proposal_id: str) -> Any:
    """Compact final-review bundle: job summary, chosen base/ATS delta, PDF readiness,
    QA answers, EEO consent flag (no values), blocked/manual items, evidence manifest.
    Requires an existing proposal — a 404 usually means propose_application was
    not called (it accepts application_id to late-link) or an application id
    was passed where a proposal id belongs. duplicate_submitted=true means a
    same-company+title proposal was already submitted (relevant to the user's
    approval decision). `flags` lists the job's recorded form answers worth a second look
    (record_filled_answers): question, source, answer (an EEO one carries eeo_answered
    instead) and each flag's reason. `base_country.eligible` is false when the resume being
    sent is set for other countries than the job's."""
    return _client.get_final_review(proposal_id)


@mcp.tool(**_write("Record Filled Answers", destructive=False, idempotent=False))
@_guard
def record_filled_answers(
    job_id: str,
    fields: FilledFields,
    step: str | int | None = None,
    application_id: str | None = None,
    base_resume: str | None = None,
) -> Any:
    """Record what was filled into this job's application form, one call per form page: each
    field's question, answer and source. Per question the latest call wins; the job page's
    What was submitted tab shows the record. An EEO answer is kept only while the user's
    standing EEO consent is recorded, and no MCP read returns its value. Returns {id,
    application_id, flag_count, flags}: each flagged field by its index in `fields`, with
    guessed_screening (a screening question answered by inference or composed prose),
    ticked_everything (a multi-select with every one of 3+ options ticked),
    differs_from_profile or eeo_without_saved_answer, each with a one-line reason. Flags
    warn; nothing is blocked, and get_final_review lists the job's flags again. `step` names
    the page: pass its URL path (location.pathname), the Companion's own key, so an agent row
    and a Companion row for one page fold together; a page number is still accepted.
    `application_id` links the record now; without it the record links, for the application of `base_resume` (the base resume's slug), when
    that application is created, marked applied or submitted."""
    return _client.record_filled_answers(
        job_id, fields, step=step, application_id=application_id, base_resume=base_resume
    )


@mcp.tool(**_write("Record Automation Run", destructive=False, idempotent=False))
@_guard
def record_run(
    automation: str,
    outcome: Literal["ok", "partial", "failed"],
    report: RunReportArg = None,
    ctx: Context | None = None,
) -> Any:
    """Stores one finished automation run. The Agent inbox lists the newest run of each
    automation under Recent runs (its counts, digest and job links), and each Automations card
    shows when its automation last ran. automation is the card id (mail-status, job-hunt,
    referral-pages, tailor-run, apply-session) or a custom automation's own name, 40 characters
    at most. outcome: ok, partial (some of the work failed) or failed (none of it was done).
    The newest 200 runs are kept. Returns the stored run."""
    return _client.record_run(automation, outcome, report, origin_detail=_client_label(ctx))


@mcp.tool(**_write("Record Application Consent", destructive=True, idempotent=False))
@_guard
def record_consent(
    proposal_id: str,
    action: Literal["approved", "rejected"],
    channel: Literal["chat", "slack", "mcp"],
    note: str | None = None,
) -> Any:
    """Record the user's explicit approve/reject decision for this proposal as an
    append-only audit row (`channel` = where the user said it, `note` = their
    words). The stored decision is attributed to the user; the server cannot
    verify it came from them. `approved` is accepted only when the proposal has
    final_review evidence, the linked application is not already applied, and a
    daily-cap slot is free, and it reserves that slot. `rejected` is a
    posting-scoped decline and is terminal."""
    consent = {"channel": channel, "note": note}
    return _client.transition_proposal(proposal_id, action, consent=consent)


@mcp.tool(**_write("Attach Evidence Image", destructive=False, idempotent=False))
@_guard
def attach_evidence(
    proposal_id: str,
    step: int,
    label: str,
    image_base64: str,
    kind: Literal["step", "final_review", "submission_receipt"] = "step",
) -> Any:
    """Attach step evidence image (base64) to a proposal. The image is supplied
    inline in the call; when the screenshot already exists as a file on this
    machine, attach_evidence_file uploads it by path without passing image bytes
    through the model context.
    kind must be step | final_review | submission_receipt."""
    return _client.attach_evidence(proposal_id, step, label, image_base64, kind=kind)


@mcp.tool(**_write("Attach Evidence File", destructive=False, idempotent=False))
@_guard
def attach_evidence_file(
    proposal_id: str,
    step: int,
    label: str,
    file_path: str,
    kind: Literal["step", "final_review", "submission_receipt"] = "step",
) -> Any:
    """Attach evidence from an image file already on this machine's disk
    (e.g. a browser tool's saved screenshot — Playwright MCP saves to its
    --output-dir and reports the path). `file_path` is an absolute path to an
    existing image, typically as reported by the browser tool — with the
    standard setup that is under the repo's .playwright-mcp/ tree (e.g.
    /Users/<user>/Projects/maestro-career-studio/.playwright-mcp/<name>.png);
    a relative or ~ path is resolved against this server's working directory.
    When this server runs inside the backend
    container, a host path with a `.playwright-mcp/` segment is read from the
    container's mount of that tree (paths that leave the tree are refused). The
    bytes are read and uploaded server-side so they never enter the model context.
    PNG/JPEG only, 5 MB max. kind must be step | final_review | submission_receipt."""
    return _client.attach_evidence_file(proposal_id, step, label, file_path, kind=kind)


@mcp.tool(**_write("Mark Application Submitted", destructive=True, idempotent=False))
@_guard
def mark_submitted(
    proposal_id: str,
    user_attested: bool = False,
    channel: Literal["chat", "slack", "mcp"] = "chat",
    note: str | None = None,
) -> Any:
    """Flip an approved proposal to submitted (terminal; links the application to
    applied). Requires submission_receipt evidence, or `user_attested=True`,
    which records the user's own statement that they submitted it (or that a
    submission_uncertain proposal went through, e.g. a confirmation email or
    portal check) as an attested consent event with their words in `note`.
    `user_attested` substitutes for receipt evidence and the server does not
    verify it; it is the user's attestation, not the caller's."""
    if user_attested:
        return _client.transition_proposal(
            proposal_id, "submitted", attested=True,
            consent={"channel": channel, "note": note},
        )
    return _client.transition_proposal(proposal_id, "submitted")


@mcp.tool(**_write("Record Triage Decision", destructive=True, idempotent=False))
@_guard
def record_triage(
    proposal_ids: list[str],
    action: Literal["accept", "decline"],
    channel: Literal["chat", "slack", "mcp"] = "mcp",
    note: str | None = None,
    reason: str | None = None,
) -> Any:
    """Record the user's TRIAGE decision over one or many proposals — accept
    queues them for the next apply run; decline drops those unique postings
    (posting-scoped, never the company). The decision is the user's own, stated
    directly or as a selection rule they gave. One append-only consent row is
    written per proposal and the result is a per-id ok/error report (a mixed
    batch partially succeeds). Accept is NOT submit consent: the
    per-application approval is recorded separately by record_consent."""
    status = "accepted" if action == "accept" else "rejected"
    return _client.bulk_transition_proposals(
        proposal_ids, status=status, channel=channel, note=note, reason=reason,
    )


@mcp.tool(**_write("Report Application Failure", destructive=True, idempotent=False))
@_guard
def report_failure(proposal_id: str, reason: str) -> Any:
    """Report execution failure. From pending_review/approved, transitions to needs_human
    (resumable). reason='submission_uncertain' (for a submit click that could not be
    verified) moves the proposal to the terminal submission_uncertain status:
    resume_proposal is refused for it, and only the user's attestation through
    mark_submitted moves it on."""
    return _client.report_failure(proposal_id, reason=reason)


# Filter tools for MAESTRO_CS_MCP_PROFILE (default full = no-op).
_ACTIVE_PROFILE = apply_profile_filter(mcp)


def list_registered_tool_names() -> list[str]:
    import asyncio

    tools = asyncio.run(mcp.list_tools())
    return [t.name for t in tools]


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
