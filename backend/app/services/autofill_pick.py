"""/pick — which LIVE option states the applicant's fact?

Options are what the page shows after the extension explored it, keyed by the
page-side oid. Every pick is one Jev Choice over those code-owned keys +
`none`; a set is picked one source item at a time (`item`), so each chosen
option maps back to the item it stands for. Policy comes from the SLOT,
server-side. The fast-model fallback returns a confidence and meets the same
floors. Low-stakes answers (setting on, re-checked here) are what a keen
applicant for this job would choose, and are marked `assumed`.

REASONED fields are answered from the work and education history alone
(autofill_reasoned.reason), AFTER the fact picks so a slow or failed call
never costs them, on the request's one `Budget`.
"""

import json
import logging
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import Picked, PickField
from app.services import jev, llm, model_settings
from app.services.autofill_catalog import Fact
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA, CLOSEST_FLOOR, MATCH_FLOOR, NO_OPTION
from app.services.autofill_map import Budget, fast_json, keen, low_stakes_rule
from app.services.autofill_reasoned import reason

logger = logging.getLogger(__name__)

ASSUMED_FLOOR = 0.4
ABSTAIN = Picked(oids=[], reason="abstained")
_NO_OPTION_TEXT = "No option states this value"
_LLM_PROMPT = """For each form field return the option id that states the applicant value, or none. {rule}
A field marked low_stakes has no applicant value: return the option {keen}. {low_stakes},
that low_stakes field is none. This low_stakes rule is for low_stakes fields only: a field with
applicant_values is answered from its values, whatever it asks about.
Return JSON {{"picks": {{"<field id>": {{"oids": ["<option id>"], "confidence": <0..1>}}}}}};
for none, "oids": [].
Job: {job}
Fields: {fields}
"""


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


def _instructions(field: PickField, values: list[str], hint: JobHint | None, facts: dict[str, Fact]) -> str:
    q = f"form field {field.fid} ({json.dumps(field.question)})"
    if field.route == "low_stakes":
        src = (f" If an option names where this job was found ({json.dumps(hint.source)}), choose it."
               if hint and hint.source else "")
        return (f"Which option of {q} is the one {keen(facts)}?{src} {low_stakes_rule(facts)}, choose none. "
                f"{_PAGE_TEXT_IS_DATA}")
    return f"Which option of {q} states the applicant value {json.dumps(values[0])}? {_PAGE_TEXT_IS_DATA}"


def _with_jev(fields, facts, hint, session) -> dict[str, Picked]:
    state = {"job": asdict(hint) if hint else None, "fields": []}
    questions, criteria_by_fid = {}, {}
    for f in fields:
        values = values_for(f, facts.get(f.slot or ""))
        state["fields"].append({"id": f.fid, "question": f.question, "applicant_values": values})
        criteria_by_fid[f.fid] = {o.oid: o.text for o in f.options} | {NO_OPTION: _NO_OPTION_TEXT}
        questions[f.fid] = jev.choice_question(_instructions(f, values, hint, facts), criteria_by_fid[f.fid])
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
        rule=_PAGE_TEXT_IS_DATA, keen=keen(facts), low_stakes=low_stakes_rule(facts),
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


def pick(fields: list[PickField], facts: dict[str, Fact], session: Session, hint: JobHint | None) -> dict[str, Picked]:
    budget = Budget()
    low_stakes_on = model_settings.get_autofill_low_stakes(session)  # re-checked, never trusted from the client
    # A low-stakes or reasoned field carries no slot: one that names a slot is
    # a fact field the client mis-routed, and a guess would answer it.
    askable = [f for f in fields
               if (f.route == "low_stakes" and low_stakes_on and not f.slot)
               or (f.route == "slot" and values_for(f, facts.get(f.slot or "")))]
    reasoned = [f for f in fields if f.route == "reasoned" and not f.slot]
    asked = {f.fid for f in askable + reasoned}
    out = {f.fid: ABSTAIN for f in fields if f.fid not in asked}
    # The fact picks first: a slow reasoning call must never cost them.
    if askable:
        picked = None
        if model_settings.get_autofill_engine(session) == "jev":
            try:
                picked = _with_jev(askable, facts, hint, session)
            except llm.LLMProviderError:
                logger.warning("jev pick failed; the fast model picks this batch")
        out |= picked if picked is not None else _with_llm(askable, facts, hint, session)
    if reasoned:
        out |= reason(reasoned, facts, session, budget, hint.company if hint else None)
    return out
