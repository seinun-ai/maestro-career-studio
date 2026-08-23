from __future__ import annotations

import functools
import inspect
import os
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

from app.schemas.resume_edit import op_kinds_ordered, render_ops_shapes
from mcp_server import workflow
from mcp_server.client import BackendClient, BackendError
from mcp_server.profiles import allowed_tools, apply_profile_filter

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
        "object; it is scoped to that one entry. Never reach for a whole-resume "
        "replace to change one field. See the tool description for each op's shape. "
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
        "resolutions untouched); fix and resend. Merge-by-gap_id; omit never "
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

_INGEST_DATA_FIELD = Field(
    description=(
        "ResumeData. Only contact.name and contact.email are required. 422 if "
        "any source fails validation or on a duplicate SOURCE key (re-running "
        "the same resume_key is a merge, not an error); atomic either way — "
        "nothing persisted; fix the payload and resend."
    )
)


def _guard(fn):
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except BackendError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


def _client_label(ctx: Context | None) -> str | None:
    """Name the MCP client for the KB timeline: 'Claude Desktop', 'ChatGPT'.

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
    return workflow.next_after_session(
        session,
        allowed_tools=_active_allowed_tools(),
        hints_enabled=_hints_enabled(),
        instruction=instruction,
    )


def _instruction_from_profile(profile: dict[str, Any]) -> str | None:
    """Mirrors app.services.quick_tailor._instruction_fallback exactly: the
    saved quick-tailor profile's standing instruction, stripped, or None when
    blank. Kept as a literal copy rather than a shared import — the two live
    in different processes' import graphs (this module never imports
    app.services.quick_tailor), and the rule is one line long."""
    return (profile.get("instruction") or "").strip() or None


# ---------- read ----------
@mcp.tool()
@_guard
def list_base_resumes() -> Any:
    """List all base resumes (slug, display name, summary)."""
    return _client.list_base_resumes()


@mcp.tool()
@_guard
def get_base_resume(slug: str) -> Any:
    """Get a base resume's full data JSON, render status, and metadata."""
    return _client.get_base_resume(slug)


@mcp.tool()
@_guard
def list_jobs(
    limit: int | None = None,
    offset: int | None = None,
    without_application: bool | None = None,
) -> Any:
    """List stored jobs as a thin summary array, paginated (limit + offset).
    Each item is a slim projection (company, title, role_category, level,
    employment_type, work_mode, location, salary, work_authorization,
    opt_accepted) — no raw_text or extracted_json; use get_job for full detail.
    Optionally only jobs without an application."""
    return _client.list_jobs(
        limit=limit, offset=offset, without_application=without_application
    )


@mcp.tool()
@_guard
def get_job(job_id: str) -> Any:
    """Get a job with its most recent application."""
    return _client.get_job(job_id)


@mcp.tool()
@_guard
def get_application(application_id: str) -> Any:
    """Get one application's full detail: the tailored resume (customized_json)
    and the joined job. Use compare_ats for before/after scores."""
    return _client.get_application(application_id)


@mcp.tool()
@_guard
def list_referrals() -> Any:
    """List referral contacts (company, careers URL, contact name, notes, applications_count)."""
    return _client.list_referrals()


@mcp.tool()
@_guard
def list_qa_entries(application_id: str) -> Any:
    """List the generated screening answers and cover letters for an application, newest first."""
    return _client.list_qa_entries(application_id)


# ---------- health check ----------
@mcp.tool()
@_guard
def run_health_check(kind: str, key: str) -> Any:
    """Run the JD-independent resume health check on a base resume or a tailored
    application. `kind` is 'base' (then `key` is the base-resume slug) or
    'application' (then `key` is the application id). Classifies every bullet on
    the evidence ladder, checks structure/content gates, and returns
    {score, grade, tier, gates, counts, findings} ranked by what each defect costs.
    Run this BEFORE create_tailoring_session — tailoring blocks on a failing fatal gate."""
    return _client.run_health_check(kind, key)


@mcp.tool()
@_guard
def get_health_report(kind: str, key: str) -> Any:
    """Fetch the most recent stored health report for a base resume or application
    without re-running it. `kind` is 'base' or 'application', `key` is the slug or
    application id. Returns {score, grade, tier, gates, counts, findings}, or an
    error if no report exists yet (run run_health_check first)."""
    return _client.get_health_report(kind, key)


@mcp.tool()
@_guard
def waive_health_gate(
    kind: Literal["base", "application"], key: str, gate_id: str, reason: str
) -> Any:
    """Escape hatch for the fatal-health-gate 409 from create_tailoring_session.
    Waiving bypasses a safety gate and is an explicit human decision: call this
    tool only when the user has said to waive. `kind` is 'base' or 'application',
    `key` is the resume slug or application id, and `reason` records why the named
    gate may be bypassed."""
    return _client.waive_health_gate(kind, key, gate_id, reason)


@mcp.tool()
@_guard
def unwaive_health_gate(
    kind: Literal["base", "application"], key: str, gate_id: str
) -> Any:
    """Remove a health-gate waiver and restore the gate's protection. The matching
    waive_health_gate tool is the escape hatch for the 409 from
    create_tailoring_session; waiving is an explicit human decision, so call that
    tool only when the user has said to waive."""
    return _client.unwaive_health_gate(kind, key, gate_id)


# ---------- JD ingest ----------
@mcp.tool()
@_guard
def store_extracted_jd(
    extracted_json: dict,
    raw_text: str | None = None,
    source_url: str | None = None,
    source: Literal["user", "agent"] = "user",
) -> Any:
    """Store a job description you (Claude) already extracted into JSON.

    extracted_json must match the app's JobExtraction schema: company, title,
    role_category, level, employment_type, work_mode, city/state/country,
    location_raw, salary_min/max, salary_period,
    work_authorization: "sponsorship_available"|"no_sponsorship"|"citizen_or_gc_required"|"unstated",
    opt_accepted: "yes"|"stem_opt_ok"|"no"|"unstated",
    years_experience_min/max, skills[{skill_name, skill_category,
    requirement_level: "required"|"preferred"|"mentioned"}],
    responsibilities[], qualifications[]. ANY other work_authorization or
    opt_accepted value silently normalizes to "unstated" with no error.
    source is "user" or "agent" (agent-hunted jobs must use source="agent").
    Returns the stored job.
    """
    return _client.store_extracted_jd(extracted_json, raw_text=raw_text, source_url=source_url, source=source)


# ---------- agentic job search ----------
@mcp.tool()
@_guard
def get_job_search_brief() -> Any:
    """Read the server-composed job-search brief: profile constraints (location,
    relocation, work-auth VERBATIM plus warnings[] when values are contradictory
    or missing — never guessed), persona text (may be empty; weigh the
    analytics-derived targets higher when it is), active base-resume summaries,
    role mix, top required skills, build areas, referral careers pages
    (company + careers_url + has_contact), and counts of jobs captured in the
    last 30 days by role category. Call this FIRST in an agentic search session
    (playbook: docs/agentic-job-search.md). The workflow it anchors is capture
    and score only — browse, extract, store_extracted_jd — never auto-apply."""
    return _client.get_job_search_brief()


