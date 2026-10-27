from __future__ import annotations

import functools
import inspect
import logging
import os
from collections.abc import Callable
from contextvars import ContextVar
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.tools import Tool
from mcp.server.lowlevel import Server
from mcp.types import ToolAnnotations
from pydantic import BeforeValidator, ConfigDict, Field, with_config

from app.schemas.autofill_profile import WorkAuthStatus
from app.schemas.quick_tailor import QuickTailorProfile
from app.schemas.resume_edit import op_kinds_ordered, render_ops_shapes
from app.services import http_client, markets
from mcp_server import orientation, replaced, workflow
from mcp_server.client import CLEAR_TAKES_A_LIST, EXPLORE_VIEWS, BackendClient, BackendError
from mcp_server.profiles import allowed_tools, get_profile

logger = logging.getLogger(__name__)


def _lowlevel(server: FastMCP) -> Server:
    """The SDK's low-level server: the one private attribute whose name changes in 2.x
    (1.x `_mcp_server`, 2.x `_lowlevel_server`)."""
    return server._mcp_server


class _ServedMCP(FastMCP):
    """One served set. The registry (`mcp`, profile None) holds every tool; build_set makes a
    set from it. A call to a removed tool, or with a removed argument, gets mcp_server.replaced's
    sentence on stdio and HTTP alike."""

    def __init__(self, *args: Any, profile: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.profile = profile  # None: the registry; hints follow MAESTRO_CS_MCP_PROFILE

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if self._tool_manager.get_tool(name) is None:
            # A set holds only its own tools, so the answer can say where the new one is.
            served = {tool.name for tool in self._tool_manager.list_tools()}
            refusal = replaced.replaced_message(name, served=served)
        else:
            refusal = replaced.refused_argument(name, arguments)
        if refusal:
            raise ToolError(refusal)
        # A profile of None (the registry, called directly in tests) leaves the caller's value
        # alone; every served set has one.
        token = CURRENT_PROFILE.set(self.profile) if self.profile is not None else None
        try:
            return await super().call_tool(name, arguments)
        finally:
            if token is not None:
                CURRENT_PROFILE.reset(token)


# The full set's text; every served set, stdio or HTTP, gets its own from build_set.
mcp = _ServedMCP("maestro-career-studio", instructions=orientation.instructions_for("full"))
_client = BackendClient()

# Each served set sets this for its calls; the registry leaves it unset, so a direct call's
# hints follow the env profile. Workflow hints must only name tools the caller's profile can see.
CURRENT_PROFILE: ContextVar[str | None] = ContextVar("maestro_mcp_profile", default=None)

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
        "OR bullets:[str] — never both; unknown keys are rejected (400, extra=\"forbid\"). "
        "Text the ops write is implied first person: a line with I/he/she/they or the "
        "owner's name is a 400 naming the lines, and nothing is written."
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

# Immune to the ~2048-char tool-description truncation: lives on the param schema.
_TAILOR_OPS_FIELD = Field(
    description=(
        "Typed edit ops, the shapes edit_application's ops parameter lists; omitted (and "
        "no_new_text false), Maestro's AI writes them when the user's writer setting is "
        "Maestro's AI. "
        "With ops the server itself applies only the saved enable_entry "
        "and port_kb_point answers: user_input and attach_project answers reach the "
        "resume only through these ops, and answers_left_to_ops lists them. On every "
        "path a saved add_keyword whose word (its wording, else the gap's jd_skill) "
        "is not on the result is added to the skills list, in the category it chose, "
        "else Additional Skills, never as a bullet; keywords_added lists those words."
    )
)
TailorOps = Annotated[list[dict] | None, _TAILOR_OPS_FIELD]

# Immune to the ~2048-char tool-description truncation: lives on the param schema.
_NO_NEW_TEXT_FIELD = Field(
    description=(
        "True: Maestro writes no new wording and calls no model, whichever writer setting "
        "the user chose. It applies only the saved answers that need none: enable_entry, "
        "port_kb_point (an approved career-history bullet) and add_keyword into the skills "
        "list (keywords_added lists the words). An add_keyword placed anywhere else needs a "
        "rewritten line: its word lands in the skills list when the resume lacks it, and "
        "otherwise the answer is listed in answers_left_to_ops beside the user_input and "
        "attach_project answers; nothing listed there reaches the resume. With non-empty ops "
        "it is a 422; when nothing can be applied without new wording it is a 400 that says so."
    )
)
NoNewText = Annotated[bool, _NO_NEW_TEXT_FIELD]

# Immune to the ~2048-char tool-description truncation: lives on the param schema.
_USE_PRESETS_FIELD = Field(
    description=(
        "True: once the session is created, fill it from the user's Quick tailor presets "
        "(get_tailoring_options explains them) through resolve_gaps' honesty-gated save "
        "path, deterministically and with no AI. The presets plan only mechanical, "
        "evidence-respecting moves; the fill does not write resume text. The returned "
        "resolutions_json may already resolve every gap, including system-planned entries "
        "(payload.provenance); a gap the presets do not decide is saved as skip. A session "
        "whose answers are all skip is not an error: the presets allowed nothing for it, "
        "and resolve_gaps still saves answers on it. An unverified or absent skill enters "
        "only a skills category (add_skill_item), never as an experience or project bullet; "
        "the server does not gate edit ops the caller writes against fabricated skills, "
        "experience, metrics or dates. A stale or no-longer-open session blocks the fill (409). "
        "The `next` hint then carries the presets' standing instruction as tailor_session's "
        "user_prompt when the session has no note of its own."
    )
)
UsePresets = Annotated[bool, _USE_PRESETS_FIELD]


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

class AuthoredAnswerInput(TypedDict):
    """One screening question with the caller's own answer."""

    question: str
    answer: str


_AUTHORED_ANSWERS_FIELD = Field(
    min_length=1,
    max_length=50,
    description=(
        "1-50 {question, answer} pairs: question as the form asks it (at most 2000 "
        "characters), answer as it goes into the form (at most 10000)."
    ),
)
AuthoredAnswers = Annotated[list[AuthoredAnswerInput], _AUTHORED_ANSWERS_FIELD]

_KB_POINTS_FIELD = Field(
    min_length=1,
    max_length=50,
    description="1-50 bullets for the one entity, each at most 1000 characters.",
)
KBPoints = Annotated[list[str], _KB_POINTS_FIELD]

_INGEST_DATA_FIELD = Field(
    description=(
        "ResumeData. Only contact.name and contact.email are required. 422 if "
        "any source fails validation or on a duplicate SOURCE key (re-running "
        "the same resume_key is a merge, not an error); atomic either way: "
        "nothing persisted on a 422."
    )
)


# ---------- profile facts: the shapes the profile writes take ----------
# Each refuses an unknown key, so a misspelt field is an error rather than an answer no reader
# looks for; the keys are the ones Profile shows and the Companion fills. A market is the market
# setting's own key ("UK", not the ISO "GB"), listed from services/data/markets.yaml.
MarketKey = Literal[tuple(markets.keys())]


@with_config(ConfigDict(extra="forbid"))
class PersonalAnswers(TypedDict, total=False):
    """Contact and address answers; a null removes one."""

    first_name: str | None
    last_name: str | None
    preferred_name: str | None
    email: str | None
    phone: str | None
    address: str | None
    address_2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None
    linkedin: str | None
    github: str | None
    website: str | None


@with_config(ConfigDict(extra="forbid"))
class EligibilityAnswers(TypedDict, total=False):
    """Yes/No eligibility answers (true is Yes); a null removes one."""

    over_18: bool | None
    previously_employed_here: bool | None
    non_compete: bool | None


@with_config(ConfigDict(extra="forbid"))
class PreferenceAnswers(TypedDict, total=False):
    """Start and pay answers, in the words a form gets; a null removes one."""

    desired_salary: str | None
    notice_period: str | None
    earliest_start_date: str | None
    willing_to_relocate: bool | None
    how_heard: str | None


@with_config(ConfigDict(extra="forbid"))
class WorkPermitAnswers(TypedDict, total=False):
    """One country's work-permit answers (true is Yes); a null removes one. status is the US
    visa status, asked for the US only; authorization_expires_on is YYYY-MM-DD, absent when the
    right to work there does not run out."""

    status: WorkAuthStatus | None
    authorized_now: bool | None
    sponsorship_now: bool | None
    sponsorship_future: bool | None
    authorization_expires_on: str | None


@with_config(ConfigDict(extra="forbid"))
class EducationEntry(TypedDict, total=False):
    """One school, most recent first in the list."""

    school: str
    degree: str
    discipline: str
    gpa: str
    start_year: str
    end_year: str


LanguageLevel = Literal["Basic", "Intermediate", "Fluent"]


@with_config(ConfigDict(extra="forbid"))
class LanguageEntry(TypedDict, total=False):
    """One language; native and fluent are separate answers, as forms ask them."""

    language: str
    read: LanguageLevel
    speak: LanguageLevel
    write: LanguageLevel
    native: bool
    fluent: bool


@with_config(ConfigDict(extra="forbid"))
class SavedAnswer(TypedDict):
    """A question the profile's other sections do not answer, with the user's answer.
    only_for names the one company or city it holds for (only_for_kind)."""

    question: str
    answer: str
    only_for: NotRequired[str]
    only_for_kind: NotRequired[Literal["company", "city"]]


@with_config(ConfigDict(extra="forbid"))
class FavoredRoleInput(TypedDict, total=False):
    """A role the user wants: label in their own words, or role as a catalog key (its category
    and label come from the catalog; an unknown key is a 422)."""

    role: str | None
    label: str
    category: str | None


@with_config(ConfigDict(extra="forbid"))
class MinSalaryInput(TypedDict, total=False):
    """The lowest yearly pay wanted; currency is ISO 4217, null for the home currency."""

    amount: int
    currency: str | None


WorkPermitsArg = Annotated[
    dict[MarketKey, WorkPermitAnswers | None] | None,
    Field(description=(
        "Work-permit answers by market key. Each country's answers merge key by key; a "
        "country set to null loses its answers; a country left out keeps them."
    )),
]


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
    return (os.environ.get("MAESTRO_CS_MCP_CLIENT") or "").strip() or None


# ---------- next-step hints (mcp_server/workflow.py) ----------
# The wrapped tools below (score_ats, create_tailoring_session, resolve_gaps,
# tailor_session, render_pdf) all need the same two facts to
# compose a hint: which tools THIS profile registered, and whether the user's
# Settings switch allows hints at all. Centralized here so each tool reads as
# "do the work, then ask for a hint" rather than re-deriving both facts inline.


def _active_allowed_tools() -> frozenset[str] | None:
    """The request profile's allowlist, falling back to the env for calls made outside a served set."""
    return allowed_tools(CURRENT_PROFILE.get())


def _hints_enabled() -> bool:
    """The user's master switch (GET /api/settings/mcp-workflow). Off means no
    hint is ever composed, whatever an individual tool call asks for — this is
    the one control the server itself can hold (see workflow.py's "Who
    controls the hints")."""
    return bool(_client.get_mcp_workflow_settings().get("hints", True))


def _writer(settings: dict[str, Any]) -> workflow.Writer:
    """Who writes for agent apps, from the saved mcp_workflow setting: "maestro" only
    when the user picked Maestro's AI, else "agent" (the default, which a setting saved
    before the choice existed also reads as). The one place the stored value is
    normalised; workflow takes it as given."""
    return "maestro" if settings.get("writer") == "maestro" else "agent"


def _session_hint(
    session: dict[str, Any], *, instruction: str | None = None
) -> dict[str, Any] | None:
    """Shared by create_tailoring_session (with or without use_presets) and
    resolve_gaps — both return a session in the same shape, so the same hint
    composer applies regardless of which call produced it. One settings read
    gives both the hints switch and who writes, which the tailor option names."""

    def compose() -> dict[str, Any] | None:
        settings = _client.get_mcp_workflow_settings()
        return workflow.next_after_session(
            session,
            allowed_tools=_active_allowed_tools(),
            hints_enabled=bool(settings.get("hints", True)),
            instruction=instruction,
            writer=_writer(settings),
        )

    return _best_effort_hint(compose)


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
def list_base_resumes(include_archived: bool = False) -> Any:
    """List base resumes (slug, display name, summary). By default only the ones
    that can be picked; include_archived=true adds the archived ones, each with
    its archived_at date (archiving hides a resume from scoring and the pickers
    without deleting it)."""
    return _client.list_base_resumes(include_archived=include_archived)


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
    opt_accepted, best_ats_score: the best stored base-resume score, null when
    unscored) of roughly 0.8k characters, with no raw_text or extracted_json;
    use get_job for full detail. Optionally only jobs without an application.
    Each job carries ownership (owned_here, owner, handover, pending_requests),
    identifying replicas and jobs being handed over."""
    return _client.list_jobs(
        limit=limit, offset=offset, without_application=without_application
    )


@mcp.tool(**_read("Get Job Details"))
@_guard
def get_job(job_id: str) -> Any:
    """Get a job with its most recent application. The nested job carries
    ownership (owned_here, owner, handover, pending_requests), identifying
    replicas and jobs being handed over."""
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
    """List an application's screening answers and cover letters, newest first:
    the ones the app's model generated and the ones a caller stored."""
    return _client.list_qa_entries(application_id)


