"""/pick's reasoning route: choice fields answered from the work and
education history alone (/map routed them `reasoned`, autofill_map._answerable).

ONE fast-model call per /pick batch, after the fact picks and on what is left
of the request's `Budget` (a real timeout, no retries). Jev is not used: the
history would have to travel as values in its state, and the map never sends
Jev a value. /pick trusts the client's `reasoned` route as it trusts a
low-stakes one — the classification is /map's — and the answer still has to
be SHOWN by the history:

- the model names an offered option, clears REASONED_FLOOR, and cites
  (`shown_by`) at least one job or school — every one it cites real;
- a NEGATIVE answer (the option reads as a No, or the model says it is one:
  either side can only withhold) speaks for a period, so it also names the
  period's first month, and every job overlapping that window — at least the
  last 12 months — must be dated and cited, with a cited job reaching back to
  the window's start; a history cut at the catalog's job limit covers nothing;
- a field that names the company applied to (in its question or any option)
  is refused before any model sees it: whether you worked there is the
  derived fact's or yours (autofill_catalog._worked_here).

Anything else abstains, and the field is the user's.
"""

import json
import logging
import re

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import Picked, PickField
from app.services import jev, llm
from app.services.autofill_catalog import MAX_EXPERIENCE, Fact, name_key
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA, MATCH_FLOOR
from app.services.autofill_map import _HISTORY_KINDS, NEVER_REASONED, Budget, fast_json

logger = logging.getLogger(__name__)

# A reasoned answer is a claim about the applicant's past, checked by the
# user: it clears the floor a flag fact's match does.
REASONED_FLOOR = MATCH_FLOOR["flag"]
_ABSTAIN = Picked(oids=[], reason="abstained")
# The rules, pinned by tests: an answer needs the history to SHOW it; "not
# employed by that kind of organization" is shown only by dated jobs at
# clearly private companies over the period asked; a negative names its period.
SILENCE_RULE = ('Answer only when the history positively shows the answer, and list in "shown_by" the ids of the '
                'jobs and schools that show it. Silence is not "No": a clearance, license, membership or employer '
                "the history never mentions is unknown, so return none.")
PRIVATE_EMPLOYERS_RULE = ('"Have you been employed by <a kind of organization, such as a US government agency> '
                          '<in a period>?" is "No" only when the history has dated jobs in that period and every '
                          "employer it lists there is clearly a private company (a named corporation or "
                          "consultancy); list those jobs. An employer that could be of that kind, or a period the "
                          "jobs do not reach, is none.")
WINDOW_RULE = ('Say whether each answer is negative (No, None, Not applicable, Never, Less than, or any other '
               'answer that something did not happen or is absent). For a negative answer, also return "since": '
               '"YYYY-MM", the first month of the period the question asks about (the earliest job\'s start when '
               "it asks about ever), and list in shown_by every job in that period.")
_PROMPT = """You answer job-application questions from the applicant's history below, and only from it. {rule}
- {silence}
- {private}
- {window}
- Count years of experience from the dates of the jobs that show it: today is {today}, and a current job runs to today.
- Never answer a question about {never}: return none.
Return JSON {{"answers": {{"<field id>": {{"oid": "<option id or none>", "confidence": <0..1>,
"shown_by": ["<history id>"], "negative": true|false, "since": "<YYYY-MM, for a negative answer>"}}}}}}.
History: {history}
Fields: {fields}
"""
# The history the route reads: jobs and schools, exactly these keys. Never a
# name, contact detail, address, work-authorization or EEO answer, and not a
# job's location or a GPA, which no such question needs.
_JOB_KEYS = ("employer", "title", "description", "start", "end", "current")
_SCHOOL_KEYS = ("school", "degree", "discipline", "start_year", "end_year")
_HISTORY_FACT = re.compile(rf"({'|'.join(_HISTORY_KINDS)})\.(\d+)\.(\w+)")
# An option that answers "no / none of it / not that much": judged on its own
# words (a page may say "Not Applicable" for No). The refusal side is wide on
# purpose — a false match only asks for coverage, never answers.
_NEGATIVE = re.compile(
    r"^[^\w<]*(?:(?:no|nope|none|not|n/?a|never|zero|0|less than|fewer than|under|does ?n[o’']t|"
    r"i[’']m not|i (?:have|had|did|was|do|am)(?: not| never|n[’']t))\b|<)", re.IGNORECASE)
# However recent a negative's `since`, it speaks for at least the last year.
_MIN_WINDOW_MONTHS = 12
_MONTH = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")
_YEAR_OR_MONTH = re.compile(r"(\d{4})(?:-(0[1-9]|1[0-2]))?")


