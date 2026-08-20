"""Guided Apply R1 — the guided-fill runner, residue, and rest_fill telemetry.

Lane G. `guidedWrite` is stubbed: Lane S owns the writer. These tests pin the
routing, the residue list, and the value-free telemetry batch. (The arming gate
and its debounced stage-swap runner were the floating card's — a MutationObserver
watching a wizard step over for a run nobody had asked for. R-C deleted both:
the panel's Fill stage starts on a click, so there is no burst to coalesce.)

**Round B Task 11 moved the orchestration, not the behaviour.** Collect →
route → /choose → guided_write → reconcile is `extension/shared/guided-run.js`,
with the transport injected — it was written as one runner for two surfaces and
R-C left it with one, the panel's Fill stage. So the table at the bottom of
this file drives the REAL runner through `loadModules()` against scripted deps,
and the caller's own wiring is pinned against `panel/actions/fill.js`. The R1
honesty rules are tested against the runner because that is where they hold:
identity data never reaching /choose, abstains and failures degrading to
residue, one write per stage, telemetry carrying no values.
"""

import json
import re

import pytest

from tests.extension_harness import FORM_MODULE_SOURCES, ROOT, js_code, run_node

_FORM_SOURCE = "\n".join(path.read_text(encoding="utf-8") for path in FORM_MODULE_SOURCES)
GUIDED_RUN_JS = (ROOT / "extension" / "shared" / "guided-run.js").read_text(
    encoding="utf-8")
# Task 12's split: routing, the /choose batch and the `rest_fill` shaping live
# here now, so the panel document can load what the runner reads. It is in
# FORM_MODULE_SOURCES, so every driver below already runs it.
CHOOSE_JS = (ROOT / "extension" / "shared" / "choose.js").read_text(encoding="utf-8")
AGENT_JS = (ROOT / "extension" / "content" / "agent.js").read_text(encoding="utf-8")
SW_JS = (ROOT / "extension" / "sw.js").read_text(encoding="utf-8")

_OBS_KEYS = {"label", "kind", "host", "outcome", "rule_id", "options"}
_REST_OUTCOMES = {
    "filled", "retry_filled", "match_recovered", "filled_unverified",
    "not_stuck", "ai_abstained",
}


_TELEMETRY_DRIVER = r"""
const ns = loadModules();
const observations = ns.buildRestFillObservations({
  questions: spec.questions,
  writeResults: spec.writeResults,
  abstained: spec.abstained,
});
emit({ observations });
"""


def test_rest_fill_telemetry_only_emits_whitelisted_keys_and_known_outcomes(tmp_path):
    """extra=forbid 422s a whole batch. Values never appear; a bogus outcome
    from a stubbed writer is dropped rather than posted.

    THE HOST IS THE ROW'S. `collectFromPage` stamps every question and every
    retryable with the host of the FRAME that answered — the truthful host for
    an iframe-embedded form — and Task 12 removed the `location.hostname`
    fallback this function used to keep for rows that carried none. It had to
    go with the move: in a panel document `location.hostname` is the
    extension's own id, so the fallback would have attributed a Workday fill to
    `chrome-extension://…`. The harness's ambient hostname is
    `jobs.example.test`, which is exactly the misattribution shape, and it must
    not appear.
    """
    frame_host = "acme.wd5.myworkdayjobs.com"
    out = run_node(
        _TELEMETRY_DRIVER,
        {
            "questions": [
                {"qid": "a", "label": "How did you hear about us?", "kind": "combobox",
                 "options": ["LinkedIn"], "host": frame_host},
                {"qid": "b", "label": "Why this role?", "kind": "text",
                 "host": frame_host},
                {"qid": "c", "label": "Secret salary", "kind": "text",
                 "value": "120000", "host": frame_host},
            ],
            "writeResults": [
                {"qid": "a", "outcome": "filled"},
                {"qid": "c", "outcome": "totally_made_up"},
            ],
            "abstained": [{"qid": "b", "label": "Why this role?", "kind": "text"}],
        },
        tmp_path,
        source=_FORM_SOURCE,
    )
    observations = out["observations"]
    outcomes = {o["outcome"] for o in observations}
    assert outcomes <= _REST_OUTCOMES
    assert outcomes == {"filled", "ai_abstained"}
    for obs in observations:
        assert set(obs) <= _OBS_KEYS
        assert "value" not in obs
        assert "answer" not in obs
        assert obs["rule_id"] is None
        # The abstained row carries no host of its own; it resolves through the
        # question map, which is the only thing keeping this true.
        assert obs["host"] == frame_host
    assert "jobs.example.test" not in json.dumps(observations)