# ---------- health check ----------
@mcp.tool(**_write("Run Resume Health Check", destructive=False, idempotent=False, open_world=True))
@_guard
def run_health_check(kind: Literal["base", "application"], key: str) -> Any:
    """Run the JD-independent resume health check on a base resume or a tailored
    application. `kind` is 'base' (then `key` is the base-resume slug) or
    'application' (then `key` is the application id). Classifies every bullet on
    the evidence ladder, checks structure/content gates, and returns
    {score, grade, tier, next_grade, gates, counts, findings, judged} ranked by what
    each defect costs. Concrete qualitative results can earn full credit. An ask/fix
    finding carries question, ask_kind (measure|detail|reword), measure_target,
    alt_question, gain and evidence. Notes score zero: the evidence.no_numbers flag and
    language.* wording notes. Disputes and the word bank are web-only for now.
    `judged` is {done, pending, by}: bullets a judge has read, bullets waiting, and the
    judges' model ids. When Maestro's own model does not judge (no model key is set, or the
    user's settings say the agent app writes), no model is called: only stored judgments
    count (any judge, current rubric version); score, grade and next_grade are null while
    a scored bullet is pending, and `judging` is {rubric_version, pending_ids, prompt},
    where prompt is the app's own evaluator prompt filled with the pending bullets;
    judge_health_bullets stores answers in that prompt's output shape.
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


@mcp.tool(**_write("Judge Resume Bullets", destructive=False, idempotent=False))
@_guard
def judge_health_bullets(
    kind: Literal["base", "application"],
    key: str,
    classifications: list[dict[str, Any]],
    ctx: Context | None = None,
) -> Any:
    """Stores evaluations of a resume's pending bullets while Maestro's own model does not
    judge them (no model key is set, or the agent app writes), then rebuilds its health
    report. `kind` is 'base' or 'application', `key` the slug or application id.
    `classifications` is the `classifications` list in the output shape that
    `judging.prompt` from run_health_check states, one entry per pending id. Each
    entry gets the checks a model's answer gets: `level` is one of direct, analogue,
    adjacent, implied, unaddressed; analogue and direct need a verbatim quote of three or
    more words from the bullet in `evidence`, else the level is stored as adjacent; a
    measure question survives only when its target is in the bullet's own words. An id
    that is not pending (already judged, or its text changed) is rejected. Judgments are
    stored under this client's name and count while Maestro's own model does not judge.
    Returns the rebuilt report (fields as in run_health_check) plus accepted [{id, level as
    stored}] and rejected [{id, reason}]. 409 while Maestro's own model judges: a model key
    is set and Maestro's AI writes for agent apps."""
    return _client.judge_health_bullets(
        kind, key, classifications, origin_detail=_client_label(ctx))


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
# Immune to the ~2048-char tool-description truncation: lives on the param schema.
_APPLY_URL_FIELD = Field(
    description=(
        "The posting's application address when it differs from source_url (http or https). "
        "Stored with the job; find_job_by_url then finds the job by it when the address names "
        "the posting (an id in its path or query). Without update, a saved job takes it only "
        "when it has none; with update it replaces the stored one."
    )
)
_UPDATE_FIELD = Field(
    description=(
        "True: when the posting is already saved, this extraction replaces that job's fields and "
        "skills through the same mapping a new capture uses; the job keeps its id, status, "
        "applications, proposals, source and raw_text. It overwrites the stored extraction, which "
        "the web app can't undo. The saved job is found the way a capture finds it: resend the "
        "saved raw_text, or omit raw_text and pass its source_url (new raw_text misses the text "
        "match and creates a new job). The response's correction is {changed: the fields whose "
        "value changed, \"skills\" when the skill list did; scores_cleared: the job's match "
        "scores deleted because a field scoring reads changed, after which the job is scored "
        "again; rescored: true when that succeeded; rescore_failed: \"bases\" or the application "
        "ids it could not score, which score_ats computes later; tailored_applications: tailored "
        "resumes, left as written; open_sessions: open gap analyses, left to read as out of date, "
        "with their score link cleared; proposals_fit_stale: proposals whose stored fit predates "
        "the correction}. A job another copy of Maestro owns is refused (409). False (default): "
        "a repeat capture returns the saved job unchanged."
    )
)


@mcp.tool(**_write("Save Extracted Job", destructive=False, idempotent=True))
@_guard
def store_extracted_jd(
    extracted_json: dict,
    raw_text: str | None = None,
    source_url: str | None = None,
    source: Literal["user", "agent"] = "user",
    apply_url: Annotated[str | None, _APPLY_URL_FIELD] = None,
    update: Annotated[bool, _UPDATE_FIELD] = False,
) -> Any:
    """Store a job description the caller already extracted into JSON (the backend
    makes no LLM call).

    extracted_json must match the app's JobExtraction schema: company, title,
    role_category, level: "intern"|"entry"|"mid"|"senior"|"lead" (other spellings
    map to these; any other level is kept in its own words), employment_type,
    work_mode: "remote"|"hybrid"|"on_site" (stored as that key), city/state/country
    (the job also stores country_code, the one ISO code they name),
    location_raw, salary_min/max, salary_period, salary_currency (ISO 4217; a bare "$"
    is no currency, so the job takes its country's, else the home one, and
    salary_currency_assumed is true),
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

    A posting already saved is returned unchanged with already_existed=true,
    unless update=true: then this extraction corrects it and the job carries
    correction. Already saved means the same raw_text (with none, the same
    extraction or the same posting at source_url) or the same company and
    requisition_id.
    """
    return _client.store_extracted_jd(
        extracted_json, raw_text=raw_text, source_url=source_url, source=source,
        apply_url=apply_url, update=update,
    )


