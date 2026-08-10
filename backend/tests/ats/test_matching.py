import pytest

from app.services.ats import embeddings, matching
from app.services.ats.config import AtsConfig, load_config
from app.services.ats.matching import SkillMatcher, normalize_term
from tests.ats.fixtures import fake_embed_texts


def _match(m, jd_term, resume_terms):
    """Lexical stages then adjacency — the engine's outer cascade lives in
    layers (with prose/semantic stages between), not on SkillMatcher; this
    helper composes the two split methods for compact full-cascade asserts."""
    form, term, credit = m.match_terms_lexical(jd_term, resume_terms)
    if form is not None:
        return form, term, credit
    return m.adjacency_match(jd_term, resume_terms) or (None, None, 0.0)


def _matcher() -> SkillMatcher:
    return SkillMatcher(load_config())


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("Zürich", "zurich"),
        ("Nestlé", "nestle"),
        ("Montréal", "montreal"),
        ("Müller", "muller"),
        ("café", "cafe"),
    ],
)
def test_normalize_term_folds_accented_latin_to_base_letters(term, expected):
    assert normalize_term(term) == expected


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("C++", "c++"),
        ("C#", "c#"),
        ("Node.js", "node.js"),
        ("CI/CD", "ci/cd"),
        ("  Power-BI! ", "power bi"),
    ],
)
def test_normalize_term_preserves_matcher_punctuation_contract(term, expected):
    assert normalize_term(term) == expected


def test_normalize_term_keeps_non_latin_out_of_ascii_matching_lane():
    assert normalize_term("機械学習") == ""


def test_exact_match():
    form, term, credit = _match(_matcher(), "Python", {"python", "sql"})
    assert (form, term, credit) == ("exact", "python", 1.0)


def test_alias_match():
    form, term, credit = _match(_matcher(), "AWS", {"amazon web services"})
    assert (form, credit) == ("alias", 1.0)


def test_containment_match():
    form, term, credit = _match(_matcher(), "Microsoft Teams", {"teams"})
    assert (form, credit) == ("fuzzy", 1.0)


def test_containment_rejects_tiny_tokens():
    # "r" ⊂ anything would be a false positive
    form, _, _ = _match(_matcher(), "R", {"ruby on rails"})
    assert form is None


def test_edit_distance_typo():
    form, _, credit = _match(_matcher(), "postgresql", {"postgresql"})
    assert (form, credit) == ("exact", 1.0)
    form, _, credit = _match(_matcher(), "postgresql", {"postgresqll"})
    assert (form, credit) == ("fuzzy", 1.0)


def test_edit_distance_rejects_short_terms():
    # near-misses between short terms are distinct skills, not typos
    m = _matcher()
    assert _match(m, "MySQL", {"mssql"}) == (None, None, 0.0)
    assert _match(m, "R", {"c"}) == (None, None, 0.0)
    assert _match(m, "SAS", {"saas"}) == (None, None, 0.0)
    assert _match(m, "C#", {"c"}) == (None, None, 0.0)


def test_edit_distance_rejects_distinct_alias_groups():
    # js and ts are both known alias forms with different canonicals
    assert _match(_matcher(), "js", {"ts"}) == (None, None, 0.0)


def test_containment_rejects_stopword_only_terms():
    # a bare vendor token must not match every product of that vendor
    form, _, _ = _match(_matcher(), "Microsoft Teams", {"microsoft"})
    assert form is None


def test_adjacency_match_capped():
    form, term, credit = _match(_matcher(), "Snowflake", {"bigquery"})
    assert (form, term) == ("adjacent", "bigquery")
    assert credit <= 0.5


def test_adjacency_prefers_highest_credit():
    cfg = AtsConfig(
        weights={"adjacency_max_credit": 0.5, "fuzzy_max_distance": 1},
        aliases=[],
        adjacency={"snowflake": {"bigquery": 0.3, "redshift": 0.5}},
        title_families={},
        version="test",
    )
    form, term, credit = _match(SkillMatcher(cfg), "Snowflake", {"bigquery", "redshift"})
    assert (form, term, credit) == ("adjacent", "redshift", 0.5)


def test_canonical():
    m = _matcher()
    assert m.canonical("AWS") == "amazon web services"
    assert m.canonical("Power-BI") == "power bi"
    assert m.canonical("some unknown skill") == "some unknown skill"


def test_all_forms():
    m = _matcher()
    forms = m.all_forms("AWS")
    assert forms[0] == "aws"
    assert "amazon web services" in forms
    assert len(forms) == len(set(forms))
    assert m.all_forms("Rust") == ["rust"]


def test_no_match():
    form, term, credit = _match(_matcher(), "Salesforce", {"python"})
    assert (form, term, credit) == (None, None, 0.0)


def test_text_search_forms():
    m = _matcher()
    # exact token in prose; returns (kind, form actually found)
    assert m.match_in_text("Python", "built python etl pipelines") == ("exact", "python")
    # alias form in prose
    assert m.match_in_text("AWS", "deployed on amazon web services infra") == ("alias", "amazon web services")
    # no substring-inside-word false positive
    assert m.match_in_text("R", "premier league") is None