def test_a_row_with_no_host_reports_none_rather_than_the_documents(tmp_path):
    """"We do not know" on the wire, and the reason the fallback is gone.

    The shipped collector cannot produce a hostless row — every question and
    retryable is stamped from the frame that answered — so this is the shape
    that would have to arrive from somewhere new. An empty string is what it
    reports. The alternative, and what this function used to do, is to name
    whatever document happens to be running the code: in a content script that
    is a plausible-looking lie for an embedded form, and in the panel it is
    `chrome-extension://…`.
    """
    out = run_node(
        _TELEMETRY_DRIVER,
        {
            "questions": [{"qid": "a", "label": "Preferred shift", "kind": "select"}],
            "writeResults": [{"qid": "a", "outcome": "filled"}],
            "abstained": [],
        },
        tmp_path,
        source=_FORM_SOURCE,
    )
    assert [obs["host"] for obs in out["observations"]] == [""]


_WRITE_DRIVER = r"""
const ns = loadModules();
const calls = [];
ns.guidedWrite = async (items) => {
  calls.push(items.map((item) => ({
    qid: item.qid, kind: item.kind, hasEl: !!item.el, answer: item.answer,
  })));
  return items.map((item) => ({ qid: item.qid, outcome: "filled" }));
};
// Stamp a tagged control so applyGuidedChoices can resolve it.
const el = { tagName: "INPUT" };
el.getAttribute = () => null;
global.document.querySelector = (sel) => (sel.includes("q1") ? el : null);
main(async () => {
  const results = await ns.applyGuidedChoices([
    { qid: "q1", kind: "text", answer: "Yes" },
    { qid: "missing", kind: "text", answer: "No" },
  ]);
  emit({ results, calls });
});
"""


def test_apply_guided_choices_stubs_through_the_frozen_write_contract(tmp_path):
    """qid → element happens in-frame. The writer receives `el`, never a
    serialized node, and a missing qid is skipped rather than thrown."""
    out = run_node(_WRITE_DRIVER, {}, tmp_path, source=_FORM_SOURCE)
    assert out["calls"] == [[{
        "qid": "q1", "kind": "text", "hasEl": True, "answer": "Yes",
    }]]
    assert out["results"] == [{"qid": "q1", "outcome": "filled"}]


def test_the_panel_hands_the_runner_the_rules_and_a_telemetry_emitter():
    """What the caller hands the runner, and it is a source pin because the
    wiring sits inside a click handler.

    Both arguments fail SILENTLY. Drop `rulePass` and the deterministic pass
    simply stops happening — every field the rules own becomes residue, and
    nothing errors. Drop `telemetry` and the runner's `rest_fill` batch goes
    nowhere, which is invisible from the surface by design.

    THE THIRD ARGUMENT IS PINNED ELSEWHERE AND BETTER. `aiAssist` is
    behavioural in `test_extension_panel_fill.py::
    test_rules_only_asks_the_model_nothing_at_all`, which counts `/choose`
    calls in both modes — a source pin would pass on an inverted expression.
    (R-C deleted the card's copy of this wiring and with it three pins that
    were about the CARD's shape rather than the pipeline: a "Start guided fill"
    button separate from a primary Autofill, and an in-frame `scrollIntoView`
    for residue. The panel's Fill stage IS the primary, and its residue rows
    jump by message — both behavioural, in that same file.)
    """
    fill_js = (ROOT / "extension" / "panel" / "actions" / "fill.js").read_text(
        encoding="utf-8")
    call = re.search(r"runGuidedFill\(\{(.*?)\n        \}, \{", fill_js, re.S)
    assert call, "the runGuidedFill call is not where this test expects it"
    body = call.group(1)
    assert "rulePass:" in body
    assert "telemetry: store.telemetry" in body


