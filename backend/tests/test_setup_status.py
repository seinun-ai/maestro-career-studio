import json

import pytest

from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity
from app.models.setting import Setting
from app.schemas.job_preferences import FavoredRole, JobPreferences
from app.services import job_preferences, persona, text_settings


def _status(client):
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    return r.json()


def _chose_us(db_session, tmp_path, monkeypatch):
    """Where you live and apply saved as the US: the US set, permits and diversity questions included."""
    from app.schemas.market_settings import MarketSetting
    from app.services import market_settings

    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    market_settings.set_market(MarketSetting(home="US", apply_in=["US"]), db_session)


def test_fresh_install_every_step_pending(client):
    body = _status(client)
    assert body["complete"] is False
    for step in ("import_resumes", "job_preferences", "persona", "template"):
        assert body[step]["done"] is False
    assert body["autofill"]["done"] is False
    assert body["autofill"]["readiness"] == 0.0
    # No country chosen yet: no work-permit questions (a permit answer belongs to a country), but
    # citizenship, which counts beside them, is asked and blocks.
    assert body["autofill"]["groups"]["work_auth"] == {"answered": 0, "answerable": 1}
    assert body["autofill"]["blocking"] == ["work_auth"]


def test_status_read_does_not_seed_settings_or_mirrors(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)

    assert db_session.query(Setting).count() == 0
    assert _status(client)["complete"] is False
    assert db_session.query(Setting).count() == 0
    assert list(tmp_path.iterdir()) == []


def test_import_step_flips_on_first_kb_entity(client, db_session):
    db_session.add(KBEntity(kind="experience", title="Data Scientist"))
    db_session.commit()
    assert _status(client)["import_resumes"]["done"] is True


def test_persona_and_preferences_steps(client, db_session):
    persona.set_persona("Builder of shipped things.", db_session)
    job_preferences.set_preferences(
        JobPreferences(role_categories=["data_scientist"]), db_session
    )
    body = _status(client)
    assert body["persona"]["done"] is True
    assert body["job_preferences"]["done"] is True


def test_suggested_bases_are_favored_roles_without_an_active_base(client, db_session):
    job_preferences.set_preferences(
        JobPreferences(role_categories=["data_scientist", "data_engineer"]), db_session
    )
    db_session.add(
        BaseResume(slug="ds", role_category="data_scientist", data_json={"contact": {}})
    )
    db_session.commit()
    suggested = {s["role_category"] for s in _status(client)["suggested_bases"]}
    assert suggested == {"data_engineer"}


def test_mapped_free_text_favored_role_covered_by_matching_tag(db_session, client):
    # THE observable bridge case, and why review rewrote this test: a MAPPED
    # free-text favored role would otherwise suggest its category. An unmapped
    # one never suggests anything, so asserting on it proves nothing — the
    # first draft of this test passed with the entire bridge deleted.
    # Different case on the two labels on purpose.
    job_preferences.set_preferences(
        JobPreferences(
            favored_roles=[
                FavoredRole(
                    role=None,
                    label="Forward Deployed Engineer",
                    category="software_engineer",
                )
            ]
        ),
        db_session,
    )
    db_session.add(
        BaseResume(
            slug="fde",
            role_category="other",
            role_label="forward deployed engineer",
            data_json={"contact": {}},
        )
    )
    db_session.commit()

    # No base carries software_engineer, so without the bridge this suggests.
    assert _status(client)["suggested_bases"] == []


def test_without_a_matching_tag_the_mapped_favored_role_still_suggests(
    db_session, client
):
    # The mirror of the test above, proving it CAN fail: same mapped favored
    # role, but the only base's tag is different words — the suggestion fires.
    job_preferences.set_preferences(
        JobPreferences(
            favored_roles=[
                FavoredRole(
                    role=None,
                    label="Forward Deployed Engineer",
                    category="software_engineer",
                )
            ]
        ),
        db_session,
    )
    db_session.add(
        BaseResume(
            slug="other-role",
            role_category="other",
            role_label="Solutions Architect",
            data_json={"contact": {}},
        )
    )
    db_session.commit()

    assert [s["role_category"] for s in _status(client)["suggested_bases"]] == [
        "software_engineer"
    ]


