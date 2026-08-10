import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from app.services import role_categories
from app.services.ats import degrees
from app.services.ats.config import AtsConfig
from app.services.ats.jd_normalizer import JdProfile
from app.services.ats.matching import SkillMatcher, normalize_term, term_in_text
from app.services.ats.resume_indexer import IndexedEntry, ResumeIndex

@lru_cache(maxsize=1)
def _seniority_vocab() -> tuple[tuple[str, ...], frozenset[str], frozenset[str]]:
    """Rank markers as (multi-word phrases, always-strip tokens, prefix-only tokens).

    Sourced from `role_categories.yaml` rather than hardcoded here: rank ladders
    are domain data (tech says "Staff", nursing says "RN III", government says
    "GS-13"), and a non-tech user must be able to fix their own title matching
    without editing the engine. Normalized through `normalize_term` so the
    vocabulary and the titles it is matched against agree on punctuation.

    Phrases are ordered longest-first so "entry level" is consumed before its
    parts can be stripped individually.
    """
    always = [normalize_term(t) for t in role_categories.seniority_always()]
    prefix_only = frozenset(
        normalize_term(t) for t in role_categories.seniority_prefix_only() if t
    )
    phrases = tuple(sorted({t for t in always if " " in t}, key=len, reverse=True))
    tokens = frozenset(t for t in always if t and " " not in t)
    return phrases, tokens, prefix_only


@dataclass
class SkillEvidence:
    jd_skill: str
    canonical: str
    requirement_level: str
    matched: bool
    match_form: str | None      # exact | alias | fuzzy | broader | semantic | adjacent
    match_credit: float         # 1.0, or adjacency/broader/semantic credit
    matched_term: str | None
    placement: str | None       # dual | experience_only | extra_only | credential_only | skills_list_only | undated_only
    last_used: str | None       # ISO date or "current"
    recency_weight: float | None
    contribution: float
    fix_hint: str | None        # mirror_wording | dual_place | resurface_recent | adjacent_available | credential_only | absent
    evidence_entries: list[str]  # entry labels where found (for the gap UI)


def _recency_weight(entry_dates: list[tuple[date | None, bool]], cfg: AtsConfig, as_of: date) -> tuple[float, str | None]:
    """Weight from the most recent dated evidence; (1.0, 'current') if any current entry."""
    recency = cfg.weights["recency"]
    if any(is_current for _, is_current in entry_dates):
        return 1.0, "current"
    dated = [d for d, _ in entry_dates if d is not None]
    if not dated:
        return 1.0, None  # undated evidence: no decay (the 0.4 placement floor handles credit)
    last = max(dated)
    # max() clamps future last_dates (indexer allows last_date > as_of) to weight 1.0
    years = max(0.0, (as_of - last).days / 365.25)
    return max(recency["floor"], recency["decay_rate"] ** years), last.isoformat()


