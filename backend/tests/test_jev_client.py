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
@pytest.mark.parametrize("status", [429, 503, 529])
def test_a_busy_provider_is_retried_twice_then_given_up(db_session, status):
    route = respx.post(URL).mock(side_effect=[httpx.Response(status)] * 3)
    with pytest.raises(LLMProviderError):
        jev.decide(QUESTIONS, "s", db_session)
    assert route.call_count == 3


@respx.mock
def test_no_retry_is_started_that_the_budget_cannot_cover(db_session, monkeypatch):
    monkeypatch.setattr(jev, "_BACKOFF_S", jev.TIMEOUT_S)
    route = respx.post(URL).mock(side_effect=[httpx.Response(529)] * 3)
    with pytest.raises(LLMProviderError):
        jev.decide(QUESTIONS, "s", db_session)
    assert route.call_count == 1


def test_every_call_goes_through_one_pooled_client(db_session, monkeypatch):
    """Two calls per fill, back to back: a connection per call would pay a TLS
    handshake each time, about what Jev's whole answer costs."""
    used = []

    class Recording(httpx.Client):
        def post(self, url, **kwargs):
            used.append(self)
            return httpx.Response(200, json={"answers": ANSWER},
                                  request=httpx.Request("POST", url))

    client = Recording()
    monkeypatch.setattr(jev, "_CLIENT", client)
    jev.decide(QUESTIONS, "s", db_session)
    jev.decide(QUESTIONS, "s", db_session)
    assert used == [client, client]


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


OFFERED = {"a": "A", "b": "B"}


def test_choice_of_reads_the_chosen_options_probability():
    picked = jev.choice_of(ANSWER["q1"], OFFERED)
    assert (picked.choice, picked.probability, picked.confidence) == ("a", 0.9, 0.8)


@pytest.mark.parametrize("answer", [
    None,
    {"choice": "a", "probabilities": {"a": 0.9, "b": 0.1}},                   # no confidence
    {"choice": "c", "probabilities": {"a": 0.9, "b": 0.1}, "confidence": 0.8},  # not offered
    {"choice": "a", "probabilities": {"a": 1.0}, "confidence": 0.8},            # key missing
    {"choice": "a", "probabilities": {"a": 0.8, "b": 0.1, "c": 0.1},
     "confidence": 0.8},                                                        # key extra
    {"choice": "a", "probabilities": {"a": 0.6, "b": 0.1}, "confidence": 0.8},  # sums to 0.7
    {"choice": "b", "probabilities": {"a": 0.9, "b": 0.1}, "confidence": 0.8},  # not the max
    {"choice": "a", "probabilities": {"a": 1.5, "b": -0.5}, "confidence": 0.8}, # out of range
    {"choice": "a", "probabilities": {"a": True, "b": 0}, "confidence": 0.8},   # a bool
    {"choice": 3, "probabilities": {"a": 0.9, "b": 0.1}, "confidence": 0.8},
])
def test_choice_of_refuses_anything_but_a_distribution_over_the_offered_keys(answer):
    assert jev.choice_of(answer, OFFERED) is None


@respx.mock
def test_the_call_log_keeps_metadata_only(db_session, tmp_path):
    respx.post(URL).mock(return_value=httpx.Response(200, json={"answers": ANSWER}))
    jev.decide(QUESTIONS, {"secret": "Ada Lovelace"}, db_session)
    [logged] = list((tmp_path / "llm_calls").iterdir())
    assert "Ada Lovelace" not in logged.read_text()
