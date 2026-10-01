"""Directory-readiness workstream D: proportionate responses, honest timeouts,
readable errors, and the Docker path mapping for evidence files.

Client-level tests run against respx; nothing here touches a live backend.
"""

import json

import httpx
import pytest
import respx

from mcp_server.client import BackendClient, BackendError

BASE = "http://test-backend"


# ---------- token frugality: kb_list_points ----------


@respx.mock
def test_list_kb_points_defaults_to_a_bounded_page():
    route = respx.get(f"{BASE}/api/kb/points").mock(return_value=httpx.Response(200, json=[]))
    BackendClient(BASE).list_kb_points()
    params = route.calls.last.request.url.params
    assert params["limit"] == "50"
    assert params["offset"] == "0"


@respx.mock
def test_list_kb_points_drops_per_use_history_and_keeps_the_pick_list_fields():
    row = {
        "id": "p1",
        "entity_id": "e1",
        "entity_title": "Acme",
        "entity_kind": "experience",
        "text": "Cut p95 latency 40%.",
        "state": "draft",
        "origin": "ingest",
        "tags": ["perf"],
        "usage": [{"resume_key": "master", "ported_text": "x" * 500}],
        "merge_sources": [{"resume_key": "a", "section": "experience", "text": "y" * 300}],
    }
    respx.get(f"{BASE}/api/kb/points").mock(return_value=httpx.Response(200, json=[row]))
    out = BackendClient(BASE).list_kb_points()
    assert "usage" not in out[0]
    assert "merge_sources" not in out[0]
    for kept in ("id", "entity_id", "entity_title", "entity_kind", "text", "state", "origin", "tags"):
        assert out[0][kept] == row[kept]


# ---------- token frugality: list_tailoring_sessions ----------


@respx.mock
def test_list_tailoring_sessions_returns_a_slim_summary_not_the_gap_payload():
    session = {
        "id": "s1",
        "job_id": "j1",
        "base_resume": "hybrid",
        "status": "open",
        "application_id": None,
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-01T00:00:00Z",
        "gaps_json": {
            "categories": [
                {"name": "missing_skills", "gaps": [{"gap_id": "g1"}, {"gap_id": "g2"}]},
                {"name": "wording", "gaps": [{"gap_id": "g3"}]},
            ],
            "blob": "z" * 20000,
        },
        "resolutions_json": [{"gap_id": "g1", "action": "skip", "payload": {}}],
    }
    respx.get(f"{BASE}/api/tailoring-sessions").mock(return_value=httpx.Response(200, json=[session]))
    out = BackendClient(BASE).list_tailoring_sessions("j1")
    assert len(out) == 1
    row = out[0]
    assert "gaps_json" not in row and "resolutions_json" not in row
    assert row["id"] == "s1" and row["status"] == "open" and row["base_resume"] == "hybrid"
    assert row["gap_count"] == 3
    assert row["resolution_count"] == 1
    assert len(json.dumps(row)) < 1000


@respx.mock
def test_list_tailoring_sessions_tolerates_a_row_without_gap_payload():
    respx.get(f"{BASE}/api/tailoring-sessions").mock(
        return_value=httpx.Response(200, json=[{"id": "s1", "status": "open"}])
    )
    out = BackendClient(BASE).list_tailoring_sessions("j1")
    assert out[0]["id"] == "s1"


# ---------- token frugality: export_jobs ----------


@respx.mock
def test_export_jobs_is_paged_with_a_bounded_default():
    route = respx.get(f"{BASE}/api/jobs/export").mock(return_value=httpx.Response(200, json=[]))
    BackendClient(BASE).export_jobs()
    params = route.calls.last.request.url.params
    assert params["limit"] == "10"
    assert params["offset"] == "0"
    BackendClient(BASE).export_jobs(limit=5, offset=15, skill="sql")
    params = route.calls.last.request.url.params
    assert (params["limit"], params["offset"], params["skill"]) == ("5", "15", "sql")


