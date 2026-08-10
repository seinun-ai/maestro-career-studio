"""The typed `work_auth` reader over the intentionally-loose autofill profile.

The two-part US sponsorship question ("authorized now?" / "sponsorship now or
in the future?") is the highest-consequence field in the profile: a wrong
answer fails an application silently and is not recoverable. These tests pin
the one rule that keeps that from happening — an answer the stored profile does
not actually contain reads back as `None` ("ask the user"), never as a guess.
"""

import pytest

from app.services import autofill_profile, text_settings
from app.services.autofill_profile import get_work_auth, set_profile


@pytest.fixture(autouse=True)
def _isolated_settings_dir(tmp_path, monkeypatch):
    # set_profile mirrors to settings/autofill.json; without this the suite
    # would overwrite the developer's real profile.
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)


def test_legacy_two_boolean_profile_migrates(db_session):
    """An OPT holder answers YES to both questions. The old shape cannot say that.

    Legacy rows must keep working: the extension updates out-of-band, so a
    backend that only understood the new shape would break every installed panel.
    """
    set_profile({"work_auth": {"authorized_to_work": True, "requires_sponsorship": True}}, db_session)
    wa = get_work_auth(db_session)
    assert wa.authorized_now is True
    assert wa.sponsorship_future is True
    # The legacy shape says nothing about NOW, so we must not invent an answer.
    assert wa.sponsorship_now is None


def test_new_shape_round_trips(db_session):
    set_profile({"work_auth": {
        "status": "opt", "sponsorship_now": False, "sponsorship_future": True,
        "authorization_expires_on": "2027-05-30",
    }}, db_session)
    wa = get_work_auth(db_session)
    assert wa.status == "opt"
    assert wa.sponsorship_now is False
    assert wa.sponsorship_future is True


def test_legacy_yes_no_strings_migrate_like_booleans(db_session):
    """Profiles saved by the pre-migration Settings page hold "yes"/"no".

    The current editor writes typed booleans, but these older profiles remain on
    disk until the user edits one. The reader must preserve their known answers
    during that window.
    """
    set_profile(
        {"work_auth": {"authorized_to_work": "yes", "requires_sponsorship": "no"}},
        db_session,
    )
    wa = get_work_auth(db_session)
    assert wa.authorized_now is True
    assert wa.sponsorship_future is False
    assert wa.sponsorship_now is None


def test_new_shape_is_recognized_by_any_of_its_keys(db_session):
    """A profile carrying only `sponsorship_now` must not be read as legacy.

    Legacy detection is "no new-shape key present". Keying it on `status` or
    `sponsorship_future` alone would send this profile down the legacy branch,
    which reads neither key — silently discarding a knockout answer the user
    did supply.
    """
    set_profile({"work_auth": {"sponsorship_now": True}}, db_session)
    assert get_work_auth(db_session).sponsorship_now is True

    set_profile({"work_auth": {"authorized_now": False}}, db_session)
    assert get_work_auth(db_session).authorized_now is False


def test_new_shape_wins_when_both_shapes_are_present(db_session):
    """Mid-migration a profile holds both. The typed answer is the current one."""
    set_profile(
        {"work_auth": {
            "authorized_to_work": "no",
            "requires_sponsorship": "no",
            "sponsorship_now": False,
            "sponsorship_future": True,
        }},
        db_session,
    )
    wa = get_work_auth(db_session)
    assert wa.sponsorship_future is True
    assert wa.sponsorship_now is False
    # The legacy keys are not re-read into the typed fields.
    assert wa.authorized_now is None


def test_uninterpretable_values_stay_unknown_instead_of_raising(db_session):
    """settings/autofill.json is hand-editable and the PUT body is untyped.

    Today the new shape can ONLY be produced by hand-editing that file, so a
    near-miss like "OPT" for `status` is the likely input, not an exotic one.
    Raising would take down every caller; keeping the sibling answers and
    reporting the bad one as unknown loses only what was actually unusable.
    """
    set_profile(
        {"work_auth": {
            "status": "OPT",  # not in the vocabulary (it is lowercase)
            "authorization_expires_on": 2027,  # not a string
            "sponsorship_now": False,
            "sponsorship_future": True,
        }},
        db_session,
    )
    wa = get_work_auth(db_session)
    assert wa.status is None
    assert wa.authorization_expires_on is None
    assert wa.sponsorship_now is False
    assert wa.sponsorship_future is True


def test_legacy_blank_answer_stays_unknown(db_session):
    """An empty select is no answer at all, and must not read as False."""
    set_profile(
        {"work_auth": {"authorized_to_work": "", "requires_sponsorship": "yes"}},
        db_session,
    )
    wa = get_work_auth(db_session)
    assert wa.authorized_now is None
    assert wa.sponsorship_future is True


def test_absent_or_malformed_work_auth_reads_as_all_unknown(db_session):
    for profile in ({}, {"work_auth": None}, {"work_auth": "F-1 OPT"}, {"work_auth": []}):
        set_profile(profile, db_session)
        wa = get_work_auth(db_session)
        assert wa.status is None
        assert wa.authorized_now is None
        assert wa.sponsorship_now is None
        assert wa.sponsorship_future is None
        assert wa.authorization_expires_on is None
        assert wa.countries_authorized == []


def test_each_read_returns_its_own_object(db_session):
    """No shared empty-answer singleton: `WorkAuth` is mutable.

    The empty path is the tempting one to hoist into a module constant, and a
    caller appending to `countries_authorized` would then poison every later
    read of a knockout field.
    """
    set_profile({}, db_session)
    first = get_work_auth(db_session)
    first.countries_authorized.append("US")
    first.sponsorship_future = True
    second = get_work_auth(db_session)
    assert second.countries_authorized == []
    assert second.sponsorship_future is None


def test_get_work_auth_opens_its_own_session_when_given_none(db_session, monkeypatch):
    """The service's session argument is optional everywhere else in this module."""
    monkeypatch.setattr(
        autofill_profile, "get_profile", lambda session=None: {"work_auth": {"status": "h1b"}}
    )
    assert get_work_auth().status == "h1b"


def test_canonical_identity_from_profile_maps_personal_keys():
    from app.services.autofill_profile import canonical_identity_from_profile

    assert canonical_identity_from_profile(
        {
            "personal": {
                "first_name": " Sample ",
                "last_name": "Applicant",
                "preferred_name": "Sam",
            }
        }
    ) == {
        "legal_first": "Sample",
        "legal_last": "Applicant",
        "preferred": "Sam",
    }


def test_canonical_identity_from_profile_missing_preferred_and_empty_personal():
    from app.services.autofill_profile import canonical_identity_from_profile

    assert canonical_identity_from_profile(
        {"personal": {"first_name": "A", "last_name": "B"}}
    ) == {"legal_first": "A", "legal_last": "B", "preferred": None}
    assert canonical_identity_from_profile({}) == {
        "legal_first": None,
        "legal_last": None,
        "preferred": None,
    }
    assert canonical_identity_from_profile(None) == {
        "legal_first": None,
        "legal_last": None,
        "preferred": None,
    }
