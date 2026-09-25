"""/pick — which LIVE option states the applicant's fact?

Options are what the page shows after the extension explored it, keyed by the
page-side oid. Every pick is one Jev Choice over those code-owned keys +
`none`; a set is picked one source item at a time (`item`), so each chosen
option maps back to the item it stands for. Policy comes from the SLOT,
server-side. The fast-model fallback returns a confidence and meets the same
floors. Low-stakes answers (setting on, re-checked here) are what a keen
applicant for this job would choose, and are marked `assumed`.
"""

import json
import logging
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import Picked, PickField
from app.services import jev, llm, model_settings
from app.services.autofill_catalog import Fact
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA, CLOSEST_FLOOR, MATCH_FLOOR, NO_OPTION

logger = logging.getLogger(__name__)

ASSUMED_FLOOR = 0.4
ABSTAIN = Picked(oids=[], reason="abstained")
_NO_OPTION_TEXT = "No option states this value"
_LLM_PROMPT = """For each form field return the option id that states the applicant value, or none. {rule}
Return JSON {{"picks": {{"<field id>": {{"oids": ["<option id>"], "confidence": <0..1>}}}}}}.
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
    never from the client. One `item` of a set slot stands alone, and only when
    the set really holds it."""
    if field.route == "low_stakes" or fact is None:
        return []
    if getattr(field, "item", None):
        return [field.item] if isinstance(fact.value, tuple) and field.item in fact.value else []
    return list(fact.value) if isinstance(fact.value, tuple) else [fact.value]


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
    q = f'form field {field.fid} ("{field.question}")'
    if field.route == "low_stakes":
        src = f" If an option names where this job was found ({hint.source}), choose it." if hint and hint.source else ""
        return f"Which option of {q} would an applicant keen on this job choose?{src} {_PAGE_TEXT_IS_DATA}"
    return f'Which option of {q} states the applicant value "{values[0]}"? {_PAGE_TEXT_IS_DATA}'


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
    raw = llm.call_openai(
        prompt=_LLM_PROMPT.format(rule=_PAGE_TEXT_IS_DATA, job=json.dumps(asdict(hint) if hint else None),
                                  fields=json.dumps(payload)),
        model=model_settings.get_fast_model(session), response_format="json", trace_name="autofill-pick")
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
    low_stakes_on = model_settings.get_autofill_low_stakes(session)  # re-checked, never trusted from the client
    askable = [f for f in fields
               if (f.route == "low_stakes" and low_stakes_on)
               or (f.route == "slot" and values_for(f, facts.get(f.slot or "")))]
    asked = {f.fid for f in askable}
    out = {f.fid: ABSTAIN for f in fields if f.fid not in asked}
    if not askable:
        return out
    if model_settings.get_autofill_engine(session) == "jev":
        try:
            return out | _with_jev(askable, facts, hint, session)
        except llm.LLMProviderError:
            logger.warning("jev pick failed; the fast model picks this batch")
    return out | _with_llm(askable, facts, hint, session)