def test_alias_bridges_the_two_sides(db_session, client):
    # Mapped favored role typed as an alias; the base's tag is the spelled-out
    # form. Either side resolving through the catalog is enough to meet.
    job_preferences.set_preferences(
        JobPreferences(
            favored_roles=[
                FavoredRole(
                    role=None, label="cv engineer", category="ai_ml_engineer"
                ),
            ]
        ),
        db_session,
    )
    db_session.add(
        BaseResume(
            slug="cv",
            role_category="other",
            role_label="Computer Vision Engineer",
            data_json={"contact": {}},
        )
    )
    db_session.commit()

    assert _status(client)["suggested_bases"] == []


def test_free_text_alias_does_not_cover_a_coarse_category(db_session, client):
    job_preferences.set_preferences(
        JobPreferences(role_categories=["ai_ml_engineer"]), db_session
    )
    db_session.add(
        BaseResume(
            slug="cv_only",
            role_category="other",
            role_label="Computer Vision Engineer",
            data_json={"contact": {}},
        )
    )
    db_session.commit()

    suggested = {s["role_category"] for s in _status(client)["suggested_bases"]}
    assert suggested == {"ai_ml_engineer"}


def test_unmapped_mismatch_still_surfaces_nothing(db_session, client):
    job_preferences.set_preferences(
        JobPreferences(
            favored_roles=[
                FavoredRole(role=None, label="Underwater Basket Weaver")
            ]
        ),
        db_session,
    )

    assert _status(client)["suggested_bases"] == []


def _template(db_session, template_id: str, origin: str, *, default: bool) -> None:
    from app.models.template import Template

    db_session.add(
        Template(
            id=template_id,
            source="x",
            engine="typst",
            origin=origin,
            is_default=default,
        )
    )


def test_template_step_is_not_done_while_the_seeded_starter_is_default(client, db_session):
    """A base with template_id=None renders through the is_default fallback, so
    the step must ask whether a default was CHOSEN, not whether every base is
    stamped."""
    db_session.add(BaseResume(slug="a", data_json={}))
    _template(db_session, "typst-classic", "seed", default=True)
    db_session.commit()

    template = _status(client)["template"]
    assert template["done"] is False
    assert template["detail"]["default_origin"] == "seed"


def test_template_step_is_done_once_a_user_made_template_is_default(client, db_session):
    db_session.add(BaseResume(slug="a", data_json={}))
    _template(db_session, "typst-classic", "seed", default=False)
    _template(db_session, "mine", "frontend", default=True)
    db_session.commit()

    template = _status(client)["template"]
    assert template["done"] is True
    assert template["detail"]["default_template_id"] == "mine"


def test_template_step_names_the_default_template(client, db_session):
    """The setup row says "Default: <name>", never the template's id (appendix D7.2)."""
    from app.models.template import Template

    db_session.add(BaseResume(slug="a", data_json={}))
    db_session.add(
        Template(id="mine", source="x", engine="typst", origin="frontend", is_default=True, display_name="My layout")
    )
    db_session.commit()

    assert _status(client)["template"]["detail"]["default_template_name"] == "My layout"


def test_template_step_ignores_bases_without_an_explicit_template(client, db_session):
    """bases_without_template stays as information, never as the gate."""
    db_session.add(BaseResume(slug="a", data_json={}, template_id="mine"))
    db_session.add(BaseResume(slug="b", data_json={}))
    _template(db_session, "mine", "frontend", default=True)
    db_session.commit()

    template = _status(client)["template"]
    assert template["done"] is True
    assert template["detail"]["bases_without_template"] == 1


def test_template_step_is_not_done_with_no_templates_at_all(client, db_session):
    db_session.add(BaseResume(slug="a", data_json={}))
    db_session.commit()

    template = _status(client)["template"]
    assert template["done"] is False
    assert template["detail"]["default_template_id"] is None
    assert template["detail"]["default_template_name"] is None