@mcp.tool()
@_guard
def get_career_context() -> Any:
    """Read the full composed career context from the Career KB: `resume` (the
    approved-points resume view assembled from profile + non-archived entities)
    and `memory` (the beyond-the-resume string: identity facts and entity notes
    that don't belong on a resume). Use this to ground social-media posts
    (LinkedIn), outreach drafts, or any writing about the user's whole career —
    optionally alongside get_base_resume for a specific resume's voice. NEVER
    invent facts, metrics, employers, or dates beyond what this data (or a
    fetched base resume) states; if the material doesn't support a claim, leave
    it out. Use the ID-bearing kb_list_entities / kb_get_entity / kb_list_points
    tools before making a user-requested correction."""
    return _client.get_career_context()


@mcp.tool()
@_guard
def get_career_export() -> str:
    """Read the exact portable career.md generated from the current Career KB.

    Returns deterministic Markdown for copy-out, download-equivalent use, or
    Markdown-oriented grounding. For structured resume and memory fields, use
    get_career_context. Read-only; this does not alter tailoring behavior.
    """
    return _client.get_career_export()


# ---------- Career KB: read with IDs ----------
@mcp.tool()
@_guard
def kb_list_entities(kind: str | None = None, status: str | None = None) -> Any:
    """List Career KB entities with their IDs (get_career_context returns prose
    with no IDs, so start here before editing anything). Optionally filter by
    kind (experience|project|education|certification|extra) or status
    (ongoing|completed|archived). Each item carries point_count and draft_count."""
    return _client.list_kb_entities(kind=kind, status=status)


@mcp.tool()
@_guard
def kb_get_entity(entity_id: str) -> Any:
    """Full detail for one Career KB entity: dates, notes, its points (each with
    id, text and state), attached documents, and the activity timeline."""
    return _client.get_kb_entity(entity_id)


@mcp.tool()
@_guard
def kb_list_points(
    state: str | None = None, limit: int = 500, offset: int = 0
) -> Any:
    """List Career KB points across all entities, optionally by state
    (draft|approved|retired). An unfiltered call is bounded to the first
    `limit` points (default 500); page with `offset`. Filter by `state`
    and page rather than pulling the whole table."""
    return _client.list_kb_points(state=state, limit=limit, offset=offset)


# ---------- Career KB: write ----------
# Every tool here mints DRAFT content, kb_ingest_resume included — an agent
# transcribing a resume is not the user approving it. The single way to
# approve from MCP is kb_approve_points, and it is consent-gated: call it only
# after the user has actually seen these points and said yes. Never state a
# date, employer, credential or metric the user did not give you — a fabricated
# fact written here becomes part of their permanent career record.
@mcp.tool()
@_guard
def kb_capture(
    text: str,
    entity_id: str | None = None,
    ctx: Context | None = None,
) -> Any:
    """Capture free-text career news into DRAFT points. A model matches it to an
    existing entity or proposes a new one; pass entity_id to force placement.
    Points land as drafts for the user to approve at /career. Use only the
    user's own words and facts."""
    return _client.kb_capture(
        text,
        entity_id=entity_id,
        origin_detail=_client_label(ctx),
    )


@mcp.tool()
@_guard
def kb_edit_point(
    point_id: str,
    text: str | None = None,
    tags: list[str] | None = None,
    ctx: Context | None = None,
) -> Any:
    """Reword a Career KB point or retag it. Changing the text sends the point
    back to DRAFT, so it leaves the composed resume and career export until the
    user re-approves it at /career — say so when you report the edit. Cannot
    approve, retire or delete a point."""
    return _client.kb_edit_point(
        point_id,
        text=text,
        tags=tags,
        origin_detail=_client_label(ctx),
    )


