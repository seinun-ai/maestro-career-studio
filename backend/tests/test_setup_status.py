import pytest
from fastapi.testclient import TestClient

from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity
from app.models.setting import Setting
from app.schemas.job_preferences import JobPreferences
from app.services import job_preferences, persona, text_settings


@pytest.fixture
def client(db_session):
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _status(client):
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    return r.json()


def test_fresh_install_every_step_pending(client):
    body = _status(client)
    assert body["complete"] is False
    for step in ("import_resumes", "job_preferences", "persona", "template"):
        assert body[step]["done"] is False
    assert body["autofill"]["done"] is False
    assert body["autofill"]["readiness"] == 0.0
    assert "work_auth" in body["autofill"]["blocking"]


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


def test_eeo_decline_counts_as_answered_and_optionals_do_not_block(client, db_session):
    from app.services import autofill_profile

    autofill_profile.set_profile(
        {
            "personal": {
                "first_name": "A", "last_name": "B", "email": "a@b.c",
                "phone": "1", "address": "x", "city": "y", "state": "s",
                "postal_code": "1", "country": "US", "linkedin": "l",
                "github": "g", "website": "w",
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


def test_authorized_now_is_required_for_work_auth_readiness(client, db_session):
    from app.services import autofill_profile

    autofill_profile.set_profile(
        {
            "personal": {
                "first_name": "A", "last_name": "B", "email": "a@b.c",
                "phone": "1", "address": "x", "city": "y", "state": "s",
                "postal_code": "1", "country": "US", "linkedin": "l",
                "github": "g", "website": "w",
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

    assert body["groups"]["work_auth"] == {"answered": 3, "answerable": 4}
    assert body["readiness"] == 0.96
    assert body["blocking"] == ["work_auth"]
    assert body["done"] is False


def test_malformed_profile_group_degrades_to_unanswered(client, db_session):
    from app.services import autofill_profile

    autofill_profile.set_profile({"personal": "garbage"}, db_session)

    body = _status(client)["autofill"]
    assert body["groups"]["personal"] == {"answered": 0, "answerable": 12}
