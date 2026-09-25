"""The loop's decisions (shared/fill-loop.js), with the page and the backend
scripted: every page message and every backend call is answered by the spec,
and recorded so a test can pin what the loop SENT."""

import re
from pathlib import Path

import pytest

from app.schemas.autofill_choose import ChooseRequest
from app.schemas.autofill_fill import MapRequest, PickRequest, StepRequest
from tests.browser.conftest import EXTENSION

# Every body the loop POSTs must be one the real endpoint accepts.
MODELS = {"/api/autofill/map": MapRequest, "/api/autofill/pick": PickRequest,
          "/api/autofill/step": StepRequest, "/api/autofill/choose": ChooseRequest}

LOOP_SOURCES = ["shared/policy.js", "shared/choose.js", "shared/guided-run.js", "shared/fill-loop.js"]
# The backend's own patterns (app/schemas/autofill_fill.py), restated so a
# history entry the loop builds is checked against what /step accepts.
HISTORY_ENTRY = re.compile(
    r"^(click:o\d+|search:value|search:word:\d|open|scroll|close|give_up|choose) -> [a-z_]+( \([a-z_]+\))?$")
GIVE_UP = {"mid": "give_up", "describe": "stop"}

DRIVER = """async (spec) => {
  const calls = [];
  const sent = [];
  const posts = [];
  const progress = [];
  const inflight = {};
  const peak = {};
  let round = 0;
  let stop = false;
  const one = (result) => [{frameId: 0, result}];
  // A scripted answer may be a list: one entry per call, the last one repeating.
  const take = (v) => (Array.isArray(v) ? (v.length > 1 ? v.shift() : v[0]) : v);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  Object.assign(window.careerStudioCompanion.fillLoop.limits, {TAIL_MS: 0}, spec.limits ?? {});
  const broadcast = async (msg) => {
    calls.push(msg.type);
    sent.push(JSON.parse(JSON.stringify(msg)));
    if (msg.type === "fill_inventory") {
      round += 1;
      const fields = spec.frames[Math.min(round, spec.frames.length) - 1];
      // null: the page no longer answers (a frame that went away).
      return fields === null ? [{frameId: 0, error: "gone"}] : one({frame: "f", host: "x.test", fields});
    }
    if (msg.type === "fill_explore") return one(Object.fromEntries(msg.requests.map(r => [r.fid, take(spec.explore[r.term ?? r.fid]) ?? {options: [], complete: false, error: "no_popup"}])));
    if (msg.type === "fill_apply" && spec.stopAfterApply) stop = true;
    if (msg.type === "fill_apply") return one(msg.actions.map(a => {
      const key = a.op === "move" ? a.mid : (a.text ?? a.value ?? (a.texts || []).join("+") ?? a.fid);
      return {fid: a.fid, committed: a.text ?? a.value ?? a.texts ?? null, ...(take(spec.apply[key]) ?? {outcome: a.op === "move" && a.mid === "give_up" ? "closed" : "verified"})};
    }));
    if (msg.type === "fill_step_state") {
      const s = spec.step.states.shift() ?? {candidates: [{mid: "give_up", describe: "stop"}]};
      return [{frameId: 1, result: null}, {frameId: 0, result: {version: 1, complete: false, ...s}}];
    }
    if (msg.type === "fill_sweep") return one(take(spec.sweep) ?? []);
    return [];
  };
  const api = async (path, init) => {
    const body = init?.body ? JSON.parse(init.body) : null;
    calls.push(path.split("?")[0]);
    posts.push({path, body});
    inflight[path] = (inflight[path] ?? 0) + 1;
    peak[path] = Math.max(peak[path] ?? 0, inflight[path]);
    if (spec.apiDelay?.[path]) await sleep(spec.apiDelay[path]);
    inflight[path] -= 1;
    if (spec.apiHang?.includes(path)) return new Promise(() => {});
    if (path.startsWith("/api/autofill/context")) return {eeo_consent: {consent_forms: false}};
    if (path === "/api/autofill/map") return {fields: Object.fromEntries(body.fields.map(f => [f.fid, spec.map[`${f.fid}:${f.question}`] ?? spec.map[f.fid] ?? {route: "none"}]))};
    if (path === "/api/autofill/pick") return {picks: Object.fromEntries(body.fields.map(f => [f.fid, spec.pick[`${f.fid}:${f.item ?? ""}`] ?? spec.pick[f.fid] ?? {oids: [], reason: "abstained"}]))};
    if (path === "/api/autofill/step") return spec.step.moves.shift() ?? {mid: null, reason: "abstained"};
    if (path === "/api/autofill/choose") return {choices: Object.fromEntries(body.fields.map(f => [f.qid, spec.choose[f.qid] ?? {answer: null, reason: "abstained"}]))};
    throw Object.assign(new Error(path), {status: 502});
  };
  let budget = spec.stopAfter ?? Infinity;
  const t0 = Date.now();
  const report = await window.careerStudioCompanion.fillLoop.runFill(
    {broadcast, api, cancelled: () => stop || (budget -= 1) < 0, onProgress: (u) => progress.push(u)},
    spec.options ?? {sourceHint: null});
  return {report, calls, sent, posts, progress, peak, ms: Date.now() - t0};
}"""


def run(page, load, **spec):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    spec = {"frames": [[]], "explore": {}, "apply": {}, "map": {}, "pick": {}, "choose": {},
            "step": {"states": [], "moves": []}} | spec
    out = page.evaluate(DRIVER, spec)
    for post in out["posts"]:
        if post["path"] in MODELS:
            MODELS[post["path"]].model_validate(post["body"])
    return out


def f(fid, shape="text", question="Q", **kw):
    return {"fid": fid, "fp": f"fp-{fid}", "shape": shape, "kind": "text" if shape in ("text", "date") else "choice",
            "multi": False, "question": question, "section": "", "repeatIndex": 0, "required": False,
            "committed": "", "answered": False, "options": None, "optionsComplete": False, "invalid": False,
            "touched": False, "policyBlocked": False} | kw


def opt(oid, text, blocked=False):
    return {"oid": oid, "text": text, "selected": False, "policyBlocked": blocked}


def statuses(out):
    return {r["fid"]: r["status"] for r in out["report"]["fields"]}


def row(out, fid):
    return next(r for r in out["report"]["fields"] if r["fid"] == fid)


def actions(out, op=None):
    got = [a for m in out["sent"] if m["type"] == "fill_apply" for a in m["actions"]]
    return [a for a in got if op is None or a["op"] == op]


def bodies(out, path):
    return [p["body"] for p in out["posts"] if p["path"] == path]


# ---------- the plan's cases