def test_eeo_decline_counts_as_answered_and_optionals_do_not_block(
    client, db_session, tmp_path, monkeypatch
):
    from app.services import autofill_profile

    _chose_us(db_session, tmp_path, monkeypatch)
    autofill_profile.set_profile(
        {
            "personal": {
                "first_name": "A", "last_name": "B", "email": "a@b.c",
                "phone": "1", "address": "x", "city": "y", "state": "s",
                "postal_code": "1", "country": "US", "linkedin": "l",
                "github": "g", "website": "w", "citizenships": ["IN"],
                # address_2 deliberately absent — optional, must not count
            },
            "work_auth": {
                "status": "opt", "authorized_now": True,
                "sponsorship_now": False, "sponsorship_future": True,
            },
            "eeo": {
                "veteran_status": "decline", "disability_status": "decline",
                "gender": "decline", "hispanic_latino": "decline",
            },
            "preferences": {
                "desired_salary": "100k", "notice_period": "2w",
                "earliest_start_date": "asap", "willing_to_relocate": "no",
                "how_heard": "board",
            },
        },
        db_session,
    )
    body = _status(client)["autofill"]
    assert body["blocking"] == []
    assert body["readiness"] == 1.0
    assert body["done"] is True


def test_authorized_now_is_required_for_work_auth_readiness(
    client, db_session, tmp_path, monkeypatch
):
    from app.services import autofill_profile

    _chose_us(db_session, tmp_path, monkeypatch)
    autofill_profile.set_profile(
        {
            "personal": {
                "first_name": "A", "last_name": "B", "email": "a@b.c",
                "phone": "1", "address": "x", "city": "y", "state": "s",
                "postal_code": "1", "country": "US", "linkedin": "l",
                "github": "g", "website": "w", "citizenships": ["IN"],
            },
            "work_auth": {
                "status": "opt",
                # authorized_now deliberately absent: status must not imply it.
                "sponsorship_now": False,
                "sponsorship_future": True,
            },
            "eeo": {
                "veteran_status": "decline", "disability_status": "decline",
                "gender": "decline", "hispanic_latino": "decline",
            },
            "preferences": {
                "desired_salary": "100k", "notice_period": "2w",
                "earliest_start_date": "asap", "willing_to_relocate": "no",
                "how_heard": "board",
            },
        },
        db_session,
    )

    body = _status(client)["autofill"]

    # Citizenship is given; the US status and two of the three answers are.
    assert body["groups"]["work_auth"] == {"answered": 4, "answerable": 5}
    assert body["groups"]["personal"] == {"answered": 9, "answerable": 9}
    assert body["readiness"] == 0.957
    assert body["blocking"] == ["work_auth"]
    assert body["done"] is False


def test_malformed_profile_group_degrades_to_unanswered(client, db_session):
    from app.services import autofill_profile

    autofill_profile.set_profile({"personal": "garbage"}, db_session)

    body = _status(client)["autofill"]
    # No country chosen, so the state line is not counted: the other eight required answers.
    assert body["groups"]["personal"] == {"answered": 0, "answerable": 8}


def test_contact_links_are_optional_so_a_profile_without_them_is_done(
    client, db_session, tmp_path, monkeypatch
):
    """Most people outside tech have no GitHub or website, and many no LinkedIn: a contact block with
    every other answer given is complete, and an agent's setup next step moves past the form answers."""
    from app.services import autofill_profile

    _chose_us(db_session, tmp_path, monkeypatch)
    autofill_profile.set_profile(
        {
            "personal": {
                "first_name": "Sam", "last_name": "Lee", "email": "sam@example.com",
                "phone": "555 0100", "address": "1 Main St", "city": "Springfield",
                "state": "IL", "postal_code": "62701", "country": "United States",
                "citizenships": ["IN"],
            },
            "work_auth": {
                "status": "citizen", "authorized_now": True,
                "sponsorship_now": False, "sponsorship_future": False,
            },
            "eeo": {
                "veteran_status": "decline", "disability_status": "decline",
                "gender": "decline", "hispanic_latino": "decline",
            },
            "preferences": {
                "desired_salary": "60000", "notice_period": "2 weeks",
                "earliest_start_date": "2026-11-01", "willing_to_relocate": "no",
                "how_heard": "job board",
            },
        },
        db_session,
    )

    body = _status(client)["autofill"]
    assert body["groups"]["personal"] == {"answered": 9, "answerable": 9}
    assert body["readiness"] == 1.0
    assert body["done"] is True


