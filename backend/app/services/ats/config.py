import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# Bump on any scoring-behavior code change; deltas are only comparable within one version.
# 2.1.1: post-phase-2 review fixes change emitted values for extra-section-bearing
# resumes — the extra_only tier now assigns a fix_hint (F#8) and flat custom
# sections no longer corroborate the skills-stuffing lint / inflate format (F#12),
# so a same-string re-score would be silently incomparable without this bump.
# 2.2.0: certifications become evidence (credential_only tier), JD-more-specific
# containment drops to adjacency credit, and l4_gate emits an advisory degree
# warning. All three change emitted values, so stored rows are not comparable
# across the bump.
# 2.3.0: normalize_term folds accents, so "Universite de Montreal" now matches
# "Montreal" — an English-language correctness fix, since a resume and a JD
# routinely spell the same name with and without the accent.
# 2.4.0: the "still in this role" vocabulary moved to services/resume_dates and
# gained `currently`/`to date`/`till date`/`to present`, and now matches the
# WHOLE end_date rather than its first token. Both directions move scores: a
# role ending "To date" is now current and earns recency credit, while one
# ending "Present day rotation" no longer does. The live corpus exercises
# neither (0 of 840 pairs moved), but a resume that uses either spelling would
# score differently, so stored rows are not comparable across the bump.
# 2.5.0: rank markers split into always-strip and prefix-only. `associate`,
# `principal`, `staff` and `lead` are head nouns in the suffix position, so
# stripping them there reduced "Tech Lead" to "tech" and "Sales Associate" to
# "sales" — cores that match nothing, collapsing the title tier to `none`.
# Those titles now keep their core and can reach `direct`, which moves the
# title subscore (0.20 of the composite) upward for anyone holding one.
ENGINE_VERSION = "ats-2.5.0"

_DATA_DIR = Path(__file__).parent / "data"


@dataclass(frozen=True)
class AtsConfig:
    weights: dict[str, Any]
    aliases: list[list[str]]
    adjacency: dict[str, dict[str, float]]
    title_families: dict[str, list[str]]
    version: str

    # The two feature-gated evidence blocks, with the F#2 feature-off contract
    # ({} when absent — a legacy/custom weights.yaml must degrade, not crash)
    # applied HERE once instead of re-derived at every consumer.

    def extras_config(self) -> dict[str, Any]:
        return self.weights.get("extra_section_evidence") or {}

    def credentials_config(self) -> dict[str, Any]:
        return self.weights.get("credential_evidence") or {}


def _load_yaml(name: str) -> Any:
    return yaml.safe_load((_DATA_DIR / name).read_text(encoding="utf-8"))


def _validate_credentials(credentials: dict[str, Any]) -> None:
    """Validate the credential-evidence block. An ABSENT block is legal and means
    feature-off (the extras F#2 fallback pattern) — a legacy/custom weights.yaml
    must degrade to pre-credential behavior, not crash. A PRESENT block must be
    fully well-formed.

    The allowed evidence fields are a hard allow-list, not a default: education
    keys are absent on purpose, so configuring education content raises loudly
    instead of silently indexing degree/institution text (school prestige and
    graduation year must reach neither the score nor the enrichment prompt).
    """
    if not credentials:
        return
    if credentials.get("placement_tier") != "credential_only":
        raise ValueError("credential_evidence.placement_tier must be credential_only")
    multiplier = credentials.get("placement_multiplier")
    # Same strictness as the extras tier: a credential is weaker than dated work
    # (1.0), so 1.0 itself is rejected. bool is an int subclass — reject it
    # explicitly so `placement_multiplier: true` cannot sneak through as 1.0.
    if (
        isinstance(multiplier, bool)
        or not isinstance(multiplier, (int, float))
        or not 0 < multiplier < 1.0
    ):
        raise ValueError(
            "credential_evidence.placement_multiplier must be a number in (0, 1)"
        )
    evidence_fields = credentials.get("evidence_fields") or {}
    configured = evidence_fields.get("certifications")
    if not isinstance(configured, list) or not configured:
        raise ValueError("credential_evidence.evidence_fields.certifications must be non-empty")
    unknown = set(configured) - {"item"}
    if unknown:
        raise ValueError(
            f"unsupported credential evidence fields: {sorted(unknown)}"
        )


@lru_cache(maxsize=1)
def load_config() -> AtsConfig:
    weights = _load_yaml("weights.yaml")
    composite_total = sum(weights["composite_weights"].values())
    if abs(composite_total - 1.0) > 1e-9:
        raise ValueError(f"composite_weights must sum to 1.0, got {composite_total}")
    if weights.get("scoring_config_version") != "ats-config-4":
        raise ValueError("weights.yaml must declare scoring_config_version ats-config-4")
    extras = weights.get("extra_section_evidence") or {}
    if extras.get("placement_tier") != "extra_only":
        raise ValueError("extra_section_evidence.placement_tier must be extra_only")
    multiplier = extras.get("placement_multiplier")
    # STRICTLY between 0 and 1: extra prose is a deliberately conservative tier,
    # worth LESS than the dated experience/project tier (multiplier 1.0), so 1.0
    # itself is rejected. bool is an int subclass, so ``placement_multiplier:
    # true`` would otherwise sneak through as 1.0 — reject it explicitly.
    if (
        isinstance(multiplier, bool)
        or not isinstance(multiplier, (int, float))
        or not 0 < multiplier < 1.0
    ):
        raise ValueError(
            "extra_section_evidence.placement_multiplier must be a number in (0, 1)"
        )
    evidence_fields = extras.get("evidence_fields") or {}
    allowed_fields = {
        "entries": {"heading", "subheading", "bullets"},
        "bullets": {"bullets"},
    }
    for kind, allowed in allowed_fields.items():
        configured = evidence_fields.get(kind)
        if not isinstance(configured, list) or not configured:
            raise ValueError(f"extra_section_evidence.evidence_fields.{kind} must be non-empty")
        unknown = set(configured) - allowed
        if unknown:
            raise ValueError(
                f"unsupported extra-section evidence fields for {kind}: {sorted(unknown)}"
            )
    _validate_credentials(weights.get("credential_evidence") or {})
    aliases = _load_yaml("aliases.yaml") or []
    adjacency = _load_yaml("adjacency.yaml") or {}
    # Keyed by role_category so cfg.title_families[role_category] actually
    # hits — the old title_families.yaml used title-cased phrases that never
    # matched, leaving the L3 "adjacent" tier unreachable.
    from app.services import role_categories

    title_families = role_categories.title_families()
    # Every input that can move a score must be in this blob. It hashes an
    # EXPLICIT dict, not the data directory, so a new YAML key is invisible here
    # until it is added by hand — and an input outside the hash changes scores
    # while `config_version` stays fixed, which turns compare()'s cross-version
    # guard from a safety net into a source of silently incomparable rows.
    # `seniority` feeds the L3 title tier via layers._strip_seniority.
    blob = json.dumps(
        {
            "weights": weights,
            "aliases": aliases,
            "adjacency": adjacency,
            "families": title_families,
            "seniority": list(role_categories.seniority_terms()),
        },
        sort_keys=True,
    )
    version = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]
    return AtsConfig(
        weights=weights,
        aliases=aliases,
        adjacency=adjacency,
        title_families=title_families,
        version=version,
    )
