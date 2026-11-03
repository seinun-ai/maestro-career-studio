"""Notice is one answer in days (docs/plans/2026-11-02-start-and-pay.md, Task 6; Decisions 1, 9 and 10).

`preferences.notice_days` holds whole days. Text under `notice_period`, from when notice was free text, is read as days
when it says them ("2 weeks" is 14), on read and on the next save of any kind, with no startup step; text that says no
days ("negotiable") stays the legacy answer until days are given. A form that asks in words gets the days in words
(`autofill_catalog.with_fill_rules`). A save that sends new text (an older Companion learning "1 month", an agent's
PATCH) is read as days, compared with the stored text, never with the read view, which has already turned it into days.
"""

import json
from datetime import date

import pytest

from app.services import autofill_country, autofill_profile, text_settings

TODAY = date(2026, 11, 3)


@pytest.fixture(autouse=True)
def _isolated_settings_dir(tmp_path, monkeypatch):
    # set_profile mirrors to settings/autofill.json; without this the suite would overwrite the
    # developer's real profile.
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)


def _write(db_session, profile: dict) -> None:
    """The stored text as an older writer left it: no save's rule applied."""
    text_settings.set_text(autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE,
                           json.dumps(profile), db_session)


def _stored(tmp_path) -> dict:
    return json.loads((tmp_path / autofill_profile.AUTOFILL_FILE).read_text())


def _filled(db_session) -> dict:
    """The preferences a form gets: the one fill view (`for_market`) of the read view."""
    view = autofill_profile.get_profile(db_session)
    return autofill_country.for_market(view, None, chosen_home=None, today=TODAY)["preferences"]


# --- save ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("sent", ["14", " 14 ", 14])
def test_a_profile_save_of_days_stores_a_number_and_fills_words(db_session, tmp_path, sent):
    """Profile's number box sends text (Decision 9): the days are stored as a number, and a form that
    asks in words gets them in words."""
    saved = autofill_profile.set_profile({"preferences": {"notice_days": sent}}, db_session)
    assert _stored(tmp_path) == {"preferences": {"notice_days": 14}}
    assert saved["preferences"] == {"notice_days": 14}
    assert _filled(db_session) == {"notice_days": 14, "notice_period": "2 weeks"}


def test_a_save_with_days_stores_no_text(db_session, tmp_path):
    """Days given, the text is not stored: neither the legacy answer echoed back from the read view nor
    text that says no days."""
    _write(db_session, {"preferences": {"notice_period": "negotiable"}})
    view = autofill_profile.get_profile(db_session)
    assert view["preferences"] == {"notice_period": "negotiable"}
    autofill_profile.set_profile({"preferences": {**view["preferences"], "notice_days": 14}}, db_session)
    assert _stored(tmp_path) == {"preferences": {"notice_days": 14}}
    autofill_profile.set_profile({"preferences": {"notice_days": 14, "notice_period": "whenever"}}, db_session)
    assert _stored(tmp_path) == {"preferences": {"notice_days": 14}}
    assert _filled(db_session) == {"notice_days": 14, "notice_period": "2 weeks"}


def test_text_that_says_no_days_is_stored_only_while_days_are_blank(db_session, tmp_path):
    autofill_profile.set_profile({"preferences": {"notice_period": "negotiable"}}, db_session)
    assert _stored(tmp_path) == {"preferences": {"notice_period": "negotiable"}}
    autofill_profile.set_profile({"preferences": {"notice_days": "", "notice_period": "negotiable"}}, db_session)
    assert _stored(tmp_path)["preferences"]["notice_period"] == "negotiable"


@pytest.mark.parametrize("stored", [{"notice_days": 14}, {"notice_period": "2 weeks"}])
def test_new_text_over_stored_days_is_read_as_days(db_session, tmp_path, stored):
    """An older Companion learning notice in words sends the read view (days and all) with its new text:
    the text differs from the stored one, so it is the new answer, read as days."""
    _write(db_session, {"preferences": stored})
    view = autofill_profile.get_profile(db_session)
    assert view["preferences"] == {"notice_days": 14}
    autofill_profile.set_profile(
        {**view, "preferences": {**view["preferences"], "notice_period": "1 month"}}, db_session)
    assert _stored(tmp_path) == {"preferences": {"notice_days": 30}}
    assert _filled(db_session) == {"notice_days": 30, "notice_period": "1 month"}


