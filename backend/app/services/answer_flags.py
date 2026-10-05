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

from app.services.autofill_catalog import Fact, ym, yes_no_word
from app.services.autofill_slots import policy_for

SCREENING_RE = re.compile(
    r"authori[sz]|sponsor|\bvisas?\b|relocat|on-?site|in[- ]office|days (?:a|per) week|in[- ]person"
    r"|clearance|citizen|\bdegree\b|graduat|enrolled|start date|availab"
    r"|\beligib\w* to work|right to work|work permit|permanent resident|green card|\bh-?1b\b"
    r"|(?:at least|over|older than|age of)\s+18\b|\b18\s*(?:\+|years? (?:of age|old)|or older)"
    r"|(?:able|willing) to commute|\bcommut\w* (?:to|distance)|can you commute"
    r"|\bhybrid (?:role|position|schedule|work|arrangement|model)\b"
    r"|\b(?:work|be|based|come|report) (?:in|from|into|to) (?:our|the) [^.?]{0,20}office"
    r"|when can you start|notice period|\byou (?:currently |now )?resid(?:e|ing)\b",
    re.IGNORECASE,
)
EEO_RE = re.compile(
    r"gender|\bsex\b|\brace\b|ethnicit|hispanic|latin[oa]|veteran|disabilit|sexual orientation"
    r"|pronoun|lgbt|queer",
    re.IGNORECASE,
)
# Any negation cue at all: where one is present but not on the question's own verb, the
# polarity is unclear and a Yes/No is never judged ("authorized WITHOUT restriction?").
NEGATION_RE = re.compile(
    r"\b(not|without|no longer|never|don't|do not|doesn't|does not|won't|will not|unable)\b",
    re.IGNORECASE,
)
# A negation on the question's own verb, near its start: "Will you NOT require...?",
# "Won't you need...?", "Are you unable to...?". Only this turns a saved Yes/No around.
OWN_VERB_NEGATION_RE = re.compile(
    r"^\W*(?:do|does|did|will|would|are|is|can|could|have|has)\s+you\s+(?:not|never)\b"
    r"|^\W*(?:don'?t|won'?t|aren'?t|can'?t|couldn'?t|isn'?t|doesn'?t)\s+you\b"
    r"|^(?:\W*\w+){0,3}?\W+unable\b",
    re.IGNORECASE,
)
REASONS = {
    "guessed_screening": "A screening question with no saved answer behind it.",
    "ticked_everything": "Every option is ticked.",
    "differs_from_profile": "Doesn't match your profile.",
    "eeo_without_saved_answer": "You have no saved answer for this voluntary question.",
}
_GUESSED = frozenset({"inferred", "written"})
# A knock-out answer is a word or a sentence; a longer written answer is an essay about something else.
MAX_KNOCKOUT_CHARS = 200


# The profile's EEO key a question's words name, for a field a writer sent without its slot.
EEO_KEY_WORDS = (
    ("gender_self_describe", re.compile(r"self[- ]describe", re.IGNORECASE)),
    ("gender", re.compile(r"gender|\bsex\b", re.IGNORECASE)),
    ("hispanic_latino", re.compile(r"hispanic|latin[oa]", re.IGNORECASE)),
    ("race_ethnicity", re.compile(r"\brace\b|ethnicit", re.IGNORECASE)),
    ("veteran_status", re.compile(r"veteran", re.IGNORECASE)),
    ("disability_status", re.compile(r"disabilit", re.IGNORECASE)),
    ("sexual_orientation", re.compile(r"sexual orientation", re.IGNORECASE)),
)
# Slots whose policy is `exact` but whose question is no knock-out: a language's name and level,
# agreeing to the application's own terms.
_NOT_SCREENING_SLOTS = ("languages.", "derived.agrees_to_terms")
# Clock-based facts: whatever the form says, "today" moves, so a stored difference means nothing.
_CLOCK_SLOTS = frozenset({"derived.today", "derived.earliest_start_date"})


def is_eeo(question: str, slot: str | None) -> bool:
    return str(slot or "").startswith("eeo.") or bool(EEO_RE.search(question or ""))


def _exact_screening_slot(slot: str | None) -> bool:
    if not slot or slot.startswith(("eeo.", *_NOT_SCREENING_SLOTS)):
        return False
    return policy_for(slot) == "exact"


def is_screening(question: str, slot: str | None) -> bool:
    if _exact_screening_slot(slot):
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


def _guessed_screening(field: dict[str, Any], facts: dict[str, Fact]) -> bool:
    """An answer read off a saved slot (a derived fact included) is not a guess; whether it
    matches the saved value is `differs_from_profile`'s question."""
    if field.get("source") not in _GUESSED or field.get("edited_by_you") or field.get("eeo"):
        return False
    if field.get("slot") in facts:
        return False
    if field.get("source") == "written" and len(str(field.get("answer") or "")) > MAX_KNOCKOUT_CHARS:
        return False
    return _answered(field) and is_screening(field.get("question", ""), field.get("slot"))