def test_rest_fill_is_the_guided_pass_action():
    """The action name, and the wiring that makes naming it mean anything.

    The emission lives in the shared runner with the rest of the pipeline. The
    runner emits through an INJECTED dep, so `"rest_fill"` sitting in that file
    proves nothing on its own: what makes the batch real is the caller handing
    it the emitter that gates on the opt-in and scrubs in the service worker.

    Both directions run through `js_code`, and both need it. The positive would
    pass on a commented-out call — the failure this repo has hit before. The
    negative is the subtler one: these files explain moves in prose, and a file
    that writes "`sendTelemetry("rest_fill")` moved to the runner" beside a
    tombstone is exactly right while a raw scan fails it.
    """
    fill_js = (ROOT / "extension" / "panel" / "actions" / "fill.js").read_text(
        encoding="utf-8")
    assert '"rest_fill"' in js_code(GUIDED_RUN_JS)
    assert "telemetry: store.telemetry" in js_code(fill_js)
    assert 'telemetry("rest_fill"' not in js_code(fill_js), (
        "a second rest_fill emitter was left in the panel; the runner's is the "
        "one every caller shares")
    assert "ai_abstained" in CHOOSE_JS


# ---------- the shared runner, driven end to end ----------
#
# `shared/guided-run.js` is a loadable module, so these run the REAL file
# through `loadModules()` against scripted deps rather than slicing source: a
# fake `broadcast` returning canned frames, a fake `api` recording every call,
# and recorders for the two `onProgress` phases and the telemetry hand-off.
# What is under test is the sequencing and the batching — the engine behind
# `guided_write` and the writer behind the rule pass have their own files and
# their own tests, and are deliberately not reached from here.

_RUNNER_SOURCE = _FORM_SOURCE + "\n" + GUIDED_RUN_JS

_RUNNER_DRIVER = r"""
const ns = loadModules();
const apiCalls = [];
const sent = [];
const progress = [];
const telemetry = [];
let rulePassRuns = 0;

const collectFrames = [{
  frameId: 0,
  result: {
    host: spec.host ?? "acme.wd5.myworkdayjobs.com",
    questions: spec.questions ?? [],
    retryables: spec.retryables ?? [],
  },
}];

const deps = {
  broadcast: async (message) => {
    sent.push(message);
    if (message.type === "collect_open_questions") {
      return spec.reachNobody ? [{ frameId: 0 }] : collectFrames;
    }
    if (message.type === "guided_write") {
      const outcomes = spec.writeOutcomes ?? {};
      // `dropWrites` models the engine answering about FEWER pairs than it was
      // sent — a control that vanished with its stage before the writer got to
      // it. The frame answered, so this is not an unreached page.
      const dropped = new Set(spec.dropWrites ?? []);
      return [{
        frameId: 0,
        result: message.pairs
          .filter((pair) => !dropped.has(pair.qid))
          .map((pair) => ({
            qid: pair.qid, outcome: outcomes[pair.qid] ?? "filled",
          })),
      }];
    }
    return [];
  },
  api: async (path, init) => {
    apiCalls.push({ path, body: JSON.parse(init.body) });
    if (spec.chooseFails) throw new Error("500");
    const choices = {};
    for (const field of JSON.parse(init.body).fields) {
      choices[field.qid] = spec.abstainAll
        ? { answer: null, reason: "abstained" }
        : { answer: "Yes", reason: "matched" };
    }
    return { choices };
  },
  onProgress: (update) => { progress.push(update); },
  telemetry: (action, observations) => { telemetry.push({ action, observations }); },
  rulePass: async () => {
    rulePassRuns += 1;
    if (spec.rulePassThrows) throw new Error("no autofill profile yet");
  },
};

// A half-wired caller, modelled by removing one dep rather than by passing a
// different object: what the guard has to catch is the dep somebody forgot.
if (spec.omitDep) delete deps[spec.omitDep];

main(async () => {
  let result = null;
  let threw = null;
  try {
    result = await ns.guidedRun.runGuidedFill(deps, spec.options ?? {});
  } catch (err) {
    threw = String(err?.message ?? err);
  }
  emit({ result, threw, apiCalls, sent, progress, telemetry, rulePassRuns });
});
"""


def _run_guided(tmp_path, **spec):
    return run_node(_RUNNER_DRIVER, spec, tmp_path, source=_RUNNER_SOURCE)


def _open_questions(n, kind="text"):
    """`n` collected controls whose labels are not QUESTIONY, so every one of
    them routes to /choose rather than to the essay queue."""
    return [
        {"qid": f"q{i}", "label": f"Field {i}", "kind": kind, "options": []}
        for i in range(n)
    ]


