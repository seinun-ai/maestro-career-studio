from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.ats_score import AtsCompareRead
from app.schemas.resume_edit import ResumeEdit


class ResolutionItem(BaseModel):
    gap_id: str
    action: Literal[
        "add_keyword",
        "user_input",
        "attach_project",
        "skip",
        "enable_entry",
        "port_kb_point",
        # "I can't confirm this": skip-for-the-document plus a durable
        # user_cannot_confirm KB record so the claim is never re-asked and
        # never laundered into evidence (SYSTEM.md inv-provenance-no-decay).
        "cannot_confirm",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)


class ResolutionsPatch(BaseModel):
    resolutions: list[ResolutionItem]
    # False: merge by gap_id (MCP incremental flow). True: the list is the whole
    # truth — omitted gap_ids are deleted (UI autosave sends the full list).
    replace: bool = False
    # Optional "how should this be tailored?" note. None = leave the stored value
    # untouched; "" clears it (see save_resolutions).
    user_prompt: str | None = None


class TailoringSessionCreate(BaseModel):
    job_id: UUID
    base_resume: str
    enrich: bool = True


class TailoringSessionRead(BaseModel):
    id: UUID
    job_id: UUID
    base_resume: str
    status: str
    # gap dicts are shape-variant (skill vs title/gate/format): plain passthrough
    gaps_json: dict[str, Any]
    resolutions_json: list[dict[str, Any]]
    user_prompt: str | None = None
    application_id: UUID | None = None
    base_ats_score_id: UUID | None = None
    # Transient, non-persisted warning set by create_session when the base resume's
    # health score is under 55 (a failing fatal gate blocks instead). Defaults to
    # None for the list/get endpoints, where the ORM row carries no such attribute.
    health_warning: str | None = None
    # Transient (GET only, open sessions): why this session is stale, or None.
    stale_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TailorRequest(BaseModel):
    user_prompt: str | None = None
    # Caller-supplied typed edit ops (Claude via MCP). When present, the backend
    # applies them directly and skips its own LLM pass; validated here at the API
    # boundary against the same ResumeEdit union the editor endpoints use.
    ops: list[ResumeEdit] | None = None
    # Fill every UNRESOLVED gap from the saved quick-tailor profile, then tailor
    # (the gap page's "Quick tailor" button). The fill runs in the router BEFORE
    # tailor(), because save_resolutions commits and tailor()'s transaction
    # boundary is score_target. Existing resolutions always win.
    apply_profile: bool = False


class KBWritebackSkip(BaseModel):
    """One substantive gap answer the flywheel could NOT save to the Career KB,
    with why — returned on the tailor response so the drop is never silent."""

    gap_id: str
    # The gap's JD skill / requirement line, for the UI note.
    skill: str | None = None
    reason: Literal["too_short", "wrong_section", "no_entity_match", "duplicate"]
    # Human sentence composed server-side (e.g. "no Career KB entity titled
    # 'Acme Corp'") so every surface words the drop the same way.
    detail: str


class TailorResponse(BaseModel):
    session: TailoringSessionRead
    # None when the post-tailor compare failed (e.g. version mismatch): the
    # tailoring itself succeeded — compare_error says how to recover.
    compare: AtsCompareRead | None = None
    compare_error: str | None = None
    # False when the post-tailor render failed. Named and shaped like
    # QuickTailorOutcome.pdf_ready deliberately: the one-shot path and this one
    # are the same pipeline, so they report the same fact the same way. The
    # failure detail lands on `application.render_error`, which the studio reads.
    pdf_ready: bool = True
    # Gap answers the KB write-back skipped, with reasons (Phase C Task 11):
    # rendered as a quiet, non-blocking note so flywheel drops are never silent.
    kb_writeback_skips: list[KBWritebackSkip] = Field(default_factory=list)