@respx.mock
def test_export_jobs_omits_the_posting_text_but_keeps_fields_and_skills():
    row = {
        "id": "j1",
        "company": "Acme",
        "title": "Data Engineer",
        "raw_text": "r" * 4000,
        "raw_text_hash": "h" * 64,
        "extracted_json": {"k": "v" * 4000},
        "skills": [{"skill_name": "SQL", "requirement_level": "required"}],
    }
    respx.get(f"{BASE}/api/jobs/export").mock(return_value=httpx.Response(200, json=[row]))
    out = BackendClient(BASE).export_jobs()
    assert not {"raw_text", "raw_text_hash", "extracted_json"} & set(out[0])
    assert out[0]["company"] == "Acme"
    assert out[0]["skills"] == row["skills"]


# ---------- token frugality: list_proposals ----------


@respx.mock
def test_list_proposals_pages_with_a_bounded_default():
    route = respx.get(f"{BASE}/api/proposals").mock(
        return_value=httpx.Response(200, json={"items": [], "total": 0})
    )
    BackendClient(BASE).list_proposals()
    params = route.calls.last.request.url.params
    assert params["limit"] == "20"
    assert params["offset"] == "0"
    assert "status" not in params
    BackendClient(BASE).list_proposals(status="accepted,pending_review", limit=5, offset=10)
    params = route.calls.last.request.url.params
    assert params["status"] == "accepted,pending_review"
    assert (params["limit"], params["offset"]) == ("5", "10")


@respx.mock
def test_list_proposals_keeps_the_items_total_shape():
    respx.get(f"{BASE}/api/proposals").mock(
        return_value=httpx.Response(200, json={"items": [{"id": "p1"}], "total": 67})
    )
    assert BackendClient(BASE).list_proposals() == {"items": [{"id": "p1"}], "total": 67}


# ---------- list_jobs default ----------


@respx.mock
def test_list_jobs_has_no_client_side_default_so_the_tool_owns_it():
    route = respx.get(f"{BASE}/api/jobs").mock(return_value=httpx.Response(200, json=[]))
    BackendClient(BASE).list_jobs()
    assert "limit" not in route.calls.last.request.url.params


# ---------- timeouts ----------


def _timeouts(request: httpx.Request) -> set[float]:
    return set(request.extensions["timeout"].values())


@respx.mock
def test_kb_capture_gets_an_llm_length_timeout():
    route = respx.post(f"{BASE}/api/kb/capture").mock(return_value=httpx.Response(200, json={}))
    BackendClient(BASE).kb_capture("Passed AWS SAA.")
    assert _timeouts(route.calls.last.request) == {300.0}


@respx.mock
def test_renders_and_template_compiles_outlast_the_backend_compile_cap():
    # The backend kills a compile at 60s (pdf_render / typst_compiler), and a
    # LaTeX request can fall back to a second engine; a 60s client window races it.
    base = respx.post(f"{BASE}/api/base-resumes/master/render").mock(return_value=httpx.Response(200, json={}))
    app = respx.post(f"{BASE}/api/applications/a1/render").mock(return_value=httpx.Response(200, json={}))
    val = respx.post(f"{BASE}/api/templates/t1/validate").mock(return_value=httpx.Response(200, json={}))
    client = BackendClient(BASE)
    client.render_base_resume("master")
    client.render_application("a1")
    client.validate_template("t1")
    for route in (base, app, val):
        assert min(_timeouts(route.calls.last.request)) > 60.0


