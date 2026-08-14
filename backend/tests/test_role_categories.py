"""The specific-role layer: display/search/alias only, never storable.

The whole point of this layer is what it does NOT do. Roles must not reach
`all_keys()` (that is what jobs, base resumes and analytics store) and must not
reach `title_families()` (that is what `config_version` hashes and what
`propose_from_resume` requires to stay unambiguous).
"""

import re
from textwrap import dedent

import pytest

from app.services import role_categories


@pytest.fixture
def vocabulary(tmp_path, monkeypatch):
    """Run a synthetic YAML through the real loader.

    Returns a callable that writes the file and forces a reload, so a test can
    assert on data the shipped vocabulary must never contain.

    `_load` is lru_cached at module scope, so the cache is cleared on BOTH
    sides: a synthetic vocabulary leaking into the rest of the suite would be a
    far worse bug than any this file pins.
    """

    def load(text: str) -> None:
        path = tmp_path / "role_categories.yaml"
        path.write_text(dedent(text), encoding="utf-8")
        monkeypatch.setattr(role_categories, "_DATA_FILE", path)
        role_categories._load.cache_clear()
        role_categories._load()

    role_categories._load.cache_clear()
    yield load
    role_categories._load.cache_clear()


def test_no_role_is_a_storable_value():
    storable = set(role_categories.all_keys())
    for category in role_categories.keys():
        for role in role_categories.roles_for(category):
            assert role["key"] not in storable
            assert role_categories.parent_of(role["key"]) == category


def test_no_role_leaks_into_the_title_families():
    # The families are what `config_version` hashes, so this is the property
    # that keeps stored ATS scores comparable across this change.
    families = role_categories.title_families()
    assert set(families) == set(role_categories.keys())
    for category in role_categories.keys():
        for role in role_categories.roles_for(category):
            assert role["key"] not in families
            for other, members in families.items():
                if other == category:
                    # A role label restating its OWN category's adjacent string
                    # is intentional. See the YAML header.
                    continue
                lowered = [member.lower() for member in members]
                assert role["label"].lower() not in lowered


def test_only_deliberately_flat_families_have_no_nested_roles():
    roleless = {
        category
        for category in role_categories.keys()
        if not role_categories.roles_for(category)
    }
    assert roleless == {"bi_developer", "database_administrator"}
    assert {
        "key": "product_data_scientist",
        "label": "Product Data Scientist",
    } in role_categories.roles_for("data_scientist")


def test_a_category_is_its_own_parent():
    # Callers treat category keys and role keys uniformly, so a category
    # resolves to itself rather than to None.
    assert role_categories.parent_of("data_scientist") == "data_scientist"
    assert role_categories.parent_of("other") == "other"
    assert role_categories.parent_of("nonsense_role") is None


def test_the_accessors_tolerate_a_missing_value():
    # Both take an Optional so a caller can pass a nullable column straight in.
    assert role_categories.parent_of(None) is None
    assert role_categories.roles_for(None) == []


def test_role_aliases_resolve_to_the_parent_category():
    # The payoff for extraction: a JD answering with a specific title lands in
    # the right coarse bucket instead of falling to `other`.
    assert role_categories.normalize("Product Data Scientist") == "data_scientist"
    assert role_categories.normalize("Deep Learning Engineer") == "ai_ml_engineer"


def test_a_category_alias_still_resolves():
    # Renamed from "..._win_over_role_aliases": since the alias guard landed, a
    # role alias contesting a category alias RAISES, so there is no silent
    # contest left for this to win. It pins plain category-alias resolution.
    assert role_categories.normalize("data science") == "data_scientist"


def test_label_for_prefers_the_curated_role_label():
    # Humanizing these mangles them: "Llmops Engineer", "Dbt Developer".
    assert role_categories.label_for("llmops_engineer") == "LLMOps Engineer"
    assert role_categories.label_for("dbt_developer") == "dbt Developer"
    # Contract unchanged for everything else.
    assert role_categories.label_for("data_scientist") == "Data Scientist"
    assert role_categories.label_for(None) == "Unknown"
    assert role_categories.label_for("never_declared") == "Never Declared"


