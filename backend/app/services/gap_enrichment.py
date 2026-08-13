"""Gap enrichment: an LLM prose pass (enrich_gaps, display-only helper text)
plus a deterministic KB/library candidate gate (stamp_library_candidates, NO
LLM) whose output drives pre-stored auto-resolutions — not display-only.

Neither function catches its own exceptions: both are best-effort, and the
try/except for each lives in the caller (tailoring session creation), which
falls back to unenriched / ungated gaps respectively.
"""
import copy
from typing import Any

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.services import kb_resolver, llm, model_settings, placement_targets, prompt_assembly

# The private handoff key enrich_gaps stashes raw LLM library_candidates under
# and stamp_library_candidates always pops: a shared constant so a one-sided
# rename can't silently degrade to "LLM proposals are dropped" with no error.
_LLM_PROPOSALS_KEY = "llm_library_proposals"

# Only these gap fields are sent to the LLM (plus the category key, the
# diagnostic's fix_hint, and the diagnostic evidence sub-fields below). The full
# diagnostic rows carry recency math the model doesn't need for helper text —
# pure token weight — so only the grounding evidence travels.
_GAP_FIELDS = ("gap_id", "kind", "jd_skill", "requirement_level", "detail", "actions")

# Diagnostic sub-fields the model needs to ground a placement/wording suggestion:
# where the skill was found, how it was matched, and how recent the evidence is.
# Copied only when present and non-None (small token cost is acceptable).
_DIAGNOSTIC_EVIDENCE_FIELDS = ("evidence_entries", "placement", "matched_term", "last_used")

def _trim_gaps(gaps: dict[str, Any]) -> dict[str, Any]:
    trimmed: list[dict[str, Any]] = []
    for category in gaps.get("categories", []):
        for gap in category["gaps"]:
            entry = {key: gap[key] for key in _GAP_FIELDS if key in gap}
            entry["category"] = category["key"]
            diagnostic = gap.get("diagnostic") or {}
            fix_hint = diagnostic.get("fix_hint")
            if fix_hint:
                entry["fix_hint"] = fix_hint
            for key in _DIAGNOSTIC_EVIDENCE_FIELDS:
                value = diagnostic.get(key)
                if value is not None:
                    entry[key] = value
            trimmed.append(entry)
    return {"gaps": trimmed}


def _coerce_enrichment(
    entry: dict[str, Any], resume_targets: dict[str, Any], fix_hint: str | None
) -> dict[str, Any]:
    """Keep only correctly-typed field values: enrichments freeze into gaps_json
    for the session's lifetime, so wrong-typed LLM output must not persist."""
    wording = entry.get("suggested_wording")
    question = entry.get("elicitation_question")
    projects = entry.get("project_candidates")
    return {
        "suggested_wording": wording if isinstance(wording, str) else None,
        "project_candidates": (
            [item for item in projects if isinstance(item, str)]
            if isinstance(projects, list)
            else []
        ),
        "elicitation_question": question if isinstance(question, str) else None,
        "suggested_placement": placement_targets.coerce(
            entry.get("suggested_placement"), resume_targets, fix_hint
        ),
    }


def _disabled_entries(resume_json: dict[str, Any]) -> list[dict[str, Any]]:
    disabled: list[dict[str, Any]] = []
    for section in ("experience", "projects"):
        for index, entry in enumerate(resume_json.get(section) or []):
            if not isinstance(entry, dict) or entry.get("enabled") is not False:
                continue
            # Shared with the verification gate; notably handles ProjectEntry.tech
            # being a STRING (iterating it as a list yields characters).
            text_parts = kb_resolver.entry_evidence_texts(section, entry)
            disabled.append(
                {
                    "section": section,
                    "index": index,
                    "name": str(
                        entry.get("name")
                        or entry.get("role")
                        or entry.get("company")
                        or ""
                    ),
                    "text": "\n".join(text_parts),
                }
            )
    return disabled


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    if candidate.get("kind") == "disabled":
        return ("disabled", candidate.get("section"), candidate.get("index"))
    if candidate.get("kind") == "kb_point":
        return ("kb_point", candidate.get("entity_id"), candidate.get("point_id"))
    return (candidate.get("kind"),)