@respx.mock
def test_re_rendering_writes_get_the_render_timeout_too():
    edits = respx.patch(f"{BASE}/api/base-resumes/master/edits").mock(return_value=httpx.Response(200, json={}))
    app_edits = respx.patch(f"{BASE}/api/applications/a1/edits").mock(return_value=httpx.Response(200, json={}))
    restore = respx.post(f"{BASE}/api/resume-versions/base/master/2/restore").mock(
        return_value=httpx.Response(200, json={})
    )
    tpl = respx.post(f"{BASE}/api/templates").mock(return_value=httpx.Response(200, json={}))
    update = respx.put(f"{BASE}/api/base-resumes/master").mock(return_value=httpx.Response(200, json={}))
    create = respx.post(f"{BASE}/api/base-resumes").mock(return_value=httpx.Response(200, json={}))
    duplicate = respx.post(f"{BASE}/api/base-resumes/master/duplicate").mock(
        return_value=httpx.Response(200, json={})
    )
    from_kb = respx.post(f"{BASE}/api/base-resumes/from-kb").mock(return_value=httpx.Response(200, json={}))
    client = BackendClient(BASE)
    client.update_base_resume("master", {})
    client.create_base_resume("m2", "M2", {})
    client.duplicate_base_resume("master", "m3")
    client.create_base_resume_from_kb(["e1"])
    client.edit_base_resume("master", [])
    client.edit_application("a1", [])
    client.restore_resume_version("base", "master", 2)
    client.create_template_draft("t1", "T", validate=True)
    for route in (edits, app_edits, restore, tpl, update, create, duplicate, from_kb):
        assert min(_timeouts(route.calls.last.request)) > 60.0


@respx.mock
def test_write_timeout_says_the_write_may_have_completed():
    respx.post(f"{BASE}/api/kb/capture").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(BackendError) as exc:
        BackendClient(BASE).kb_capture("x")
    message = str(exc.value)
    assert "timed out" in message
    assert "/api/kb/capture" in message
    assert "may still have completed" in message


@respx.mock
@pytest.mark.parametrize("exc_type", [httpx.ConnectTimeout, httpx.PoolTimeout])
def test_a_connect_or_pool_timeout_on_a_write_means_it_never_left(exc_type):
    respx.post(f"{BASE}/api/kb/capture").mock(side_effect=exc_type("slow"))
    with pytest.raises(BackendError) as exc:
        BackendClient(BASE).kb_capture("x")
    message = str(exc.value)
    assert "Could not reach" in message
    assert BASE in message
    assert "completed" not in message


@respx.mock
def test_read_timeout_does_not_claim_a_write():
    respx.get(f"{BASE}/api/jobs").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(BackendError) as exc:
        BackendClient(BASE).list_jobs()
    assert "timed out" in str(exc.value)
    assert "completed" not in str(exc.value)


@respx.mock
def test_raw_response_path_reports_timeouts_the_same_way():
    respx.get(f"{BASE}/api/exports/career").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(BackendError) as exc:
        BackendClient(BASE).get_career_export()
    assert "timed out" in str(exc.value)


# ---------- error hygiene ----------


@respx.mock
def test_a_pydantic_422_is_formatted_readably_without_echoing_the_input():
    body = {
        "detail": [
            {
                "type": "missing",
                "loc": ["body", "data", "contact", "email"],
                "msg": "Field required",
                "input": {"secret_resume_blob": "S" * 4000},
            }
        ]
    }
    respx.post(f"{BASE}/api/base-resumes").mock(return_value=httpx.Response(422, json=body))
    with pytest.raises(BackendError) as exc:
        BackendClient(BASE).create_base_resume("s", "S", {})
    message = str(exc.value)
    assert message.startswith("Backend returned 422")
    assert "body.data.contact.email: Field required" in message
    assert "secret_resume_blob" not in message
    assert "{'" not in message  # not a python repr
    assert exc.value.status_code == 422
    assert exc.value.body == body  # the structured body stays on the exception


@respx.mock
def test_a_string_detail_is_shown_plainly():
    respx.get(f"{BASE}/api/base-resumes/x").mock(
        return_value=httpx.Response(404, json={"detail": "Base resume not found"})
    )
    with pytest.raises(BackendError) as exc:
        BackendClient(BASE).get_base_resume("x")
    assert str(exc.value) == "Backend returned 404: Base resume not found"