def _select_placement(
    *,
    skills_hit: bool,
    has_dated: bool,
    has_undated_core: bool,
    has_extra: bool,
    has_credential: bool = False,
    placements: dict[str, float],
    extra_tier: str | None,
    extra_mult: float | None,
    credential_tier: str | None = None,
    credential_mult: float | None = None,
) -> tuple[str, float]:
    """Pick a matched skill's placement tier + multiplier from its available
    evidence sources.

    ``dual`` is the special two-source case (a skills-list item AND a dated core
    entry). Every other case picks the SINGLE strongest available tier by
    EFFECTIVE MULTIPLIER (deterministic max), NOT lexical branch order (finding
    F#9): a skill honestly corroborated by more than one source (e.g. an undated
    core project AND a custom section) is credited at whichever tier is worth
    most, robust to however the YAML multipliers are (re)tuned. Ties break toward
    CORE attribution first, then the documented cascade rank
    (experience > extra > skills > undated) — which reproduces the historical
    single-source classifications and the skills>undated preference exactly.

    Extras only participate when ``extra_tier`` is configured (feature-off
    fallback, finding F#2).

    BOTH classification paths run through here: the lexical path passes every
    available source, and the semantic path (``classify`` in _semantic_stage)
    passes exactly ONE flag per candidate — so a tier added here is reachable
    from both paths, and `dual` stays semantic-impossible by construction."""
    if skills_hit and has_dated:
        return "dual", placements["dual"]
    # (multiplier, is_core, cascade_rank, tier)
    candidates: list[tuple[float, int, int, str]] = []
    if has_dated:
        candidates.append((placements["experience_only"], 1, 5, "experience_only"))
    if has_extra and extra_tier is not None and extra_mult is not None:
        candidates.append((extra_mult, 0, 4, extra_tier))
    if has_credential and credential_tier is not None and credential_mult is not None:
        candidates.append((credential_mult, 0, 3, credential_tier))
    if skills_hit:
        candidates.append((placements["skills_list_only"], 1, 2, "skills_list_only"))
    if has_undated_core:
        candidates.append((placements["undated_only"], 1, 1, "undated_only"))
    if not candidates:
        # Reachable for exactly one shape: the only evidence is a `broader`
        # skills-list term, which carries partial keyword credit but earns no
        # placement of its own (see resolve_evidence). The weakest skills tier is
        # the right home for it — combined with the reduced credit it lands below
        # every full-credit tier.
        return "skills_list_only", placements["skills_list_only"]
    best = max(candidates, key=lambda c: (c[0], c[1], c[2]))
    return best[3], best[0]


def _lexical_stages(
    skill_name: str,
    index: ResumeIndex,
    matcher: SkillMatcher,
    skills_terms: set[str],
) -> tuple[
    str | None, str | None, float, bool,
    list[IndexedEntry], tuple[str, str | None, float] | None,
]:
    """Stages 1-2: skills-list lexical match, then dated-entry prose search.

    Returns (form, matched_term, credit, skills_hit, entry_hits,
    broader_fallback)."""
    # stage 1 (lexical): skills-section match, exact -> alias -> containment -> fuzzy
    form, matched_term, credit = matcher.match_terms_lexical(skill_name, skills_terms)
    # A `broader` skills-list term is NOT this JD skill: the list says "aws",
    # the ask is "AWS SageMaker", and a recruiter boolean search for the
    # specific term does not hit it. It is FALLBACK-grade evidence, so it is
    # held aside here and only used if the prose and semantic stages both
    # miss — the same position adjacency occupies. Left inline it would
    # short-circuit those stages (the semantic stage runs only when every
    # lexical stage missed), replacing a semantic match against a DATED entry
    # with skills-list partial credit and making a true addition lose points.
    # It also earns no skills-list PLACEMENT, and never `dual`.
    broader_fallback: tuple[str, str | None, float] | None = None
    if form == "broader":
        broader_fallback = (form, matched_term, credit)
        form, matched_term, credit = None, None, 0.0
    skills_hit = form is not None
    # stage 2 (lexical): dated-entry prose match (search the JD term)
    entry_hits: list[IndexedEntry] = []
    text_hit: tuple[str, str] | None = None  # (kind, form actually found)
    for entry in index.entries:
        hit = matcher.match_in_text(skill_name, entry.text)
        if hit:
            entry_hits.append(entry)
            # an exact prose hit in any entry outranks an alias hit elsewhere
            if text_hit is None or (hit[0] == "exact" and text_hit[0] != "exact"):
                text_hit = hit
    if not skills_hit and text_hit is not None:
        # matched only in prose; form/term come from the text search
        # (adjacent impossible here); matched_term is the form actually found.
        # A deferred `broader` leaves form None, so a literal occurrence in an
        # entry correctly beats a family term sitting in the skills list.
        form, matched_term, credit = text_hit[0], text_hit[1], 1.0
    return form, matched_term, credit, skills_hit, entry_hits, broader_fallback


