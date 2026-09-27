"""/pick — which LIVE option states the applicant's fact?

Options are what the page shows after the extension explored it, keyed by the
page-side oid. Every pick is one Jev Choice over those code-owned keys +
`none`; a set is picked one source item at a time (`item`), so each chosen
option maps back to the item it stands for. Policy comes from the SLOT,
server-side. The fast-model fallback returns a confidence and meets the same
floors. Low-stakes answers (setting on, re-checked here) are what a keen
applicant for this job would choose, and are marked `assumed`.

REASONED fields (`_reason`) are answered from the work and education history
alone, in ONE fast-model call per batch, only on what the history positively
shows (the model must name the jobs or schools that show it), and are marked
`assumed` too: listed for the user to check.
"""

import json
import logging
import re
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import Picked, PickField
from app.services import jev, llm, model_settings
from app.services.autofill_catalog import Fact
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA, CLOSEST_FLOOR, MATCH_FLOOR, NO_OPTION
from app.services.autofill_map import _NEVER_LOW_STAKES, _NEVER_REASONED, fast_json

logger = logging.getLogger(__name__)

ASSUMED_FLOOR = 0.4
# A reasoned answer is a claim about the applicant's past, checked by the
# user: it clears the floor a flag fact's match does.
REASONED_FLOOR = MATCH_FLOOR["flag"]
ABSTAIN = Picked(oids=[], reason="abstained")
_NO_OPTION_TEXT = "No option states this value"
# The low-stakes answer, and which way a conflict question goes.
_KEEN = ("an applicant keen on this job would choose (No to being related to, or previously employed by, "
         "the company)")
_LLM_PROMPT = """For each form field return the option id that states the applicant value, or none. {rule}
A field marked low_stakes has no applicant value: return the option {keen},
unless the field asks about {never} — then return none.
Return JSON {{"picks": {{"<field id>": {{"oids": ["<option id>"], "confidence": <0..1>}}}}}};
for none, "oids": [].
Job: {job}
Fields: {fields}
"""
# The reasoning route's two rules, pinned by tests: an answer needs the
# history to SHOW it, and "not employed by that kind of organization" is shown
# only by dated jobs at clearly private companies over the period asked.
_SILENCE_RULE = ('Answer only when the history positively shows the answer, and list in "shown_by" the ids of the '
                 'jobs and schools that show it. Silence is not "No": a clearance, license, membership or employer '
                 "the history never mentions is unknown, so return none.")
_PRIVATE_EMPLOYERS_RULE = ('"Have you been employed by <a kind of organization, such as a US government agency> '
                           '<in a period>?" is "No" only when the history has dated jobs in that period and every '
                           "employer it lists there is clearly a private company (a named corporation or "
                           "consultancy); list those jobs. An employer that could be of that kind, or a period the "
                           "jobs do not reach, is none.")
_REASONED_PROMPT = """You answer job-application questions from the applicant's history below, and only from it. {rule}
- {silence}
- {private}
- Count years of experience from the dates of the jobs that show it: today is {today}, and a current job runs to today.
- Never answer a question about {never}: return none.
Return JSON {{"answers": {{"<field id>": {{"oid": "<option id or none>", "confidence": <0..1>,
"shown_by": ["<history id>"]}}}}}}.
History: {history}
Fields: {fields}
"""
# The history the reasoning route reads: jobs and schools, exactly these keys.
# Never a name, contact detail, address, work-authorization or EEO answer, and
# not a job's location or a GPA, which no such question needs.
_JOB_KEYS = ("employer", "title", "description", "start", "end", "current")
_SCHOOL_KEYS = ("school", "degree", "discipline", "start_year", "end_year")
_HISTORY_FACT = re.compile(r"(experience|education)\.(\d+)\.(\w+)")


@dataclass(frozen=True)
class JobHint:
    title: str | None
    company: str | None
    source: str | None


def values_for(field, fact: Fact | None) -> list[str]:
    """The applicant values a field is picked against, from the SLOT's fact —
    never from the client. A set slot is picked one `item` at a time, and only
    an item the set really holds; a set slot with no item has nothing to pick."""
    if field.route == "low_stakes" or fact is None:
        return []
    item = getattr(field, "item", None)
    if isinstance(fact.value, tuple):
        return [item] if item and item in fact.value else []
    return [] if item else [fact.value]


def verdict(field, oid: str | None, p: float, policy: str, *, complete: bool) -> Picked:
    """One single-answer decision → Picked, shared by /pick and /step.

    A `closest` near miss needs a flag slot AND a complete view of the options:
    the nearest of a partial list is a guess."""
    if not oid or oid == NO_OPTION:
        return ABSTAIN
    if field.route == "low_stakes":
        return Picked(oids=[oid], reason="assumed") if p >= ASSUMED_FLOOR else ABSTAIN
    if p >= MATCH_FLOOR[policy]:
        return Picked(oids=[oid], reason="matched")
    if policy == "flag" and complete and p >= CLOSEST_FLOOR:
        return Picked(oids=[oid], reason="closest")
    return ABSTAIN


def _policy(field: PickField, facts: dict[str, Fact]) -> str:
    fact = facts.get(field.slot or "")
    return fact.policy if fact else "any"


def _instructions(field: PickField, values: list[str], hint: JobHint | None) -> str:
    q = f"form field {field.fid} ({json.dumps(field.question)})"
    if field.route == "low_stakes":
        src = (f" If an option names where this job was found ({json.dumps(hint.source)}), choose it."
               if hint and hint.source else "")
        return (f"Which option of {q} is the one {_KEEN}?{src} If the field asks "
                f"about {_NEVER_LOW_STAKES}, choose none. {_PAGE_TEXT_IS_DATA}")
    return f"Which option of {q} states the applicant value {json.dumps(values[0])}? {_PAGE_TEXT_IS_DATA}"