def test_title_families_cannot_be_mutated_through_the_accessor():
    # The lists are hashed into `config_version`; a caller appending to one
    # would change scores under a version claiming they are comparable.
    role_categories.title_families()["data_scientist"].append("astronaut")
    assert "astronaut" not in role_categories.title_families()["data_scientist"]


def test_normalized_adjacent_phrases_are_owned_by_exactly_one_family():
    owners: dict[str, str] = {}
    for category, phrases in role_categories.title_families().items():
        for phrase in phrases:
            normalized = re.sub(r"[^a-z0-9]+", " ", phrase.casefold()).strip()
            assert normalized not in owners, (
                f"{normalized!r} is adjacent to both {owners.get(normalized)!r} "
                f"and {category!r}"
            )
            owners[normalized] = category


def test_a_role_key_may_not_shadow_a_category(vocabulary):
    # The shadowed category is declared BELOW the offending role on purpose:
    # this guard can only see it because pass 1 registers every category before
    # pass 2 reads any role. Collapse the two passes back into one and the role
    # sails through, silently outranking a storable key.
    with pytest.raises(ValueError, match="collides with an existing key: beta"):
        vocabulary(
            """
            categories:
              - key: alpha
                roles:
                  - {key: beta, label: Beta}
              - key: beta
            """
        )


def test_a_role_key_may_not_be_declared_twice(vocabulary):
    with pytest.raises(ValueError, match="collides with an existing key: shared_role"):
        vocabulary(
            """
            categories:
              - key: alpha
                roles:
                  - {key: shared_role, label: Shared Role}
              - key: beta
                roles:
                  - {key: shared_role, label: Shared Role}
            """
        )


def test_a_role_key_may_not_be_another_categorys_alias(vocabulary):
    # normalize() would answer `alpha` while parent_of() answered `beta`.
    with pytest.raises(ValueError, match="already an alias of 'alpha'"):
        vocabulary(
            """
            categories:
              - key: alpha
                aliases: [beta_role]
              - key: beta
                roles:
                  - {key: beta_role, label: Beta Role}
            """
        )


def test_two_roles_may_not_claim_one_alias(vocabulary):
    # The headline ambiguity: without this guard "shared" resolves to whichever
    # category the YAML happens to list first.
    with pytest.raises(ValueError, match="'shared' under 'b_role' is already claimed by 'alpha'"):
        vocabulary(
            """
            categories:
              - key: alpha
                roles:
                  - {key: a_role, label: A Role, aliases: [shared]}
              - key: beta
                roles:
                  - {key: b_role, label: B Role, aliases: [shared]}
            """
        )


def test_a_role_alias_may_not_contest_a_category_alias(vocabulary):
    # Also the pass-ordering test, which is why the ROLE's category is declared
    # first: pass 1 still registers `data_analyst`'s claim before pass 2 reads
    # the role, so the role is refused. Collapse the two passes into one and
    # this stops raising — the role would register `crossover` first and the
    # category's own alias would lose the `setdefault`, silently.
    with pytest.raises(ValueError, match="already claimed by 'data_analyst'"):
        vocabulary(
            """
            categories:
              - key: data_engineer
                roles:
                  - {key: pipeline_analyst, label: Pipeline Analyst, aliases: [crossover]}
              - key: data_analyst
                aliases: [crossover]
            """
        )