def _adjacency_stage(
    skill_name: str,
    index: ResumeIndex,
    matcher: SkillMatcher,
    skills_terms: set[str],
    entry_hits: list[IndexedEntry],
) -> tuple[str, str | None, float] | None:
    """Stage 4b: adjacency match, only when every stage above missed. Extends
    entry_hits in place with prose hits for the matched source term."""
    adjacent = matcher.adjacency_match(skill_name, skills_terms)
    if adjacent is None:
        return None
    form, matched_term, credit = adjacent
    # re-run the prose search on the matched source term for placement
    search_term = matched_term or skill_name
    for entry in index.entries:
        hit = matcher.match_in_text(search_term, entry.text)
        if hit and entry not in entry_hits:
            entry_hits.append(entry)
    return form, matched_term, credit


def _fix_hint(
    form: str | None,
    placement: str | None,
    recency: float,
    resurface_threshold: float,
    extra_tier: str | None,
    credential_tier: str | None,
) -> str | None:
    """Precedence decision: wording fixes (adjacent/alias/fuzzy) outrank
    placement fixes — the literal JD token is what Boolean recruiter
    searches hit and mirroring it is the cheapest tier-1 intervention;
    placement stays visible on the row for the gap builder regardless."""
    if form in ("adjacent", "broader"):
        # `broader`: the resume evidences the FAMILY, not the specific member
        # the JD named ("aws" vs "AWS SageMaker"). That is an adjacency-shaped
        # gap, NOT a wording mismatch — routing it to mirror_wording told the
        # user that pasting the JD's product name on was free hygiene.
        return "adjacent_available"
    if form in ("alias", "fuzzy"):
        return "mirror_wording"
    if placement == "skills_list_only":
        return "dual_place"
    if placement == "undated_only":
        # honest intervention: surface the skill in a dated entry
        return "resurface_recent"
    if credential_tier is not None and placement == credential_tier:
        # The ONLY evidence is a certification. This is real, verifiable
        # evidence — NOT a missing skill — so it must never route to
        # missing_skills. The honest intervention is the same as extra_only:
        # show the credential being USED in a dated entry.
        return "credential_only"
    if extra_tier is not None and placement == extra_tier:
        # FIX F#8: the ONLY evidence is an enabled custom section (undated,
        # non-core). Previously this fell through to fix_hint=None and the gap
        # builder dropped the skill entirely despite real placement headroom.
        # Give it a distinct hint whose intervention mirrors undated_only —
        # move/strengthen the evidence into a dated core section.
        return "extra_only"
    if recency < resurface_threshold:
        return "resurface_recent"
    return None


