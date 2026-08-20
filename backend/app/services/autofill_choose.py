"""Pick a form field's answer out of the profile, or decline to.

One call, one prompt, whatever the field's history. A field the profile could
not answer and a field whose known answer the page's matcher rejected are the
same question to a model — "return one of these strings or null" — and the
second is only the first with `known_value` populated. Splitting them into two
prompts would double the latency of a pass whose entire selling point is that it
is fast.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.autofill_choose import Choice, ChooseField
from app.services import autofill_profile, career_kb, llm, model_settings, persona, prompt_assembly


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
    prompt = prompt_assembly.build_autofill_choose_prompt(
        profile=autofill_profile.get_profile(session),
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