def test_a_role_may_restate_an_alias_of_its_own_category(vocabulary):
    # The intentional case, shipped three times over
    # (machine_learning_engineer, product_analyst, ml_platform_engineer):
    # spelling a role out as its parent's alias is not a collision.
    vocabulary(
        """
        categories:
          - key: ai_ml_engineer
            label: AI/ML Engineer
            aliases: [machine_learning_engineer]
            roles:
              - {key: machine_learning_engineer, label: Machine Learning Engineer}
        """
    )
    assert role_categories.normalize("machine learning engineer") == "ai_ml_engineer"
    assert role_categories.parent_of("machine_learning_engineer") == "ai_ml_engineer"


def test_industry_wide_catalog_has_the_fixed_25_family_cut():
    assert set(role_categories.keys()) == {
        "data_scientist",
        "data_analyst",
        "data_engineer",
        "ai_ml_engineer",
        "analytics_engineer",
        "business_analyst",
        "bi_developer",
        "research_scientist",
        "software_engineer",
        "mlops_engineer",
        "security_engineer",
        "platform_engineer",
        "product_manager",
        "engineering_manager",
        "qa_engineer",
        "it_support",
        "network_engineer",
        "database_administrator",
        "solutions_engineer",
        "enterprise_apps_consultant",
        "devrel",
        "forward_deployed_engineer",
        "technical_program_manager",
        "supply_chain_analyst",
        "embedded_engineer",
    }


@pytest.mark.parametrize(
    "category,alias,roles",
    [
        ("qa_engineer", "software tester", {"sdet", "automation_test_engineer"}),
        (
            "it_support",
            "desktop support",
            {"help_desk_specialist", "systems_administrator", "cloud_administrator"},
        ),
        ("network_engineer", "network administrator", {"network_architect"}),
        ("database_administrator", "dba", set()),
        (
            "solutions_engineer",
            "sales engineer",
            {"solutions_architect", "sales_engineer", "technical_account_manager"},
        ),
        (
            "enterprise_apps_consultant",
            "salesforce developer",
            {"salesforce_consultant", "sap_consultant", "erp_consultant"},
        ),
        ("devrel", "devrel engineer", {"developer_advocate"}),
        (
            "forward_deployed_engineer",
            "fde",
            {"applied_ai_engineer"},
        ),
        (
            "technical_program_manager",
            "tpm",
            {"it_project_manager", "scrum_master"},
        ),
        (
            "supply_chain_analyst",
            "supply chain planner",
            {"supply_chain_manager", "logistics_analyst"},
        ),
        (
            "embedded_engineer",
            "embedded software engineer",
            {"firmware_engineer", "hardware_engineer"},
        ),
    ],
)
def test_new_families_keep_required_aliases_and_specific_roles(category, alias, roles):
    assert role_categories.normalize(alias) == category
    assert {role["key"] for role in role_categories.roles_for(category)} == roles


def test_security_category_is_broadened_without_changing_its_key():
    assert role_categories.label_for("security_engineer") == (
        "Security / Cybersecurity Engineer"
    )
    assert role_categories.normalize("cybersecurity engineer") == "security_engineer"
    assert role_categories.normalize("cybersecurity analyst") == "security_engineer"
    assert {"security_analyst", "grc_analyst"} <= {
        role["key"] for role in role_categories.roles_for("security_engineer")
    }


def test_description_accessor_is_optional_and_category_scoped():
    assert role_categories.description_for("forward_deployed_engineer") == (
        "Embeds with customers to adapt and deploy software or AI solutions "
        "in real operating environments."
    )
    assert role_categories.description_for("qa_engineer") is None
    assert role_categories.description_for("other") is None


@pytest.mark.parametrize(
    "title,category",
    [
        ("Decision Scientist", "data_scientist"),
        ("Experimentation Scientist", "data_scientist"),
        ("Marketing Data Scientist", "data_scientist"),
        ("Streaming Data Engineer", "data_engineer"),
        ("Reporting Analyst", "data_analyst"),
        ("Growth Analyst", "data_analyst"),
        ("Tableau Developer", "bi_developer"),
        ("Power BI Developer", "bi_developer"),
        ("Looker Developer", "bi_developer"),
        ("NLP Engineer", "ai_ml_engineer"),
        ("Computer Vision Engineer", "ai_ml_engineer"),
        ("Prompt Engineer", "ai_ml_engineer"),
    ],
)
def test_pruned_specific_titles_remain_reachable_as_category_aliases(title, category):
    assert role_categories.match_free_text(title) == {
        "role": None,
        "category": category,
        "label": title,
        "confidence": "alias",
    }


