"""Read-only coherence lint over a tailored resume's changed loci (design §4.4).

Never mutates anything: flags are transient, response-only proposals the studio
may apply through the normal edit path. Best-effort — any LLM failure or
malformed response degrades to zero flags rather than raising.
"""
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services import llm, model_settings, prompt_assembly, resume_diff

logger = logging.getLogger(__name__)

_ISSUES = frozenset({"fragment", "tense", "summary_mismatch", "dangling"})

# Locus fields forwarded to the model; `after` carries the changed text itself.
_LOCUS_FIELDS = ("kind", "section", "index", "after")


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


def run(
    base_json: dict[str, Any],
    customized_json: dict[str, Any],
    session: Session,
) -> dict[str, Any]:
    hunks = resume_diff.diff_resume(base_json, customized_json)
    loci = [
        {key: hunk.get(key) for key in _LOCUS_FIELDS}
        for hunk in hunks
        if hunk.get("after") is not None
    ]
    if not loci:
        return {"flags": []}
    try:
        result = llm.call_openai(
            prompt=prompt_assembly.build_coherence_check_prompt(customized_json, loci),
            model=model_settings.get_fast_model(session),
            response_format="json",
            trace_name="coherence-check",
        )
    except Exception:
        logger.warning("coherence check failed; returning no flags", exc_info=True)
        return {"flags": []}
    raw = result.get("flags") if isinstance(result, dict) else None
    if not isinstance(raw, list):
        return {"flags": []}
    needle_by_locus = {
        (locus.get("kind"), locus.get("section"), locus.get("index")): locus["after"]
        for locus in loci
        if isinstance(locus.get("after"), str)
    }
    flags = [flag for entry in raw if (flag := _coerce_flag(entry, needle_by_locus))]
    return {"flags": flags}
