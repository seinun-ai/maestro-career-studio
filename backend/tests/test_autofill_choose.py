from unittest.mock import patch

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