def test_unchanged_stored_text_beside_new_days_leaves_the_days(db_session, tmp_path):
    """The stored text sent back with new days is no new answer: the days stand."""
    _write(db_session, {"preferences": {"notice_period": "2 weeks"}})
    autofill_profile.set_profile({"preferences": {"notice_days": "30", "notice_period": "2 weeks"}}, db_session)
    assert _stored(tmp_path) == {"preferences": {"notice_days": 30}}


@pytest.mark.parametrize("days", [60, "60"])
def test_new_days_and_new_text_in_one_save_keep_the_days(db_session, tmp_path, days):
    """Days given win: a save that changes the days and sends text too stores the days, whatever the text."""
    autofill_profile.set_profile({"preferences": {"notice_days": 14}}, db_session)
    autofill_profile.set_profile({"preferences": {"notice_days": days, "notice_period": "2 weeks"}}, db_session)
    assert _stored(tmp_path) == {"preferences": {"notice_days": 60}}
    autofill_profile.patch_profile({"preferences": {"notice_days": 90, "notice_period": "1 month"}}, db_session)
    assert _stored(tmp_path) == {"preferences": {"notice_days": 90}}


# Days that say no days: no answer, so storage, the view, the fill and readiness agree and nothing is guessed.
_NOT_DAYS = [14.5, "14.5", -1, "-1", "1e1", "soon", True, False, [], {}, [14]]


@pytest.mark.parametrize("given", _NOT_DAYS)
def test_days_that_say_no_days_are_no_answer(db_session, client, tmp_path, given):
    _write(db_session, {"preferences": {"notice_days": given, "how_heard": "A friend"}})
    view = autofill_profile.get_profile(db_session)
    assert view["preferences"] == {"how_heard": "A friend"}
    assert _filled(db_session) == {"how_heard": "A friend"}
    counted = _start_and_pay(client)
    _write(db_session, {"preferences": {"how_heard": "A friend"}})
    assert _start_and_pay(client) == counted
    autofill_profile.set_profile({"preferences": {"notice_days": given, "how_heard": "A friend"}}, db_session)
    assert _stored(tmp_path) == {"preferences": {"how_heard": "A friend"}}


@pytest.mark.parametrize("given", _NOT_DAYS)
def test_legacy_text_survives_days_that_say_no_days(db_session, tmp_path, given):
    """The legacy text answers until days are given, and a value that says no days is none."""
    _write(db_session, {"preferences": {"notice_days": given, "notice_period": "2 weeks"}})
    assert autofill_profile.get_profile(db_session)["preferences"] == {"notice_days": 14}
    _write(db_session, {"preferences": {"notice_days": given, "notice_period": "negotiable"}})
    assert autofill_profile.get_profile(db_session)["preferences"] == {"notice_period": "negotiable"}
    assert _filled(db_session) == {"notice_period": "negotiable"}
    autofill_profile.set_profile({"preferences": {"notice_days": given, "notice_period": "negotiable"}}, db_session)
    assert _stored(tmp_path) == {"preferences": {"notice_period": "negotiable"}}


@pytest.mark.parametrize("given, days, words", [
    (14.0, 14, "2 weeks"), ("2 weeks", 14, "2 weeks"), (" 3 months ", 90, "3 months"), ("now", 0, "Immediately"),
])
def test_days_written_another_way_are_read_as_days(db_session, tmp_path, given, days, words):
    """A whole float (a hand edit) is its number, and text that says days ("2 weeks", an agent's or a
    hand edit's) is read as notice text is."""
    _write(db_session, {"preferences": {"notice_days": given, "notice_period": "negotiable"}})
    assert autofill_profile.get_profile(db_session)["preferences"] == {"notice_days": days}
    assert _filled(db_session) == {"notice_days": days, "notice_period": words}
    autofill_profile.set_profile({"preferences": {"notice_days": given}}, db_session)
    assert _stored(tmp_path) == {"preferences": {"notice_days": days}}