@mcp.tool()
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
    certification|extra. Writes immediately and is NOT draft-gated: call it only after
    the user has actually asked for this entity, with their own dates and
    wording. `detail` is a free-form dict (conventional keys: `tech` list[str]|str,
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


@mcp.tool()
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
    immediately with no draft gate: confirm the exact values with the user
    first. Kind cannot be changed here — that is a rebuild, not a correction."""
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


@mcp.tool()
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
    value wholesale, so read get_career_context first and send the merged result.
    Writes immediately with no draft gate — confirm with the user first."""
    return _client.kb_edit_profile(
        contact=contact,
        summary=summary,
        skills=skills,
        notes=notes,
        origin_detail=_client_label(ctx),
    )


@mcp.tool()
@_guard
def kb_ingest_resume(
    resume_key: str,
    data: Annotated[dict[str, Any], _INGEST_DATA_FIELD],
    brief: bool = False,
    ctx: Context | None = None,
) -> Any:
    """Persist one caller-parsed resume into the Career KB. No in-house LLM.

    Points land as DRAFTS — safe once you have shown the user what you extracted.
    Puts nothing on a resume: the consent gate is kb_approve_points, called ONLY
    after the user actually approved these points (record_consent convention).

    HONESTY: transcribe the user's resume text exactly — no embellishment, no
    rewording, no invented metrics. Same honesty model as caller-authored tailor ops.

    ENTITY NAMES: matching is two-pass. Exact identity-key first (experience:
    company+role+start_date; projects: name; education: institution+degree;
    certs: the string), then a near-identity pass for experience/projects/certs
    (token-subset; projects allow ≤2 extra tokens). Education and extra are
    identity-key-only. Different spellings can merge on that second pass —
    you need not normalize names for the near cases it covers, but everything
    outside them still forks.

    Re-running the same resume_key is a merge: no duplicate entities; a bullet
    already on the entity (any state, including retired) is not re-created.
    resume_key must match ^[a-z0-9][a-z0-9_]*$.

    `data` is ResumeData (only contact.name and contact.email required).
    Sections: contact, summary, skills[{category, items}], experience, projects,
    education, certifications[str], extra_sections. Experience:
    {company, role, location?, start_date?, end_date?, bullets[str]}.
    extra_sections are NOT stored in the Career KB (report warns); add them
    after the base is created. skills/contact/summary go to the KB profile
    (no draft state). Profile seeding is first-write-wins — ingest the CURRENT
    resume first.

    Response {report, next}. report: created/matched entity ids, DRAFT point
    ids, counts, warnings. next is a hint (null when suppressed). brief=True
    in a multi-resume loop suppresses next before any settings read. 422 if
    any source fails ResumeData validation or on a duplicate source key
    (atomic: nothing persisted); fix and resend.
    """
    report = _client.kb_ingest_resume(
        resume_key, data, origin_detail=_client_label(ctx),
    )
    if brief:
        return {"report": report, "next": None}
    return {
        "report": report,
        "next": workflow.next_after_kb_ingest(
            report,
            allowed_tools=_active_allowed_tools(),
            hints_enabled=_hints_enabled(),
        ),
    }


@mcp.tool()
@_guard
def kb_approve_points(
    point_ids: list[str],
    state: Literal["approved", "retired"] = "approved",
) -> Any:
    """Batch-set Career KB point state. This is the approval gate: it is what
    puts a point on composed resumes. Call ONLY after the user explicitly
    approved (or asked to retire) these points — record_consent convention.

    state is approved|retired only; bulk-to-draft is impossible. 1-500 ids;
    repeats collapse to one result row. Per-id results are honest: unknown ids
    return ok=false detail="not found" and the rest still proceed. Report
    failures to the user; do not retry blindly.

    Response is {results: [{id, ok, state, detail}], next}. next is a hint
    (null when suppressed).
    """
    body = _client.kb_approve_points(point_ids, state=state)
    results = body.get("results") or [] if isinstance(body, dict) else []
    return {
        "results": results,
        "next": workflow.next_after_bulk_state(
            results,
            requested_state=state,
            allowed_tools=_active_allowed_tools(),
            hints_enabled=_hints_enabled(),
        ),
    }


@mcp.tool()
@_guard
def kb_sync_base(slug: str) -> Any:
    """Sync one base resume into the Career KB.

    Deterministic: zero LLM calls. New material lands as DRAFT points
    (origin=base_sync) for the user to approve at /career. Never edits
    resumes. Safe to rerun — a second call is a no-op when already in sync.
    """
    return _client.kb_sync_base(slug)


@mcp.tool()
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
    slug `other`/`other_2`…; display_name never affects the slug — read
    `base.slug` off the response. Only APPROVED points under the selected entities compose —
    points from kb_ingest_resume are DRAFTS and contribute nothing until
    kb_approve_points (or the user, at /career) approves them.
    skills and contact arrive in full from the KB profile regardless of entity
    selection — tell the user to trim skills per-base afterwards. The
    whole-career summary is dropped unless include_summary, or pass a reviewed
    summary. A 422 "no resume content" means the selected entities have no
    approved points.

    Response is {base, next}. next is a hint (null when suppressed). If this
    call errors AFTER the base was created (the hint's settings read can fail),
    the base exists: run list_base_resumes before retrying, because a retry
    mints a second slug (<slug>_2) rather than reusing the first.
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
        "next": workflow.next_after_base_from_kb(
            base if isinstance(base, dict) else {},
            allowed_tools=_active_allowed_tools(),
            hints_enabled=_hints_enabled(),
        ),
    }


@mcp.tool()
@_guard
def get_autofill_profile(application_id: str | None = None, base: str | None = None) -> Any:
    """Read the user's application-form autofill data: `profile` (personal
    contact + address, typed work-authorization answers, preferences like
    salary/notice/relocation, education, custom Q&A presets), plus `employment`
    blocks and `skills` from the selected resume when application_id or base is
    given. Response is labeled `source: "profile"` and includes
    `canonical_identity` (`legal_first`, `legal_last`, `preferred`) mapped only
    from stored autofill personal fields — use that block for form identity
    fields and never prefer ATS-parsed values over profile. This is the same
    feed the Chrome extension's deterministic fill uses — use it to fill ATS
    forms with real stored values instead of asking the user or guessing.
    EEO/demographic answer values (`profile.eeo`) are returned ONLY when Profile
    standing consent is active (`eeo_consent.enabled`); Playwright/agent fill
    must use those exact stored answers with no inference or model-authored EEO.
    Without standing consent, `profile.eeo` is stripped. Never ask the user to
    paste or re-dictate consented stored EEO answers into chat — if values are
    missing from the profile, hand off in-browser or have them update Profile.
    Values absent here (e.g. an unstored county) must come from the user —
    never invent them. WOTC/signatures/terms stay human-only."""
    return _client.get_autofill_context(application_id=application_id, base=base)


@mcp.tool()
@_guard
def find_job_by_url(source_url: str) -> Any:
    """Answer "is this posting already captured?" BEFORE spending an extraction:
    posting-equality source_url lookup returning {found, job,
    application_exists, application_id}. Matching ignores query strings and
    fragments (?utm_*, ?gh_src=, #apply) and treats the posting's own
    sub-paths (/apply, /application) as the same posting — pass the URL you
    are on; no need to strip tracking parameters first. A search-results or
    employer-index URL still matches nothing. found=False means the posting
    is new — extract it and call store_extracted_jd (which still dedupes
    authoritatively via already_existed)."""
    return _client.find_job_by_url(source_url)


# ---------- base resume writes ----------
@mcp.tool()
@_guard
def update_base_resume(slug: str, data: dict, display_name: str | None = None) -> Any:
    """Replace a base resume's data (the full ResumeData object, required).
    Optionally also update display_name. PUT replaces the whole resume body."""
    return _client.update_base_resume(slug, data=data, display_name=display_name)


# The docstring IS the agent's API reference, so its op block is RENDERED from
# the schema-side registry (a hand-copied block once listed 8 of 16 kinds).
# Set via __doc__ before decoration: _guard's functools.wraps propagates it to
# what FastMCP registers; an f-string literal would not be a docstring at all.
_EDIT_BASE_RESUME_DOC = f"""Apply typed edit ops to a base resume (read-then-edit). For dates, title,
    company, project name, link or tech, send replace_entry. update_base_resume
    is a LAST RESORT (whole-resume PUT). ExtraSection shape is on `ops` (ATS-neutral).

    get_base_resume first. Indices 0-based into the FULL array (incl. enabled:false,
    never PDF order). Response `applied` echoes each op. Kinds:
{render_ops_shapes()}
    <sec>=experience|projects|education (toggle_entry/add_bullet: experience|projects).
    section_key is ExtraSection.key. Bad index/category/key → error. Re-renders PDF.
    If auto re-render fails, `render_error` is non-null and the old PDF is stale —
    check it every call, not just `applied[]`."""


def _doc(text: str):
    """Attach a generated docstring before _guard/mcp.tool() read it."""

    def deco(fn):
        fn.__doc__ = inspect.cleandoc(text)
        return fn

    return deco


@mcp.tool()
@_guard
@_doc(_EDIT_BASE_RESUME_DOC)
def edit_base_resume(slug: str, ops: EditOps) -> Any:
    return _client.edit_base_resume(slug, ops)


@mcp.tool()
@_guard
def create_base_resume(slug: str, display_name: str, data: dict) -> Any:
    """Create a new base resume. Slug must be lowercase alphanumeric/underscores, not 'master'."""
    return _client.create_base_resume(slug, display_name, data)


@mcp.tool()
@_guard
def duplicate_base_resume(slug: str, new_slug: str, new_display_name: str | None = None) -> Any:
    """Clone an existing base resume into a new slug."""
    return _client.duplicate_base_resume(slug, new_slug, new_display_name=new_display_name)


@mcp.tool()
@_guard
def list_resume_versions(kind: Literal["base", "application"], key: str) -> Any:
    """List append-only resume snapshots for one target, newest last.

    kind is "base" (key = base-resume slug) or "application" (key = application
    id). This is NOT render_pdf's target_type vocabulary — there is no
    "base_resume" kind here. Each row is a version summary (number, label,
    created_at); use get_resume_version for the snapshot and diff.
    """
    return _client.list_resume_versions(kind, key)


@mcp.tool()
@_guard
def get_resume_version(
    kind: Literal["base", "application"], key: str, number: int
) -> Any:
    """Fetch one resume version including its snapshot and the diff vs its parent.

    kind/key as on list_resume_versions: "base"+slug or "application"+id.
    number is the version number from that list.
    """
    return _client.get_resume_version(kind, key, number)


@mcp.tool()
@_guard
def restore_resume_version(
    kind: Literal["base", "application"], key: str, number: int
) -> Any:
    """Copy a past version's snapshot into the live resume.

    Restore goes through the standard versioned write path — it is itself a
    new version (history is append-only; nothing is deleted). kind/key as on
    list_resume_versions: "base"+slug or "application"+id. For applications,
    the old PDF is cleared; call render_pdf before attaching.
    """
    return _client.restore_resume_version(kind, key, number)


@mcp.tool()
@_guard
def archive_base_resume(slug: str) -> Any:
    """Hide a base resume from pickers without deleting it.

    Sets archived_at (reversible timestamp, not a delete). Archived bases drop
    out of list_base_resumes' default view; JSON, PDF, TEX and version history
    stay. Undo with unarchive_base_resume.
    """
    return _client.archive_base_resume(slug)


@mcp.tool()
@_guard
def unarchive_base_resume(slug: str) -> Any:
    """Restore an archived base resume to list_base_resumes' default view.

    Clears archived_at. The resume is again selectable; nothing else changes.
    """
    return _client.unarchive_base_resume(slug)


# ---------- tailor + render ----------
@mcp.tool()
@_guard
def tailor_application(
    job_id: str, base_resume: str, ops: EditOps, application_id: str | None = None
) -> Any:
    """REBUILD FROM SCRATCH: apply typed edit ops to the BASE resume and store the
    result as customized_json, REPLACING whatever was there before wholesale.

    Read the base with get_base_resume, then send only the changed fields as `ops`
    (same op shapes as edit_base_resume) — the server starts from the stored base
    and inherits every untouched field from IT, not from any prior tailored draft.
    If an application already has tailored edits (from a previous tailor_application
    or edit_application call), calling this again DESTROYS them — the new result is
    computed fresh from the base, not layered on top. Only use this for a genuine
    do-over. For incremental fixes on top of what's already tailored (the common
    case — refining wording, swapping a bullet, retrying after a PDF preview), use
    edit_application instead, which edits the CURRENT customized_json in place.
    Does NOT trigger AI suggestions. With no application_id, the job's newest
    application for this base resume is updated in place (still replaced wholesale);
    pass application_id to target a specific application explicitly. `ops` accepts
    the FULL vocabulary documented on edit_base_resume — every kind, not just
    the bullet/summary ones: replace_entry is how you change an entry's dates, title,
    company or tech list, and add/replace/remove/move_extra_section handle custom
    sections, which are ATS-neutral.
    """
    return _client.tailor_application(job_id, base_resume, ops, application_id=application_id)


@mcp.tool()
@_guard
def edit_application(application_id: str, ops: EditOps) -> Any:
    """INCREMENTAL FIX: apply typed edit ops on top of an existing application's
    CURRENT tailored resume (customized_json), preserving every prior edit.

    Falls back to the base resume only when the application has no customized_json
    yet (nothing to preserve). This is the right tool for refining or retrying a
    tailored resume after inspecting PDF previews — swap a bullet, tweak wording,
    fix one thing — without losing the rest of what's already been tailored and
    without creating duplicate applications. Contrast with tailor_application, which
    recomputes customized_json from scratch off the BASE resume and discards any
    tailored edits already on the application; use that only for a genuine rebuild.
    Accepts the FULL op vocabulary documented on edit_base_resume — every
    kind. Use replace_entry to change an entry's dates, title, company, project name
    or tech list; add/replace/remove/move_extra_section handle the custom
    Publications/Awards/Volunteer sections.

    Op field names (first-run friction fix — these exact keys, no synonyms):
    {"kind": "replace_bullet", "section": "experience", "index": 0,
     "bullet_index": 2, "value": "New bullet text"} — `kind` (not op/type),
    `index` (not entry_index; 0-based into the FULL array incl. disabled rows),
    `value` (not text). Check the response's applied[].name to confirm the
    intended entry was touched.
    Index is 0-based into the full customized_json array (including enabled:false);
    resolve indices from get_application, never PDF ordinals. Response `applied`
    echoes which entry name/index each op touched so a mismatch is obvious.
    Clears pdf_path/tex_path (old PDF is now stale) — call render_pdf before
    using or attaching the PDF.
    """
    return _client.edit_application(application_id, ops)


@mcp.tool()
@_guard
def update_application(
    application_id: str,
    status: str | None = None,
    applied_at: str | None = None,
    notes: str | None = None,
    referral_id: str | None = None,
) -> Any:
    """Update an application's tracking fields (status, applied_at, notes, referral_id).

    Only the arguments you pass are sent to the backend — the PATCH endpoint is
    driven by which fields were actually set on the request, so omitting an
    argument here leaves that field untouched. This means you CANNOT use this
    tool to clear a field back to null/empty (e.g. remove notes or unlink a
    referral): omitting an arg skips it entirely rather than sending an explicit
    null. Clearing a field requires the web UI.

    Allowed statuses: draft, applied, interviewing, offered, accepted, rejected,
    withdrawn (anything else is rejected).

    applied_at sync rule: if you change `status` without also passing `applied_at`,
    the backend keeps applied_at in sync automatically — entering "applied" stamps
    it with the current time (only if not already set), moving back to "draft"
    clears it, and every later stage (interviewing/offered/accepted/rejected/
    withdrawn) preserves whatever applied_at already holds. Pass `applied_at`
    explicitly (ISO 8601) only when you need to override that automatic behavior.
    """
    return _client.update_application(
        application_id,
        status=status,
        applied_at=applied_at,
        notes=notes,
        referral_id=referral_id,
    )


# ---------- apply package ----------
@mcp.tool()
@_guard
def generate_qa_answers(application_id: str, questions: list[str]) -> Any:
    """Generate a batch of screening-question answers for an application.
    `questions` is the complete list of questions to answer in this batch.
    Outreach/cold messages are asked as free-form questions here (e.g. "Write a
    short LinkedIn DM to the hiring manager") — answers are grounded in the
    resume and the application's linked referral contact when one exists."""
    return _client.generate_qa_answers(application_id, questions)


@mcp.tool()
@_guard
def generate_cover_letter(application_id: str, tone: str) -> Any:
    """Generate a cover letter for an application in the requested tone. This
    replaces the application's prior generated cover-letter entry."""
    return _client.generate_cover_letter(application_id, tone)


@mcp.tool()
@_guard
def render_pdf(target_type: Literal["base_resume", "application"], target_id: str,
               template_id: str | None = None) -> Any:
    """Render a PDF. target_type is 'base_resume' (target_id=slug) or 'application'
    (target_id=application id). Optional template_id selects a template (either
    engine; must be 'ready'; omit for the default). Response reports
    resolved_template_id / resolved_engine (the template actually used);
    template_fallback=true means the requested id was unusable and the default
    was silently substituted. Returns the render result incl.
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
        next_hint = None
        if _hints_enabled():
            next_hint = workflow.next_after_render(
                setup_status=_client.get_setup_status(),
                allowed_tools=_active_allowed_tools(),
                hints_enabled=True,
            )
        return {**result, "next": next_hint}
    raise ToolError("target_type must be 'base_resume' or 'application'")


@mcp.tool()
@_guard
def get_rendered_pdf(target_type: Literal["base_resume", "application", "template"], target_id: str) -> Any:
    """Save a rendered PDF locally and render one PNG per page without inlining images.
    target_type 'base_resume'(slug)/'application'(id) returns the last rendered resume
    PDF; 'template'(id) returns the sample preview PDF. Returns {filename, path,
    size_bytes, mime_type, page_count, page_images, em_dash_found, em_dash_pages,
    artifact_dir?}. Paths are local to where the backend/MCP server run — for
    browser upload use prepare_application_pdf_upload. The PDF and per-page PNGs ({id}.pN.png, ~120 dpi) are written under
    $MAESTRO_CS_PDF_DIR (or a temp dir). This slim response never includes image
    base64; call get_rendered_pdf_page_image for exactly one page when visual bytes
    are required. em_dash_found flags the STANDING RULE that a rendered resume must
    contain NO em dash (U+2014) — em_dash_pages lists the offending page numbers;
    fix and re-render before sending. (page_count is None / page_images empty if the
    PDF can't be read.) Render first (render_pdf / validate_template)."""
    return _client.get_rendered_pdf(target_type, target_id)


@mcp.tool()
@_guard
def get_rendered_pdf_page_image(
    target_type: Literal["base_resume", "application", "template"],
    target_id: str,
    page_number: int,
    max_dimension_px: int = 1024,
) -> Any:
    """Return one rendered PDF page as an explicit opt-in visual payload.
    page_number is 1-based. max_dimension_px (default 1024) is the longest
    side of the re-rendered PNG — only exceed 1024 when you ask. Encoded
    payloads over ~1MB are rejected; lower max_dimension_px and retry.
    Returns target_type, target_id, page_number, page_count, filename/path/
    size/mime metadata, and page_image_b64 for only the requested PNG.
    Out-of-range page numbers are rejected. Does not change get_rendered_pdf's
    pre-rendered preview PNGs."""
    return _client.get_rendered_pdf_page_image(
        target_type, target_id, page_number, max_dimension_px=max_dimension_px
    )


@mcp.tool()
@_guard
def prepare_application_pdf_upload(application_id: str) -> Any:
    """Stage a disposable copy of an application's canonical rendered PDF for
    direct Playwright upload. If the PDF has not been rendered, render it and
    retry once. Writes atomically under
    $MAESTRO_CS_UPLOAD_DIR/<application_id>/<canonical filename>, defaulting
    to the repository's .playwright-mcp/uploads directory (pair Playwright
    --output-dir with the parent .playwright-mcp tree). Returns upload_path —
    pass that absolute path straight to Playwright's file chooser. Do NOT
    copy/move the PDF with shell or Claude filesystem tools, invent a path under
    a screenshot dir, or upload from applications/artifact_dir. The canonical
    server artifact is preserved. Also returns filename/path integrity and PDF
    lint metadata. This preparation tool does not authorize or submit an
    application."""
    return _client.prepare_application_pdf_upload(application_id)


# ---------- resume templates (latex | typst) ----------
@mcp.tool()
@_guard
def list_templates() -> Any:
    """List resume templates — both engines (id, display_name, status['draft'|'ready'],
    engine, is_default, last_error). parse_certified false = a 'ready' template that
    still loses word boundaries under strict extraction — see validate_template."""
    return _client.list_templates()


@mcp.tool()
@_guard
def get_template(template_id: str) -> Any:
    """Get a template incl. its full source (Jinja2+LaTeX for engine='latex';
    raw .typ text for engine='typst') plus engine and supported_fmt_keys.
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


@mcp.tool()
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

    Typst constraints: dates arrive PRE-FORMATTED server-side — do not
    reference fmt.date_format. Package imports (`#import "@preview/..."` or
    any `@...` import) are REJECTED — inline instead. Fonts: only vendored
    XCharter plus typst's embedded defaults (e.g. Libertinus Serif); any
    other family compiles WITHOUT error and silently substitutes. MUST render
    r.extra_sections (both `entries` and `bullets` shapes) or a resume with
    custom sections hard-fails — copy the block from get_template('typst-classic').

    LaTeX: omit `source` to start from the canonical starter. Given source
    must be a complete compilable document (\\documentclass + preamble) as
    Jinja2 with blocks ((* *)), variables ((( ))), comments ((# #)). Write
    raw LaTeX not HTML entities: bare `&` for tabular, `\\&` for a literal
    ampersand — never `&amp;`. Includable: ((* include '_header.tex.j2' *)).
    Wire spacing/look to `fmt.*` (full knob list on get_template) rather than
    hard-coded values. Tip: start from get_template('default') and adapt.

    Pass validate=True to test-compile in the same call (status/last_error).
    Not usable until validation succeeds. `id` is a slug: [a-z0-9_-]."""
    return _client.create_template_draft(
        id, display_name, source, validate=validate, engine=engine
    )


@mcp.tool()
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


@mcp.tool()
@_guard
def validate_template(template_id: str) -> Any:
    """Test-compile a template against a built-in sample resume. On success it becomes
    'ready' (usable via render_pdf template_id) and a preview is available via
    get_rendered_pdf('template', id). On failure returns {ok: false, error} with the
    engine's compile error (Typst errors carry file:line:col); fix the source and
    re-validate. Returns {ok, error, parse_certified} — parse_certified is true when
    the template's compiled PDF round-trips through a strict text extractor with word
    boundaries intact, false when it drops text, null when not assessed.
    Also returns parse_report: {missing, headers_missing, extra_sections_supported,
    extra_sections_missing} — missing lists the exact sample phrases the PDF dropped
    (fix those, don't guess); extra_sections_missing non-empty means the template
    will hard-fail rendering any resume that has custom sections."""
    return _client.validate_template(template_id)


# ---------- profile coach ----------
@mcp.tool()
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


@mcp.tool()
@_guard
def explore_skill_heatmap(limit: int | None = None) -> Any:
    """Skill demand by role category (pct of jobs per skill x role)."""
    return _client.explore_skill_heatmap(limit=limit)


@mcp.tool()
@_guard
def explore_role_mix_over_time() -> Any:
    """Counts of jobs by role category per week."""
    return _client.explore_role_mix_over_time()


@mcp.tool()
@_guard
def explore_fit_distribution() -> Any:
    """How each base resume's ATS composites (deterministic engine) are
    distributed across jobs."""
    return _client.explore_fit_distribution()


@mcp.tool()
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
    stale, or is merely mis-placed on this one. For the learn-vs-move
    distinction, read the per-skill `tier` on build_areas (`build` = no resume
    evidence AND nothing in the Career KB, the only genuinely learn-it rows;
    `surface` = the material exists, port or strengthen it) — get_job_search_brief
    carries build_areas, or GET /api/explore/build-areas. Hygiene mirror_wording
    gaps are excluded here: the resume already matches those at full keyword
    credit, so the literal JD token moves no score and is not demand.
    Optionally filtered by role/level/type; limit caps the number of skills
    returned."""
    return _client.explore_gap_frequency(
        role_category=role_category,
        level=level,
        employment_type=employment_type,
        limit=limit,
    )


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
@_guard
def list_applications(
    status: str | None = None,
    role_category: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> Any:
    """List your applications as a thin paginated summary array. Filter by
    status/role_category; page with limit/offset. Use get_application(id) for
    the full record and compare_ats for scores."""
    return _client.list_applications(
        status=status, role_category=role_category, limit=limit, offset=offset
    )


@mcp.tool()
@_guard
def score_ats(
    job_id: str,
    target_type: str | None = None,
    target_id: str | None = None,
    brief: bool = False,
) -> Any:
    """Deterministic hybrid ATS score (no LLM): deterministic lexical layers +
    anchored pinned-model semantic matching + section-level semantic_fit. Omit
    target to score ALL base resumes (fast).

    target_type "base_resume" (target_id = slug) or "application" (target_id = id).
    Same inputs always give the same score; use it to compare bases and to
    verify an edit actually moved the number.

    Response is {scores, recommendation, next}. `scores` is the raw per-target
    list: composite (0-100), per-layer subscores (incl. semantic_fit), gate
    warnings, and a per-skill diagnostic table with fix_hints. `recommendation`
    is a deterministic ranking of the base-resume rows (order, recommended slug,
    margin, close_call, reasons, coverage_warning) — always present, cheap, and
    useful during triage even with hints off. `next` is an optional next-step
    hint (null when suppressed) naming quick_tailor / create_tailoring_session
    against the recommended base.

    Pass brief=True when scoring many jobs in a triage/mass-capture loop: it
    suppresses ONLY `next` (never `recommendation`) and is checked before any
    settings lookup, so a twenty-posting triage loop pays no extra HTTP
    round-trip for a hint nobody will read."""
    scores = _client.score_ats(job_id, target_type=target_type, target_id=target_id)
    recommendation = workflow.rank_bases(scores)
    if brief:
        return {"scores": scores, "recommendation": recommendation, "next": None}
    # Fetch the quick-tailor profile ONLY when it can actually be shown. It fills
    # exactly one thing — the quick_tailor option's `detail` — so fetching it with
    # hints off, or under a profile that never registers quick_tailor (hunt), is a
    # round-trip whose result is discarded. As keyword ARGUMENTS both reads would
    # be evaluated unconditionally, which is the trap this avoids: a twenty-posting
    # hunt loop would have paid 20 wasted calls even with hints switched off.
    allowed = _active_allowed_tools()
    hints_enabled = _hints_enabled()
    show_quick = hints_enabled and (allowed is None or "quick_tailor" in allowed)
    return {
        "scores": scores,
        "recommendation": recommendation,
        "next": workflow.next_after_scores(
            recommendation,
            job_id=job_id,
            quick_profile=_client.get_quick_tailor_profile() if show_quick else {},
            allowed_tools=allowed,
            hints_enabled=hints_enabled,
        ),
    }


@mcp.tool()
@_guard
def compare_ats(application_id: str) -> Any:
    """Before/after ATS comparison for an application: composite and per-layer deltas
    plus a per-skill diff (absent→matched, skills-list-only→dual, decayed→recent).
    Computes any missing phase row on demand."""
    return _client.compare_ats(application_id)


@mcp.tool()
@_guard
def create_tailoring_session(job_id: str, base_resume: str, enrich: bool = False) -> Any:
    """Start the gap-analysis tailoring workflow for a job + base resume.

    Calling again for the same job+base SUPERSEDES the open session (saved
    resolutions become unreachable) — check list_tailoring_sessions first
    when resuming.

    Scores the base (deterministic ATS engine, persisted as the 'before' score) and
    returns a session whose gaps_json.categories list every gap in fix-cost order:
    missing skills, wording mismatches, placement upgrades, stale evidence, adjacent
    skills, title/structure. Walk the user through the gaps in that order, collect
    their answers, save them with resolve_gaps, then run tailor_session. Each gap
    carries its allowed actions. A missing skill MAY use add_keyword ONLY to add the
    keyword to a skills category (placement_target.section="skills") when the candidate
    genuinely has the skill but won't add a project/bullet — it inserts an unverified
    skills-list item, never a fabricated bullet. Prefer the evidence-backed paths: ask
    the gap's elicitation question (enrichment.elicitation_question) and record the
    user's answer with a user_input resolution, or attach_project (or skip if they
    don't have it).

    enrich=False (default) skips the backend's fast-model enrichment pass — no
    in-house LLM call — so gaps carry only their deterministic fields (no
    enrichment.elicitation_question / suggested_wording / suggested_placement).
    KB coverage detection does NOT depend on it: the deterministic self-nomination
    and evidence-verification pass that used to sit downstream of the LLM call now
    runs unconditionally, so KB autos still get stamped with enrich=False and even
    if a provider outage would have broken the LLM pass. Pass enrich=True to
    additionally pay for one fast-model call that adds those display-only
    explanations and elicitation questions to each gap — it never changes scores
    or which gaps exist.

    Response is the session plus a `next` next-step hint (null when the user's
    Settings switch has hints off)."""
    session = _client.create_tailoring_session(job_id, base_resume, enrich=enrich)
    return {**session, "next": _session_hint(session)}


@mcp.tool()
@_guard
def quick_tailor(job_id: str, base_resume: str) -> Any:
    """Start Quick Tailor over MCP: the fast path that fills gaps from the
    user's saved quick-tailor profile instead of walking them one by one.

    Calling again for the same job+base SUPERSEDES the open session (saved
    resolutions become unreachable) — check list_tailoring_sessions first
    when resuming.

    Composes create_tailoring_session(enrich=False) with POST .../apply-profile
    (deterministic, same honesty-gated save path as resolve_gaps) and returns
    the filled session.

    This tool makes NO in-house LLM call of its own. Sessions rely on the
    CALLING agent's own model, not the backend's. The saved profile only plans
    mechanical, evidence-respecting moves — it does NOT write resume prose.
    After this call: read resolutions_json (may already resolve every gap,
    including system-planned entries with payload.provenance), author typed
    edit ops yourself, then tailor_session(tailoring_session_id=..., ops=[...])
    — supplying `ops` skips the backend LLM pass.

    Honesty: never fabricate skills, experience, metrics, or dates. An
    unverified or absent skill may ONLY be added to a skills category
    (add_skill_item) — never as an experience or project bullet asserting
    the candidate did the work.

    A session whose resolutions_json contains no planned action beyond
    "skip" means the profile was not ALLOWED to add anything to THIS
    session — it is not an error. Walk the gaps with resolve_gaps instead.

    Raises (409, message says which): a failing fatal health gate on the
    base blocks session creation; a stale or no-longer-open session blocks
    the profile fill. Response is the filled session plus a `next` hint
    suggesting tailor_session (profile standing instruction as user_prompt
    when the session has no note of its own)."""
    session = _client.create_tailoring_session(job_id, base_resume, enrich=False)
    filled = _client.apply_quick_tailor_profile(session["id"])
    if not _hints_enabled():
        return {**filled, "next": None}
    profile = _client.get_quick_tailor_profile()
    next_hint = workflow.next_after_session(
        filled,
        allowed_tools=_active_allowed_tools(),
        hints_enabled=True,
        instruction=_instruction_from_profile(profile),
    )
    return {**filled, "next": next_hint}


@mcp.tool()
@_guard
def list_tailoring_sessions(job_id: str) -> Any:
    """List all tailoring sessions for a job, newest first.

    Use this to rediscover a session id you've lost track of instead of calling
    create_tailoring_session again and spawning a duplicate. Each item's status is
    one of: open (in-progress gap walkthrough, resumable via get_tailoring_session),
    tailored (finished — tailor_session already ran), superseded (a newer session
    for the same job+base replaced it), or abandoned (explicitly closed via
    close_tailoring_session without tailoring). Filter client-side for status
    "open" to find a session worth resuming."""
    return _client.list_tailoring_sessions(job_id)


@mcp.tool()
@_guard
def get_tailoring_session(tailoring_session_id: str) -> Any:
    """Fetch a tailoring session to resume a half-done gap walkthrough.

    `tailoring_session_id` is the id returned by create_tailoring_session. Returns
    the session with its frozen gap list (gaps_json), any resolutions saved so far
    (resolutions_json), and status (open/tailored). resolutions_json may already
    contain SYSTEM-PLANNED auto-resolutions stamped at creation (their payload
    carries `provenance`, e.g. library_auto/kb_auto/kb_profile/wording_auto —
    hand-made resolutions never do): verified evidence the resolver pre-applied.
    Review them instead of re-deriving; to retract one, resend its gap_id with
    action "skip". Pick up at the first unresolved gap, collect the remaining
    resolutions, then tailor_session."""
    return _client.get_tailoring_session(tailoring_session_id)


@mcp.tool()
@_guard
def close_tailoring_session(tailoring_session_id: str) -> Any:
    """Abandon an OPEN tailoring session without tailoring it.

    `tailoring_session_id` is the id returned by create_tailoring_session. This is
    the explicit exit for a "changed my mind" flow — e.g. the user walks through
    some gaps, then decides to use the base resume as-is and never calls
    tailor_session. Marks the session's status "abandoned" so it stops looking like
    unfinished work. Errors (409) if the session isn't currently open (already
    tailored, already superseded, or already abandoned)."""
    return _client.close_tailoring_session(tailoring_session_id)


@mcp.tool()
@_guard
def resolve_gaps(
    tailoring_session_id: str, resolutions: GapResolutions
) -> Any:
    """Save gap resolutions on a tailoring session (merge by gap_id, idempotent).
    The batch is validated as ONE unit — one invalid item saves NOTHING
    (existing saved resolutions untouched); fix and resend.

    `tailoring_session_id` is the id from create_tailoring_session. Each item
    is {gap_id, action, payload}. Actions: add_keyword, user_input,
    attach_project, skip, enable_entry, port_kb_point, cannot_confirm.
    Payload shapes live on the `resolutions` parameter schema.

    enable_entry and port_kb_point carry verified evidence and are exempt
    from the add_keyword missing-skill rule (unverified additions stay in
    skills). Re-sending a gap_id overwrites that gap; other saved resolutions
    stay — including system-planned autos (payload.provenance; see
    get_tailoring_session). Call as many times as needed, then tailor_session.
    Merge-only: omitting a gap_id never removes its saved resolution — resend
    that gap_id with action "skip" to retract.

    Response is the session plus a `next` hint (null when hints are off)."""
    session = _client.resolve_gaps(tailoring_session_id, resolutions)
    return {**session, "next": _session_hint(session)}


@mcp.tool()
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
    - Caller-supplied (ops given): you have already produced the typed edit ops
      yourself (same op shapes as tailor_application/edit_application). The backend
      skips its own LLM pass and applies your ops directly — your judgment IS the
      tailor. Read the base with get_base_resume first, then send only the changed
      fields as `ops`.

    Whichever path you use, the honesty rules still apply: never fabricate skills,
    experience, metrics, or dates. An unverified or absent skill may ONLY be added
    to the skills list (an add_skill_item op into a skills category) — never as an
    experience or project bullet asserting the candidate did the work. Every edit
    should trace back to a resolution or the candidate's real material; the
    before/after compare view is the audit surface for any edit that goes beyond
    the saved resolutions, so keep your ops honest and reviewable.

    Optional user_prompt adds free-form tailoring guidance. Creates the application
    from the base resume plus the ops, scores the result, and returns
    {session, compare, compare_error, next}. compare holds the before/after ATS
    deltas; it may be null with compare_error set if the scores weren't comparable
    — the tailor still succeeded in that case, so relay the application and the
    error note to the user rather than retrying. `kb_writeback_skips` derives
    from each user_input resolution's STORED placement_target from resolve_gaps,
    not from your ops — keep them aligned or expect a spurious wrong_section
    skip. `next` is a next-step hint naming render_pdf for the new application
    (null when suppressed)."""
    result = _client.tailor_session(tailoring_session_id, user_prompt=user_prompt, ops=ops)
    application_id = (result.get("session") or {}).get("application_id")
    next_hint = (
        workflow.next_after_tailor(
            application_id=application_id,
            allowed_tools=_active_allowed_tools(),
            hints_enabled=_hints_enabled(),
        )
        if application_id
        else None
    )
    return {**result, "next": next_hint}


@mcp.tool()
@_guard
def export_jobs(
    role_category: str | None = None,
    level: str | None = None,
    since: str | None = None,
    skill: str | None = None,
) -> Any:
    """Bulk export jobs with extracted fields and nested skills, for open-ended analysis.
    since is an ISO date (YYYY-MM-DD); skill is a case-insensitive substring."""
    return _client.export_jobs(role_category=role_category, level=level, since=since, skill=skill)


# ---------- proposal ledger tools ----------
@mcp.tool()
@_guard
def propose_application(
    job_id: str,
    fit: dict | None = None,
    plan: dict | None = None,
    application_id: str | None = None,
    referral_id: str | None = None,
) -> Any:
    """File an agent-hunted application proposal for user review.

    If an open proposal already exists for the job, returns that proposal (idempotent)
    instead of 409. Pass application_id after tailoring to late-link when the open
    proposal is still unlinked (409 if already linked to a different application).
    Refused (409) when the company is blocklisted or when THIS posting was
    previously declined (declines are posting-scoped and permanent — never
    re-propose a declined job; other roles at the same company are fine).
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
    )


@mcp.tool()
@_guard
def list_proposals(status: str | None = None) -> Any:
    """List application proposals, optionally filtered by status.

    Contract for apply runs: execute status='accepted' proposals ONLY —
    pending_review is staging/discussion inventory, never auto-executed;
    a proposal reaches accepted through the user's triage decision
    (/proposals page or record_triage)."""
    return _client.list_proposals(status=status)


@mcp.tool()
@_guard
def get_proposal(proposal_id: str) -> Any:
    """Get proposal detail including job facts, application summary, QA entries, and evidence manifest."""
    return _client.get_proposal(proposal_id)


@mcp.tool()
@_guard
def record_decision(proposal_id: str, fit: dict, application_id: str | None = None) -> Any:
    """Record user decision when proposal is in needs_decision state. Resolves back to
    pending_review. application_id may be omitted; the backend then links the newest
    application matching the proposal job and fit.chosen_base (409 if none)."""
    return _client.record_decision(
        proposal_id, fit=fit, application_id=application_id
    )


@mcp.tool()
@_guard
def request_decision(proposal_id: str, reason: str) -> Any:
    """Escalate an unlinked/ambiguous proposal to needs_decision. Idempotent if already
    needs_decision."""
    return _client.request_decision(proposal_id, reason=reason)


@mcp.tool()
@_guard
def resume_proposal(proposal_id: str) -> Any:
    """Return a needs_human proposal to pending_review so preparation can continue.
    Releases any pre-click daily-cap reservation. Refused for submission_uncertain."""
    return _client.resume_proposal(proposal_id)


@mcp.tool()
@_guard
def get_final_review(proposal_id: str) -> Any:
    """Compact final-review bundle: job summary, chosen base/ATS delta, PDF readiness,
    QA answers, EEO consent flag (no values), blocked/manual items, evidence manifest.
    Requires an existing proposal — a 404 usually means propose_application was
    never called (it accepts application_id to late-link) or an application id
    was passed where a proposal id belongs. duplicate_submitted=true means a
    same-company+title proposal was already submitted — surface this to the user
    LOUDLY before asking for consent."""
    return _client.get_final_review(proposal_id)


@mcp.tool()
@_guard
def record_consent(
    proposal_id: str,
    action: Literal["approved", "rejected"],
    channel: Literal["chat", "slack", "mcp"],
    note: str | None = None,
) -> Any:
    """Record the user's explicit consent decision. Only call after the user has actually said yes/no; the backend writes an append-only audit row. Approval requires final_review evidence and reserves a daily-cap slot."""
    consent = {"channel": channel, "note": note}
    return _client.transition_proposal(proposal_id, action, consent=consent)


@mcp.tool()
@_guard
def attach_evidence(
    proposal_id: str,
    step: int,
    label: str,
    image_base64: str,
    kind: Literal["step", "final_review", "submission_receipt"] = "step",
) -> Any:
    """Attach step evidence image (base64) to a proposal. PREFER
    attach_evidence_file whenever the screenshot exists as a file on this
    machine — never round-trip image bytes through your own context.
    kind must be step | final_review | submission_receipt."""
    return _client.attach_evidence(proposal_id, step, label, image_base64, kind=kind)


@mcp.tool()
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
    --output-dir and reports the path). Pass the ABSOLUTE path exactly as the
    browser tool reported it — with the standard setup that is under the repo's
    .playwright-mcp/ tree (e.g.
    /Users/<user>/Projects/maestro-career-studio/.playwright-mcp/<name>.png). Do not
    invent screenshot-dir paths or pass relative paths. The bytes are read and
    uploaded server-side so they never enter the model context.
    PNG/JPEG only, 5 MB max. kind must be step | final_review | submission_receipt."""
    return _client.attach_evidence_file(proposal_id, step, label, file_path, kind=kind)


@mcp.tool()
@_guard
def mark_submitted(
    proposal_id: str,
    user_attested: bool = False,
    channel: Literal["chat", "slack", "mcp"] = "chat",
    note: str | None = None,
) -> Any:
    """Flip an approved proposal to submitted (links the application to applied).
    Normally requires submission_receipt evidence. When the USER explicitly says
    they submitted it themselves (or confirms a submission_uncertain proposal
    went through — confirmation email / portal check), pass user_attested=True
    with their words in note; recorded as an attested consent event. NEVER pass
    user_attested on your own judgment — receipt evidence is the agent-verified
    path."""
    if user_attested:
        return _client.transition_proposal(
            proposal_id, "submitted", attested=True,
            consent={"channel": channel, "note": note},
        )
    return _client.transition_proposal(proposal_id, "submitted")


@mcp.tool()
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
    (never the company). Call ONLY after the user actually stated the decision
    or the selection criteria; the backend writes one append-only consent row
    per proposal and returns a per-id ok/error report. Triage accept is NOT
    submit consent: the final per-application approval still happens at the
    submit boundary via record_consent."""
    status = "accepted" if action == "accept" else "rejected"
    return _client.bulk_transition_proposals(
        proposal_ids, status=status, channel=channel, note=note, reason=reason,
    )


@mcp.tool()
@_guard
def report_failure(proposal_id: str, reason: str) -> Any:
    """Report execution failure. From pending_review/approved, transitions to needs_human
    (resumable). Pass reason='submission_uncertain' after an unverified browser submit click
    to enter the terminal submission_uncertain status — never resume or click again."""
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
