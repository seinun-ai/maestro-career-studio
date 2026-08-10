"""The candidate's persona: vision, strengths, goals, working style.

Freeform durable context injected into the writing prompts (tailoring, Q&A,
cover letters) to keep every generated document in the
candidate's own voice. It shapes tone and emphasis — it is never a source of
new factual claims.
"""

import json
from string import Template

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.career_kb import KBEntity
from app.services import text_settings

PERSONA_KEY = "persona"
PERSONA_FILE = "persona.md"


def get_persona(session: Session | None = None) -> str:
    return text_settings.get_text(PERSONA_KEY, PERSONA_FILE, session)


def peek_persona(session: Session | None = None) -> str:
    return text_settings.peek_text(PERSONA_KEY, PERSONA_FILE, session)


def set_persona(text: str, session: Session | None = None) -> str:
    return text_settings.set_text(PERSONA_KEY, PERSONA_FILE, text, session)


def draft_persona(session: Session) -> str:
    """Propose persona text from the KB compose + job preferences.

    Persists nothing: the user reviews and explicitly saves the resulting
    draft in the persona editor. An empty KB cannot ground a persona.
    """
    from app.services import career_kb, job_preferences, llm, model_settings, prompts

    if not (session.scalar(select(func.count()).select_from(KBEntity)) or 0):
        raise ValueError("Career KB is empty — import a resume first, then draft.")

    resume = career_kb.compose_resume_data(session)
    memory_text = career_kb.compose_context(session)
    prefs = job_preferences.get_preferences(session)

    prompt = Template(prompts.get_prompt("persona_draft", session)).safe_substitute(
        resume_json=json.dumps(
            resume.model_dump() if hasattr(resume, "model_dump") else resume,
            indent=1,
        ),
        memory=memory_text or "(none)",
        preferences_json=prefs.model_dump_json(indent=1),
    )
    return llm.call_openai(
        prompt=prompt,
        model=model_settings.get_smart_model(session),
        response_format="text",
        trace_name="persona-draft",
    ).strip()