# ---------- orientation ----------
@mcp.tool(**_read("Get Setup Status"))
@_guard
def get_setup_status() -> Any:
    """Where this user's Maestro setup stands, for an agent starting fresh. Returns
    ai_key (whether Maestro has its own AI key), writer (who writes for agent apps:
    "agent", the default, means the agent app writes, so the tools where Maestro's own
    AI writes the text refuse (409) and the agent writes it and saves it with the
    matching store or add tool; "maestro" means Maestro's AI writes it with the user's
    key, which needs ai_key), demo_bases (slugs of the shipped demo resume, never the
    user's own), next_step (the first setup step an agent can do that is not done,
    {step, tool_set, says}; null when none is left), tool_sets (each set's name,
    use_when and holds, in journey order) and steps (the full setup status: each step's
    done and detail, form-answer readiness, suggested bases, PDF engines). The AI key,
    the writer and the default resume design are set by the user in the app and are
    never a next step."""
    status = _client.get_setup_status()
    return {
        "ai_key": bool((status.get("model_key") or {}).get("done")),
        "writer": _writer(_client.get_mcp_workflow_settings()),
        "demo_bases": list(status.get("demo_bases") or []),
        "next_step": workflow.setup_next_step(status),
        "tool_sets": [
            {"name": s.name, "use_when": s.use_when, "holds": s.holds} for s in orientation.SETS
        ],
        "steps": status,
    }


@mcp.tool(**_read("Get Tailoring Options"))
@_guard
def get_tailoring_options() -> Any:
    """The user's Quick tailor presets, as data an agent can explain or work around.
    Returns presets ([{key, on, means}]: each switch, whether it is on, and its plain
    meaning), instruction (an extra instruction the user gave for every tailor, may be
    empty) and persona (the user's own words on tone, may be empty).
    create_tailoring_session with use_presets follows these presets; a custom tailor
    walks the gaps with the user however the agent talks with them and saves the
    decisions with resolve_gaps. Either way the server keeps its rules: an unproven
    skill enters only a skills list, resume lines stay in the owner's implied first
    person, and saved keywords land. The presets are the user's, set in the app; no
    tool changes them."""
    stored = _client.get_quick_tailor_profile() or {}
    fields = QuickTailorProfile.model_fields
    return {
        "presets": [
            {"key": key, "on": bool(stored.get(key, field.default)), "means": field.description}
            for key, field in fields.items()
            if key != "instruction"
        ],
        "instruction": str(stored.get("instruction") or ""),
        "persona": _client.get_persona(),
    }


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
    captured in the last 30 days by role category. profile.work_auth_by_country
    holds those yes/no answers for each market the user applies in, keyed by
    market ("UK", not "GB"); profile.work_auth is the home market's set, named by
    work_auth_market and kept for one release; unless the user lives and applies
    in one country, each warning names its country. last_runs maps each automation to
    when its newest run that did not fail finished (UTC ISO; a failed run does not
    count; absent when none has).
    roles is the role catalog as {key, label}. It is the entry point of the
    agentic job-search workflow (playbook: docs/agentic-job-search.md), which
    covers capture, scoring and proposals; applying is outside its scope.
    sync carries enabled and role (home, remote, or null when sync is off).
    applying.answer_level is the Screening answers level (facts, history, queued)."""
    return _client.get_job_search_brief()


@mcp.tool(**_write("Sync Now", destructive=False, idempotent=True, open_world=True))
@_guard
def sync_now() -> Any:
    """Run one sync round on the always-on copy. Returns its outcome
    (ok, transient, needs_person) and per-step counts, or a skip reason.
    Forces a round through the backoff window; an attempt within the last
    30 seconds is skipped with 'Synced moments ago.'. Sync off returns
    \"Sync isn't set up.\"; home returns
    \"This is your laptop's copy; your bot runs the sync.\""""
    return _client.sync_now()


@mcp.tool(**_read("Get Career Context"))
@_guard
def get_career_context(format: Literal["json", "markdown"] = "json") -> Any:
    """Read the user's career record from the Career KB, as format="json" (the default)
    or format="markdown".

    json: `resume`, the approved-points resume view assembled from the profile and the
    non-archived entities, and `memory`, the beyond-the-resume string: identity facts and
    entity notes that don't belong on a resume. `resume` carries approved points only;
    `memory` also includes the profile summary and notes and the non-archived entities'
    notes.

    markdown: the exact portable career.md generated from the current Career KB, as
    deterministic Markdown text, the file the web's career export downloads.

    Intended as grounding for writing about the user's career (LinkedIn posts, outreach
    drafts), optionally beside a base resume for its voice. It never invents facts,
    metrics, employers, or dates; anything absent from it (and from a fetched base resume)
    is not part of the user's recorded career. Neither format carries IDs; the profile
    set's career history tools return the IDs needed to correct anything. Read-only."""
    return _client.get_career_context(format=format)


# ---------- Career KB: read with IDs ----------
@mcp.tool(**_read("List Career Entities"))
@_guard
def kb_list_entities(kind: str | None = None, status: str | None = None) -> Any:
    """List Career KB entities with their IDs (get_career_context returns prose
    with no IDs; this tool returns the IDs needed to edit). Optionally filter by
    kind (experience|project|education|certification|extra) or status
    (ongoing|completed|archived). Each item carries point_count, draft_count and
    approved_count (the bullets a resume can use; retired ones are in point_count only,
    except a bullet combined into another, which is counted nowhere)
    and used_in_bases, the base resumes it is on (archived included, deleted excluded)."""
    return _client.list_kb_entities(kind=kind, status=status)


@mcp.tool(**_read("Get Career Entity"))
@_guard
def kb_get_entity(entity_id: str) -> Any:
    """Full detail for one Career KB entity: dates, notes, its points (each with
    id, text and state), attached documents, and the activity timeline; also
    used_in_bases, the base resumes it is on (archived included, deleted excluded)."""
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


@mcp.tool(**_read("Find Similar Career Points"))
@_guard
def kb_groom_entity(entity_id: str) -> Any:
    """Similar bullets on one Career KB entity, clustered, with a proposed keeper.
    Deterministic and zero LLM calls: the pinned local embedder scores every pair of
    the entity's active points (drafts included, retired and user_cannot_confirm
    excluded) and joins pairs at 0.80 cosine and above, minus pairs the user marked
    "Not the same" at /career. Proposes only; nothing is written. Each cluster
    carries score, keeper_id, members [{id, text, state, origin, provenance,
    usage_count, best_score}] and pairs. The keeper rule is approved over draft,
    then most recently updated, then longest text. compared_wording is false when
    the embedder could not run; clusters is then empty. Acting on a cluster is
    kb_combine_points (one claim in other words: the others become the keeper's
    wordings) or kb_retire_points (a similar but stale one)."""
    return _client.get_kb_groom(entity_id)


# ---------- Career KB: write ----------
# Most tools here mint DRAFT content, kb_ingest_resume included — an agent
# transcribing a resume is not the user approving it. The user-gated state
# writes are kb_approve_points, kb_retire_points and kb_combine_points: each
# records the user's decision about points they have seen and said yes to, and
# kb_approve_points is the single way to approve from MCP. Never state a
# date, employer, credential or metric the user did not give you — a fabricated
# fact written here becomes part of their permanent career record.
@mcp.tool(**_write("Capture Career Notes", destructive=False, idempotent=False, open_world=True))
@_guard
def kb_capture(
    text: str,
    entity_id: str | None = None,
    ctx: Context | None = None,
) -> Any:
    """Capture free-text career news into DRAFT points. Maestro's AI matches it to
    an existing entity or proposes a new one, with the user's API key (with none
    set it returns an error); pass entity_id to force placement. Refused (409)
    when the user's writer setting (get_setup_status) says the agent app writes;
    kb_add_points stores bullets the caller already wrote, with no LLM call.
    Points land as drafts for the user to approve at /career. The text is stored
    as the user's own words and facts; the server does not verify it."""
    return _client.kb_capture(
        text,
        entity_id=entity_id,
        origin_detail=_client_label(ctx),
    )


