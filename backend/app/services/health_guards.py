"""Mechanical rewrite guards, enforced at generation (design: 'Guards').
You cannot prompt your way out of fabrication — these run in code.
FAIL → re-prompt once with the violations → still failing → caller downgrades
the finding to `ask`."""
import json
import logging
import re
from collections import Counter
from string import Template as StringTemplate

from sqlalchemy.orm import Session

from app.services import llm, model_settings, prompts

logger = logging.getLogger(__name__)

_NUMBER = re.compile(r"[$€£]?\d[\d,]*(?:\.\d+)?[kmb]?[%x]?", re.IGNORECASE)
_PLACEHOLDER = re.compile(
    r"\[|\{[^}]*\}|\bTODO\b|\bTBD\b|\bX{2,}\b|_{3,}", re.IGNORECASE
)
# Acronyms + capitalized runs (proper nouns, tool names). First word excluded:
# every bullet starts capitalized regardless of content.
_ACRONYM = re.compile(r"\b[A-Z]{2,}\b")
_PROPER = re.compile(r"(?<!^)(?<![.!?] )\b[A-Z][a-zA-Z0-9+#.]*\b")


def _numbers(text: str) -> Counter:
    return Counter(m.lower() for m in _NUMBER.findall(text))


def _entities(text: str) -> set[str]:
    return set(_ACRONYM.findall(text)) | set(_PROPER.findall(text))


def guard_violations(original: str, rewrite: str) -> list[str]:
    violations: list[str] = []
    extra = _numbers(rewrite) - _numbers(original)
    if extra:
        violations.append(f"introduced number(s) not in the original: {sorted(extra)}")
    if _PLACEHOLDER.search(rewrite):
        violations.append("contains a placeholder (bracket, brace, TODO, TBD, XX, or blank)")
    lost = _entities(original) - _entities(rewrite)
    lost |= set((_numbers(original) - _numbers(rewrite)).keys())
    if lost:
        violations.append(f"lost entities from the original: {sorted(lost)}")
    return violations


def guarded_rewrite(db: Session, original: str, *, context: str = "") -> str | None:
    """One rewrite attempt + one guarded re-prompt. None = caller emits `ask`."""
    template = prompts.get_prompt("resume_bullet_rewrite", db)
    model = model_settings.get_smart_model(db)
    violations: list[str] = []
    for attempt in range(2):
        prompt = StringTemplate(template).safe_substitute(
            bullet=original,
            context=context,
            violations=json.dumps(violations),
        )
        raw = llm.call_openai(
            prompt=prompt, model=model, response_format="json",
            trace_name="resume_bullet_rewrite",
        )
        rewrite = str((raw or {}).get("rewrite") or "").strip()
        if not rewrite:
            return None
        violations = guard_violations(original, rewrite)
        if not violations:
            return rewrite
        logger.info("rewrite guard failed (attempt %d): %s", attempt + 1, violations)
    return None