def test_a_text_slot_is_typed_and_verified(page, load):
    out = run(page, load, frames=[[f("a", question="City")]], map={"a": {"route": "slot", "slot": "personal.city", "value": "Springfield"}})
    assert statuses(out) == {"a": "verified"}
    assert row(out, "a")["answer"] == "Springfield"


def test_a_closed_dropdown_is_explored_before_it_is_picked(page, load):
    out = run(page, load, frames=[[f("d", "popup")]],
              map={"d": {"route": "slot", "slot": "work_auth.authorized_now", "value": "Yes"}},
              explore={"d": {"options": [opt("o1", "Yes"), opt("o2", "No")], "complete": True}},
              pick={"d": {"oids": ["o1"], "reason": "matched"}})
    assert statuses(out) == {"d": "verified"}
    assert out["calls"].index("fill_explore") < out["calls"].index("/api/autofill/pick")
    [pick] = bodies(out, "/api/autofill/pick")
    [field] = pick["fields"]
    assert field["complete"] is True and "item" not in field
    assert field["options"] == [{"oid": "o1", "text": "Yes"}, {"oid": "o2", "text": "No"}]


def test_an_unexpected_commit_hands_over_to_the_adaptive_step(page, load):
    out = run(page, load, frames=[[f("h", "popup", "How did you hear?")]],
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              explore={"h": {"options": [opt("o1", "Job Board")], "complete": True}},
              pick={"h": {"oids": ["o1"], "reason": "matched"}},
              apply={"Job Board": {"outcome": "unexpected", "reason": "new_options"}, "click:o1": {"outcome": "verified"}},
              step={"states": [{"candidates": [{"mid": "click:o1", "describe": 'Click the option "LinkedIn"'}, GIVE_UP]}],
                    "moves": [{"mid": "click:o1", "reason": "matched"}]})
    assert statuses(out) == {"h": "verified"}
    [step] = bodies(out, "/api/autofill/step")
    assert step["history"] == ["choose -> unexpected (new_options)"]
    assert "item" not in step and step["route"] == "slot" and step["slot"] == "preferences.how_heard"
    [move] = actions(out, "move")
    # Only fid, fp, op, mid, version — and no `as` on an answer click.
    assert move == {"fid": "h", "fp": "fp-h", "op": "move", "mid": "click:o1", "version": 1}


def test_no_options_goes_straight_to_the_adaptive_step_and_give_up_is_honest(page, load):
    out = run(page, load, frames=[[f("x", "popup")]],
              map={"x": {"route": "slot", "slot": "education.0.discipline", "value": "Business Analytics"}})
    assert statuses(out) == {"x": "needs_answer"}
    assert out["calls"].count("fill_step_state") == 1
    assert [a["mid"] for a in actions(out, "move")] == ["give_up"]  # the give_up close
    # Nothing but give_up on offer: no model is asked.
    assert "/api/autofill/step" not in out["calls"]


def test_an_honest_abstain_on_a_popup_hands_over_to_the_adaptive_step(page, load):
    out = run(page, load, frames=[[f("h", "popup", "How did you hear?")]],
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              explore={"h": {"options": [opt("o1", "Job Board"), opt("o2", "Social Media")], "complete": True}},
              pick={"h": {"oids": [], "reason": "abstained"}},
              apply={"click:o1": {"outcome": "progressed"}, "click:o2": {"outcome": "verified"}},
              step={"states": [{"version": 1, "complete": True, "candidates": [{"mid": "click:o1", "describe": 'Click the option "Job Board"'}]},
                               {"version": 2, "complete": True, "candidates": [{"mid": "click:o2", "describe": 'Click the option "LinkedIn"'}]}],
                    "moves": [{"mid": "click:o1", "reason": "matched"}, {"mid": "click:o2", "reason": "matched"}]})
    assert statuses(out) == {"h": "verified"}
    # An answer click that progressed (an unmarked category) re-takes the state.
    assert [(a["mid"], a["version"]) for a in actions(out, "move")] == [("click:o1", 1), ("click:o2", 2)]
    steps = bodies(out, "/api/autofill/step")
    assert [s["history"] for s in steps] == [["choose -> abstained"], ["choose -> abstained", "click:o1 -> progressed"]]
    assert all(s["complete"] is True for s in steps)


def test_an_existing_chip_does_not_stop_missing_items_being_added(page, load):
    out = run(page, load, frames=[[f("k", "search", "Skills", multi=True, committed=["SQL"], answered=False)]],
              map={"k": {"route": "slot", "slot": "skills", "value": ["SQL", "Python"]}},
              explore={"SQL": {"options": [opt("o1", "SQL")]}, "Python": {"options": [opt("o1", "Python")]}},
              pick={"k:SQL": {"oids": ["o1"], "reason": "matched"}, "k:Python": {"oids": ["o1"], "reason": "matched"}},
              apply={"SQL+Python": {"outcome": "verified", "added": ["Python"], "missing": []}})
    assert statuses(out) == {"k": "verified"}


def test_eleven_skills_with_ten_added_is_partial_not_verified(page, load):
    skills = [f"S{i}" for i in range(11)]
    out = run(page, load, frames=[[f("k", "search", "Skills", multi=True)]],
              map={"k": {"route": "slot", "slot": "skills", "value": skills}},
              explore={s: {"options": [opt("o1", s)]} for s in skills},
              pick={f"k:{s}": {"oids": ["o1"], "reason": "matched"} for s in skills},
              apply={"+".join(skills[:10]): {"outcome": "verified", "added": skills[:10], "missing": []}})
    [r] = out["report"]["fields"]
    assert (r["status"], r["answer"]) == ("partial", "10 of 11 added")
    [s] = actions(out, "set")
    assert s["texts"] == skills[:10] and s["terms"] == skills[:10]


def test_an_unchecked_lone_checkbox_is_not_already_answered(page, load):
    out = run(page, load, frames=[[f("c", "group", "I agree to relocate", committed="No", answered=False,
                                      options=[opt("yes", "Yes"), opt("no", "No")], optionsComplete=True)]],
              map={"c": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "Yes"}},
              pick={"c": {"oids": ["yes"], "reason": "matched"}})
    assert statuses(out) == {"c": "verified"}
    assert "fill_explore" not in out["calls"]  # a complete passive list is not explored again


def test_a_user_edit_during_the_model_call_is_respected(page, load):
    out = run(page, load, frames=[[f("a", question="City")]] * 3,
              map={"a": {"route": "slot", "slot": "personal.city", "value": "X"}}, apply={"X": {"outcome": "yours"}})
    assert statuses(out) == {"a": "yours"}
    assert len(actions(out)) == 1  # a refusal is final: never retried


