"""Mechanical rewrite guards, enforced at generation (design: 'Guards').
You cannot prompt your way out of fabrication — these run in code.
FAIL → re-prompt once with the violations → still failing → caller downgrades
the finding to `ask`."""
import json
import logging
import re
from collections import Counter
from string import Template as StringTemplate
from typing import Literal

from sqlalchemy.orm import Session

from app.models.bullet_rewrite import BulletRewrite
from app.services import bullet_classify, llm, model_settings, prompts

logger = logging.getLogger(__name__)

_NUMBER = re.compile(r"[$€£]?\d[\d,]*(?:\.\d+)?[kmb]?[%x]?", re.IGNORECASE)
_PLACEHOLDER = re.compile(
    r"\[|\{[^}]*\}|\bTODO\b|\bTBD\b|\bX{2,}\b|_{3,}", re.IGNORECASE
)
# Acronyms + capitalized runs (proper nouns, tool names). First word excluded:
# every bullet starts capitalized regardless of content.
_ACRONYM = re.compile(r"\b[A-Z]{2,}\b")
_PROPER = re.compile(r"(?<!^)(?<![.!?] )\b[A-Z][a-zA-Z0-9+#.]*\b")
_CANDIDATE_CONTEXT_OVERRIDE = """
CANDIDATE CONTEXT OVERRIDE — this governs any conflicting hard rule above:
- Facts and numbers explicitly supplied in the candidate context may be added to the rewrite.
- When the candidate context corrects an original number, it may replace the original number.
- Facts absent from both the original and candidate context remain forbidden.
""".strip()
_CONDENSE_OVERRIDE = """
CONDENSE OBJECTIVE — this governs length, not facts:
- Rewrite as one sentence of at most ~30 words.
- Keep every number, tool, and entity from the original (and from candidate context if supplied).
""".strip()
RewriteObjective = Literal["strengthen", "condense"]


def _numbers(text: str) -> Counter:
    return Counter(m.lower().replace(",", "") for m in _NUMBER.findall(text))


def _entities(text: str) -> set[str]:
    return set(_ACRONYM.findall(text)) | set(_PROPER.findall(text))


def guard_violations(original: str, rewrite: str, *, supplied: str = "") -> list[str]:
    violations: list[str] = []
    original_numbers = _numbers(original)
    supplied_numbers = _numbers(supplied)
    extra = _numbers(rewrite) - original_numbers - supplied_numbers
    if extra:
        violations.append(
            "introduced number(s) not in the original or candidate context: "
            f"{sorted(extra)}"
        )
    if _PLACEHOLDER.search(rewrite):
        violations.append("contains a placeholder (bracket, brace, TODO, TBD, XX, or blank)")
    lost = _entities(original) - _entities(rewrite)
    if not supplied_numbers:
        lost |= set((original_numbers - _numbers(rewrite)).keys())
    if lost:
        violations.append(f"lost entities from the original: {sorted(lost)}")
    return violations


def _cache_unattended(context: str, objective: str) -> bool:
    return not str(context or "").strip() and objective == "strengthen"


def guarded_rewrite(
    db: Session,
    original: str,
    *,
    context: str = "",
    objective: RewriteObjective = "strengthen",
) -> str | None:
    """One rewrite attempt + one guarded re-prompt. None = caller emits `ask`.

    Unattended strengthen results (including a guard-rejected None) are cached
    on BulletRewrite by content hash. Answered rewrites and condense drafts
    are not — those persist per-finding on HealthAskAnswer.
    """
    chash = bullet_classify.content_hash(original)
    use_cache = _cache_unattended(context, objective)
    if use_cache:
        cached = db.get(BulletRewrite, chash)
        if cached is not None:
            return cached.rewrite_text

    template = prompts.get_prompt("resume_bullet_rewrite", db)
    model = model_settings.get_smart_model(db)
    violations: list[str] = []
    result: str | None = None
    for attempt in range(2):
        prompt = StringTemplate(template).safe_substitute(
            bullet=original,
            context=context,
            violations=json.dumps(violations),
        )
        if context:
            prompt = f"{prompt.rstrip()}\n\n{_CANDIDATE_CONTEXT_OVERRIDE}\n"
        if objective == "condense":
            prompt = f"{prompt.rstrip()}\n\n{_CONDENSE_OVERRIDE}\n"
        raw = llm.call_openai(
            prompt=prompt, model=model, response_format="json",
            trace_name="resume_bullet_rewrite",
        )
        rewrite = str((raw or {}).get("rewrite") or "").strip()
        if not rewrite:
            result = None
            break
        violations = guard_violations(original, rewrite, supplied=context)
        if not violations:
            result = rewrite
            break
        logger.info("rewrite guard failed (attempt %d): %s", attempt + 1, violations)
        result = None
    if use_cache:
        db.merge(BulletRewrite(content_hash=chash, rewrite_text=result))
    return result