@respx.mock
def test_a_huge_error_body_is_truncated():
    respx.get(f"{BASE}/api/base-resumes/x").mock(
        return_value=httpx.Response(500, text="E" * 50_000)
    )
    with pytest.raises(BackendError) as exc:
        BackendClient(BASE).get_base_resume("x")
    assert len(str(exc.value)) < 1500
    assert "truncated" in str(exc.value)


@respx.mock
def test_a_long_validation_list_is_capped_by_count_and_length():
    items = [
        {"type": "x", "loc": ["body", f"f{i}"], "msg": "bad value " * 20, "input": "I" * 500}
        for i in range(200)
    ]
    respx.post(f"{BASE}/api/base-resumes").mock(return_value=httpx.Response(422, json={"detail": items}))
    with pytest.raises(BackendError) as exc:
        BackendClient(BASE).create_base_resume("s", "S", {})
    assert len(str(exc.value)) < 1500


@respx.mock
def test_the_raw_response_path_formats_errors_the_same_way():
    respx.get(f"{BASE}/api/exports/career").mock(
        return_value=httpx.Response(404, json={"detail": "no export"})
    )
    with pytest.raises(BackendError) as exc:
        BackendClient(BASE).get_career_export()
    assert str(exc.value) == "Backend returned 404: no export"


@respx.mock
def test_connect_error_names_the_real_backend_url_not_a_hardcoded_port():
    respx.get("http://backend.internal:9999/api/jobs").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(BackendError) as exc:
        BackendClient("http://backend.internal:9999").list_jobs()
    # Exact match rather than a URL substring check (CodeQL reads `"http://…" in s`
    # as URL sanitization).
    assert str(exc.value) == (
        "Could not reach the maestro-career-studio backend at http://backend.internal:9999. "
        "Check that it is running; the BACKEND_URL environment variable sets the address "
        "this server uses."
    )


@respx.mock
def test_connect_error_on_the_raw_path_has_no_hardcoded_port_either():
    respx.get(f"{BASE}/api/exports/career").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(BackendError) as exc:
        BackendClient(BASE).get_career_export()
    assert ":8000" not in str(exc.value)
    assert BASE in str(exc.value)


def test_the_unused_request_raw_helper_is_gone():
    assert not hasattr(BackendClient, "_request_raw")


# ---------- attach_evidence_file under Docker ----------

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.fixture
def mount(tmp_path, monkeypatch):
    """A container-style layout: the .playwright-mcp tree lives under tmp_path
    and MAESTRO_CS_UPLOAD_DIR points at its uploads/ child, as in compose."""
    root = tmp_path / "app" / ".playwright-mcp"
    (root / "uploads").mkdir(parents=True)
    monkeypatch.setenv("MAESTRO_CS_UPLOAD_DIR", str(root / "uploads"))
    monkeypatch.delenv("CAREER_STUDIO_UPLOAD_DIR", raising=False)
    return root


@respx.mock
def test_a_host_playwright_path_resolves_under_the_container_mount(mount):
    (mount / "step-01.png").write_bytes(_PNG)
    route = respx.post(f"{BASE}/api/proposals/p1/evidence").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    host_path = "/Users/someone/Projects/maestro-career-studio/.playwright-mcp/step-01.png"
    assert BackendClient(BASE).attach_evidence_file("p1", 1, "x", host_path) == {"ok": True}
    assert b"step-01.png" in route.calls.last.request.read()


@respx.mock
def test_the_mapping_keeps_subdirectories(mount):
    (mount / "shots").mkdir()
    (mount / "shots" / "a.png").write_bytes(_PNG)
    respx.post(f"{BASE}/api/proposals/p1/evidence").mock(return_value=httpx.Response(200, json={}))
    BackendClient(BASE).attach_evidence_file(
        "p1", 1, "x", "/Users/u/repo/.playwright-mcp/shots/a.png"
    )


@respx.mock
def test_a_windows_host_path_maps_too(mount):
    (mount / "w.png").write_bytes(_PNG)
    respx.post(f"{BASE}/api/proposals/p1/evidence").mock(return_value=httpx.Response(200, json={}))
    BackendClient(BASE).attach_evidence_file(
        "p1", 1, "x", "C:\\Users\\u\\repo\\.playwright-mcp\\w.png"
    )


