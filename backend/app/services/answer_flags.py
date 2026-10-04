"""Which filled answers deserve a second look before Submit. Warn only: nothing here blocks.

Four flags, computed at READ time from the latest answer per question, so a profile change
re-flags an old receipt (docs/entities/filled-answers.md):

- guessed_screening: a screening question answered by inference or written prose;
- ticked_everything: a multi-select with more than two options and every one ticked;
- differs_from_profile: the answer is not the saved value of its slot;
- eeo_without_saved_answer: a voluntary (EEO) question answered with nothing saved for it.

A SCREENING question is a knock-out: a slot with the `exact` policy (not an EEO one), or a
question whose words match SCREENING_RE. Phase 4's auto-submit rule reads `is_screening`, so its
words are pinned question by question in tests/test_answer_flags.py. Pure: no session, no model.
"""

import re
from typing import Any

from app.services.autofill_catalog import Fact, yes_no_word
from app.services.autofill_slots import policy_for

SCREENING_RE = re.compile(
    r"authori[sz]|sponsor|\bvisas?\b|relocat|on-?site|in[- ]office|days a week|in[- ]person"
    r"|clearance|citizen|\bdegree\b|graduat|enrolled|start date|availab",
    re.IGNORECASE,
)
EEO_RE = re.compile(
    r"gender|\bsex\b|\brace\b|ethnicit|hispanic|latin[oa]|veteran|disabilit|sexual orientation",
    re.IGNORECASE,
)
# A question worded against its fact ("work WITHOUT sponsorship?") legitimately flips a Yes/No.
NEGATION_RE = re.compile(
    r"\b(not|without|no longer|never|don't|do not|doesn't|does not|won't|will not|unable)\b",
    re.IGNORECASE,
)
REASONS = {
    "guessed_screening": "A screening question with no saved answer behind it.",
    "ticked_everything": "Every option is ticked.",
    "differs_from_profile": "Doesn't match your profile.",
    "eeo_without_saved_answer": "You have no saved answer for this voluntary question.",
}
_GUESSED = frozenset({"inferred", "written"})


def is_eeo(question: str, slot: str | None) -> bool:
    return str(slot or "").startswith("eeo.") or bool(EEO_RE.search(question or ""))


def is_screening(question: str, slot: str | None) -> bool:
    if slot and not slot.startswith("eeo.") and policy_for(slot) == "exact":
        return True
    return bool(SCREENING_RE.search(question or ""))


def saved_eeo(profile: dict[str, Any]) -> set[str]:
    """The EEO keys the (consent-gated) profile holds an answer for."""
    eeo = profile.get("eeo") if isinstance(profile, dict) else None
    if not isinstance(eeo, dict):
        return set()
    return {key for key, value in eeo.items() if value not in (None, "", [])}


def _answered(field: dict[str, Any]) -> bool:
    answer = field.get("answer")
    if isinstance(answer, list):
        return any(str(item).strip() for item in answer)
    return bool(str(answer or "").strip()) or bool(field.get("eeo_answered"))


def _guessed_screening(field: dict[str, Any]) -> bool:
    if field.get("source") not in _GUESSED or field.get("edited_by_you") or field.get("eeo"):
        return False
    return _answered(field) and is_screening(field.get("question", ""), field.get("slot"))


def _ticked_everything(field: dict[str, Any]) -> bool:
    answer, total = field.get("answer"), field.get("options_count")
    return isinstance(answer, list) and isinstance(total, int) and total > 2 and len(set(answer)) >= total


def _fold(text: Any) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", str(text).casefold()).split())


def _yes_no(text: str) -> str | None:
    word = yes_no_word(text)
    head = word.split(",", 1)[0]
    return head if head in ("Yes", "No") else None


def _yes_no_differs(question: str, answer: str, saved: str) -> bool:
    said, kept = _yes_no(answer), _yes_no(saved)
    if said is None or kept is None or said == kept:
        return False
    return not NEGATION_RE.search(question)


def _comparable(fact: Fact | None, answer: Any) -> bool:
    """A saved single value, and a typed answer to hold against it (a list fact is not compared)."""
    return (fact is not None and not isinstance(fact.value, tuple)
            and isinstance(answer, str) and bool(answer.strip()))


def _differs(field: dict[str, Any], facts: dict[str, Fact]) -> bool:
    fact = facts.get(field.get("slot") or "")
    answer = field.get("answer")
    if not _comparable(fact, answer):
        return False
    if fact.yes_no:
        return _yes_no_differs(field.get("question", ""), answer, fact.value)
    said, kept = _fold(answer), _fold(fact.value)
    return bool(said and kept) and said not in kept and kept not in said


def _eeo_unsaved(field: dict[str, Any], saved: set[str]) -> bool:
    if not field.get("eeo") or not _answered(field):
        return False
    slot = str(field.get("slot") or "")
    return slot.split(".", 1)[1] not in saved if slot.startswith("eeo.") else not saved


def flags_for(field: dict[str, Any], facts: dict[str, Fact], saved: set[str]) -> list[dict[str, str]]:
    """The field's flags, in a fixed order. `facts`: the profile catalog
    (`autofill_catalog.build` over the consent-gated profile); `saved`: `saved_eeo` of it."""
    hits = (
        ("guessed_screening", _guessed_screening(field)),
        ("ticked_everything", _ticked_everything(field)),
        ("differs_from_profile", _differs(field, facts)),
        ("eeo_without_saved_answer", _eeo_unsaved(field, saved)),
    )
    return [{"id": flag, "reason": REASONS[flag]} for flag, hit in hits if hit]
