"""Read-only coherence lint over a tailored resume (design §4.4, 2026-08-12).

Never mutates anything: flags/hygiene are transient, response-only proposals
the studio may apply through the normal edit path; gates are read-only status.
Best-effort throughout — any LLM or gate failure degrades that group to empty
rather than raising. Three groups, each scoped to loci the tailoring actually
touched:

- ``flags``: one fast-LLM call over changed loci — fragment/tense/
  summary_mismatch/dangling.
- ``hygiene``: deterministic ``resume_lint.rule_notes`` findings (skills/
  certifications punctuation, duplicates, sentence-like items, bullet length,
  ...), with any defect already present in the base resume suppressed — it
  isn't the tailoring's doing. Tailoring injects keywords straight into the
  skills list, which is exactly where this class of defect gets introduced.
- ``gates``: the health check's structural gates (parse fidelity, contact
  reachability, headers, dates, placeholders), run against the tailored
  artifact — tailoring changes pagination, so a tailored PDF can fail parse
  fidelity where the base passed. Unlike the score, gates are NOT inherited
  from the base's health report; they're about the document actually
  submitted.
"""
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services import health_gates, llm, model_settings, prompt_assembly, resume_diff, resume_lint

logger = logging.getLogger(__name__)

_ISSUES = frozenset({"fragment", "tense", "summary_mismatch", "dangling"})

# Locus fields forwarded to the model; `after` carries the changed text itself.
_LOCUS_FIELDS = ("kind", "section", "index", "after")

# Hygiene rules whose fix is unambiguous enough to propose automatically.
# Everything else (duplicates, sentence-like items) is read-only: which copy
# to drop, or how to shorten a sentence, is a judgment call.
_MECHANICAL = frozenset({"skills.trailing_punct", "certifications.trailing_punct"})


def _coerce_flag(
    entry: Any, needle_by_locus: dict[tuple[Any, Any, Any], str]
) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    locus = entry.get("locus")
    issue = entry.get("issue")
    proposal = entry.get("proposal")
    if not isinstance(locus, dict) or issue not in _ISSUES:
        return None
    if not isinstance(proposal, str) or not proposal.strip():
        return None
    # The apply-by-exact-match needle. Models drop echoed fields (observed
    # live 2026-08-05), so never depend on the echo: backfill deterministically
    # from the diff hunk the locus points at.
    after = locus.get("after")
    if not isinstance(after, str):
        after = needle_by_locus.get(
            (locus.get("kind"), locus.get("section"), locus.get("index"))
        )
    return {
        "locus": {
            "kind": locus.get("kind"),
            "section": locus.get("section"),
            "index": locus.get("index"),
            "after": after,
        },
        "issue": issue,
        "proposal": proposal.strip(),
    }


def _flags(
    customized_json: dict[str, Any], session: Session, hunks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    loci = [
        {key: hunk.get(key) for key in _LOCUS_FIELDS}
        for hunk in hunks
        if hunk.get("after") is not None
    ]
    if not loci:
        return []
    try:
        result = llm.call_openai(
            prompt=prompt_assembly.build_coherence_check_prompt(customized_json, loci),
            model=model_settings.get_fast_model(session),
            response_format="json",
            trace_name="coherence-check",
        )
    except Exception:
        logger.warning("coherence check failed; returning no flags", exc_info=True)
        return []
    raw = result.get("flags") if isinstance(result, dict) else None
    if not isinstance(raw, list):
        return []
    needle_by_locus = {
        (locus.get("kind"), locus.get("section"), locus.get("index")): locus["after"]
        for locus in loci
        if isinstance(locus.get("after"), str)
    }
    return [flag for entry in raw if (flag := _coerce_flag(entry, needle_by_locus))]


def _changed(hunks: list[dict]) -> tuple[set[str], set[tuple[str, int]]]:
    """(sections that changed, (section, entry_index) pairs that changed)."""
    sections = {h["section"] for h in hunks if h.get("section")}
    entries = {
        (h["section"], h["index"])
        for h in hunks
        if h.get("section") in ("experience", "projects") and isinstance(h.get("index"), int)
    }
    return sections, entries


def _in_scope(note: dict, sections: set, entries: set) -> bool:
    loc = note.get("location") or {}
    section, index = loc.get("section"), loc.get("index")
    if section in ("experience", "projects") and isinstance(index, int):
        return (section, index) in entries
    return section in sections


def _skills_group_index(resume: dict[str, Any], subject: str) -> int | None:
    """The skills group containing ``subject``, if exactly one does."""
    matches = [
        i
        for i, group in enumerate(resume.get("skills") or [])
        if any(
            str(item) == subject or str(item).strip() == subject
            for item in (group.get("items") or [])
        )
    ]
    return matches[0] if len(matches) == 1 else None


def _hygiene_entry(note: dict[str, Any], customized_json: dict[str, Any]) -> dict[str, Any]:
    loc = note.get("location") or {}
    section, index = loc.get("section"), loc.get("index")
    subject = note.get("subject")
    if section == "skills" and index is None and subject is not None:
        index = _skills_group_index(customized_json, subject)
    rule = note["rule"]
    proposal = None
    if rule in _MECHANICAL and subject is not None:
        proposal = resume_lint._TRAILING_PUNCT_RUN.sub("", subject).strip()
    return {
        "locus": {"kind": "hygiene", "section": section, "index": index, "after": subject},
        "rule": rule,
        "issue": note["issue"],
        "why": note["why"],
        "how": note["how"],
        "label": note["label"],
        "proposal": proposal,
    }


def _hygiene(
    base_json: dict[str, Any], customized_json: dict[str, Any], hunks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    base_ids = {note["id"] for note in resume_lint.rule_notes(base_json)}
    tailored_notes = resume_lint.rule_notes(customized_json)
    # A defect present in both base and tailored is not the tailoring's doing.
    new_notes = [note for note in tailored_notes if note["id"] not in base_ids]
    sections, entries = _changed(hunks)
    scoped = [note for note in new_notes if _in_scope(note, sections, entries)]
    return [_hygiene_entry(note, customized_json) for note in scoped]


def _gates(
    session: Session, template_id: str | None, customized_json: dict[str, Any]
) -> list[dict[str, Any]]:
    try:
        gates = resume_lint.structure_gates(session, template_id, customized_json)
        gates.append(health_gates.gate_dates(customized_json))
        gates.append(health_gates.gate_placeholders(customized_json))
        return gates
    except Exception:
        logger.warning("coherence gates failed; returning no gates", exc_info=True)
        return []


def run(
    base_json: dict[str, Any],
    customized_json: dict[str, Any],
    session: Session,
    template_id: str | None = None,
) -> dict[str, Any]:
    hunks = resume_diff.diff_resume(base_json, customized_json)
    return {
        "flags": _flags(customized_json, session, hunks),
        "hygiene": _hygiene(base_json, customized_json, hunks),
        "gates": _gates(session, template_id, customized_json),
    }