def _writes(out):
    return [m for m in out["sent"] if m["type"] == "guided_write"]


def test_forty_one_questions_are_two_choose_calls_through_the_runner(tmp_path):
    """The 40-cap is the request's, and the runner is what feeds it. Driven
    here rather than only at `requestChoose` because a runner that collected
    into one array and posted it whole would still pass that test."""
    out = _run_guided(tmp_path, questions=_open_questions(41))

    assert [call["path"] for call in out["apiCalls"]] == [
        "/api/autofill/choose", "/api/autofill/choose"]
    assert [len(call["body"]["fields"]) for call in out["apiCalls"]] == [40, 1]
    assert {row["qid"] for row in out["result"]["residue"]} == set()


def test_a_choose_failure_degrades_to_residue_and_rolls_nothing_back(tmp_path):
    """R1's third honesty rule, through the whole pipeline: the /choose call
    fails, the runner still returns, the rule pass is NOT re-run or undone, and
    the fields it could not answer come back as the residue the user is shown.
    A throw here would leave the page half-filled with no list of what is left."""
    out = _run_guided(
        tmp_path,
        questions=_open_questions(3),
        retryables=[{"qid": "r0", "label": "Country", "kind": "combobox",
                     "known_value": "United States"}],
        chooseFails=True,
    )

    assert out["threw"] is None
    assert out["rulePassRuns"] == 1
    assert {row["qid"] for row in out["result"]["residue"]} == {"q0", "q1", "q2"}
    # The rule pass's own work stands, and so does the retryable write that
    # never depended on /choose: degrading is not rolling back.
    assert [pair["qid"] for pair in _writes(out)[0]["pairs"]] == ["r0"]
    assert out["result"]["writeResults"] == [{"qid": "r0", "outcome": "filled"}]


def test_rules_only_never_reaches_the_api_and_residues_the_remainder(tmp_path):
    """`aiAssist: false` is a mode, not a preference: nothing is asked, so the
    residue is everything the rules could not answer rather than a shorter
    list that would read as a better result."""
    out = _run_guided(
        tmp_path,
        questions=_open_questions(3),
        retryables=[{"qid": "r0", "label": "Country", "kind": "combobox",
                     "known_value": "United States"}],
        options={"aiAssist": False},
    )

    assert out["apiCalls"] == []
    assert out["rulePassRuns"] == 1
    assert {row["qid"] for row in out["result"]["residue"]} == {"q0", "q1", "q2"}
    assert [pair["qid"] for pair in _writes(out)[0]["pairs"]] == ["r0"]


def test_identity_data_never_reaches_choose(tmp_path):
    """R1's first honesty rule. The retryables lane carries a value a rule
    already knows — a country, a phone number, a name — and it goes straight to
    the writer. The assertion is over the RAW request bodies, not over a field
    list, because the way this breaks is a retryable folded into the choose set
    somewhere upstream and serialized along with everything else."""
    out = _run_guided(
        tmp_path,
        questions=_open_questions(2),
        retryables=[{"qid": "r0", "label": "Country of residence",
                     "kind": "combobox", "known_value": "United States"}],
    )

    posted = json.dumps(out["apiCalls"])
    assert "Country of residence" not in posted
    assert "United States" not in posted
    assert "r0" not in posted
    # …and it was still written, first, without costing a model call.
    assert [pair["qid"] for pair in _writes(out)[0]["pairs"]] == ["r0", "q0", "q1"]


def test_a_write_that_did_not_stick_is_residue_and_is_never_rewritten(tmp_path):
    """The retry bound. ONE `guided_write` per stage run, always: the single
    bounded retry of a control that would not take the value is the engine's
    (`content/autofill.js`, alternate gesture order, outcome `retry_filled`),
    and a second write from the runner would be a second retry on a form the
    user is watching. `not_stuck` is residue instead."""
    out = _run_guided(
        tmp_path,
        questions=_open_questions(2),
        writeOutcomes={"q1": "not_stuck"},
    )

    assert len(_writes(out)) == 1
    assert {row["qid"] for row in out["result"]["residue"]} == {"q1"}


