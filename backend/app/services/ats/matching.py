import re
import unicodedata

from app.services.ats.config import AtsConfig

# keep +, #, ., / so "c++", "c#", "node.js", "ci/cd" survive normalization;
# `-` is intentionally excluded from the allowed class, so hyphens become spaces
# ("power-bi" -> "power bi")
_NORM_RE = re.compile(r"[^a-z0-9+#./ ]+")
_MIN_CONTAINMENT_LEN = 3  # single tokens shorter than this never containment-match
_MIN_FUZZY_LEN = 6  # edit-distance matching below this length conflates distinct skills
# generic vendor tokens: a shorter term made only of these never containment-matches
_CONTAINMENT_STOPWORDS = {"microsoft", "amazon", "google", "apache", "ms", "ibm"}
# Generic nouns a JD adds around a skill without naming a distinct product. When
# the JD's EXTRA tokens are all from this set, the ask is the same skill dressed
# up ("CI/CD pipelines" vs "ci/cd") and keeps full credit. Keep this list tight:
# every entry here is a word that, added to a skill name, must not change what
# skill is being asked for. "cloud", "architect" and vendor product names are
# deliberately ABSENT — "AWS Cloud Architect" is not "AWS".
_GENERIC_MODIFIERS = {
    "pipeline", "pipelines", "design", "development", "engineering",
    "management", "system", "systems", "tool", "tools", "platform", "platforms",
    "framework", "frameworks", "technology", "technologies", "concepts",
    "principles", "practices", "fundamentals", "experience", "environment",
    "environments", "stack", "ecosystem",
}
# Short alias forms individually vetted as safe to search in prose. Being a
# registered alias is NOT enough: "tf" (tensorflow) would false-positive on
# "TF-IDF" (normalizes to "tf idf" — the space is a word boundary), and any
# future short alias (go, r, ...) would silently become prose-searchable.
# Skills-section matching is unaffected — items there are discrete terms.
_PROSE_SEARCHABLE_SHORT_FORMS = {"ml"}

# Anchor-gate stopwords (post-review C1): tokens too generic to count as a shared
# anchor between a JD skill and a candidate chunk. Without this, "data" alone
# would anchor "data engineering" to "data entry". These are connective/filler
# words plus the handful of ubiquitous resume nouns; keep it conservative — every
# entry here is a token that, shared ALONE, does not evidence a real skill match.
_ANCHOR_STOPWORDS = {
    "a", "an", "and", "or", "the", "of", "in", "on", "to", "for", "with", "at",
    "by", "as", "is", "are", "be", "using", "used", "via",
    "experience", "experienced", "skills", "skill", "knowledge", "ability",
    "strong", "proficient", "proficiency", "familiar", "familiarity",
    "understanding", "expertise", "years", "year", "work", "working",
}
# Single-char tokens never anchor (too generic); alnum-with-symbol short forms
# like "c#"/"r"/"go" are handled by the lexical stages, not the semantic gate.
_MIN_ANCHOR_TOKEN_LEN = 2


def _anchor_tokens(text: str) -> set[str]:
    """Content tokens of a normalized string, minus stopwords and 1-char tokens."""
    return {
        tok
        for tok in normalize_term(text).split()
        if len(tok) >= _MIN_ANCHOR_TOKEN_LEN and tok not in _ANCHOR_STOPWORDS
    }


def normalize_term(term: str) -> str:
    decomposed = unicodedata.normalize("NFKD", term)
    folded = "".join(char for char in decomposed if not unicodedata.combining(char))
    lowered = folded.lower().strip()
    cleaned = _NORM_RE.sub(" ", lowered)
    return " ".join(cleaned.split())