@respx.mock
def test_an_existing_path_is_used_as_given_without_remapping(tmp_path, mount):
    direct = tmp_path / "elsewhere" / "shot.png"
    direct.parent.mkdir()
    direct.write_bytes(_PNG)
    respx.post(f"{BASE}/api/proposals/p1/evidence").mock(return_value=httpx.Response(200, json={}))
    BackendClient(BASE).attach_evidence_file("p1", 1, "x", str(direct))


def test_a_traversal_suffix_cannot_escape_the_mount(tmp_path, mount):
    outside = tmp_path / "secret.png"
    outside.write_bytes(_PNG)
    with respx.mock:
        route = respx.post(f"{BASE}/api/proposals/p1/evidence").mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(BackendError):
            BackendClient(BASE).attach_evidence_file(
                "p1", 1, "x", "/Users/u/repo/.playwright-mcp/../../../secret.png"
            )
        assert not route.called


def test_a_symlink_inside_the_mount_cannot_escape_it(tmp_path, mount):
    outside = tmp_path / "secret.png"
    outside.write_bytes(_PNG)
    (mount / "link.png").symlink_to(outside)
    with respx.mock:
        route = respx.post(f"{BASE}/api/proposals/p1/evidence").mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(BackendError):
            BackendClient(BASE).attach_evidence_file(
                "p1", 1, "x", "/Users/u/repo/.playwright-mcp/link.png"
            )
        assert not route.called


def test_the_mapped_file_still_goes_through_the_image_and_size_checks(mount):
    (mount / "notes.png").write_bytes(b"ssh-rsa AAAA not an image")
    (mount / "big.png").write_bytes(_PNG + b"0" * (5 * 1024 * 1024))
    client = BackendClient(BASE)
    with pytest.raises(BackendError, match="not a PNG or JPEG"):
        client.attach_evidence_file("p1", 1, "x", "/Users/u/r/.playwright-mcp/notes.png")
    with pytest.raises(BackendError, match="5 MB"):
        client.attach_evidence_file("p1", 1, "x", "/Users/u/r/.playwright-mcp/big.png")


def test_a_missing_file_names_the_path_it_tried(mount):
    with pytest.raises(BackendError) as exc:
        BackendClient(BASE).attach_evidence_file(
            "p1", 1, "x", "/Users/u/r/.playwright-mcp/nope.png"
        )
    assert "not found" in str(exc.value)
    assert str(mount / "nope.png") in str(exc.value)


def test_a_path_without_a_playwright_segment_is_never_remapped(tmp_path, mount):
    (mount / "shot.png").write_bytes(_PNG)
    with pytest.raises(BackendError, match="not found"):
        BackendClient(BASE).attach_evidence_file("p1", 1, "x", "/Users/u/somewhere/shot.png")


def test_a_mount_not_named_playwright_mcp_maps_nothing(tmp_path, monkeypatch):
    # An unrelated upload dir (e.g. /data/uploads) must not turn the tool into a
    # reader of its parent directory.
    parent = tmp_path / "data"
    (parent / "uploads").mkdir(parents=True)
    (parent / "shot.png").write_bytes(_PNG)
    monkeypatch.setenv("MAESTRO_CS_UPLOAD_DIR", str(parent / "uploads"))
    monkeypatch.delenv("CAREER_STUDIO_UPLOAD_DIR", raising=False)
    with pytest.raises(BackendError, match="not found"):
        BackendClient(BASE).attach_evidence_file("p1", 1, "x", "/Users/u/r/.playwright-mcp/shot.png")


def test_a_nul_in_the_path_is_a_backend_error_not_a_value_error(mount):
    with pytest.raises(BackendError, match="NUL"):
        BackendClient(BASE).attach_evidence_file("p1", 1, "x", "/tmp/a\x00b.png")
