"""Setup status, derived entirely from existing data — onboarding stores NO
wizard progress (FirstRunImportCard doctrine: derived signals, dismissible).

Readiness counts the form-question catalog's required questions
(services/form_questions, resolved for the stored market), never a list of its
own. Rules:
- "Complete" means ANSWERABLE, not filled: "decline" answers count.
- Optional fields never count, so a country's own answers (all optional) don't.
- Work-permit answers count once per country you apply in (`work_auth_by_country`,
  keyed by market); no country chosen asks none.
- They are the knockout answers the extension reports missing_source on, so they
  are read as readers see them: each country's stored answers over the ones a
  citizenship settles there (`autofill_derive.answers_for`), through the typed
  reader.
- Citizenship (`personal.citizenships`, a `countries` list) counts in the
  `work_auth` group, beside the permits it settles, never in personal: Profile
  asks it in Country answers, and Contact never shows it.
- The `work_auth` group is citizenship plus every country's permits. Only a
  country's missing knockout answer blocks: a missing citizenship shows in the
  group and in readiness but blocks nothing. Each country's own count rides
  along for the setup flow's one-question-per-country step.
"""

from sqlalchemy import func, select

from app.services import base_resume_data
from sqlalchemy.orm import Session

from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity
from app.models.template import Template
from app.schemas.form_questions import Field as FormField, QuestionSet
from app.schemas.setup_status import (
    AutofillStep,
    EnginesProbe,
    GroupCompleteness,
    SetupStatus,
    SetupStep,
    SuggestedBase,
)
from app.services import (
    autofill_derive,
    autofill_profile,
    countries,
    engines,
    form_questions,
    job_preferences,
    market_settings,
    persona,
    role_categories,
)


def _answered(field: FormField, value) -> bool:
    """Whether `value` answers `field`. A list of countries (`type: countries`, citizenship) answers
    only when it names one, as the citizenship rules read it (`countries.codes_in`): an empty list,
    an entry that names no country or loose text is no answer. Any other list answers when it holds
    something."""
    if field.type == "countries":
        return bool(countries.codes_in(value))
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return True  # booleans (False is an answer), numbers


def _group(profile: dict, key: str, fields: list[FormField]) -> GroupCompleteness:
    """How many of `fields`' required ones (`form_questions.required_fields`) the stored group `key`
    answers."""
    values = profile.get(key) or {}
    if not isinstance(values, dict):
        values = {}
    required = form_questions.required_fields(fields)
    answered = sum(1 for f in required if _answered(f, values.get(f.key)))
    return GroupCompleteness(answered=answered, answerable=len(required))


def _work_permits(profile: dict, questions: QuestionSet) -> dict[str, GroupCompleteness]:
    """Each apply-in country's knockout answers (`questions.countries`; none when unchosen): its
    required permit questions (the US status, the three yes/no answers; the other status lists and
    the expiry are optional), answered as readers see them (`autofill_derive.answers_for`: the
    stored answers over the ones a citizenship settles there, unless a stored one differs). The
    profile is a read view, its legacy single set already placed, so no `home` is passed."""
    out: dict[str, GroupCompleteness] = {}
    for country in questions.countries:
        work_auth = autofill_profile.typed_work_auth(
            autofill_derive.answers_for(profile, country.market), country.market
        )
        keys = form_questions.required_keys(country.permits)
        out[country.market] = GroupCompleteness(
            answered=sum(1 for k in keys if getattr(work_auth, k) is not None), answerable=len(keys))
    return out


def _autofill_step(db: Session) -> AutofillStep:
    profile = autofill_profile.peek_profile(db)
    market = market_settings.peek_market(db)
    questions = form_questions.resolve(
        home=market.home, apply_in=market.apply_in, chosen=market.chosen, profile=profile
    )
    fields = {g.key: g.fields for g in questions.groups}
    # Citizenship (the `countries` list, stored in personal) counts with the permits it settles.
    contact = [f for f in fields["personal"] if f.type != "countries"]
    citizenship = _group(profile, "personal", [f for f in fields["personal"] if f.type == "countries"])
    by_country = _work_permits(profile, questions)
    permits = [citizenship, *by_country.values()]
    groups = {
        "personal": _group(profile, "personal", contact),
        "work_auth": GroupCompleteness(
            answered=sum(g.answered for g in permits),
            answerable=sum(g.answerable for g in permits),
        ),
        "preferences": _group(profile, "preferences", fields["preferences"]),
    }
    # The diversity group is the US question set — veteran status, CC-305
    # disability, and the EEO-1's two-part hispanic_latino ethnicity split.
    # Counting it as required in a market with no verified question set made
    # 100% readiness unreachable for every non-US user, and readiness is what
    # the setup strip reports as "done". Only the countries you apply in that
    # have a checked module (US, UK today) ask diversity answers; with none of
    # them, the group is omitted from the denominator rather than scored as
    # unanswered.
    if questions.offers_eeo:
        groups["eeo"] = _group(profile, "eeo", fields["eeo"])
    answered = sum(g.answered for g in groups.values())
    answerable = sum(g.answerable for g in groups.values())
    # Only the knockout answers block (setup-steps.ts `autofillTarget`): a country's permit answers,
    # never the citizenship counted beside them.
    blocking = ["work_auth"] if any(g.answered < g.answerable for g in by_country.values()) else []
    readiness = round(answered / answerable, 3) if answerable else 1.0
    return AutofillStep(
        done=readiness >= 1.0, readiness=readiness, groups=groups, blocking=blocking,
        work_auth_by_country=by_country,
    )


def _demo_bases(bases: list[BaseResume]) -> list[str]:
    """The shipped demo among the bases base_resumes counts, so the count minus these is the user's."""
    from app.services.seeding import DEMO_SLUG  # noqa: PLC0415 (seeding imports the world)

    return [b.slug for b in bases if b.slug == DEMO_SLUG]


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
    # Derived like every other step: no probe result is consulted and nothing
    # is stored. Whether a key WORKS is what `POST /settings/openai/probe`
    # answers; this is only whether one is configured at all, which is the
    # difference between "the app cannot run" and "a model might refuse".
    # It lives on /settings, not /profile — readiness already spans surfaces
    # (import → /career, template → /templates).
    from app.services import llm

    key_configured = llm.any_model_key_configured()
    probed = engines.probe()
    default_engine_available = (
        default_tpl is None or default_tpl.engine != "latex" or probed.pdflatex.available
    )
    steps = SetupStatus(
        model_key=SetupStep(done=key_configured),
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
                # The setup row names the template, never its id.
                "default_template_name": getattr(default_tpl, "display_name", None),
                "default_origin": default_tpl.origin if default_tpl else None,
                # Information only — an unstamped base renders via the fallback.
                "bases_without_template": sum(1 for b in active_bases if not b.template_id),
                "default_engine_available": default_engine_available,
            },
        ),
        engines=EnginesProbe.model_validate(probed),
        suggested_bases=suggested,
        demo_bases=_demo_bases(active_bases),
        complete=False,
    )
    steps.complete = all(
        s.done
        for s in (
            steps.model_key, steps.import_resumes, steps.autofill,
            steps.job_preferences, steps.persona, steps.template,
        )
    )
    return steps
