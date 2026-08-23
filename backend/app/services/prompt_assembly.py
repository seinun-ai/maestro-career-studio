import json
from string import Template
from typing import Any

from app.services import prompts


def _json_block(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def _render_template(key: str, values: dict[str, str]) -> str:
    template = Template(prompts.get_prompt(key))
    return template.safe_substitute(values).strip()


def _skill_preamble() -> str:
    """The tailoring judgment doc, prepended (not $-substituted) into the writing
    prompts. Prepend, not placeholder: safe_substitute silently drops unknown
    $vars and a DB-seeded prompt row would never gain a new one, so a placeholder
    would vanish on seeded deployments. get_prompt lazy-seeds its own key."""
    return prompts.get_prompt("tailoring_skill").strip()


def _persona_block(persona: str) -> str:
    """The candidate's persona, prepended (not $-substituted) for the same
    reason as _skill_preamble: seeded prompt rows never gain new placeholders.
    Empty persona -> empty block, so prompts are unchanged until one is set."""
    text = (persona or "").strip()
    if not text:
        return ""
    return (
        "CANDIDATE PERSONA (durable personal context — vision, strengths, goals, "
        "working style; use it to shape voice and emphasis, never as a source of "
        "factual claims about experience):\n"
        f"{text}\n\n---\n\n"
    )


def _questions_block(questions: list[str]) -> str:
    return "\n".join(f"{index}. {question}" for index, question in enumerate(questions, start=1))


def build_extraction_prompt(raw_jd: str) -> str:
    # $role_options is generated from ats/data/role_categories.yaml so the
    # prompt's option list cannot drift from what the code accepts.
    from app.services import role_categories

    return _render_template(
        "extract_jd",
        {"raw_jd": raw_jd, "role_options": role_categories.prompt_options()},
    )


def _user_prompt_section(user_prompt: str | None) -> str:
    text = (user_prompt or "").strip()
    if not text:
        return ""
    return (
        "\n\nUSER PROMPT (optional tailoring instructions — follow only when "
        "consistent with the resume and JD):\n"
        f"{text}"
    )


def build_gap_tailor_prompt(
    resume_json: dict[str, Any],
    jd_json: dict[str, Any],
    resolutions: list[dict[str, Any]],
    skipped_gaps: list[str],
    user_prompt: str | None = None,
    persona: str = "",
    already_applied: list[str] | None = None,
) -> str:
    """Prompt for the resolutions -> typed edit ops call.

    `resolutions` are the non-skip resolutions, each joined with its gap's
    diagnostic/enrichment and exact placement target (including a stable
    ``section_key`` for custom sections); `skipped_gaps` are display names
    listed only under the do-not-touch heading (explicitly out of the LLM's
    mandate).
    """
    already_applied_section = _already_applied_section(already_applied)
    body = _render_template(
        "gap_tailor",
        {
            "resume_json": _json_block(resume_json),
            "jd_json": _json_block(jd_json),
            "resolutions_json": json.dumps(resolutions, indent=2, sort_keys=True),
            "skipped_gaps_json": json.dumps(skipped_gaps, indent=2),
            "already_applied_section": already_applied_section,
            "user_prompt_section": _user_prompt_section(user_prompt),
        },
    )
    # Existing customized prompt rows may predate the new placeholder. Preserve
    # the guardrail by prepending it when substitution had nowhere to render it.
    if already_applied_section and already_applied_section not in body:
        body = f"{already_applied_section}\n\n{body}"
    return f"{_skill_preamble()}\n\n---\n\n{_persona_block(persona)}{body}"


def _already_applied_section(lines: list[str] | None) -> str:
    applied = [line.strip() for line in lines or [] if isinstance(line, str) and line.strip()]
    if not applied:
        return ""
    rendered = "\n".join(f"- {line}" for line in applied)
    return f"Already applied — do not redo or undo:\n{rendered}"


def build_gap_enrichment_prompt(
    resume_json: dict[str, Any],
    jd_json: dict[str, Any],
    gaps_json: dict[str, Any],
    *,
    kb_snapshot: dict[str, Any] | None = None,
    disabled_entries: list[dict[str, Any]] | None = None,
) -> str:
    body = _render_template(
        "gap_enrichment",
        {
            "resume_json": _json_block(resume_json),
            "jd_json": _json_block(jd_json),
            "gaps_json": _json_block(gaps_json),
        },
    )
    library_block = _library_evidence_block(kb_snapshot, disabled_entries)
    return f"{_skill_preamble()}\n\n---\n\n{library_block}{body}"


def build_coherence_check_prompt(
    customized_json: dict[str, Any], changed_loci: list[dict[str, Any]]
) -> str:
    """Read-only lint prompt over the tailored document's changed loci."""
    return _render_template(
        "coherence_check",
        {
            "resume_json": _json_block(customized_json),
            "changed_loci": _json_block(changed_loci),
        },
    )


def _library_evidence_block(
    kb_snapshot: dict[str, Any] | None,
    disabled_entries: list[dict[str, Any]] | None,
) -> str:
    if kb_snapshot is None:
        return ""

    lines = ["## Career knowledge base"]
    profile_skills = kb_snapshot.get("profile_skills") or []
    lines.append("Profile skills: " + json.dumps(profile_skills, ensure_ascii=False))
    for entity in kb_snapshot.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        entity_id = entity.get("id")
        lines.append(
            f"- [entity_id={entity_id}] kind={entity.get('kind')} "
            f"title={entity.get('title')!r} status={entity.get('status')} "
            f"tech={json.dumps(entity.get('tech') or [], ensure_ascii=False)}"
        )
        for point in entity.get("points") or []:
            if not isinstance(point, dict):
                continue
            lines.append(
                f"  - [point_id={point.get('id')} entity_id={entity_id} "
                f"state={point.get('state')}] {point.get('text')}"
            )

    lines.extend(
        [
            "",
            "## Disabled resume entries",
            "These are not currently on the resume; they may be proposed as evidence.",
        ]
    )
    for entry in disabled_entries or []:
        if not isinstance(entry, dict):
            continue
        lines.append(
            f"- [section={entry.get('section')} index={entry.get('index')}] "
            f"name={entry.get('name')!r}\n{entry.get('text') or ''}"
        )
    lines.extend(
        [
            "",
            "For each missing-skills gap, nominate at most 3 library_candidates by the real "
            "ids or full-array indices above. Never invent ids. Prefer approved points. "
            "Candidate kind is disabled, kb_point, or profile; include placement_target "
            "for kb_point candidates when an enabled destination is known.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


# CODE-LEVEL immutable output contract for screening-question answers
# (SYSTEM.md §11 8b, qa half). Prepended — never $-substituted — so it survives
# ANY user-customized prompt.qa Setting row; form fields and clipboard targets
# are plain-text surfaces, and markdown here leaks verbatim into applications.
QA_OUTPUT_CONTRACT = """NON-NEGOTIABLE ANSWER RULES (these override anything below):
- Never fabricate experience, skills, employers, dates, or credentials; answer only from the resume, job description, and career context provided.
- Output PLAIN TEXT only: no markdown of any kind — no **bold**, no headings, no backticks, no bullet markers, no horizontal rules.
- When multiple questions are asked, answer each question in order as a numbered list ("1. ...", "2. ...") with exactly one entry per question, matching the question count; never restate, echo, or repeat the question text itself — give each answer directly.
- Keep each answer concise: a few sentences unless the question explicitly demands more."""


def build_qa_prompt(
    resume_json: dict[str, Any],
    jd_json: dict[str, Any],
    memory: str,
    questions: list[str],
    persona: str = "",
    referral: dict[str, Any] | None = None,
) -> str:
    body = _render_template(
        "qa",
        {
            "resume_json": _json_block(resume_json),
            "jd_json": _json_block(jd_json),
            "memory": memory,
            "questions": _questions_block(questions),
            "referral_section": _referral_section(referral),
        },
    )
    return f"{QA_OUTPUT_CONTRACT}\n\n---\n\n{_persona_block(persona)}{body}"


# CODE-LEVEL immutable output contract for cover letters. Prepended — never
# $-substituted — so it survives ANY user-customized prompt.cover_letter
# Setting row, same reason as QA_OUTPUT_CONTRACT above.
COVER_LETTER_OUTPUT_CONTRACT = """NON-NEGOTIABLE COVER LETTER RULES (these override anything below):
- Never state skills, achievements, numbers, dates, credentials, or employer facts that are absent from the provided resume, career context, and job description.
- Never fabricate enthusiasm about facts not in evidence.
- Respect the requested tone.
- Output PLAIN PROSE only: no markdown headers, no heading markers, no fenced code.
- Never use em-dashes (—) or en-dashes (–); write commas or hyphens instead."""


def build_cover_letter_prompt(
    resume_json: dict[str, Any],
    jd_json: dict[str, Any],
    memory: str,
    tone: str,
    persona: str = "",
) -> str:
    body = _render_template(
        "cover_letter",
        {
            "resume_json": _json_block(resume_json),
            "jd_json": _json_block(jd_json),
            "memory": memory,
            "tone": tone,
        },
    )
    return f"{COVER_LETTER_OUTPUT_CONTRACT}\n\n---\n\n{_persona_block(persona)}{body}"


# CODE-LEVEL immutable output contract for the second fill pass's chooser
# (Task 5). Prepended — never $-substituted — for the same reason as
# QA_OUTPUT_CONTRACT above: it must survive any user-customized prompt.
# autofill_choose Setting row, and it carries the one rule this endpoint exists
# to enforce — abstain is the default, not an error.
CHOOSE_OUTPUT_CONTRACT = """NON-NEGOTIABLE RULES (these override anything below):
- You are FILLING A FORM FIELD, not writing prose. Never explain, never add a sentence around an answer.
- Answer ONLY from the profile and career context provided. If they do not contain the answer, return null. Returning null is the correct, expected outcome for most fields — it is never a failure.
- Never invent an employer, date, credential, number, skill, or preference that is not in the provided context.
- When a field lists options, your answer MUST be one of those option strings copied EXACTLY, character for character. Never paraphrase an option, never combine two, never invent a seventh.
- When a field has a known_value, the profile ALREADY holds the answer and your only job is to say which listed option means the same thing. If none of them does, return null.
- Return a single JSON object: {"choices": {"<qid>": {"answer": <string or null>, "reason": "matched" or "abstained"}}}. Include every qid you were given, exactly once."""


def build_autofill_choose_prompt(
    profile: dict[str, Any],
    memory: str,
    fields: list[dict[str, Any]],
    persona: str = "",
) -> str:
    body = _render_template(
        "autofill_choose",
        {
            "profile": _json_block(profile),
            "memory": memory,
            # fields is a LIST (one dict per qid), not the dict _json_block
            # expects — same json.dumps call, sorted+indented to match.
            "fields": json.dumps(fields, indent=2, sort_keys=True),
        },
    )
    return f"{CHOOSE_OUTPUT_CONTRACT}\n\n---\n\n{_persona_block(persona)}{body}"


def _referral_section(referral: dict[str, Any] | None) -> str:
    if not referral:
        return ""
    parts = [referral.get("contact_name"), referral.get("company")]
    label = " at ".join(p for p in parts if p)
    if not label:
        return ""
    lines = [f"\n\nKNOWN CONTACT for this application: {label}."]
    if referral.get("notes"):
        lines.append(f"Notes: {referral['notes']}")
    # This block is injected into EVERY application-level QA batch; without a
    # guardrail the model may greet or name the contact in an ordinary
    # screening answer. Keep the contact scoped to outreach-style requests.
    lines.append(
        "This contact is context for outreach-style requests only; never "
        "mention or address the contact in ordinary screening answers."
    )
    return "\n".join(lines)