def resolve_evidence(
    profile: JdProfile,
    index: ResumeIndex,
    matcher: SkillMatcher,
    cfg: AtsConfig,
    *,
    as_of: date,
) -> list[SkillEvidence]:
    # Known limitation: normalize_jd dedupes JD skills by normalize_term only,
    # so a JD listing both "AWS" and "Amazon Web Services" yields two JdSkills
    # that both match the same resume evidence and both contribute. Calibration
    # and the alias table keep this rare; no dedup here by design.
    skills_terms = {item.norm for item in index.skills_items}
    placements = cfg.weights["placement_multipliers"]
    req_weights = cfg.weights["requirement_weights"]
    resurface_threshold = cfg.weights["resurface_recency_threshold"]

    # FIX F#2: read the phase-2 extras config ONCE per scoring run via .get() with
    # a feature-off fallback. A legacy/custom weights.yaml lacking the
    # extra_section_evidence key must NOT crash the engine on every matched row:
    # when it is absent, extra_tier is None (the indexer likewise appends no extra
    # entries, so extra_hits stays empty), extras contribute nothing, and the
    # engine behaves exactly as it did pre-phase-2.
    extras_cfg = cfg.extras_config()
    extra_tier = extras_cfg.get("placement_tier")
    extra_mult = extras_cfg.get("placement_multiplier")

    # Credential evidence, same feature-off contract as extras: with no configured
    # block the tier is None, the indexer appends no credential entries, and the
    # engine behaves exactly as it did pre-credential.
    credentials_cfg = cfg.credentials_config()
    credential_tier = credentials_cfg.get("placement_tier")
    credential_mult = credentials_cfg.get("placement_multiplier")

    semantic_cfg = cfg.weights["semantic"]
    semantic_threshold = float(semantic_cfg["match_threshold"])
    semantic_credit = float(semantic_cfg["match_credit"])
    # Two-threshold generic-anchor rule (Task 8). Defaults keep the stage working
    # if an older config omits the keys (generic rule inert -> single threshold).
    semantic_generic_threshold = float(
        semantic_cfg.get("generic_anchor_threshold", semantic_threshold)
    )
    semantic_generic_anchors = {normalize_term(a) for a in semantic_cfg.get("generic_anchors", [])}

    # FIX 4 (I1): embed the resume candidate chunk-set ONCE for the whole call.
    # The candidate list (skills items then entry texts, one combined ordered
    # list) is identical for every unmatched skill, so re-embedding it per skill
    # was O(unmatched_skills x candidates). We cache the vectors here; each
    # unmatched skill then embeds only its own JD term (cheap) and cosines against
    # this cache, over the anchor-gated subset. Lazily: only pay the embed if at
    # least one skill actually reaches the semantic stage.
    semantic_candidates = [item.norm for item in index.skills_items] + [
        e.text for e in index.entries
    ]
    _cand_vectors: list[list[float]] | None = None

    def candidate_vectors() -> list[list[float]]:
        nonlocal _cand_vectors
        if _cand_vectors is None:
            from app.services.ats import embeddings

            _cand_vectors = (
                embeddings.embed_texts(semantic_candidates) if semantic_candidates else []
            )
        return _cand_vectors

    rows: list[SkillEvidence] = []
    for skill in profile.skills:
        # stages 1-2 (lexical): skills-section match, then dated-entry prose
        form, matched_term, credit, skills_hit, entry_hits, broader_fallback = (
            _lexical_stages(skill.name, index, matcher, skills_terms)
        )

        # semantic_evidence: set when the semantic stage is what matched (evidence
        # attribution comes from ONE winning candidate — the skills item or entry —
        # so dual placement is impossible for a semantic match by construction).
        semantic_evidence: SkillEvidence | None = None
        if form is None:
            # stage 3 (semantic): only when every lexical stage missed. Candidates
            # are the SAME enabled-only index the lexical stages saw (disabled
            # entries never enter this list), as one combined ordered list so the
            # matcher's deterministic tie-break applies across skills + entries.
            # Anchor-gated (C1) + candidate vectors cached across skills (I1).
            semantic_evidence = _semantic_stage(
                skill, index, matcher, cfg, as_of,
                candidates=semantic_candidates, candidate_vectors=candidate_vectors(),
                threshold=semantic_threshold, credit=semantic_credit,
                generic_threshold=semantic_generic_threshold,
                generic_anchors=semantic_generic_anchors,
                extra_tier=extra_tier, extra_mult=extra_mult,
                credential_tier=credential_tier, credential_mult=credential_mult,
            )

        if form is None and semantic_evidence is not None:
            rows.append(semantic_evidence)
            continue

        # stage 4a (broader): the deferred partial-credit containment hit, used
        # only now that prose and semantics have both missed. skills_hit stays
        # False, so _select_placement lands it on the weakest skills tier.
        if form is None and broader_fallback is not None:
            form, matched_term, credit = broader_fallback

        # stage 4b (adjacency): only when every stage above missed
        if form is None:
            adjacent = _adjacency_stage(
                skill.name, index, matcher, skills_terms, entry_hits
            )
            if adjacent is not None:
                form, matched_term, credit = adjacent
                skills_hit = True  # adjacency evidence is a skills-list term

        matched = form is not None
        if not matched:
            rows.append(SkillEvidence(
                jd_skill=skill.name, canonical=skill.canonical,
                requirement_level=skill.requirement_level, matched=False,
                match_form=None, match_credit=0.0, matched_term=None, placement=None,
                last_used=None, recency_weight=None, contribution=0.0,
                fix_hint="absent", evidence_entries=[],
            ))
            continue

        dated_hits = [e for e in entry_hits if e.last_date is not None or e.is_current]
        extra_hits = [e for e in entry_hits if e.section == "extra"]
        credential_hits = [e for e in entry_hits if e.section == "credential"]
        # credentials are undated but are NOT undated *core* evidence — without
        # this exclusion they would silently claim the undated_only tier
        undated_core_hits = [
            e for e in entry_hits
            if e.section not in ("extra", "credential")
            and e.last_date is None and not e.is_current
        ]

        placement, placement_mult = _select_placement(
            skills_hit=skills_hit,
            has_dated=bool(dated_hits),
            has_undated_core=bool(undated_core_hits),
            has_extra=bool(extra_hits),
            has_credential=bool(credential_hits),
            placements=placements,
            extra_tier=extra_tier,
            extra_mult=extra_mult,
            credential_tier=credential_tier,
            credential_mult=credential_mult,
        )

        recency, last_used = _recency_weight(
            [(e.last_date, e.is_current) for e in dated_hits], cfg, as_of
        )
        req_weight = req_weights[skill.requirement_level]
        contribution = req_weight * credit * placement_mult * recency

        fix_hint = _fix_hint(
            form, placement, recency, resurface_threshold, extra_tier, credential_tier
        )

        rows.append(SkillEvidence(
            jd_skill=skill.name, canonical=skill.canonical,
            requirement_level=skill.requirement_level, matched=True,
            match_form=form, match_credit=credit, matched_term=matched_term,
            placement=placement, last_used=last_used,
            # no dated evidence -> report None (the neutral 1.0 stays in the
            # contribution math above; only the reported field stops claiming
            # a recency that was never measured)
            recency_weight=round(recency, 4) if dated_hits else None,
            contribution=round(contribution, 4), fix_hint=fix_hint,
            evidence_entries=[e.label for e in entry_hits],
        ))
    return rows