def _self_proposals(
    kb_snapshot: dict[str, Any],
    disabled_entries: list[dict[str, Any]],
    resume_json: dict[str, Any],
) -> list[dict[str, Any]]:
    """Deterministic self-nomination: every library item, proposed for every
    missing-skills gap, gated by kb_resolver.verify_candidate like any LLM
    proposal. Live E2E (2026-08-05) showed the fast model returning
    library_candidates: null even for literal matches sitting in its prompt —
    lexical discovery must not depend on the LLM following instructions. The
    LLM's own proposals remain additive (it can supply placement targets and
    semantic finds the enumeration can't)."""
    proposals: list[dict[str, Any]] = [
        {"kind": "disabled", "section": item["section"], "index": item["index"]}
        for item in disabled_entries
    ]
    for entity in kb_snapshot.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        target = kb_resolver.default_target_for_entity(entity, resume_json)
        for point in entity.get("points") or []:
            if isinstance(point, dict):
                proposals.append(
                    {
                        "kind": "kb_point",
                        "entity_id": entity.get("id"),
                        "point_id": point.get("id"),
                        "placement_target": target,
                    }
                )
    proposals.append({"kind": "profile"})
    return proposals


def pop_stash(gaps: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy ``gaps`` and pop the private ``_LLM_PROPOSALS_KEY`` stash off
    every missing_skills gap, writing no ``library_candidates`` — there is
    nothing to gate. This is stamp_library_candidates' own "no KB snapshot"
    shape, and also tailoring_session's safe re-call when the gated path
    raises: this has no ``kb_resolver.verify_candidate`` calls in it (the
    shared prefix — deepcopy, category/gap iteration, the pop itself — is all
    that's left), so it cannot fail the way a malformed KB entity just did.
    """
    stamped = copy.deepcopy(gaps)
    for category in stamped.get("categories", []):
        if category.get("key") != "missing_skills":
            continue
        for gap in category["gaps"]:
            gap.pop(_LLM_PROPOSALS_KEY, None)
    return stamped


def stamp_library_candidates(
    gaps: dict[str, Any],
    resume_json: dict[str, Any],
    kb_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """Gate KB/library evidence onto missing-skills gaps. NO LLM.

    Runs whether or not enrichment did, so enrich=False and a provider outage
    keep deterministic coverage detection — it used to sit downstream of
    llm.call_openai and died with it, which was code placement, not design.

    Always pops the private ``_LLM_PROPOSALS_KEY`` stash off every
    missing_skills gap, even when kb_snapshot is None (nothing to gate, so no
    ``library_candidates`` key gets written either): there is then no
    reachable state where enrich_gaps writes the stash and nothing ever runs
    to pop it. gaps_json is frozen at session creation and served raw to the
    web UI, MCP, and the resolver — a leaked private key would persist
    forever.

    Self-nomination is blind enumeration over the library, so only its LEXICAL
    hits survive: a semantic demotion there is noise, not a plausible
    suggestion. LLM proposals (present only when enrichment ran) were chosen
    FOR the gap, so their semantic hits stay. On duplicates keep the
    auto-eligible variant — either side may carry a placement target the other
    could not derive.
    """
    if kb_snapshot is None:
        return pop_stash(gaps)

    stamped = copy.deepcopy(gaps)
    disabled_entries = _disabled_entries(resume_json)
    self_proposals = _self_proposals(kb_snapshot, disabled_entries, resume_json)

    for category in stamped.get("categories", []):
        if category.get("key") != "missing_skills":
            continue
        for gap in category["gaps"]:
            merged: dict[tuple[Any, ...], dict[str, Any]] = {}
            order: list[tuple[Any, ...]] = []

            def _consider(proposal: Any, *, lexical_only: bool) -> None:
                candidate = kb_resolver.verify_candidate(
                    proposal, kb_snapshot, resume_json, gap.get("jd_skill") or ""
                )
                if candidate is None:
                    return
                if lexical_only and candidate.get("match_form") == "semantic":
                    return
                key = _candidate_key(candidate)
                if key not in merged:
                    merged[key] = candidate
                    order.append(key)
                elif candidate.get("auto") and not merged[key].get("auto"):
                    merged[key] = candidate

            for proposal in self_proposals:
                _consider(proposal, lexical_only=True)
            raw = gap.pop(_LLM_PROPOSALS_KEY, None)
            for proposal in raw if isinstance(raw, list) else []:
                _consider(proposal, lexical_only=False)

            autos = [merged[k] for k in order if merged[k].get("auto")]
            suggestions = [merged[k] for k in order if not merged[k].get("auto")]
            gap["library_candidates"] = (autos + suggestions)[:5]
    return stamped


def enrich_gaps(
    gaps: dict[str, Any],
    resume_json: dict[str, Any],
    jd_json: dict[str, Any],
    kb_snapshot: dict[str, Any] | None = None,
    session: Session | None = None,
) -> dict[str, Any]:
    """Merge LLM enrichments into a copy of the gaps dict, keyed by gap_id.

    Unknown gap_ids in the response are ignored; gaps the response skips keep
    ``enrichment: None``.
    """
    owns_session = session is None
    session = session or SessionLocal()
    try:
        prompt_kwargs: dict[str, Any] = {}
        disabled_entries: list[dict[str, Any]] = []
        if kb_snapshot is not None:
            disabled_entries = _disabled_entries(resume_json)
            prompt_kwargs = {
                "kb_snapshot": kb_snapshot,
                "disabled_entries": disabled_entries,
            }
        prompt = prompt_assembly.build_gap_enrichment_prompt(
            resume_json, jd_json, _trim_gaps(gaps), **prompt_kwargs
        )
        result = llm.call_openai(
            prompt=prompt,
            model=model_settings.get_fast_model(session),
            response_format="json",
            trace_name="gap-enrichment",
        )
        entries = result.get("enrichments", []) if isinstance(result, dict) else []
        if not isinstance(entries, list):
            raise ValueError("Enrichment response must contain an enrichments list")

        resume_targets = placement_targets.build_targets(resume_json)
        fix_hints = {
            gap["gap_id"]: (gap.get("diagnostic") or {}).get("fix_hint")
            for category in gaps.get("categories", [])
            for gap in category["gaps"]
        }
        by_id = {
            entry["gap_id"]: _coerce_enrichment(
                entry, resume_targets, fix_hints.get(entry["gap_id"])
            )
            for entry in entries
            if isinstance(entry, dict) and entry.get("gap_id")
        }
        raw_by_id = {
            entry["gap_id"]: entry.get("library_candidates")
            for entry in entries
            if isinstance(entry, dict) and entry.get("gap_id")
        }
        enriched = copy.deepcopy(gaps)
        for category in enriched.get("categories", []):
            for gap in category["gaps"]:
                if gap["gap_id"] in by_id:
                    gap["enrichment"] = by_id[gap["gap_id"]]
                if category.get("key") != "missing_skills":
                    continue
                # Raw, UNGATED nominations. stamp_library_candidates ALWAYS
                # gates and pops this key for every missing_skills gap — even
                # when kb_snapshot is None, in which case it pops without
                # gating anything — so there is no reachable state where it
                # is written here and nothing ever pops it. gating cannot
                # live here regardless, or it dies with the LLM call above.
                proposals = raw_by_id.get(gap["gap_id"])
                if isinstance(proposals, list):
                    gap[_LLM_PROPOSALS_KEY] = proposals
        return enriched
    finally:
        if owns_session:
            session.close()
