"""Pick a form field's answer out of the profile, or decline to.

One call, one prompt, whatever the field's history. A field the profile could
not answer and a field whose known answer the page's matcher rejected are the
same question to a model — "return one of these strings or null" — and the
second is only the first with `known_value` populated. Splitting them into two
prompts would double the latency of a pass whose entire selling point is that it
is fast.

The ENGINE is a setting (Settings › AI & models › Form filling). With `jev`, two
Jev calls do what they can — map each field's LABEL to a profile slot (no
values sent), then pick the rendered option that states the slot's value — and
a per-slot policy turns the pick's probability into `matched`, `closest` or an
abstention. Whatever Jev cannot place (free-text questions, unmapped or
low-confidence fields, every field of a Jev call that failed) goes to the fast
model's prompt below, unchanged — so the user always gets a fill.
"""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.autofill_choose import MAX_OPTIONS, Choice, ChooseField
from app.services import (
    autofill_slots,
    career_kb,
    eeo_consent,
    jev,
    llm,
    model_settings,
    persona,
    prompt_assembly,
)

logger = logging.getLogger(__name__)

# Jev path thresholds, on the chosen option's probability. Starting values —
# tune them from real fills, not from argument.
SLOT_FLOOR = 0.6
MATCH_FLOOR: dict[autofill_slots.Policy, float] = {"any": 0.5, "flag": 0.85, "exact": 0.9}
CLOSEST_FLOOR = 0.5
NO_OPTION = "(no suitable option)"


def _wire_fields(fields: list[ChooseField]) -> list[dict]:
    return [
        {
            "qid": f.qid,
            "label": f.label,
            "kind": f.kind,
            "options": f.options,
            "known_value": f.known_value,
        }
        for f in fields
    ]


def _answer_for(field: ChooseField, raw: object) -> str | None:
    """The option guard, applied HERE and nowhere else.

    Whatever the model returned for this qid, only a non-empty string that is
    among the field's rendered options (when options exist) survives."""
    entry = raw.get(field.qid) if isinstance(raw, dict) else None
    answer = (entry or {}).get("answer") if isinstance(entry, dict) else None
    answer = str(answer).strip() if answer is not None else None
    if answer and field.options and answer not in field.options:
        return None
    return answer or None


def choose(
    fields: list[ChooseField],
    application_id: UUID | None,
    session: Session,
) -> dict[str, Choice]:
    if model_settings.get_autofill_engine(session) == "jev":
        return _choose_with_jev(fields, application_id, session)
    return _choose_with_llm(fields, application_id, session)


def _map_slots(
    fields: list[ChooseField], slots: dict[str, str], session: Session
) -> dict[str, str]:
    """qid → slot, for every field Jev placed with confidence. Labels only."""
    if not fields:
        return {}
    criteria = autofill_slots.slot_criteria(slots)
    state = {"form_fields": [
        {"id": f.qid, "label": f.label, "control": f.kind, "options": f.options}
        for f in fields
    ]}
    questions = {
        f.qid: jev.choice_question(
            f'Which applicant fact does form field {f.qid} ("{f.label}") ask for?', criteria)
        for f in fields
    }
    answers = jev.decide(questions, state, session)
    mapped: dict[str, str] = {}
    for f in fields:
        picked = jev.choice_of(answers.get(f.qid))
        # FREE_TEXT / NO_SLOT are not in `slots`, so they fall through with the rest.
        if picked and picked.choice in slots and picked.probability >= _slot_floor(picked.choice):
            mapped[f.qid] = picked.choice
    return mapped


def _slot_floor(slot: str) -> float:
    """An `exact` slot is a knockout answer: a shaky map — "now OR in the future"
    onto `sponsorship_now` — writes a false one, so it maps only as surely as it
    would be written. The fast model sees every answer and can combine them."""
    policy = autofill_slots.policy_for(slot)
    return max(SLOT_FLOOR, MATCH_FLOOR["exact"]) if policy == "exact" else SLOT_FLOOR


def _verdict(
    field: ChooseField, picked: jev.ChoiceAnswer | None, policy: autofill_slots.Policy
) -> Choice:
    # The option guard, as `_answer_for`: only a rendered option is ever written.
    if picked is None or picked.choice not in field.options:
        return Choice(answer=None, reason="abstained")
    if picked.probability >= MATCH_FLOOR[policy]:
        return Choice(answer=picked.choice, reason="matched")
    # A list at the cap is probably the first MAX_OPTIONS of a longer one, and
    # its nearest option a guess over a partial list: no near miss from it.
    cut = len(field.options) >= MAX_OPTIONS
    if policy == "flag" and not cut and picked.probability >= CLOSEST_FLOOR:
        return Choice(answer=picked.choice, reason="closest")
    return Choice(answer=None, reason="abstained")