def test_a_late_reversion_found_by_the_tail_sweep_is_retried(page, load):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    got = page.evaluate("""async () => {
      window.careerStudioCompanion.fillLoop.limits.TAIL_MS = 30;
      let sweeps = 0, writes = 0;
      const field = {fid: "a", fp: "p", shape: "text", kind: "text", question: "City", options: null, committed: "", answered: false};
      const broadcast = async (m) => {
        if (m.type === "fill_inventory") return [{frameId: 0, result: {frame: "f", host: "x", fields: [field]}}];
        if (m.type === "fill_apply") { writes += 1; return [{frameId: 0, result: [{fid: "a", outcome: "verified", committed: "X"}]}]; }
        if (m.type === "fill_sweep") { sweeps += 1; return [{frameId: 0, result: sweeps === 2 ? [{fid: "a", outcome: "reverted"}] : []}]; }
        return [{frameId: 0, result: []}];
      };
      const api = async (p, init) => p.startsWith("/api/autofill/context") ? {}
        : {fields: {a: {route: "slot", slot: "personal.city", value: "X"}}};
      const report = await window.careerStudioCompanion.fillLoop.runFill({broadcast, api}, {});
      return {writes, sweeps, status: report.fields[0].status};
    }""")
    assert (got["writes"], got["status"]) == (2, "verified")
    assert got["sweeps"] >= 3  # the tail sweep after the re-write found nothing more


def test_the_tail_sweep_runs_even_when_the_rounds_run_out(page, load):
    out = run(page, load, frames=[[f("a", question="City")]], limits={"MAX_ROUNDS": 1},
              map={"a": {"route": "slot", "slot": "personal.city", "value": "X"}},
              sweep=[[], [{"fid": "a", "outcome": "reverted"}]])
    assert (row(out, "a")["status"], row(out, "a")["lastOutcome"]) == ("cannot_operate", "reverted")
    assert out["calls"].count("fill_sweep") == 2


def test_phone_slots_are_written_with_the_phone_format(page, load):
    out = run(page, load, frames=[[f("p", question="Phone"), f("c", question="City")]],
              map={"p": {"route": "slot", "slot": "personal.phone", "value": "5550100000"},
                   "c": {"route": "slot", "slot": "personal.city", "value": "Springfield"}})
    assert statuses(out) == {"p": "verified", "c": "verified"}
    writes = {a["fid"]: a for a in actions(out, "write")}
    assert writes["p"]["format"] == "phone" and "format" not in writes["c"]


def test_unknown_controls_are_listed_as_could_not_operate(page, load):
    out = run(page, load, frames=[[f("u", "unknown", "Rate your SQL", kind="unknown")]])
    assert statuses(out) == {"u": "cannot_operate"}
    assert "/api/autofill/map" not in out["calls"]


def test_a_search_set_adds_each_item_and_partial_is_not_verified(page, load):
    out = run(page, load, frames=[[f("k", "search", "Skills", multi=True)]],
              map={"k": {"route": "slot", "slot": "skills", "value": ["Python", "Rust"]}},
              explore={"Python": {"options": [opt("o1", "Python")], "complete": False},
                       "Rust": {"options": [opt("o1", "Rust (language)")], "complete": False}},
              pick={"k:Python": {"oids": ["o1"], "reason": "matched"}},
              apply={"Python": {"outcome": "partial", "added": ["Python"], "missing": []}})
    [r] = out["report"]["fields"]
    assert r["status"] == "partial" and r["answer"] == "1 of 2 added"
    picks = [b["fields"][0] for b in bodies(out, "/api/autofill/pick")]
    assert [(p["item"], p["complete"]) for p in picks] == [("Python", False), ("Rust", False)]


def test_prose_goes_to_choose_and_an_abstain_is_left_for_the_user(page, load):
    out = run(page, load, frames=[[f("w", question="Why us?"), f("x", question="Tell us a secret")]],
              map={"w": {"route": "free_text"}, "x": {"route": "free_text"}},
              choose={"w": {"answer": "Because.", "reason": "matched"}})
    assert statuses(out) == {"w": "verified", "x": "needs_answer"}


def test_a_field_that_keeps_reverting_is_given_up_after_three_attempts(page, load):
    out = run(page, load, frames=[[f("a")]] * 5, map={"a": {"route": "slot", "slot": "personal.city", "value": "X"}},
              apply={"X": {"outcome": "reverted"}})
    assert statuses(out) == {"a": "cannot_operate"}
    assert len(actions(out, "write")) == 3
    assert row(out, "a")["lastOutcome"] == "reverted"


def test_blocked_touched_and_prefilled_fields_are_never_sent(page, load):
    out = run(page, load, frames=[[f("p", question="Signature", policyBlocked=True), f("t", touched=True),
                                   f("v", committed="Springfield", answered=True)]])
    assert statuses(out) == {"p": "blocked", "t": "yours", "v": "already"}
    assert "/api/autofill/map" not in out["calls"]


def test_a_value_that_is_not_an_answer_is_not_already(page, load):
    # `answered`, not "has a value", decides: a select sitting on its first option.
    out = run(page, load, frames=[[f("s", "select", "Country", committed="Select…", answered=False,
                                      options=[opt("o1", "Select…"), opt("o2", "United States")], optionsComplete=True)]],
              map={"s": {"route": "slot", "slot": "personal.country", "value": "United States"}},
              pick={"s": {"oids": ["o2"], "reason": "matched"}})
    assert statuses(out) == {"s": "verified"}


def test_a_field_that_appears_after_an_answer_is_filled_next_round(page, load):
    first = [f("a", question="Country")]
    out = run(page, load, frames=[first, first + [f("b", question="State")], first + [f("b", question="State")]],
              map={"a": {"route": "slot", "slot": "personal.country", "value": "US"},
                   "b": {"route": "slot", "slot": "personal.state", "value": "TX"}})
    assert statuses(out) == {"a": "verified", "b": "verified"}
    assert out["calls"].count("/api/autofill/map") == 2  # a field is mapped once


def test_an_unreachable_ai_guesses_nothing(page, load):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    got = page.evaluate("""async () => {
      window.careerStudioCompanion.fillLoop.limits.TAIL_MS = 0;
      const broadcast = async (m) => m.type === "fill_inventory"
        ? [{frameId: 0, result: {frame: "f", host: "x", fields: [{fid: "a", fp: "p", shape: "text", kind: "text", question: "City", options: null, committed: ""}]}}]
        : [{frameId: 0, result: []}];
      const api = async (p) => { if (p.startsWith("/api/autofill/context")) return {}; throw Object.assign(new Error("down"), {status: 502}); };
      return window.careerStudioCompanion.fillLoop.runFill({broadcast, api}, {});
    }""")
    assert [r["status"] for r in got["fields"]] == ["needs_answer"] and got["aiFailure"]


