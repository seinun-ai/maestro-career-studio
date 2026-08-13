"""Role-category vocabulary, loaded from data rather than compiled as an enum.

Why this exists: `role_category` used to be a closed 6-value `Literal` covering
four data/AI roles plus `other`/`unknown`. Every role outside that taxonomy —
BI developer, product analyst, research scientist, and all of non-tech — was
forced to `other`, and analytics groups on that column, so unrelated roles piled
into one meaningless bucket.

Three vocabularies had drifted apart:
  * the `RoleCategory` Literal (what could be stored),
  * `title_families.yaml`'s title-cased keys (what the ATS title tier looked
    up — and never matched, making the "adjacent" tier dead in production),
  * `ROLE_CATEGORY_LABELS` (which carried a `hybrid` entry the Literal could
    not produce, and no label for `other`/`unknown`).

All three now derive from `ats/data/role_categories.yaml`. The extraction
prompt's option list is generated from it too, so the prompt cannot drift from
the code. Adding a category for another domain requires no code change.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, TypedDict

import yaml

_DATA_FILE = Path(__file__).parent / "ats" / "data" / "role_categories.yaml"

# Always available, never declared in the YAML.
OTHER = "other"
UNKNOWN = "unknown"
RESERVED: dict[str, str] = {OTHER: "Other", UNKNOWN: "Unknown"}

# Declared here rather than at each consumer so the authority sits with the
# producer: an HTTP layer re-spelling this literal is free to drift from it.
Confidence = Literal["exact", "alias", "none"]


class RoleMatch(TypedDict):
    """What `match_free_text` answers. `label` is always present, never None."""

    role: str | None
    category: str | None
    label: str
    confidence: Confidence


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").strip().lower()).strip("_")


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    raw = yaml.safe_load(_DATA_FILE.read_text(encoding="utf-8")) or {}
    entries = raw.get("categories") or []

    labels: dict[str, str] = {}
    descriptions: dict[str, str] = {}
    families: dict[str, list[str]] = {}
    alias_to_key: dict[str, str] = {}

    roles: dict[str, list[dict[str, str]]] = {}
    role_index: dict[str, dict[str, str]] = {}
    # Parallel to `alias_to_key`, which can only ever answer with a CATEGORY.
    # Without this, "cv engineer" and "Computer Vision Engineer" — spellings the
    # YAML declares to be one job — give structurally different answers, and the
    # abbreviation the alias exists FOR is the one that loses its role key.
    role_alias_index: dict[str, str] = {}

    # Pass 1 — categories. These register FIRST so that a category alias always
    # wins the `setdefault` below: a specific role must never shadow a coarse
    # key, or `normalize()` would route a job into the wrong analytics bucket.
    # The ordering is also what makes pass 2's `role_key in labels` check work
    # at all — collapsing these back into one loop would let a role declared
    # above its colliding category through unnoticed.
    for entry in entries:
        key = _slug(entry.get("key"))
        if not key or key in RESERVED:
            continue
        labels[key] = str(entry.get("label") or key.replace("_", " ").title())
        description = str(entry.get("description") or "").strip()
        if description:
            descriptions[key] = description
        # No loader guard checks `adjacent` for cross-family duplication — that
        # invariant lives ONLY in test_normalized_adjacent_phrases_are_owned_by
        # _exactly_one_family. Deleting that test would let a duplicated phrase
        # load silently and turn propose_from_resume into a tie machine.
        families[key] = [str(t) for t in (entry.get("adjacent") or [])]
        roles[key] = []
        # A key is its own alias, plus its label and any declared aliases.
        for alias in [key, labels[key], *(entry.get("aliases") or [])]:
            slug = _slug(alias)
            if not slug:
                continue
            # The mirror of pass 2's role-alias guard, and the layer where it
            # matters MORE: these keys are what a job and a base resume STORE,
            # so a duplicate decided by YAML file order routes rows into the
            # wrong analytics bucket permanently. A category re-claiming its own
            # slug is ordinary — key, label and aliases all funnel through here,
            # and a label usually slugs straight back to its key.
            owner = alias_to_key.get(slug)
            if owner is not None and owner != key:
                raise ValueError(
                    f"category alias {slug!r} under {key!r} is already "
                    f"claimed by {owner!r}, so normalize() would decide by "
                    f"file order"
                )
            alias_to_key.setdefault(slug, key)

    # Pass 2 — specific roles. Display, search and aliasing only. They are
    # deliberately absent from `families`: `propose_from_resume` proposes only
    # when EXACTLY ONE family matches, so diluting the families would turn
    # ordinary titles into ties, i.e. `unknown`.
    for entry in entries:
        key = _slug(entry.get("key"))
        if key not in labels:
            continue
        for role in entry.get("roles") or []:
            role_key = _slug(role.get("key"))
            if not role_key:
                continue
            if role_key in labels or role_key in role_index or role_key in RESERVED:
                raise ValueError(f"role key collides with an existing key: {role_key}")
            # Deliberately redundant with the alias guard below, which re-checks
            # `role_key` as the first entry of the alias loop. Kept because this
            # case is a key/alias CONTRADICTION, not a file-order tie, and the
            # generic message would misdiagnose it. Do not "simplify" by dropping
            # `role_key` from that loop's list — registering it is what makes
            # `normalize("product_data_scientist")` resolve to its parent.
            claimed = alias_to_key.get(role_key)
            if claimed is not None and claimed != key:
                raise ValueError(
                    f"role key {role_key!r} is already an alias of {claimed!r}, "
                    f"so normalize() and parent_of() would disagree"
                )
            role_label = str(role.get("label") or role_key.replace("_", " ").title())
            roles[key].append({"key": role_key, "label": role_label})
            role_index[role_key] = {"key": role_key, "label": role_label, "category": key}
            for alias in [role_key, role_label, *(role.get("aliases") or [])]:
                slug = _slug(alias)
                if not slug:
                    continue
                # Two roles under DIFFERENT categories claiming one alias is the
                # exact ambiguity `propose_from_resume` refuses to resolve — the
                # winner would be YAML file order. Refuse it here too rather
                # than let `normalize()` decide quietly. Re-claiming a slug the
                # same category already owns is the intended overlap (a role
                # spelled out as its parent's alias) and must stay silent.
                owner = alias_to_key.get(slug)
                if owner is not None and owner != key:
                    raise ValueError(
                        f"role alias {slug!r} under {role_key!r} is already "
                        f"claimed by {owner!r}, so normalize() would decide by "
                        f"file order"
                    )
                alias_to_key.setdefault(slug, key)
                # `setdefault` for the same reason as above: first claim wins,
                # and every cross-category contest has already raised.
                role_alias_index.setdefault(slug, role_key)

    def _terms(values) -> tuple[str, ...]:
        return tuple(
            term
            for term in (
                " ".join(str(t or "").strip().lower().split()) for t in (values or [])
            )
            if term
        )

    raw_seniority = raw.get("seniority") or {}
    # Tolerate the pre-2026-08-06 flat-list shape: a hand-edited or older YAML
    # must degrade to "everything is always-strip" rather than raising, which
    # would take the whole engine down at import.
    #
    # Yes, this is the opposite of the guards above, and the split is the point:
    # a stale seniority SHAPE has a safe default, so refusing to boot buys
    # nothing. An ambiguous alias has no safe default — it silently routes a job
    # into the wrong analytics bucket, and the damage is invisible and durable.
    # Raise where a wrong answer would be quiet; degrade where it would be loud.
    if isinstance(raw_seniority, list):
        always, prefix_only = _terms(raw_seniority), ()
    else:
        always = _terms(raw_seniority.get("always"))
        prefix_only = _terms(raw_seniority.get("prefix_only"))

    return {
        "labels": labels,
        "descriptions": descriptions,
        "families": families,
        "roles": roles,
        "role_index": role_index,
        "aliases": alias_to_key,
        "role_aliases": role_alias_index,
        "seniority": always + prefix_only,
        "seniority_always": always,
        "seniority_prefix_only": prefix_only,
    }


def keys() -> list[str]:
    """Declared category keys, in file order. Excludes `other`/`unknown`."""
    return list(_load()["labels"].keys())


def all_keys() -> list[str]:
    """Every storable value: declared categories plus the reserved two."""
    return [*keys(), OTHER, UNKNOWN]


def labels() -> dict[str, str]:
    """key -> display label, including `other`/`unknown`."""
    return {**_load()["labels"], **RESERVED}


def description_for(key: str | None) -> str | None:
    """Optional one-line context for an ambiguous or emerging category."""
    return _load()["descriptions"].get(key or "")


def roles_for(key: str | None) -> list[dict[str, str]]:
    """Specific roles nested under a category, in file order.

    A role is never a `role_category` VALUE: role keys stay out of `all_keys()`
    and off `Job.role_category`/`BaseResume.role_category`, and never reach
    `title_families()`. They exist so a picker can offer "Product Data
    Scientist" while the row still records `data_scientist`.
    """
    return [dict(role) for role in _load()["roles"].get(key or "", [])]


def parent_of(key: str | None) -> str | None:
    """Coarse category a catalog key belongs to, or None if it is not one.

    A category is its own parent, so callers can pass a category key or a
    specific role key without branching. Reserved keys resolve to themselves.
    """
    if not key:
        return None
    if key in RESERVED:
        return key
    loaded = _load()
    if key in loaded["labels"]:
        return key
    entry = loaded["role_index"].get(key)
    return entry["category"] if entry else None


def label_for(key: str | None) -> str:
    """Display label for a stored value.

    Resolves specific roles too, because humanizing a role key mangles the very
    labels the YAML curates: `llmops_engineer` renders as "LLMOps Engineer",
    not "Llmops Engineer".

    Never raises and never returns an empty string: an unrecognized value is
    humanized (`bi_developer` -> `Bi Developer`) rather than dropped, so a row
    written before a category was renamed still renders.
    """
    if not key:
        return RESERVED[UNKNOWN]
    known = labels().get(key)
    if known:
        return known
    role = _load()["role_index"].get(key)
    if role:
        return role["label"]
    return str(key).replace("_", " ").title()


def title_families() -> dict[str, list[str]]:
    """role_category key -> adjacent title strings, for the ATS L3 title tier.

    The inner lists are copied, not shared: `ats/config.py` hashes this into
    `config_version`, so a caller appending to a returned list would mutate the
    lru_cached vocabulary and change scores under a version that claims they
    are comparable.
    """
    return {key: list(members) for key, members in _load()["families"].items()}


def seniority_terms() -> tuple[str, ...]:
    """Rank markers that qualify how senior a role is without changing what it is.

    Lowercased and whitespace-collapsed; entries may be multi-word ("entry
    level"). Two consumers compose this differently and must not be merged:
    the ATS L3 title tier strips ONLY these, so that "Senior Data Scientist"
    matches a "Data Scientist" resume; `role_titles.generic_role_title` layers
    management level and niche modifiers on top for its display labels.

    Management titles (`manager`, `director`, `head`, `vp`) deliberately do NOT
    belong here — they name a different job, and stripping them would score
    "Engineering Manager" as a direct match for "Engineer".

    Hashed into the ATS `config_version` (see `ats/config.py::load_config`), so
    editing the YAML invalidates stored scores rather than silently changing
    what a fixed version means.

    This is the COMBINED list. Consumers that strip titles want
    `seniority_always()` and `seniority_prefix_only()` instead — see those.
    """
    return _load()["seniority"]


def seniority_always() -> tuple[str, ...]:
    """Rank markers safe to remove wherever they appear in a title.

    These are never a job on their own: "Senior" and "IV" are not roles.
    """
    return _load()["seniority_always"]


def seniority_prefix_only() -> tuple[str, ...]:
    """Rank markers removed ONLY when they lead the title.

    `associate`, `principal`, `staff` and `lead` double as head nouns —
    "Sales Associate", "Tech Lead", "Team Lead" are the job, not a rank applied
    to one. Stripping them in the suffix position reduced those titles to
    "sales" / "tech" / "team", which match nothing, so the title tier collapsed
    to `none`. Leading them ("Lead Engineer", "Associate Data Scientist") is a
    genuine rank and still strips.
    """
    return _load()["seniority_prefix_only"]


def normalize(value: str | None) -> str:
    """Coerce any inbound value to a canonical key.

    Unrecognized non-empty input becomes `other` rather than being stored
    verbatim — that keeps analytics groupable while the YAML stays the only
    place the vocabulary grows.
    """
    if value is None:
        return UNKNOWN
    slug = _slug(value)
    if not slug:
        return UNKNOWN
    if slug in RESERVED:
        return slug
    return _load()["aliases"].get(slug, OTHER)


def _strip_rank_markers(slug: str) -> str:
    """Remove seniority markers from an already-slugged title.

    Composed exactly like `ats/layers._strip_seniority` — phrases longest-first,
    then always-strip tokens anywhere, then prefix-only tokens from the front and
    never down to nothing — because the two must not disagree about what "Tech
    Lead" means. It is spelled separately only because `layers` imports this
    module, so the dependency cannot run the other way; it reads the same two
    accessors rather than a token list of its own.

    Differs from `layers` in one DELIBERATE way: when a title is nothing BUT
    rank markers ("Senior"), that function keeps the original so two such titles
    do not compare equal, while this one returns "" — there is no catalog entry
    to look up, and `none` is the honest answer.

    It also differs in two INCIDENTAL ways, because the two functions normalize
    differently before they strip. `_slug` collapses all punctuation, while
    `matching.normalize_term` preserves `. / + #` so skill terms like `node.js`
    survive. A differential over 1696 titles found 110 disagreements: 19 are the
    deliberate case above, 90 are punctuated rank markers, and 1 is `C++`.
    Do not read this docstring as a claim of parity — the punctuation gap is a
    live defect on the `layers` side (`normalize_term("Sr.")` is `"sr."`, which
    never matches the vocabulary's bare `sr`, so a JD titled "Sr. Data Scientist"
    silently loses a title tier). It is filed as its own round, together with
    collapsing these two implementations into one; fixing it there is what makes
    a real parity claim possible.

    Not cached, unlike its two siblings: a cache keyed off the vocabulary would
    survive the `cache_clear()` that the tests' synthetic-YAML fixture performs
    on `_load` alone. The list is a few dozen terms; recomputing it is cheaper
    than the invalidation bug.
    """
    always = {_slug(term) for term in seniority_always()}
    prefix_only = {_slug(term) for term in seniority_prefix_only()}
    text = slug
    for phrase in sorted((t for t in always if "_" in t), key=len, reverse=True):
        text = re.sub(rf"(?:^|_){re.escape(phrase)}(?=_|$)", "_", text)
    parts = [part for part in text.split("_") if part and part not in always]
    while len(parts) > 1 and parts[0] in prefix_only:
        parts = parts[1:]
    return "_".join(parts)


def _lookup(slug: str) -> tuple[str | None, str | None, str | None] | None:
    """The three exact lookups, as (role, category, catalog label), or None.

    A catalog label of None marks an alias hit — the caller keeps the user's own
    words in that case, so there is nothing canonical to offer.
    """
    loaded = _load()
    if slug in loaded["labels"]:
        return slug, slug, loaded["labels"][slug]
    role = loaded["role_index"].get(slug)
    if role:
        return role["key"], role["category"], role["label"]
    category = loaded["aliases"].get(slug)
    if category:
        # A role owns most aliases; a category owns the rest. Answering None for
        # the former would hide a catalog entry the alias was written to reach.
        return loaded["role_aliases"].get(slug), category, None
    return None


def match_free_text(text: str) -> RoleMatch:
    """Map typed text onto the vocabulary by exact slug, plus a rank-strip retry.

    No LLM, no fuzzy or edit-distance matching, no substring scanning. Text is
    slugged and looked up against the category keys, the role keys, then the
    aliases; if all three miss, seniority markers are stripped and those same
    three run once more. Deliberately timid, for the same reason as
    `propose_from_resume`: a visible blank beats a plausible wrong answer.

    `role` is any catalog key, coarse or specific — a category is its own role
    here, exactly as it is its own parent in `parent_of`. Only `exact` names a
    catalog entry outright. An `alias` hit — whether by declared alias or by
    rank-strip — is a SUGGESTION the user confirms, so it keeps the user's typed
    words as the label rather than substituting the catalog's. `none` is a
    perfectly valid outcome and the caller must not treat it as an error.

    Unlike `normalize()`, this never falls back to `other`, and it does not
    recognize `other`/`unknown` as INPUT either. Those two are storage
    sentinels, not words anyone types to name a job: "Count this as Unknown?"
    is not a question worth asking, so typing one is simply an unmatched custom
    role. Both halves are pinned by tests — do not "fix" either.
    """
    cleaned = " ".join(str(text or "").split())
    slug = _slug(cleaned)
    if not slug:
        return {"role": None, "category": None, "label": cleaned, "confidence": "none"}

    found = _lookup(slug)
    if found:
        role, category, catalog_label = found
        return {
            "role": role, "category": category,
            "label": catalog_label or cleaned,
            "confidence": "exact" if catalog_label else "alias",
        }

    # "Senior Data Scientist" is likely the single most common thing typed into
    # a role box, and the rank is not part of the job. A stripped hit is only
    # ever `alias`: the catalog never contained what they typed.
    stripped = _strip_rank_markers(slug)
    if stripped and stripped != slug:
        found = _lookup(stripped)
        if found:
            role, category, _ = found
            return {
                "role": role, "category": category,
                "label": cleaned, "confidence": "alias",
            }
    return {"role": None, "category": None, "label": cleaned, "confidence": "none"}


def prompt_options() -> str:
    """Pipe-joined option list for the extraction prompt's JSON skeleton."""
    return "|".join([*keys(), OTHER])


def propose_from_resume(data: dict) -> str:
    """Propose a role from resume content — or `unknown` when unsure.

    Deliberately deterministic and deliberately timid. Adjacent phrases are
    uniquely owned, but substring matches, compound titles, and two-role career
    paths can still hit multiple families. Any single-winner scheme would decide
    those ties by YAML file order. Exact catalog ownership is a veto only: a
    nested role or alias may prevent a different-family proposal, never create
    one without an adjacent hit.

    So this only proposes when the answer is UNAMBIGUOUS — exactly one category
    matches the most recent role title. Anything else returns ``unknown``, which
    the UI shows as "Role not set" with a one-click picker. A visible blank beats
    a plausible wrong answer; the user confirms either way.
    """
    experience = data.get("experience") or []
    titles = [str((e or {}).get("role") or "") for e in experience[:2]]
    if not any(titles):
        return UNKNOWN

    catalog_categories = {
        match["category"]
        for title in titles
        if (match := match_free_text(title))["category"] is not None
    }

    loaded = _load()
    haystack = " ".join(_slug(t).replace("_", " ") for t in titles if t)
    if not haystack.strip():
        return UNKNOWN

    hits: set[str] = set()
    for key, members in loaded["families"].items():
        for member in members:
            if member and member.lower() in haystack:
                hits.add(key)
                break

    # Exactly one adjacent category, or nothing. Never a tie-break. A catalog
    # role/alias owned elsewhere vetoes a confidently wrong substring match.
    if len(hits) != 1:
        return UNKNOWN
    proposed = next(iter(hits))
    return proposed if catalog_categories <= {proposed} else UNKNOWN