def test_text_search_short_registered_alias_forms():
    m = _matcher()
    # "ml" is on the vetted prose allowlist -> searchable in prose
    assert m.match_in_text("Machine Learning", "shipped ml pipelines") == ("alias", "ml")
    # boundary guard keeps allowlisted short forms out of html/xml
    assert m.match_in_text("Machine Learning", "parsed xml and html files") is None
    # unregistered short terms stay unsearchable in prose
    assert m.match_in_text("R", "premier league") is None


def test_text_search_short_alias_not_allowlisted_is_skipped():
    m = _matcher()
    # "tf" is a registered tensorflow alias but NOT prose-allowlisted:
    # "TF-IDF" normalizes to "tf idf" and the space is a word boundary, so
    # searching "tf" in prose would false-positive on it
    assert m.match_in_text("TensorFlow", "implemented tf idf vectorization") is None


def test_term_in_text_word_boundaries():
    assert not matching.term_in_text("ml engineer", "built xml engineering pipelines")
    assert matching.term_in_text("data scientist", "senior data scientist consultant")


# --- lexical / adjacency split -----------------------------------------------


def test_match_terms_lexical_hits_all_lexical_stages():
    m = _matcher()
    assert m.match_terms_lexical("Python", {"python"}) == ("exact", "python", 1.0)
    form, _, credit = m.match_terms_lexical("AWS", {"amazon web services"})
    assert (form, credit) == ("alias", 1.0)
    form, _, credit = m.match_terms_lexical("Microsoft Teams", {"teams"})
    assert (form, credit) == ("fuzzy", 1.0)
    form, _, credit = m.match_terms_lexical("postgresql", {"postgresqll"})
    assert (form, credit) == ("fuzzy", 1.0)


def test_match_terms_lexical_excludes_adjacency():
    # Snowflake/bigquery is an adjacency pair: no lexical hit...
    assert _matcher().match_terms_lexical("Snowflake", {"bigquery"}) == (None, None, 0.0)


def test_adjacency_match_finds_adjacent_pair():
    # ...but adjacency_match finds it
    result = _matcher().adjacency_match("Snowflake", {"bigquery"})
    assert result is not None
    form, term, credit = result
    assert (form, term) == ("adjacent", "bigquery")
    assert credit <= 0.5


def test_adjacency_match_returns_none_without_adjacency():
    assert _matcher().adjacency_match("Salesforce", {"python"}) is None


def test_match_terms_still_covers_all_stages():
    # backward compat: match_terms = lexical stages + adjacency, unchanged shape
    m = _matcher()
    assert _match(m, "Python", {"python"}) == ("exact", "python", 1.0)
    form, term, _ = _match(m, "Snowflake", {"bigquery"})
    assert (form, term) == ("adjacent", "bigquery")
    assert _match(m, "Salesforce", {"python"}) == (None, None, 0.0)


# --- semantic stage -----------------------------------------------------------
# Cosines below are hand-computed from the fake's 4-D vectors; see fixtures.py.


