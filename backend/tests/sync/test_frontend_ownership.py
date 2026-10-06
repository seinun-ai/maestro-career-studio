"""Ownership wire-policy parity: guard states produce the promised web controls."""

from tests.node_ts import run_node_test, ts_map


def test_web_ownership_policy_behaviors():
    done = run_node_test("lib/job-ownership.test.ts")
    assert done.returncode == 0, done.stdout + done.stderr


def test_wire_states_match_the_web_marks():
    values = [
        {"owned_here": True, "owner": None, "handover": None, "pending_requests": 0},
        {"owned_here": False, "owner": "bot", "handover": None, "pending_requests": 1},
        {"owned_here": False, "owner": "laptop", "handover": "offered", "pending_requests": 0},
        {"owned_here": True, "owner": "laptop", "handover": None, "pending_requests": 0},
    ]
    actual = ts_map("./lib/job-ownership.ts", "jobOwnershipView", values)
    assert [view["mark"] for view in actual] == [None, "With your bot", "Going to your bot", "On your laptop"]
    assert [view["canWrite"] for view in actual] == [True, False, False, True]
    assert [view["canRequest"] for view in actual] == [True, True, False, True]
    assert [view["action"] for view in actual] == [None, "work-here", "keep-here", None]


def test_actual_marks_render_without_a_browser():
    done = run_node_test("components/job-ownership.test.mjs")
    assert done.returncode == 0, done.stdout + done.stderr