def _pick_options(
    items: list[tuple[ChooseField, str, autofill_slots.Policy]], session: Session
) -> dict[str, Choice]:
    """One Jev call: which rendered option states each field's value."""
    if not items:
        return {}
    state = {"fields": [
        {"id": f.qid, "label": f.label, "applicant_value": value} for f, value, _ in items
    ]}
    questions = {}
    for f, value, _ in items:
        criteria = {option: option for option in f.options}
        criteria[NO_OPTION] = "No option states this value"
        questions[f.qid] = jev.choice_question(
            f'Which option of form field {f.qid} ("{f.label}") states the applicant '
            f'value "{value}"?',
            criteria,
        )
    answers = jev.decide(questions, state, session)
    return {
        f.qid: _verdict(f, jev.choice_of(answers.get(f.qid)), policy)
        for f, _value, policy in items
    }


def _choose_with_jev(
    fields: list[ChooseField], application_id: UUID | None, session: Session
) -> dict[str, Choice]:
    """Jev places what it can; the fast model answers the rest, as it always did.

    Consent-gated like the LLM path: slots come from `disclosable_profile`, so an
    EEO answer without standing consent is not a slot and never reaches Jev."""
    slots = autofill_slots.flatten(eeo_consent.disclosable_profile(session))
    try:
        mapped = _map_slots([f for f in fields if not f.known_value], slots, session)
    except llm.LLMProviderError:
        logger.warning("jev slot mapping failed; the fast model answers this batch")
        return _choose_with_llm(fields, application_id, session)

    out: dict[str, Choice] = {}
    to_pick: list[tuple[ChooseField, str, autofill_slots.Policy]] = []
    fallback: list[ChooseField] = []
    for f in fields:
        slot = mapped.get(f.qid)
        value = f.known_value or (slots[slot] if slot else None)
        policy = autofill_slots.policy_for(slot)
        if value is None:
            fallback.append(f)
        elif not f.options and policy == "exact" and slot is not None:
            # Exact slots store codes ("stem_opt", "not_veteran"): typed into a
            # text box verbatim they are wrong. The fast model words them.
            fallback.append(f)
        elif not f.options:
            out[f.qid] = Choice(answer=value, reason="matched")
        else:
            to_pick.append((f, value, policy))
    try:
        out.update(_pick_options(to_pick, session))
    except llm.LLMProviderError:
        logger.warning("jev option pick failed; the fast model answers those fields")
        fallback.extend(f for f, _value, _policy in to_pick)
    if fallback:
        try:
            out.update(_choose_with_llm(fallback, application_id, session))
        except llm.LLMProviderError:
            # Nothing placed: the error is the answer, and the extension says why.
            if not out:
                raise
            # Keep what Jev placed; the rest stays open, as an abstain would.
            logger.warning("fast model failed; keeping %d Jev answers", len(out))
            out.update({f.qid: Choice(answer=None, reason="abstained") for f in fallback})
    return out


def _choose_with_llm(
    fields: list[ChooseField],
    application_id: UUID | None,
    session: Session,
) -> dict[str, Choice]:
    prompt = prompt_assembly.build_autofill_choose_prompt(
        # Consent-gated like GET /context: the prompt goes to a model provider,
        # so diversity answers go only when standing consent is on.
        profile=eeo_consent.disclosable_profile(session),
        memory=career_kb.compose_context(session),
        fields=_wire_fields(fields),
        persona=persona.get_persona(session),
    )
    response = llm.call_openai(
        prompt=prompt,
        model=model_settings.get_fast_model(session),
        response_format="json",
        trace_name="autofill-choose",
    )
    raw = (response or {}).get("choices", {}) if isinstance(response, dict) else {}

    out: dict[str, Choice] = {}
    for field in fields:
        answer = _answer_for(field, raw)
        out[field.qid] = (
            Choice(answer=answer, reason="matched")
            if answer
            # Covers three cases on purpose — the model said null, it returned
            # an unofferable string, it forgot the qid. The caller's next move
            # is identical for all three: leave the field.
            else Choice(answer=None, reason="abstained")
        )
    return out
