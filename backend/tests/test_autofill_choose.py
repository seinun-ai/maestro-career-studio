from unittest.mock import patch

import pytest

from app.models.qa_entry import QAEntry
from app.schemas.autofill_choose import ChooseField
from app.services import autofill_choose, model_settings


def _fields() -> list[ChooseField]:
    return [
        ChooseField(
            qid="a-0",
            label="Notice period",
            kind="text",
            options=[],
            known_value=None,
        )
    ]


def test_it_runs_on_the_fast_model_not_the_smart_one(db_session):
    """The premise of this pass: cheap picks. Reaching for the smart model here
    would make a second click cost what a tailoring run costs."""
    with patch.object(
        autofill_choose.llm, "call_openai", return_value={"choices": {}}
    ) as call:
        autofill_choose.choose(_fields(), application_id=None, session=db_session)
    assert call.call_args.kwargs["model"] == model_settings.get_fast_model(db_session)
    assert call.call_args.kwargs["response_format"] == "json"


def test_an_answer_outside_the_offered_options_becomes_an_abstention(db_session):
    """The model returned a plausible string that is not on the page. Writing it
    would put a value in a select that has no such option — or worse, snap to a
    fuzzy neighbour, since the extension's optionMatches() does containment
    matching. Refuse it here, once, rather than in three writers."""
    reply = {"choices": {"a-0": {"answer": "Two weeks", "reason": "matched"}}}
    with patch.object(autofill_choose.llm, "call_openai", return_value=reply):
        out = autofill_choose.choose(
            [
                ChooseField(
                    qid="a-0",
                    label="Notice",
                    kind="select",
                    options=["Immediate", "30 days"],
                )
            ],
            application_id=None,
            session=db_session,
        )
    assert out["a-0"].answer is None and out["a-0"].reason == "abstained"


def test_a_qid_the_model_invented_is_dropped(db_session):
    reply = {"choices": {"not-a-qid": {"answer": "x", "reason": "matched"}}}
    with patch.object(autofill_choose.llm, "call_openai", return_value=reply):
        assert "not-a-qid" not in autofill_choose.choose(
            _fields(), application_id=None, session=db_session
        )


def test_a_qid_the_model_skipped_comes_back_as_an_abstention(db_session):
    """Every field asked about gets an entry. A missing key is the model
    forgetting, and the caller must not have to tell that apart from a
    deliberate null."""
    with patch.object(
        autofill_choose.llm, "call_openai", return_value={"choices": {}}
    ):
        out = autofill_choose.choose(_fields(), application_id=None, session=db_session)
    assert out["a-0"].answer is None and out["a-0"].reason == "abstained"


def test_it_writes_no_qa_entry(db_session):
    """A ticked checkbox is not transcript material. The Q&A history is for real
    questions the user may want to re-read and edit."""
    before = db_session.query(QAEntry).count()
    with patch.object(
        autofill_choose.llm, "call_openai", return_value={"choices": {}}
    ):
        autofill_choose.choose(_fields(), application_id=None, session=db_session)
    assert db_session.query(QAEntry).count() == before


# ---------- the standing EEO consent gates what the model sees ----------
#
# inv-eeo-standing-consent: protected-class answers leave the server only under
# standing consent, and "leave" includes the prompt this pass sends to a model
# provider, not only the GET /context reply. The model is faked at
# `llm.call_openai` (SYSTEM.md §12: fake the model, never the gate), so what is
# asserted is the prompt text that would have left the machine.

_EEO = {
    "gender": "Woman",
    "race_ethnicity": "Native Hawaiian or Other Pacific Islander",
    "veteran_status": "Protected veteran",
    "disability_status": "Yes, I have a disability",
}


@pytest.fixture
def settings_here(monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "settings_dir", tmp_path)


def _prompt_sent(db_session, monkeypatch) -> str:
    from app.services import autofill_profile

    autofill_profile.set_profile(
        {"personal": {"first_name": "Ada"}, "eeo": dict(_EEO)}, db_session)
    sent: list[str] = []

    def fake_model(**kwargs):
        sent.append(kwargs["prompt"])
        return {"choices": {}}

    monkeypatch.setattr(autofill_choose.llm, "call_openai", fake_model)
    autofill_choose.choose(_fields(), application_id=None, session=db_session)
    [prompt] = sent
    return prompt


def _eeo_values_in(prompt: str) -> list[str]:
    return [value for value in _EEO.values() if value in prompt]


def _set_consent(db_session, enabled: bool) -> None:
    from app.schemas.eeo_consent import EeoConsent
    from app.services import eeo_consent

    eeo_consent.set_consent(EeoConsent(enabled=enabled, policy_version="1"), db_session)


def test_without_consent_no_diversity_answer_reaches_the_model(db_session, monkeypatch, settings_here):
    _set_consent(db_session, False)
    prompt = _prompt_sent(db_session, monkeypatch)
    assert _eeo_values_in(prompt) == []
    assert '"eeo"' not in prompt
    # The rest of the profile still grounds the answer.
    assert "Ada" in prompt


def test_with_consent_the_diversity_answers_are_offered(db_session, monkeypatch, settings_here):
    _set_consent(db_session, True)
    prompt = _prompt_sent(db_session, monkeypatch)
    assert _eeo_values_in(prompt) == list(_EEO.values())


def test_a_consent_that_cannot_be_read_withholds_them(db_session, monkeypatch, settings_here):
    """Fails CLOSED, as GET /context does: a consent record that could not be
    computed is not consent."""
    from app.services import eeo_consent

    _set_consent(db_session, True)
    monkeypatch.setattr(eeo_consent, "get_consent",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    prompt = _prompt_sent(db_session, monkeypatch)
    assert _eeo_values_in(prompt) == []