def test_platform_engineer_no_longer_ties_with_software_engineer():
    # `software_engineer.adjacent` used to claim "platform engineer". Left in
    # place alongside the new category, propose_from_resume would see two
    # matches, tie, and return `unknown` — the exact failure the layered design
    # exists to avoid.
    families = role_categories.title_families()
    assert "platform engineer" not in families["software_engineer"]
    assert "platform engineer" in families["platform_engineer"]


def test_a_platform_engineer_resume_resolves_to_one_category():
    proposed = role_categories.propose_from_resume(
        {"experience": [{"role": "Platform Engineer"}]}
    )
    assert proposed == "platform_engineer"


@pytest.mark.parametrize(
    "title,category",
    [
        ("Forward Deployed Engineer", "forward_deployed_engineer"),
        ("QA Engineer", "qa_engineer"),
        ("Supply Chain Analyst", "supply_chain_analyst"),
        ("QA Engineer / Software Engineer", "unknown"),
    ],
)
def test_expanded_catalog_proposal_smoke_corpus(title, category):
    assert role_categories.propose_from_resume(
        {"experience": [{"role": title}]}
    ) == category


@pytest.mark.parametrize(
    "title",
    ["Applied AI Engineer", "Embedded Software Engineer"],
)
def test_catalog_owned_title_never_proposes_a_different_family(title):
    match = role_categories.match_free_text(title)
    assert match["category"] is not None
    assert role_categories.propose_from_resume(
        {"experience": [{"role": title}]}
    ) == "unknown"


@pytest.mark.parametrize(
    "title, category",
    [
        # The four titles the new categories exist FOR: before they landed,
        # every one of these proposed nothing a base resume could be created
        # for. Pinned as a corpus because the new `adjacent` lists add ~16
        # title strings to a SUBSTRING matcher with an exactly-one-match rule,
        # so the risk is not that these fail — it is that they start tying.
        ("Security Engineer", "security_engineer"),
        ("Application Security Engineer", "security_engineer"),
        ("Information Security Analyst", "security_engineer"),
        ("Platform Engineer", "platform_engineer"),
        ("DevOps Engineer", "platform_engineer"),
        ("Site Reliability Engineer", "platform_engineer"),
        ("Product Manager", "product_manager"),
        ("Technical Product Manager", "product_manager"),
        ("Engineering Manager", "engineering_manager"),
        ("Data Science Manager", "engineering_manager"),
        ("Analytics Manager", "engineering_manager"),
        # …and the neighbours they must not have stolen.
        ("Data Scientist", "data_scientist"),
        ("Software Engineer", "software_engineer"),
        ("Backend Engineer", "software_engineer"),
        ("Machine Learning Engineer", "ai_ml_engineer"),
        ("MLOps Engineer", "mlops_engineer"),
        # Already ambiguous before this change: "data platform engineer" is in
        # `data_engineer.adjacent` while "platform engineer" now sits under
        # `platform_engineer` (it sat under `software_engineer` before). The
        # tie is inherited, not new, and `unknown` is the honest answer.
        ("Data Platform Engineer", "unknown"),
        # The one title in the corpus this change made LESS specific, pinned so
        # it is visible rather than silent. `platform_engineer.adjacent` claims
        # "infrastructure engineer", which is a substring of
        # `mlops_engineer.adjacent`'s "machine learning infrastructure
        # engineer", so the two families now tie where mlops used to win alone.
        #
        # Left as `unknown` on purpose. Exact adjacent phrases are now disjoint,
        # but the shorter Platform-family phrase remains a substring of the
        # MLOps-family title. Resolving that needs a matching-rule change, not a
        # duplicate-list cleanup.
        ("Machine Learning Infrastructure Engineer", "unknown"),
    ],
)
def test_propose_from_resume_over_a_realistic_title_corpus(title, category):
    assert role_categories.propose_from_resume(
        {"experience": [{"role": title}]}
    ) == category