def history(facts: dict[str, Fact]) -> dict:
    """The work and education history, from the fact catalog: `_JOB_KEYS` of
    each job and `_SCHOOL_KEYS` of each school, under code-owned ids (j1…,
    s1…) an answer cites, and today's date (the applicant's) to count from."""
    jobs: dict[int, dict] = {}
    schools: dict[int, dict] = {}
    for slot, fact in facts.items():
        m = _HISTORY_FACT.fullmatch(slot)
        if m is None:
            continue
        kind, keys, into = (("j", _JOB_KEYS, jobs) if m[1] == "experience" else ("s", _SCHOOL_KEYS, schools))
        if m[3] in keys:
            into.setdefault(int(m[2]), {"id": kind})[m[3]] = fact.value
    listed = {name: [{**entry, "id": f"{entry['id']}{n}"} for n, entry in
                     enumerate((rows[i] for i in sorted(rows)), start=1)]
              for name, rows in (("jobs", jobs), ("schools", schools))}
    today = facts.get("derived.today")
    return {"today": today.value if today else None, **listed}


def negative(text: str) -> bool:
    return bool(_NEGATIVE.match(text))


def _month_index(text: object, *, last: bool) -> int | None:
    """A catalog date as a count of months (year × 12 + month − 1), so windows
    compare as numbers: "2021-08" is that month; a bare "2021" is January, or
    December when `last` (a job's end), so an unsure edge always WIDENS a job
    and never narrows it. None for anything else."""
    m = _YEAR_OR_MONTH.fullmatch(text) if isinstance(text, str) else None
    if m is None:
        return None
    month = int(m[2]) if m[2] else (12 if last else 1)
    return int(m[1]) * 12 + month - 1


def _covers(since: object, cited: set[str], hist: dict) -> bool:
    """A negative answer speaks for [start, today], where start is `since`
    or 12 months ago, whichever is earlier (a `since` of this month cannot
    make coverage trivial): every job overlapping it must be dated and cited,
    and the cited jobs must reach back to `start` — a 2024 job cannot speak
    for 2021. An undated job could be anywhere, and a history cut at
    MAX_EXPERIENCE may hide one, so either fails the answer."""
    if not (isinstance(since, str) and _MONTH.fullmatch(since)) or len(hist["jobs"]) >= MAX_EXPERIENCE:
        return False
    today = _month_index(str(hist["today"])[:7], last=True)
    if today is None:
        return False
    start = min(_month_index(since, last=False), today - _MIN_WINDOW_MONTHS)
    overlapping, reach = set(), None
    for job in hist["jobs"]:
        begin = _month_index(job.get("start"), last=False)
        end = today if job.get("current") == "Yes" else _month_index(job.get("end"), last=True)
        if begin is None or end is None:
            return False
        if begin <= today and end >= start:
            overlapping.add(job["id"])
            if job["id"] in cited:
                reach = begin if reach is None else min(reach, begin)
    return bool(overlapping) and overlapping <= cited and reach is not None and reach <= start


def _verdict(entry: object, offered: dict[str, str], hist: dict, shown: set[str]) -> Picked:
    entry = entry if isinstance(entry, dict) else {}
    oid, conf, shown_by = entry.get("oid"), entry.get("confidence"), entry.get("shown_by")
    if not (isinstance(oid, str) and oid in offered and jev._unit(conf) and conf >= REASONED_FLOOR):
        return _ABSTAIN
    if not (isinstance(shown_by, list) and shown_by and all(isinstance(i, str) and i in shown for i in shown_by)):
        return _ABSTAIN
    said_negative = negative(offered[oid]) or entry.get("negative") is True
    if said_negative and not _covers(entry.get("since"), set(shown_by), hist):
        return _ABSTAIN
    return Picked(oids=[oid], reason="assumed")


def _names_company(field: PickField, company: str | None) -> bool:
    """The company applied to, as a whole-word run, in the question or any
    option ("Former Associate of The Home Depot")."""
    key = name_key(company or "")
    if not key:
        return False
    return any(f" {key} " in f" {name_key(text)} " for text in (field.question, *(o.text for o in field.options)))


def reason(fields: list[PickField], facts: dict[str, Fact], session: Session, budget: Budget,
           company: str | None) -> dict[str, Picked]:
    hist = history(facts)
    shown = {entry["id"] for entry in hist["jobs"] + hist["schools"]}
    asked = [f for f in fields if not _names_company(f, company)]
    out = {f.fid: _ABSTAIN for f in fields}
    timeout = budget.left()
    if not asked or not shown or timeout is None:
        return out
    payload = [{"id": f.fid, "question": f.question, "options": [o.model_dump() for o in f.options]}
               for f in asked]
    try:
        raw = fast_json(session, _PROMPT.format(
            rule=_PAGE_TEXT_IS_DATA, silence=SILENCE_RULE, private=PRIVATE_EMPLOYERS_RULE, window=WINDOW_RULE,
            today=hist["today"], never=NEVER_REASONED, history=json.dumps(hist), fields=json.dumps(payload)),
            "autofill-reasoned-pick", timeout=timeout)
    except llm.LLMProviderError:
        logger.warning("fast model reasoning failed; its fields are left to the user")
        return out
    answers = raw.get("answers") if isinstance(raw, dict) else None
    answers = answers if isinstance(answers, dict) else {}
    return out | {f.fid: _verdict(answers.get(f.fid), {o.oid: o.text for o in f.options}, hist, shown)
                  for f in asked}