def _semantic_stage(
    skill,
    index: ResumeIndex,
    matcher: SkillMatcher,
    cfg: AtsConfig,
    as_of: date,
    *,
    candidates: list[str],
    candidate_vectors: list[list[float]],
    threshold: float,
    credit: float,
    generic_threshold: float,
    generic_anchors: set[str],
    extra_tier: str | None,
    extra_mult: float | None,
    credential_tier: str | None = None,
    credential_mult: float | None = None,
) -> SkillEvidence | None:
    """Anchor-gated embedding fallback for a single JD skill. ``candidates`` is
    the enabled-only index's skills items followed by entry texts (one combined
    list so the deterministic best-score / first-seen tie-break spans both) and
    ``candidate_vectors`` are their embeddings, computed ONCE per resolve_evidence
    call and shared across skills (I1).

    Only candidates that pass the anchor gate — sharing a non-stopword token with
    the JD term or its aliases (C1) — are scored, so a match requires BOTH lexical
    overlap and embedding proximity. Two-threshold rule (Task 8): a candidate whose
    shared anchors are all generic domain nouns must clear ``generic_threshold``;
    others clear ``threshold``. On a hit, evidence is attributed to the single
    winning candidate: a skills item (-> skills_list_only) or an entry (dated ->
    experience_only, ordinary undated -> undated_only, custom -> its configured
    extra tier; recency from that entry only). Dual placement is impossible for
    a semantic match by construction."""
    from app.services.ats import embeddings

    if generic_anchors:
        gated = matcher.semantic_gate(skill.name, candidates, generic_anchors=generic_anchors)
    else:
        gated = [(i, False) for i in matcher.semantic_candidate_indices(skill.name, candidates)]
    if not gated:
        return None
    skills_items = index.skills_items
    entries = index.entries
    placements = cfg.weights["placement_multipliers"]
    req_weight = cfg.weights["requirement_weights"][skill.requirement_level]

    def classify(i: int) -> tuple[str, float]:
        """(placement, multiplier) for one candidate index.

        DELEGATES to _select_placement with exactly ONE evidence flag set, so
        the tier logic (names, multiplier keys, feature-off fallback) lives in
        one place for BOTH classification paths. A semantic match is attributed
        to its single winning candidate, so only one flag can ever be true —
        which is what keeps `dual` structurally impossible here. Used both to
        RANK and to report, so ranking and attribution can never diverge.
        """
        if i < len(skills_items):
            return _select_placement(
                skills_hit=True,
                has_dated=False,
                has_undated_core=False,
                has_extra=False,
                placements=placements,
                extra_tier=extra_tier,
                extra_mult=extra_mult,
                credential_tier=credential_tier,
                credential_mult=credential_mult,
            )
        entry = entries[i - len(skills_items)]
        # FIX F#2 feature-off fallback preserved: an extra/credential entry with
        # its tier unconfigured classifies by its dates like a core entry
        # (defensive — the indexer does not index such entries at all).
        is_extra = entry.section == "extra" and extra_tier is not None and extra_mult is not None
        is_credential = (
            entry.section == "credential"
            and credential_tier is not None
            and credential_mult is not None
        )
        dated = entry.last_date is not None or entry.is_current
        return _select_placement(
            skills_hit=False,
            has_dated=not is_extra and not is_credential and dated,
            has_undated_core=not is_extra and not is_credential and not dated,
            has_extra=is_extra,
            has_credential=is_credential,
            placements=placements,
            extra_tier=extra_tier,
            extra_mult=extra_mult,
            credential_tier=credential_tier,
            credential_mult=credential_mult,
        )

    jd_vec = embeddings.embed_texts([skill.name])[0]
    # Rank by EVIDENCE STRENGTH first, cosine second. Ranking on cosine alone let
    # a short, undated chunk (a certification line, a custom-section blurb) that
    # merely reads closer to the JD phrasing outrank the DATED BULLET describing
    # the work itself — demoting a genuinely practiced skill from experience_only
    # (1.0) to credential_only (0.5) and LOWERING the score for adding a true
    # certification. _select_placement already resolves the lexical path this way
    # ("strongest available tier by effective multiplier, not branch order",
    # finding F#9); the semantic stage now follows the same rule.
    # No best_score: the winning cosine is already carried as best_rank[1].
    best_idx, best_rank = -1, (0.0, 0.0)
    for i, generic_only in gated:  # gated preserves candidate order -> first-seen tie-break
        score = embeddings.cosine(jd_vec, candidate_vectors[i])
        floor = generic_threshold if generic_only else threshold
        if score < floor:
            continue
        rank = (classify(i)[1], score)
        if rank > best_rank:  # strict >: first-seen wins exact ties
            best_idx, best_rank = i, rank
    if best_idx < 0:
        return None

    placement, placement_mult = classify(best_idx)
    if best_idx < len(skills_items):
        # winner is a skills-list item: no dated evidence, no recency claim
        recency, last_used, dated = 1.0, None, False
        evidence_entries: list[str] = []
    else:
        entry = entries[best_idx - len(skills_items)]
        dated = entry.last_date is not None or entry.is_current
        recency, last_used = _recency_weight([(entry.last_date, entry.is_current)], cfg, as_of)
        evidence_entries = [entry.label]
    contribution = req_weight * credit * placement_mult * recency
    return SkillEvidence(
        jd_skill=skill.name, canonical=skill.canonical,
        requirement_level=skill.requirement_level, matched=True,
        match_form="semantic", match_credit=credit,
        # FIX 2 (C3): do NOT surface the raw candidate chunk as matched_term — a
        # bullet fragment reads as literal evidence the resume does not contain.
        # The honest signal is carried by evidence_entries + placement + the
        # mirror_wording fix_hint; the matched term is intentionally None.
        matched_term=None,
        placement=placement, last_used=last_used,
        recency_weight=round(recency, 4) if dated else None,
        contribution=round(contribution, 4),
        # A semantic match reproduces the meaning without the literal token, so
        # mirror_wording is the intervention (design: wording-mismatch gap) —
        # EXCEPT when the winner is a credential, where "mirror the JD wording"
        # would invite writing a certification name the candidate may not hold.
        fix_hint=(
            "credential_only"
            if credential_tier is not None and placement == credential_tier
            else "mirror_wording"
        ),
        evidence_entries=evidence_entries,
    )