@pytest.mark.parametrize(
    "titles,category",
    [
        # Recency: the current title is one family, so an older different
        # family no longer poisons the guess (the joined-haystack rule did).
        (["Engineering Manager", "Software Engineer"], "engineering_manager"),
        (["Data Science Manager", "Senior Data Scientist"], "engineering_manager"),
        # Still unambiguous when both titles sit in ONE family.
        (["Senior Data Scientist", "Data Scientist"], "data_scientist"),
    ],
)
def test_propose_from_resume_reads_the_two_most_recent_titles_independently(titles, category):
    assert role_categories.propose_from_resume(
        {"experience": [{"role": t} for t in titles]}
    ) == category


@pytest.mark.parametrize(
    "display_name,summary,titles,expected",
    [
        # Filename is the user's own statement of the target; it beats history.
        ("data engineer", "", ["Business Analyst", "Data Analyst"], "data_engineer"),
        # SUMMARY usually names the role; it beats older titles.
        (None, "Data Scientist with 5 years in analytics.", ["Business Analyst"], "data_scientist"),
        # An ambiguous summary (two families) falls through to a clear title.
        (
            None,
            "Mentored a data engineer and a data analyst across the org.",
            ["Data Scientist", "Business Analyst"],
            "data_scientist",
        ),
        # Recency: the current title wins over an older different family.
        (None, "", ["Data Scientist", "Business Analyst"], "data_scientist"),
        # Two families in the only signal: stay unknown. Never YAML-order.
        (None, "", ["Data Engineer / Analytics Engineer"], "unknown"),
        # Every signal empty or ambiguous: the honesty property.
        (
            None,
            "Mentored a data engineer and a data analyst across the org.",
            ["Data Engineer / Analytics Engineer"],
            "unknown",
        ),
        # Word-boundary: a substring of "analyst" must not mint the analyst family.
        (None, "", ["Analystics"], "unknown"),
        # Word-boundary, the DISCRIMINATING case: "data analyst" is a plain
        # substring of "Data Analystics" (…analyst|ics…), so a naive `in`
        # check proposes data_analyst here — only \b-anchored matching stays
        # unknown. Review-added after a mutation check showed the row above
        # passes under substring matching too (no family phrase is a
        # substring of bare "Analystics" either way).
        (None, "", ["Data Analystics Platform Lead"], "unknown"),
        # No signals at all.
        (None, "", [], "unknown"),
    ],
)
def test_propose_from_resume_priority_cascade(
    display_name, summary, titles, expected
):
    data = {
        "summary": summary,
        "experience": [{"role": t} for t in titles],
    }
    assert role_categories.propose_from_resume(data, display_name=display_name) == expected


def test_two_categories_may_not_claim_one_alias(vocabulary):
    # The category layer's mirror of `test_two_roles_may_not_claim_one_alias`,
    # and the layer where it matters MORE: these keys are what actually gets
    # stored on a job and a base resume. Without this, the winner of a
    # duplicate category alias is YAML file order.
    with pytest.raises(ValueError, match="'shared' under 'beta' is already claimed by 'alpha'"):
        vocabulary(
            """
            categories:
              - key: alpha
                aliases: [shared]
              - key: beta
                aliases: [shared]
            """
        )


