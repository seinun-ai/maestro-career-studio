from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.setting import Setting


PROMPT_DIR = Path(__file__).parent.parent / "prompts"
PROMPT_PREFIX = "prompt."
VALID_PROMPTS = {
    "extract_jd",
    "qa",
    "cover_letter",
    "gap_enrichment",
    "gap_tailor",
    "coherence_check",
    "tailoring_skill",
    "chat_system",
    "resume_bullet_classify",
    "resume_bullet_rewrite",
    "resume_finding_verify",
    "kb_mint",
    "kb_capture",
    "kb_adapt",
    "kb_document_ingest",
    "kb_entity_resolve",
    "kb_cluster_points",
    "kb_resume_parse",
    "base_from_kb_plan",
    "base_resume_instruct",
    "persona_draft",
    "autofill_choose",
    # NOTE: every key here must have a prompt file: seed_prompts() and
    # GET /api/settings/prompts read PROMPT_DIR/<key>.txt for each key, so
    # registering a fileless name would break startup seeding and the settings UI.
}


def _setting_key(key: str) -> str:
    if key not in VALID_PROMPTS:
        raise KeyError(f"Unknown prompt key: {key}")
    return f"{PROMPT_PREFIX}{key}"


def _prompt_file(key: str) -> Path:
    _setting_key(key)
    return PROMPT_DIR / f"{key}.txt"


def _file_default(key: str) -> str:
    return _prompt_file(key).read_text(encoding="utf-8")


def _get_setting(session: Session, key: str) -> Setting | None:
    return session.scalar(select(Setting).where(Setting.key == _setting_key(key)))


def get_prompt(key: str, session: Session | None = None) -> str:
    owns_session = session is None
    session = session or SessionLocal()
    try:
        existing = _get_setting(session, key)
        if existing is not None:
            return existing.value or ""

        value = _file_default(key)
        session.add(Setting(key=_setting_key(key), value=value))
        session.commit()
        return value
    finally:
        if owns_session:
            session.close()


def set_prompt(key: str, text: str, session: Session | None = None) -> str:
    owns_session = session is None
    session = session or SessionLocal()
    try:
        existing = _get_setting(session, key)
        if existing is None:
            session.add(Setting(key=_setting_key(key), value=text))
        else:
            existing.value = text
        session.commit()
        return text
    finally:
        if owns_session:
            session.close()


def reset_prompt(key: str, session: Session | None = None) -> str:
    return set_prompt(key, _file_default(key), session)
