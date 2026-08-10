"""Deterministic gap list from an AtsResult. Categories = fix tiers, ordered by
intervention cost; within a category, by contribution potential (required first)."""
from typing import Any

from app.services.ats import load_config, normalize_term
from app.services.ats.engine import AtsResult

_LEVEL_RANK = {"required": 0, "preferred": 1, "mentioned": 2}

_CATEGORIES = [
    ("missing_skills", "Missing skills", "JD skills with no evidence on the resume"),
    ("mirror_wording", "Wording mismatches", "Matched semantically but the literal JD token is missing"),
    ("dual_place", "Placement upgrades", "In the skills list but not corroborated in any dated entry"),
    ("resurface_recent", "Stale evidence", "Matched, but the latest evidence is old or undated"),
    ("adjacent", "Adjacent skills", "Transferable skills that could be surfaced explicitly"),
    ("weak_coverage", "Uncovered responsibilities", "JD responsibilities your resume prose does not clearly cover"),
    ("title_structure", "Title & structure", "Title alignment, experience gate, format lint"),
]

# Best-cosine below which an L6 requirement line counts as not clearly covered by
# the resume prose. Conservative; tunable.
_COVERAGE_THRESHOLD = 0.55

_HINT_TO_CATEGORY = {
    "absent": "missing_skills",
    "mirror_wording": "mirror_wording",
    "dual_place": "dual_place",
    "resurface_recent": "resurface_recent",
    "adjacent_available": "adjacent",
    # Evidence lives only in a custom (extra) section: same honest intervention as
    # an undated-core match (undated_only -> resurface_recent) — move/strengthen
    # the evidence into a dated core entry — so route it to the same category
    # rather than dropping the skill from the workflow (finding F#8).
    "extra_only": "resurface_recent",
    # Evidence is a held certification and nothing else. Real, verifiable
    # evidence — never missing_skills — so it routes to the same honest
    # intervention as extra_only: show the credential being used in a dated entry.
    "credential_only": "resurface_recent",
}

_ACTIONS = {
    # honesty carve-out: missing skills MAY be added with add_keyword, but only into
    # the skills list (the frontend restricts placement to skills; the tailor prompt
    # forbids inventing any bullet/experience for them). Evidence-backed adds use the
    # other categories below.
    "missing_skills": [
        "add_keyword",
        "user_input",
        "attach_project",
        "skip",
        "enable_entry",
        "port_kb_point",
    ],
    "mirror_wording": ["add_keyword", "skip"],
    "dual_place": ["add_keyword", "skip"],
    "resurface_recent": ["add_keyword", "user_input", "skip"],
    "adjacent": ["add_keyword", "user_input", "skip"],
    "title_structure": ["user_input", "skip"],
}


def _potential_points(row: dict[str, Any]) -> float:
    """Deterministic estimate (0-100 composite scale) of the ATS headroom a skill
    gap could recover. NO LLM; reads only fields the engine already put on the row
    and the same weights the engine scored with — it changes no scoring.

    A skill row feeds the placement_recency subscore through
        contribution = requirement_weight * match_credit * placement_multiplier * recency
    (app/services/ats/layers.py resolve_evidence ~L168-173). That subscore is
        l2 = sum(contribution) / sum(requirement_weight * dual_multiplier)   (0-1)
    and rolls into the composite as 100 * composite_weight[placement_recency] * l2
    (app/services/ats/engine.py).

    Best case for a row is the dual-placement ceiling at full credit & recency for
    its requirement level; this also covers the "literal-token match" case, since a
    literal match means match_credit = 1.0:
        best_case = requirement_weight * dual_multiplier
    Current is the row's present contribution (0.0 for an absent/unmatched skill).

    We renormalize the per-row contribution headroom by the largest contribution
    any single row can carry (a required, dual-placed, full-credit/recency row) so
    it lands in [0, 1], then lift it onto the 0-100 composite scale through the
    placement_recency composite weight:
        potential_points = max(0, best_case - current) / max_row_contribution
                           * composite_weight[placement_recency] * 100

    This is a MONOTONIC ordering signal, not an exact predictor: it equals the
    composite gain if this row were the SOLE driver of its subscore (an upper
    bound — a resume with many skills dilutes each row's real marginal effect).
    It preserves the requirement-level ordering (required >= preferred >= mentioned)
    and the placement ordering (skills_list_only headroom > dual ceiling = 0)."""
    weights = load_config().weights
    req_weights = weights["requirement_weights"]
    dual_mult = weights["placement_multipliers"]["dual"]
    placement_composite_weight = weights["composite_weights"]["placement_recency"]

    req_weight = req_weights.get(row["requirement_level"], 0.0)
    best_case = req_weight * dual_mult
    current = row.get("contribution") or 0.0
    max_row_contribution = req_weights["required"] * dual_mult
    headroom = max(0.0, best_case - current)
    points = headroom / max_row_contribution * placement_composite_weight * 100
    return round(points, 1)


