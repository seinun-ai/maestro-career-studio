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


@respx.mock
def test_store_extracted_jd_sends_the_apply_link_and_update_only_when_given():
    """A call without them sends exactly what it always did (the test above)."""
    import json

    route = respx.post(f"{BASE}/api/jobs/ingest").mock(
        return_value=httpx.Response(200, json={"id": "j1"})
    )
    client = BackendClient(BASE)
    client.store_extracted_jd(
        {"company": "Kestrel Logistics"}, raw_text="jd",
        apply_url="https://apply.kestrel.example/requisitions/77", update=True,
    )
    body = json.loads(route.calls.last.request.read())
    assert body["apply_url"] == "https://apply.kestrel.example/requisitions/77"
    assert body["update"] is True
    client.store_extracted_jd({"company": "Kestrel Logistics"}, raw_text="jd", update=False)
    assert "update" not in json.loads(route.calls.last.request.read())


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
def test_update_application_clear_sends_explicit_nulls():
    route = respx.patch(f"{BASE}/api/applications/a1").mock(
        return_value=httpx.Response(200, json={"id": "a1"})
    )
    BackendClient(BASE).update_application("a1", status="withdrawn", clear=["notes", "referral_id"])
    import json as _json
    assert _json.loads(route.calls.last.request.read()) == {
        "status": "withdrawn", "notes": None, "referral_id": None,
    }


@respx.mock(assert_all_called=False)
def test_update_application_refuses_a_field_both_set_and_cleared():
    import pytest

    from mcp_server.client import BackendError

    route = respx.patch(f"{BASE}/api/applications/a1").mock(
        return_value=httpx.Response(200, json={"id": "a1"})
    )
    with pytest.raises(BackendError, match="referral_id"):
        BackendClient(BASE).update_application("a1", referral_id="r1", clear=["referral_id"])
    assert not route.called


@respx.mock(assert_all_called=False)
def test_update_application_refuses_a_bare_string_clear():
    import pytest

    from mcp_server.client import BackendError

    route = respx.patch(f"{BASE}/api/applications/a1").mock(
        return_value=httpx.Response(200, json={"id": "a1"})
    )
    with pytest.raises(BackendError, match="a single name goes in a list too"):
        BackendClient(BASE).update_application("a1", clear="notes")
    assert not route.called


def test_update_application_clears_only_notes_and_referral_id():
    import pytest

    from mcp_server.client import BackendError

    with pytest.raises(BackendError, match="status"):
        BackendClient(BASE).update_application("a1", clear=["status"])


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


@respx.mock
def test_list_resume_versions_hits_kind_key_collection():
    route = respx.get(f"{BASE}/api/resume-versions/base/master").mock(
        return_value=httpx.Response(200, json=[{"number": 1}])
    )
    assert BackendClient(BASE).list_resume_versions("base", "master") == [{"number": 1}]
    assert route.called


@respx.mock
def test_get_resume_version_hits_kind_key_number():
    route = respx.get(f"{BASE}/api/resume-versions/application/a1/3").mock(
        return_value=httpx.Response(200, json={"number": 3, "diff": []})
    )
    out = BackendClient(BASE).get_resume_version("application", "a1", 3)
    assert out["number"] == 3
    assert route.called


@respx.mock
def test_restore_resume_version_posts_restore():
    route = respx.post(f"{BASE}/api/resume-versions/base/master/2/restore").mock(
        return_value=httpx.Response(200, json={"number": 3})
    )
    assert BackendClient(BASE).restore_resume_version("base", "master", 2) == {
        "number": 3
    }
    assert route.called


@respx.mock
def test_archive_base_resume_posts_archive():
    route = respx.post(f"{BASE}/api/base-resumes/other/archive").mock(
        return_value=httpx.Response(200, json={"slug": "other", "archived_at": "t"})
    )
    assert BackendClient(BASE).archive_base_resume("other")["slug"] == "other"
    assert route.called


@respx.mock
def test_unarchive_base_resume_posts_unarchive():
    route = respx.post(f"{BASE}/api/base-resumes/other/unarchive").mock(
        return_value=httpx.Response(200, json={"slug": "other", "archived_at": None})
    )
    assert BackendClient(BASE).unarchive_base_resume("other")["archived_at"] is None
    assert route.called


@respx.mock
def test_set_base_resume_identity_sends_only_supplied_keys():
    route = respx.patch(f"{BASE}/api/base-resumes/uk_ds/identity").mock(
        return_value=httpx.Response(200, json={"slug": "uk_ds"})
    )
    client = BackendClient(BASE)
    client.set_base_resume_identity("uk_ds", countries=["GB"], role_label="Data scientist")
    import json as _json
    assert _json.loads(route.calls.last.request.read()) == {
        "countries": ["GB"],
        "role_label": "Data scientist",
    }


@respx.mock
def test_set_base_resume_identity_sends_clearing_values_as_given():
    route = respx.patch(f"{BASE}/api/base-resumes/uk_ds/identity").mock(
        return_value=httpx.Response(200, json={"slug": "uk_ds"})
    )
    client = BackendClient(BASE)
    client.set_base_resume_identity("uk_ds", company="", focus="", countries=[])
    import json as _json
    assert _json.loads(route.calls.last.request.read()) == {
        "company": "",
        "focus": "",
        "countries": [],
    }