def test_an_empty_alias_is_skipped_rather_than_claimed(vocabulary):
    # Both categories declare an alias that slugs to "". Without pass 1's
    # `if not slug: continue`, the second one collides with the first on the
    # empty string and the whole vocabulary refuses to load — a spurious raise
    # from a guard meant to catch real ambiguity. Pinned because that line
    # otherwise reads as dead code to the next editor, which is exactly how the
    # equivalent redundancy in pass 2 nearly got deleted.
    vocabulary(
        """
        categories:
          - key: alpha
            aliases: ["-"]
          - key: beta
            aliases: ["!"]
        """
    )
    assert role_categories.normalize("alpha") == "alpha"
    assert role_categories.normalize("beta") == "beta"


def test_a_category_may_restate_its_own_alias(vocabulary):
    # Key, label and declared aliases all funnel through the same loop, so a
    # category naming itself twice must stay silent — otherwise a label that
    # slugs to its own key (the common case) would refuse to load.
    vocabulary(
        """
        categories:
          - key: data_science
            label: Data Science
            aliases: [data_science, Data Science, ds]
        """
    )
    assert role_categories.normalize("ds") == "data_science"
    assert role_categories.normalize("Data Science") == "data_science"


def test_match_exact_category():
    assert role_categories.match_free_text("Data Scientist") == {
        "role": "data_scientist", "category": "data_scientist",
        "label": "Data Scientist", "confidence": "exact",
    }


def test_match_exact_role():
    assert role_categories.match_free_text("quantitative researcher") == {
        "role": "quantitative_researcher", "category": "research_scientist",
        "label": "Quantitative Researcher", "confidence": "exact",
    }


def test_match_by_alias_keeps_the_users_words():
    # An alias hit is a SUGGESTION, so the label stays what the user typed —
    # the UI asks them to confirm before the mapping counts.
    match = role_categories.match_free_text("Quant")
    assert match["role"] == "quantitative_researcher"
    assert match["category"] == "research_scientist"
    assert match["label"] == "Quant"
    assert match["confidence"] == "alias"


def test_a_role_owned_alias_still_names_its_role():
    # `alias_to_key` only knows the category, so this used to answer role=None —
    # meaning the abbreviation an alias was WRITTEN for lost the catalog entry
    # it points at, and the picker offered only the coarse category.
    assert role_categories.match_free_text("genai engineer") == {
        "role": "generative_ai_engineer", "category": "ai_ml_engineer",
        "label": "genai engineer", "confidence": "alias",
    }


def test_a_category_owned_alias_names_no_role():
    # The other branch: nothing more specific exists, so `role` stays None
    # rather than inventing one.
    assert role_categories.match_free_text("data science") == {
        "role": None, "category": "data_scientist",
        "label": "data science", "confidence": "alias",
    }


def test_match_gives_up_rather_than_guessing():
    match = role_categories.match_free_text("Underwater Basket Weaver")
    assert match == {
        "role": None, "category": None,
        "label": "Underwater Basket Weaver", "confidence": "none",
    }


def test_match_does_not_read_the_storage_sentinels_as_roles():
    # Deliberate divergence from `normalize()`, which maps both to themselves.
    # `other`/`unknown` are storage decisions, not words a person types to name
    # a job: "Count this as Unknown?" is not a question worth asking. Pinned
    # because a mutation returning `exact` here is otherwise invisible.
    for sentinel in ("other", "unknown", "Other", "Unknown"):
        assert role_categories.match_free_text(sentinel) == {
            "role": None, "category": None,
            "label": sentinel, "confidence": "none",
        }


def test_match_of_blank_input():
    # The full dict, so this pins the blank guard rather than the incidental
    # fact that "" misses all three maps anyway.
    assert role_categories.match_free_text("   ") == {
        "role": None, "category": None, "label": "", "confidence": "none",
    }