def _format_flag_actionable(flag: str) -> bool:
    """Whether an edit op can actually address a format flag. Actionable: a missing
    summary or skills section (replace_summary / add_skill_item) and the skills
    stuffing lint (replace_skills_group can prune). Fix-at-source (no op exists):
    unparseable dates, an incomplete contact block, and a missing experience or
    education section — these are routed skip-only with a "fix in the base resume"
    hint instead of a user_input textarea the tailor could never apply.

    Coupled to l5_format's flag strings (app/services/ats/layers.py); the
    format-routing test pins each real flag to its classification so a reworded
    flag cannot silently mis-route."""
    if flag.startswith("Section missing or empty:"):
        section = flag.split(":", 1)[1].strip()
        return section in {"summary", "skills"}
    return "skills-section items have no supporting evidence" in flag


def _skill_gap(row: dict[str, Any], category: str) -> dict[str, Any]:
    gap: dict[str, Any] = {
        "gap_id": f"skill:{normalize_term(row['jd_skill'])}",
        "kind": "skill",
        "jd_skill": row["jd_skill"],
        "requirement_level": row["requirement_level"],
        "potential_points": _potential_points(row),
        "diagnostic": row,
        "actions": _ACTIONS[category],
        "enrichment": None,
    }
    if category == "mirror_wording":
        # A lexical alias/fuzzy match already carries full keyword credit (1.0), so
        # adding the literal JD token is hygiene: it helps recruiter Boolean search
        # but does not move the score. A semantic match (credit < 1.0) gains real
        # keyword credit from the literal token. The UI copy splits on this.
        gap["score_effect"] = (
            "adds_credit" if (row.get("match_credit") or 0.0) < 1.0 else "hygiene"
        )
    return gap


def build_gaps(result: AtsResult) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {key: [] for key, _, _ in _CATEGORIES}

    for row in result.skill_table:
        category = _HINT_TO_CATEGORY.get(row.get("fix_hint") or "")
        if category:
            buckets[category].append(_skill_gap(row, category))

    for key in ("missing_skills", "mirror_wording", "dual_place", "resurface_recent", "adjacent"):
        buckets[key].sort(key=lambda g: (_LEVEL_RANK[g["requirement_level"]], g["jd_skill"]))

    # weak_coverage: JD requirement lines the resume prose does not clearly cover
    # (best semantic cosine below threshold). Kept in requirement-line order.
    for i, line in enumerate(result.requirement_coverage):
        if line["score"] < _COVERAGE_THRESHOLD:
            buckets["weak_coverage"].append({
                "gap_id": f"coverage:{i}", "kind": "requirement",
                "jd_skill": line["line"], "requirement_level": "preferred",
                "detail": "Resume prose does not clearly cover this responsibility",
                "diagnostic": {"coverage_score": line["score"]},
                "actions": ["user_input", "skip"], "enrichment": None,
            })

    if result.title_tier != "direct":
        buckets["title_structure"].append({
            "gap_id": "title:alignment", "kind": "title",
            "diagnostic": {"tier": result.title_tier},
            "detail": "Resume title/headline does not directly match the JD title",
            "actions": _ACTIONS["title_structure"], "enrichment": None,
        })
    buckets["title_structure"].append({
        "gap_id": "summary:value_prop", "kind": "summary",
        "detail": "Refresh the summary as a JD-aligned value proposition",
        "diagnostic": {}, "actions": ["user_input", "skip"], "enrichment": None,
    })
    for i, warning in enumerate(result.gate_warnings):
        buckets["title_structure"].append({
            "gap_id": f"gate:{i}", "kind": "gate", "detail": warning,
            "diagnostic": {}, "actions": ["skip"], "enrichment": None,
        })
    for i, flag in enumerate(result.format_flags):
        actionable = _format_flag_actionable(flag)
        buckets["title_structure"].append({
            "gap_id": f"format:{i}", "kind": "format",
            "detail": flag if actionable else f"{flag}. Fix this in the base resume.",
            "diagnostic": {},
            "actions": ["user_input", "skip"] if actionable else ["skip"],
            "enrichment": None,
        })

    return {
        "base_composite": result.composite,
        "subscores": result.subscores,
        "engine_version": result.engine_version,
        "config_version": result.config_version,
        "jd_skills_extracted_count": result.jd_skills_extracted_count,
        "jd_skills_matched_count": result.jd_skills_matched_count,
        "coverage_ratio": result.coverage_ratio,
        "coverage_warning": result.coverage_warning,
        "categories": [
            {"key": key, "title": title, "description": description, "gaps": buckets[key]}
            for key, title, description in _CATEGORIES
            if buckets[key]
        ],
    }