@respx.mock
def test_set_base_resume_identity_sends_the_colour_hue():
    route = respx.patch(f"{BASE}/api/base-resumes/uk_ds/identity").mock(
        return_value=httpx.Response(200, json={"slug": "uk_ds"})
    )
    BackendClient(BASE).set_base_resume_identity("uk_ds", color_hue=230)
    import json as _json
    assert _json.loads(route.calls.last.request.read()) == {"color_hue": 230}


@respx.mock
def test_score_ats_posts_include_other_countries_only_when_true():
    route = respx.post(f"{BASE}/api/ats-scores").mock(return_value=httpx.Response(200, json=[]))
    client = BackendClient(BASE)
    import json as _json
    client.score_ats("j1")
    assert _json.loads(route.calls.last.request.read()) == {"job_id": "j1"}
    client.score_ats("j1", include_other_countries=True)
    assert _json.loads(route.calls.last.request.read()) == {
        "job_id": "j1",
        "include_other_countries": True,
    }


@respx.mock
def test_ats_candidates_gets_the_country_rule_for_a_job():
    route = respx.get(f"{BASE}/api/ats-scores/candidates").mock(
        return_value=httpx.Response(
            200, json={"job_country": "US", "fallback": False, "skipped": ["uk_ds"]}
        )
    )
    client = BackendClient(BASE)
    out = client.ats_candidates("j1")
    assert out["skipped"] == ["uk_ds"]
    assert route.calls.last.request.url.params["job_id"] == "j1"


@respx.mock
def test_ats_candidates_sends_include_other_countries_only_when_true():
    route = respx.get(f"{BASE}/api/ats-scores/candidates").mock(
        return_value=httpx.Response(200, json={"job_country": "US", "fallback": False, "skipped": []})
    )
    client = BackendClient(BASE)
    client.ats_candidates("j1")
    assert "include_other_countries" not in route.calls.last.request.url.params
    client.ats_candidates("j1", include_other_countries=True)
    assert route.calls.last.request.url.params["include_other_countries"] == "true"


@respx.mock
def test_resume_writes_carry_the_agent_origin_so_the_voice_rule_applies():
    """The backend refuses a third-person line only from a connected agent (the MCP
    origin header); without the header these writes would store it like a web save."""
    app_id = "1a824847-f6ff-43d9-bca5-f536d978e3ca"
    routes = [
        respx.patch(f"{BASE}/api/base-resumes/master/edits").mock(return_value=httpx.Response(200, json={})),
        respx.patch(f"{BASE}/api/applications/{app_id}/edits").mock(return_value=httpx.Response(200, json={})),
        respx.put(f"{BASE}/api/base-resumes/master").mock(return_value=httpx.Response(200, json={})),
    ]
    client = BackendClient(BASE)
    ops = [{"kind": "replace_summary", "value": "Led the team."}]
    client.edit_base_resume("master", ops)
    client.edit_application(app_id, ops)
    client.update_base_resume("master", {"contact": {"name": "R", "email": "r@example.com"}})
    for route in routes:
        assert route.calls.last.request.headers.get("X-Maestro-CS-Origin") == "mcp"


# ---------- save_referral: POST to add, PUT (a partial update) to edit ----------


@respx.mock
def test_save_referral_adds_one_with_only_the_fields_given():
    route = respx.post(f"{BASE}/api/referrals").mock(
        return_value=httpx.Response(200, json={"id": "r1", "company": "Northwind Labs"})
    )
    out = BackendClient(BASE).save_referral("Northwind Labs", careers_url="https://northwind.example/jobs")
    assert out["id"] == "r1"
    import json as _json
    assert _json.loads(route.calls.last.request.read()) == {
        "company": "Northwind Labs", "careers_url": "https://northwind.example/jobs",
    }


@respx.mock
def test_save_referral_edits_by_id_and_sends_only_what_it_was_given():
    route = respx.put(f"{BASE}/api/referrals/r1").mock(
        return_value=httpx.Response(200, json={"id": "r1"})
    )
    BackendClient(BASE).save_referral(notes="Intro sent", referral_id="r1")
    import json as _json
    # No company: an edit never renames the referral unless it is asked to.
    assert _json.loads(route.calls.last.request.read()) == {"notes": "Intro sent"}


def test_save_referral_needs_a_company_and_a_careers_page_to_add_one():
    import pytest

    from mcp_server.client import BackendError

    with pytest.raises(BackendError, match="careers_url"):
        BackendClient(BASE).save_referral("Northwind Labs", contact_name="Amara Okafor")
    with pytest.raises(BackendError, match="company"):
        BackendClient(BASE).save_referral(careers_url="https://northwind.example/jobs")


def test_save_referral_refuses_a_blank_company():
    import pytest

    from mcp_server.client import BackendError

    with pytest.raises(BackendError, match="company"):
        BackendClient(BASE).save_referral("  ", careers_url="https://northwind.example/jobs")
    with pytest.raises(BackendError, match="company"):
        BackendClient(BASE).save_referral(" ", referral_id="r1")


@respx.mock
def test_save_referral_unknown_id_is_the_backends_404():
    import pytest

    from mcp_server.client import BackendError

    respx.put(f"{BASE}/api/referrals/r404").mock(
        return_value=httpx.Response(404, json={"detail": "Referral not found"})
    )
    with pytest.raises(BackendError, match="Referral not found") as exc:
        BackendClient(BASE).save_referral(notes="x", referral_id="r404")
    assert exc.value.status_code == 404
