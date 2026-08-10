import json

import httpx
import respx

from mcp_server.client import BackendClient

BASE = "http://test-backend"


def _assert_llm_timeout(request: httpx.Request) -> None:
    assert set(request.extensions["timeout"].values()) == {300.0}


@respx.mock
def test_generate_qa_answers_posts_batch():
    route = respx.post(f"{BASE}/api/qa").mock(
        return_value=httpx.Response(200, json={"answers": ["Yes.", "No."]})
    )
    questions = ["Are you authorized to work?", "Do you need sponsorship?"]

    out = BackendClient(BASE).generate_qa_answers("a1", questions)

    assert out == {"answers": ["Yes.", "No."]}
    request = route.calls.last.request
    assert request.method == "POST"
    assert json.loads(request.read()) == {
        "application_id": "a1",
        "questions": questions,
    }
    _assert_llm_timeout(request)


@respx.mock
def test_generate_cover_letter_posts_tone_variant():
    route = respx.post(f"{BASE}/api/qa").mock(
        return_value=httpx.Response(200, json={"cover_letter": "Dear hiring team..."})
    )

    out = BackendClient(BASE).generate_cover_letter("a1", "formal")

    assert out == {"cover_letter": "Dear hiring team..."}
    request = route.calls.last.request
    assert request.method == "POST"
    assert json.loads(request.read()) == {
        "application_id": "a1",
        "cover_letter": {"tone": "formal"},
    }
    _assert_llm_timeout(request)


@respx.mock
def test_list_qa_entries_gets_application_entries():
    entries = [{"id": "q1", "application_id": "a1", "kind": "question"}]
    route = respx.get(f"{BASE}/api/qa").mock(
        return_value=httpx.Response(200, json=entries)
    )

    out = BackendClient(BASE).list_qa_entries("a1")

    assert out == entries
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.params["application_id"] == "a1"


@respx.mock
def test_waive_health_gate_posts_reason():
    route = respx.post(f"{BASE}/api/resume-lint/base/master/gates/S1/waive").mock(
        return_value=httpx.Response(204)
    )

    out = BackendClient(BASE).waive_health_gate(
        "base", "master", "S1", "Reviewed and accepted"
    )

    assert out is None
    request = route.calls.last.request
    assert request.method == "POST"
    assert json.loads(request.read()) == {"reason": "Reviewed and accepted"}


@respx.mock
def test_unwaive_health_gate_uses_waiver_endpoint_without_delete_tool_name():
    route = respx.delete(
        f"{BASE}/api/resume-lint/application/a1/gates/C2/waive"
    ).mock(return_value=httpx.Response(204))

    out = BackendClient(BASE).unwaive_health_gate("application", "a1", "C2")

    assert out is None
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert request.read() == b""
