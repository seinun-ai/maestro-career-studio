import json

import pytest

from app.schemas.autofill_choose import ChooseField
from app.services import autofill_choose, autofill_profile, autofill_slots, model_settings
from app.services.llm import LLMProviderError

PROFILE = {
    "personal": {"first_name": "Ada"},
    "education": {"discipline": "Business analytics"},
    "work_auth": {"sponsorship_now": False},
    "preferences": {"how_heard": "Job board"},
    "eeo": {"gender": "Woman"},
}


@pytest.fixture
def jev_on(db_session, monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile(PROFILE, db_session)
    model_settings.set_jev_api_key(db_session, "sk-or-test")
    model_settings.set_autofill_engine(db_session, "jev")


def _fake_jev(monkeypatch, slot_for=None, option_for=None):
    """Fake the MODEL, never the gate (§12). Slot questions are recognised by
    their FREE_TEXT criterion; everything else is an option question."""
    calls = []

    def decide(questions, state, session=None):
        calls.append({"questions": questions, "state": state})
        out = {}
        for qid, q in questions.items():
            if autofill_slots.FREE_TEXT in q["criteria"]:
                choice, p = (slot_for or {}).get(qid, (autofill_slots.NO_SLOT, 0.95))
            else:
                choice, p = (option_for or {}).get(qid, (autofill_choose.NO_OPTION, 0.9))
            out[qid] = {"choice": choice, "probabilities": {choice: p}, "confidence": p}
        return out

    monkeypatch.setattr(autofill_choose.jev, "decide", decide)
    return calls


def _fake_llm(monkeypatch, answers=None):
    prompts = []

    def call_openai(**kwargs):
        prompts.append(kwargs["prompt"])
        return {"choices": {q: {"answer": a} for q, a in (answers or {}).items()}}

    monkeypatch.setattr(autofill_choose.llm, "call_openai", call_openai)
    return prompts


def _field(qid, label, kind="text", options=(), known_value=None):
    return ChooseField(qid=qid, label=label, kind=kind, options=list(options),
                       known_value=known_value)


def test_the_fast_engine_never_calls_jev(db_session, monkeypatch):
    calls = _fake_jev(monkeypatch)
    _fake_llm(monkeypatch)
    autofill_choose.choose([_field("a", "First name")], None, db_session)
    assert calls == []


def test_a_text_field_gets_its_slot_value_without_the_llm(db_session, monkeypatch, jev_on):
    _fake_jev(monkeypatch, slot_for={"a": ("personal.first_name", 0.97)})
    prompts = _fake_llm(monkeypatch)
    out = autofill_choose.choose([_field("a", "Legal first name")], None, db_session)
    assert (out["a"].answer, out["a"].reason) == ("Ada", "matched")
    assert prompts == []


def test_the_slot_question_carries_no_profile_values(db_session, monkeypatch, jev_on):
    calls = _fake_jev(monkeypatch, slot_for={"a": ("personal.first_name", 0.97)})
    _fake_llm(monkeypatch)
    autofill_choose.choose([_field("a", "Legal first name")], None, db_session)
    assert "Ada" not in json.dumps(calls[0])


def test_an_exact_slot_writes_only_a_confident_option(db_session, monkeypatch, jev_on):
    field = _field("s", "Do you need sponsorship?", "select", ["Yes", "No"])
    _fake_jev(monkeypatch, slot_for={"s": ("work_auth.sponsorship_now", 0.95)},
              option_for={"s": ("No", 0.97)})
    _fake_llm(monkeypatch)
    assert autofill_choose.choose([field], None, db_session)["s"].answer == "No"

    _fake_jev(monkeypatch, slot_for={"s": ("work_auth.sponsorship_now", 0.95)},
              option_for={"s": ("No", 0.7)})
    assert autofill_choose.choose([field], None, db_session)["s"].reason == "abstained"


def test_a_flag_slot_writes_a_near_miss_as_closest(db_session, monkeypatch, jev_on):
    field = _field("m", "Major", "select", ["Information Systems", "Marketing"])
    _fake_jev(monkeypatch, slot_for={"m": ("education.discipline", 0.93)},
              option_for={"m": ("Information Systems", 0.6)})
    _fake_llm(monkeypatch)
    out = autofill_choose.choose([field], None, db_session)
    assert (out["m"].answer, out["m"].reason) == ("Information Systems", "closest")


def test_a_flag_slot_below_the_closest_floor_abstains(db_session, monkeypatch, jev_on):
    field = _field("m", "Major", "select", ["Information Systems", "Marketing"])
    _fake_jev(monkeypatch, slot_for={"m": ("education.discipline", 0.93)},
              option_for={"m": ("Marketing", 0.3)})
    _fake_llm(monkeypatch)
    assert autofill_choose.choose([field], None, db_session)["m"].reason == "abstained"


def test_no_suitable_option_abstains(db_session, monkeypatch, jev_on):
    field = _field("h", "How did you hear?", "select", ["LinkedIn", "A friend"])
    _fake_jev(monkeypatch, slot_for={"h": ("preferences.how_heard", 0.9)})
    _fake_llm(monkeypatch)
    assert autofill_choose.choose([field], None, db_session)["h"].reason == "abstained"


def test_free_text_and_unmapped_fields_go_to_the_fast_model(db_session, monkeypatch, jev_on):
    _fake_jev(monkeypatch, slot_for={
        "w": (autofill_slots.FREE_TEXT, 0.9),
        "n": (autofill_slots.NO_SLOT, 0.9),
        "l": ("personal.first_name", 0.4),  # below the slot floor
    })
    prompts = _fake_llm(monkeypatch, answers={"w": "Because", "n": "2 weeks", "l": "Ada"})
    out = autofill_choose.choose(
        [_field("w", "Why us?"), _field("n", "Notice"), _field("l", "Name?")], None, db_session)
    assert len(prompts) == 1
    assert {q: c.answer for q, c in out.items()} == {"w": "Because", "n": "2 weeks", "l": "Ada"}


def test_a_known_value_skips_slot_mapping(db_session, monkeypatch, jev_on):
    field = _field("c", "Country", "combobox", ["United States of America", "Canada"],
                   known_value="United States")
    calls = _fake_jev(monkeypatch, option_for={"c": ("United States of America", 0.96)})
    _fake_llm(monkeypatch)
    out = autofill_choose.choose([field], None, db_session)
    assert out["c"].answer == "United States of America"
    assert len(calls) == 1  # the option call only


def test_eeo_values_never_reach_jev_without_consent(db_session, monkeypatch, jev_on):
    from app.schemas.eeo_consent import EeoConsent
    from app.services import eeo_consent

    eeo_consent.set_consent(EeoConsent(enabled=False, policy_version="1"), db_session)
    field = _field("g", "Gender", "select", ["Woman", "Man"])
    calls = _fake_jev(monkeypatch, slot_for={"g": ("eeo.gender", 0.95)},
                      option_for={"g": ("Woman", 0.99)})
    _fake_llm(monkeypatch)
    out = autofill_choose.choose([field], None, db_session)
    # Without consent `eeo` is not a slot: the slot question cannot offer it,
    # so no option question (the only one carrying a value) is ever asked.
    assert "eeo.gender" not in json.dumps(calls[0]["questions"])
    assert len(calls) == 1
    assert out["g"].answer is None


def test_a_failed_slot_call_sends_the_whole_batch_to_the_fast_model(db_session, monkeypatch, jev_on):
    def down(*a, **k):
        raise LLMProviderError("Jev couldn't answer (error 529).")

    monkeypatch.setattr(autofill_choose.jev, "decide", down)
    prompts = _fake_llm(monkeypatch, answers={"a": "Ada"})
    out = autofill_choose.choose([_field("a", "First name")], None, db_session)
    assert out["a"].answer == "Ada" and len(prompts) == 1


def test_a_failed_option_call_sends_only_option_fields_to_the_fast_model(
        db_session, monkeypatch, jev_on):
    _fake_jev(monkeypatch, slot_for={
        "a": ("personal.first_name", 0.97), "h": ("preferences.how_heard", 0.9)})
    fake_decide = autofill_choose.jev.decide

    def slot_ok_then_down(questions, state, session=None):
        if any(autofill_slots.FREE_TEXT in q["criteria"] for q in questions.values()):
            return fake_decide(questions, state, session)
        raise LLMProviderError("Jev couldn't answer (error 529).")

    monkeypatch.setattr(autofill_choose.jev, "decide", slot_ok_then_down)
    prompts = _fake_llm(monkeypatch, answers={"h": "LinkedIn"})
    out = autofill_choose.choose(
        [_field("a", "First name"),
         _field("h", "How did you hear?", "select", ["LinkedIn", "A friend"])],
        None, db_session)
    assert out["a"].answer == "Ada" and out["h"].answer == "LinkedIn"
    assert '"h"' in prompts[0] and '"a"' not in prompts[0]
