"""An id goes into a REST path as one plain segment, never as a way to another route.

httpx resolves `..` and treats `?` and `#` as the end of the path, so an unchecked id such
as "../settings/autofill" turned get_base_resume into a read of the stored autofill profile
(EEO answers included), and unwaive_health_gate into a DELETE on any route.
"""

import httpx
import pytest
import respx

from mcp_server.client import BackendClient, BackendError

BASE = "http://test-backend"
JOB = "2c8b09e6-ce44-438e-9d5b-e2efaf26be04"

BAD_IDS = [
    "../settings/autofill",
    "..",
    ".",
    "x/../../settings/autofill",
    "x?",
    "x#frag",
    "a/b",
    "a\\b",
    "%2e%2e",
    "",
    " spaced",
]

CALLS = [
    ("get_base_resume", lambda c, bad: c.get_base_resume(bad)),
    ("get_job", lambda c, bad: c.get_job(bad)),
    ("unwaive_health_gate", lambda c, bad: c.unwaive_health_gate("base", "master", bad)),
    ("unwaive_health_gate key", lambda c, bad: c.unwaive_health_gate("base", bad, "S1")),
    ("validate_template", lambda c, bad: c.validate_template(bad)),
    ("get_proposal", lambda c, bad: c.get_proposal(bad)),
    ("list_resume_versions", lambda c, bad: c.list_resume_versions("base", bad)),
]


@pytest.mark.respx(assert_all_called=False)
@pytest.mark.parametrize("bad", BAD_IDS)
@pytest.mark.parametrize("name,call", CALLS, ids=[c[0] for c in CALLS])
def test_an_unsafe_id_is_refused_before_any_request(respx_mock, name, call, bad):
    catch_all = respx_mock.route().mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(BackendError, match="Not a valid id"):
        call(BackendClient(BASE), bad)
    assert not catch_all.called


def test_every_value_in_a_rest_path_goes_through_seg():
    """A "/" in an id passes the whole-path backstop as two plain segments, so each value is
    checked on its own where the path is built."""
    import re
    from pathlib import Path

    import mcp_server.client as client_module

    source = Path(client_module.__file__).read_text()
    paths = re.findall(r'f"/api[^"]*"', source)
    assert paths, "no REST path f-strings found: the scan needs updating"
    unchecked = [p for p in paths if re.search(r"\{(?!_seg\()", p)]
    assert unchecked == []


@respx.mock
def test_plain_slugs_uuids_and_file_names_still_reach_their_routes():
    respx.get(f"{BASE}/api/base-resumes/supply_chain_analyst_2").mock(
        return_value=httpx.Response(200, json={"slug": "supply_chain_analyst_2"})
    )
    respx.get(f"{BASE}/api/jobs/{JOB}/detail").mock(return_value=httpx.Response(200, json={"id": JOB}))
    respx.delete(f"{BASE}/api/resume-lint/base/master/gates/S1/waive").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client = BackendClient(BASE)
    assert client.get_base_resume("supply_chain_analyst_2")["slug"] == "supply_chain_analyst_2"
    assert client.get_job(JOB)["id"] == JOB
    assert client.unwaive_health_gate("base", "master", "S1") == {"ok": True}
