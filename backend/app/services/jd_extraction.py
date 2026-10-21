import re
from decimal import Decimal
from typing import Any

from app.schemas.job_extraction import JobExtraction
from app.services import countries, llm, model_settings, prompt_assembly


# An hourly pay hint, for when the model left pay out. The unit is "per hour", "/hr", "an hour"
# or "hourly" right after the amount, never a bare "40 hours", and the amount is pay only with a
# currency mark beside it ($, £, €, ¥, ₹, "US$", "USD") or a pay word just before it: "40 hours
# per week" is working time.
_SYMBOL = r"(?:[A-Z]{0,2}\$|[£€¥₹])"
_CODE = "(?-i:" + "|".join(sorted(countries.currency_codes())) + ")"
_PER_HOUR = r"\s*(?:/\s*(?:hr|hour)|per\s+(?:hr|hour)|an\s+hour|hourly)\b"


def _amount(name: str) -> str:
    return rf"(?P<{name}_mark>{_SYMBOL})?\s*(?P<{name}>\d+(?:\.\d+)?)\s*(?P<{name}_code>{_CODE}\b)?"


HOURLY_RANGE_RE = re.compile(
    _amount("min") + r"\s*(?:-|to|–|—)\s*" + _amount("max") + _PER_HOUR, re.IGNORECASE
)
HOURLY_SINGLE_RE = re.compile(_amount("value") + _PER_HOUR, re.IGNORECASE)
_PAY_WORD_BEFORE = re.compile(r"\b(?:pay|rate|salary|compensation|wage)s?\b[^.;\n]{0,40}$", re.IGNORECASE)


# Work-authorization backstop. The LLM defaults to "unstated" when a posting
# uses plain disqualifying language; these precompiled patterns flip "unstated"
# (and only "unstated") to a concrete value. Mirrors the HOURLY_* salary-hint
# precedent above. `no_sponsorship` wins over `citizen_or_gc_required` when both
# fire (sponsorship is the OPT-relevant signal).
NO_SPONSORSHIP_RE = re.compile(
    r"(?:no\s+sponsorship"
    r"|will\s+not\s+sponsor"
    r"|do\s+not\s+(?:offer|provide)\s+(?:visa|work|immigration|employment)?\s*sponsorship"
    r"|unable\s+to\s+sponsor"
    r"|not\s+able\s+to\s+sponsor"
    r"|without\s+(?:requiring\s+)?sponsorship"
    r"|authoriz\w+\s+to\s+work\s+(?:in\s+the\s+us\s+)?without\s+sponsorship)",
    re.IGNORECASE,
)
# Citizenship / clearance gated on requirement context ("must be", "required",
# "only", "is required") to avoid flagging inclusive "US citizens encouraged to
# apply" postings.
CITIZEN_GC_RE = re.compile(
    r"(?:us\s+citizens?\s+only"
    r"|(?:us\s+)?citizenship\s+(?:is\s+)?required"
    r"|must\s+be\s+a\s+us\s+(?:citizen|person)"
    r"|(?:must\s+(?:have|hold)|active)\s+(?:an?\s+)?security\s+clearance"
    r"|security\s+clearance\s+(?:is\s+)?required"
    r"|green\s+card\s+(?:holder\s+)?required)",
    re.IGNORECASE,
)


def apply_work_auth_backstop(
    raw_text: str | None, extraction: dict[str, Any]
) -> dict[str, Any]:
    """Flip an `unstated` work_authorization to a concrete value when the raw
    posting plainly disqualifies sponsorship or non-citizens. Mutates and
    returns `extraction`. No-op unless work_authorization == "unstated" and
    raw_text is truthy; never downgrades a stronger LLM answer.
    """
    if not raw_text or extraction.get("work_authorization") != "unstated":
        return extraction
    if NO_SPONSORSHIP_RE.search(raw_text):
        extraction["work_authorization"] = "no_sponsorship"
    elif CITIZEN_GC_RE.search(raw_text):
        extraction["work_authorization"] = "citizen_or_gc_required"
    return extraction


def _is_pay(raw_text: str, match: re.Match[str], names: tuple[str, ...]) -> bool:
    """A currency mark on an amount, or a pay word just before the match."""
    groups = match.groupdict()
    if any(groups.get(f"{name}_mark") or groups.get(f"{name}_code") for name in names):
        return True
    return bool(_PAY_WORD_BEFORE.search(raw_text[: match.start()]))


def _hourly_pay(raw_text: str) -> tuple[str, str] | None:
    for pattern, low, high in ((HOURLY_RANGE_RE, "min", "max"), (HOURLY_SINGLE_RE, "value", "value")):
        for match in pattern.finditer(raw_text):
            if _is_pay(raw_text, match, (low, high)):
                return match.group(low), match.group(high)
    return None


def _apply_salary_hints(raw_text: str, extraction: dict[str, Any]) -> dict[str, Any]:
    if extraction.get("salary_min") is not None or extraction.get("salary_max") is not None:
        return extraction
    found = _hourly_pay(raw_text)
    if found:
        extraction["salary_min"], extraction["salary_max"] = (Decimal(value) for value in found)
        extraction["salary_period"] = "hour"
    return extraction


def extract_jd(raw_text: str, session=None) -> dict[str, Any]:
    prompt = prompt_assembly.build_extraction_prompt(raw_text)
    model = model_settings.get_fast_model(session)
    result = llm.call_openai(
        prompt=prompt,
        model=model,
        response_format="json",
        trace_name="jd-extraction",
    )
    if not isinstance(result, dict):
        raise ValueError("JD extraction returned non-object JSON")

    enriched = _apply_salary_hints(raw_text, dict(result))
    extraction = JobExtraction.model_validate(enriched)
    return extraction.model_dump(mode="json")


