"""Ownership wire-policy parity: guard states produce the promised web controls."""

import pytest

from app.services.sync import hooks
from tests.node_ts import FRONTEND, _node_with_typescript, run_node_test, ts_map


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
    """Renders the real React components, so it needs the web app's installed packages.

    Node's type stripping cannot do that (JSX, react, react-query, next). The backend CI job has
    no frontend node_modules, so there it is the frontend job that runs this file
    (`node --test components/job-ownership.test.mjs` after `npm ci`); here it runs wherever the
    packages are installed, and a missing node still fails in CI through `run_node_test`.
    """
    if not (FRONTEND / "node_modules" / "typescript").is_dir():
        _node_with_typescript()  # fails in CI when node itself is absent; only then skip
        pytest.skip("frontend packages are not installed; the frontend CI job runs this file")
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


def test_the_web_app_says_what_the_server_says():
    """A refused write shows the server's sentence; the page's own copy is the same sentence."""
    text = _source("lib/job-ownership.ts")
    for sentence in (hooks.ON_LAPTOP_MESSAGE, hooks.WITH_BOT_MESSAGE, hooks.OFFERED_MESSAGE,
                     hooks.RETURNING_MESSAGE):
        assert f'"{sentence}"' in text, sentence