def _answers_but_state(home: str) -> dict:
    """Every answer a form-answers step counts where `home` is where you live, except the state line."""
    work_auth = {"authorized_now": True, "sponsorship_now": False, "sponsorship_future": False}
    if home == "US":
        work_auth["status"] = "citizen"
    return {
        "personal": {
            "first_name": "Sam", "last_name": "Lee", "email": "sam@example.com",
            "phone": "555 0100", "address": "1 Main St", "city": "Springfield",
            "postal_code": "12345", "country": "Example", "citizenships": ["IN"],
        },
        "work_auth_by_country": {home: work_auth},
        "eeo": {
            "veteran_status": "decline", "disability_status": "decline",
            "gender": "decline", "hispanic_latino": "decline",
        },
        "preferences": {
            "desired_salary": "60000", "notice_period": "2 weeks",
            "earliest_start_date": "2026-11-01", "willing_to_relocate": "no",
            "how_heard": "job board",
        },
    }


def test_a_home_whose_addresses_have_no_state_is_done_without_one(client, db_session, tmp_path, monkeypatch):
    """Dutch addresses have no state line (`asks_state: false`): every other answer given is done."""
    from app.schemas.market_settings import MarketSetting
    from app.services import autofill_profile, market_settings

    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    market_settings.set_market(MarketSetting(home="NL", apply_in=["NL"]), db_session)
    autofill_profile.set_profile(_answers_but_state("NL"), db_session)

    body = _status(client)["autofill"]
    assert body["groups"]["personal"] == {"answered": 8, "answerable": 8}
    assert body["readiness"] == 1.0
    assert body["done"] is True


def test_a_us_home_with_no_state_is_not_done(client, db_session, tmp_path, monkeypatch):
    """US forms ask the state, so a US contact block without one still has an answer to give."""
    from app.schemas.market_settings import MarketSetting
    from app.services import autofill_profile, market_settings

    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    market_settings.set_market(MarketSetting(home="US", apply_in=["US"]), db_session)
    autofill_profile.set_profile(_answers_but_state("US"), db_session)

    body = _status(client)["autofill"]
    assert body["groups"]["personal"] == {"answered": 8, "answerable": 9}
    assert body["done"] is False


def test_with_no_country_chosen_the_state_is_not_counted(client, db_session, tmp_path, monkeypatch):
    """No country chosen, no address rule: the state line is optional, and the permit and diversity
    answers stored are not asked, so every other answer given is done."""
    from app.services import autofill_profile

    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    autofill_profile.set_profile(_answers_but_state("US"), db_session)

    body = _status(client)["autofill"]
    assert body["groups"]["personal"] == {"answered": 8, "answerable": 8}
    # Citizenship is the one answer counted beside the (absent) work permits.
    assert body["groups"]["work_auth"] == {"answered": 1, "answerable": 1}
    assert body["work_auth_by_country"] == {} and "eeo" not in body["groups"]
    assert body["done"] is True


@pytest.mark.parametrize(
    "home,answerable",
    [("US", 9), ("CA", 9), ("AU", 9), ("IN", 9), ("UK", 8), ("IE", 8), ("DE", 8), ("NL", 8), ("AE", 8)],
)
def test_the_state_counts_only_where_your_home_puts_one_in_addresses(
    client, db_session, tmp_path, monkeypatch, home, answerable
):
    """A state or province where addresses require one; Ireland's county is written but not required. A UAE
    address has an emirate and no postal code (`asks_postcode: false`)."""
    from app.schemas.market_settings import MarketSetting
    from app.services import market_settings

    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    market_settings.set_market(MarketSetting(home=home, apply_in=[home]), db_session)
    assert _status(client)["autofill"]["groups"]["personal"] == {"answered": 0, "answerable": answerable}


