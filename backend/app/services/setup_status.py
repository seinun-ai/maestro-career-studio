"""Setup status, derived entirely from existing data — onboarding stores NO
wizard progress (FirstRunImportCard doctrine: derived signals, dismissible).

The autofill field lists are a hand-mirror of the frontend GROUPS array in
frontend/components/settings/autofill-section.tsx (the ALLOWED_STATUSES /
APPLICATION_STATUSES precedent) — update BOTH when a field is added. Rules:
"complete" means ANSWERABLE, not filled ("decline" answers count; optional
fields are excluded), and work_auth is read through the typed reader because
its answers are the knockout ones the extension reports missing_source on.
"""

from sqlalchemy import func, select

from app.services import base_resume_data
from sqlalchemy.orm import Session

from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity
from app.models.template import Template
from app.schemas.setup_status import (
    AutofillStep,
    GroupCompleteness,
    SetupStatus,
    SetupStep,
    SuggestedBase,
)
from app.services import (
    autofill_profile,
    job_preferences,
    market_settings,
    persona,
    role_categories,
)

# Required (answerable) fields per group. address_2 / education / custom Q&A
# never count against readiness.
_PERSONAL = [
    "first_name", "last_name", "email", "phone", "address", "city", "state",
    "postal_code", "country", "linkedin", "github", "website",
]
_EEO = ["veteran_status", "disability_status", "gender", "hispanic_latino"]
_PREFERENCES = [
    "desired_salary", "notice_period", "earliest_start_date",
    "willing_to_relocate", "how_heard",
]
# The typed work-auth core; authorization and sponsorship answers are knockout-grade.
_WORK_AUTH_CORE = [
    "status", "authorized_now", "sponsorship_now", "sponsorship_future",
]


def _answered(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True  # booleans (False is an answer), numbers, lists


def _group(profile: dict, key: str, fields: list[str]) -> GroupCompleteness:
    values = profile.get(key) or {}
    if not isinstance(values, dict):
        values = {}
    answered = sum(1 for f in fields if _answered(values.get(f)))
    return GroupCompleteness(answered=answered, answerable=len(fields))


def _autofill_step(db: Session) -> AutofillStep:
    profile = autofill_profile.peek_profile(db)
    work_auth = autofill_profile.peek_work_auth(db)
    groups = {
        "personal": _group(profile, "personal", _PERSONAL),
        "work_auth": GroupCompleteness(
            answered=sum(1 for f in _WORK_AUTH_CORE if getattr(work_auth, f) is not None),
            answerable=len(_WORK_AUTH_CORE),
        ),
        "preferences": _group(profile, "preferences", _PREFERENCES),
    }
    # `_EEO` is the US question set — veteran status, CC-305 disability, and the
    # EEO-1's two-part hispanic_latino ethnicity split. Counting it as required
    # in a market with no verified question set made 100% readiness unreachable
    # for every non-US user, and readiness is what the setup strip reports as
    # "done". A market that offers no EEO module contributes no EEO answers, so
    # it is omitted from the denominator rather than scored as unanswered.
    if market_settings.offers_eeo(db):
        groups["eeo"] = _group(profile, "eeo", _EEO)
    answered = sum(g.answered for g in groups.values())
    answerable = sum(g.answerable for g in groups.values())
    wa = groups["work_auth"]
    blocking = ["work_auth"] if wa.answered < wa.answerable else []
    readiness = round(answered / answerable, 3) if answerable else 1.0
    return AutofillStep(
        done=readiness >= 1.0, readiness=readiness, groups=groups, blocking=blocking
    )


def build_status(db: Session) -> SetupStatus:
    kb_entities = db.scalar(select(func.count()).select_from(KBEntity)) or 0

    active_bases = db.scalars(
        select(BaseResume).where(base_resume_data.active_filter())
    ).all()

    prefs = job_preferences.peek_preferences(db)

    def _resolve(label: str | None) -> str | None:
        # casefold identity, with one chance to resolve through the catalog so
        # "cv engineer" and "Computer Vision Engineer" meet if EITHER side
        # resolves. No fuzz beyond this: a near-miss is visibly uncovered.
        if not label:
            return None
        match = role_categories.match_free_text(label)
        if match["category"] is not None:
            return f"cat:{match['category']}"
        return f"label:{label.casefold()}"

    covered = {b.role_category for b in active_bases}
    covered |= {
        key for key in (_resolve(b.role_label) for b in active_bases) if key
    }
    labels = role_categories.labels()
    suggested: list[SuggestedBase] = []
    seen_suggestions: set[str] = set()
    for favored in prefs.favored_roles:
        # The label bridge fires for FREE-TEXT favored roles (role is None),
        # mapped or not: a base tagged with the same words — or words that
        # resolve to the same place — covers them, even when no base carries
        # the mapped category. Catalog picks stay off the bridge: picking
        # "Data Scientist" asks for a data-scientist RESUME, and a base whose
        # free-text tag merely resolves near it is not that resume.
        # (Review fix: the first draft consulted the bridge only in a branch
        # whose both arms `continue`d — an observable no-op.)
        if favored.role is None and _resolve(favored.label) in covered:
            continue
        if favored.category is None:
            # Unmapped custom roles deliberately drive no suggestion — there
            # is no safe category to propose. Decided 2026-08-10.
            continue
        if (
            favored.category in covered
            or favored.category in seen_suggestions
        ):
            continue
        seen_suggestions.add(favored.category)
        suggested.append(
            SuggestedBase(
                role_category=favored.category,
                label=labels.get(favored.category, favored.category),
            )
        )

    # "Has a default template been CHOSEN?" — not "does every base carry an
    # explicit template_id". A base with template_id=None renders through the
    # is_default fallback (base_resume_render.py:24-25), so the old predicate
    # flagged a non-problem, and satisfying it meant stamping every base through
    # the full PUT, which recompiles each PDF. `origin` separates the shipped
    # starter ("seed") from anything the user made or imported.
    #
    # Known trade-off: deliberately keeping the seeded starter as the default
    # reads as incomplete forever. That is a false NEGATIVE on a step that is
    # non-blocking and dismissible, and the only alternative is recording that
    # the user pressed a button — the stored onboarding progress this module's
    # docstring forbids. Do not "fix" this by adding a flag.
    default_tpl = db.scalar(select(Template).where(Template.is_default.is_(True)))

    autofill = _autofill_step(db)
    steps = SetupStatus(
        import_resumes=SetupStep(
            done=kb_entities > 0,
            detail={"kb_entities": kb_entities, "base_resumes": len(active_bases)},
        ),
        autofill=autofill,
        job_preferences=SetupStep(done=job_preferences.is_set(prefs)),
        persona=SetupStep(done=bool(persona.peek_persona(db).strip())),
        template=SetupStep(
            done=default_tpl is not None and default_tpl.origin != "seed",
            detail={
                "default_template_id": default_tpl.id if default_tpl else None,
                "default_origin": default_tpl.origin if default_tpl else None,
                # Information only — an unstamped base renders via the fallback.
                "bases_without_template": sum(1 for b in active_bases if not b.template_id),
            },
        ),
        suggested_bases=suggested,
        complete=False,
    )
    steps.complete = all(
        s.done
        for s in (
            steps.import_resumes, steps.autofill, steps.job_preferences,
            steps.persona, steps.template,
        )
    )
    return steps
