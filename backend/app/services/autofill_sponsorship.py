"""A "what type of sponsorship will you need" question, answered from a saved No in code.

The saved sponsorship facts are Yes/No. A question that asks the TYPE of sponsorship (H-1B, TN, ...) has no Yes/No
options for the polarity step to read, so it was left empty. When the fact says no sponsorship is needed, the answer
is the option that means none or not applicable; with no such option the user answers. A saved Yes never takes this
rule. The saved No is used even when the question counts OPT or STEM OPT as sponsorship (owner decision 2026-10-15)."""

import re

SLOTS = frozenset({"work_auth.sponsorship_now", "work_auth.sponsorship_future", "derived.sponsorship_now_or_future"})
_TYPE_OF = re.compile(r"\b(?:type|kind|sort|category)s?\s+of\s+(?:\w+\s+){0,2}sponsorship\b|"
                      r"\bsponsorship\s+(?:type|kind|category)\b", re.IGNORECASE)
# The option that says no sponsorship is needed. "None of the above" and "Other" are about the listed types.
_NONE = re.compile(r"^\W*(?:none|n\s*/\s*a|not\s+applicable|no\s+(?:visa\s+)?sponsorship|not\s+(?:required|needed)|"
                   r"i\s+(?:do\s+not|don'?t|will\s+not|won'?t)\s+(?:require|need)|(?:does|do)\s+not\s+apply)\b",
                   re.IGNORECASE)
_ABOUT_THE_LIST = re.compile(r"\bof\s+the\s+above\b|^\W*other\b", re.IGNORECASE)
_YES_NO = re.compile(r"^\W*(?:yes|no)\W*$", re.IGNORECASE)


def asks_type(question: str) -> bool:
    """Whether the question asks which TYPE of sponsorship is needed (not whether it is)."""
    return bool(_TYPE_OF.search(question))


def none_option(options: list[tuple[str, str]]) -> str | None:
    """The id of the first option that means no sponsorship / not applicable, else None. A plain Yes / No list is
    not a type list (the polarity step reads it)."""
    if any(_YES_NO.match(text) for _, text in options):
        return None
    return next((oid for oid, text in options if _NONE.search(text) and not _ABOUT_THE_LIST.search(text)), None)


def is_type_question(slot: str | None, question: str, options: list[tuple[str, str]]) -> bool:
    """Whether this rule decides the field: a sponsorship fact's slot, a type question, and not a Yes / No list."""
    return slot in SLOTS and asks_type(question) and not any(_YES_NO.match(text) for _, text in options)