def test_source_hint_survives_a_malformed_query(page, load):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    hint = page.evaluate("(u) => window.careerStudioCompanion.fillLoop.sourceHintOf(u)",
                         "https://x.test/apply?source=REC_LINKEDIN?utm_source=y")
    assert hint == "rec_linkedin"


# ---------- the contracts Tasks 4–6 settled


def test_no_page_reached_is_the_shown_sentence(page, load):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    got = page.evaluate("""async () => {
      const ns = window.careerStudioCompanion;
      try {
        await ns.fillLoop.runFill({broadcast: async () => [{frameId: 0, error: "no receiver"}], api: async () => ({})}, {});
        return null;
      } catch (err) { return {shown: err.shown === true, same: err.message === ns.guidedRun.NO_FRAME_REACHED}; }
    }""")
    assert got == {"shown": True, "same": True}


def test_one_run_id_for_every_inventory_of_a_run_and_a_new_one_per_run(page, load):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    got = page.evaluate("""async () => {
      const ns = window.careerStudioCompanion;
      ns.fillLoop.limits.TAIL_MS = 0;
      const ids = [];
      const broadcast = async (m) => {
        if (m.type === "fill_inventory") { ids.push([m.runId, m.consentForms]); return [{frameId: 0, result: {frame: "f", host: "x", fields: []}}]; }
        return [{frameId: 0, result: []}];
      };
      const api = async () => ({eeo_consent: {consent_forms: true}});
      await ns.fillLoop.runFill({broadcast, api}, {});
      const first = ids.length;
      await ns.fillLoop.runFill({broadcast, api}, {});
      return {ids, first};
    }""")
    ids, first = got["ids"], got["first"]
    assert first >= 1 and len({i for i, _ in ids[:first]}) == 1 and all(c is True for _, c in ids)
    assert ids[0][0] != ids[-1][0] and isinstance(ids[0][0], str) and ids[0][0]


def test_a_progress_click_is_sent_as_progress_and_an_answer_click_is_not(page, load):
    out = run(page, load, frames=[[f("h", "popup", "How did you hear?")]],
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              explore={"h": {"options": [opt("o1", "Job Board")], "complete": True}},
              pick={"h": {"oids": [], "reason": "abstained"}},
              apply={"click:o1": [{"outcome": "progressed"}, {"outcome": "verified"}], "scroll": {"outcome": "progressed"}},
              step={"states": [{"version": 4, "candidates": [{"mid": "click:o1", "describe": 'Open the group "Job Board"'}, GIVE_UP]},
                               {"version": 5, "candidates": [{"mid": "scroll", "describe": "Scroll"}, GIVE_UP]},
                               {"version": 6, "candidates": [{"mid": "click:o1", "describe": 'Click the option "LinkedIn"'}, GIVE_UP]}],
                    "moves": [{"mid": "click:o1", "reason": "progress"}, {"mid": "scroll", "reason": "progress"},
                              {"mid": "click:o1", "reason": "matched"}]})
    assert statuses(out) == {"h": "verified"}
    moves = actions(out, "move")
    assert [(m["mid"], m["version"], m.get("as")) for m in moves] == [
        ("click:o1", 4, "progress"), ("scroll", 5, None), ("click:o1", 6, None)]


def test_a_group_that_committed_a_value_is_left_for_the_user_to_check(page, load):
    out = run(page, load, frames=[[f("h", "popup", "How did you hear?")]] * 3,
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              explore={"h": {"options": [opt("o1", "Job Board")], "complete": True}},
              pick={"h": {"oids": [], "reason": "abstained"}},
              apply={"click:o1": {"outcome": "unexpected", "reason": "group_committed"}},
              step={"states": [{"candidates": [{"mid": "click:o1", "describe": 'Open the group "Job \\"Board\\""'}, GIVE_UP]}],
                    "moves": [{"mid": "click:o1", "reason": "progress"}]})
    r = row(out, "h")
    assert (r["status"], r["answer"]) == ("needs_answer", 'Companion clicked "Job "Board"" — check it')
    assert r["lastOutcome"] == "group_committed"
    assert [m["mid"] for m in actions(out, "move")] == ["click:o1"]  # not re-tried, not given up over it


def test_not_a_group_re_takes_the_state_and_steps_again(page, load):
    out = run(page, load, frames=[[f("h", "popup", "How did you hear?")]],
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              explore={"h": {"options": [opt("o1", "Job Board")], "complete": True}},
              pick={"h": {"oids": [], "reason": "abstained"}},
              apply={"click:o1": [{"outcome": "unexpected", "reason": "not_a_group"}, {"outcome": "verified"}]},
              step={"states": [{"version": 1, "candidates": [{"mid": "click:o1", "describe": 'Open the group "LinkedIn"'}]},
                               {"version": 2, "candidates": [{"mid": "click:o1", "describe": 'Click the option "LinkedIn"'}]}],
                    "moves": [{"mid": "click:o1", "reason": "progress"}, {"mid": "click:o1", "reason": "matched"}]})
    assert statuses(out) == {"h": "verified"}
    assert out["calls"].count("fill_step_state") == 2
    assert bodies(out, "/api/autofill/step")[1]["history"][-1] == "click:o1 -> unexpected (not_a_group)"


def test_a_stale_move_re_takes_the_state(page, load):
    out = run(page, load, frames=[[f("h", "popup")]],
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              explore={"h": {"options": [opt("o1", "Job Board")], "complete": True}},
              pick={"h": {"oids": [], "reason": "abstained"}},
              apply={"click:o1": [{"outcome": "stale"}, {"outcome": "verified"}]},
              step={"states": [{"version": 1, "candidates": [{"mid": "click:o1", "describe": 'Click the option "LinkedIn"'}]},
                               {"version": 2, "candidates": [{"mid": "click:o1", "describe": 'Click the option "LinkedIn"'}]}],
                    "moves": [{"mid": "click:o1", "reason": "matched"}, {"mid": "click:o1", "reason": "matched"}]})
    assert statuses(out) == {"h": "verified"}
    assert [m["version"] for m in actions(out, "move")] == [1, 2]


