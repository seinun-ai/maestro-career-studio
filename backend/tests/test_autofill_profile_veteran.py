"""Veteran status is one Yes/No question (owner, 2026-10-14): `no`, `yes`, `decline`.

The profile is a JSON text setting, so the old values are mapped when it is READ, not rewritten by a
migration: the settings row, its hand-editable file mirror, a profile sync applies from a peer that has
not updated, and an older Settings page's PUT all land in the same text, and every reader gets the new
words. Nothing is written back until the user saves. `veteran` is a `yes`. `not_veteran` ("not a PROTECTED
veteran") is NOT a `no`: a veteran who is not protected could truthfully have chosen it, so it reads as
unanswered and the profile says so (`stale_answers`), for Settings to ask again (owner, 2026-10-14).
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import autofill_profile, text_settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolated_settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)


def _store(db_session, profile):
    """The text as an older build (or a peer, or a hand edit) left it: written as it is."""
    text_settings.set_text(autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE,
                           json.dumps(profile), db_session)


@pytest.mark.parametrize("stored, read", [
    ("veteran", "yes"), ("decline", "decline"),
    ("no", "no"), ("yes", "yes"),
    ("", ""), ("something else", "something else"),   # a value this does not know is left as it is
])
@pytest.mark.parametrize("read_profile", [autofill_profile.get_profile, autofill_profile.peek_profile])
def test_a_stored_veteran_value_is_read_in_the_new_words(db_session, stored, read, read_profile):
    _store(db_session, {"eeo": {"veteran_status": stored, "gender": "female"}})
    assert read_profile(db_session)["eeo"] == {"veteran_status": read, "gender": "female"}


@pytest.mark.parametrize("profile", [
    {}, {"eeo": None}, {"eeo": "not_veteran"}, {"eeo": ["veteran"]}, {"eeo": {}}, {"eeo": {"veteran_status": None}},
    {"eeo": {"veteran_status": ["veteran"]}}, {"personal": {"veteran_status": "veteran"}},
])
def test_a_profile_without_a_readable_veteran_answer_reads_as_it_was(db_session, profile):
    _store(db_session, profile)
    assert autofill_profile.get_profile(db_session) == profile


@pytest.mark.parametrize("read_profile", [autofill_profile.get_profile, autofill_profile.peek_profile])
def test_the_old_not_a_protected_veteran_answer_reads_as_unanswered_and_says_so(db_session, read_profile):
    _store(db_session, {"eeo": {"veteran_status": "not_veteran", "gender": "female"}})
    got = read_profile(db_session)
    assert got["eeo"] == {"gender": "female"}
    assert got["stale_answers"] == ["eeo.veteran_status"]
    # No other answer is marked stale.
    _store(db_session, {"eeo": {"veteran_status": "veteran"}})
    assert "stale_answers" not in read_profile(db_session)


def test_a_stored_marker_holds_until_the_question_is_answered(db_session):
    _store(db_session, {"eeo": {}, "stale_answers": ["eeo.veteran_status"]})
    assert autofill_profile.get_profile(db_session)["stale_answers"] == ["eeo.veteran_status"]
    # …and an answer retires it: a marker beside an answered question is not believed.
    _store(db_session, {"eeo": {"veteran_status": "no"}, "stale_answers": ["eeo.veteran_status"]})
    assert "stale_answers" not in autofill_profile.get_profile(db_session)
    # Only the one marker means anything.
    _store(db_session, {"eeo": {}, "stale_answers": ["personal.city", 3]})
    assert "stale_answers" not in autofill_profile.get_profile(db_session)


def _stored(tmp_path):
    return json.loads((tmp_path / autofill_profile.AUTOFILL_FILE).read_text())


def test_a_save_without_the_veteran_answer_keeps_the_hint_until_it_is_answered(db_session, tmp_path):
    """The pause row (and any other save) writes the profile back without the dropped answer: the hint
    must outlast it."""
    _store(db_session, {"eeo": {"veteran_status": "not_veteran", "gender": "female"}})
    # What a pause save sends: the profile it just read (marker and all), plus a new custom answer.
    current = client.get("/api/settings/autofill").json()["value"]
    client.put("/api/settings/autofill", json={"value": {**current, "custom": [{"question": "Q?", "answer": "A"}]}})
    assert _stored(tmp_path)["stale_answers"] == ["eeo.veteran_status"]
    assert client.get("/api/settings/autofill").json()["value"]["stale_answers"] == ["eeo.veteran_status"]
    # A save that carries no marker at all (a patch built from another read) does not erase it either.
    client.put("/api/settings/autofill", json={"value": {"eeo": {"gender": "female"}, "personal": {"city": "Springfield"}}})
    assert client.get("/api/settings/autofill").json()["value"]["stale_answers"] == ["eeo.veteran_status"]


@pytest.mark.parametrize("answer", ["no", "yes", "decline"])
def test_only_an_explicit_veteran_answer_clears_the_hint(db_session, tmp_path, answer):
    _store(db_session, {"eeo": {"veteran_status": "not_veteran"}})
    client.put("/api/settings/autofill", json={"value": {"eeo": {"veteran_status": answer},
                                                          "stale_answers": ["eeo.veteran_status"]}})
    assert "stale_answers" not in _stored(tmp_path) and _stored(tmp_path)["eeo"]["veteran_status"] == answer
    assert "stale_answers" not in client.get("/api/settings/autofill").json()["value"]


def test_a_profile_that_never_had_the_old_answer_never_gets_a_marker(db_session, tmp_path):
    client.put("/api/settings/autofill", json={"value": {"eeo": {"gender": "female"}}})
    assert "stale_answers" not in _stored(tmp_path)
    assert "stale_answers" not in client.get("/api/settings/autofill").json()["value"]


def test_the_settings_api_marks_the_old_answer_stale(db_session):
    _store(db_session, {"eeo": {"veteran_status": "not_veteran"}})
    value = client.get("/api/settings/autofill").json()["value"]
    assert value["eeo"] == {} and value["stale_answers"] == ["eeo.veteran_status"]


def test_reading_does_not_rewrite_what_is_stored(db_session, tmp_path):
    """Lazy: the row and the file keep the old value (an old peer reads them too) until a save."""
    _store(db_session, {"eeo": {"veteran_status": "not_veteran"}})
    autofill_profile.get_profile(db_session)
    assert json.loads((tmp_path / autofill_profile.AUTOFILL_FILE).read_text())["eeo"]["veteran_status"] == "not_veteran"
    assert json.loads(text_settings.get_text(autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE,
                                             db_session))["eeo"]["veteran_status"] == "not_veteran"


def test_the_settings_api_serves_the_new_words_whatever_was_stored(db_session):
    _store(db_session, {"eeo": {"veteran_status": "veteran"}})
    assert client.get("/api/settings/autofill").json()["value"]["eeo"]["veteran_status"] == "yes"
    # An older Settings page that still saves the old value: served in the new words on the next read.
    client.put("/api/settings/autofill", json={"value": {"eeo": {"veteran_status": "veteran"}}})
    assert client.get("/api/settings/autofill").json()["value"]["eeo"]["veteran_status"] == "yes"


def test_a_save_in_the_new_words_is_kept_as_it_is(db_session, tmp_path):
    client.put("/api/settings/autofill", json={"value": {"eeo": {"veteran_status": "no"}}})
    assert json.loads((tmp_path / autofill_profile.AUTOFILL_FILE).read_text())["eeo"]["veteran_status"] == "no"


def test_the_profile_asks_one_veteran_question():
    """Profile's control: "Are you a veteran?" with No / Yes / decline, in the values the backend reads."""
    from pathlib import Path

    frontend = Path(__file__).resolve().parents[2] / "frontend"
    source = (frontend / "lib/autofill-options.ts").read_text(encoding="utf-8")
    block = source[source.index('key: "veteran_status"'):source.index('key: "disability_status"')]
    assert 'label: "Are you a veteran?"' in block
    assert ('{ value: "no", label: "No, I am not a veteran" }' in block
            and '{ value: "yes", label: "Yes, I am a veteran" }' in block
            and '{ value: "decline", label: "I don\'t wish to answer" }' in block)
    assert "not_veteran" not in block.split("options:")[1] and "protected veteran" not in block.split("options:")[1]
    # Asked again when the old answer ("not a protected veteran") was dropped.
    assert 'staleHint: "Answer again: this question changed."' in block
    fields = (frontend / "components/profile/field-control.tsx").read_text(encoding="utf-8")
    assert "isBlank(rawValue) && stale.includes(field.key)" in fields
    fold = (frontend / "components/profile/diversity.tsx").read_text(encoding="utf-8")
    assert 'staleAnswers(profile).flatMap((item) => (item.startsWith("eeo.") ? [item.slice(4)] : []))' in fold
    assert "stale={stale}" in fold