def _with_jev(fields, facts, hint, session) -> dict[str, Picked]:
    state = {"job": asdict(hint) if hint else None, "fields": []}
    questions, criteria_by_fid = {}, {}
    for f in fields:
        values = values_for(f, facts.get(f.slot or ""))
        state["fields"].append({"id": f.fid, "question": f.question, "applicant_values": values})
        criteria_by_fid[f.fid] = {o.oid: o.text for o in f.options} | {NO_OPTION: _NO_OPTION_TEXT}
        questions[f.fid] = jev.choice_question(_instructions(f, values, hint), criteria_by_fid[f.fid])
    answers = jev.decide(questions, state, session)
    out = {}
    for f in fields:
        got = jev.choice_of(answers.get(f.fid), criteria_by_fid[f.fid])
        out[f.fid] = verdict(f, got.choice if got else None, got.probability if got else 0.0,
                             _policy(f, facts), complete=f.complete)
    return out


def _with_llm(fields, facts, hint, session) -> dict[str, Picked]:
    payload = [{"id": f.fid, "question": f.question, "low_stakes": f.route == "low_stakes",
                "applicant_values": values_for(f, facts.get(f.slot or "")),
                "options": [o.model_dump() for o in f.options]} for f in fields]
    raw = fast_json(session, _LLM_PROMPT.format(
        rule=_PAGE_TEXT_IS_DATA, keen=_KEEN, never=_NEVER_LOW_STAKES,
        job=json.dumps(asdict(hint) if hint else None), fields=json.dumps(payload)), "autofill-pick")
    picks = raw.get("picks") if isinstance(raw, dict) else None
    picks = picks if isinstance(picks, dict) else {}
    out = {}
    for f in fields:
        entry = picks.get(f.fid)
        entry = entry if isinstance(entry, dict) else {}
        offered = {o.oid for o in f.options}
        oids = entry.get("oids")
        oids = [o for o in oids if isinstance(o, str) and o in offered] if isinstance(oids, list) else []
        conf = entry.get("confidence")
        conf = float(conf) if jev._unit(conf) else 0.0
        out[f.fid] = verdict(f, oids[0] if oids else None, conf, _policy(f, facts), complete=f.complete)
    return out


def _history(facts: dict[str, Fact]) -> dict:
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


def _reasoned_verdict(entry: object, offered: set[str], shown: set[str]) -> Picked:
    """An answer only when it names an offered option, clears the floor, and
    cites at least one job or school of the history — every one it cites
    real. Anything else is silence, and silence is not an answer."""
    entry = entry if isinstance(entry, dict) else {}
    oid, conf, shown_by = entry.get("oid"), entry.get("confidence"), entry.get("shown_by")
    if not (isinstance(oid, str) and oid in offered and jev._unit(conf) and conf >= REASONED_FLOOR):
        return ABSTAIN
    if not (isinstance(shown_by, list) and shown_by and all(isinstance(i, str) and i in shown for i in shown_by)):
        return ABSTAIN
    return Picked(oids=[oid], reason="assumed")


def _reason(fields: list[PickField], facts: dict[str, Fact], session: Session) -> dict[str, Picked]:
    """ONE fast-model call for every reasoned field of the batch. Jev is not
    used for this route: the history would have to travel as values in its
    state, and the map never sends Jev a value. A failed call abstains these
    fields only — the batch's other picks stand."""
    history = _history(facts)
    shown = {entry["id"] for entry in history["jobs"] + history["schools"]}
    if not shown:
        return {f.fid: ABSTAIN for f in fields}
    payload = [{"id": f.fid, "question": f.question, "options": [o.model_dump() for o in f.options]}
               for f in fields]
    try:
        raw = fast_json(session, _REASONED_PROMPT.format(
            rule=_PAGE_TEXT_IS_DATA, silence=_SILENCE_RULE, private=_PRIVATE_EMPLOYERS_RULE,
            today=history["today"], never=_NEVER_REASONED, history=json.dumps(history),
            fields=json.dumps(payload)), "autofill-reasoned-pick")
    except llm.LLMProviderError:
        logger.warning("fast model reasoning failed; its fields are left to the user")
        return {f.fid: ABSTAIN for f in fields}
    answers = raw.get("answers") if isinstance(raw, dict) else None
    answers = answers if isinstance(answers, dict) else {}
    return {f.fid: _reasoned_verdict(answers.get(f.fid), {o.oid for o in f.options}, shown) for f in fields}


def pick(fields: list[PickField], facts: dict[str, Fact], session: Session, hint: JobHint | None) -> dict[str, Picked]:
    low_stakes_on = model_settings.get_autofill_low_stakes(session)  # re-checked, never trusted from the client
    # A low-stakes or reasoned field carries no slot: one that names a slot is
    # a fact field the client mis-routed, and a guess would answer it.
    askable = [f for f in fields
               if (f.route == "low_stakes" and low_stakes_on and not f.slot)
               or (f.route == "slot" and values_for(f, facts.get(f.slot or "")))]
    reasoned = [f for f in fields if f.route == "reasoned" and not f.slot]
    asked = {f.fid for f in askable + reasoned}
    out = {f.fid: ABSTAIN for f in fields if f.fid not in asked}
    if reasoned:
        out |= _reason(reasoned, facts, session)
    if not askable:
        return out
    if model_settings.get_autofill_engine(session) == "jev":
        try:
            return out | _with_jev(askable, facts, hint, session)
        except llm.LLMProviderError:
            logger.warning("jev pick failed; the fast model picks this batch")
    return out | _with_llm(askable, facts, hint, session)