def test_a_step_state_the_page_refuses_as_stale_goes_back_to_the_inventory(page, load):
    out = run(page, load, frames=[[f("h", "popup")]] * 4,
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              explore={"h": [{"options": [], "complete": False, "error": "empty_popup"},
                             {"options": [opt("o1", "LinkedIn")], "complete": True}]},
              pick={"h": {"oids": ["o1"], "reason": "matched"}},
              step={"states": [{"error": "stale", "version": None, "candidates": []}], "moves": []})
    assert statuses(out) == {"h": "verified"}
    assert out["calls"].count("fill_inventory") >= 2 and "/api/autofill/step" not in out["calls"]
    # No give_up for a state that never existed.
    assert [a["op"] for a in actions(out)] == ["choose"]


def test_a_step_state_refused_as_yours_is_final(page, load):
    out = run(page, load, frames=[[f("h", "popup")]] * 3,
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              step={"states": [{"error": "yours", "version": None, "candidates": []}], "moves": []})
    assert statuses(out) == {"h": "yours"}
    assert out["calls"].count("fill_step_state") == 1


def test_history_is_built_from_move_ids_and_outcomes_and_keeps_the_last_eight(page, load):
    n = 11
    states = [{"version": i, "candidates": [{"mid": "scroll", "describe": "Scroll"}, GIVE_UP]} for i in range(n)]
    out = run(page, load, frames=[[f("h", "popup", "Where did you hear about this very long question? " * 8)]],
              limits={"MAX_STEPS": n},
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              explore={"h": {"options": [], "complete": False, "error": "empty_popup"}},
              apply={"scroll": [{"outcome": "progressed"}] * 3 + [{"outcome": "unexpected", "reason": "list_end"}]},
              step={"states": states, "moves": [{"mid": "scroll", "reason": "progress"}] * n})
    steps = bodies(out, "/api/autofill/step")
    assert len(steps) == n
    assert steps[0]["history"] == ["open -> unexpected (empty_popup)"]
    assert all(len(s["history"]) <= 8 for s in steps)
    assert steps[-1]["history"][-1] == "scroll -> unexpected (list_end)" and len(steps[-1]["history"]) == 8
    for s in steps:
        for e in s["history"]:
            assert HISTORY_ENTRY.match(e) and len(e) <= 80, e
    assert row(out, "h")["status"] == "cannot_operate"  # the step budget ran out
    assert actions(out, "move")[-1]["mid"] == "give_up"


def test_a_native_set_is_picked_per_source_item_and_never_offers_a_blocked_option(page, load):
    options = [opt("o1", "SQL"), opt("o2", "Python"), opt("o3", "Password manager", blocked=True)]
    out = run(page, load, frames=[[f("k", "select", "Skills", multi=True, options=options, optionsComplete=True)]],
              map={"k": {"route": "slot", "slot": "skills", "value": ["SQL", "Go"]}},
              pick={"k:SQL": {"oids": ["o1"], "reason": "matched"}},
              apply={"SQL": {"outcome": "verified", "added": ["SQL"], "missing": []}})
    assert (row(out, "k")["status"], row(out, "k")["answer"]) == ("partial", "1 of 2 added")
    picks = [b["fields"][0] for b in bodies(out, "/api/autofill/pick")]
    assert sorted(p["item"] for p in picks) == ["Go", "SQL"]
    for p in picks:
        assert [o["oid"] for o in p["options"]] == ["o1", "o2"]
        assert p["complete"] is False  # a list with a hidden option is not a complete view
    [s] = actions(out, "set")
    assert s["texts"] == ["SQL"] and "terms" not in s  # terms are search queries, for search sets only


def test_blocked_set_items_are_reported_apart_from_the_missing_ones(page, load):
    out = run(page, load, frames=[[f("k", "search", "Skills", multi=True)]],
              map={"k": {"route": "slot", "slot": "skills", "value": ["Python", "Rust", "Go"]}},
              explore={"Python": {"options": [opt("o1", "Python")]},
                       "Rust": {"options": [opt("o1", "Rust")]},
                       "Go": {"options": [opt("o1", "Go signature", blocked=True)]}},
              pick={"k:Python": {"oids": ["o1"], "reason": "matched"}, "k:Rust": {"oids": ["o1"], "reason": "matched"}},
              apply={"Python+Rust": {"outcome": "partial", "added": ["Python"], "missing": [], "blocked": ["Rust"]}})
    r = row(out, "k")
    assert (r["status"], r["answer"]) == ("partial", "1 of 3 added · 2 left to you by policy")
    assert all(o["text"] != "Go signature" for b in bodies(out, "/api/autofill/pick") for o in b["fields"][0]["options"])
    assert len(bodies(out, "/api/autofill/pick")) == 2


def test_a_set_item_the_generic_path_missed_gets_the_adaptive_step_with_its_item(page, load):
    out = run(page, load, frames=[[f("k", "search", "Skills", multi=True)]],
              map={"k": {"route": "slot", "slot": "skills", "value": ["Python"]}},
              explore={"Python": {"options": [], "complete": False, "error": "empty_popup"}},
              apply={"search:value": {"outcome": "progressed"}, "click:o1": {"outcome": "verified"}},
              step={"states": [{"candidates": [{"mid": "search:value", "describe": "Type"}, GIVE_UP]},
                               {"candidates": [{"mid": "click:o1", "describe": 'Click the option "Python"'}, GIVE_UP]}],
                    "moves": [{"mid": "search:value", "reason": "progress"}, {"mid": "click:o1", "reason": "matched"}]})
    assert statuses(out) == {"k": "verified"}
    assert [s["item"] for s in bodies(out, "/api/autofill/step")] == ["Python", "Python"]
    states = [m for m in out["sent"] if m["type"] == "fill_step_state"]
    assert [s["value"] for s in states] == ["Python", "Python"]


def test_an_explore_refusal_is_final(page, load):
    out = run(page, load, frames=[[f("d", "popup")]] * 3,
              map={"d": {"route": "slot", "slot": "work_auth.authorized_now", "value": "Yes"}},
              explore={"d": {"options": [], "complete": False, "error": "unsupported"}})
    assert statuses(out) == {"d": "cannot_operate"}
    assert out["calls"].count("fill_explore") == 1 and not actions(out)


def test_a_sweep_about_a_field_the_engine_did_not_fill_is_ignored(page, load):
    out = run(page, load, frames=[[f("v", committed="x", answered=True)]] * 3,
              sweep=[{"fid": "v", "outcome": "reverted"}])
    assert statuses(out) == {"v": "already"}
    assert not actions(out)


# ---------- never stall


def test_a_model_call_that_hangs_is_bounded(page, load):
    out = run(page, load, frames=[[f("a", question="City")]], limits={"API_MS": 80},
              apiHang=["/api/autofill/map"])
    assert statuses(out) == {"a": "needs_answer"}
    assert out["report"]["aiFailure"]
    assert out["ms"] < 3000