def test_status_reports_engines_and_default_engine_availability(
    client, db_session, monkeypatch
):
    from app.models.template import Template
    from app.services import engines

    # Tests do not run ensure_seed_templates; insert the seeded LaTeX default
    # the plan's assertion names so default_engine_available can be False.
    db_session.add(
        Template(
            id="classic",
            source="x",
            engine="latex",
            origin="seed",
            is_default=True,
        )
    )
    db_session.commit()

    monkeypatch.setattr(
        engines, "probe_pdflatex",
        lambda: engines.EngineStatus("pdflatex", False, reason="pdflatex not found (test)"),
    )
    body = _status(client)
    assert body["engines"]["pdflatex"]["available"] is False
    assert "not found" in body["engines"]["pdflatex"]["reason"]
    assert body["engines"]["typst"]["available"] is True
    assert body["engines"]["typst"]["version"]
    # The seeded default is LaTeX Classic, so its engine is the missing one.
    assert body["template"]["detail"]["default_engine_available"] is False
    assert body["template"]["done"] is False  # engines never change completeness


def _no_keys(monkeypatch):
    from app.config import settings as app_settings

    for name in ("openai_api_key", "gemini_api_key", "anthropic_api_key",
                 "openrouter_api_key", "openai_base_url"):
        monkeypatch.setattr(app_settings, name, "")


def test_model_key_step_is_pending_with_no_key_and_no_endpoint(client, monkeypatch):
    _no_keys(monkeypatch)
    assert _status(client)["model_key"]["done"] is False


def test_model_key_step_done_with_a_claude_key_alone(client, db_session, monkeypatch):
    _no_keys(monkeypatch)
    db_session.add(Setting(key="llm.anthropic_api_key", value="sk-ant-x"))
    db_session.commit()
    assert _status(client)["model_key"]["done"] is True


def test_model_key_step_done_with_a_custom_endpoint_alone(client, db_session, monkeypatch):
    _no_keys(monkeypatch)
    db_session.add(Setting(key="llm.base_url", value="http://localhost:11434/v1"))
    db_session.commit()
    assert _status(client)["model_key"]["done"] is True


def test_work_permits_count_once_per_country_you_apply_in(client, db_session, tmp_path, monkeypatch):
    """Each apply-in country has its own work-permit answers (D9). The US set also asks the visa
    status (`work_auth_vocab: us_visa`); a generic one asks now, now-sponsorship and later."""
    from app.schemas.market_settings import MarketSetting
    from app.services import autofill_profile, market_settings

    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    market_settings.set_market(MarketSetting(home="US", apply_in=["US", "DE"]), db_session)
    autofill_profile.set_profile({"personal": {"citizenships": ["IN"]}, "work_auth_by_country": {
        "US": {"status": "citizen", "authorized_now": True, "sponsorship_now": False,
               "sponsorship_future": False},
        "DE": {"authorized_now": False},
        "UK": {"authorized_now": True},   # not applied in: not counted
    }}, db_session)

    body = _status(client)["autofill"]
    assert body["work_auth_by_country"] == {
        "US": {"answered": 4, "answerable": 4}, "DE": {"answered": 1, "answerable": 3}}
    # Citizenship and both countries' permits.
    assert body["groups"]["work_auth"] == {"answered": 6, "answerable": 8}
    assert body["blocking"] == ["work_auth"]


def test_a_legacy_single_work_auth_answers_only_the_home_country(client, db_session, tmp_path, monkeypatch):
    from app.schemas.market_settings import MarketSetting
    from app.services import autofill_profile, market_settings

    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    market_settings.set_market(MarketSetting(home="UK", apply_in=["UK", "NL"]), db_session)
    autofill_profile.set_profile({"work_auth": {"authorized_now": True, "sponsorship_now": False,
                                                "sponsorship_future": False}}, db_session)

    by_country = _status(client)["autofill"]["work_auth_by_country"]
    assert by_country == {"UK": {"answered": 3, "answerable": 3}, "NL": {"answered": 0, "answerable": 3}}


