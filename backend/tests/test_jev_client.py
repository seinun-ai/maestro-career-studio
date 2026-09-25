import json

import httpx
import pytest
import respx

from app.config import settings
from app.services import jev, model_settings
from app.services.llm import LLMProviderError

URL = "https://openrouter.ai/api/v1/systemone"
QUESTIONS = {"q1": jev.choice_question("Which?", {"a": "A", "b": "B"})}
ANSWER = {"q1": {"choice": "a", "probabilities": {"a": 0.9, "b": 0.1}, "confidence": 0.8}}


@pytest.fixture(autouse=True)
def _keyed(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "logs_dir", tmp_path)
    monkeypatch.setattr(jev, "_BACKOFF_S", 0)
    model_settings.set_jev_api_key(db_session, "sk-or-test")


@respx.mock
def test_it_posts_model_state_and_questions_with_the_bearer_key(db_session):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={"answers": ANSWER}))
    assert jev.decide(QUESTIONS, {"x": 1}, db_session) == ANSWER
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer sk-or-test"
    assert json.loads(sent.content) == {
        "model": "typesafe/jev-1.13", "state": {"x": 1}, "questions": QUESTIONS}


def test_no_key_is_a_provider_error_and_no_request(db_session):
    model_settings.set_jev_api_key(db_session, None)
    with pytest.raises(LLMProviderError, match="Jev"):
        jev.decide(QUESTIONS, "s", db_session)


@respx.mock
def test_a_refused_key_says_so(db_session):
    respx.post(URL).mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(LLMProviderError, match="refused"):
        jev.decide(QUESTIONS, "s", db_session)


@respx.mock
def test_a_rate_limit_is_retried_once(db_session):
    route = respx.post(URL).mock(side_effect=[
        httpx.Response(429), httpx.Response(200, json={"answers": ANSWER})])
    assert jev.decide(QUESTIONS, "s", db_session) == ANSWER
    assert route.call_count == 2


@respx.mock
def test_a_second_overload_gives_up(db_session):
    respx.post(URL).mock(side_effect=[httpx.Response(529), httpx.Response(529)])
    with pytest.raises(LLMProviderError):
        jev.decide(QUESTIONS, "s", db_session)


@respx.mock
def test_a_network_failure_is_a_provider_error(db_session):
    respx.post(URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(LLMProviderError):
        jev.decide(QUESTIONS, "s", db_session)


@respx.mock
def test_an_unreadable_body_is_a_provider_error(db_session):
    respx.post(URL).mock(return_value=httpx.Response(200, text="<html>"))
    with pytest.raises(LLMProviderError):
        jev.decide(QUESTIONS, "s", db_session)


def test_choice_of_reads_the_chosen_options_probability():
    picked = jev.choice_of(ANSWER["q1"])
    assert (picked.choice, picked.probability, picked.confidence) == ("a", 0.9, 0.8)


def test_choice_of_falls_back_to_confidence_and_refuses_junk():
    assert jev.choice_of({"choice": "a", "confidence": 0.7}).probability == 0.7
    assert jev.choice_of(None) is None
    assert jev.choice_of({"choice": 3}) is None


@respx.mock
def test_the_call_log_keeps_metadata_only(db_session, tmp_path):
    respx.post(URL).mock(return_value=httpx.Response(200, json={"answers": ANSWER}))
    jev.decide(QUESTIONS, {"secret": "Ada Lovelace"}, db_session)
    [logged] = list((tmp_path / "llm_calls").iterdir())
    assert "Ada Lovelace" not in logged.read_text()
