"""Workflow composition for the MCP surface: deterministic base ranking and the
next-step hint envelope.

Pure functions over client responses — no httpx, no DB, no LLM. This is a
deliberate exception to SYSTEM.md §7's "thin wrappers over REST": the sequence
has to live somewhere, and the alternative (server `instructions=`) is surfaced
inconsistently across clients. Keeping it pure is what makes it testable under
mcp_server/tests, which never opens a database.
"""
from __future__ import annotations

from typing import Any, Literal

# Who writes for agent apps: the saved setting's two values (app/schemas/mcp_workflow.py's
# Writer; a test pins the pair). server._writer turns the stored setting into one of them.
Writer = Literal["agent", "maestro"]

# Below this composite gap the two bases are not meaningfully different, so the
# agent must present a CHOICE rather than a verdict. Deliberately NOT
# auto_apply.auto_pick_margin: that setting means "pick without asking" in the
# hunt lane, and one saved setting must not come to mean two things (§4).
CLOSE_CALL_MARGIN = 3.0

MAX_REASONS = 3

# The ONLY keys in subscores_json that are score layers — the ones the composite
# is a weighted sum of (services/ats/engine.py: `sum(subscores[k] * weights[k]
# for k in cfg.weights["composite_weights"])`). subscores_json also carries
# numeric DIAGNOSTICS that are not points: coverage_ratio,
# jd_skills_matched_count, jd_skills_extracted_count. Filtering on
# isinstance(value, float) admits those too, and a live run then reported
# "jd_skills_matched_count +4.0" as a reason one base beat another — a COUNT
# difference narrated to the user as a scoring margin. Unit fixtures used
# invented layer names, so only a real score exposed it.
# test_score_layers_match_the_engines_composite_weights pins this against the
# engine's own weights so a new layer cannot silently go unreported.
SCORE_LAYERS = frozenset(
    {"keyword", "placement_recency", "semantic_fit", "title", "format"}
)