def test_a_diversity_set_only_for_countries_you_apply_in_that_have_one(client, db_session, tmp_path, monkeypatch):
    """Germany has no checked diversity set: applying there alone asks none. Adding the US asks the US set."""
    from app.schemas.market_settings import MarketSetting
    from app.services import market_settings

    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    market_settings.set_market(MarketSetting(home="DE", apply_in=["DE"]), db_session)
    assert "eeo" not in _status(client)["autofill"]["groups"]

    market_settings.set_market(MarketSetting(home="DE", apply_in=["DE", "US"]), db_session)
    assert _status(client)["autofill"]["groups"]["eeo"] == {"answered": 0, "answerable": 4}


# ------------------------------------------------------- country questions (Task 3.6): knockouts only


def _chose(db_session, tmp_path, monkeypatch, home: str, apply_in: list[str]) -> None:
    from app.schemas.market_settings import MarketSetting
    from app.services import market_settings

    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    market_settings.set_market(MarketSetting(home=home, apply_in=apply_in), db_session)


def _contact(**extra) -> dict:
    """Every contact answer a US home counts but citizenship."""
    return {
        "first_name": "Sam", "last_name": "Lee", "email": "sam@example.com", "phone": "555 0100",
        "address": "1 Main St", "city": "Springfield", "state": "IL", "postal_code": "62701",
        "country": "United States", **extra,
    }


@pytest.mark.parametrize(
    "citizenships,answered",
    [(None, 0), ([], 0), (["Narnia"], 0), ("India", 0), (["IN"], 1), (["IN", "FR"], 1)],
)
def test_citizenship_counts_once_beside_the_work_permits(client, db_session, tmp_path, monkeypatch, citizenships, answered):
    """The one new required answer (Decision 6), counted once in `work_auth` beside the permits it settles
    (Country answers asks it), never in personal though it is stored there. Answered by a list that names a
    country, as the citizenship rules read it (`countries.codes_in`): an empty list, an entry that names no
    country or loose text is no answer."""
    from app.services import autofill_profile

    _chose_us(db_session, tmp_path, monkeypatch)
    personal = _contact() if citizenships is None else _contact(citizenships=citizenships)
    # Written as stored, past the save's own clean-up, so the hand-edited shapes are read as they are.
    text_settings.set_text(
        autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE, json.dumps({"personal": personal}), db_session
    )

    groups = _status(client)["autofill"]["groups"]
    assert groups["personal"] == {"answered": 9, "answerable": 9}
    # Citizenship and the US's four permit answers, none of them stored (IN settles nothing in the US).
    assert groups["work_auth"] == {"answered": answered, "answerable": 5}


def test_a_citizenship_answers_the_work_permits_it_settles(client, db_session, tmp_path, monkeypatch):
    """A French citizen may work in Germany with no permit (the EU rule): Germany's three knockout answers
    count with nothing stored, beside the citizenship itself, and nothing blocks."""
    from app.services import autofill_profile

    _chose(db_session, tmp_path, monkeypatch, "IN", ["DE"])
    autofill_profile.set_profile({"personal": {"citizenships": ["FR"]}}, db_session)

    body = _status(client)["autofill"]
    assert body["work_auth_by_country"] == {"DE": {"answered": 3, "answerable": 3}}
    assert body["groups"]["work_auth"] == {"answered": 4, "answerable": 4}
    assert body["blocking"] == []


def test_a_given_answer_that_differs_turns_the_settled_ones_off(client, db_session, tmp_path, monkeypatch):
    """The user knows something the rule does not: a French citizen who said they may not work in Germany
    has only that answer counted there, and the rest are asked."""
    from app.services import autofill_profile

    _chose(db_session, tmp_path, monkeypatch, "IN", ["DE", "NL"])
    autofill_profile.set_profile(
        {"personal": {"citizenships": ["FR"]}, "work_auth_by_country": {"DE": {"authorized_now": False}}},
        db_session,
    )

    body = _status(client)["autofill"]
    assert body["work_auth_by_country"] == {
        "DE": {"answered": 1, "answerable": 3}, "NL": {"answered": 3, "answerable": 3}}
    assert body["blocking"] == ["work_auth"]


