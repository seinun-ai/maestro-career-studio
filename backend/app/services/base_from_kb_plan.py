"""Plan a role-targeted base resume from the Career KB, from a free instruction.

Proposes; persists nothing. The caller reviews the selection and the drafted
summary and then calls `POST /base-resumes/from-kb` to create — the same
propose-then-approve shape as `persona.draft_persona`.

Deliberately does NOT touch bullet wording. Approved KB points are the
candidate's own verified evidence and are composed verbatim; rewriting them is
`kb_adapt`'s job, which proposes per-bullet changes WITH provenance and requires
approval. A create-time rewrite would launder invented text into a resume under
the appearance of a routine action.
"""

from dataclasses import dataclass, field
from string import Template
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.career_kb import KBEntity
from app.services import llm, model_settings, prompts, role_categories

# Kinds whose resume rendering does not come from bullets.
_RENDERS_WITHOUT_POINTS = {"certification", "education"}


@dataclass(frozen=True)
class ExcludedEntity:
    """One KB entry the plan left off, with a reason shown to the user."""

    id: UUID
    title: str
    reason: str


@dataclass
class BasePlan:
    include: list[UUID] = field(default_factory=list)
    exclude: list[ExcludedEntity] = field(default_factory=list)
    summary: str = ""


def _render_entities(entities: list[KBEntity], approved: dict[UUID, int]) -> str:
    """One line per entry.

    The bullet count is shown ONLY where bullets are what the section renders.
    Printing "0 approved points" next to a certification made the model exclude
    every one of them as "would render empty" — it reasoned from a number that
    does not apply to that section.
    """
    lines = []
    for e in entities:
        dates = " – ".join(v for v in (e.start_date, e.end_date) if v) or "—"
        detail = (
            "renders without bullets"
            if e.kind in _RENDERS_WITHOUT_POINTS
            else f"{approved.get(e.id, 0)} approved bullets"
        )
        lines.append(
            f"{e.id} | {e.kind} | {e.title} | {e.org or ''} | {dates} | {detail}"
        )
    return "\n".join(lines)


def _selectable(session: Session) -> tuple[list[KBEntity], dict[UUID, int]]:
    """The entries a plan may legitimately choose from, and their bullet counts.

    Experience and projects render FROM their bullets, so one with none approved
    would be an empty entry. Certifications compose to a bare title string and
    education to institution/degree/dates, so those render fine with zero —
    excluding them silently dropped every certification the candidate held, on
    real data, before this distinction existed.
    """
    entities = list(
        session.scalars(
            select(KBEntity)
            .where(KBEntity.status != "archived")
            .order_by(KBEntity.kind, KBEntity.title)
        )
    )
    if not entities:
        raise ValueError("Career KB is empty — import a resume first.")

    approved = {
        e.id: sum(1 for p in e.points if p.state == "approved") for e in entities
    }
    keep = [
        e
        for e in entities
        if e.kind in _RENDERS_WITHOUT_POINTS or approved[e.id] > 0
    ]
    return keep, approved


def _ask(
    session: Session,
    role_category: str,
    instruction: str,
    entities: list[KBEntity],
    approved: dict[UUID, int],
) -> dict:
    labels = role_categories.labels()
    prompt = Template(prompts.get_prompt("base_from_kb_plan", session)).safe_substitute(
        role_label=labels.get(role_category, role_category),
        instruction=(instruction or "").strip() or "(none given)",
        entities=_render_entities(entities, approved),
    )
    try:
        result = llm.call_openai(
            prompt=prompt,
            model=model_settings.get_smart_model(session),
            response_format="json",
            trace_name="base-from-kb-plan",
        )
    except Exception as exc:  # noqa: BLE001 — provider outage is transient
        raise RuntimeError(f"base plan LLM call failed: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError("base plan returned a non-object")
    return result


def _read(result: dict, titles: dict[UUID, str]) -> BasePlan:
    """Validate the model's answer against the entries it was actually shown."""

    def known(value: object) -> UUID | None:
        """Ids the model made up must never reach the compose call."""
        try:
            parsed = UUID(str(value))
        except (ValueError, AttributeError, TypeError):
            return None
        return parsed if parsed in titles else None

    out = BasePlan()
    for raw in result.get("include") or []:
        entity_id = known(raw)
        if entity_id is not None:
            out.include.append(entity_id)

    for raw in result.get("exclude") or []:
        if not isinstance(raw, dict):
            continue
        entity_id = known(raw.get("id"))
        if entity_id is None or entity_id in out.include:
            continue
        reason = raw.get("reason")
        out.exclude.append(
            ExcludedEntity(
                id=entity_id,
                title=titles[entity_id],
                reason=(
                    reason if isinstance(reason, str) and reason.strip() else "not selected"
                ),
            )
        )

    summary = result.get("summary")
    out.summary = summary.strip() if isinstance(summary, str) else ""
    return out


def plan(session: Session, role_category: str, instruction: str) -> BasePlan:
    """Propose which KB entries belong on a base resume for `role_category`.

    Raises ValueError on an empty KB or unusable model output (router -> 422),
    RuntimeError when the provider is unavailable (router -> 502).
    """
    entities, approved = _selectable(session)
    result = _ask(session, role_category, instruction, entities, approved)
    return _read(result, {e.id: e.title for e in entities})
