"""Links, emails and phone numbers in free text, and whether the owner gave them.

Read by the draft check (`qa.draft_answers`: a link or number a model made up is never right) and by the
reasoning step's note (`autofill_reason.clean_note`: none reaches the panel). One finder so the two cannot drift.

A phone is a STRUCTURED run (a country code, then groups of digits split by spaces, dots, dashes or a
parenthesised area code) of 7 to 15 digits. Dates ("2019-2023", "2023-01-15", "15.01.2023"), runs of years,
digit-grouped counts ("10 000 000"), versions and ISBNs are not phones; a bare 10 or 11 digit run is. A host
with a path is a link on any letters TLD; a bare host only on a known one (every country code and the common
generic ones, less file-extension look-alikes), so "Node.js", "main.py" and "B.Tech" are not hosts."""

import re
from typing import Any

# Two-letter country codes, less the ones that are also file extensions ("main.py", "app.ts", "README.md").
_FILE_LABELS = frozenset({"js", "ts", "py", "rs", "sh", "pl", "md", "ps", "cs", "ml", "rb", "go", "json", "csv",
                          "pdf", "txt"})
_CC_TLDS = frozenset((
    "ad ae af ag ai al am ao aq ar as at au aw ax az ba bb bd be bf bg bh bi bj bm bn bo br bs bt bw by bz ca cc cd "
    "cf cg ch ci ck cl cm cn co cr cu cv cw cx cy cz de dj dk dm do dz ec ee eg er es et eu fi fj fk fm fo fr ga gd "
    "ge gf gg gh gi gl gm gn gp gq gr gs gt gu gw gy hk hm hn hr ht hu id ie il im in io iq ir is it je jm jo jp ke "
    "kg kh ki km kn kp kr kw ky kz la lb lc li lk lr ls lt lu lv ly ma mc me mg mh mk mm mn mo mp mq mr ms mt mu mv "
    "mw mx my mz na nc ne nf ng ni nl no np nr nu nz om pa pe pf pg ph pk pm pn pr pt pw qa re ro ru rw sa sb sc sd "
    "se sg si sk sl sm sn so sr ss st su sv sx sy sz tc td tf tg th tj tk tl tm tn to tr tt tv tw tz ua ug uk us uy "
    "uz va vc ve vg vi vn vu wf ws ye yt za zm zw").split()) - _FILE_LABELS
_G_TLDS = frozenset(("com org net edu gov info xyz dev app test biz jobs careers link site online top club shop").split())   # not "tech": "B.Tech" is a degree
_TLDS = "|".join(sorted(_CC_TLDS | _G_TLDS, key=len, reverse=True))
_CONTACT = re.compile(
    r"(?P<email>[\w.+-]+@[\w-]+(?:\.[\w-]+)+)"
    r"|(?P<url>(?:https?://|www\.)\S+)"
    # A host with a path is a link on ANY alphabetic TLD; a bare host only on a known one.
    r"|(?P<link>(?<![\w.@/-])(?:[a-z0-9-]+\.)+[a-z]{2,}/\S*)"
    rf"|(?P<host>(?<![\w.@/-])(?:[a-z0-9-]+\.)+(?:{_TLDS})(?![\w-]))"
    r"|(?P<phone>(?<![\w.-])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)\s?|\d{2,4}[\s.-])\d{3,4}[\s.-]?\d{3,4}(?!\w|[.-]\d))"
    r"|(?P<digits>(?<!\w)\d{10,11}(?!\w))",
    re.IGNORECASE)
_TRAILING = ".,;:!?)]\"'"
_NOT_HOSTS = frozenset({"asp.net", "vb.net"})   # ".net" is a host only after anything else
# Any dotted word whose last label is letters: what a NOTE must not carry (clean_note), "Node.js" included.
HOSTLIKE = re.compile(r"\w[\w-]*(?:\.[\w-]+)+(?:/\S*)?")
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
        if kind in ("phone", "digits"):
            if kind == "phone" and _phone_digits(run) is None:
                continue
            kind = "phone"
        elif kind in ("host", "link"):
            host = run.split("/", 1)[0].lower()
            if host in _NOT_HOSTS or host.rsplit(".", 1)[-1] in _FILE_LABELS:
                continue   # ASP.NET, Node.js/Express, README.md
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
    known = re.sub(r"https?://|(?<![\w.-])www\.", "", known)
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
            if kind == "host" and re.search(rf"(?<![\w.-]){re.escape(needle)}(?![\w-]|\.\w)", known):
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