def test_match_strips_a_rank_prefix_and_downgrades_to_alias():
    # A rank-prefixed title is the likeliest thing typed into a role box, and
    # the rank is not part of the job. Never `exact`: the catalog did not
    # contain what they typed, so the user still confirms.
    senior = role_categories.match_free_text("Senior Data Scientist")
    assert senior == {
        "role": "data_scientist", "category": "data_scientist",
        "label": "Senior Data Scientist", "confidence": "alias",
    }
    assert role_categories.match_free_text("Staff ML Engineer") == {
        "role": None, "category": "ai_ml_engineer",
        "label": "Staff ML Engineer", "confidence": "alias",
    }


@pytest.mark.parametrize(
    "typed, category",
    [
        ("Lead Data Analyst", "data_analyst"),
        ("Data Scientist II", "data_scientist"),
        ("Sr. Data Scientist", "data_scientist"),
        ("Entry Level Data Analyst", "data_analyst"),
        ("Junior Computer Vision Engineer", "ai_ml_engineer"),
    ],
)
def test_rank_markers_strip_in_every_shipped_shape(typed, category):
    # Suffix numerals, abbreviations, and the multi-word phrase that must be
    # consumed whole — "entry level" losing only "entry" would strand "level".
    match = role_categories.match_free_text(typed)
    assert match["category"] == category
    assert match["confidence"] == "alias"
    assert match["label"] == typed


def test_stripping_a_rank_cannot_manufacture_a_match():
    # The strip is not a licence to guess: it only ever retries the same three
    # exact lookups, so a novel role stays novel.
    assert role_categories.match_free_text("Senior Underwater Basket Weaver") == {
        "role": None, "category": None,
        "label": "Senior Underwater Basket Weaver", "confidence": "none",
    }
    # A title that is nothing but a rank has no core to look up.
    assert role_categories.match_free_text("Senior")["confidence"] == "none"


def test_matching_survives_a_vocabulary_with_no_seniority_block(vocabulary):
    # A hand-edited or older YAML has no `seniority:` key, which the loader
    # degrades to an empty vocabulary rather than raising. The rank-strip retry
    # must degrade with it — a no-op — instead of taking the picker down.
    vocabulary(
        """
        categories:
          - key: alpha
            label: Alpha
            roles:
              - {key: alpha_role, label: Alpha Role, aliases: [ar]}
        """
    )
    assert role_categories.seniority_always() == ()
    assert role_categories.match_free_text("Senior Alpha")["confidence"] == "none"
    # And the role-alias index is built by the loader, not hardcoded for the
    # shipped file.
    assert role_categories.match_free_text("ar") == {
        "role": "alpha_role", "category": "alpha",
        "label": "ar", "confidence": "alias",
    }


def test_the_rank_strip_is_not_cached_across_vocabularies(vocabulary):
    # ONE input, two vocabularies, two answers — which is what makes this the
    # only test that can catch an `lru_cache` on `_strip_rank_markers`. The
    # fixture clears `_load`, not a helper's own cache, so a cached strip would
    # answer the second assertion with the first vocabulary's rank markers.
    # Every other test here asks each slug once, so the cache stays invisible.
    assert role_categories.match_free_text("Senior Data Scientist")["confidence"] == "alias"
    vocabulary(
        """
        categories:
          - key: data_scientist
            label: Data Scientist
        """
    )
    assert role_categories.match_free_text("Senior Data Scientist")["confidence"] == "none"


def test_a_trailing_rank_word_that_is_the_job_survives():
    # `lead`/`staff`/`associate`/`principal` are head nouns in the suffix
    # position. Stripping "Tech Lead" down to "tech" is the exact regression
    # `seniority_prefix_only` exists to prevent, so the two lists must not be
    # merged into one anywhere-strip pass.
    assert role_categories._strip_rank_markers("tech_lead") == "tech_lead"
    assert role_categories._strip_rank_markers("lead_data_analyst") == "data_analyst"
    # Pass 2 before pass 3: "Senior Associate" keeps `associate` rather than
    # reducing to nothing.
    assert role_categories._strip_rank_markers("senior_associate") == "associate"
