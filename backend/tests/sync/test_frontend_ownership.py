"""Ownership wire-policy parity: guard states produce the promised web controls."""

from tests.node_ts import FRONTEND, run_node_test, ts_map


def test_web_ownership_policy_behaviors():
    done = run_node_test("lib/job-ownership.test.ts")
    assert done.returncode == 0, done.stdout + done.stderr


def test_wire_states_match_the_web_marks():
    values = [
        {"owned_here": True, "owner": None, "handover": None, "pending_requests": 0},
        {"owned_here": False, "owner": "bot", "handover": None, "pending_requests": 1},
        {"owned_here": False, "owner": "laptop", "handover": "offered", "pending_requests": 0,
         "can_keep_here": True},
        {"owned_here": True, "owner": "laptop", "handover": None, "pending_requests": 0},
        {"owned_here": False, "owner": "laptop", "handover": "offered", "pending_requests": 0,
         "can_keep_here": False},
    ]
    actual = ts_map("./lib/job-ownership.ts", "jobOwnershipView", values)
    assert [view["mark"] for view in actual] == [
        None, "With your bot", "Going to your bot", "On your laptop", "Going to your bot"]
    assert [view["canWrite"] for view in actual] == [True, False, False, True, False]
    assert [view["canRequest"] for view in actual] == [True, True, False, True, False]
    assert [view["action"] for view in actual] == [None, "work-here", "keep-here", None, None]


def test_actual_marks_render_without_a_browser():
    done = run_node_test("components/job-ownership.test.mjs")
    assert done.returncode == 0, done.stdout + done.stderr


def _source(path):
    return (FRONTEND / path).read_text(encoding="utf-8")


def test_sync_off_pages_make_no_ownership_requests():
    """Ownership rides on the rows the pages already fetch: no job-list read, no refusals read."""
    assert not (FRONTEND / "hooks/use-job-ownership.ts").exists()
    for path in ["app/applications/page.tsx", "components/proposals/proposals-section.tsx",
                 "components/proposals/recent-runs.tsx", "components/job-ownership.tsx"]:
        text = _source(path)
        assert "use-job-ownership" not in text and "refused-requests" not in text, path
        assert "limit=500" not in text, path
    assert _source("components/proposals/recent-runs.tsx").count("apiFetch<") == 1


def test_tailor_page_reads_ownership_and_locks_every_write():
    text = _source("app/jobs/[id]/tailor/[sessionId]/page.tsx")
    assert "jobDetail.data?.job.ownership" in text
    assert "<GapLocked value={tailorBusy || !ownership.canWrite}>" in text
    assert "readOnly={tailorBusy || !ownership.canWrite}" in text
    assert text.count("|| !ownership.canWrite}") >= 4  # notes, use as is, quick tailor, tailor
    assert "<JobOwnershipMark" in text and "<JobOwnershipNotice" in text
    assert "isOwnershipRefusal" in text
