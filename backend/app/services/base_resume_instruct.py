"""Propose edits to a base resume from a free instruction; persist nothing.

The base-resume twin of chat's `propose_edits`: the user types an instruction
on the resume itself ("tighten the summary", "pivot this toward data
engineering", "what roles could this support?"), the smart model answers with
typed edit ops and/or prose, and the user applies the ops through the ordinary
`PATCH /edits` door — or discards them. Nothing here writes.

Same shape as `base_from_kb_plan` (propose → review → a separate write) and
the same anti-fabrication stance: the prompt forbids invented facts, and the
ops are validated against the op schema AND dry-run against the live document
before the user ever sees them, so an "Apply" cannot fail for a reason the
model could have known. One corrective retry carries the validator's message
back to the model; a second failure is a 422 with that message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from string import Template
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.base_resume import BaseResume
from app.schemas.resume_edit import ResumeEdit, ResumeEditRequest, render_ops_shapes
from app.services import llm, model_settings, prompts
from app.services.resume_edit import apply_edits

MAX_INSTRUCTION_CHARS = 4000


@dataclass
class Proposal:
    summary: str = ""
    notes: str = ""
    ops: list[ResumeEdit] = field(default_factory=list)


def _ask(session: Session, instruction: str, resume: dict, correction: str | None) -> dict:
    prompt = Template(prompts.get_prompt("base_resume_instruct", session)).safe_substitute(
        instruction=instruction,
        resume_json=json.dumps(resume, indent=1),
        op_shapes=render_ops_shapes(),
    )
    if correction:
        prompt += (
            "\n\nYour previous answer did not apply to the document:\n"
            f"{correction}\nReturn a corrected answer in the same JSON shape."
        )
    try:
        result = llm.call_openai(
            prompt=prompt,
            model=model_settings.get_smart_model(session),
            response_format="json",
            trace_name="base-resume-instruct",
        )
    except Exception as exc:  # noqa: BLE001 — provider outage is transient
        raise RuntimeError(f"instruction LLM call failed: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError("the model returned a non-object")
    return result


def _read(result: dict, resume: dict) -> Proposal:
    """Validate the answer: op schema, then a dry run against the document.

    Raises ValueError with a message the model can act on; the caller retries
    once with it.
    """
    raw_ops = result.get("ops")
    if raw_ops is None:
        raw_ops = []
    if not isinstance(raw_ops, list):
        raise ValueError("`ops` must be a list")
    try:
        ops = ResumeEditRequest.model_validate({"ops": raw_ops}).ops
    except ValidationError as exc:
        raise ValueError(f"invalid ops: {exc.errors()[:3]}") from exc
    try:
        apply_edits(resume, ops)  # pure; index bounds and payload errors surface here
    except ValueError as exc:
        raise ValueError(f"ops do not apply to the current resume: {exc}") from exc

    def text(key: str) -> str:
        value = result.get(key)
        return value.strip() if isinstance(value, str) else ""

    return Proposal(summary=text("summary"), notes=text("notes"), ops=ops)


def propose(session: Session, row: BaseResume, instruction: str) -> Proposal:
    """One proposal for `row` from `instruction`.

    ValueError → 422 (empty instruction, or the model's answer could not be
    made to apply after one correction); RuntimeError → 502.
    """
    instruction = (instruction or "").strip()
    if not instruction:
        raise ValueError("Say what you want changed or asked.")
    if len(instruction) > MAX_INSTRUCTION_CHARS:
        raise ValueError(f"Instruction is over {MAX_INSTRUCTION_CHARS} characters.")
    resume: dict[str, Any] = row.data_json
    correction: str | None = None
    for _attempt in range(2):
        result = _ask(session, instruction, resume, correction)
        try:
            return _read(result, resume)
        except ValueError as exc:
            correction = str(exc)
    raise ValueError(f"The model could not produce edits that apply to this resume: {correction}")