def test_a_field_out_of_time_is_given_up_and_the_run_moves_on(page, load):
    states = [{"candidates": [{"mid": "scroll", "describe": "Scroll"}, GIVE_UP]} for _ in range(6)]
    out = run(page, load, frames=[[f("h", "popup"), f("c", question="City")]],
              limits={"FIELD_MS": 150},
              apiDelay={"/api/autofill/step": 60},
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"},
                   "c": {"route": "slot", "slot": "personal.city", "value": "Springfield"}},
              explore={"h": {"options": [], "complete": False, "error": "empty_popup"}},
              apply={"scroll": {"outcome": "progressed"}},
              step={"states": states, "moves": [{"mid": "scroll", "reason": "progress"}] * 6})
    assert statuses(out) == {"h": "cannot_operate", "c": "verified"}
    assert row(out, "h")["lastOutcome"] == "timeout"
    assert out["report"]["aiFailure"] is None  # a clock running out is not the AI failing
    assert actions(out, "move")[-1]["mid"] == "give_up"  # the popup it held is closed
    assert len(bodies(out, "/api/autofill/step")) < 6


def test_the_run_has_a_deadline(page, load):
    out = run(page, load, frames=[[f("a", question="City"), f("b", question="State")]],
              limits={"RUN_MS": 100}, apiDelay={"/api/autofill/map": 150},
              map={"a": {"route": "slot", "slot": "personal.city", "value": "X"},
                   "b": {"route": "slot", "slot": "personal.state", "value": "Y"}})
    assert out["report"]["timedOut"] is True
    assert out["report"]["aiFailure"] is None
    assert not actions(out)
    assert statuses(out) == {"a": "needs_answer", "b": "needs_answer"}
    # The panel can say "ran out of time" rather than "no answer".
    assert {r["lastOutcome"] for r in out["report"]["fields"]} == {"timeout"}


def test_the_run_running_out_mid_step_closes_the_popup_it_held(page, load):
    states = [{"candidates": [{"mid": "scroll", "describe": "Scroll"}, GIVE_UP]} for _ in range(8)]
    out = run(page, load, frames=[[f("h", "popup")]], limits={"RUN_MS": 250},
              apiDelay={"/api/autofill/step": 100},
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              explore={"h": {"options": [], "complete": False, "error": "empty_popup"}},
              apply={"scroll": {"outcome": "progressed"}},
              step={"states": states, "moves": [{"mid": "scroll", "reason": "progress"}] * 8})
    assert out["report"]["timedOut"] is True
    moves = [a["mid"] for a in actions(out, "move")]
    assert moves[0] == "scroll" and moves[-1] == "give_up"
    assert out["report"]["aiFailure"] is None


def test_a_stop_mid_step_sends_no_give_up(page, load):
    out = run(page, load, frames=[[f("h", "popup")]], stopAfterApply=True,
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              explore={"h": {"options": [], "complete": False, "error": "empty_popup"}},
              apply={"scroll": {"outcome": "progressed"}},
              step={"states": [{"candidates": [{"mid": "scroll", "describe": "Scroll"}, GIVE_UP]}] * 3,
                    "moves": [{"mid": "scroll", "reason": "progress"}] * 3})
    # The panel's fill_cancel closes what the engine held; the loop sends nothing more.
    assert [a["mid"] for a in actions(out, "move")] == ["scroll"]
    assert out["report"]["stopped"] is True


def test_native_set_picks_run_one_at_a_time(page, load):
    options = [opt(f"o{i}", t) for i, t in enumerate("ABCD")]
    out = run(page, load, frames=[[f("k", "select", "Skills", multi=True, options=options, optionsComplete=True)]],
              apiDelay={"/api/autofill/pick": 20},
              map={"k": {"route": "slot", "slot": "skills", "value": list("ABCD")}},
              pick={f"k:{t}": {"oids": [f"o{i}"], "reason": "matched"} for i, t in enumerate("ABCD")},
              apply={"A+B+C+D": {"outcome": "verified", "added": list("ABCD"), "missing": []}})
    assert statuses(out) == {"k": "verified"}
    assert out["peak"]["/api/autofill/pick"] == 1
    assert [b["fields"][0]["item"] for b in bodies(out, "/api/autofill/pick")] == list("ABCD")


def test_a_stop_between_native_set_items_stops_the_picks(page, load):
    options = [opt(f"o{i}", t) for i, t in enumerate("ABCD")]
    load(page, "<div></div>", sources=LOOP_SOURCES)
    got = page.evaluate("""async (options) => {
      const ns = window.careerStudioCompanion; ns.fillLoop.limits.TAIL_MS = 0;
      let stop = false, picks = 0, applies = 0;
      const field = {fid: "k", fp: "p", shape: "select", kind: "choice", multi: true, question: "Skills",
                     options, optionsComplete: true, committed: [], answered: false};
      const broadcast = async (m) => {
        if (m.type === "fill_inventory") return [{frameId: 0, result: {frame: "f", host: "x", fields: [field]}}];
        if (m.type === "fill_apply") applies += 1;
        return [{frameId: 0, result: []}];
      };
      const api = async (p, init) => {
        if (p.startsWith("/api/autofill/context")) return {};
        if (p === "/api/autofill/map") return {fields: {k: {route: "slot", slot: "skills", value: ["A", "B", "C", "D"]}}};
        picks += 1; if (picks === 2) stop = true;
        return {picks: {k: {oids: ["o0"], reason: "matched"}}};
      };
      const r = await ns.fillLoop.runFill({broadcast, api, cancelled: () => stop}, {});
      return {picks, applies, stopped: r.stopped};
    }""", options)
    assert got == {"picks": 2, "applies": 0, "stopped": True}


@pytest.mark.parametrize(("item_ms", "status", "picks"), [(150, "verified", 3), (0, "partial", 2)])
def test_a_set_clock_grows_per_item(page, load, item_ms, status, picks):
    options = [opt(f"o{i}", t) for i, t in enumerate("ABC")]
    out = run(page, load, frames=[[f("k", "select", "Skills", multi=True, options=options, optionsComplete=True)]],
              limits={"FIELD_MS": 100, "ITEM_MS": item_ms}, apiDelay={"/api/autofill/pick": 60},
              map={"k": {"route": "slot", "slot": "skills", "value": list("ABC")}},
              pick={f"k:{t}": {"oids": [f"o{i}"], "reason": "matched"} for i, t in enumerate("ABC")},
              apply={"A+B+C": {"outcome": "verified", "added": list("ABC"), "missing": []}})
    assert statuses(out) == {"k": status}
    assert len(bodies(out, "/api/autofill/pick")) == picks
    if status == "partial":  # out of time mid-picks: what was picked is still committed
        assert [a["texts"] for a in actions(out, "set")] == [["A"]]
        assert (row(out, "k")["answer"], row(out, "k")["lastOutcome"]) == ("1 of 3 added · 2 ran out of time", "timeout")


