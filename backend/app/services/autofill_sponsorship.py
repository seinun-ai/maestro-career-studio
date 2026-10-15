"""A "what type of sponsorship will you need" question, answered from a saved No in code.

The saved sponsorship facts are Yes/No. A question that asks the TYPE of sponsorship (H-1B, TN, ...) has no Yes/No
options for the polarity step to read, so it was left empty. When the fact says no sponsorship is needed, the answer
is the option that means none or not applicable; with no such option the user answers. A saved Yes never takes this
rule. The saved No is used even when the question counts OPT or STEM OPT as sponsorship (owner decision 2026-10-15)."""

import re

SLOTS = frozenset({"work_auth.sponsorship_now", "work_auth.sponsorship_future", "derived.sponsorship_now_or_future"})
_TYPE_OF = re.compile(r"\b(?:type|kind|sort|category)s?\s+of\s+(?:\w+\s+){0,2}sponsorship\b|"
                      r"\bsponsorship\s+(?:type|kind|category)\b", re.IGNORECASE)
# "Will you require ANY type of sponsorship?" asks whether, not which.
_ANY_TYPE = re.compile(r"\bany\s+(?:type|kind|sort)s?\s+of\b", re.IGNORECASE)
# The question asks what is NEEDED ("what type do you currently hold" asks about a status the profile holds).
_NEED = re.compile(r"\b(?:need|needs|needed|require|requires|required|requiring)\b", re.IGNORECASE)
_NOW = re.compile(r"\b(?:now|currently|at\s+this\s+time|at\s+present|right\s+now|today)\b", re.IGNORECASE)
_LATER = re.compile(r"\b(?:future|later|eventually|going\s+forward|down\s+the\s+(?:road|line)|upcoming|after|"
                    r"or\s+in\s+the\s+future)\b", re.IGNORECASE)
# The option that says no sponsorship is needed. "None of the above" and "Other" are about the listed types.
_NONE = re.compile(r"^\W*(?:none|n\s*/\s*a|not\s+applicable|no\s+(?:visa\s+)?sponsorship|not\s+(?:required|needed)|"
                   r"i\s+(?:do\s+not|don'?t|will\s+not|won'?t)\s+(?:require|need)|(?:does|do)\s+not\s+apply)\b",
                   re.IGNORECASE)
_ABOUT_THE_LIST = re.compile(r"\bof\s+the\s+above\b|^\W*other\b", re.IGNORECASE)
# A Yes / No list: an option that begins with Yes ("Yes, I will require sponsorship"), or a bare No. An option such as
# "No sponsorship required" among types is a type.
_YES_NO = re.compile(r"^\W*(?:yes\b|no\W*$)", re.IGNORECASE)


def asks_type(question: str) -> bool:
    """Whether the question asks which TYPE of sponsorship is needed (not whether it is)."""
    return bool(_TYPE_OF.search(question)) and not _ANY_TYPE.search(question)


def none_option(options: list[tuple[str, str]]) -> str | None:
    """The id of the first option that means no sponsorship / not applicable, else None. A Yes / No list is
    not a type list (the polarity step reads it)."""
    if _yes_no_list(options):
        return None
    return next((oid for oid, text in options if _NONE.search(text) and not _ABOUT_THE_LIST.search(text)), None)


def _yes_no_list(options: list[tuple[str, str]]) -> bool:
    return any(_YES_NO.match(text) for _, text in options)


def _every_fact_says_no(slot: str, question: str, facts: dict) -> bool:
    """Whether the saved sponsorship answers all say No: now, future and the either-fact, whichever the profile holds.
    A question that names only the present ("now", "currently") needs only the now fact."""
    def no(key: str) -> bool:
        return getattr(facts.get(key), "value", None) == "No"

    if _NOW.search(question) and not _LATER.search(question) and "work_auth.sponsorship_now" in facts:
        return no("work_auth.sponsorship_now")
    held = [k for k in SLOTS if k in facts]
    return slot in facts and all(no(k) for k in held)


def is_type_question(slot: str | None, question: str, options: list[tuple[str, str]], facts: dict) -> bool:
    """Whether this rule decides the field: a sponsorship fact's slot, a question asking which type is NEEDED, no
    Yes / No list, and every saved sponsorship answer No."""
    return (slot in SLOTS and asks_type(question) and bool(_NEED.search(question)) and not _yes_no_list(options)
            and _every_fact_says_no(slot, question, facts))
