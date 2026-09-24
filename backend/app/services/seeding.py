import json
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from app.services import base_resume_data
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity
from app.models.setting import Setting
from app.services import (
    role_categories,
    base_resume_render,
    career_kb,
    kb_consolidation,
    llm,
    persona,
    prompts,
    template_registry,
    text_settings,
    exports as career_exports,
)


logger = logging.getLogger(__name__)

# Marks that the one-time Career KB seed has run. Guarding on this (not the
# entity count) makes the seed truly once-only: a source resume that yields
# zero entities (e.g. skills-only) would otherwise leave the count-based guard
# open forever, re-consolidating on every restart.
KB_SEEDED_FLAG = "kb.seeded"
# The synthetic resume shipped in the repo — a starting point, not the user.
DEMO_SLUG = "example"


def run_migrations() -> None:
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    command.upgrade(Config(str(alembic_ini)), "head")


def _display_name(slug: str) -> str:
    return slug.replace("_", " ").title()


def seed_base_resumes(session: Session) -> list[str]:
    seeded: list[str] = []
    base_dir = Path(settings.base_resumes_dir)
    if not base_dir.exists():
        return seeded

    for path in sorted(base_dir.glob("*.json")):
        slug = path.stem
        if session.get(BaseResume, slug) is not None:
            continue
        session.add(
            BaseResume(
                slug=slug,
                display_name=_display_name(slug),
                data_json=json.loads(path.read_text(encoding="utf-8")),
                # Declare ONLY what is unambiguously true: a slug that is itself
                # a category key. Anything else stays "unknown" and the UI
                # proposes a value rather than this guessing silently. This is
                # the normative path — the equivalent migration backfill matches
                # nothing on a fresh install, because migrations run first.
                role_category=(
                    slug if slug in role_categories.keys() else role_categories.UNKNOWN
                ),
            )
        )
        seeded.append(slug)

    session.commit()

    for slug in seeded:
        try:
            base_resume_render.render_base_resume(slug, session)
        except Exception:
            pass

    return seeded


def seed_prompts(session: Session) -> list[str]:
    seeded: list[str] = []
    for key in sorted(prompts.VALID_PROMPTS):
        setting_key = f"{prompts.PROMPT_PREFIX}{key}"
        if session.get(Setting, setting_key) is not None:
            continue
        value = (prompts.PROMPT_DIR / f"{key}.txt").read_text(encoding="utf-8")
        session.add(Setting(key=setting_key, value=value))
        seeded.append(key)

    session.commit()
    return seeded


def seed_templates(session: Session) -> None:
    """Best-effort: seeded templates must never take down startup."""
    try:
        template_registry.ensure_seed_templates(session)
    except Exception:
        logger.exception("template seeding failed; deferring")


def ensure_persona(session: Session) -> str:
    return text_settings.ensure_text(session, persona.PERSONA_KEY, persona.PERSONA_FILE)


def seed_career_kb(session: Session) -> None:
    """One-time Career KB seed from every active current base-resume snapshot.

    Guarded on the ``kb.seeded`` flag so it runs exactly once, regardless of how
    many entities the seed produced. A missing provider key is the only case
    that leaves the flag unset, so startup retries after configuration; any
    other failure is logged and deferred rather than crashing startup.
    """
    if session.get(Setting, KB_SEEDED_FLAG) is not None:
        return

    # Belt-and-suspenders for installs that seeded before this flag existed:
    # a non-empty KB means the one-time seed already ran.
    if session.scalar(select(func.count()).select_from(KBEntity)):
        session.add(Setting(key=KB_SEEDED_FLAG, value="1"))
        session.commit()
        return

    # EXCLUDE the shipped demo resume. On a fresh clone `example` is the only
    # base, so seeding it makes the demo person the user's KBProfile contact —
    # and `_seed_profile` is deliberately non-clobbering, so a later real import
    # can never replace it. The user would have to clear kb.seeded by hand,
    # which is exactly the chore the import flow exists to remove.
    rows = session.scalars(
        select(BaseResume)
        .where(base_resume_data.active_filter(), BaseResume.slug != DEMO_SLUG)
        .order_by(BaseResume.updated_at.asc(), BaseResume.slug.asc())
    ).all()
    sources = [(row.slug, row.data_json) for row in rows]

    if not sources:
        # Nothing to migrate yet. Leave the flag UNSET so a later-added resume
        # still seeds on a subsequent startup. Re-running this path is a
        # harmless idempotent no-op (get_or_create_profile).
        career_kb.get_or_create_profile(session)
        session.commit()
        return

    if not llm.get_openai_key() and not llm.get_gemini_key():
        logger.warning("KB seed deferred: no LLM key configured")
        return  # flag left unset -> retried once a key is configured

    try:
        # Keep the KB writes and the seeded flag in ONE transaction, so a
        # mid-stage failure leaves nothing committed and the flag unset (the
        # whole thing retries).
        report = kb_consolidation.consolidate(session, sources, commit=False)
        session.add(Setting(key=KB_SEEDED_FLAG, value="1"))
        session.commit()
    except Exception:
        # Do NOT crash app startup on a seed failure; roll back and defer.
        session.rollback()
        logger.exception("KB seed failed; deferring to a later startup")
        return

    logger.info("KB seeded: %s", report.model_dump())


def seed_startup_data(session: Session) -> None:
    seed_base_resumes(session)
    seed_prompts(session)
    seed_templates(session)
    ensure_persona(session)
    seed_career_kb(session)
    career_exports.best_effort_refresh(session)


def run_startup() -> None:
    run_migrations()
    with SessionLocal() as session:
        seed_startup_data(session)