def test_a_group_committed_inside_a_set_is_named_once(page, load):
    group = {"candidates": [{"mid": "click:o1", "describe": 'Open the group "Job Board"'}, GIVE_UP]}
    out = run(page, load, frames=[[f("k", "search", "Where did you hear?", multi=True)]],
              map={"k": {"route": "slot", "slot": "preferences.how_heard", "value": ["A", "B", "C"]}},
              explore={"A": {"options": [opt("o1", "A")]}},
              pick={"k:A": {"oids": ["o1"], "reason": "matched"}},
              apply={"A": {"outcome": "verified", "added": ["A"], "missing": []},
                     "click:o1": {"outcome": "unexpected", "reason": "group_committed"}},
              step={"states": [group, group], "moves": [{"mid": "click:o1", "reason": "progress"}] * 2})
    r = row(out, "k")
    assert (r["status"], r["answer"]) == ("partial", '1 of 3 added · Companion clicked "Job Board" — check it')
    assert [(m["mid"], m.get("as")) for m in actions(out, "move")] == [("click:o1", "progress")] * 2
    assert [s["item"] for s in bodies(out, "/api/autofill/step")] == ["B", "C"]


def test_a_field_re_listed_under_a_new_fid_keeps_its_row(page, load):
    out = run(page, load, frames=[[f("a", question="City", fp="same")],
                                  [f("a2", question="City", fp="same", committed="X", answered=True)]],
              map={"a": {"route": "slot", "slot": "personal.city", "value": "X"}})
    assert statuses(out) == {"a2": "verified"}  # not "already": the engine wrote it
    assert [[x["fid"] for x in b["fields"]] for b in bodies(out, "/api/autofill/map")] == [["a"]]
    assert row(out, "a2")["slot"] == "personal.city"


def test_a_later_round_that_reaches_no_frame_keeps_the_report(page, load):
    out = run(page, load, frames=[[f("a", question="City")], None],
              map={"a": {"route": "slot", "slot": "personal.city", "value": "X"}})
    assert statuses(out) == {"a": "verified"}


def test_the_report_lists_only_the_latest_inventory(page, load):
    out = run(page, load, frames=[[f("a", question="City"), f("b", question="Gone")], [f("a", question="City")]],
              map={"a": {"route": "slot", "slot": "personal.city", "value": "X"}})
    assert [r["fid"] for r in out["report"]["fields"]] == ["a"]


def test_a_set_fact_on_a_one_answer_field_is_left_for_the_user(page, load):
    out = run(page, load, frames=[[f("d", "popup", "Main skill")]],
              map={"d": {"route": "slot", "slot": "skills", "value": ["SQL", "Python"]}})
    assert (row(out, "d")["status"], row(out, "d")["lastOutcome"]) == ("needs_answer", "set_for_one")
    assert "fill_explore" not in out["calls"] and "/api/autofill/pick" not in out["calls"]


def test_a_native_list_that_surprises_is_retried_next_round_not_stepped(page, load):
    options = [opt("o1", "Select…"), opt("o2", "United States")]
    out = run(page, load, frames=[[f("s", "select", "Country", options=options, optionsComplete=True)]] * 3,
              map={"s": {"route": "slot", "slot": "personal.country", "value": "United States"}},
              pick={"s": {"oids": ["o2"], "reason": "matched"}},
              apply={"United States": [{"outcome": "unexpected", "reason": "option_missing"}, {"outcome": "verified"}]})
    assert statuses(out) == {"s": "verified"}
    assert "fill_step_state" not in out["calls"] and "/api/autofill/step" not in out["calls"]
    assert len(actions(out, "choose")) == 2


def test_a_stop_between_two_writes_ends_the_run(page, load):
    out = run(page, load, frames=[[f("a", question="City"), f("b", question="State")]], stopAfterApply=True,
              map={"a": {"route": "slot", "slot": "personal.city", "value": "X"},
                   "b": {"route": "slot", "slot": "personal.state", "value": "Y"}})
    assert [a["fid"] for a in actions(out)] == ["a"]
    assert statuses(out) == {"a": "verified", "b": "needs_answer"}
    assert out["report"]["stopped"] is True
    assert "fill_sweep" not in out["calls"]


def test_progress_events_name_each_field_once_and_each_round(page, load):
    out = run(page, load, frames=[[f("a", question="City"), f("v", committed="x", answered=True)]] * 2,
              map={"a": {"route": "slot", "slot": "personal.city", "value": "X"}})
    events = out["progress"]
    assert {"phase": "field", "fid": "a", "status": "verified"} in events
    assert {"phase": "field", "fid": "v", "status": "already"} in events
    assert {"phase": "round", "round": 1} in events
    assert all(set(e) in ({"phase", "fid", "status"}, {"phase", "round"}) for e in events)
    fields = [(e["fid"], e["status"]) for e in events if e["phase"] == "field"]
    assert len(fields) == len(set(fields))


# ---------- code-quality review


def test_a_relabelled_field_keeping_its_fid_is_mapped_again(page, load):
    out = run(page, load, frames=[[f("a", question="City")], [f("a", question="Company", fp="fp-a2", committed="Springfield")]],
              map={"a:City": {"route": "slot", "slot": "personal.city", "value": "Springfield"},
                   "a:Company": {"route": "slot", "slot": "experience.0.employer", "value": "Acme"}})
    assert [[(x["fid"], x["question"]) for x in b["fields"]] for b in bodies(out, "/api/autofill/map")] == [
        [("a", "City")], [("a", "Company")]]
    r = row(out, "a")
    assert (r["status"], r["answer"], r["slot"]) == ("verified", "Acme", "experience.0.employer")


@pytest.mark.parametrize("remapped", [True, False])
def test_a_relabelled_field_holding_the_engines_old_write_is_not_already(page, load, remapped):
    relabelled = f("a", question="Company", fp="fp-a2", committed="Springfield", answered=True)
    mapping = {"a:City": {"route": "slot", "slot": "personal.city", "value": "Springfield"}}
    if remapped:
        mapping["a:Company"] = {"route": "slot", "slot": "experience.0.employer", "value": "Acme"}
    out = run(page, load, frames=[[f("a", question="City")], [relabelled]], map=mapping)
    r = row(out, "a")
    assert len(bodies(out, "/api/autofill/map")) == 2
    if remapped:
        assert (r["status"], r["answer"]) == ("verified", "Acme")
        assert [a["value"] for a in actions(out, "write")] == ["Springfield", "Acme"]
    else:
        assert r["status"] == "needs_answer"
        assert r["answer"] == 'Companion wrote "Springfield" here for an earlier question — check it'