def test_a_countrys_optional_answers_never_count(client, db_session, tmp_path, monkeypatch):
    """India's own answers (current CTC, expected pay) and its notice in days are optional: the same
    readiness without them as with them."""
    from app.services import autofill_profile

    _chose(db_session, tmp_path, monkeypatch, "IN", ["IN"])
    base = {
        "personal": _contact(citizenships=["DE"]),
        "work_auth_by_country": {"IN": {"authorized_now": True}},
        "preferences": {"desired_salary": "20 LPA", "notice_period": "60 days"},
    }
    autofill_profile.set_profile(base, db_session)
    without = _status(client)["autofill"]

    autofill_profile.set_profile({
        **base,
        "answers_by_country": {"IN": {"current_ctc": "18 LPA", "expected_pay": "24 LPA"}},
        "preferences": {**base["preferences"], "notice_days": 60},
    }, db_session)
    stored = autofill_profile.peek_profile(db_session)
    assert stored["answers_by_country"]["IN"]["current_ctc"] == "18 LPA"
    assert stored["preferences"]["notice_days"] == 60
    with_them = _status(client)["autofill"]

    assert with_them["groups"] == without["groups"]
    assert with_them["readiness"] == without["readiness"] < 1.0


def test_with_no_country_chosen_only_citizenship_is_asked_beside_the_permits(
    client, db_session, tmp_path, monkeypatch
):
    """A permit answer belongs to a country: unchosen asks none, even with a half-answered set stored. Citizenship
    is still asked, and blocks until given."""
    from app.services import autofill_profile

    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    autofill_profile.set_profile({"work_auth_by_country": {"US": {"authorized_now": True}}}, db_session)

    body = _status(client)["autofill"]
    assert body["groups"]["work_auth"] == {"answered": 0, "answerable": 1}
    assert body["work_auth_by_country"] == {}
    assert body["blocking"] == ["work_auth"]

    autofill_profile.set_profile({"personal": {"citizenships": ["IN"]}}, db_session)
    body = _status(client)["autofill"]
    assert body["groups"]["work_auth"] == {"answered": 1, "answerable": 1}
    assert body["blocking"] == []


def test_a_uae_home_with_no_postal_code_has_personal_details_complete(client, db_session, tmp_path, monkeypatch):
    from app.services import autofill_profile

    _chose(db_session, tmp_path, monkeypatch, "AE", ["AE"])
    personal = {k: v for k, v in _contact(state="Dubai", citizenships=["IN"]).items() if k != "postal_code"}
    autofill_profile.set_profile({"personal": personal}, db_session)

    assert _status(client)["autofill"]["groups"]["personal"] == {"answered": 8, "answerable": 8}


def test_the_shipped_demo_base_is_named_so_it_is_never_taken_for_the_users(client, db_session):
    from datetime import UTC, datetime

    contact = {"contact": {"name": "Sample", "email": "sample@example.com"}}
    assert _status(client)["demo_bases"] == []
    db_session.add(BaseResume(slug="example", display_name="Example", data_json=contact))
    db_session.add(BaseResume(slug="mine", display_name="Mine", data_json=contact))
    db_session.commit()
    assert _status(client)["demo_bases"] == ["example"]

    # Archived, it still counts in import_resumes' base_resumes (active_filter), so it stays named: an
    # agent subtracts demo_bases from that count, and dropping it would read the demo as the user's.
    db_session.get(BaseResume, "example").archived_at = datetime.now(UTC)
    db_session.commit()
    status = _status(client)
    assert status["demo_bases"] == ["example"]
    assert status["import_resumes"]["detail"]["base_resumes"] == 2

    db_session.get(BaseResume, "example").deleted_at = datetime.now(UTC)
    db_session.commit()
    assert _status(client)["demo_bases"] == []