def term_in_text(term: str, text: str) -> bool:
    """Word-boundary occurrence check of a normalized term in normalized prose.

    The lookarounds stop matches from crossing token boundaries ("ml" never
    hits inside "xml"/"html"; "ml engineer" never hits inside "xml engineering")
    while still allowing the term inside longer phrases.
    """
    return re.search(rf"(?<![a-z0-9+#]){re.escape(term)}(?![a-z0-9+#])", text) is not None


def _edit_distance_within(a: str, b: str, limit: int) -> bool:
    if abs(len(a) - len(b)) > limit:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return False
        prev = cur
    return prev[-1] <= limit


class SkillMatcher:
    """Deterministic skill matching, cheapest-first:
    exact → alias → containment → edit-distance → semantic → adjacency.

    match_terms covers the classic lexical+adjacency pipeline (v1-compatible);
    match_terms_lexical / semantic_match / adjacency_match expose the stages
    individually so evidence resolution can interleave the semantic fallback."""

    def __init__(self, config: AtsConfig):
        self._alias_to_canonical: dict[str, str] = {}
        self._alias_groups: dict[str, list[str]] = {}
        for group in config.aliases:
            canonical = normalize_term(group[0])
            forms = [normalize_term(a) for a in group]
            for form in forms:
                self._alias_to_canonical[form] = canonical
            self._alias_groups[canonical] = forms
        self._adjacency = {
            normalize_term(jd): {normalize_term(r): min(float(c), config.weights["adjacency_max_credit"])
                                 for r, c in sources.items()}
            for jd, sources in config.adjacency.items()
        }
        self._fuzzy_max = int(config.weights["fuzzy_max_distance"])
        self._broader_credit = float(config.weights["adjacency_max_credit"])

    def canonical(self, term: str) -> str:
        normalized = normalize_term(term)
        return self._alias_to_canonical.get(normalized, normalized)

    def all_forms(self, term: str) -> list[str]:
        """The term plus every registered alias form, normalized."""
        canonical = self.canonical(term)
        forms = self._alias_groups.get(canonical, [])
        normalized = normalize_term(term)
        return list(dict.fromkeys([normalized, canonical, *forms]))

    def match_terms_lexical(
        self, jd_term: str, resume_terms: set[str]
    ) -> tuple[str | None, str | None, float]:
        """Lexical stages only: exact → alias → containment → edit-distance.

        No adjacency (see adjacency_match) and no semantics (see semantic_match) —
        callers that want the full v2 stage order sequence these explicitly.
        """
        jd_norm = normalize_term(jd_term)
        jd_canonical = self.canonical(jd_term)

        if jd_norm in resume_terms:
            return "exact", jd_norm, 1.0
        for resume_term in sorted(resume_terms):
            if self.canonical(resume_term) == jd_canonical:
                return "alias", resume_term, 1.0
        jd_tokens = jd_norm.split()
        # Containment is DIRECTIONAL. Take the legitimate direction first, across
        # ALL resume terms, so a resume holding both "apache spark" and "aws"
        # cannot lose full credit to sort order.
        #
        # (a) resume term is MORE specific than the ask: "apache spark" covers a
        #     JD asking for "Spark". Full credit — the evidence is strictly
        #     stronger than what was requested.
        for resume_term in sorted(resume_terms):
            if self._tokens_contained(jd_tokens, resume_term.split()):
                return "fuzzy", resume_term, 1.0
        # (b) resume term is BROADER than the ask: "aws" against a JD asking for
        #     "AWS SageMaker". The resume evidences the family, not the member,
        #     so this earns adjacency-level partial credit — EXCEPT when the JD's
        #     extra tokens are purely generic nouns ("CI/CD pipelines" over
        #     "ci/cd"), which name no distinct product.
        for resume_term in sorted(resume_terms):
            resume_tokens = resume_term.split()
            if self._tokens_contained(resume_tokens, jd_tokens):
                extra = [t for t in jd_tokens if t not in resume_tokens]
                # Extra tokens that are purely a VENDOR qualifier ("Microsoft
                # Teams" over "teams", "Amazon Redshift" over "redshift") or a
                # generic noun do not change WHICH skill is being asked for, so
                # they keep full credit. A product name does ("AWS SageMaker"
                # over "aws"), so it does not.
                if extra and all(
                    t in _GENERIC_MODIFIERS or t in _CONTAINMENT_STOPWORDS for t in extra
                ):
                    return "fuzzy", resume_term, 1.0
                return "broader", resume_term, self._broader_credit
        for resume_term in sorted(resume_terms):
            # short-term near-misses (r/c, sas/saas, mysql/mssql) are distinct
            # skills, not typos — only fuzzy-match reasonably long terms
            if min(len(jd_norm), len(resume_term)) < _MIN_FUZZY_LEN:
                continue
            # terms in different KNOWN alias groups (e.g. js vs ts) are never typos
            if self._known_distinct_groups(jd_norm, resume_term):
                continue
            if _edit_distance_within(jd_norm, resume_term, self._fuzzy_max):
                return "fuzzy", resume_term, 1.0
        return None, None, 0.0

    def adjacency_match(
        self, jd_term: str, resume_terms: set[str]
    ) -> tuple[str, str, float] | None:
        """Adjacency stage: JD term covered by a registered adjacent resume skill.

        Returns ("adjacent", matched_term, credit) or None.
        """
        jd_norm = normalize_term(jd_term)
        jd_canonical = self.canonical(jd_term)
        adjacency = self._adjacency.get(jd_canonical) or self._adjacency.get(jd_norm)
        if adjacency:
            candidates = [
                (resume_term, adjacency[self.canonical(resume_term)])
                for resume_term in sorted(resume_terms)
                if self.canonical(resume_term) in adjacency
            ]
            if candidates:
                # highest credit wins; alphabetical tie-break for determinism
                best_term, best_credit = min(candidates, key=lambda tc: (-tc[1], tc[0]))
                return "adjacent", best_term, best_credit
        return None

    def semantic_anchor_tokens(self, jd_term: str) -> set[str]:
        """Content tokens of the JD term AND all its registered alias forms.

        The anchor gate (post-review C1) only considers a semantic candidate that
        shares at least one of these tokens — so aliases count as anchors too
        ("k8s" JD anchors a "kubernetes cluster" chunk via the alias form)."""
        tokens: set[str] = set()
        for form in self.all_forms(jd_term):
            tokens |= _anchor_tokens(form)
        return tokens

    def semantic_candidate_indices(self, jd_term: str, candidates: list[str]) -> list[int]:
        """Indices of candidates that pass the anchor gate: they share at least one
        non-stopword token with the JD term or its aliases. Preserves order so the
        downstream first-seen tie-break stays deterministic."""
        anchors = self.semantic_anchor_tokens(jd_term)
        if not anchors:
            return []
        return [i for i, c in enumerate(candidates) if anchors & _anchor_tokens(c)]

    def semantic_gate(
        self, jd_term: str, candidates: list[str], *, generic_anchors: set[str]
    ) -> list[tuple[int, bool]]:
        """Anchor gate + generic-only classification (Task 8). Returns, in order,
        ``(candidate_index, generic_only)`` for every candidate that shares an
        anchor token with the JD term/aliases; ``generic_only`` is True when EVERY
        shared anchor is a generic domain noun (see semantic.generic_anchors),
        which requires the stricter cosine floor downstream. A candidate sharing
        any non-generic anchor is False (normal floor). Order preserved for the
        deterministic first-seen tie-break."""
        anchors = self.semantic_anchor_tokens(jd_term)
        if not anchors:
            return []
        out: list[tuple[int, bool]] = []
        for i, c in enumerate(candidates):
            shared = anchors & _anchor_tokens(c)
            if shared:
                out.append((i, shared <= generic_anchors))
        return out

    def semantic_match(
        self,
        jd_term: str,
        candidates: list[str],
        *,
        threshold: float,
        credit: float,
        generic_threshold: float | None = None,
        generic_anchors: set[str] | None = None,
    ) -> tuple[str, float, float] | None:
        """Anchor-gated embedding cosine fallback. Only candidates that share a
        non-stopword token with the JD term (or its aliases) are considered — the
        embedding decides *among* lexically-anchored candidates, it never conjures
        a match out of pure vector proximity (post-review C1: 87% of ungated
        semantic matches on the real corpus were zero-overlap false positives).

        Two-threshold rule (Task 8): a candidate whose shared anchors are ALL
        generic domain nouns must clear ``generic_threshold`` (stricter); any other
        anchored candidate uses ``threshold``. This kills weak generic-only matches
        (Data Mining -> data-analyst bullet at ~0.6) while keeping genuine variants
        (data warehouse <-> data warehousing at 0.915). When ``generic_anchors`` is
        None the rule is inert (single threshold) — used by callers that don't wire
        the config, e.g. legacy tests.

        Deterministic: best *eligible* score wins, then candidate order breaks
        ties. Returns (candidate, score, credit) or None."""
        from app.services.ats import embeddings  # local import: seam for monkeypatching

        if generic_anchors:
            gated = self.semantic_gate(jd_term, candidates, generic_anchors=generic_anchors)
        else:
            gated = [(i, False) for i in self.semantic_candidate_indices(jd_term, candidates)]
        if not gated:
            return None
        gt = generic_threshold if generic_threshold is not None else threshold
        vectors = embeddings.embed_texts(
            [normalize_term(jd_term), *[candidates[i] for i, _ in gated]]
        )
        jd_vec, cand_vecs = vectors[0], vectors[1:]
        best_idx, best_score = -1, 0.0
        for local_i, (cand_i, generic_only) in enumerate(gated):
            score = embeddings.cosine(jd_vec, cand_vecs[local_i])
            floor = gt if generic_only else threshold
            # only candidates clearing their own floor are eligible; among those,
            # strict > keeps the first-seen winner on ties (deterministic)
            if score >= floor and score > best_score:
                best_idx, best_score = cand_i, score
        if best_idx >= 0:
            return candidates[best_idx], best_score, credit
        return None

    def match_in_text(self, jd_term: str, normalized_text: str) -> tuple[str, str] | None:
        """Word-boundary search of the JD term (and alias forms) inside prose.

        Only exact/alias forms — no fuzzy in free text (false positives are
        worse than misses). Short single-token forms are unsearchable in prose
        UNLESS individually vetted in _PROSE_SEARCHABLE_SHORT_FORMS (e.g. "ml");
        other registered short aliases like "tf" stay skipped — see the
        allowlist comment for the TF-IDF false positive.
        Returns (kind, form) — kind is "exact" or "alias", form is the
        normalized form string actually found — or None.
        """
        for i, form in enumerate(self.all_forms(jd_term)):
            if (
                len(form) < _MIN_CONTAINMENT_LEN
                and " " not in form
                and form not in _PROSE_SEARCHABLE_SHORT_FORMS
            ):
                continue
            if term_in_text(form, normalized_text):
                return ("exact" if i == 0 else "alias"), form
        return None

    def _known_distinct_groups(self, a: str, b: str) -> bool:
        """Both terms are registered alias forms whose canonicals differ."""
        canon_a = self._alias_to_canonical.get(a)
        canon_b = self._alias_to_canonical.get(b)
        return canon_a is not None and canon_b is not None and canon_a != canon_b

    @staticmethod
    def _tokens_contained(shorter: list[str], longer: list[str]) -> bool:
        if not shorter or len(shorter) >= len(longer):
            return False
        if any(len(t) < _MIN_CONTAINMENT_LEN for t in shorter):
            return False
        if all(t in _CONTAINMENT_STOPWORDS for t in shorter):
            return False
        return all(t in longer for t in shorter)