@mcp.tool(**_write("Add Career Points as Drafts", destructive=False, idempotent=True))
@_guard
def kb_add_points(
    entity_id: str,
    points: KBPoints,
    ctx: Context | None = None,
) -> Any:
    """Add bullets the caller wrote to an existing Career KB entity as DRAFT
    points, with no LLM call (kb_capture with entity_id, minus the model that
    splits and places free text). Drafts appear on no resume and in no career
    export until approved with kb_approve_points (or at /career). The text is
    stored as the user's own words and facts; the server does not verify it.

    Store-time rules: en and em dashes become a hyphen in a range
    ("2020-2023") and a comma elsewhere, and one opening a bullet is dropped.
    Resume text is implied first person:
    a bullet where I, he or she opens a clause, his/her/my opens one or follows
    its verb ("Grew his team"), or the owner's name appears returns 400 naming
    the lines and stores nothing; they/their and pronouns about other people
    are stored. A bullet already on the entity in any state
    (case and spacing ignored), or repeated in the call, is skipped, so a
    repeated call adds nothing; a rephrasing is added as a new draft
    (kb_groom_entity reports similar bullets).

    Returns {entity_id, entity_title, point_ids, skipped}: the new DRAFT point
    ids and the skipped texts. An unknown entity_id is a 404; kb_list_entities
    returns the ids, and kb_create_entity makes a new entity."""
    return _client.kb_add_points(entity_id, points, origin_detail=_client_label(ctx))


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
    delete a point. New text gets the kb_add_points rules: en and em dashes
    become a hyphen or a comma, and a third-person line is a 400 naming it."""
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


@mcp.tool(**_write("Approve Career Points", destructive=False, idempotent=True))
@_guard
def kb_approve_points(point_ids: list[str]) -> Any:
    """Batch-approve Career KB points. Approved points are the only ones that appear on
    composed resumes and the career export; this is the single approval path available over
    MCP, and kb_retire_points retires points. The approval written is the user's decision
    about the listed points; the server does not check that the user reviewed them (a
    convention, not enforcement).

    1-500 ids; repeats collapse to one result row. Per-id results are honest: unknown ids
    return ok=false detail="not found" and the rest still proceed; a failed id fails the
    same way until corrected (kb_list_points returns the current ids).

    Response is {results: [{id, ok, state, detail}], next}. next is a hint
    (null when suppressed or unavailable).
    """
    body = _client.kb_approve_points(point_ids, state="approved")
    results = body.get("results") or [] if isinstance(body, dict) else []
    return {
        "results": results,
        "next": _best_effort_hint(
            lambda: workflow.next_after_bulk_state(
                results,
                requested_state="approved",
                allowed_tools=_active_allowed_tools(),
                hints_enabled=_hints_enabled(),
            )
        ),
    }


@mcp.tool(**_write("Combine Career Points", destructive=False, idempotent=True))
@_guard
def kb_combine_points(keeper_id: str, point_ids: list[str]) -> Any:
    """Fold Career KB points into one: the keeper stays the bullet, and every
    point in point_ids (the others, not the keeper) is retired and recorded as
    one of the keeper's wordings. Resumes that use any of them keep their
    text; combining never edits a resume.
    Reversible from /career (Make its own bullet). The grouping written is the
    user's decision about the listed points; the server does not check that the
    user reviewed them (a convention, not enforcement, the same gate as
    kb_approve_points). Same entity required (400); a retired or
    user_cannot_confirm keeper, a user_cannot_confirm loser, and a loser the
    user stopped (retired but not folded) are refused (400), and so is a keeper
    that is itself folded into another; a loser already folded elsewhere moves
    to this keeper. Returns {keeper, repointed}: the keeper with its
    wordings, and any combined claims the fold moved from a loser onto it. 1-50 ids."""
    return _client.kb_combine_points(keeper_id, point_ids)


@mcp.tool(**_write("Merge Career Items", destructive=True, idempotent=True))
@_guard
def kb_merge_entities(keep_id: str, merge_id: str) -> Any:
    """Fold one Career KB item into another of the same kind, the cure for a duplicate an import
    split off: merge_id goes, keep_id stays. Everything on merge_id moves to keep_id: its
    bullets in every state (approved, drafts, retired, and the wordings folded into a bullet),
    its evidence documents, and its record of which resumes its bullets were copied into.

    keep_id keeps its own title, dates, status and notes. A field keep_id has blank (org,
    start or end date, notes) is filled from merge_id, except the end date of an ongoing item,
    and a detail key keep_id lacks is taken from merge_id. Lost: merge_id's title, its status,
    its creation record, and each value of it where keep_id already holds a different one.
    Bullets are not de-duplicated: one both items carried is there twice afterwards
    (kb_combine_points folds them into one). Resumes are not edited. There is no unmerge.
    The merge written is the user's decision about the two items; the server does not check
    that the user agreed (a convention, not enforcement).

    Refused: the same id twice, items of different kinds, `extra` items from different
    sections, and an archived keep_id (400; an archived merge_id is fine), an unknown id
    (404), and a merge of the same item running at once (409). Returns keep_id's detail,
    kb_get_entity's shape."""
    return _client.kb_merge_entities(keep_id, merge_id)