def l6_semantic_fit_coverage(
    profile: JdProfile, index: ResumeIndex
) -> tuple[float, list[dict]]:
    """Coverage-oriented semantic similarity, returning BOTH the L6 subscore and
    its per-line detail from a SINGLE embed call:

      - subscore: for each JD requirement line, the best cosine against any resume
        chunk; the mean of those maxima. 0.0 when either side has no text.
      - coverage: [{"line": <requirement line>, "score": <best cosine>}, ...]
        ordered as the (non-blank) requirement lines. [] when there is no text.

    The per-line maxima drive both outputs, so exposing the coverage detail costs
    no second embed and cannot drift the subscore (the mean is unchanged)."""
    from app.services.ats import embeddings

    jd_lines = [line for line in profile.requirement_lines if line.strip()]
    chunks = [c for c in (index.summary, *(e.text for e in index.entries)) if c and c.strip()]
    if not jd_lines or not chunks:
        return 0.0, []
    vectors = embeddings.embed_texts([*jd_lines, *chunks])
    jd_vecs, chunk_vecs = vectors[: len(jd_lines)], vectors[len(jd_lines):]
    per_line_best = [
        max(embeddings.cosine(jv, cv) for cv in chunk_vecs) for jv in jd_vecs
    ]
    coverage = [
        {"line": line, "score": round(score, 4)}
        for line, score in zip(jd_lines, per_line_best)
    ]
    return sum(per_line_best) / len(per_line_best), coverage


