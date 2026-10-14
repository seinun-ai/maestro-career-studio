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


def test_a_self_description_reaches_the_model_only_with_consent(db_session, monkeypatch, settings_here):
    """The /choose prompt reads the same gate as GET /context, and the user's
    own words for a self-described gender are inside `eeo` like every answer."""
    from app.services import autofill_profile

    for enabled in (False, True):
        _set_consent(db_session, enabled)
        autofill_profile.set_profile(
            {"personal": {"first_name": "Ada"},
             "eeo": {"gender": "self_describe", "gender_self_describe": "Genderfluid"}},
            db_session)
        sent: list[str] = []
        monkeypatch.setattr(autofill_choose.llm, "call_openai",
                            lambda **kw: sent.append(kw["prompt"]) or {"choices": {}})
        autofill_choose.choose(_fields(), application_id=None, session=db_session)
        assert ("Genderfluid" in sent[0]) is enabled


def test_a_consent_that_cannot_be_read_withholds_them(db_session, monkeypatch, settings_here):
    """Fails CLOSED, as GET /context does: a consent record that could not be
    computed is not consent."""
    from app.services import eeo_consent

    _set_consent(db_session, True)
    monkeypatch.setattr(eeo_consent, "get_consent",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    prompt = _prompt_sent(db_session, monkeypatch)
    assert _eeo_values_in(prompt) == []


# ---------- J3: a required written question the chooser left null is drafted

from datetime import UTC, datetime  # noqa: E402

from app.models.application import Application  # noqa: E402
from app.models.job import Job  # noqa: E402

IMPRESSIVE = "What's the most impressive project you've worked on? Why?"


def _application(db_session):
    job = Job(raw_text="Need analytics", raw_text_hash="draft-hash", title="Data Analyst", company="Acme",
              extracted_json={"title": "Data Analyst", "company": "Acme"}, extracted_at=datetime.now(UTC))
    db_session.add(job)
    db_session.flush()
    application = Application(
        job_id=job.id, base_resume="data_analyst", status="draft",
        customized_json={"summary": "Analyst", "contact": {"name": "Jane Doe", "email": "jane@example.test"},
                         "experience": [{"company": "Globex", "title": "Analyst",
                                         "bullets": ["Built a forecasting pipeline for 40 stores"]}]})
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


def _written(qid="w", label=IMPRESSIVE, **kw):
    return ChooseField(qid=qid, label=label, kind=kw.pop("kind", "textarea"), required=kw.pop("required", True), **kw)


class Writer:
    """The fake model: /choose says null for everything; the essay writer answers `drafts`."""

    def __init__(self, monkeypatch, drafts):
        self.prompts = []
        self.drafts = drafts

        def call_openai(**kw):
            if kw["trace_name"] == "autofill-draft":
                self.prompts.append(kw["prompt"])
                return {"answers": self.drafts}
            return {"choices": {}}

        monkeypatch.setattr(autofill_choose.llm, "call_openai", call_openai)


def test_a_required_written_question_with_no_answer_is_drafted_and_assumed(db_session, monkeypatch):
    application = _application(db_session)
    writer = Writer(monkeypatch, {"w": "Built a forecasting pipeline for 40 stores. It cut stockouts by a third."})
    out = autofill_choose.choose([_written()], application.id, db_session)
    assert out["w"].reason == "assumed"
    assert out["w"].answer == "Built a forecasting pipeline for 40 stores. It cut stockouts by a third."
    assert out["w"].note == "Drafted from your history: read it"
    [prompt] = writer.prompts
    assert IMPRESSIVE in prompt and "Globex" in prompt and "Data Analyst" in prompt   # history and job
    assert "implied first person" in prompt and "120 words" in prompt


def test_a_draft_is_never_saved_as_an_answer(db_session, monkeypatch):
    application = _application(db_session)
    Writer(monkeypatch, {"w": "Built a forecasting pipeline."})
    before = db_session.query(QAEntry).count()
    autofill_choose.choose([_written()], application.id, db_session)
    assert db_session.query(QAEntry).count() == before


def test_a_matched_answer_is_not_redrafted(db_session, monkeypatch):
    application = _application(db_session)
    writer = Writer(monkeypatch, {"w": "never used"})
    monkeypatch.setattr(autofill_choose.llm, "call_openai", lambda **kw: (
        writer.prompts.append(kw["trace_name"]) or {"choices": {"w": {"answer": "From the profile", "reason": "matched"}}}))
    out = autofill_choose.choose([_written()], application.id, db_session)
    assert (out["w"].answer, out["w"].reason) == ("From the profile", "matched")
    assert writer.prompts == ["autofill-choose"]


@pytest.mark.parametrize("field", [
    _written(required=False),                               # optional: the user's to write
    _written(kind="select", options=["A", "B"]),            # a choice is never an essay
    _written(label="City"),                                 # not a written question
    _written(label="Phone Extension"),
])
def test_only_a_required_written_question_is_drafted(db_session, monkeypatch, field):
    application = _application(db_session)
    writer = Writer(monkeypatch, {"w": "Should not be used."})
    out = autofill_choose.choose([field], application.id, db_session)
    assert (out["w"].answer, out["w"].reason) == (None, "abstained")
    assert writer.prompts == []


@pytest.mark.parametrize("label", [
    "Do you identify as a person with a disability? Please explain.",
    "What is your gender identity and how do you describe your race or ethnicity?",
    "Are you a protected veteran? Please describe your service.",
    "Will you now or in the future require visa sponsorship? Explain your work authorization.",
    "What are your salary expectations and desired compensation? Explain.",
    "Describe any felony convictions or criminal history.",
    "Do you hold an active security clearance? Describe it.",
    "Please type your full name as your electronic signature to certify this application is true.",
    "Have you previously been employed by this company? Describe the role.",
])
def test_a_protected_or_never_list_question_is_never_drafted(db_session, monkeypatch, label):
    application = _application(db_session)
    writer = Writer(monkeypatch, {"w": "Should not be used."})
    out = autofill_choose.choose([_written(label=label)], application.id, db_session)
    assert (out["w"].answer, out["w"].reason) == (None, "abstained")
    assert writer.prompts == [], label


def test_with_no_application_there_is_nothing_to_draft_from(db_session, monkeypatch):
    writer = Writer(monkeypatch, {"w": "Should not be used."})
    out = autofill_choose.choose([_written()], None, db_session)
    assert (out["w"].answer, out["w"].reason) == (None, "abstained")
    assert writer.prompts == []


def test_a_failed_draft_leaves_the_field_open_and_does_not_fail_the_batch(db_session, monkeypatch):
    application = _application(db_session)

    def call_openai(**kw):
        if kw["trace_name"] == "autofill-draft":
            raise autofill_choose.llm.LLMProviderError("down", "down")
        return {"choices": {"w": {"answer": None, "reason": "abstained"}, "c": {"answer": "x", "reason": "matched"}}}

    monkeypatch.setattr(autofill_choose.llm, "call_openai", call_openai)
    out = autofill_choose.choose([_written(), _written("c", "Nickname", kind="text", required=False)],
                                 application.id, db_session)
    assert (out["w"].answer, out["w"].reason) == (None, "abstained")
    assert out["c"].answer == "x"


@pytest.mark.parametrize(("draft", "expected"), [
    ("He built a forecasting pipeline for 40 stores.", "Built a forecasting pipeline for 40 stores."),
    ("I built a forecasting pipeline for 40 stores.", "Built a forecasting pipeline for 40 stores."),
    ("Jane Doe built a forecasting pipeline for 40 stores.", "Built a forecasting pipeline for 40 stores."),
])
def test_a_draft_follows_the_voice_rule_in_code_not_just_in_the_prompt(db_session, monkeypatch, draft, expected):
    application = _application(db_session)
    Writer(monkeypatch, {"w": draft})
    out = autofill_choose.choose([_written()], application.id, db_session)
    assert (out["w"].answer, out["w"].reason) == (expected, "assumed")


def test_a_draft_that_cannot_be_put_in_the_owners_voice_is_dropped(db_session, monkeypatch):
    application = _application(db_session)
    Writer(monkeypatch, {"w": "He is."})
    out = autofill_choose.choose([_written()], application.id, db_session)
    assert (out["w"].answer, out["w"].reason) == (None, "abstained")


def test_a_draft_is_kept_near_120_words_unless_the_field_says_otherwise(db_session, monkeypatch):
    application = _application(db_session)
    sentence = "Built a forecasting pipeline for forty stores that cut stockouts by a third. "
    long = sentence * 20                      # 14 words x 20 = 280
    Writer(monkeypatch, {"a": long, "b": long})
    out = autofill_choose.choose(
        [_written("a"), _written("b", "In 250 words, what is the most impressive project you've worked on?")],
        application.id, db_session)
    assert 60 <= len(out["a"].answer.split()) <= 150 and out["a"].answer.endswith(".")
    assert 200 <= len(out["b"].answer.split()) <= 250


def test_drafts_are_asked_in_one_call_and_matched_by_qid(db_session, monkeypatch):
    application = _application(db_session)
    writer = Writer(monkeypatch, {"a": "Built the first thing.", "b": "Built the second thing.",
                                  "not-asked": "Invented."})
    out = autofill_choose.choose([_written("a"), _written("b", "Describe the most interesting technology you used.")],
                                 application.id, db_session)
    assert len(writer.prompts) == 1
    assert (out["a"].answer, out["b"].answer) == ("Built the first thing.", "Built the second thing.")
    assert "not-asked" not in out


@pytest.mark.parametrize("label", [
    "What's the most impressive project you've worked on? Why?",
    "Describe a bug you traced to its root cause.",
    "What is the most interesting technology you have used, relative to your peers?",
    "Tell us about a time you embraced a hard change at work.",
    "Why do you want to work at Acme?",
])
def test_ordinary_written_questions_are_drafted(db_session, monkeypatch, label):
    application = _application(db_session)
    Writer(monkeypatch, {"w": "Built a forecasting pipeline for 40 stores."})
    out = autofill_choose.choose([_written(label=label)], application.id, db_session)
    assert out["w"].reason == "assumed", label