@pytest.mark.parametrize("stored", [
    {"notice_days": 14},
    {"notice_days": 0, "earliest_start_date": "2026-12-01"},
    {"notice_period": "negotiable"},
    {"notice_period": "2 weeks"},
    {"notice_period": "now", "notice_days": ""},
])
def test_an_echo_of_the_read_view_changes_nothing(db_session, tmp_path, stored):
    _write(db_session, {"preferences": stored})
    before = autofill_profile.get_profile(db_session)
    saved = autofill_profile.set_profile(before, db_session)
    assert saved == before
    assert autofill_profile.get_profile(db_session) == before
    assert _stored(tmp_path) == before  # and it lands in storage as read


def test_an_agents_patch_of_notice_in_words_stores_days(db_session, tmp_path):
    autofill_profile.set_profile({"preferences": {"notice_days": 0, "how_heard": "A friend"}}, db_session)
    saved = autofill_profile.patch_profile({"preferences": {"notice_period": "2 weeks"}}, db_session)
    assert _stored(tmp_path) == {"preferences": {"notice_days": 14, "how_heard": "A friend"}}
    assert saved["preferences"] == {"notice_days": 14, "how_heard": "A friend"}


def test_an_agents_patch_of_days_drops_the_legacy_text(db_session, tmp_path):
    _write(db_session, {"preferences": {"notice_period": "negotiable"}})
    autofill_profile.patch_profile({"preferences": {"notice_days": 60}}, db_session)
    assert _stored(tmp_path) == {"preferences": {"notice_days": 60}}


# --- read ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,days,words", [
    ("0", 0, "Immediately"), ("Immediately", 0, "Immediately"), (" now ", 0, "Immediately"),
    ("2 weeks", 14, "2 weeks"), ("1 month", 30, "1 month"), ("45 days", 45, "45 days"),
])
def test_stored_notice_in_words_reads_as_days(db_session, text, days, words):
    _write(db_session, {"preferences": {"notice_period": text}})
    assert autofill_profile.get_profile(db_session)["preferences"] == {"notice_days": days}
    assert autofill_profile.peek_profile(db_session)["preferences"] == {"notice_days": days}
    assert _filled(db_session) == {"notice_days": days, "notice_period": words}


def test_stored_days_as_text_read_as_a_number(db_session):
    _write(db_session, {"preferences": {"notice_days": "21"}})
    assert autofill_profile.get_profile(db_session)["preferences"] == {"notice_days": 21}


def test_stored_days_win_over_stored_text(db_session):
    _write(db_session, {"preferences": {"notice_days": 30, "notice_period": "2 weeks"}})
    assert autofill_profile.get_profile(db_session)["preferences"] == {"notice_days": 30}
    assert _filled(db_session) == {"notice_days": 30, "notice_period": "1 month"}


def _start_and_pay(client) -> dict:
    """Readiness's count of Start and pay's required answers."""
    return client.get("/api/setup/status").json()["autofill"]["groups"]["preferences"]


@pytest.mark.parametrize("text", ["negotiable", "2", "two weeks"])
def test_text_that_says_no_days_stays_the_legacy_answer(db_session, client, text):
    """A bare "2" has no unit and "negotiable" no number: never guessed. Forms get it as written, and
    readiness still counts notice as answered, so no one's count drops."""
    _write(db_session, {"preferences": {"notice_period": text}})
    assert autofill_profile.get_profile(db_session)["preferences"] == {"notice_period": text}
    assert _filled(db_session) == {"notice_period": text}
    legacy = _start_and_pay(client)
    _write(db_session, {"preferences": {"notice_days": 14}})
    assert legacy == _start_and_pay(client)
    _write(db_session, {"preferences": {}})
    assert _start_and_pay(client)["answered"] == legacy["answered"] - 1