def l1_keyword(rows: list[SkillEvidence], cfg: AtsConfig) -> float:
    req_weights = cfg.weights["requirement_weights"]
    total = sum(req_weights[r.requirement_level] for r in rows)
    if total == 0:
        return 0.0
    got = sum(req_weights[r.requirement_level] * r.match_credit for r in rows)
    return got / total


def l2_placement_recency(rows: list[SkillEvidence], cfg: AtsConfig) -> float:
    req_weights = cfg.weights["requirement_weights"]
    dual_mult = cfg.weights["placement_multipliers"]["dual"]
    total = sum(req_weights[r.requirement_level] * dual_mult for r in rows)
    if total == 0:
        return 0.0
    got = sum(r.contribution for r in rows)
    return min(1.0, got / total)


def _strip_seniority(title: str) -> str:
    """Reduce a title to its role core by removing rank markers only.

    Three passes, in this order:

    1. Multi-word phrases, longest-first — otherwise "entry level" loses
       "entry" to the token pass and strands "level".
    2. Always-strip tokens, anywhere. "Senior", "IV" are never a job.
    3. Prefix-only tokens, from the FRONT only, and never down to nothing.
       `associate`/`principal`/`staff`/`lead` are real head nouns in the suffix
       position: stripping them there turned "Tech Lead" into "tech" and "Sales
       Associate" into "sales", cores that match nothing, collapsing the tier to
       `none`. Leading them ("Lead Engineer") is a genuine rank.

    Pass 2 runs before pass 3 so "Senior Associate" — common in consulting and
    law — loses "senior", leaves "associate" as the only token, and keeps it
    rather than reducing to an empty core.
    """
    phrases, tokens, prefix_only = _seniority_vocab()
    text = normalize_term(title)
    for phrase in phrases:
        text = re.sub(rf"\b{re.escape(phrase)}\b", " ", text)
    parts = [t for t in text.split() if t not in tokens]
    while len(parts) > 1 and parts[0] in prefix_only:
        parts = parts[1:]
    if parts:
        return " ".join(parts)
    # Everything was a rank marker ("Senior", "Lead"). Returning "" would make
    # every such title equal to every other; keep the original core instead.
    return " ".join(text.split())