def _ticked_everything(field: dict[str, Any]) -> bool:
    answer, total = field.get("answer"), field.get("options_count")
    return isinstance(answer, list) and isinstance(total, int) and total > 2 and len(set(answer)) >= total


def _fold(text: Any) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", str(text).casefold()).split())


def _tokens(text: Any) -> frozenset[str]:
    return frozenset(_fold(text).split())


def _same_words(said: Any, kept: Any) -> bool:
    """Every word of the shorter side is in the other ("Master of Science (MS)" is a richer
    "Master of Science"); "male" is not in "female", nor "US" in "Russia"."""
    a, b = _tokens(said), _tokens(kept)
    return bool(a and b) and (a <= b or b <= a)


def _digits(text: Any) -> str:
    return re.sub(r"\D", "", str(text))[-10:]


def _same_date(said: Any, kept: Any) -> bool | None:
    """Whether two dates agree, or None when either is not a date `autofill_catalog.ym` reads."""
    a, b = ym(str(said)), ym(str(kept))
    return None if a is None or b is None else a == b


def _same_text(slot: str, said: str, kept: str) -> bool:
    if slot.endswith("phone") and len(_digits(said)) >= 7 and len(_digits(kept)) >= 7:
        return _digits(said) == _digits(kept)
    dates = _same_date(said, kept)
    return _same_words(said, kept) if dates is None else dates


def _asking_clause(question: str) -> str:
    """The sentence that asks: the last one holding the question mark, else the whole text.
    "We do not offer relocation assistance. Are you willing to relocate?" asks the second."""
    text = question.replace("\u2019", "'").replace("\u2018", "'")
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    asking = [s for s in sentences if "?" in s]
    return (asking or sentences or [text])[-1]


def _yes_no(text: str) -> str | None:
    word = yes_no_word(text)
    head = word.split(",", 1)[0]
    return head if head in ("Yes", "No") else None


def _polarity(question: str) -> str:
    """"plain", "negated" (the question's own verb is negated) or "unclear" (a cue elsewhere in
    it). Only the last comma-separated part of the asking sentence counts: "If you do not have a
    degree, are you willing to relocate?" asks the second."""
    clause = _asking_clause(question).rsplit(",", 1)[-1].strip()
    if OWN_VERB_NEGATION_RE.search(clause):
        return "negated"
    return "unclear" if NEGATION_RE.search(clause) else "plain"


def _yes_no_differs(question: str, answer: str, saved: str) -> bool:
    """A negated question ("Will you NOT require sponsorship?") turns the saved fact's answer
    around, so the literal same Yes/No is the odd one out there; an unclear one judges nothing."""
    said, kept = _yes_no(answer), _yes_no(saved)
    polarity = _polarity(question)
    if said is None or kept is None or polarity == "unclear":
        return False
    return (said == kept) if polarity == "negated" else (said != kept)


def _comparable(fact: Fact | None, answer: Any) -> bool:
    """A saved single value, and a typed answer to hold against it (a list fact is not compared)."""
    return (fact is not None and not isinstance(fact.value, tuple)
            and isinstance(answer, str) and bool(answer.strip()))


def _differs(field: dict[str, Any], facts: dict[str, Fact]) -> bool:
    slot = field.get("slot") or ""
    fact, answer = facts.get(slot), field.get("answer")
    if slot in _CLOCK_SLOTS or not _comparable(fact, answer):
        return False
    if fact.yes_no:
        return _yes_no_differs(field.get("question", ""), answer, fact.value)
    return not _same_text(slot, answer, fact.value)


def _eeo_key(field: dict[str, Any]) -> str | None:
    """The profile key a voluntary question asks about: its slot, else its words."""
    slot = str(field.get("slot") or "")
    if slot.startswith("eeo."):
        return slot.split(".", 1)[1]
    question = field.get("question", "")
    return next((key for key, words in EEO_KEY_WORDS if words.search(question)), None)


def _eeo_unsaved(field: dict[str, Any], saved: set[str]) -> bool:
    """Not when you chose the answer yourself; an unnamed question falls back to "anything saved"."""
    if not field.get("eeo") or not _answered(field) or field.get("source") == "you":
        return False
    key = _eeo_key(field)
    return (not saved) if key is None else key not in saved


def flags_for(field: dict[str, Any], facts: dict[str, Fact], saved: set[str]) -> list[dict[str, str]]:
    """The field's flags, in a fixed order. `facts`: the profile catalog
    (`autofill_catalog.build` over the consent-gated profile); `saved`: `saved_eeo` of it."""
    hits = (
        ("guessed_screening", _guessed_screening(field, facts)),
        ("ticked_everything", _ticked_everything(field)),
        ("differs_from_profile", _differs(field, facts)),
        ("eeo_without_saved_answer", _eeo_unsaved(field, saved)),
    )
    return [{"id": flag, "reason": REASONS[flag]} for flag, hit in hits if hit]