def rank_bases(scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Order base-resume score rows best-first and explain the lead.

    Ties break on slug so the same input always yields the same pick — two
    MCP sessions given identical scores must recommend the same base; only
    the agent's prose is allowed to differ.

    coverage_warning is read off the winning (recommended) row only. It is
    NOT purely a JD-parse-failure signal that is guaranteed identical across
    every row — the low-coverage threshold in
    services/ats/engine._calc_coverage_signal compares each resume's own
    matched-skill ratio, so two bases scored against the same job CAN
    disagree (one resume's evidence clears the threshold, another's does
    not). What the caller needs is "should I trust the score I'm about to
    recommend", which is answered by the recommended row's own warning, not
    by some other row's.
    """
    rows = [s for s in scores if s.get("target_type") == "base_resume"]
    ordered = sorted(
        rows,
        key=lambda s: (-_number(s.get("composite")), str(s.get("target_id") or "")),
    )
    order = [str(s.get("target_id") or "") for s in ordered]
    if not ordered:
        return {
            "order": [],
            "recommended": None,
            "margin": None,
            "close_call": False,
            "reasons": [],
            "coverage_warning": None,
        }

    top = ordered[0]
    runner = ordered[1] if len(ordered) > 1 else None
    margin = (
        _number(top.get("composite")) - _number(runner.get("composite"))
        if runner is not None
        else None
    )
    return {
        "order": order,
        "recommended": str(top.get("target_id") or ""),
        "margin": margin,
        "close_call": margin is not None and margin < CLOSE_CALL_MARGIN,
        "reasons": _lead_layers(top, runner),
        "coverage_warning": top.get("coverage_warning") or None,
    }


def _number(value: Any) -> float:
    """Coerce a composite to float, treating garbage as the worst possible
    score rather than raising.

    A malformed row still needs to sort SOMEWHERE — raising here would take
    down the ranking for every other (valid) base in the same call, and the
    caller has no row-level try/except to fall back on. Sorting it last is
    the least-surprising failure mode: a corrupt row never outranks a good
    one, and it is still visible in `order` for whoever wants to investigate,
    instead of vanishing silently.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _lead_layers(top: dict[str, Any], runner: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The layers the winner actually wins on — only positive deltas, biggest first."""
    if runner is None:
        return []
    top_sub = top.get("subscores_json") or {}
    runner_sub = runner.get("subscores_json") or {}
    deltas = [
        {"layer": layer, "delta": _number(value) - _number(runner_sub.get(layer))}
        for layer, value in top_sub.items()
        if layer in SCORE_LAYERS and isinstance(value, (int, float)) and layer in runner_sub
    ]
    positive = [d for d in deltas if d["delta"] > 0]
    positive.sort(key=lambda d: (-d["delta"], d["layer"]))
    return positive[:MAX_REASONS]


# ---- next-step hint envelope ------------------------------------------------
#
# Every wrapped tool response gets a "next" key shaped like:
#   {state, blocking, offer, ask_user, options, call}
# `offer` is non-blocking prose describing the next steps that exist;
# `ask_user` is the pending decision, phrased as a question, which belongs
# mid-arc after the user has already committed to tailoring; `call` names the
# single next tool when there is no choice to make.
#
# The prose DESCRIBES state and what each available tool does or records. It
# does not address the calling model: no "tell the user", "never", "check
# before", "safe to ignore". Tool results are data, and the client decides what
# to do with them. Every tool name in the prose is derived from the options (or
# the allowlist) that survived profile filtering, so prose cannot name a tool
# the active profile did not register.


def _suppressed(hints_enabled: bool, brief: bool = False) -> bool:
    """brief is checked by the CALLER before any settings read; this is the
    belt-and-braces gate. The user switch is the master: off means no hint is
    ever composed, whatever the agent asked for."""
    return not hints_enabled or brief


def _visible(options: list[dict[str, Any]], allowed_tools: "frozenset[str] | None") -> list[dict[str, Any]]:
    """A hint must never name a tool the active profile did not register — the
    hunt profile carries score_ats but no tailoring tools, so an unfiltered
    offer would send that session after something that is not there."""
    if allowed_tools is None:
        return options
    return [o for o in options if o["tool"] in allowed_tools]


def _registered(tool: str, allowed_tools: "frozenset[str] | None") -> bool:
    """Whether prose may name `tool` — the same test `_visible` applies to
    options, for sentences that mention a tool without offering it."""
    return allowed_tools is None or tool in allowed_tools


def _listed(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])}, or {parts[-1]}"


def _offer_from_options(
    options: list[dict[str, Any]],
    phrases: dict[str, str],
    *,
    prefix: str = "",
    suffix: str = "",
) -> str | None:
    """Prose assembled from the options that actually survived `_visible`.

    A hand-written offer string drifts the moment a profile filters an option
    out, or a branch suppresses one — the hint then names a tool this session
    does not have. Two options on one tool share its phrase, said once. None
    when nothing survived."""
    parts = list(dict.fromkeys(phrases[o["tool"]] for o in options if o["tool"] in phrases))
    if not parts:
        return None
    return " ".join(
        x for x in (prefix, f"Available next steps: {_listed(parts)}.", suffix) if x
    )


def next_after_scores(
    ranking: dict[str, Any],
    *,
    job_id: str,
    quick_profile: dict[str, Any],
    allowed_tools: "frozenset[str] | None",
    hints_enabled: bool,
    brief: bool = False,
) -> dict[str, Any] | None:
    """Compose the hint that follows score_ats.

    NON-BLOCKING by construction: mass JD capture scores twenty postings in a
    triage loop, and a question on every one of them would derail the batch.
    So this is the one hint that never sets `ask_user` — only a non-blocking
    `offer` that lists what is available.

    The presets option (create_tailoring_session with use_presets) embeds the
    caller's resolved quick-tailor profile as `detail` (D3 in the design doc)
    rather than making the agent round-trip for it — a separate read the agent
    would likely skip, leaving the mode choice vague.
    """
    if _suppressed(hints_enabled, brief):
        return None
    recommended = ranking.get("recommended")
    if recommended is None:
        # Nothing scored (e.g. no active base resumes yet) — there is no base
        # to offer tailoring against, so there is nothing to say either.
        return None

    options = _visible(
        [
            {
                "label": f"Tailor {recommended} with the saved presets",
                "tool": "create_tailoring_session",
                "args": {"job_id": job_id, "base_resume": recommended, "use_presets": True},
                "detail": dict(quick_profile),
            },
            {
                "label": f"Start a custom tailoring session against {recommended}",
                "tool": "create_tailoring_session",
                "args": {"job_id": job_id, "base_resume": recommended, "enrich": False},
                "detail": None,
            },
        ],
        allowed_tools,
    )
    offer = _offer_from_options(
        options,
        {
            "create_tailoring_session": (
                "create_tailoring_session, with use_presets (fills the gaps from the saved "
                "presets) or without it (gap walkthrough)"
            ),
        },
        prefix=f"Top-ranked base for this job: {recommended}.",
    )
    return {
        "state": "bases_scored",
        "blocking": False,
        "offer": offer,
        "ask_user": None,
        "options": options,
        "call": None,
    }


def next_after_session(
    session: dict[str, Any],
    *,
    allowed_tools: "frozenset[str] | None",
    hints_enabled: bool,
    brief: bool = False,
    instruction: str | None = None,
    writer: Writer = "agent",
) -> dict[str, Any] | None:
    """Compose the hint that follows create_tailoring_session (with or without
    use_presets' fill) or resolve_gaps — each returns a session in this shape.

    `writer` is the user's saved choice of who writes for agent apps ("agent",
    the default, or "maestro"). It changes what the tailor option says, never
    its args: with the agent app writing, tailor_session takes the agent's ops,
    or no_new_text for only what needs no wording (Maestro's AI is refused
    there); with Maestro's AI writing, ops omitted has it write the edits.

    The deterministic KB/wording autos (Task 1's hoist) mean resolutions_json
    can already be partly populated even on a fresh enrich=False session, and
    the use_presets fill can resolve every gap outright. So the real
    branch point is not "which call produced this session" but "are there
    still unresolved gaps" — computed here from gaps_json vs resolutions_json
    rather than trusted from a caller-supplied flag, so a caller can't get
    this wrong by mislabeling which path it came from.

    `instruction` pays the standing-instruction debt the MCP presets fill
    owes: POST .../apply-profile deliberately discards the quick-tailor
    profile's standing instruction (fill_checkpoint_session's return value) —
    persisting it there would be wrong, the web path keeps it transient — so
    the one-shot and gap-page quick-tailor paths pass it into tailor() as
    user_prompt but the MCP fill step has nowhere to put it.
    create_tailoring_session(use_presets=True) threads it through here
    instead, stamped onto the suggested tailor_session
    call's args so the agent carries it forward on the next hop. Applied ONLY
    when the session carries no note of its own (session["user_prompt"]) —
    this mirrors app.services.quick_tailor._instruction_fallback's rule that
    an explicit/stored note always beats the fallback, so a user's own note
    (whichever path wrote it) is never silently overridden.
    """
    if _suppressed(hints_enabled, brief):
        return None
    session_id = session.get("id")
    gaps = session.get("gaps_json") or {}
    resolved_ids = {r.get("gap_id") for r in (session.get("resolutions_json") or [])}
    # gaps_json's categories carry the gap ids; walking .keys() would only see
    # top-level category names, so the real ids live one level down in each
    # category's gap list. Every gap in this repo carries a "gap_id" field
    # (see resolve_gaps' docstring), so collect over that instead.
    all_gap_ids = [
        gap.get("gap_id")
        for category in (gaps.get("categories") or [])
        for gap in (category.get("gaps") or [])
        if gap.get("gap_id")
    ]
    unresolved = [gid for gid in all_gap_ids if gid not in resolved_ids]

    tailor_args: dict[str, Any] = {"tailoring_session_id": session_id}
    if instruction and not (session.get("user_prompt") or "").strip():
        tailor_args["user_prompt"] = instruction

    saved = (
        "resolutions_json holds the saved decisions (including any "
        "system-planned provenance-carrying entries). "
    )
    if writer == "maestro":
        label = "Tailor from the saved resolutions; Maestro's AI writes the edits"
        note = saved + (
            "The user's writer setting is Maestro's AI: tailor_session with ops "
            "omitted has it write the edits from the saved decisions, using the "
            "user's key."
        )
    else:
        label = (
            "Tailor from the saved resolutions with edit ops the agent app writes, "
            "or with no_new_text (no new wording)"
        )
        note = saved + (
            "The user's writer setting is the agent app, so Maestro's AI writes no "
            "edits here. tailor_session takes ops=[...] that implement the saved "
            "decisions: the server itself applies enable_entry and port_kb_point, "
            "and adds a saved add_keyword the ops leave out to the skills list; "
            "user_input and attach_project reach the resume only through the ops. "
            "Or no_new_text=true: no new wording, only the saved answers that need "
            "none are applied, and answers_left_to_ops lists the rest."
        )
    tailor_option = {
        "label": label,
        "tool": "tailor_session",
        "args": tailor_args,
        "detail": {
            "writer": writer,
            "resolutions_json": session.get("resolutions_json") or [],
            "note": note,
        },
    }

    if not unresolved:
        options = _visible([tailor_option], allowed_tools)
        return {
            "state": "gaps_resolved",
            "blocking": True,
            "offer": None,
            "ask_user": None,
            "options": options,
            "call": "tailor_session" if options else None,
        }

    resolve_option = {
        "label": f"Resolve the {len(unresolved)} remaining gap(s)",
        "tool": "resolve_gaps",
        "args": {"tailoring_session_id": session_id},
        "detail": {"unresolved_gap_ids": unresolved},
    }
    options = _visible([resolve_option, tailor_option], allowed_tools)
    return {
        "state": "gaps_pending",
        "blocking": True,
        "offer": None,
        "ask_user": (
            f"{len(unresolved)} gap(s) have no saved resolution. Resolve them "
            "first, or tailor with the decisions already saved?"
        ),
        "options": options,
        "call": None,
    }


def next_after_tailor(
    *,
    application_id: str,
    allowed_tools: "frozenset[str] | None",
    hints_enabled: bool,
    brief: bool = False,
    pdf_ready: bool = False,
    setup_status: dict[str, Any] | None = None,
    keywords_added: list[str] | tuple[str, ...] = (),
    answers_left_to_ops: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
) -> dict[str, Any] | None:
    """Compose the hint that follows tailor_session, which renders the PDF itself.

    With the PDF made (`pdf_ready`) the arc is at its last step, so the hint is
    next_after_render's: apply readiness and the handoff, from `setup_status`.
    When that render failed, render_pdf is offered, and it is the `call` when
    nothing else is pending. Saved keywords the server added to the skills list
    ride on the render option.

    Saved answers that need wording the server did not write come first, as an
    edit_application option with an `ask_user`, and then nothing is the `call`:
    writing them may need the user, and an edit clears the PDF, so following a
    render first would make the PDF twice."""
    if _suppressed(hints_enabled, brief):
        return None
    left = list(answers_left_to_ops)
    candidates: list[dict[str, Any]] = []
    if left:
        candidates.append(
            {
                "label": "Write the saved answers that need wording",
                "tool": "edit_application",
                "args": {"application_id": application_id},
                "detail": {
                    "answers_left_to_ops": left,
                    "note": (
                        "These saved answers need wording the server did not write: "
                        "user_input and attach_project answers, and an add_keyword whose "
                        "word needs a rewritten line. Each is on the resume only where "
                        "edit ops wrote it."
                    ),
                },
            }
        )
    if not pdf_ready:
        render_option = {
            "label": "Render the tailored application to PDF",
            "tool": "render_pdf",
            "args": {"target_type": "application", "target_id": application_id},
            "detail": None,
        }
        if keywords_added:
            render_option["detail"] = {
                "keywords_added": list(keywords_added),
                "note": "No edit put these saved keywords on the resume; the server added them to the skills list.",
            }
        candidates.append(render_option)
    options = _visible(candidates, allowed_tools)
    if pdf_ready and setup_status is not None:
        hint = next_after_render(
            setup_status=setup_status, allowed_tools=allowed_tools, hints_enabled=True
        )
    else:
        hint = {"state": "rendered" if pdf_ready else "tailored", "offer": None}
    return {
        **hint,
        "blocking": bool(options),
        "ask_user": (
            f"{len(left)} saved answer(s) need wording the server did not write. "
            "Write them into the resume, or keep it as it is?"
            if left and options
            else None
        ),
        "options": options,
        "call": "render_pdf" if options and not left else None,
    }


def next_after_render(
    *,
    setup_status: dict[str, Any],
    allowed_tools: "frozenset[str] | None",
    hints_enabled: bool,
    brief: bool = False,
) -> dict[str, Any] | None:
    """Compose the terminal hint that follows render_pdf: apply readiness
    facts plus a conditional offer.

    `readiness` is read from GET /api/setup/status's `autofill` block, which
    is already the derived "can this profile fill a form" signal — its own
    `done` is exactly readiness >= 1.0, so `autofill_ready` is a direct
    passthrough rather than a re-derivation that could drift from it.

    There is no cross-server introspection: this process cannot see whether
    the calling MCP client also holds Playwright/browser tools, so the offer
    states that the handoff needs browser tools and that this server cannot
    detect them, rather than asserting a capability we cannot confirm. No tool
    `options` are emitted for the handoff itself — the browser tools are not
    ours to name. The upload/consent tools ARE ours, and are named only when the
    active set registered them (only apply and full do), so the offer is
    None there. record_consent / mark_submitted are described as recording the
    USER's decisions: the consent semantics are statements of what they mean.
    """
    if _suppressed(hints_enabled, brief):
        return None
    autofill = setup_status.get("autofill") or {}
    groups = autofill.get("groups") or {}
    incomplete_groups = [
        name
        for name, g in groups.items()
        if (g.get("answered") or 0) < (g.get("answerable") or 0)
    ]
    readiness = {
        "autofill_ready": bool(autofill.get("done")),
        "incomplete_groups": incomplete_groups,
        "blocking_groups": list(autofill.get("blocking") or []),
    }
    handoff = [
        text
        for tool, text in (
            ("prepare_application_pdf_upload", "prepare_application_pdf_upload stages the PDF for upload"),
            ("record_consent", "record_consent records the user's consent"),
            ("mark_submitted", "mark_submitted records the user's submission"),
        )
        if _registered(tool, allowed_tools)
    ]
    offer = (
        "Apply handoff (needs browser tools, which this server cannot "
        f"detect): {'; '.join(handoff)}."
        if handoff
        else None
    )
    return {
        "state": "rendered",
        "blocking": False,
        "offer": offer,
        "ask_user": None,
        "options": [],
        "call": None,
        "readiness": readiness,
    }


def next_after_kb_ingest(
    report: dict[str, Any],
    *,
    allowed_tools: "frozenset[str] | None",
    hints_enabled: bool,
) -> dict[str, Any] | None:
    """Offer-only hint after one resume lands in the KB.

    Multi-resume ingestion is a loop — a question on every file would derail
    it, same lesson as score_ats. The primary offer is APPROVAL, not
    composition: ingest writes drafts, and nothing this path wrote reaches a
    composed resume until kb_approve_points (or the /career inbox) stamps it.
    Creating a base belongs after that step, so it is offered by
    next_after_bulk_state instead.

    The prose is derived from the options that survived filtering — a static
    string would keep advertising a tool this profile never registered, or a
    step this report has no ids for.
    """
    if _suppressed(hints_enabled):
        return None
    point_ids = [str(p.get("id")) for p in (report.get("points") or []) if p.get("id")]
    options: list[dict[str, Any]] = []
    if point_ids:
        options.append({
            "label": f"Approve the {len(point_ids)} draft point(s) that just landed",
            "tool": "kb_approve_points",
            # Verbatim-callable: these are the ids this very report returned.
            "args": {"point_ids": point_ids},
            "detail": (
                "Points from this report are drafts; the user's approval is "
                "what puts them on composed resumes. state='retired' discards "
                "drafts the user rejects."
            ),
        })
    options.extend([
        {
            "label": "Ingest another resume",
            "tool": "kb_ingest_resume",
            "args": {},
            "detail": None,
        },
        {
            "label": "Review the entities that landed",
            "tool": "kb_list_entities",
            "args": {},
            "detail": None,
        },
        {
            "label": "Review the points that landed",
            "tool": "kb_list_points",
            "args": {"state": "draft"},
            "detail": None,
        },
    ])
    options = _visible(options, allowed_tools)
    return {
        "state": "kb_ingested",
        "blocking": False,
        "offer": _offer_from_options(
            options,
            {
                "kb_approve_points": (
                    f"kb_approve_points records the user's approval of the "
                    f"{len(point_ids)} new draft point(s)"
                ),
                "kb_ingest_resume": "kb_ingest_resume (another resume)",
                "kb_list_entities": "kb_list_entities (what landed)",
                "kb_list_points": "kb_list_points (the drafts)",
            },
            suffix=(
                "Drafts stay off composed resumes until approved."
                if point_ids
                else ""
            ),
        ),
        "ask_user": None,
        "options": options,
        "call": None,
    }


def next_after_bulk_state(
    results: list[dict[str, Any]],
    *,
    requested_state: str,
    allowed_tools: "frozenset[str] | None",
    hints_enabled: bool,
) -> dict[str, Any] | None:
    """After batch approve, offer creating a base; after retire, stay neutral.

    `requested_state` comes from the SERVER, not from the results: a batch
    where every id failed carries no state at all, and inferring intent from an
    empty result list is how this composer used to report "Points retired.
    Nothing else required." after an approval that changed nothing.
    """
    if _suppressed(hints_enabled):
        return None
    ok = [r for r in results if r.get("ok")]
    failed = [r for r in results if not r.get("ok")]
    options: list[dict[str, Any]] = []

    if not ok:
        first = next(
            (str(r.get("detail")) for r in failed if r.get("detail")), "no reason given"
        )
        offer = (
            f"No point changed state: {len(failed)} of {len(results)} id(s) failed "
            f"({first})."
        )
        if _registered("kb_list_points", allowed_tools):
            offer += " kb_list_points returns the current ids and states."
    elif requested_state == "approved":
        options = _visible(
            [{
                "label": "Create a base resume from approved KB points",
                "tool": "create_base_resume_from_kb",
                # No args: this composer knows neither which entities the user
                # wants on the base nor the role, and entity_ids=[] is a
                # documented 422.
                "detail": (
                    "Takes entity_ids for what belongs on this base, plus a "
                    "role_category or role_label."
                ),
            }],
            allowed_tools,
        )
        offer = _offer_from_options(
            options,
            {"create_base_resume_from_kb": (
                "create_base_resume_from_kb (builds a base resume from chosen "
                "entity_ids)"
            )},
            prefix=f"{len(ok)} point(s) approved.",
        ) or f"{len(ok)} point(s) approved."
    else:
        offer = f"{len(ok)} point(s) retired."

    if ok and failed:
        offer = f"{offer} {len(failed)} id(s) failed."
    return {
        "state": "kb_points_updated",
        "blocking": False,
        "offer": offer,
        "ask_user": None,
        "options": options,
        "call": None,
    }


def next_after_base_from_kb(
    base: dict[str, Any],
    *,
    allowed_tools: "frozenset[str] | None",
    hints_enabled: bool,
    setup_status: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Handoff into the tailoring arc: render the new base.

    Scoring is named in prose only — score_ats needs a job_id this composer
    cannot know, and an option whose args are incomplete is a 422 waiting to
    happen (the whole point of `args` is that they are callable verbatim). It
    is named only where the profile registered it (career does not). The form
    answers are prose for the same reason (they are the user's to give), named
    only while GET /api/setup/status reads them as not done; an unknown status
    names nothing.
    """
    if _suppressed(hints_enabled):
        return None
    slug = str(base.get("slug") or "")
    if not slug:
        # The server degrades a non-dict body to {}. With no slug there is no
        # verbatim-callable option and no honest prose — say nothing, the way
        # next_after_scores does when nothing was scored.
        return None
    render_error = str(base.get("render_error") or "").strip()
    if render_error:
        # The base exists but its PDF failed: calling it ready, or offering a
        # render that fails the same way, sends the agent into a loop.
        first_line = render_error.splitlines()[0][:200]
        offer = f"Base {slug} was created, but its PDF could not be made: {first_line}."
        if _registered("edit_base_resume", allowed_tools):
            offer += " Fix the resume with edit_base_resume, then render it again."
        return {
            "state": "base_render_failed",
            "blocking": False,
            "offer": offer,
            "ask_user": None,
            "options": [],
            "call": None,
        }
    options = _visible(
        [
            {
                "label": f"Render {slug} to PDF",
                "tool": "render_pdf",
                "args": {"target_type": "base_resume", "target_id": slug},
                "detail": None,
            },
        ],
        allowed_tools,
    )
    steps = []
    if options:
        steps.append("render_pdf (preview)")
    if _registered("score_ats", allowed_tools):
        steps.append("score_ats (against a captured job)")
    autofill = (setup_status or {}).get("autofill")
    answers_open = isinstance(autofill, dict) and autofill.get("done") is False
    if answers_open and _registered("set_autofill_profile", allowed_tools):
        steps.append("set_autofill_profile (the form answers, which setup reads as not done)")
    offer = f"Base {slug} is ready."
    if steps:
        offer += f" Available next steps: {_listed(steps)}."
    if not options:
        offer += " This set has no render tool; the profile set has one."
    return {
        "state": "base_from_kb",
        "blocking": False,
        "offer": offer,
        "ask_user": None,
        "options": options,
        "call": None,
    }


# --- Setup status: the first setup step an agent can do -----------------------

# In order. The AI key and the default template are the user's, in the app: get_setup_status
# reports them but they are never a next step. Read from every set, so each step names only
# the set that does it and describes the work in plain words (no tool names).
_SETUP_STEPS: tuple[tuple[str, str], ...] = (
    ("career_history", "Import the user's resume and any project write-ups into their career "
                       "history, and have the user approve the bullets."),
    ("base_resume", "Build a base resume from the approved career history for each role the "
                    "user targets; the shipped demo resume does not count. Imported bullets start "
                    "as drafts, and a base resume takes only the ones the user approved."),
    ("form_answers", "Save the answers application forms ask for: contact, address, and work "
                     "permits for each country the user applies in. The diversity answers are the "
                     "user's, in the app."),
    ("job_preferences", "Save the jobs the user wants: roles, places, work mode and minimum pay."),
    ("persona", "Save the user's persona: a few sentences in their own words that every "
                "writing prompt reads for tone."),
)


def _step_done(status: dict[str, Any], key: str) -> bool:
    return bool((status.get(key) or {}).get("done"))


def _answers_done(status: dict[str, Any]) -> bool:
    """Every form-answer group an agent can save is complete. The diversity answers (`eeo`) count
    toward the app's own done, but set_autofill_profile refuses them: only the user gives those."""
    groups = ((status.get("autofill") or {}).get("groups") or {}).items()
    open_groups = [g for k, g in groups if k != "eeo" and g.get("answered", 0) < g.get("answerable", 0)]
    return _step_done(status, "autofill") or bool(groups) and not open_groups


def setup_next_step(status: dict[str, Any]) -> dict[str, Any] | None:
    """The first agent-doable setup step not done, from a GET /api/setup/status body."""
    imported = status.get("import_resumes") or {}
    real_bases = int((imported.get("detail") or {}).get("base_resumes") or 0) - len(
        status.get("demo_bases") or []
    )
    done = {
        "career_history": _step_done(status, "import_resumes"),
        "base_resume": real_bases > 0,
        "form_answers": _answers_done(status),
        "job_preferences": _step_done(status, "job_preferences"),
        "persona": _step_done(status, "persona"),
    }
    for step, says in _SETUP_STEPS:
        if not done[step]:
            return {"step": step, "tool_set": "profile", "says": says}
    return None