@pytest.fixture()
def fake_embedder(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_texts", fake_embed_texts)


def test_semantic_match_hit_above_threshold(fake_embedder):
    # "machine learning" <-> "shipped ml models to production": share "ml" (alias
    # form) -> gate ok; cos 0.96 >= 0.60 -> hit.
    result = _matcher().semantic_match(
        "Machine Learning",
        ["totally unrelated text", "shipped ml models to production"],
        threshold=0.60,
        credit=0.75,
    )
    assert result is not None
    candidate, score, credit = result
    assert candidate == "shipped ml models to production"
    assert score == pytest.approx(0.96)
    assert credit == 0.75


def test_semantic_match_shared_token_pair_hits(fake_embedder):
    # "statistical modeling" (0,0,0,1,0) <-> "statistical analysis" (0,0,0,0.8,0.6):
    # share "statistical" -> gate ok; cos = 0.8 >= 0.60 -> hit. (A shared-token
    # reformulation the embedding is legitimately good at.)
    result = _matcher().semantic_match(
        "Statistical Modeling", ["statistical analysis"], threshold=0.60, credit=0.6,
    )
    assert result is not None
    assert result[0] == "statistical analysis"
    assert result[1] == pytest.approx(0.8)


def test_semantic_match_zero_overlap_blocked_by_anchor_gate(fake_embedder):
    # "kubernetes" <-> "container orchestration experience": cos 0.96 (well above
    # threshold) BUT zero shared tokens -> the anchor gate blocks it, so no hit.
    # This is the false-positive class the gate exists to kill; the genuine
    # reformulation now lives in adjacency.yaml instead.
    result = _matcher().semantic_match(
        "Kubernetes", ["container orchestration experience"], threshold=0.60, credit=0.6,
    )
    assert result is None


def test_semantic_match_miss_below_threshold(fake_embedder):
    # share "ml" so the gate lets it through, but cos 0.28 < 0.60 -> miss on score.
    result = _matcher().semantic_match(
        "Machine Learning",
        ["container orchestration ml experience"],
        threshold=0.60,
        credit=0.75,
    )
    assert result is None


def test_semantic_match_unrelated_text_misses(fake_embedder):
    # no shared token AND unknown vector -> gate blocks before scoring.
    result = _matcher().semantic_match(
        "Machine Learning",
        ["managed a coffee shop"],
        threshold=0.60,
        credit=0.75,
    )
    assert result is None


def test_semantic_match_empty_candidates(fake_embedder):
    assert _matcher().semantic_match("Machine Learning", [], threshold=0.60, credit=0.75) is None


def test_semantic_match_deterministic_tie_break(fake_embedder):
    # both share "ml" (gate ok) and embed to the same vector (cos 0.96); strict >
    # keeps first-seen.
    candidates = ["shipped ml models to production", "ml systems in production"]
    result = _matcher().semantic_match("Machine Learning", candidates, threshold=0.60, credit=0.75)
    assert result is not None
    assert result[0] == "shipped ml models to production"
    # and with the order reversed, the other one wins — order is the only tie-break
    result_rev = _matcher().semantic_match(
        "Machine Learning", list(reversed(candidates)), threshold=0.60, credit=0.75
    )
    assert result_rev is not None
    assert result_rev[0] == "ml systems in production"


def test_semantic_candidate_indices_gates_on_shared_token(fake_embedder):
    m = _matcher()
    candidates = ["statistical analysis", "container orchestration experience", "ml pipelines"]
    # "Machine Learning" anchors on "machine"/"learning"/"ml" (alias) -> only the
    # "ml pipelines" candidate shares a token.
    assert m.semantic_candidate_indices("Machine Learning", candidates) == [2]
    # a JD term whose only tokens are stopwords anchors nothing
    assert m.semantic_candidate_indices("of the", candidates) == []


# --- generic-anchor two-threshold rule (Task 8) -------------------------------

_GENERIC = {"data", "analysis", "learning", "model", "modeling", "engineering",
            "management", "development", "system", "systems", "design", "analytics",
            "science", "scientist", "analyst", "engineer", "developer", "tool", "tools"}


def test_semantic_gate_flags_generic_only_candidates(fake_embedder):
    m = _matcher()
    # "Data Analysis" anchors on "data"/"analysis" (both generic).
    #   "statistical analysis" shares only "analysis" (generic) -> generic_only True
    #   "spark data pipelines" shares only "data" (generic)      -> generic_only True
    #   "customer analysis dashboards" shares "analysis" only     -> generic_only True
    # A candidate sharing a NON-generic token flips the flag off:
    candidates = ["statistical analysis", "unrelated text", "customer churn analysis"]
    gate = m.semantic_gate("Data Analysis", candidates, generic_anchors=_GENERIC)
    # every gated candidate here shares only generic anchors -> all True
    assert gate == [(0, True), (2, True)]  # index 1 shares nothing -> excluded


def test_semantic_gate_non_generic_anchor_not_flagged(fake_embedder):
    m = _matcher()
    # "Statistical Modeling": anchors "statistical" (non-generic) + "modeling"
    # (generic). A candidate sharing "statistical" is NOT generic-only.
    gate = m.semantic_gate(
        "Statistical Modeling", ["statistical analysis", "data modeling"],
        generic_anchors=_GENERIC,
    )
    # "statistical analysis" shares "statistical" (non-generic) -> False
    # "data modeling" shares only "modeling" (generic)          -> True
    assert gate == [(0, False), (1, True)]


def test_semantic_match_generic_only_needs_higher_threshold(fake_embedder):
    m = _matcher()
    # generic-only anchor: at cos 0.96 it clears the 0.82 generic floor -> hit.
    hit = m.semantic_match(
        "Data Analysis", ["statistical analysis"],
        threshold=0.60, generic_threshold=0.82, generic_anchors=_GENERIC, credit=0.6,
    )
    assert hit is not None and hit[0] == "statistical analysis"


def test_semantic_match_generic_only_below_generic_floor_blocked(fake_embedder):
    m = _matcher()
    # generic-only anchor ("data") at cos 0.60: clears the 0.60 base but NOT the
    # 0.82 generic floor -> blocked. This is the false-positive class the rule
    # exists to kill (Data Structures/Data Mining -> data-analyst bullet at ~0.6).
    hit = m.semantic_match(
        "Data Mining", ["data pipeline chores"],
        threshold=0.60, generic_threshold=0.82, generic_anchors=_GENERIC, credit=0.6,
    )
    assert hit is None


def test_semantic_match_non_generic_anchor_uses_base_threshold(fake_embedder):
    m = _matcher()
    # non-generic anchor ("statistical") -> base 0.60 applies even though the
    # generic floor is 0.82; cos 0.96 clears 0.60 -> hit.
    hit = m.semantic_match(
        "Statistical Modeling", ["statistical analysis"],
        threshold=0.60, generic_threshold=0.82, generic_anchors=_GENERIC, credit=0.6,
    )
    assert hit is not None and hit[0] == "statistical analysis"