def test_a_relabelled_field_holding_someone_elses_value_is_already(page, load):
    out = run(page, load, frames=[[f("a", question="City")],
                                  [f("a", question="Company", fp="fp-a2", committed="Initech", answered=True)]],
              map={"a:City": {"route": "slot", "slot": "personal.city", "value": "Springfield"}})
    assert statuses(out) == {"a": "already"}


def test_complete_native_lists_are_picked_in_one_call(page, load):
    yes_no = [opt("o1", "Yes"), opt("o2", "No")]
    fields = [f(x, "select", f"Q{x}", options=yes_no, optionsComplete=True) for x in "abc"]
    out = run(page, load, frames=[fields],
              map={x: {"route": "slot", "slot": f"work_auth.{x}", "value": "Yes"} for x in "abc"},
              pick={x: {"oids": ["o1"], "reason": "matched"} for x in "abc"})
    assert statuses(out) == {"a": "verified", "b": "verified", "c": "verified"}
    [pick] = bodies(out, "/api/autofill/pick")
    assert [x["fid"] for x in pick["fields"]] == ["a", "b", "c"]
    assert "fill_explore" not in out["calls"]


def test_a_pick_reason_outside_the_vocabulary_is_an_abstain(page, load):
    out = run(page, load, frames=[[f("s", "select", "Country", options=[opt("o1", "US")], optionsComplete=True)]],
              map={"s": {"route": "slot", "slot": "personal.country", "value": "US"}},
              pick={"s": {"oids": ["o1"], "reason": "sure"}})
    assert (row(out, "s")["status"], row(out, "s")["lastOutcome"]) == ("needs_answer", "abstained")
    assert not actions(out)


def test_a_step_reason_outside_the_vocabulary_gives_up(page, load):
    out = run(page, load, frames=[[f("h", "popup")]],
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              explore={"h": {"options": [], "complete": False, "error": "empty_popup"}},
              step={"states": [{"candidates": [{"mid": "click:o1", "describe": 'Click the option "LinkedIn"'}, GIVE_UP]}],
                    "moves": [{"mid": "click:o1", "reason": "sure"}]})
    assert statuses(out) == {"h": "needs_answer"}
    assert [a["mid"] for a in actions(out, "move")] == ["give_up"]


def test_repeated_set_items_are_picked_once(page, load):
    out = run(page, load, frames=[[f("k", "search", "Skills", multi=True)]],
              map={"k": {"route": "slot", "slot": "skills", "value": ["SQL", "SQL", "Python"]}},
              explore={"SQL": {"options": [opt("o1", "SQL")]}, "Python": {"options": [opt("o1", "Python")]}},
              pick={"k:SQL": {"oids": ["o1"], "reason": "matched"}, "k:Python": {"oids": ["o1"], "reason": "matched"}},
              apply={"SQL+Python": {"outcome": "verified", "added": ["SQL", "Python"], "missing": []}})
    assert statuses(out) == {"k": "verified"}
    assert [b["fields"][0]["item"] for b in bodies(out, "/api/autofill/pick")] == ["SQL", "Python"]


def test_a_long_base_selector_is_cut_to_the_schema(page, load):
    out = run(page, load, frames=[[f("a", question="City")]], options={"base": "b" * 300},
              map={"a": {"route": "slot", "slot": "personal.city", "value": "X"}})
    [m] = bodies(out, "/api/autofill/map")
    assert m["base"] == "b" * 200


def test_prose_is_written_as_soon_as_its_answers_arrive(page, load):
    yes_no = [opt("o1", "Yes"), opt("o2", "No")]
    out = run(page, load, frames=[[f("c1", "popup", "Q1"), f("c2", "popup", "Q2"), f("w", question="Why us?")]],
              apiDelay={"/api/autofill/pick": 40, "/api/autofill/choose": 10},
              map={"c1": {"route": "slot", "slot": "work_auth.a", "value": "Yes"},
                   "c2": {"route": "slot", "slot": "work_auth.b", "value": "Yes"}, "w": {"route": "free_text"}},
              explore={"c1": {"options": yes_no, "complete": True}, "c2": {"options": yes_no, "complete": True}},
              pick={"c1": {"oids": ["o1"], "reason": "matched"}, "c2": {"oids": ["o1"], "reason": "matched"}},
              choose={"w": {"answer": "Because.", "reason": "matched"}})
    assert statuses(out) == {"c1": "verified", "c2": "verified", "w": "verified"}
    assert [a["fid"] for a in actions(out)] == ["c1", "w", "c2"]


def test_a_one_item_list_fact_answers_a_one_answer_field(page, load):
    out = run(page, load, frames=[[f("d", "popup", "Main skill"), f("t", question="Top skill")]],
              map={"d": {"route": "slot", "slot": "skills", "value": ["SQL"]},
                   "t": {"route": "slot", "slot": "skills", "value": ["SQL"]}},
              explore={"d": {"options": [opt("o1", "SQL"), opt("o2", "Go")], "complete": True}},
              pick={"d:SQL": {"oids": ["o1"], "reason": "matched"}})
    assert statuses(out) == {"d": "verified", "t": "verified"}
    [pick] = bodies(out, "/api/autofill/pick")
    assert pick["fields"][0]["item"] == "SQL"
    assert [a.get("value") for a in actions(out, "write")] == ["SQL"]


# ---------- the wire


def test_every_page_message_the_loop_sends_is_a_page_handler():
    loop = (EXTENSION / "shared" / "fill-loop.js").read_text(encoding="utf-8")
    agent = (EXTENSION / "content" / "agent.js").read_text(encoding="utf-8")
    block = re.search(r"const PAGE_HANDLERS = \{(.*?)\n  \};", agent, re.S)
    handled = set(re.findall(r"^    ([a-z_]+):", block.group(1), re.M))
    sent = set(re.findall(r'\btype:\s*"([a-z_]+)"', loop))
    assert sent == {"fill_inventory", "fill_explore", "fill_apply", "fill_step_state", "fill_sweep"}
    assert sent <= handled


def test_the_panel_loads_the_loop_after_the_guided_runner():
    html = (Path(EXTENSION) / "panel" / "panel.html").read_text(encoding="utf-8")
    srcs = re.findall(r'<script src="([^"]+)"></script>', html)
    assert srcs.index("../shared/fill-loop.js") == srcs.index("../shared/guided-run.js") + 1