@mcp.tool(**_write("Retire Career Points", destructive=False, idempotent=True))
@_guard
def kb_retire_points(point_ids: list[str]) -> Any:
    """Batch-retire Career KB points: they stop being offered to resumes and the
    career export; resumes that already use them keep their text. Reversible
    from /career (Use again). The state written is the user's decision about
    the listed points; the server does not check that the user reviewed them
    (a convention, not enforcement, the same gate as kb_approve_points).

    1-500 ids; repeats collapse to one result row. Per-id results are honest:
    unknown ids return ok=false detail="not found" and the rest still proceed.
    Response is {results: [{id, ok, state, detail}], next}; next is a hint
    (null when suppressed or unavailable).
    """
    body = _client.kb_approve_points(point_ids, state="retired")
    results = body.get("results") or [] if isinstance(body, dict) else []
    return {
        "results": results,
        "next": _best_effort_hint(
            lambda: workflow.next_after_bulk_state(
                results,
                requested_state="retired",
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
    (origin=base_sync) for the user to approve at /career. A bullet that
    rephrases an existing point on the same item (0.80 cosine and above) is
    kept as that point's wording, not added as a second point; only a new
    claim lands as a draft. Never edits resumes. Safe to rerun — a second
    call is a no-op when already in sync. compared_wording is false when the
    embedder could not run: a rephrased bullet was then added as new rather
    than kept as a wording (exact text still matches).
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
    argument). role_category is strict: an unknown value 422s naming the
    closest categories, no normalization. An unmatched role_label maps to
    role_category "other" and slug `other`/`other_2`…; display_name never
    affects the slug, which is `base.slug` in the response. Only APPROVED
    points under the selected entities compose —
    points from kb_ingest_resume are DRAFTS and contribute nothing until
    kb_approve_points (or the user, at /career) approves them.
    skills and contact arrive in full from the KB profile regardless of entity
    selection (the KB has no per-entity skill data), so skills may need trimming
    on the resulting base. The
    whole-career summary is dropped unless include_summary, or pass a reviewed
    summary. A selected job or project with no approved point is left out, and
    a 422 "None of the items you picked has approved bullets." means none has any.

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
    def compose() -> dict[str, Any] | None:
        hints, allowed = _hints_enabled(), _active_allowed_tools()
        # Setup status only where the hint could name the form answers: hints on and the
        # write registered. A failed read names nothing and keeps the render hint.
        status = (
            _best_effort_hint(_client.get_setup_status)
            if hints and (allowed is None or "set_autofill_profile" in allowed)
            else None
        )
        return workflow.next_after_base_from_kb(
            base if isinstance(base, dict) else {},
            allowed_tools=allowed,
            hints_enabled=hints,
            setup_status=status,
        )

    return {"base": base, "next": _best_effort_hint(compose)}


@mcp.tool(**_read("Get Autofill Profile"))
@_guard
def get_autofill_profile(application_id: str | None = None, base: str | None = None) -> Any:
    """Read the user's application-form autofill data: `profile` (personal
    contact + address, work-authorization answers (`work_auth`: the job's
    country's, none without one; `work_auth_by_country`: per market key, e.g.
    UK; a question naming a country takes its), preferences like
    salary/notice/relocation, education, `languages` — each a language with
    read/speak/write level Basic/Intermediate/Fluent and separate `native`
    and `fluent` booleans — custom Q&A presets), plus `employment`
    blocks and `skills` from the selected resume when application_id or base is
    given. Response is labeled `source: "profile"` and includes
    `canonical_identity` (`legal_first`, `legal_last`, `preferred`) mapped only
    from stored autofill personal fields; it is the source of truth for form
    identity fields and takes precedence over ATS-parsed values. It is the
    feed the Chrome extension's deterministic fill uses. EEO/demographic answer values
    (`profile.eeo`) are returned ONLY when Profile standing consent is active
    (`eeo_consent.enabled`) and are stripped otherwise; when returned they are
    the user's stored answers, intended for Playwright/agent fill verbatim with
    no inference or model-authored values. `eeo.veteran_status` is no, yes
    or decline: one question, "Are you a veteran?" (a no also answers "not a
    protected veteran"; a yes alone never says which protected class applies,
    so leave a protected-class list to the user). `eeo.gender` is male, female,
    non_binary, self_describe or decline; with self_describe,
    `eeo.gender_self_describe` is the user's own words for a form's
    self-describe box. A form lacking a matching option is left to the user.
    Missing EEO values are completed by the user in Profile or in the browser;
    consented answers are not pasted or re-dictated through chat. A value absent
    here (a county) is not in the profile and is not guessable.
    WOTC, signatures and terms are human-only."""
    return _client.get_autofill_context(application_id=application_id, base=base)


# ---------- profile facts: what Setup and Profile ask for ----------
# Over MCP an agent writes the facts Setup and Profile ask the user, except the AI key and the
# diversity answers. Settings' switches, the consent records and the job-site login stay the
# user's (docs/plans/2026-10-23-mcp-profile-writes-design.md; mcp_server/tests/
# test_profile_write_tools.py pins the settings the client writes).
def _setup_autofill() -> dict[str, Any] | None:
    """Setup's form-answer readiness, read after a landed write: null when the read fails."""
    status = _best_effort_hint(_client.get_setup_status)
    return status.get("autofill") if isinstance(status, dict) else None


def _given(*, refusal: str, **fields: Any) -> dict[str, Any]:
    """The fields a patch write was passed. None of them is refused, not sent back unchanged:
    FastMCP drops an argument a tool does not declare, so a call naming only those (`eeo`)
    reaches here as no change at all."""
    given = {key: value for key, value in fields.items() if value is not None}
    if not given:
        raise ToolError(refusal)
    return given


@mcp.tool(**_write("Update Autofill Profile", destructive=True, idempotent=True))
@_guard
def set_autofill_profile(
    personal: PersonalAnswers | None = None,
    eligibility: EligibilityAnswers | None = None,
    preferences: PreferenceAnswers | None = None,
    work_auth_by_country: WorkPermitsArg = None,
    education: list[EducationEntry] | None = None,
    languages: list[LanguageEntry] | None = None,
    custom: list[SavedAnswer] | None = None,
) -> Any:
    """Save the user's application-form answers: the profile get_autofill_profile reads and
    the Companion fills forms from. Only the sections passed change. Inside personal,
    eligibility, preferences and each country's work-permit answers only the keys passed
    change, and a null removes one; education and languages replace the stored list whole
    (get_autofill_profile returns them). Each custom answer replaces the saved one with the
    same question (case and spacing ignored) and the same only_for and only_for_kind, or is
    added: for an answer held for one company or city, send its only_for and only_for_kind
    as get_autofill_profile shows them, or a second scoped answer is added. A saved answer is
    never removed here, so one the Companion learned meanwhile stays (removing one is the
    user's, in Profile). A work-permit answer is per
    country and a form question without one is asked on that form, never defaulted; setup
    counts the answers of each country in apply_in (set_markets). Diversity (EEO) answers
    have no field here: they and their consent are the user's, in Profile. An unknown
    section, key or market key writes nothing. Returns {profile, setup}: the saved profile
    without eeo, and setup status's form-answer readiness (readiness 0 to 1, groups,
    blocking, work_auth_by_country counts), null when that read fails."""
    changes = _given(
        refusal=(
            "Nothing to save: no section was passed. Diversity (eeo) answers have no field "
            "here; they are the user's, in Profile."
        ),
        personal=personal, eligibility=eligibility, preferences=preferences,
        work_auth_by_country=work_auth_by_country, education=education,
        languages=languages, custom=custom,
    )
    return {"profile": _client.set_autofill_profile(changes), "setup": _setup_autofill()}


@mcp.tool(**_write("Update Job Preferences", destructive=True, idempotent=True))
@_guard
def set_job_preferences(
    favored_roles: list[FavoredRoleInput] | None = None,
    years_experience: Annotated[int | None, Field(ge=0, le=60)] = None,
    employment_types: list[Literal["full_time", "contract", "part_time", "internship"]] | None = None,
    locations: list[str] | None = None,
    remote: Literal["remote", "hybrid", "onsite", "any"] | None = None,
    min_salary: MinSalaryInput | None = None,
    notes: str | None = None,
) -> Any:
    """Save the jobs the user wants, which get_job_search_brief reads and setup counts as
    done once any is set. Only the fields passed change; [] clears a list and "" clears
    notes. favored_roles holds at most 25 roles, duplicates dropped. A role the catalog
    does not know (the refusal names the closest), a currency that is not ISO 4217 or
    more than 25 roles is a 422 that saves nothing. Returns the stored preferences, with
    role_categories derived from favored_roles."""
    return _client.set_job_preferences(_given(
        refusal="Nothing to save: no field was passed.",
        favored_roles=favored_roles, years_experience=years_experience,
        employment_types=employment_types, locations=locations, remote=remote,
        min_salary=min_salary, notes=notes,
    ))


@mcp.tool(**_write("Set Where You Live and Apply", destructive=False, idempotent=True))
@_guard
def set_markets(
    home: MarketKey | None = None,
    apply_in: list[MarketKey] | None = None,
    home_currency: str | None = None,
) -> Any:
    """Save where the user lives and applies. home (a market key, "UK" not "GB") sets the
    date format and, while home_currency is unset, the currency pay is shown in. apply_in
    is every market the user applies in, each asking its own work-permit answers; [] reads
    as home alone, and a market dropped from it keeps its stored answers. home alone leaves
    apply_in as stored. home_currency is ISO 4217; "" follows home again. Only the fields
    passed change, all in one save: a refused field (an unknown currency) writes none of
    them. No field passed reads the current values. Returns {home, apply_in,
    home_currency (the resolved one), setup}: setup is setup status's form-answer readiness,
    null when that read fails."""
    place = _client.set_markets(home=home, apply_in=apply_in, home_currency=home_currency)
    return {**place, "setup": _setup_autofill()}


@mcp.tool(**_write("Update Persona", destructive=True, idempotent=True))
@_guard
def set_persona(text: str) -> Any:
    """Replace the user's persona: their direction, strengths and working style in their
    own words. Every writing prompt (tailoring, application answers, cover letters) reads it
    for tone and emphasis, never as a source of facts. The whole text is replaced; "" clears
    it, and setup counts the step done while it is not empty. The app's own persona draft
    needs Maestro's AI key and has no MCP tool. Returns {key, value}."""
    return _client.set_persona(text)


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


@mcp.tool(**_write("Set Resume Target", destructive=False, idempotent=True))
@_guard
def set_base_resume_identity(
    slug: str,
    display_name: str | None = None,
    role_category: str | None = None,
    role_label: str | None = None,
    countries: list[str] | None = None,
    company: str | None = None,
    focus: str | None = None,
    color_hue: int | None = None,
) -> Any:
    """Set what a base resume is written for. Only the fields passed change.
    `countries` (ISO codes) restricts which jobs the resume is scored and
    recommended for: a job in another country skips it, and a resume sent to
    one is flagged. `role_category`/`role_label` name the role, `company` and
    `focus` are free-text emphasis hints for tailoring (at most 80 characters
    each), and `display_name` renames the resume. `[]` clears countries and
    `""` clears company or focus. `color_hue` (0-359) sets the colour the app
    shows beside the resume's name; it never changes the PDF. An unknown country,
    an over-long value or a hue outside 0-359 is a 422 that saves none of the
    fields. Resume content, versions and the PDF are never touched."""
    return _client.set_base_resume_identity(
        slug,
        display_name=display_name,
        role_category=role_category,
        role_label=role_label,
        countries=countries,
        company=company,
        focus=focus,
        color_hue=color_hue,
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
@mcp.tool(**_write("Edit Tailored Resume", destructive=True, idempotent=False))
@_guard
def edit_application(application_id: str, ops: EditOps) -> Any:
    """INCREMENTAL FIX: apply typed edit ops on top of an existing application's
    CURRENT tailored resume (customized_json), preserving every prior edit.

    Falls back to the base resume only when the application has no customized_json
    yet (nothing to preserve). Suited to refining or retrying a tailored resume
    after inspecting PDF previews — swap a bullet, tweak wording, fix one thing —
    without losing the rest of what's already been tailored and without creating
    duplicate applications.
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


_CLEAR_FIELD = Field(
    description=(
        'Fields to empty: "notes" removes the notes, "referral_id" unlinks the referral contact '
        "(the referral itself is kept). A field given a value in the same call is refused, and "
        "nothing is written."
    )
)


def _clear_is_a_list(value: Any) -> Any:
    """A bare string ("notes") gets a sentence, not pydantic's list_type error."""
    if isinstance(value, str):
        raise ValueError(CLEAR_TAKES_A_LIST)
    return value


@mcp.tool(**_write("Update Application Tracking", destructive=True, idempotent=True))
@_guard
def update_application(
    application_id: str,
    status: str | None = None,
    applied_at: str | None = None,
    notes: str | None = None,
    referral_id: str | None = None,
    clear: Annotated[
        list[Literal["notes", "referral_id"]] | None, BeforeValidator(_clear_is_a_list), _CLEAR_FIELD
    ] = None,
    from_email: bool = False,
    ctx: Context | None = None,
) -> Any:
    """Update an application's tracking fields (status, applied_at, notes, referral_id).

    Only the arguments passed are sent to the backend — the PATCH endpoint is
    driven by which fields were actually set on the request, so an argument left
    out leaves that field untouched. `clear` empties notes or unlinks the
    referral (an explicit null on the request).

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

    Every status change is logged with its date and who made it (this client's
    name). Pass `from_email=True` when you read the change in the user's job
    email (the mail-status automation): the log then says it came from mail.
    """
    return _client.update_application(
        application_id,
        status=status,
        applied_at=applied_at,
        notes=notes,
        referral_id=referral_id,
        clear=clear,
        from_email=from_email,
        origin_detail=_client_label(ctx),
    )


@mcp.tool(**_write("Save Referral Contact", destructive=True, idempotent=False))
@_guard
def save_referral(
    company: str | None = None,
    careers_url: str | None = None,
    contact_name: str | None = None,
    notes: str | None = None,
    referral_id: str | None = None,
) -> Any:
    """Add a referral contact, or edit one when referral_id is given (list_referrals
    has the ids). A referral is a company the user can apply to with someone's
    referral: its careers page, the contact's name and notes. A new referral needs
    company and careers_url (an http or https address); contact_name and notes are
    optional, and each call without referral_id adds another referral. An edit
    changes only the fields passed, and company is optional there: a field left
    out keeps its saved value, and a field passed replaces it (referrals keep no
    history of earlier values). An unknown referral_id is a 404 and nothing is
    written. Returns the saved referral {id, company, careers_url, contact_name,
    notes, applications_count, created_at, updated_at}."""
    return _client.save_referral(
        company,
        careers_url=careers_url,
        contact_name=contact_name,
        notes=notes,
        referral_id=referral_id,
    )


# ---------- apply package ----------
@mcp.tool(**_write("Generate Screening Answers", destructive=False, idempotent=False, open_world=True))
@_guard
def generate_qa_answers(application_id: str, questions: list[str]) -> Any:
    """Maestro's AI writes a batch of screening-question answers for an
    application, with the user's API key (with none set it returns an error).
    `questions` is the complete list of questions to answer in this batch.
    Outreach/cold messages are asked as free-form questions here (e.g. "Write a
    short LinkedIn DM to the hiring manager") — answers are grounded in the
    resume and the application's linked referral contact when one exists.
    Refused (409) when the user's writer setting (get_setup_status) says the
    agent app writes; store_qa_answers stores answers the caller wrote, with no
    LLM call."""
    return _client.generate_qa_answers(application_id, questions)


@mcp.tool(**_write("Store Screening Answers", destructive=True, idempotent=True))
@_guard
def store_qa_answers(
    application_id: str,
    answers: AuthoredAnswers,
    ctx: Context | None = None,
) -> Any:
    """Store screening-question answers the caller wrote for an application,
    with no LLM call (generate_qa_answers has the app's configured model write
    them). One entry per question, shown in the job's Apply step history and in
    list_qa_entries. A question the application already holds (the same words,
    case and spacing ignored) has its answer replaced and the others are added,
    so a repeated call changes nothing. Answers are stored as plain form text,
    as generated ones are: markdown bold, headings, bullet markers and backticks
    are removed, and en and em dashes become a hyphen in a range ("2020-2023")
    and a comma elsewhere, line breaks kept. The text is stored as the user's
    own words; the server does not verify it. An answer that is empty once its
    formatting is removed is a 400 that stores nothing. Returns the stored
    entries [{id, kind, prompt, answer, model_used, created_at}]; model_used
    names the agent."""
    return _client.store_qa_answers(
        application_id, [dict(item) for item in answers], origin_detail=_client_label(ctx)
    )


@mcp.tool(**_write("Generate Cover Letter", destructive=True, idempotent=False, open_world=True))
@_guard
def generate_cover_letter(application_id: str, tone: str) -> Any:
    """Maestro's AI writes a cover letter for an application in the requested
    tone, with the user's API key (with none set it returns an error). This
    replaces the application's prior generated cover-letter entry. Refused (409)
    when the user's writer setting (get_setup_status) says the agent app writes;
    store_cover_letter stores a letter the caller wrote, with no LLM call."""
    return _client.generate_cover_letter(application_id, tone)


@mcp.tool(**_write("Store Cover Letter", destructive=True, idempotent=True))
@_guard
def store_cover_letter(application_id: str, text: str, ctx: Context | None = None) -> Any:
    """Store a cover letter the caller wrote for an application and render its
    PDF, with no LLM call (generate_cover_letter has the app's configured model
    write it). It replaces the application's cover letter and that letter's PDF
    (an application holds one); the new one shows on the job's Apply step and in
    list_qa_entries. The text is stored as the user's own letter; the server does
    not verify its facts. As with a generated letter, en and em dashes become a
    hyphen in a range ("2020-2023") and a comma elsewhere, and one opening a line
    ("— Jane") is dropped; the rest is stored as written, line breaks and
    paragraphs included, up to 20000 characters. The PDF puts the base
    resume's contact block above the letter, in the engine of the application's
    resume template.

    Returns the stored entry {id, application_id, kind, answer, model_used,
    pdf_path, render_note, render_error, created_at}; model_used names the
    agent. render_error non-null means the letter is stored and its PDF could
    not be made (pdf_path is null). render_note is non-null only when a TeX-less
    backend rendered a LaTeX template through a Typst one."""
    return _client.store_cover_letter(application_id, text, origin_detail=_client_label(ctx))


# Immune to the ~2048-char tool-description truncation: lives on the param schema.
_FORMATTING_FIELD = Field(
    description=(
        "Look settings to keep (keep=true), one object of the template knobs: font_size "
        "(10|11|12), side_margins and top_bottom_margin (0.3-1.0 inches), line_spacing (0.9-1.4), "
        "section_spacing (0-14 pt), entry_spacing (0-10 pt), justify and hide_divider (true|false), "
        'bullet_icon ("bullet"|"dash"), header_align ("left"|"center"|"right"), date_format '
        '("verbatim"|"short_month"|"long_month"|"numeric"), education_order ("degree_first"|'
        '"institution_first"), skills_layout ("inline"|"bulleted"), section_order (a list of '
        "summary, experience, projects, extra_sections, skills, education, certifications; the "
        "rest follow in the template's order). It replaces the resume's saved look settings: a "
        "knob left out takes the template's default (on a tailored resume, its base resume's "
        "setting first), and {} clears them. An unknown knob or a value out of range is a 400 and "
        "nothing is kept. get_base_resume returns a base resume's saved formatting and template_id."
    )
)
_KEEP_FIELD = Field(
    description=(
        "True: before rendering, the template_id and/or formatting given are saved on this base "
        "resume or tailored resume, so its later renders use them, after an edit too; template_id "
        "must name a ready template. False (default): template_id is a one-off for this render, "
        "the saved design is unchanged, and formatting is refused."
    )
)


@mcp.tool(**_write("Render Resume PDF", destructive=False, idempotent=True))
@_guard
def render_pdf(
    target_type: Literal["base_resume", "application"],
    target_id: str,
    template_id: str | None = None,
    formatting: Annotated[dict | None, _FORMATTING_FIELD] = None,
    keep: Annotated[bool, _KEEP_FIELD] = False,
) -> Any:
    """Render a PDF. target_type is 'base_resume' (target_id=slug) or 'application'
    (target_id=application id). Optional template_id selects a template (either
    engine; must be 'ready'; omit for the default). Response reports
    resolved_template_id / resolved_engine (the template actually used);
    template_fallback=true only when an explicit template_id was passed and the
    resolved id differs — a substitution of the persisted choice is reported
    by render_note, never by the flag. render_note is non-null only when the
    backend has no TeX and a LaTeX template was rendered through a Typst
    template instead; it names both. Returns the render result incl.
    pdf_path (an application render also has copy_path: where the user finds the PDF
    in their resumes folder, null when off), plus a `next` key: for an 'application' render this is the terminal
    apply-readiness hint (autofill_ready, incomplete/blocking groups, a conditional
    browser-handoff offer); for a 'base_resume' render it is always null — a
    base-resume preview isn't part of the score->tailor->render arc, so there is
    nothing to offer.

    Without keep, template_id is a one-off and the saved design is unchanged.
    With keep=true the template_id and/or formatting are saved on the resume
    first, its later renders use them, and the response adds kept
    {template_id, formatting}: what the resume now keeps."""
    if target_type not in ("base_resume", "application"):
        raise ToolError("target_type must be 'base_resume' or 'application'")
    with_kept = _kept_design(target_type, target_id, template_id, formatting, keep)
    render = _client.render_base_resume if target_type == "base_resume" else _client.render_application
    try:
        result = render(target_id, template_id=template_id)
    except BackendError as exc:
        if not with_kept:
            raise
        # The save landed first: a failed render must not read as "nothing happened".
        raise ToolError(f"{exc} The design was kept before this render: {with_kept['kept']}.") from exc
    if target_type == "base_resume":
        return {**result, "next": None, **with_kept}

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

    return {**result, "next": _best_effort_hint(compose), **with_kept}


def _kept_design(
    target_type: str, target_id: str, template_id: str | None, formatting: dict | None, keep: bool
) -> dict[str, Any]:
    """render_pdf's keep, before it renders: {} without keep (where formatting is refused), else the
    design saved and {"kept": what the resume now keeps}. A template that is not ready is refused
    here: the render would quietly fall back to the default template, and every later render
    with it."""
    if not keep:
        if formatting is not None:
            raise ToolError(
                "formatting is saved on the resume, so it takes keep=true; a one-off render takes "
                "template_id only."
            )
        return {}
    if template_id is None and formatting is None:
        raise ToolError("keep=true keeps a template_id, formatting or both; neither was given.")
    if template_id is not None:
        status = (_client.get_template(template_id) or {}).get("status")
        if status != "ready":
            raise ToolError(
                f"Template {template_id!r} is {status or 'not ready'}; only a ready template is kept."
            )
    saved = _client.keep_design(target_type, target_id, template_id=template_id, formatting=formatting)
    return {"kept": {"template_id": saved.get("template_id"), "formatting": saved.get("formatting")}}


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


_DOCUMENT_FIELD = Field(
    description=(
        '"resume" (default): the tailored resume\'s PDF. "cover_letter": the PDF of the cover '
        "letter stored for the application (store_cover_letter or generate_cover_letter), rendered "
        "first when it has none, staged in the same folder under its own file name, so the two "
        "copies sit side by side. With no cover letter stored the call is refused and nothing is "
        "staged."
    )
)


@mcp.tool(**_write("Stage PDF for Upload", destructive=False, idempotent=True))
@_guard
def prepare_application_pdf_upload(
    application_id: str,
    document: Annotated[Literal["resume", "cover_letter"], _DOCUMENT_FIELD] = "resume",
) -> Any:
    """Stage a disposable copy of an application's canonical rendered PDF for
    direct Playwright upload: its tailored resume by default, or its cover letter
    (document). If the PDF has not been rendered, render it and
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
    return _client.prepare_application_pdf_upload(application_id, document=document)


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
# Immune to the ~2048-char tool-description truncation: lives on the param schema.
_EXPLORE_VIEW_FIELD = Field(
    description=(
        "top_skills: the most in-demand skills across the stored JDs, as {meta, top, rest}; "
        "meta.total_jobs counts the jobs read. heatmap: skill demand by role category, one row "
        "per skill and role with pct_jobs, the share of that role's jobs, and count of `of`, "
        "the role's jobs. role_mix: jobs by role category per week; every week from the first "
        "to the last has a row for every role, with count 0 where the role had no jobs. "
        "fit_distribution: how each base resume's match scores (deterministic engine) spread "
        "across jobs in five buckets; display_name is the resume's own name (null for a slug "
        "with no row), and the slug is an internal identifier. ats_over_time: the average match "
        "score per week, split by phase (base vs tailored) and role category. tailoring_lift: "
        "how much tailoring lifts the match score (base to tailored), averaged per role "
        "category, plus an overall row."
    )
)
ExploreViewName = Literal[tuple(EXPLORE_VIEWS)]


@mcp.tool(**_read("Search Trends"))
@_guard
def explore_trends(
    view: Annotated[ExploreViewName, _EXPLORE_VIEW_FIELD],
    role_category: str | None = None,
    level: str | None = None,
    employment_type: str | None = None,
    limit: Annotated[int | None, Field(ge=1, le=100)] = None,
) -> Any:
    """The saved jobs and their match scores as one chart's rows, one view per call: top_skills,
    heatmap, role_mix, fit_distribution, ats_over_time or tailoring_lift (what each returns is on
    `view`). role_category, level and employment_type filter the jobs for every view but
    fit_distribution; limit (1-100) caps the skills top_skills and heatmap return. A filter or limit the view does not take is refused, and nothing is read.
    Skills that recur as gaps are explore_gap_frequency."""
    takes = EXPLORE_VIEWS[view]
    if not takes.filters and any(v is not None for v in (role_category, level, employment_type)):
        raise ToolError(f"{view} takes no filters")
    if not takes.limit and limit is not None:
        raise ToolError(f"{view} takes no limit")
    return _client.explore_trends(
        view, role_category=role_category, level=level, employment_type=employment_type,
        limit=limit,
    )


@mcp.tool(**_read("Recurring Skill Gaps"))
@_guard
def explore_gap_frequency(
    role_category: str | None = None,
    level: str | None = None,
    employment_type: str | None = None,
    limit: int | None = None,
) -> Any:
    """Skills that recur as gaps across saved JDs (best-scoring base resume vs JD,
    before tailoring), ranked by how many jobs want them and their potential match score
    gain. This is RECURRING DEMAND, not a "you lack this" or learn-next list:
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
    (`base_resume_name`) and the stored score (`ats_score`, null when unscored).
    Use get_application(id) for the full record and compare_ats for scores."""
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
    """Deterministic hybrid match score (no LLM): deterministic lexical layers +
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
    hint (null when suppressed or unavailable): in a set with the tailoring tools,
    a gap analysis of the recommended base, filled from the saved presets or
    walked by hand.

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
    # exactly one thing — the presets option's `detail` — so fetching it with hints
    # off, or under a profile that never registers create_tailoring_session (hunt),
    # is a round-trip whose result is discarded. As keyword ARGUMENTS both reads would
    # be evaluated unconditionally, which is the trap this avoids: a twenty-posting
    # hunt loop would have paid 20 wasted calls even with hints switched off.
    def compose() -> dict[str, Any] | None:
        allowed = _active_allowed_tools()
        hints_enabled = _hints_enabled()
        show_presets = hints_enabled and (allowed is None or "create_tailoring_session" in allowed)
        return workflow.next_after_scores(
            recommendation,
            job_id=job_id,
            quick_profile=_client.get_quick_tailor_profile() if show_presets else {},
            allowed_tools=allowed,
            hints_enabled=hints_enabled,
        )

    return {
        "scores": scores,
        "recommendation": recommendation,
        **countries,
        "next": _best_effort_hint(compose),
    }


@mcp.tool(**_read("Compare Match Scores"))
@_guard
def compare_ats(application_id: str) -> Any:
    """Before/after match score comparison for an application: composite and per-layer deltas
    plus a per-skill diff (absent→matched, skills-list-only→dual, decayed→recent).
    Computes any missing phase row on demand."""
    return _client.compare_ats(application_id)


@mcp.tool(**_write("Start Tailoring Session", destructive=True, idempotent=False, open_world=True))
@_guard
def create_tailoring_session(
    job_id: str, base_resume: str, enrich: bool = False, use_presets: UsePresets = False
) -> Any:
    """Start the gap-analysis tailoring workflow for a job + base resume.

    Calling again for the same job+base SUPERSEDES the open session (saved
    resolutions become unreachable); list_tailoring_sessions shows existing
    sessions. A failing fatal health gate on the base is a 409.

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

    use_presets=True also fills every gap the user's Quick tailor presets decide
    (get_tailoring_options explains them), with no AI; undecided gaps are saved
    as skip. When that fill fails, the error names the session it started.

    enrich=True has Maestro's AI add display-only explanations to each gap (one
    fast-model call with the user's key; no score, gap or career-history match
    changes). Refused (409) when the user's writer setting (get_setup_status) says
    the agent app writes: run it without enrich, the default, which calls no model.

    Response is the session (filled, with use_presets) plus a `next` hint (null
    when hints are off or unavailable). `base_anchors` are the base's emphasis
    hints (countries, role, company, focus), not evidence; the anchor company is
    the resume's own target, not necessarily this job's employer."""
    session = _client.create_tailoring_session(job_id, base_resume, enrich=enrich)
    if not use_presets:
        return {**session, "next": _session_hint(session)}
    try:
        filled = _client.apply_quick_tailor_profile(session["id"])
    except BackendError as exc:
        # The session exists now: name it, so a retry neither loses it nor
        # supersedes it unknowingly (audit 6.6).
        raise ToolError(
            f"The gap analysis {session['id']} was started, but filling it from the presets "
            f"failed: {str(exc).rstrip('.')}. Call create_tailoring_session again (it replaces it)."
        ) from exc

    def compose() -> dict[str, Any] | None:
        settings = _client.get_mcp_workflow_settings()
        if not settings.get("hints", True):
            return None
        profile = _client.get_quick_tailor_profile()
        return workflow.next_after_session(
            filled,
            allowed_tools=_active_allowed_tools(),
            hints_enabled=True,
            instruction=_instruction_from_profile(profile),
            writer=_writer(settings),
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
    company is the resume's own target, not necessarily this job's employer."""
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
    ops: TailorOps = None,
    no_new_text: NoNewText = False,
) -> Any:
    """Run the tailor pipeline for a session: saved resolutions -> edit ops ->
    the job's tailored application, scored and rendered.

    Three ways to produce the edits:
    - ops omitted: Maestro's AI writes them, only when the user's writer setting
      (get_setup_status) is Maestro's AI; otherwise refused (409).
    - ops: the caller's own typed edit ops, the shapes edit_application takes
      (its ops schema lists each kind), carrying only the changed fields; no
      model call.
    - no_new_text=True: no new wording and no model call, under either setting.
    The ops and no_new_text parameters say which saved answers the server
    applies; answers_left_to_ops lists the ones that need wording.

    Caller-supplied ops are applied as authored: the server validates structure
    only, so nothing gates fabricated skills, experience, metrics, or dates. A
    skill the candidate cannot evidence goes only in the skills list
    (add_skill_item), not in a bullet; the compare view audits any edit beyond
    the saved resolutions. Resume text is implied first person: an edited line
    in I/he/she voice or naming the owner is a 400 naming the lines.

    Optional user_prompt adds free-form tailoring guidance. Writes the job's ONE
    application from the base plus the edits: it rebuilds the draft (version
    history keeps the old draft) and renders its PDF; pdf_ready is false when
    that render failed. compare (before/after match score deltas) may be null
    with compare_error set: the tailor still succeeded. unbacked_skills names
    missing skills this tailor put on the resume that career history does not
    back. kb_writeback_skips derives from each user_input resolution's STORED
    placement_target from resolve_gaps, not from the ops, so ops that disagree
    with the stored target produce a spurious wrong_section skip. `next` (null
    when off or unavailable): render_pdf if pdf_ready is false, else apply
    readiness; no_new_text's answers left come first."""
    result = _client.tailor_session(
        tailoring_session_id, user_prompt=user_prompt, ops=ops, no_new_text=no_new_text
    )
    application_id = (result.get("session") or {}).get("application_id")
    pdf_ready = bool(result.get("pdf_ready", False))

    # With the PDF made the hint carries apply readiness, as render_pdf's does;
    # setup status (one more request) is read only then, and only with hints on.
    def compose() -> dict[str, Any] | None:
        if not _hints_enabled():
            return None
        return workflow.next_after_tailor(
            application_id=application_id,
            allowed_tools=_active_allowed_tools(),
            hints_enabled=True,
            pdf_ready=pdf_ready,
            setup_status=_client.get_setup_status() if pdf_ready else None,
            keywords_added=result.get("keywords_added") or [],
            answers_left_to_ops=result.get("answers_left_to_ops") or [],
            no_new_text=no_new_text,
        )

    next_hint = _best_effort_hint(compose) if application_id else None
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
    pending_review. application_id may be omitted; the backend then links the job's
    application on fit.chosen_base when there is one, else the job's one application
    (409 only when the job has no application); an automatic link sets fit.chosen_base
    to the linked application's resume."""
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
    """Compact final-review bundle: job summary, chosen base/match score delta, PDF readiness,
    QA answers, blocked/manual items, evidence manifest. `approval_recorded` is the user's
    yes on this proposal; `eeo.consent_recorded` is their standing EEO consent (no values).
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
    """Stores one finished automation run. The Automations page lists the newest run of each
    automation under Recent runs (its counts, digest and job links) and each card shows when its
    automation last ran; the Agent inbox says so when the run proposed jobs. automation is the card id (mail-status, job-hunt,
    referral-pages, tailor-run, apply-session) or a custom automation's own name, 40 characters
    at most. outcome: ok, partial (some of the work failed) or failed (none of it was done).
    The newest 200 runs are kept. Returns the stored run."""
    return _client.record_run(automation, outcome, report, origin_detail=_client_label(ctx))


@mcp.tool(**_write("Record Application Consent", destructive=True, idempotent=False))
@_guard
def record_consent(
    proposal_id: str,
    action: Literal["approved", "rejected"],
    channel: Literal["chat", "slack", "mcp", "auto"],
    note: str | None = None,
) -> Any:
    """Record the user's explicit approve/reject decision for this proposal as an
    append-only audit row (`channel` = where the user said it, `note` = their
    words). The stored decision is attributed to the user; the server cannot
    verify it came from them. `approved` is accepted only when the proposal has
    final_review evidence, the linked application is not already applied, and a
    daily-cap slot is free, and it reserves that slot. `rejected` is a
    posting-scoped decline and is terminal. `auto` is the agent's own yes in full
    automation mode: accepted only for `approved` and only while full automation is on."""
    consent = {"channel": channel, "note": note}
    return _client.transition_proposal(proposal_id, action, consent=consent)


@mcp.tool(**_write("Get Job-Site Login", destructive=False, idempotent=True))
@_guard
def get_job_site_login(proposal_id: str, ctx: Context | None = None) -> Any:
    """The email and password the user saved for job-site accounts, for creating an account or
    signing in on this proposal's application site. Available only while full automation is on
    and only for a queued or approved proposal; each call is recorded (never the value). The
    value passes through the agent's AI provider, which is why it is a password the user keeps
    for job sites alone. Returns {email, password}."""
    return _client.get_job_site_login(proposal_id, origin_detail=_client_label(ctx))


# Immune to the ~2048-char tool-description truncation: lives on the param schema.
_EVIDENCE_FILE_FIELD = Field(
    description=(
        "An absolute path to an existing PNG or JPEG on this machine, typically as a browser "
        "tool reports it (Playwright MCP saves to its --output-dir; with the standard setup "
        "that is under the repo's .playwright-mcp/ tree, e.g. "
        "/Users/<user>/Projects/maestro-career-studio/.playwright-mcp/<name>.png); a relative "
        "or ~ path is resolved against this server's working directory. When this server runs "
        "inside the backend container, a host path with a `.playwright-mcp/` segment is read "
        "from the container's mount of that tree (paths that leave the tree are refused). "
        "PNG/JPEG only, 5 MB max."
    )
)


@mcp.tool(**_write("Attach Evidence", destructive=False, idempotent=False))
@_guard
def attach_evidence(
    proposal_id: str,
    step: int,
    label: str,
    kind: Literal["step", "final_review", "submission_receipt"] = "step",
    image_base64: str | None = None,
    file_path: Annotated[str | None, _EVIDENCE_FILE_FIELD] = None,
) -> Any:
    """Attach an evidence image to a proposal, from exactly one of image_base64 (the image,
    base64, supplied inline in the call) or file_path (an image file already on this
    machine's disk, e.g. a browser tool's saved screenshot; its bytes are read and uploaded
    server-side, so they never enter the model context). Both or neither is refused, and
    nothing is uploaded. kind must be step | final_review | submission_receipt."""
    given = [name for name, value in (("image_base64", image_base64), ("file_path", file_path))
             if value is not None]
    if len(given) != 1:
        raise ToolError(
            "attach_evidence takes exactly one of image_base64 or file_path, and got "
            + ("both." if given else "neither.")
        )
    if file_path is not None:
        return _client.attach_evidence_file(proposal_id, step, label, file_path, kind=kind)
    return _client.attach_evidence(proposal_id, step, label, image_base64, kind=kind)


@mcp.tool(**_write("Mark Application Submitted", destructive=True, idempotent=False))
@_guard
def mark_submitted(
    proposal_id: str,
    user_attested: bool = False,
    channel: Literal["chat", "slack", "mcp", "auto"] = "chat",
    note: str | None = None,
    ctx: Context | None = None,
) -> Any:
    """Flip an approved proposal to submitted (terminal; links the application to
    applied). Requires submission_receipt evidence, or `user_attested=True`,
    which records the user's own statement that they submitted it (or that a
    submission_uncertain proposal went through, e.g. a confirmation email or
    portal check) as an attested consent event with their words in `note`.
    `user_attested` substitutes for receipt evidence and the server does not
    verify it; it is the user's attestation, not the caller's. In full automation mode,
    channel `auto` records the agent's own word that the application went through, with
    `note` naming what confirmed it (the confirmation page or a confirmation email);
    no receipt is needed, and it is accepted only while full automation is on."""
    origin_detail = _client_label(ctx)  # the application's status log names this client
    if user_attested or channel == "auto":
        return _client.transition_proposal(
            proposal_id, "submitted", attested=True,
            consent={"channel": channel, "note": note}, origin_detail=origin_detail,
        )
    return _client.transition_proposal(proposal_id, "submitted", origin_detail=origin_detail)


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
    """Report execution failure. From pending_review/accepted/approved, transitions to needs_human
    (resumable). reason='submission_uncertain' (for a submit click that could not be
    verified) moves the proposal to the terminal submission_uncertain status:
    resume_proposal is refused for it. The user's attestation, or the agent's
    (channel auto) in full automation mode, through mark_submitted moves it on."""
    return _client.report_failure(proposal_id, reason=reason)


def _set_tools(profile: str | None = None, registry: _ServedMCP | None = None) -> list[Tool]:
    """The registry's Tool objects a client of `profile` (default: the env profile) can see, in
    registration order. `registry` defaults to `mcp`; a test passes its own."""
    allow = allowed_tools(profile)
    tools = (mcp if registry is None else registry)._tool_manager.list_tools()
    return [t for t in tools if allow is None or t.name in allow]


def list_registered_tool_names(profile: str | None = None) -> list[str]:
    """Tool names a client of `profile` (default: the env profile) can see."""
    return [t.name for t in _set_tools(profile)]


def build_set(
    profile: str | None = None,
    cls: type[_ServedMCP] = _ServedMCP,
    registry: _ServedMCP | None = None,
) -> _ServedMCP:
    """A server holding `profile`'s tools (default: the env profile) and instructions. The set is
    a snapshot of the registry (default `mcp`) at build time and holds the registry's own Tool
    objects, so a set must never change a shared Tool in place."""
    registry = mcp if registry is None else registry
    active = get_profile(profile)
    tools = _set_tools(active, registry)
    instructions = orientation.instructions_for(active)
    served = cls(registry.name, instructions=instructions, tools=tools, profile=active)
    _lowlevel(served).version = os.environ.get("APP_VERSION", "dev")
    return served


def main() -> None:
    http_client.repair_proxy_env()
    build_set().run()  # stdio: this process serves one set


if __name__ == "__main__":
    main()
