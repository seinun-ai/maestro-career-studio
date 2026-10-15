"""Links, emails and phone numbers in free text, and whether the owner gave them.

Read by the draft check (`qa.draft_answers`: a link or number a model made up is never right) and by the
reasoning step's note (`autofill_reason.clean_note`: none reaches the panel). One finder so the two cannot drift.

A phone is a STRUCTURED run (a country code, then groups of digits split by spaces, dots, dashes or a
parenthesised area code) of 7 to 15 digits. Dates ("2019-2023", "2023-01-15", "15.01.2023"), runs of years,
digit-grouped counts ("10 000 000"), versions and ISBNs are not phones. A bare host counts as a link only on a
TLD list (so "Node.js" and "B.Tech" are not hosts)."""

import re
from typing import Any

_TLDS = "com|org|net|io|dev|app|test|edu|gov|info|xyz|co|uk|ca|de|ai|me"
_CONTACT = re.compile(
    r"(?P<email>[\w.+-]+@[\w-]+(?:\.[\w-]+)+)"
    r"|(?P<url>(?:https?://|www\.)\S+)"
    rf"|(?P<host>(?<![\w.@/-])(?:[a-z0-9-]+\.)+(?:{_TLDS})\b(?:/\S*)?)"
    r"|(?P<phone>(?<![\w.-])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)\s?|\d{2,4}[\s.-])\d{3,4}[\s.-]?\d{3,4}(?!\w|[.-]\d))",
    re.IGNORECASE)
_TRAILING = ".,;:!?)]\"'"
_NOT_HOSTS = frozenset({"asp.net", "vb.net"})
_GROUPED_COUNT = re.compile(r"^\d{1,3}(?:[ .]\d{3})+$")
_YEAR = re.compile(r"^(?:19|20)\d\d$")


def _phone_digits(run: str) -> str | None:
    """The digits of `run` when it is a phone, else None (a date, a run of years, a grouped count)."""
    digits = re.sub(r"\D", "", run)
    if not 7 <= len(digits) <= 15 or _GROUPED_COUNT.match(run.strip()):
        return None
    if all(_YEAR.match(group) for group in re.findall(r"\d+", run)):
        return None
    return digits


def _found(text: str) -> list[tuple[str, str]]:
    """(kind, run) for every email, link and phone in `text`, in order, trailing punctuation off."""
    out = []
    for m in _CONTACT.finditer(text):
        kind = m.lastgroup or ""
        run = m.group().rstrip(_TRAILING)
        if kind == "phone" and _phone_digits(run) is None:
            continue
        if kind == "host" and run.lower() in _NOT_HOSTS:
            continue
        out.append((kind, run))
    return out


def contacts(text: str) -> list[str]:
    """Every link, email and phone-like run in `text`."""
    return [run for _kind, run in _found(text)]


def _bare(link: str) -> str:
    return re.sub(r"^(?:https?://)?(?:www\.)?", "", link.lower()).rstrip("/")


def foreign(text: str, owner: list[str], known: str = "") -> bool:
    """Whether `text` carries a link, email or phone number the owner did not give. `owner`: the owner's own
    strings, lowercased (email, phone, links). `known`: lowercased text of the resume, where a bare host the
    owner already names ("Booking.com", an employer) is not an invented link; a host with a path never is."""
    emails = {o.strip() for o in owner if "@" in o}
    links = [_bare(o.strip()) for o in owner if "@" not in o and "." in o and " " not in o.strip()]
    owner_phones = [d for o in owner if re.fullmatch(r"[\d\s().+-]+", o.strip())
                    and 7 <= len(d := re.sub(r"\D", "", o)) <= 15]
    for kind, run in _found(text):
        if kind == "email":
            if run.lower() not in emails:
                return True
        elif kind == "phone":
            digits = _phone_digits(run) or ""
            if not any(digits[-n:] == d[-n:] for d in owner_phones if (n := min(10, len(digits), len(d)))):
                return True
        else:
            needle = _bare(run)
            if any(needle == link or needle.startswith(link + "/") for link in links):
                continue
            if kind == "host" and "/" not in needle and needle in known:
                continue
            return True
    return False


def strings(node: Any) -> list[str]:
    """Every string in a nested dict/list, in order."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [t for v in node.values() for t in strings(v)]
    if isinstance(node, list):
        return [t for v in node for t in strings(v)]
    return []