def l3_title(profile: JdProfile, index: ResumeIndex, cfg: AtsConfig) -> tuple[str, float]:
    """Title tiering. direct: stripped JD title equals the stripped recent role
    or appears verbatim in the summary. adjacent: any title-family member for
    the JD's role_category appears in the stripped recent role or summary.
    Otherwise none."""
    credits = cfg.weights["title_credit"]
    jd_core = _strip_seniority(profile.title)
    recent_core = _strip_seniority(index.recent_role)
    # word-boundary checks throughout: "ml engineer" must never hit inside
    # "xml engineering"
    if jd_core and (jd_core == recent_core or term_in_text(jd_core, index.summary)):
        return "direct", credits["direct"]
    haystack = " || ".join(c for c in (recent_core, index.summary) if c)
    for member in cfg.title_families.get(profile.role_category or "", []):
        if term_in_text(normalize_term(member), haystack):
            return "adjacent", credits["adjacent"]
    return "none", credits["none"]


def l4_gate(profile: JdProfile, index: ResumeIndex) -> list[str]:
    """Advisory warnings ONLY. engine.py builds the composite from `subscores`,
    so nothing here moves the score — by design. Education and years are enforced
    by application-form questions at every ATS platform surveyed, not by resume
    parsing, so the honest behavior is to warn the user a question is coming."""
    warnings: list[str] = []
    years = index.total_experience_years
    if profile.years_experience_min is not None and years < profile.years_experience_min - 0.25:
        warnings.append(
            f"JD asks for {profile.years_experience_min}+ years; dated entries show {years:.1f}"
        )
    asked = degrees.required_degree_level(profile.requirement_lines)
    shown = index.degree_level
    # Fail-silent: warn only on a POSITIVE reading that the resume is short. An
    # unparsed JD phrasing or an unparsed resume degree says nothing.
    if asked is not None and shown is not None and shown < asked:
        warnings.append(
            f"JD asks for a {degrees.LEVEL_NAMES[asked]} degree; resume shows "
            f"{degrees.LEVEL_NAMES[shown]}. This is normally an application-form "
            f"question — answer it honestly; your score is unaffected."
        )
    return warnings


def l5_format(index: ResumeIndex, rows: list[SkillEvidence], cfg: AtsConfig) -> tuple[float, list[str]]:
    flags: list[str] = []
    checks: list[bool] = []

    dates_ok = all(e.date_parse_ok for e in index.entries if e.section == "experience")
    checks.append(dates_ok)
    if not dates_ok:
        flags.append("Some experience dates failed to parse (use 'Jul 2022' format)")

    checks.append(index.contact_ok)
    if not index.contact_ok:
        flags.append("Contact block missing name, email, or phone")

    for section, present in index.sections_present.items():
        checks.append(present)
        if not present:
            flags.append(f"Section missing or empty: {section}")

    # stuffing lint: skills items with zero corroboration in any entry text.
    # FIX F#12: a flat `bullets` custom section is an unstructured keyword channel
    # and must NOT launder a skills-list item into "corroborated" (it would
    # trivially defeat this integrity check). Structured `entries` extras still
    # count — SYSTEM.md §4 allows extra evidence to affect skills-item
    # corroboration; only unstructured keyword channels (is_keyword_channel — a
    # flat extra section or the certifications list) are excluded.
    matched_terms = {r.matched_term for r in rows if r.matched_term}
    corroborated = 0
    for item in index.skills_items:
        in_entries = any(
            item.norm in e.text for e in index.entries if not e.is_keyword_channel
        )
        if in_entries or item.norm in matched_terms:
            corroborated += 1
    if index.skills_items:
        share_uncorroborated = 1 - corroborated / len(index.skills_items)
        ok = share_uncorroborated <= cfg.weights["stuffing_max_uncorroborated_share"]
        checks.append(ok)
        if not ok:
            flags.append(
                f"{share_uncorroborated:.0%} of skills-section items have no supporting evidence in any entry"
            )

    return (sum(checks) / len(checks) if checks else 1.0), flags