def test_a_pair_the_writer_never_reported_back_is_residue(tmp_path):
    """The honesty loop nothing else reaches: silence about a field is not
    success.

    The engine answers per pair, but a control that left the DOM with its stage
    between the collect and the write is simply absent from the results — no
    outcome, not even `not_stuck`. Counting only what came back would drop it
    from both lists and tell the user a field nobody wrote is done."""
    out = _run_guided(
        tmp_path, questions=_open_questions(3), dropWrites=["q1"])

    assert [row["qid"] for row in out["result"]["writeResults"]] == ["q0", "q2"]
    assert {row["qid"] for row in out["result"]["residue"]} == {"q1"}


def test_the_essay_queue_is_handed_over_before_the_model_is_asked(tmp_path):
    """Both `onProgress` phases, in the order the card used to assign them.

    The essays go out BEFORE /choose on purpose: they are the caller's queue
    already, and a page that stops answering between the collect and the write
    must not take them back with it."""
    out = _run_guided(
        tmp_path,
        questions=[
            {"qid": "e0", "label": "Why do you want this role?",
             "kind": "textarea", "options": []},
            *_open_questions(1),
        ],
        reachNobody=False,
    )

    assert [update["phase"] for update in out["progress"]] == ["essays", "residue"]
    assert [q["qid"] for q in out["progress"][0]["essays"]] == ["e0"]
    assert out["progress"][0]["essays"] == out["result"]["essays"]
    # The essay never becomes a ChooseField, and never becomes residue either:
    # it is on the /api/qa path, which is a different feature.
    assert "e0" not in json.dumps(out["apiCalls"])
    assert out["result"]["residue"] == []


def test_a_page_that_answers_nothing_stops_the_run(tmp_path):
    """The finding/unreached split, at the runner's own boundary: no frame
    answered the collect, so nothing downstream may claim anything about this
    page — not a residue list, and not an empty one."""
    out = _run_guided(tmp_path, questions=_open_questions(2), reachNobody=True)

    assert out["threw"].startswith("Can't reach this page.")
    assert out["apiCalls"] == []
    assert _writes(out) == []


def test_telemetry_is_one_batch_of_values_free_observations(tmp_path):
    """The runner is where the batch is assembled, so this is where a value
    could be folded into it. The abstains and the write outcomes both land in
    ONE `rest_fill` batch, and every key in it is on the wire contract.

    The host is the FRAME's, and this is where that is pinned: the runner takes
    no host of its own (see the runner's note on why a run-level one would have
    no reachable effect), so the only way `acme.wd5…` can appear below is the
    per-row stamp `collectFromPage` takes off the frame that answered. The
    ambient `location.hostname` in this harness is `jobs.example.test` — the
    value an embedded Greenhouse form would be misattributed to — and it must
    not show up.
    """
    out = _run_guided(
        tmp_path,
        questions=_open_questions(2),
        abstainAll=True,
        host="acme.wd5.myworkdayjobs.com",
    )

    assert [batch["action"] for batch in out["telemetry"]] == ["rest_fill"]
    observations = out["telemetry"][0]["observations"]
    assert {obs["outcome"] for obs in observations} == {"ai_abstained"}
    for obs in observations:
        assert set(obs) <= _OBS_KEYS
        assert obs["host"] == "acme.wd5.myworkdayjobs.com"
    assert "jobs.example.test" not in json.dumps(observations)


@pytest.mark.parametrize("missing", ["broadcast", "api", "onProgress"])
def test_a_missing_required_dep_names_itself(tmp_path, missing):
    """Whose bug it is, said out loud.

    A forgotten dep's natural failure is a TypeError several awaits in — after
    the rule pass has written half a form — and the widget renders any throw
    from here as a note about the PAGE. So the guard runs before anything else
    and names the dep. `api` is on the list even though `aiAssist: false` never
    calls it: the mode is per run, and a caller that cannot ask has not chosen
    rules-only, it is unfinished.
    """
    out = _run_guided(tmp_path, questions=_open_questions(1), omitDep=missing)

    assert out["threw"] == f"guided-run: missing dep {missing}"
    assert out["rulePassRuns"] == 0, "the guard ran after the rule pass"
    assert out["sent"] == [] and out["apiCalls"] == []


def test_a_rule_pass_that_throws_does_not_stop_the_guided_pass(tmp_path):
    """No profile, or a page the rules do not cover, is not the end of the run:
    the remainder path is the primary fill on a rule-sparse form."""
    out = _run_guided(
        tmp_path, questions=_open_questions(1), rulePassThrows=True)

    assert out["threw"] is None
    assert out["rulePassRuns"] == 1
    assert len(out["apiCalls"]) == 1
