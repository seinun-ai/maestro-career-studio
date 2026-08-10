import httpx
import respx

from mcp_server.client import BackendClient

BASE = "http://test-backend"


@respx.mock
def test_store_extracted_jd():
    route = respx.post(f"{BASE}/api/jobs/ingest").mock(
        return_value=httpx.Response(200, json={"id": "j1", "company": "Acme"})
    )
    client = BackendClient(BASE)
    out = client.store_extracted_jd({"company": "Acme"}, raw_text="jd", source_url="u")
    assert out["company"] == "Acme"
    assert route.calls.last.request.read() == (
        b'{"extracted_json":{"company":"Acme"},"raw_text":"jd","source_url":"u","source":"user"}'
    )


# Note: the {"name": "X"} data blobs below are request-shape stand-ins, not
# schema-valid ResumeData (real ResumeData requires a contact object). respx
# mocks the response, so these tests only verify the CLIENT REQUEST SHAPE.
@respx.mock
def test_update_base_resume():
    route = respx.put(f"{BASE}/api/base-resumes/master").mock(
        return_value=httpx.Response(200, json={"slug": "master"})
    )
    client = BackendClient(BASE)
    out = client.update_base_resume("master", data={"name": "X"}, display_name="Master")
    assert out["slug"] == "master"
    import json as _json
    body = _json.loads(route.calls.last.request.read())
    assert body == {"data": {"name": "X"}, "display_name": "Master"}


@respx.mock
def test_update_base_resume_data_only():
    route = respx.put(f"{BASE}/api/base-resumes/master").mock(
        return_value=httpx.Response(200, json={"slug": "master"})
    )
    client = BackendClient(BASE)
    client.update_base_resume("master", data={"name": "X"})
    import json as _json
    assert _json.loads(route.calls.last.request.read()) == {"data": {"name": "X"}}


@respx.mock
def test_create_base_resume():
    route = respx.post(f"{BASE}/api/base-resumes").mock(
        return_value=httpx.Response(200, json={"slug": "ds"})
    )
    client = BackendClient(BASE)
    out = client.create_base_resume("ds", "Data Scientist", {"name": "X"})
    assert out["slug"] == "ds"
    import json as _json
    body = _json.loads(route.calls.last.request.read())
    assert body == {"slug": "ds", "display_name": "Data Scientist", "data": {"name": "X"}}


@respx.mock
def test_duplicate_base_resume():
    route = respx.post(f"{BASE}/api/base-resumes/master/duplicate").mock(
        return_value=httpx.Response(200, json={"slug": "copy"})
    )
    client = BackendClient(BASE)
    out = client.duplicate_base_resume("master", "copy", new_display_name="Copy")
    assert out["slug"] == "copy"
    import json as _json
    body = _json.loads(route.calls.last.request.read())
    assert body == {"new_slug": "copy", "new_display_name": "Copy"}


@respx.mock
def test_edit_base_resume():
    route = respx.patch(f"{BASE}/api/base-resumes/data_scientist/edits").mock(
        return_value=httpx.Response(200, json={"slug": "data_scientist"})
    )
    client = BackendClient(BASE)
    ops = [{"kind": "replace_summary", "value": "New"}]
    out = client.edit_base_resume("data_scientist", ops)
    assert out["slug"] == "data_scientist"
    import json as _json
    assert _json.loads(route.calls.last.request.read()) == {"ops": ops}


@respx.mock
def test_tailor_application_posts_ops_to_from_base():
    route = respx.post(f"{BASE}/api/applications/from-base").mock(
        return_value=httpx.Response(200, json={"id": "a1", "customized_json": {"k": 1}})
    )
    client = BackendClient(BASE)
    ops = [{"kind": "toggle_entry", "section": "projects", "index": 0, "enabled": False}]
    out = client.tailor_application("job1", "data_scientist", ops)
    assert out["customized_json"] == {"k": 1}
    import json as _json
    body = _json.loads(route.calls.last.request.read())
    assert body == {"job_id": "job1", "base_resume": "data_scientist", "ops": ops}


@respx.mock
def test_render_base_resume():
    respx.post(f"{BASE}/api/base-resumes/master/render").mock(
        return_value=httpx.Response(200, json={"slug": "master", "pdf_path": "/p.pdf"})
    )
    client = BackendClient(BASE)
    assert client.render_base_resume("master")["pdf_path"] == "/p.pdf"


@respx.mock
def test_render_application():
    route = respx.post(f"{BASE}/api/applications/a1/render").mock(
        return_value=httpx.Response(200, json={"pdf_path": "/a.pdf"})
    )
    client = BackendClient(BASE)
    assert client.render_application("a1")["pdf_path"] == "/a.pdf"
    assert route.called


@respx.mock
def test_tailor_application_with_id_posts_to_from_base():
    route = respx.post(f"{BASE}/api/applications/from-base").mock(
        return_value=httpx.Response(200, json={"id": "a1", "customized_json": {"k": 2}})
    )
    client = BackendClient(BASE)
    ops = [{"kind": "replace_summary", "value": "Updated"}]
    out = client.tailor_application("job1", "data_scientist", ops, application_id="a1")
    assert out["customized_json"] == {"k": 2}
    import json as _json
    body = _json.loads(route.calls.last.request.read())
    assert body == {"job_id": "job1", "base_resume": "data_scientist", "ops": ops, "application_id": "a1"}


@respx.mock
def test_edit_application_patches_edits():
    route = respx.patch(f"{BASE}/api/applications/a1/edits").mock(
        return_value=httpx.Response(200, json={"id": "a1", "customized_json": {"k": 3}})
    )
    client = BackendClient(BASE)
    ops = [{"kind": "replace_summary", "value": "Edited"}]
    out = client.edit_application("a1", ops)
    assert out["customized_json"] == {"k": 3}
    import json as _json
    assert _json.loads(route.calls.last.request.read()) == {"ops": ops}


@respx.mock
def test_update_application_sends_only_set_fields():
    route = respx.patch(f"{BASE}/api/applications/a1").mock(
        return_value=httpx.Response(200, json={"id": "a1", "status": "applied"})
    )
    client = BackendClient(BASE)
    out = client.update_application("a1", status="applied")
    assert out["status"] == "applied"
    import json as _json
    assert _json.loads(route.calls.last.request.read()) == {"status": "applied"}


@respx.mock
def test_update_application_omits_none_args():
    route = respx.patch(f"{BASE}/api/applications/a1").mock(
        return_value=httpx.Response(200, json={"id": "a1"})
    )
    client = BackendClient(BASE)
    client.update_application("a1")
    import json as _json
    assert _json.loads(route.calls.last.request.read()) == {}


@respx.mock
def test_update_application_sends_all_fields_when_given():
    route = respx.patch(f"{BASE}/api/applications/a1").mock(
        return_value=httpx.Response(200, json={"id": "a1"})
    )
    client = BackendClient(BASE)
    client.update_application(
        "a1",
        status="interviewing",
        applied_at="2026-07-01T00:00:00Z",
        notes="Recruiter call scheduled",
        referral_id="r1",
    )
    import json as _json
    assert _json.loads(route.calls.last.request.read()) == {
        "status": "interviewing",
        "applied_at": "2026-07-01T00:00:00Z",
        "notes": "Recruiter call scheduled",
        "referral_id": "r1",
    }
