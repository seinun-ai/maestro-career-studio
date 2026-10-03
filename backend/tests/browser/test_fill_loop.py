"""The loop's decisions (shared/fill-loop.js), with the page and the backend
scripted: every page message and every backend call is answered by the spec,
and recorded so a test can pin what the loop SENT."""

import json
import re
from pathlib import Path

import pytest

from app.schemas.autofill_choose import ChooseRequest
from app.schemas.autofill_fill import MapRequest, PickRequest, SectionsRequest, StepRequest
from app.schemas.autofill_trace import RunTrace
from tests.browser.conftest import EXTENSION

# Every body the loop POSTs must be one the real endpoint accepts.
MODELS = {"/api/autofill/map": MapRequest, "/api/autofill/pick": PickRequest,
          "/api/autofill/step": StepRequest, "/api/autofill/choose": ChooseRequest,
          "/api/autofill/sections": SectionsRequest}

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
  // A click move commits the option it names, as the page reports it (its
  // quoted text in the last state's description); an explicit `committed` wins.
  let candidates = [];
  const clicked = (mid) => {
    const d = candidates.find((c) => c.mid === mid)?.describe ?? "";
    try { return d.includes('"') ? JSON.parse(d.slice(d.indexOf('"'))) : null; } catch { return null; }
  };
  const one = (result) => [{frameId: 0, result}];
  // A scripted answer may be a list: one entry per call, the last one repeating.
  const take = (v) => (Array.isArray(v) ? (v.length > 1 ? v.shift() : v[0]) : v);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  Object.assign(window.careerStudioCompanion.fillLoop.limits, {QUIET_MS: 0}, spec.limits ?? {});
  const broadcast = async (msg) => {
    // A peek (the fid set only, after a commit) is its own call: it is not a round.
    calls.push(msg.type === "fill_inventory" && msg.peek ? "fill_peek" : msg.type);
    sent.push(JSON.parse(JSON.stringify(msg)));
    if (msg.type === "fill_inventory" && msg.peek) {
      // `peek`: the fid sets the page answers (a list: one per call); else the current frame's.
      const fields = spec.frames[Math.min(Math.max(round, 1), spec.frames.length) - 1];
      return fields === null ? [{frameId: 0, error: "gone"}]
        : one({frame: "f", fids: take(spec.peek) ?? fields.map((x) => x.fid)});
    }
    if (msg.type === "fill_inventory") {
      round += 1;
      const fields = spec.frames[Math.min(round, spec.frames.length) - 1];
      // null: the page no longer answers (a frame that went away).
      return fields === null ? [{frameId: 0, error: "gone"}] : one({frame: "f", host: "x.test", fields});
    }
    if (msg.type === "fill_explore") return one(Object.fromEntries(msg.requests.map(r => [r.fid, take(spec.explore[r.term ?? r.fid]) ?? {options: [], complete: false, error: "no_popup"}])));
    if (msg.type === "fill_apply" && spec.stopAfterApply) stop = true;
    // `pageDelay[key]`: how long the page takes over that action (a list: one per call).
    const keyOf = (a) => (a.op === "move" ? a.mid : (a.text ?? a.value ?? (a.texts || []).join("+") ?? a.fid));
    if (msg.type === "fill_apply") {
      for (const a of msg.actions) {
        const delay = take(spec.pageDelay?.[keyOf(a)]);
        if (delay) await sleep(delay);
      }
      return one(msg.actions.map(a => {
        const key = keyOf(a);
        return {fid: a.fid, committed: a.text ?? a.value ?? a.texts ?? (a.op === "move" ? clicked(a.mid) : null), ...(take(spec.apply[key]) ?? {outcome: a.op === "move" && a.mid === "give_up" ? "closed" : "verified"})};
      }));
    }
    if (msg.type === "fill_step_state") {
      const s = spec.step.states.shift() ?? {candidates: [{mid: "give_up", describe: "stop"}]};
      candidates = s.candidates ?? [];
      return [{frameId: 1, result: null}, {frameId: 0, result: {version: 1, complete: false, ...s}}];
    }
    // A page gone (this round's frames null) answers no sweep either.
    if (msg.type === "fill_sweep") {
      return spec.frames[Math.min(Math.max(round, 1), spec.frames.length) - 1] === null
        ? [{frameId: 0, error: "gone"}] : one(take(spec.sweep) ?? []);
    }
    // `sections`: the page's repeating sections (a list: one snapshot per
    // read); absent, no frame answers. `stopOnSections`: Stop lands as they are read.
    if (msg.type === "fill_sections") {
      if (spec.stopOnSections) stop = true;
      return spec.sections ? one(take(spec.sections)) : [];
    }
    // `add[sid]`: what one press did (a list: one per press); by default the
    // section grew by one entry.
    if (msg.type === "fill_add") {
      return [{frameId: 1, result: null},
              {frameId: 0, result: {sid: msg.sid, ...(take(spec.add?.[msg.sid]) ?? {outcome: "added", entries: msg.entries + 1})}}];
    }
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
    // An entry placed nowhere (profile_entry null) gets nothing, as the real /map does.
    if (path === "/api/autofill/map") return {fields: Object.fromEntries(body.fields.map(f => [f.fid, f.profile_entry === null ? {route: "none"} : spec.map[`${f.fid}:${f.question}`] ?? spec.map[f.fid] ?? {route: "none"}]))};
    // A scripted pick may be a list too: one entry per /pick call for that field.
    if (path === "/api/autofill/pick") return {picks: Object.fromEntries(body.fields.map(f => [f.fid, take(spec.pick[`${f.fid}:${f.item ?? ""}`]) ?? take(spec.pick[f.fid]) ?? {oids: [], reason: "abstained"}]))};
    if (path === "/api/autofill/step") return spec.step.moves.shift() ?? {mid: null, reason: "abstained"};
    if (path === "/api/autofill/sections") return {sections: Object.fromEntries(body.sections.map(x => [x.sid, spec.kinds?.[x.sid] ?? {kind: "none", wanted: 0}]))};
    if (path === "/api/autofill/choose") return {choices: Object.fromEntries(body.fields.map(f => [f.qid, spec.choose[f.qid] ?? {answer: null, reason: "abstained"}]))};
    throw Object.assign(new Error(path), {status: 502});
  };
  // `recipes` (opt-in): the panel's recipe store, scripted. `recipes.book`
  // answers a lookup by family (a recipe, or null); `recipes.fail` makes both
  // halves throw. What was looked up and what was recorded come back.
  const gets = [];
  let lessons = null;
  const recipes = spec.recipes ? {
    get: async (r) => {
      gets.push(r);
      if (spec.recipes.fail) throw new Error("storage is unavailable");
      return spec.recipes.book?.[r.family] ?? null;
    },
    record: async (ls) => {
      lessons = [...(lessons ?? []), ...ls];
      if (spec.recipes.fail) throw new Error("storage is unavailable");
    },
  } : undefined;
  let budget = spec.stopAfter ?? Infinity;
  const t0 = Date.now();
  const report = await window.careerStudioCompanion.fillLoop.runFill(
    {broadcast, api, cancelled: () => stop || (budget -= 1) < 0, onProgress: (u) => progress.push(u),
     ...(recipes ? {recipes} : {})},
    spec.options ?? {sourceHint: null});
  return {report, calls, sent, posts, progress, peak, ms: Date.now() - t0, gets, lessons};
}"""


def run(page, load, **spec):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    spec = {"frames": [[]], "explore": {}, "apply": {}, "map": {}, "pick": {}, "choose": {},
            "step": {"states": [], "moves": []}} | spec
    out = page.evaluate(DRIVER, spec)
    for post in out["posts"]:
        if post["path"] in MODELS:
            MODELS[post["path"]].model_validate(post["body"])
    # The trace the loop builds must be one POST /api/autofill/runs accepts: one field the
    # schema rejects loses the whole run, so no live run may be the first to meet it.
    if out["report"].get("trace"):
        RunTrace.model_validate(out["report"]["trace"])
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


def explored_terms(out):
    return [r.get("term") for m in out["sent"] if m["type"] == "fill_explore" for r in m["requests"]]


def test_a_search_whose_rows_show_checkboxes_takes_the_set_path(page, load):
    """Not known to take several at inventory (one Workday container for School
    and Skills); the first item's explore shows checkbox rows: a set."""
    out = run(page, load, frames=[[f("k", "search", "Skills", multi=None)]],
              map={"k": {"route": "slot", "slot": "skills", "value": ["SQL", "Python"]}},
              explore={"SQL": {"options": [opt("o1", "SQL")], "multi": True},
                       "Python": {"options": [opt("o1", "Python")], "multi": True}},
              pick={"k:SQL": {"oids": ["o1"], "reason": "matched"}, "k:Python": {"oids": ["o1"], "reason": "matched"}},
              apply={"SQL+Python": {"outcome": "verified", "added": ["SQL", "Python"], "missing": []}})
    assert statuses(out) == {"k": "verified"}
    assert explored_terms(out) == ["SQL", "Python"]   # the first item's explore is not repeated
    # Each explore carries what the field's clock has left, so the page's explore never outlives it.
    assert all(0 < r["ms"] <= 31000 for m in out["sent"] if m["type"] == "fill_explore" for r in m["requests"])
    assert [a["texts"] for a in actions(out, "set")] == [["SQL", "Python"]]


def test_a_search_whose_rows_show_radios_takes_one_answer(page, load):
    out = run(page, load, frames=[[f("k", "search", "School", multi=None)]],
              map={"k": {"route": "slot", "slot": "education.0.school", "value": ["UT Arlington", "UT Austin"]}},
              explore={"UT Arlington": {"options": [opt("o1", "UT Arlington")], "multi": False}})
    assert (row(out, "k")["status"], row(out, "k")["lastOutcome"]) == ("needs_answer", "set_for_one")
    assert explored_terms(out) == ["UT Arlington"]   # asked the rows first
    assert "/api/autofill/pick" not in out["calls"] and not actions(out)


def test_a_search_known_to_take_one_answer_is_not_explored_for_a_set(page, load):
    """Its rows already said single (inventory `multi: false`, not null): a
    fact of several items is no answer, and nothing is typed to learn that."""
    out = run(page, load, frames=[[f("k", "search", "School", multi=False)]],
              map={"k": {"route": "slot", "slot": "education.0.school", "value": ["UT Arlington", "UT Austin"]}})
    assert (row(out, "k")["status"], row(out, "k")["lastOutcome"]) == ("needs_answer", "set_for_one")
    assert explored_terms(out) == [] and not actions(out)


def test_a_one_answer_search_box_that_already_holds_a_value_is_left_alone(page, load):
    """Its one pill did not say single or several; the rows (radios) did. What
    it holds — the user's, or a parsed resume's — is never overwritten."""
    out = run(page, load, frames=[[f("k", "search", "School", committed=["UT Austin"])]],
              map={"k": {"route": "slot", "slot": "education.0.school", "value": "UT Arlington"}},
              explore={"UT Arlington": {"options": [opt("o1", "UT Arlington")], "multi": False}},
              pick={"k": {"oids": ["o1"], "reason": "matched"}})
    assert statuses(out) == {"k": "already"}
    assert not actions(out) and "/api/autofill/pick" not in out["calls"]


def test_radio_rows_turn_a_one_item_set_into_one_answer(page, load):
    out = run(page, load, frames=[[f("k", "search", "School", multi=True)]],
              map={"k": {"route": "slot", "slot": "education.0.school", "value": ["UT Arlington"]}},
              explore={"UT Arlington": {"options": [opt("o1", "UT Arlington")], "multi": False}},
              pick={"k:UT Arlington": {"oids": ["o1"], "reason": "matched"}})
    assert statuses(out) == {"k": "verified"}
    assert [(a["op"], a.get("text")) for a in actions(out)] == [("choose", "UT Arlington")]


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


# ---------- a commit that adds or removes fields (notes §4)
def current_box(fid="c", **kw):
    return f(fid, "group", "I currently work here", **{"section": "Work Experience", "committed": "No",
             "options": [opt("yes", "Yes"), opt("no", "No")], "optionsComplete": True, **kw})


SECTION_MAP = {
    "c": {"route": "slot", "slot": "experience.0.current", "value": "Yes"},
    "t": {"route": "slot", "slot": "experience.0.title", "value": "Analyst"},
    "d1": {"route": "slot", "slot": "experience.0.start_date", "value": "2021-05"},
    "d2": {"route": "slot", "slot": "experience.0.end_date", "value": "2023-01"},
}


def test_currently_employed_is_ticked_before_the_dates_of_its_entry(page, load):
    """By the MAPPED SLOT, never the label: a choice mapped to `<…>.current`
    goes before the text and date fields, though the page lists it after them."""
    t = f("t", question="Job Title", section="Work Experience")
    d1 = f("d1", "date", "From", section="Work Experience")
    d2 = f("d2", "date", "To", section="Work Experience")
    out = run(page, load, frames=[[t, d1, d2, current_box()]], map=SECTION_MAP,
              pick={"c": {"oids": ["yes"], "reason": "matched"}})
    assert [a["fid"] for a in actions(out)] == ["c", "t", "d1", "d2"]
    assert statuses(out) == {"t": "verified", "d1": "verified", "d2": "verified", "c": "verified"}


def test_fields_added_or_removed_by_a_commit_are_re_observed_before_continuing(page, load):
    """Ticking "I currently work here" removes the entry's To date a frame
    later: the peek after the commit sees the fid set change, the loop takes a
    fresh inventory before the next field, never writes the To date, and the
    report has no row for it (no `stale`)."""
    t = f("t", question="Job Title", section="Work Experience")
    d1 = f("d1", "date", "From", section="Work Experience")
    d2 = f("d2", "date", "To", section="Work Experience")
    ticked = current_box(committed="Yes", answered=True)
    out = run(page, load, frames=[[t, d1, d2, current_box()], [t, d1, ticked]], map=SECTION_MAP,
              peek=[["t", "d1", "c"]], pick={"c": {"oids": ["yes"], "reason": "matched"}})
    assert [a["fid"] for a in actions(out)] == ["c", "t", "d1"]
    # (The round's read of repeating sections — none here — is not part of this order.)
    calls = [c for c in out["calls"] if c.startswith("fill_") and c != "fill_sections"]
    assert calls[:5] == ["fill_inventory", "fill_apply", "fill_peek", "fill_inventory", "fill_apply"]
    assert statuses(out) == {"t": "verified", "d1": "verified", "c": "verified"}
    # The new inventory mapped nothing again: every field it listed was known.
    assert [len(b["fields"]) for b in bodies(out, "/api/autofill/map")] == [4]


def test_a_field_a_commit_adds_is_mapped_and_filled_in_the_same_round(page, load):
    """A choice that reveals a field (an "Other, please specify" box): the peek
    sees a new fid, the fresh inventory lists it, only IT is mapped, and it is
    filled before the round moves on. A commit that changes nothing is not
    followed by a second inventory."""
    q = f("q", "popup", "How did you hear?")
    other = f("o", question="Please specify")
    p = f("p", "popup", "Degree")
    out = run(page, load, frames=[[q, p], [q, other, p]],
              peek=[["q", "o", "p"]],
              map={"q": {"route": "slot", "slot": "preferences.how_heard", "value": "Other"},
                   "p": {"route": "slot", "slot": "education.0.degree", "value": "MBA"},
                   "o": {"route": "slot", "slot": "preferences.how_heard_other", "value": "A friend"}},
              explore={"q": {"options": [opt("o1", "Other")], "complete": True},
                       "p": {"options": [opt("o1", "MBA")], "complete": True}},
              pick={"q": {"oids": ["o1"], "reason": "matched"}, "p": {"oids": ["o1"], "reason": "matched"}})
    assert [a["fid"] for a in actions(out)] == ["q", "o", "p"]
    assert statuses(out) == {"q": "verified", "o": "verified", "p": "verified"}
    assert [[x["fid"] for x in b["fields"]] for b in bodies(out, "/api/autofill/map")] == [["q", "p"], ["o"]]
    # One re-inventory (after q); p's commit changed nothing, so its peek is all.
    first_round = out["calls"][:out["calls"].index("fill_sweep")]
    assert first_round.count("fill_inventory") == 2 and first_round.count("fill_peek") == 2


def test_a_prose_field_a_commit_re_renders_is_picked_up_next_round(page, load):
    """A commit re-renders a free-text box under a new fid (same frame, same
    fingerprint) while its answer is still being written: the old fid is gone
    from the page, so the round skips it (no crash, no write to it) and the
    replacement is answered and written in the next round."""
    q = f("q", "popup", "How did you hear?")
    w1 = f("w1", question="Why us?", fp="fp-w")
    w2 = f("w2", question="Why us?", fp="fp-w")
    out = run(page, load, frames=[[q, w1], [q, w2]], peek=[["q", "w2"]],
              apiDelay={"/api/autofill/choose": 300},
              map={"q": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"},
                   "w1": {"route": "free_text"}, "w2": {"route": "free_text"}},
              explore={"q": {"options": [opt("o1", "LinkedIn")], "complete": True}},
              pick={"q": {"oids": ["o1"], "reason": "matched"}},
              choose={"w1": {"answer": "Because.", "reason": "matched"}, "w2": {"answer": "Because.", "reason": "matched"}})
    assert statuses(out) == {"q": "verified", "w2": "verified"}
    assert [a["fid"] for a in actions(out)] == ["q", "w2"]


def test_the_leads_are_picked_in_one_call(page, load):
    """However many entries carry a `.current` box, their picks are one /pick call."""
    boxes = [current_box(f"c{i}", repeatIndex=i) for i in range(3)]
    out = run(page, load, frames=[boxes],
              map={f"c{i}": {"route": "slot", "slot": f"experience.{i}.current", "value": "Yes"} for i in range(3)},
              pick={f"c{i}": {"oids": ["yes"], "reason": "matched"} for i in range(3)})
    assert statuses(out) == {"c0": "verified", "c1": "verified", "c2": "verified"}
    assert [[x["fid"] for x in b["fields"]] for b in bodies(out, "/api/autofill/pick")] == [["c0", "c1", "c2"]]


def test_a_commit_an_explore_could_not_take_back_is_followed_by_a_peek(page, load):
    """Exploring picked a value the page would not give back: that is a change
    on the page like any commit, so the loop peeks before the next field."""
    out = run(page, load, frames=[[f("k", "search", "Minor")]],
              map={"k": {"route": "slot", "slot": "education.0.minor", "value": "Analytics"}},
              explore={"Analytics": {"options": [], "complete": False, "error": "committed_while_exploring",
                                     "committed": "Analytics"}})
    assert statuses(out) == {"k": "needs_answer"}
    assert "fill_peek" in out["calls"] and not actions(out)


def test_a_user_edit_during_the_model_call_is_respected(page, load):
    out = run(page, load, frames=[[f("a", question="City")]] * 3,
              map={"a": {"route": "slot", "slot": "personal.city", "value": "X"}}, apply={"X": {"outcome": "yours"}})
    assert statuses(out) == {"a": "yours"}
    assert len(actions(out)) == 1  # a refusal is final: never retried


def test_a_late_reversion_found_by_the_final_sweep_is_retried(page, load):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    got = page.evaluate("""async () => {
      window.careerStudioCompanion.fillLoop.limits.QUIET_MS = 30;
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
    assert got["sweeps"] >= 3  # the final sweep after the re-write found nothing more


def test_the_final_sweep_runs_even_when_the_rounds_run_out(page, load):
    out = run(page, load, frames=[[f("a", question="City")]], limits={"MAX_ROUNDS": 1},
              map={"a": {"route": "slot", "slot": "personal.city", "value": "X"}},
              sweep=[[], [{"fid": "a", "outcome": "reverted"}]])
    # Reverted and never re-committed: the user learns the page took it back.
    r = row(out, "a")
    assert (r["status"], r["lastOutcome"]) == ("unconfirmed", "reverted")
    assert r["answer"] == 'Companion filled "X", then the page took it back. Check it.'
    assert out["calls"].count("fill_sweep") == 2


def test_the_write_format_is_the_backends(page, load):
    """/map says the format, decided by the slot server-side (the backend's
    `format_of` is the only reading of a slot name). The loop never guesses
    one: a response that does not say, or names a format it does not know,
    writes with none."""
    out = run(page, load, frames=[[f("p", question="Contact number"), f("s", question="Desired salary"),
                                   f("c", question="City"), f("o", question="Phone"), f("x", question="X")]],
              map={"p": {"route": "slot", "slot": "custom.4", "value": "5550100000", "format": "phone"},
                   "s": {"route": "slot", "slot": "preferences.desired_salary", "value": "80000", "format": "money"},
                   "c": {"route": "slot", "slot": "personal.city", "value": "Springfield", "format": None},
                   "o": {"route": "slot", "slot": "personal.phone", "value": "5550100000"},
                   "x": {"route": "slot", "slot": "personal.phone", "value": "1", "format": "zip"}})
    assert set(statuses(out).values()) == {"verified"}
    writes = {a["fid"]: a.get("format") for a in actions(out, "write")}
    assert writes == {"p": "phone", "s": "money", "c": None, "o": None, "x": None}
    assert not [a for a in actions(out, "write") if "format" in a and a["format"] is None]


def test_every_backend_call_carries_the_browsers_date(page, load):
    """"Today" is the applicant's date: the backend may run on UTC."""
    out = run(page, load, frames=[[f("a", question="City")]],
              map={"a": {"route": "slot", "slot": "personal.city", "value": "Springfield"}})
    local = page.evaluate("""() => { const d = new Date();
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }""")
    [body] = bodies(out, "/api/autofill/map")
    assert body["today"] == local


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
      window.careerStudioCompanion.fillLoop.limits.QUIET_MS = 0;
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
      ns.fillLoop.limits.QUIET_MS = 0;
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
    assert (r["status"], r["answer"]) == ("needs_answer", 'Companion clicked "Job "Board"". Check it.')
    assert r["lastOutcome"] == "group_committed"
    assert [m["mid"] for m in actions(out, "move")] == ["click:o1"]  # not re-tried, not given up over it


def test_a_search_move_whose_enter_committed_a_hit_is_left_for_the_user_to_check(page, load):
    """A search's one hit that the page committed on its own (notes §2 rule 5)
    is named with what it left — never filled, never tried again."""
    out = run(page, load, frames=[[f("k", "search", "Field of study")]] * 3,
              map={"k": {"route": "slot", "slot": "education.0.discipline", "value": "Business analytics"}},
              explore={"Business analytics": {"options": [], "complete": False, "error": "empty_popup"}},
              apply={"search:word:1": {"outcome": "unexpected", "reason": "search_committed", "committed": "Analytics"}},
              step={"states": [{"candidates": [{"mid": "search:word:1", "describe": 'Type "analytics" into the search box'},
                                               GIVE_UP]}],
                    "moves": [{"mid": "search:word:1", "reason": "progress"}]})
    r = row(out, "k")
    assert (r["status"], r["answer"], r["lastOutcome"]) == (
        "needs_answer", 'Searching picked "Analytics". Check it.', "search_committed")
    assert [m["mid"] for m in actions(out, "move")] == ["search:word:1"]
    obs = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.buildLoopObservations(r)", out["report"])
    assert [o["outcome"] for o in obs] == ["filled_unverified"]


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
    # Each scroll shows a different window of the list: a different state, so
    # a scroll that failed from one is tried again from the next.
    states = [{"version": i, "candidates": [{"mid": f"click:o{i}", "describe": f'Click the option "Row {i}"'},
                                            {"mid": "scroll", "describe": "Scroll"}, GIVE_UP]} for i in range(n)]
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
      const ns = window.careerStudioCompanion; ns.fillLoop.limits.QUIET_MS = 0;
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
    assert (r["status"], r["answer"]) == ("partial", '1 of 3 added · Companion clicked "Job Board". Check it.')
    assert [(m["mid"], m.get("as")) for m in actions(out, "move")] == [("click:o1", "progress")] * 2
    assert [s["item"] for s in bodies(out, "/api/autofill/step")] == ["B", "C"]


def test_a_search_commit_inside_a_set_is_named_as_a_search(page, load):
    """Nothing covered, one item landed by a search's own commit: the row's
    lastOutcome says so (search_committed), not group_committed."""
    searched = {"candidates": [{"mid": "search:word:0", "describe": 'Type "Py" into the search box'}, GIVE_UP]}
    out = run(page, load, frames=[[f("k", "search", "Skills", multi=True)]],
              map={"k": {"route": "slot", "slot": "skills", "value": ["B", "C"]}},
              explore={"B": {"options": [], "error": "no_results"}, "C": {"options": [], "error": "no_results"}},
              apply={"search:word:0": {"outcome": "unexpected", "reason": "search_committed", "committed": ["Bx"]}},
              step={"states": [searched, {"candidates": [GIVE_UP]}], "moves": [{"mid": "search:word:0", "reason": "progress"}]})
    r = row(out, "k")
    assert (r["status"], r["lastOutcome"]) == ("needs_answer", "search_committed")
    assert r["answer"] == 'Searching picked "Bx". Check it.'


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
        assert r["answer"] == 'Companion wrote "Springfield" here for an earlier question. Check it.'


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


# ---------- committed evidence (Task 3): a pick that shows but did not save


def test_an_unconfirmed_pick_is_never_counted_as_verified(page, load):
    out = run(page, load, frames=[[f("d", "popup", "Willing to relocate?")]] * 2,
              map={"d": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "Yes"}},
              explore={"d": {"options": [opt("o1", "Yes"), opt("o2", "No")], "complete": True}},
              pick={"d": {"oids": ["o1"], "reason": "matched"}},
              apply={"Yes": {"outcome": "unconfirmed"}})
    r = row(out, "d")
    assert (r["status"], r["lastOutcome"], r["answer"]) == ("unconfirmed", "unconfirmed", 'Companion clicked "Yes". Check it.')
    assert len(actions(out, "choose")) == 1   # final for this run: not retried as a failure
    obs = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.buildLoopObservations(r)", out["report"])
    assert [o["outcome"] for o in obs] == ["unconfirmed"]


def test_an_unconfirmed_adaptive_click_is_never_counted_as_verified(page, load):
    out = run(page, load, frames=[[f("d", "popup", "Willing to relocate?")]],
              map={"d": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "Yes"}},
              explore={"d": {"options": [opt("o1", "Yes")], "complete": True}},
              pick={"d": {"oids": [], "reason": "abstained"}},
              apply={"click:o1": {"outcome": "unconfirmed"}},
              step={"states": [{"candidates": [{"mid": "click:o1", "describe": 'Click the option "Yes"'}, GIVE_UP]}],
                    "moves": [{"mid": "click:o1", "reason": "matched"}]})
    r = row(out, "d")
    assert (r["status"], r["lastOutcome"], r["answer"]) == ("unconfirmed", "unconfirmed", 'Companion clicked "Yes". Check it.')
    assert out["calls"].count("/api/autofill/step") == 1


def test_a_placeholder_option_is_never_offered_as_an_answer(page, load):
    """Live Workday lists "Select One" as an option (§3a, §8b): whatever a list
    carries, /pick and /map see neither it nor an empty or dash-only row, and
    the list still counts as complete (it hides no answer)."""
    blanks = [opt("o1", "Select One"), opt("o2", ""), opt("o3", "--")]
    out = run(page, load, frames=[[f("d", "popup", "Degree"), f("s", "select", "Country", options=[
                  *blanks, opt("o4", "Canada")], optionsComplete=True)]],
              map={"d": {"route": "slot", "slot": "education.0.degree", "value": "Masters"},
                   "s": {"route": "slot", "slot": "personal.country", "value": "Canada"}},
              explore={"d": {"options": [*blanks, opt("o4", "Masters")], "complete": True}},
              pick={"d": {"oids": ["o4"], "reason": "matched"}, "s": {"oids": ["o4"], "reason": "matched"}})
    assert statuses(out) == {"d": "verified", "s": "verified"}
    fields = [x for b in bodies(out, "/api/autofill/pick") for x in b["fields"]]
    assert {x["fid"]: x["options"] for x in fields} == {
        "d": [{"oid": "o4", "text": "Masters"}], "s": [{"oid": "o4", "text": "Canada"}]}
    assert all(x["complete"] for x in fields)
    [mapped] = bodies(out, "/api/autofill/map")
    assert {x["fid"]: x["options"] for x in mapped["fields"]}["s"] == ["Canada"]


def test_an_empty_or_placeholder_commit_is_never_verified(page, load):
    """Defence in depth: whatever the page says, nothing (or "Select One") is no answer."""
    for committed in ("", "Select One"):
        out = run(page, load, frames=[[f("d", "popup", "Degree")]],
                  map={"d": {"route": "slot", "slot": "education.0.degree", "value": "Masters"}},
                  explore={"d": {"options": [opt("o1", "Select One"), opt("o2", "Masters")], "complete": True}},
                  pick={"d": {"oids": ["o2"], "reason": "matched"}},
                  apply={"Masters": {"outcome": "verified", "committed": committed}})
        r = row(out, "d")
        assert (r["status"], r["lastOutcome"]) == ("unconfirmed", "unconfirmed"), committed
        obs = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.buildLoopObservations(r)", out["report"])
        assert [o["outcome"] for o in obs] == ["unconfirmed"]


def test_an_empty_answer_is_never_written(page, load):
    out = run(page, load, frames=[[f("p", question="Why us?")]], map={"p": {"route": "free_text"}},
              choose={"p": {"answer": "   ", "reason": "matched"}})
    assert (row(out, "p")["status"], row(out, "p")["lastOutcome"]) == ("needs_answer", "no_value")
    assert not actions(out, "write")


def test_an_unconfirmed_write_is_left_to_check_not_retried(page, load):
    out = run(page, load, frames=[[f("a", question="City")]] * 3,
              map={"a": {"route": "slot", "slot": "personal.city", "value": "Springfield"}},
              apply={"Springfield": {"outcome": "unconfirmed"}})
    assert (row(out, "a")["status"], row(out, "a")["lastOutcome"]) == ("unconfirmed", "unconfirmed")
    assert len(actions(out, "write")) == 1


# ---------- one controller per field (Task 4)


def test_an_unconfirmed_commit_is_reported_as_unconfirmed_never_filled(page, load):
    out = run(page, load, frames=[[f("a", question="City"), f("d", "popup", "Relocate?")]] * 2,
              map={"a": {"route": "slot", "slot": "personal.city", "value": "Springfield"},
                   "d": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "Yes"}},
              explore={"d": {"options": [opt("o1", "Yes"), opt("o2", "No")], "complete": True}},
              pick={"d": {"oids": ["o1"], "reason": "matched"}},
              apply={"Springfield": {"outcome": "unconfirmed"}, "Yes": {"outcome": "unconfirmed"}})
    assert statuses(out) == {"a": "unconfirmed", "d": "unconfirmed"}
    assert {"phase": "field", "fid": "d", "status": "unconfirmed"} in out["progress"]
    obs = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.buildLoopObservations(r)", out["report"])
    assert [o["outcome"] for o in obs] == ["unconfirmed", "unconfirmed"]


def test_a_reverted_field_gets_exactly_one_recommit(page, load):
    out = run(page, load, frames=[[f("a", question="City")]] * 4,
              map={"a": {"route": "slot", "slot": "personal.city", "value": "Springfield"}},
              sweep=[[{"fid": "a", "outcome": "reverted"}], [{"fid": "a", "outcome": "reverted"}], []])
    assert len(actions(out, "write")) == 2   # the first commit and ONE re-commit
    r = row(out, "a")
    assert (r["status"], r["lastOutcome"]) == ("unconfirmed", "unstable")
    assert r["answer"] == 'Companion filled "Springfield" twice and the page took it back both times. Check it.'


def test_a_recommit_runs_on_the_fields_remaining_time(page, load):
    """The sweep's re-commit gets no fresh clock: a field that spent its
    budget on the first commit is out of time, not written again — and is
    reported as a value the page took back, never "couldn't operate"."""
    out = run(page, load, frames=[[f("a", question="City")]] * 3, limits={"FIELD_MS": 300},
              pageDelay={"Springfield": 320},
              map={"a": {"route": "slot", "slot": "personal.city", "value": "Springfield"}},
              sweep=[[{"fid": "a", "outcome": "reverted"}], []])
    assert len(actions(out, "write")) == 1
    r = row(out, "a")
    assert (r["status"], r["lastOutcome"]) == ("unconfirmed", "timeout")
    assert r["answer"] == 'Companion filled "Springfield", then the page took it back. Check it.'



def test_every_proposal_source_shares_the_field_budget(page, load):
    """Round 1's commit spends most of the field's clock; round 2's retry
    (a quick commit, then the adaptive step) runs on what is left, never on a
    fresh FIELD_MS: some adaptive steps run, and the clock stops them before
    the 8 that would have verified."""
    states = [{"candidates": [{"mid": "scroll", "describe": "Scroll"}, GIVE_UP]} for _ in range(7)] + [
        {"candidates": [{"mid": "click:o1", "describe": 'Click the option "LinkedIn"'}, GIVE_UP]}]
    # Wide margins, for a slow machine: a fresh clock would leave 1500 ms for
    # 8 steps of ~100 ms (verified); the shared one leaves ~500 ms (about 4).
    out = run(page, load, frames=[[f("h", "popup", "How did you hear?")]] * 4, limits={"FIELD_MS": 1500},
              pageDelay={"Job Board": [1000, 0]}, apiDelay={"/api/autofill/step": 100},
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              explore={"h": {"options": [opt("o1", "Job Board")], "complete": True}},
              pick={"h": {"oids": ["o1"], "reason": "matched"}},
              apply={"Job Board": [{"outcome": "reverted"}, {"outcome": "unexpected", "reason": "new_options"}],
                     "scroll": {"outcome": "progressed"}, "click:o1": {"outcome": "verified"}},
              step={"states": states, "moves": [{"mid": "scroll", "reason": "progress"}] * 7
                    + [{"mid": "click:o1", "reason": "matched"}]})
    assert (row(out, "h")["status"], row(out, "h")["lastOutcome"]) == ("cannot_operate", "timeout")
    assert len(actions(out, "choose")) == 2
    assert 1 <= len(bodies(out, "/api/autofill/step")) < 8
    assert "click:o1" not in [a["mid"] for a in actions(out, "move")]


def test_a_failed_state_move_pair_is_not_retried(page, load):
    same = {"version": 1, "candidates": [{"mid": "click:o1", "describe": 'Click the option "Yes"'}, GIVE_UP]}
    out = run(page, load, frames=[[f("d", "popup", "Relocate?")]],
              map={"d": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "Yes"}},
              explore={"d": {"options": [opt("o1", "Yes")], "complete": True}},
              pick={"d": {"oids": [], "reason": "abstained"}},
              apply={"click:o1": {"outcome": "unexpected", "reason": "not_committed"}},
              step={"states": [same, dict(same)],
                    "moves": [{"mid": "click:o1", "reason": "matched"}, {"mid": "click:o1", "reason": "matched"},
                              {"mid": "give_up", "reason": "abstained"}]})
    assert [a["mid"] for a in actions(out, "move")] == ["click:o1", "give_up"]
    steps = bodies(out, "/api/autofill/step")
    assert steps[-1]["history"] == ["choose -> abstained", "click:o1 -> unexpected (not_committed)",
                                    "click:o1 -> already_failed"]
    assert all(HISTORY_ENTRY.match(e) for s in steps for e in s["history"])
    assert statuses(out) == {"d": "needs_answer"}


def test_a_widget_that_ignores_every_input_is_unsupported(page, load):
    """A press ignored, then the keyboard ignored: two different kinds."""
    out = run(page, load, frames=[[f("d", "popup", "Relocate?")]] * 3,
              map={"d": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "Yes"}},
              explore={"d": {"options": [], "complete": False, "error": "no_effect", "gestures": ["pointer"]}},
              apply={"open": {"outcome": "unexpected", "reason": "no_effect", "gestures": ["keyboard"]}},
              step={"states": [{"candidates": [{"mid": "open", "describe": "Open the dropdown"}, GIVE_UP]}],
                    "moves": [{"mid": "open", "reason": "progress"}]})
    assert statuses(out) == {"d": "unsupported"}
    assert [a["mid"] for a in actions(out, "move")] == ["open"]
    obs = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.buildLoopObservations(r)", out["report"])
    assert [o["outcome"] for o in obs] == ["unsupported"]


def test_the_same_value_refused_every_time_never_counts_twice(page, load):
    """A text box that takes neither typing nor the setter for this value
    (type=number given text) is retried as before and ends "couldn't
    operate" after its attempts — the same value twice is one gesture."""
    out = run(page, load, frames=[[f("n", question="Years")]] * 4,
              map={"n": {"route": "slot", "slot": "custom.years", "value": "ten"}},
              apply={"ten": {"outcome": "reverted", "reason": "no_effect", "gestures": ["type"]}})
    assert statuses(out) == {"n": "cannot_operate"}
    assert len(actions(out, "write")) == 3


def test_the_same_gesture_ignored_twice_is_not_unsupported(page, load):
    """Explore's press and the adaptive step's open are the same press: a
    widget that needed another kind of gesture is never called unsupported
    for ignoring one kind twice. And an effect in between starts over."""
    state = {"candidates": [{"mid": "open", "describe": "Open the dropdown"}, GIVE_UP]}
    out = run(page, load, frames=[[f("d", "popup", "Relocate?"), f("a", question="Code")]] * 3,
              map={"d": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "Yes"},
                   "a": {"route": "slot", "slot": "custom.code", "value": "ABC"}},
              explore={"d": {"options": [], "complete": False, "error": "no_effect", "gestures": ["pointer"]}},
              apply={"open": {"outcome": "unexpected", "reason": "no_effect", "gestures": ["pointer"]},
                     "ABC": [{"outcome": "reverted", "reason": "no_effect", "gestures": ["type"]},
                             {"outcome": "reverted"},
                             {"outcome": "reverted", "reason": "no_effect", "gestures": ["type"]}]},
              step={"states": [state, dict(state)],
                    "moves": [{"mid": "open", "reason": "progress"}, {"mid": "give_up", "reason": "abstained"}]})
    assert statuses(out) == {"d": "needs_answer", "a": "cannot_operate"}
    assert len(actions(out, "write")) == 3


def test_a_box_that_refuses_one_value_is_retried_not_unsupported(page, load):
    """A type=number box given text takes neither insertText nor the setter:
    that is the box refusing the VALUE. One write is one gesture — retried as
    before, never unsupported for it."""
    out = run(page, load, frames=[[f("n", question="Years")]] * 3,
              map={"n": {"route": "slot", "slot": "custom.years", "value": "ten"}},
              apply={"ten": [{"outcome": "reverted", "reason": "no_effect", "gestures": ["type"]}, {"outcome": "verified"}]})
    assert statuses(out) == {"n": "verified"}
    assert len(actions(out, "write")) == 2


def test_a_keyboard_open_that_committed_is_left_for_the_user(page, load):
    out = run(page, load, frames=[[f("d", "popup", "Relocate?")]] * 2,
              map={"d": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "No"}},
              explore={"d": {"options": [opt("o1", "Yes"), opt("o2", "No")], "complete": True}},
              pick={"d": {"oids": ["o2"], "reason": "matched"}},
              apply={"No": {"outcome": "unexpected", "reason": "committed_while_opening", "committed": "Yes"}})
    r = row(out, "d")
    assert (r["status"], r["lastOutcome"]) == ("needs_answer", "committed_while_opening")
    assert r["answer"] == 'Opening the list picked "Yes" and Companion couldn\'t take it back. Check it.'
    assert len(actions(out, "choose")) == 1 and "fill_step_state" not in out["calls"]
    obs = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.buildLoopObservations(r)", out["report"])
    assert [o["outcome"] for o in obs] == ["filled_unverified"]


def test_two_refusals_in_a_row_end_the_adaptive_step(page, load):
    same = {"version": 1, "candidates": [{"mid": "click:o1", "describe": 'Click the option "Yes"'}, GIVE_UP]}
    out = run(page, load, frames=[[f("d", "popup", "Relocate?")]],
              map={"d": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "Yes"}},
              explore={"d": {"options": [opt("o1", "Yes")], "complete": True}},
              pick={"d": {"oids": [], "reason": "abstained"}},
              apply={"click:o1": {"outcome": "unexpected", "reason": "not_committed"}},
              step={"states": [same, dict(same)], "moves": [{"mid": "click:o1", "reason": "matched"}] * 4})
    assert [a["mid"] for a in actions(out, "move")] == ["click:o1", "give_up"]
    assert len(bodies(out, "/api/autofill/step")) == 3
    assert (row(out, "d")["status"], row(out, "d")["lastOutcome"]) == ("needs_answer", "abstained")


def test_a_recommit_whose_explore_left_another_value_names_that_value(page, load):
    """The page took "UT Arlington" back; exploring for the re-commit left
    "UT Austin" behind. The note names what the field holds now — never
    "filled UT Arlington, then the page took it back"."""
    out = run(page, load, frames=[[f("k", "search", "School")]] * 3,
              map={"k": {"route": "slot", "slot": "education.0.school", "value": "UT Arlington"}},
              explore={"UT Arlington": [{"options": [opt("o1", "UT Arlington")], "multi": False},
                                        {"options": [], "error": "committed_while_exploring", "committed": "UT Austin"}]},
              pick={"k": {"oids": ["o1"], "reason": "matched"}},
              sweep=[[{"fid": "k", "outcome": "reverted"}], []])
    r = row(out, "k")
    assert (r["status"], r["lastOutcome"]) == ("needs_answer", "committed_while_exploring")
    assert r["answer"] == 'Searching picked "UT Austin" and Companion couldn\'t take it back. Check it.'
    obs = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.buildLoopObservations(r)", out["report"])
    assert [o["outcome"] for o in obs] == ["filled_unverified"]


def test_a_recommit_that_does_not_commit_still_says_the_page_took_it_back(page, load):
    out = run(page, load, frames=[[f("d", "popup", "Relocate?")]] * 3,
              map={"d": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "Yes"}},
              explore={"d": {"options": [opt("o1", "Yes"), opt("o2", "No")], "complete": True}},
              pick={"d": {"oids": ["o1"], "reason": "matched"}},
              apply={"Yes": [{"outcome": "verified"}, {"outcome": "unexpected", "reason": "not_committed"}]},
              sweep=[[{"fid": "d", "outcome": "reverted"}], []])
    r = row(out, "d")
    assert (r["status"], r["answer"]) == ("unconfirmed", 'Companion filled "Yes", then the page took it back. Check it.')
    assert len(actions(out, "choose")) == 2


def test_a_failed_search_for_one_item_is_still_tried_for_the_next(page, load):
    """`search:value` reads the same for every item of a set; what it types
    does not. A search that failed for A is not a failed search for B."""
    search = {"candidates": [{"mid": "search:value", "describe": "Type the applicant value into the search box"}, GIVE_UP]}
    out = run(page, load, frames=[[f("k", "search", "Skills", multi=True)]],
              map={"k": {"route": "slot", "slot": "skills", "value": ["A", "B"]}},
              explore={"A": {"options": [], "error": "no_results"}, "B": {"options": [], "error": "no_results"}},
              apply={"search:value": {"outcome": "unexpected", "reason": "no_results"}},
              step={"states": [dict(search) for _ in range(4)],
                    "moves": [{"mid": "search:value", "reason": "progress"}, {"mid": "give_up", "reason": "abstained"},
                              {"mid": "search:value", "reason": "progress"}, {"mid": "give_up", "reason": "abstained"}]})
    assert [a["mid"] for a in actions(out, "move")] == ["search:value", "give_up", "search:value", "give_up"]
    assert [s["item"] for s in bodies(out, "/api/autofill/step")] == ["A", "A", "B", "B"]


def test_a_scroll_that_hit_the_end_is_tried_again_once_the_list_grew(page, load):
    scroll = [{"mid": "scroll", "describe": "Scroll the list to see more options"}, GIVE_UP]
    five = [opt(f"o{i}", f"Row {i}") for i in range(5)]
    out = run(page, load, frames=[[f("h", "popup", "How did you hear?")]],
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              explore={"h": {"options": [], "complete": False, "error": "empty_popup"}},
              apply={"scroll": [{"outcome": "unexpected", "reason": "list_end"}, {"outcome": "progressed"}]},
              step={"states": [{"options": five, "candidates": scroll},
                               {"options": five + [opt("o5", "Row 5")], "candidates": scroll},
                               {"options": five + [opt("o5", "Row 5")], "candidates": scroll}],
                    "moves": [{"mid": "scroll", "reason": "progress"}] * 2 + [{"mid": "give_up", "reason": "abstained"}]})
    assert [a["mid"] for a in actions(out, "move")] == ["scroll", "scroll", "give_up"]


def test_a_field_the_engine_filled_is_not_already_after_a_re_render(page, load):
    """Verified, then re-rendered under a new fid (its learnt single-answer
    rows forgotten, so its one pill reads as a list): the explore that follows
    finds it holding what the ENGINE wrote — still verified, never "already"."""
    out = run(page, load, frames=[[f("k", "search", "School", fp="school")],
                                  [f("k2", "search", "School", fp="school", committed=["UT Arlington"])]],
              map={"k": {"route": "slot", "slot": "education.0.school", "value": "UT Arlington"}},
              explore={"UT Arlington": {"options": [opt("o1", "UT Arlington")], "multi": False}},
              pick={"k": {"oids": ["o1"], "reason": "matched"}})
    assert statuses(out) == {"k2": "verified"}
    assert len(actions(out, "choose")) == 1


def test_a_commit_explore_could_not_take_back_is_left_for_the_user(page, load):
    out = run(page, load, frames=[[f("m", "search", "Minor")]] * 2,
              map={"m": {"route": "slot", "slot": "education.0.minor", "value": "Analytics"}},
              explore={"Analytics": {"options": [opt("o1", "Analytics")], "error": "committed_while_exploring",
                                     "committed": "Analytics"}})
    r = row(out, "m")
    assert (r["status"], r["lastOutcome"]) == ("needs_answer", "committed_while_exploring")
    assert r["answer"] == 'Searching picked "Analytics" and Companion couldn\'t take it back. Check it.'
    assert not actions(out) and "/api/autofill/pick" not in out["calls"]


# ---------- repeating sections: Add what the profile can fill (Task 7)


def work(n, **kw):
    """Work Experience entry n's Job Title and Company, as the inventory lists them."""
    sec = {"section": f"Work Experience {n}", "repeatIndex": n - 1}
    return [f(f"t{n}", question="Job Title", **sec, **kw), f(f"c{n}", question="Company", **sec, **kw)]


def section(sid="f-s1", heading="Work Experience", entries=1, filled=None, held=None, numbers=None):
    return {"sid": sid, "heading": heading, "entries": entries,
            "filled": filled if filled is not None else [False] * entries,
            "held": held if held is not None else [[]] * entries,
            "numbers": numbers if numbers is not None else list(range(1, entries + 1)), "add": "Add Another"}


JOBS = {"t1": {"route": "slot", "slot": "experience.0.title", "value": "Analyst"},
        "c1": {"route": "slot", "slot": "experience.0.employer", "value": "Acme"},
        "t2": {"route": "slot", "slot": "experience.1.title", "value": "Intern"},
        "c2": {"route": "slot", "slot": "experience.1.employer", "value": "Initech"}}


def adds(out):
    return [{k: m[k] for k in ("sid", "heading", "entries")} for m in out["sent"] if m["type"] == "fill_add"]


def test_the_loop_adds_entries_the_profile_can_fill_then_fills_them(page, load):
    out = run(page, load, frames=[work(1), work(1) + work(2)],
              sections=[[section(entries=1)], [section(entries=2)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 2, "order": [0, 1]}}, map=JOBS)
    # One press, on the view it was decided from, before anything is mapped.
    assert adds(out) == [{"sid": "f-s1", "heading": "Work Experience", "entries": 1}]
    calls = out["calls"]
    assert calls.index("fill_add") < calls.index("/api/autofill/map")
    # A full inventory after the add: the new entry's fields are mapped in the same round.
    assert calls[:calls.index("/api/autofill/map")].count("fill_inventory") == 2
    [first_map, *_] = bodies(out, "/api/autofill/map")
    assert [(x["fid"], x["repeat_index"]) for x in first_map["fields"]] == [("t1", 0), ("c1", 0), ("t2", 1), ("c2", 1)]
    assert statuses(out) == {"t1": "verified", "c1": "verified", "t2": "verified", "c2": "verified"}
    assert {a["fid"]: a["value"] for a in actions(out, "write")} == {
        "t1": "Analyst", "c1": "Acme", "t2": "Intern", "c2": "Initech"}
    # Headings and counts go out; kinds and counts come back — asked once per section.
    [ask] = bodies(out, "/api/autofill/sections")
    assert ask["sections"] == [{"sid": "f-s1", "heading": "Work Experience", "entries": 1, "filled": [False],
                                "held": [[]]}]
    # The report says what was added, by kind (value-free).
    assert out["report"]["sections"] == [{"heading": "Work Experience", "kind": "experience", "wanted": 2,
                                          "entries": 2, "added": 1, "outcome": "added", "reason": None}]


def test_an_entry_already_holding_data_counts_and_is_never_overwritten(page, load):
    held = work(1, committed="Acme", answered=True)
    out = run(page, load, frames=[held, held + work(2)],
              sections=[[section(entries=1, filled=[True], held=[["Acme", "Acme"]])],
                        [section(entries=2, filled=[True, False])]],
              kinds={"f-s1": {"kind": "experience", "wanted": 2, "order": [0, 1]}}, map=JOBS)
    # What the entry holds goes to the (local) backend, which reconciles it.
    [ask] = bodies(out, "/api/autofill/sections")
    assert ask["sections"][0]["held"] == [["Acme", "Acme"]]
    # The held entry counts as one of the two: one Add, never two.
    assert len(adds(out)) == 1
    # What it holds stays: never written over.
    assert statuses(out) == {"t1": "already", "c1": "already", "t2": "verified", "c2": "verified"}
    assert {a["fid"] for a in actions(out)} == {"t2", "c2"}
    # Two entries on the page already, one of them held: nothing to add.
    out = run(page, load, frames=[held + work(2)], sections=[[section(entries=2, filled=[True, False])]],
              kinds={"f-s1": {"kind": "experience", "wanted": 2, "order": [0, 1]}}, map=JOBS)
    assert adds(out) == [] and statuses(out)["t2"] == "verified"


def test_add_never_exceeds_what_the_profile_can_fill(page, load):
    # As many entries as the profile can fill: nothing is pressed.
    out = run(page, load, frames=[work(1)], sections=[[section(entries=1)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 1, "order": [0]}}, map=JOBS)
    assert adds(out) == [] and "fill_add" not in out["calls"]
    # More on the page than the profile has: never Add, never Delete.
    out = run(page, load, frames=[work(1) + work(2)], sections=[[section(entries=2)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 1, "order": [0]}}, map=JOBS)
    assert adds(out) == []
    # Two short: two presses, one at a time, each on the count the last one left.
    out = run(page, load, frames=[work(1), work(1) + work(2), work(1) + work(2) + work(3)],
              sections=[[section(entries=1)], [section(entries=3)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 3, "order": [0, 1, 2]}}, map=JOBS)
    assert [a["entries"] for a in adds(out)] == [1, 2]
    assert out["report"]["sections"][0]["added"] == 2
    # A section that is none of the profile's lists, or one the profile has
    # nothing for, gets nothing; a second section of the same kind gets nothing.
    out = run(page, load, frames=[work(1)],
              sections=[[section("f-s1", entries=1), section("f-s2", "Skills", 0), section("f-s3", "Languages", 1),
                         section("f-s4", "Relevant Experience", 0)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 1, "order": [0]}, "f-s3": {"kind": "languages", "wanted": 0},
                     "f-s4": {"kind": "experience", "wanted": 1, "order": [0]}}, map=JOBS)
    assert adds(out) == []


def test_entries_held_twice_add_nothing_and_the_report_says_why(page, load):
    """The backend found two entries holding the same profile job
    (app/services/autofill_sections): nothing is added."""
    out = run(page, load, frames=[work(1, committed="Initech", answered=True) + work(2, committed="Initech", answered=True)],
              sections=[[section(entries=2, filled=[True, True], held=[["Initech"], ["Initech"]])]],
              kinds={"f-s1": {"kind": "experience", "wanted": 2, "reason": "held_twice",
                              "order": [1, None]}}, map=JOBS)
    assert adds(out) == []
    assert out["report"]["sections"] == [{"heading": "Work Experience", "kind": "experience", "wanted": 2,
                                          "entries": 2, "added": 0, "outcome": None,
                                          "reason": "held_twice"}]


def test_each_entrys_fields_carry_the_profile_entry_it_was_placed_at(page, load):
    """/sections placed the page's entries by what they hold (`order`): entry 1
    is empty and entry 2 holds job #1, so entry 1 gets job #2 and the added
    entry 3 gets job #3. /map is told each field's `profile_entry`; a field in
    no listed section is told nothing."""
    held = work(2, committed="Acme", answered=True)
    out = run(page, load, frames=[work(1) + held, work(1) + held + work(3)],
              sections=[[section(entries=2, filled=[False, True], held=[[], ["Acme"]])],
                        [section(entries=3, filled=[False, True, False], held=[[], ["Acme"], []])]],
              kinds={"f-s1": {"kind": "experience", "wanted": 3, "order": [1, 0, 2]}},
              map=JOBS | {"city": {"route": "slot", "slot": "personal.city", "value": "Springfield"}})
    assert len(adds(out)) == 1
    [body] = bodies(out, "/api/autofill/map")
    assert {x["fid"]: x.get("profile_entry", "absent") for x in body["fields"]} == {
        "t1": 1, "c1": 1, "t3": 2, "c3": 2}
    # The section's kind goes with it: a fact of another kind is no entry's.
    assert {x["entry_kind"] for x in body["fields"]} == {"experience"}


def test_a_foreign_entry_and_one_past_the_order_are_placed_nowhere(page, load):
    """null in `order` (an entry holding a job the profile does not have), or
    an entry the order does not reach: sent as null, never absent, so /map
    puts nothing of the profile's there."""
    out = run(page, load, frames=[work(1) + work(2) + work(3)],
              sections=[[section(entries=3)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 3, "reason": "held_twice",
                              "order": [None, 0]}}, map=JOBS)
    [body] = bodies(out, "/api/autofill/map")
    assert {x["fid"]: x.get("profile_entry", "absent") for x in body["fields"]} == {
        "t1": None, "c1": None, "t2": 0, "c2": 0, "t3": None, "c3": None}


@pytest.mark.parametrize("order", ["absent", None])
def test_a_job_or_school_section_without_an_order_is_left_alone(page, load, order):
    """Jobs and schools are placed by profile entry: a response without an
    order for one is not page order, even with every entry empty — an Add by
    page order could pair a new entry with a profile entry missing a
    required fact. Nothing written, nothing added, a report line."""
    kinds = {"kind": "experience", "wanted": 2} | ({} if order == "absent" else {"order": order})
    out = run(page, load, frames=[work(1)], sections=[[section(entries=1)]], kinds={"f-s1": kinds}, map=JOBS)
    [body] = bodies(out, "/api/autofill/map")
    assert all(x["profile_entry"] is None and "entry_kind" not in x for x in body["fields"])
    assert adds(out) == [] and out["report"]["sections"][0]["reason"] == "unplaced"


def test_a_kind_placed_nowhere_never_adds_in_a_second_section(page, load):
    """The first Work Experience section is left alone (numbered 1, 3): its
    kind is spent. A second section read as the same kind ("Volunteer
    Experience") never presses Add — its entries' fields are placed nowhere,
    so an added entry would stand with its required fields blank."""
    vol = [f("v1", question="Organization", section="Volunteer Experience 1")]
    out = run(page, load, frames=[work(1) + work(3) + vol],
              sections=[[section("f-s1", entries=2, numbers=[1, 3]), section("f-s4", "Volunteer Experience", 1)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 3, "order": [0, 1, 2]},
                     "f-s4": {"kind": "experience", "wanted": 3, "order": [0, 1, 2]}}, map=JOBS)
    assert "fill_add" not in out["calls"]


@pytest.mark.parametrize("order", ["0,1", [0, "1"], [0, -1], [0, 1.5], [0, 21], [0] * 51])
def test_an_order_that_cannot_be_read_places_nothing(page, load, order):
    """A malformed order is not page order: page order is what can give an
    empty entry a job the page already shows. The section is left alone —
    placed nowhere, nothing added — and the report says so."""
    out = run(page, load, frames=[work(1)], sections=[[section(entries=1)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 2, "order": order}}, map=JOBS)
    [body] = bodies(out, "/api/autofill/map")
    assert [(x["profile_entry"], "entry_kind" in x) for x in body["fields"]] == [(None, False)] * 2
    assert adds(out) == [] and out["report"]["sections"][0]["reason"] == "unplaced"


@pytest.mark.parametrize("how", ["failed", "none", "a response without order"])
def test_a_section_with_held_entries_and_no_placement_is_left_alone(page, load, how):
    """No placement for a section — /sections failed or hung, the model read
    the heading as none, or a response without order — yet an entry
    holds data ([empty, "Acme"]): page order would give the empty entry job
    #1 again. Nothing is written in the section, nothing is added, and the
    report says the section was left."""
    held = work(2, committed="Acme", answered=True)
    kinds = {"failed": None, "none": {"kind": "none", "wanted": 0},
             "a response without order": {"kind": "experience", "wanted": 3}}[how]
    spec = {"apiHang": ["/api/autofill/sections"], "limits": {"API_MS": 200}} if kinds is None \
        else {"kinds": {"f-s1": kinds}}
    out = run(page, load, frames=[work(1) + held],
              sections=[[section(entries=2, filled=[False, True], held=[[], ["Acme"]])]], map=JOBS, **spec)
    [body] = bodies(out, "/api/autofill/map")
    assert [(x["fid"], x["profile_entry"], "entry_kind" in x) for x in body["fields"]] == [
        ("t1", None, False), ("c1", None, False)]
    assert actions(out) == [] and adds(out) == []
    assert statuses(out) == {"t1": "needs_answer", "c1": "needs_answer", "t2": "already", "c2": "already"}
    lines = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.sectionLines(r)", out["report"])
    assert lines == ["Work Experience: the items on the page couldn't be matched to your profile, so this "
                     "section was left for you."]


def test_a_section_with_only_empty_entries_and_no_placement_keeps_page_order(page, load):
    out = run(page, load, frames=[work(1) + work(2)], sections=[[section(entries=2)]],
              apiHang=["/api/autofill/sections"], limits={"API_MS": 200}, map=JOBS)
    [body] = bodies(out, "/api/autofill/map")
    assert all("profile_entry" not in x for x in body["fields"])
    assert statuses(out) == {"t1": "verified", "c1": "verified", "t2": "verified", "c2": "verified"}
    assert page.evaluate("(r) => window.careerStudioCompanion.fillLoop.sectionLines(r)", out["report"]) == []


@pytest.mark.parametrize("numbers", [[1, 3], [2, 1], [1], [0, 1]])
def test_a_section_numbered_out_of_step_with_its_entries_is_left_alone(page, load, numbers):
    """The backend places entries by their place on the page, the loop finds a
    field's entry by its title's number: a page numbering its two entries
    "1, 3" (or out of order, or not every one) would give an empty entry the
    job the next one holds. Unless the titles run 1..N in page order, the
    section is placed nowhere."""
    out = run(page, load, frames=[work(1) + work(3)], sections=[[section(entries=2, numbers=numbers)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 3, "order": [1, 0, 2]}}, map=JOBS)
    [body] = bodies(out, "/api/autofill/map")
    assert all(x["profile_entry"] is None and "entry_kind" not in x for x in body["fields"])
    assert adds(out) == [] and out["report"]["sections"][0]["reason"] == "unplaced"


def test_an_older_reason_word_is_still_understood(page, load):
    out = run(page, load, frames=[work(1)], sections=[[section(entries=1)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 1, "reason": "held_out_of_order", "order": [0]}},
              map=JOBS)
    assert out["report"]["sections"][0]["reason"] == "held_twice"


def language(n, **kw):
    """Languages entry n as Workday renders it (probed live 2026-09-26, Home
    Depot): a required Language popup, a lone "I am fluent in this language."
    checkbox (not required), and required Read / Speak / Write popups (Select
    One, Basic, Fluent, Intermediate). An added entry's fields are required
    too. Simplified: the test's explore offers the Language popup 2 options,
    not the 61 seen live."""
    sec = {"section": f"Languages {n}", "repeatIndex": n - 1}
    lang = {k: v for k, v in kw.items() if k in ("committed", "answered")}
    return [f(f"l{n}", "popup", "Language", required=True, **sec, **lang),
            f(f"fl{n}", "group", "I am fluent in this language.", committed="No",
              options=[opt("yes", "Yes"), opt("no", "No")], optionsComplete=True, **sec),
            *(f(f"{w[0]}{n}", "popup", w, required=True, **sec) for w in ("Read", "Speak", "Write"))]


def test_language_entries_are_added_and_placed_by_the_language_they_hold(page, load):
    """Two profile languages, one Language entry on the page already holding
    the SECOND (French): one Add, and each entry's fields carry the profile
    language /sections placed there — entry 1 French's, the added entry 2
    Spanish's — never Spanish's levels beside French."""
    held = language(1, committed="French", answered=True)
    out = run(page, load, frames=[held, held + language(2)],
              sections=[[section("f-s3", "Languages", 1, filled=[True], held=[["French"]])],
                        [section("f-s3", "Languages", 2, filled=[True, False], held=[["French"], []])]],
              kinds={"f-s3": {"kind": "languages", "wanted": 2, "order": [1, 0]}},
              map={"l2": {"route": "slot", "slot": "languages.0.language", "value": "Spanish"},
                   "R2": {"route": "slot", "slot": "languages.0.read", "value": "Fluent"}},
              explore={"l2": {"options": [opt("o1", "French"), opt("o2", "Spanish")], "complete": True},
                       "R2": {"options": [opt("o1", "Select One"), opt("o2", "Basic"), opt("o3", "Fluent"),
                                          opt("o4", "Intermediate")], "complete": True}},
              pick={"l2": {"oids": ["o2"], "reason": "matched"}, "R2": {"oids": ["o3"], "reason": "matched"}})
    assert adds(out) == [{"sid": "f-s3", "heading": "Languages", "entries": 1}]
    [body] = bodies(out, "/api/autofill/map")
    assert {x["fid"]: (x.get("profile_entry", "absent"), x.get("entry_kind")) for x in body["fields"]} == {
        "fl1": (1, "languages"), "R1": (1, "languages"), "S1": (1, "languages"), "W1": (1, "languages"),
        "l2": (0, "languages"), "fl2": (0, "languages"), "R2": (0, "languages"), "S2": (0, "languages"),
        "W2": (0, "languages")}
    assert statuses(out)["l1"] == "already"
    assert (statuses(out)["l2"], statuses(out)["R2"]) == ("verified", "verified")
    assert out["report"]["sections"] == [{"heading": "Languages", "kind": "languages", "wanted": 2,
                                          "entries": 2, "added": 1, "outcome": "added", "reason": None}]


def test_the_loops_entry_limits_mirror_the_backends():
    from typing import get_args

    from app.schemas.autofill_fill import MAX_ENTRY_INDEX, EntryKind

    loop = (EXTENSION / "shared" / "fill-loop.js").read_text(encoding="utf-8")
    assert re.search(r"const MAX_ENTRY_INDEX = (\d+);", loop).group(1) == str(MAX_ENTRY_INDEX)
    kinds = re.search(r"const PLACED_KINDS = new Set\(\[(.*?)\]\);", loop).group(1)
    assert set(re.findall(r'"([a-z]+)"', kinds)) == set(get_args(EntryKind))


def test_two_sections_of_a_kind_are_both_placed_nowhere(page, load):
    """A second section the backend reads as work experience ("Volunteer
    Experience", misread) makes the kind ambiguous: which one is misread
    cannot be told, so neither is given job #1 (owner, 2026-09-27). A section
    of another kind keeps its order."""
    vol = [f("v1", question="Organization", section="Volunteer Experience 1")]
    school = [f("s1", question="School", section="Education 1")]
    out = run(page, load, frames=[work(1) + vol + school],
              sections=[[section("f-s1", entries=1), section("f-s4", "Volunteer Experience", 1),
                         section("f-s5", "Education", 1)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 1, "order": [0]},
                     "f-s4": {"kind": "experience", "wanted": 1, "order": [0]},
                     "f-s5": {"kind": "education", "wanted": 1, "order": [0]}}, map=JOBS)
    [body] = bodies(out, "/api/autofill/map")
    assert {x["fid"]: (x.get("profile_entry", "absent"), x.get("entry_kind")) for x in body["fields"]} == {
        "t1": (None, None), "c1": (None, None), "v1": (None, None), "s1": (0, "education")}


def test_a_section_left_to_the_user_says_so(page, load):
    """held_unmatched: an entry holds a job the profile does not have. Nothing
    is added, and the report carries the reason even with nothing to add."""
    out = run(page, load, frames=[work(1, committed="TCS", answered=True) + work(2)],
              sections=[[section(entries=2, filled=[True, False], held=[["TCS"], []])]],
              kinds={"f-s1": {"kind": "experience", "wanted": 2, "reason": "held_unmatched",
                              "order": [None, None]}}, map=JOBS)
    assert adds(out) == []
    assert out["report"]["sections"][0]["reason"] == "held_unmatched"
    lines = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.sectionLines(r)", out["report"])
    assert lines == ["Work Experience: the items on the page don't match your profile, so this section was left "
                     "for you."]


def site(n, **kw):
    return f(f"u{n}", question="URL", section=f"Websites {n}", repeatIndex=n - 1, **kw)


WEBSITES = [[section("f-s2", "Websites", 2)]]  # the section fill_sections returned; no kind, no Add


def test_one_fact_is_never_written_into_two_entries_of_a_section(page, load):
    """personal.website carries no entry number, so /map can hand the same
    fact to both Websites entries: the second entry's field is left for the
    user, never written."""
    out = run(page, load, frames=[[site(1), site(2)]], sections=WEBSITES,
              map={"u1": {"route": "slot", "slot": "personal.website", "value": "https://ada.dev"},
                   "u2": {"route": "slot", "slot": "personal.website", "value": "https://ada.dev"}})
    assert [a["fid"] for a in actions(out)] == ["u1"]
    assert (row(out, "u2")["status"], row(out, "u2")["lastOutcome"]) == ("needs_answer", "in_another_entry")
    # Nor a fact another entry already HOLDS (the user's, a parsed resume's).
    out = run(page, load, frames=[[site(1, committed="https://GitHub.com/ada ", answered=True), site(2)]],
              sections=WEBSITES,
              map={"u2": {"route": "slot", "slot": "personal.github", "value": "https://github.com/ada"}})
    assert actions(out) == [] and row(out, "u2")["lastOutcome"] == "in_another_entry"
    # A URL is the same URL whatever its scheme, `www.`, host case, default
    # port, trailing slash or #fragment.
    for held, fact in (("Example.dev/", "https://www.example.dev"),
                       ("example.dev/#top", "https://example.dev:443/"),
                       ("http://example.dev:80/about", "example.dev/about/")):
        out = run(page, load, frames=[[site(1, committed=held, answered=True), site(2)]], sections=WEBSITES,
                  map={"u2": {"route": "slot", "slot": "personal.website", "value": fact}})
        assert actions(out) == [] and row(out, "u2")["lastOutcome"] == "in_another_entry", (held, fact)
    # A different fact in the second entry is written.
    out = run(page, load, frames=[[site(1), site(2)]], sections=WEBSITES,
              map={"u1": {"route": "slot", "slot": "personal.website", "value": "https://ada.dev"},
                   "u2": {"route": "slot", "slot": "personal.github", "value": "https://github.com/ada"}})
    assert statuses(out) == {"u1": "verified", "u2": "verified"}


def test_one_fact_per_entry_holds_only_in_a_section_the_page_lists(page, load):
    """Numbered titles that are not a repeating section the page listed
    ("Question 1", "Step 2") are not entries: the same answer is written in
    each, and a confirm-email box is written with the email the other holds."""
    yes_no = [opt("o1", "Yes"), opt("o2", "No")]
    q = lambda n: f(f"q{n}", "group", "Are you 18 or older?", section=f"Question {n}", repeatIndex=n - 1,  # noqa: E731
                    options=yes_no, optionsComplete=True)
    out = run(page, load, frames=[[q(1), q(2)]], sections=WEBSITES,
              map={f"q{n}": {"route": "slot", "slot": "eligibility.over_18", "value": "Yes"} for n in (1, 2)},
              pick={"q1": {"oids": ["o1"], "reason": "matched"}, "q2": {"oids": ["o1"], "reason": "matched"}})
    assert statuses(out) == {"q1": "verified", "q2": "verified"}
    # Even with a "Step" section listed: "Step 2" is never an entry title.
    out = run(page, load, frames=[[f("e1", question="Email", section="Step 1", committed="a@b.test", answered=True),
                                   f("e2", question="Confirm email", section="Step 2", repeatIndex=1)]],
              sections=[[section("f-s2", "Step", 2)]],
              map={"e2": {"route": "slot", "slot": "personal.email", "value": "a@b.test"}})
    assert statuses(out) == {"e1": "already", "e2": "verified"}


def test_the_same_value_in_numbered_entries_of_different_facts_is_written(page, load):
    """Two jobs can share a title: entry-numbered facts (experience.0 / .1)
    are different facts, whatever their values."""
    out = run(page, load, frames=[work(1, committed="Analyst", answered=True)[:1] + work(2)[:1]],
              map={"t2": {"route": "slot", "slot": "experience.1.title", "value": "Analyst"}})
    assert statuses(out) == {"t1": "already", "t2": "verified"}


def test_an_add_that_did_not_grow_the_section_is_pressed_once(page, load):
    """A deliberate write, never a trial: a press that added nothing is not
    pressed again — not for the next wanted entry, not in a later round."""
    out = run(page, load, frames=[work(1)], sections=[[section(entries=1)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 3, "order": [0, 1, 2]}},
              add={"f-s1": {"outcome": "not_added", "entries": 1}}, map=JOBS)
    assert len(adds(out)) == 1
    assert out["report"]["sections"] == [{"heading": "Work Experience", "kind": "experience", "wanted": 3,
                                          "entries": 1, "added": 0, "outcome": "not_added", "reason": None}]
    assert statuses(out) == {"t1": "verified", "c1": "verified"}
    # The page answering "added" without the count growing is not an entry either.
    out = run(page, load, frames=[work(1)], sections=[[section(entries=1)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 2, "order": [0, 1]}},
              add={"f-s1": {"outcome": "added", "entries": 1}}, map=JOBS)
    assert len(adds(out)) == 1 and out["report"]["sections"][0]["added"] == 0


def test_a_stopped_run_never_presses_add(page, load):
    out = run(page, load, frames=[work(1)], sections=[[section(entries=1)]], stopOnSections=True,
              kinds={"f-s1": {"kind": "experience", "wanted": 2, "order": [0, 1]}}, map=JOBS)
    assert "fill_add" not in out["calls"] and out["report"]["stopped"] is True


def test_sections_the_backend_could_not_classify_add_nothing(page, load):
    out = run(page, load, frames=[work(1)], sections=[[section(entries=1)]], apiHang=["/api/autofill/sections"],
              limits={"API_MS": 200}, map=JOBS)
    assert "fill_add" not in out["calls"]
    assert statuses(out) == {"t1": "verified", "c1": "verified"}
    # Asked once per run, not once a round: a hung backend costs one wait.
    assert out["calls"].count("fill_sections") >= 2 and out["calls"].count("/api/autofill/sections") == 1


def test_a_section_re_rendered_after_a_failed_add_is_not_pressed_again(page, load):
    """A press that added nothing is remembered by the section's frame and
    heading, not only its sid: the page re-rendering it under a new sid does
    not buy a second press, nor a second report row."""
    out = run(page, load, frames=[work(1)], sections=[[section("f-s1", entries=1)], [section("f-s9", entries=1)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 2, "order": [0, 1]}, "f-s9": {"kind": "experience", "wanted": 2, "order": [0, 1]}},
              add={"f-s1": {"outcome": "not_added", "entries": 1}}, map=JOBS)
    assert out["calls"].count("fill_sections") >= 2
    assert adds(out) == [{"sid": "f-s1", "heading": "Work Experience", "entries": 1}]
    assert [(r["heading"], r["outcome"]) for r in out["report"]["sections"]] == [("Work Experience", "not_added")]


# ---------- the wire


def test_every_page_message_the_loop_sends_is_a_page_handler():
    loop = (EXTENSION / "shared" / "fill-loop.js").read_text(encoding="utf-8")
    agent = (EXTENSION / "content" / "agent.js").read_text(encoding="utf-8")
    block = re.search(r"const PAGE_HANDLERS = \{(.*?)\n  \};", agent, re.S)
    handled = set(re.findall(r"^    ([a-z_]+):", block.group(1), re.M))
    sent = set(re.findall(r'\btype:\s*"([a-z_]+)"', loop))
    assert sent == {"fill_inventory", "fill_explore", "fill_apply", "fill_step_state", "fill_sweep", "fill_sections",
                    "fill_add"}
    assert sent <= handled


def test_the_loop_reads_repeated_titles_by_the_field_readers_rule():
    """The loop runs in the panel, where field-reader.js never loads, so it
    keeps a MIRROR of `ns.repeatOf`'s two patterns: they must stay identical."""
    reader = (EXTENSION / "content" / "field-reader.js").read_text(encoding="utf-8")
    loop = (EXTENSION / "shared" / "fill-loop.js").read_text(encoding="utf-8")
    for name in ("REPEAT", "NOT_REPEAT"):
        pattern = re.compile(rf"const {name} = (/.*?/[a-z]*);")
        assert pattern.search(reader).group(1) == pattern.search(loop).group(1), name


def test_the_panel_loads_the_loop_after_the_guided_runner():
    html = (Path(EXTENSION) / "panel" / "panel.html").read_text(encoding="utf-8")
    srcs = re.findall(r'<script src="([^"]+)"></script>', html)
    assert srcs.index("../shared/fill-loop.js") == srcs.index("../shared/guided-run.js") + 1


# ---------- telemetry (Task 8)


def test_a_real_report_becomes_value_free_observations(page, load):
    out = run(page, load, frames=[[f("a", question="City"), f("d", "popup", "Authorized?"),
                                   f("u", "unknown", "Mystery")]],
              map={"a": {"route": "slot", "slot": "personal.city", "value": "Springfield"},
                   "d": {"route": "slot", "slot": "work_auth.authorized_now", "value": "Yes"}},
              explore={"d": {"options": [opt("o1", "Yes"), opt("o2", "No")], "complete": True}},
              pick={"d": {"oids": ["o1"], "reason": "matched"}})
    obs = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.buildLoopObservations(r)", out["report"])
    assert obs == [
        {"label": "City", "kind": "text", "host": "x.test", "outcome": "verified", "rule_id": "slot:personal.city"},
        {"label": "Authorized?", "kind": "combobox", "host": "x.test", "outcome": "verified",
         "rule_id": "slot:work_auth.authorized_now"},
        {"label": "Mystery", "kind": "text", "host": "x.test", "outcome": "cannot_operate", "rule_id": None},
    ]
    assert "Springfield" not in str(obs)


def test_an_observation_label_never_carries_the_value_written(page, load):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    report = {"host": "x.test", "fields": [
        {"fid": "a", "question": "Country: United States", "shape": "popup", "status": "verified",
         "answer": "united states", "route": "slot", "slot": "personal.country", "lastOutcome": "verified"},
        {"fid": "b", "question": "Phone number", "shape": "text", "status": "verified",
         "answer": "No", "route": "slot", "slot": "x", "lastOutcome": "verified"},
        {"fid": "c", "question": "Start date: Next week", "shape": "popup", "status": "needs_answer",
         "answer": 'Companion clicked "Next week". Check it.', "route": "slot", "slot": "y",
         "lastOutcome": "group_committed"},
    ]}
    obs = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.buildLoopObservations(r)", report)
    # Blanked when it holds the value (whole words, any case); a word inside
    # another word ("No" in "number") is not the value.
    assert [o["label"] for o in obs] == ["", "Phone number", ""]


# ---------- the reasoning route (plan Task 9b): /pick's alone, never /step's

GOVERNMENT = "Are you currently, or have you within the last five years been, employed by a US government agency?"


def test_a_reasoned_popup_is_picked_with_its_route_and_listed_to_check(page, load):
    out = run(page, load, frames=[[f("g", "popup", GOVERNMENT)]], map={"g": {"route": "reasoned"}},
              explore={"g": {"options": [opt("o1", "Yes"), opt("o2", "No")], "complete": True}},
              pick={"g": {"oids": ["o2"], "reason": "assumed"}})
    assert statuses(out) == {"g": "assumed"}
    [pick] = bodies(out, "/api/autofill/pick")
    [field] = pick["fields"]
    assert (field["route"], field["slot"]) == ("reasoned", None)


def test_a_reasoned_native_list_is_picked_with_the_others(page, load):
    out = run(page, load, frames=[[f("s", "select", "Do you hold a US Security Clearance?",
                                     options=[opt("o1", "Yes"), opt("o2", "No")], optionsComplete=True)]],
              map={"s": {"route": "reasoned"}}, pick={"s": {"oids": ["o1"], "reason": "assumed"}})
    assert statuses(out) == {"s": "assumed"}
    assert "fill_explore" not in out["calls"]
    assert [x["route"] for b in bodies(out, "/api/autofill/pick") for x in b["fields"]] == ["reasoned"]


@pytest.mark.parametrize("case", ["abstained", "unexpected", "no_options"])
def test_a_reasoned_field_the_pick_did_not_finish_is_the_users_never_stepped(page, load, case):
    """/step has no history to answer from: a reasoned abstain is left for the user."""
    explore = {} if case == "no_options" else {
        "g": {"options": [opt("o1", "Yes"), opt("o2", "No")], "complete": True}}
    pick = {"g": {"oids": ["o2"], "reason": "assumed"} if case == "unexpected" else {"oids": [], "reason": "abstained"}}
    out = run(page, load, frames=[[f("g", "popup", GOVERNMENT)]], map={"g": {"route": "reasoned"}},
              explore=explore, pick=pick, apply={"No": {"outcome": "unexpected", "reason": "new_options"}})
    # An unexpected commit is retried like a native list's, then given up.
    assert statuses(out)["g"] == ("cannot_operate" if case == "unexpected" else "needs_answer")
    assert "fill_step_state" not in out["calls"] and "/api/autofill/step" not in out["calls"]


@pytest.mark.parametrize("route", [{"route": "slot", "slot": "work_auth.authorized_now", "value": "Yes"},
                                   {"route": "low_stakes"}])
def test_a_list_with_no_options_still_goes_to_the_step_on_the_other_routes(page, load, route):
    """Only the reasoning route stops at "no options": a select or group on a
    slot or low-stakes route keeps its step, as before."""
    out = run(page, load, frames=[[f("x", "select", "Authorized?")]], map={"x": route})
    assert out["calls"].count("fill_step_state") == 1


# ---------- recipes (revision Task 11): a learned move order, value-free, via deps.recipes

RECIPE = {"family": "f:fam1", "site": "s:sitea"}
KEYS_FIRST = {"open": ["keys", "press"]}
LEARNED = {"f:fam1": {"key": "s:sitea", "variant": KEYS_FIRST}}


# The page's sweep re-checked the field and found it holding (fill-ops `held`).
HELD = [{"fid": "d", "outcome": "verified", "held": True}]


def popup_run(page, load, **kw):
    """One popup field whose widget family has a recipe key; by default every
    sweep re-checks it and finds it holding."""
    kw.setdefault("sweep", [HELD])
    kw.setdefault("frames", [[f("d", "popup", "Willing to travel?", recipe=RECIPE)]])
    kw.setdefault("explore", {"d": {"options": [opt("o1", "Yes"), opt("o2", "No")], "complete": True}})
    kw.setdefault("pick", {"d": {"oids": ["o1"], "reason": "matched"}})
    return run(page, load, map={"d": {"route": "slot", "slot": "preferences.travel", "value": "Yes"}}, **kw)


def variants(out):
    """Every variant order the loop sent to the page, by operation."""
    explores = [r.get("variant") for m in out["sent"] if m["type"] == "fill_explore" for r in m["requests"]]
    return {"explore": explores, **{op: [a.get("variant") for a in actions(out, op)] for op in ("choose", "set", "write")}}


def test_a_learned_order_rides_with_the_fields_explore_and_its_commit(page, load):
    out = popup_run(page, load, recipes={"book": LEARNED},
                    apply={"Yes": {"outcome": "verified", "variant": {"open": "keys"}}})
    assert statuses(out) == {"d": "verified"}
    assert out["gets"] == [RECIPE]
    assert variants(out) == {"explore": [KEYS_FIRST], "choose": [KEYS_FIRST], "set": [], "write": []}
    assert out["lessons"] == [{"recipe": RECIPE, "used": "s:sitea", "moves": {"open": "keys"}, "outcome": "kept"}]


def test_a_move_the_generic_order_found_is_handed_to_the_book(page, load):
    out = popup_run(page, load, recipes={}, apply={"Yes": {"outcome": "verified", "variant": {"open": "keys"}}})
    assert variants(out) == {"explore": [None], "choose": [None], "set": [], "write": []}
    assert out["lessons"] == [{"recipe": RECIPE, "used": None, "moves": {"open": "keys"}, "outcome": "kept"}]


def test_a_value_the_sweep_found_reverted_is_a_contradiction_never_a_move(page, load):
    """Verified, then reverted before the final sweep, re-committed and held:
    the field is filled, and the move that verified it first is NOT learned."""
    out = popup_run(page, load, recipes={"book": LEARNED}, sweep=[[{"fid": "d", "outcome": "reverted"}], HELD],
                    apply={"Yes": {"outcome": "verified", "variant": {"open": "keys"}}})
    assert statuses(out) == {"d": "verified"}
    assert out["lessons"] == [{"recipe": RECIPE, "used": "s:sitea", "moves": {"open": "keys"},
                               "outcome": "contradicted"}]


def test_an_unconfirmed_pick_is_a_contradiction(page, load):
    out = popup_run(page, load, recipes={"book": LEARNED},
                    apply={"Yes": {"outcome": "unconfirmed", "variant": {"open": "keys"}}})
    assert statuses(out) == {"d": "unconfirmed"}
    assert [x["outcome"] for x in out["lessons"]] == ["contradicted"]


def test_a_learned_move_the_control_could_not_take_is_a_mismatch(page, load):
    out = popup_run(page, load, recipes={"book": LEARNED},
                    apply={"Yes": {"outcome": "verified", "variant": {"open": "press"}, "mismatch": "open"}})
    assert statuses(out) == {"d": "verified"}
    assert out["lessons"] == [{"recipe": RECIPE, "used": "s:sitea", "moves": {"open": "press"}, "outcome": "mismatch"}]


def test_a_value_the_final_sweep_could_not_recheck_teaches_nothing(page, load):
    """Verified, but the final sweep never re-checked it (the page could no
    longer resolve the element, so it reported nothing): no lesson at all —
    not reported reverted is not the same as found holding."""
    out = popup_run(page, load, recipes={"book": LEARNED}, sweep=[[]],
                    apply={"Yes": {"outcome": "verified", "variant": {"open": "keys"}}})
    assert statuses(out) == {"d": "verified"}
    assert out["lessons"] is None


def test_a_revert_is_a_contradiction_even_when_the_final_sweep_cannot_recheck(page, load):
    """Seen reverting, re-committed, then gone from the final sweep's view
    (element gone, or re-rendered under a new fid): the revert was observed,
    so it still demotes the recipe; only a `kept` needs the final re-check."""
    out = popup_run(page, load, recipes={"book": LEARNED}, sweep=[[{"fid": "d", "outcome": "reverted"}], []],
                    apply={"Yes": {"outcome": "verified", "variant": {"open": "keys"}}})
    assert statuses(out) == {"d": "verified"}
    assert out["lessons"] == [{"recipe": RECIPE, "used": "s:sitea", "moves": {"open": "keys"},
                               "outcome": "contradicted"}]


def test_a_page_gone_before_the_final_sweep_teaches_nothing(page, load):
    """The page answered a round's sweep, then went away: the final sweep
    reached no frame, so nothing is recorded — whatever the earlier sweep said."""
    out = popup_run(page, load, recipes={"book": LEARNED},
                    frames=[[f("d", "popup", "Willing to travel?", recipe=RECIPE)], None],
                    apply={"Yes": {"outcome": "verified", "variant": {"open": "keys"}}})
    assert statuses(out) == {"d": "verified"}
    assert out["calls"].count("fill_sweep") >= 2
    assert out["lessons"] is None


@pytest.mark.parametrize("failure", [
    {"outcome": "unexpected", "reason": "committed_while_opening"},
    {"outcome": "unexpected", "reason": "unsettled"},
    {"outcome": "unexpected", "reason": "no_popup"},
    {"outcome": "unexpected", "reason": "no_effect", "gestures": ["keyboard"]},
])
def test_a_recipe_under_which_the_commit_failed_outright_is_contradicted(page, load, failure):
    """No verified or unconfirmed value to learn from, but the learned order
    was in use and the commit failed: that demotes the recipe tried (moves
    empty, so the family is not taught anything)."""
    out = popup_run(page, load, recipes={"book": LEARNED}, apply={"Yes": failure})
    assert out["lessons"] == [{"recipe": RECIPE, "used": "s:sitea", "moves": {}, "outcome": "contradicted"}]


def test_a_recipe_under_which_the_explore_committed_is_contradicted(page, load):
    """The harm case, earliest: a keys-first explore whose keys picked a value
    the page would not give back. The field is left to the user, and the
    recipe tried is demoted."""
    out = popup_run(page, load, recipes={"book": LEARNED}, explore={"d": {
        "options": [], "complete": False, "error": "committed_while_exploring", "committed": "No"}})
    assert statuses(out) == {"d": "needs_answer"}
    assert out["lessons"] == [{"recipe": RECIPE, "used": "s:sitea", "moves": {}, "outcome": "contradicted"}]


def test_an_adaptive_step_that_failed_is_not_the_recipes_fault(page, load):
    """The pick abstains and the adaptive step takes over: its moves carry no
    recipe order, so a move that finds no popup demotes nothing."""
    out = popup_run(page, load, recipes={"book": LEARNED}, pick={"d": {"oids": [], "reason": "abstained"}},
                    apply={"open": {"outcome": "unexpected", "reason": "no_popup"}},
                    step={"states": [{"candidates": [{"mid": "open", "describe": "Open the dropdown"}, GIVE_UP]}],
                          "moves": [{"mid": "open", "reason": "progress"}]})
    assert any(a["op"] == "move" and a["mid"] == "open" for a in actions(out, "move"))
    assert out["lessons"] is None


def test_an_outright_failure_with_no_recipe_in_use_teaches_nothing(page, load):
    out = popup_run(page, load, recipes={}, apply={"Yes": {"outcome": "unexpected", "reason": "committed_while_opening"}})
    assert out["lessons"] is None


def test_a_set_whose_items_opened_differently_is_not_learned_as_one_move(page, load):
    kw = dict(frames=[[f("k", "search", "Skills", multi=True, recipe=RECIPE)]],
              map={"k": {"route": "slot", "slot": "skills", "value": ["SQL", "Python"]}},
              explore={"SQL": {"options": [opt("o1", "SQL")]}, "Python": {"options": [opt("o1", "Python")]}},
              pick={"k:SQL": {"oids": ["o1"], "reason": "matched"}, "k:Python": {"oids": ["o1"], "reason": "matched"}},
              apply={"SQL+Python": {"outcome": "verified", "variant": {"open": "keys"}, "varied": ["open"]}},
              sweep=[[{"fid": "k", "outcome": "verified", "held": True}]])
    assert run(page, load, recipes={}, **kw)["lessons"] is None
    out = run(page, load, recipes={"book": LEARNED}, **kw)
    assert out["lessons"] == [{"recipe": RECIPE, "used": "s:sitea", "moves": {}, "outcome": "contradicted"}]


def test_a_set_carries_the_learned_order(page, load):
    out = run(page, load, frames=[[f("k", "search", "Skills", multi=True, recipe=RECIPE)]],
              map={"k": {"route": "slot", "slot": "skills", "value": ["SQL", "Python"]}},
              explore={"SQL": {"options": [opt("o1", "SQL")]}, "Python": {"options": [opt("o1", "Python")]}},
              pick={"k:SQL": {"oids": ["o1"], "reason": "matched"}, "k:Python": {"oids": ["o1"], "reason": "matched"}},
              recipes={"book": LEARNED})
    assert statuses(out) == {"k": "verified"}
    assert variants(out) == {"explore": [KEYS_FIRST, KEYS_FIRST], "choose": [], "set": [KEYS_FIRST], "write": []}


def test_deliberate_writes_never_consult_a_recipe(page, load):
    """Text (a signature box among them) and passive choices (a consent tick
    among them) are written once, on a decision: never reordered, never
    looked up — even carrying a recipe key."""
    yes_no = [opt("o1", "Yes"), opt("o2", "No")]
    out = run(page, load, frames=[[
        f("t", "text", "City", recipe=RECIPE),
        f("s", "select", "Country", recipe=RECIPE, options=[opt("o1", "Canada")], optionsComplete=True),
        f("c", "group", "I agree to the terms", recipe=RECIPE, options=yes_no, optionsComplete=True),
    ]], map={"t": {"route": "slot", "slot": "personal.city", "value": "Springfield"},
             "s": {"route": "slot", "slot": "personal.country", "value": "Canada"},
             "c": {"route": "slot", "slot": "consent.terms", "value": "Yes"}},
        pick={"s": {"oids": ["o1"], "reason": "matched"}, "c": {"oids": ["o1"], "reason": "matched"}},
        recipes={"book": LEARNED})
    assert statuses(out) == {"t": "verified", "s": "verified", "c": "verified"}
    assert out["gets"] == [] and out["lessons"] in (None, [])
    assert all(v is None for vs in variants(out).values() for v in vs)


def test_a_stopped_run_learns_nothing(page, load):
    out = popup_run(page, load, recipes={"book": LEARNED}, stopAfterApply=True,
                    apply={"Yes": {"outcome": "verified", "variant": {"open": "keys"}}})
    assert out["report"]["stopped"] is True and out["lessons"] is None


def test_a_recipe_store_that_fails_costs_the_fill_nothing(page, load):
    out = popup_run(page, load, recipes={"fail": True},
                    apply={"Yes": {"outcome": "verified", "variant": {"open": "keys"}}})
    assert statuses(out) == {"d": "verified"}
    assert variants(out) == {"explore": [None], "choose": [None], "set": [], "write": []}


def test_without_a_recipe_store_no_order_is_sent(page, load):
    out = popup_run(page, load, apply={"Yes": {"outcome": "verified", "variant": {"open": "keys"}}})
    assert statuses(out) == {"d": "verified"}
    assert variants(out) == {"explore": [None], "choose": [None], "set": [], "write": []}


# ---------- a date written into ONE part of a date (iCIMS, live 2026-10-01)
# /map says a slot is a date (`format: "date"`, the slot's); the inventory says
# a control holds one part (`part`, the field reader's). The loop writes only
# that part: live, a Year box was given "2026-06".
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def dated(value="2026-06", slot="experience.0.start"):
    return {"route": "slot", "slot": slot, "value": value, "format": "date"}


def test_a_year_box_gets_the_year_and_a_month_box_the_month(page, load):
    out = run(page, load, frames=[[f("y", question="Start: Year", part="year"),
                                   f("m", question="Start: Month", part="month")]],
              map={"y": dated(), "m": dated()})
    assert statuses(out) == {"y": "verified", "m": "verified"}
    assert {a["fid"]: a["value"] for a in actions(out, "write")} == {"y": "2026", "m": "06"}
    assert all("format" not in a for a in actions(out, "write"))


@pytest.mark.parametrize("texts, chosen", [
    (MONTHS, "Jun"), ([f"{i:02d}" for i in range(1, 13)], "06"), ([str(i) for i in range(1, 13)], "6"),
    (["January", "February", "March", "April", "May", "June", "July"], "June"),
], ids=["short", "two-digit", "number", "long"])
def test_a_month_list_is_chosen_in_its_own_spelling_without_a_model(page, load, texts, chosen):
    options = [opt(f"o{i + 1}", t) for i, t in enumerate(texts)]
    out = run(page, load, frames=[[f("m", "select", "Start: Month", part="month", options=options, optionsComplete=True)]],
              map={"m": dated()})
    assert statuses(out) == {"m": "verified"}
    assert [a["text"] for a in actions(out, "choose")] == [chosen]
    assert "/api/autofill/pick" not in out["calls"]


def test_a_year_list_and_an_explored_month_popup_are_chosen_by_their_part(page, load):
    years = [opt(f"o{i}", str(2020 + i)) for i in range(8)]
    out = run(page, load, frames=[[f("y", "select", "Start: Year", part="year", options=years, optionsComplete=True),
                                   f("m", "popup", "Start: Month", part="month")]],
              map={"y": dated(), "m": dated()},
              explore={"m": {"options": [opt(f"o{i + 1}", t) for i, t in enumerate(MONTHS)], "complete": True}})
    assert statuses(out) == {"y": "verified", "m": "verified"}
    assert [a["text"] for a in actions(out, "choose")] == ["2026", "Jun"]
    assert "/api/autofill/pick" not in out["calls"] and "/api/autofill/step" not in out["calls"]


def test_a_part_the_date_does_not_have_is_left_calmly(page, load):
    """No day in a YYYY-MM fact, no month in a year-only one: nothing is
    written, nothing is asked, and the row says why."""
    days = [opt(f"o{i}", str(i)) for i in range(1, 32)]
    out = run(page, load, frames=[[f("d", "select", "Start: Day", part="day", options=days, optionsComplete=True),
                                   f("m", question="Graduated: Month", part="month")]],
              map={"d": dated(), "m": dated("2019", "education.0.end_year")})
    assert statuses(out) == {"d": "needs_answer", "m": "needs_answer"}
    assert [row(out, x)["lastOutcome"] for x in ("d", "m")] == ["no_date_part", "no_date_part"]
    assert row(out, "d")["answer"] == "Your profile has no day for this date."
    assert row(out, "m")["answer"] == "Your profile has no month for this date."
    assert actions(out) == [] and "/api/autofill/pick" not in out["calls"]


def test_a_month_list_with_no_option_for_the_month_is_left(page, load):
    out = run(page, load, frames=[[f("m", "select", "Start: Month", part="month",
                                     options=[opt("o1", "Spring"), opt("o2", "Fall")], optionsComplete=True)]],
              map={"m": dated()})
    assert statuses(out) == {"m": "needs_answer"} and actions(out) == []


def test_only_a_date_slot_on_a_part_control_is_narrowed(page, load):
    """A whole date box, a part control mapped to a slot that is no date, and
    a backend that does not say `date` keep the value whole."""
    out = run(page, load, frames=[[f("w", question="Start date"), f("n", question="Phone: Number", part=None),
                                   f("y", question="Year", part="year")]],
              map={"w": dated(), "n": {"route": "slot", "slot": "personal.phone", "value": "555-0100", "format": "phone"},
                   "y": {"route": "slot", "slot": "custom.1", "value": "2026-06"}})
    assert {a["fid"]: a["value"] for a in actions(out, "write")} == {"w": "2026-06", "n": "555-0100", "y": "2026-06"}


def test_an_end_date_whose_job_is_unclear_is_left_with_its_own_note(page, load):
    """/map left an end date because the entry's job could not be told (its
    `why`): the profile has the date, so the row never says "no fact"."""
    out = run(page, load, frames=[[f("e", question="End Date: Year", part="year"), f("n", question="Nickname")]],
              map={"e": {"route": "none", "why": "unclear_job"}, "n": {"route": "none"}})
    assert statuses(out) == {"e": "needs_answer", "n": "needs_answer"}
    assert (row(out, "e")["lastOutcome"], row(out, "e")["answer"]) == (
        "unclear_job", "Left for you: it isn't clear which of your jobs this entry is.")
    assert row(out, "n")["lastOutcome"] == "no_fact"
    assert actions(out) == []
    # Telemetry keeps its outcome vocabulary: the reason stays in the report.
    obs = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.buildLoopObservations(r)", out["report"])
    assert {o["outcome"] for o in obs} == {"needs_answer"}


# ---------- the run trace: each field's decision path (value-free)

SOURCE = (EXTENSION / "shared" / "fill-loop.js").read_text(encoding="utf-8")


def trace_of(out):
    trace = out["report"]["trace"]
    assert trace, "the loop built no trace"
    return trace


def traced(out, fid):
    return next(t for t in trace_of(out)["fields"] if t["fid"] == fid)


def ops(out, fid):
    return [s["op"] for s in traced(out, fid)["steps"]]


SELECT_AND_TEXT = dict(
    frames=[[f("s", "select", "Authorized to work?", options=[opt("o1", "Yes"), opt("o2", "No")], optionsComplete=True),
             f("t", question="City")]],
    map={"s": {"route": "slot", "slot": "work_auth.authorized_now", "value": "Yes",
               "trace": {"engine": "fast", "p": 0.97, "floor": 0.9}},
         "t": {"route": "slot", "slot": "personal.city", "value": "Springfield"}},
    pick={"s": {"oids": ["o1"], "reason": "matched", "trace": {"engine": "jev", "p": 0.95, "floor": 0.9,
                                                               "second": "asked", "chose_none": False}}})


def test_a_trace_lists_each_decision_and_page_action_in_order(page, load):
    out = run(page, load, **SELECT_AND_TEXT)
    assert statuses(out) == {"s": "verified", "t": "verified"}
    assert ops(out, "s") == ["map", "pick", "choose"]
    assert ops(out, "t") == ["map", "write"]
    s_map, s_pick, _ = traced(out, "s")["steps"]
    assert (s_map["route"], s_map["slot"], s_map["engine"], s_map["p"]) == ("slot", "work_auth.authorized_now", "fast", 0.97)
    assert (s_pick["reason"], s_pick["option"], s_pick["engine"], s_pick["p"]) == ("matched", 0, "jev", 0.95)
    assert (s_pick["second"], s_pick["chose_none"], "first_p" in s_pick) == ("asked", False, False)  # only what was sent


def test_every_trace_step_is_timed_in_whole_milliseconds(page, load):
    out = run(page, load, **SELECT_AND_TEXT)
    steps = [step for fid in ("s", "t") for step in traced(out, fid)["steps"]]
    assert {type(step["ms"]) for step in steps} == {int}
    assert min(step["ms"] for step in steps) >= 0


def test_a_verified_action_is_progress_in_the_round_it_ran(page, load):
    out = run(page, load, **SELECT_AND_TEXT)
    done = [traced(out, "s")["steps"][-1], traced(out, "t")["steps"][-1]]
    assert [(step["op"], step["effect"], step["word"]) for step in done] == [
        ("choose", "progress", "verified"), ("write", "progress", "verified")]
    assert (traced(out, "t")["round"], traced(out, "s")["outcome"], traced(out, "s")["option_count"]) == (1, "verified", 2)
    assert (trace_of(out)["host"], trace_of(out)["rounds"], trace_of(out)["halted"]) == ("x.test", 2, None)  # round 2 settles it


def test_a_trace_notes_a_picks_polarity_before_the_pick(page, load):
    out = run(page, load,
              frames=[[f("s", "select", "Disability?", options=[opt("o1", "Yes"), opt("o2", "No")], optionsComplete=True)]],
              map={"s": {"route": "slot", "slot": "eeo.disability", "value": "No"}},
              pick={"s": {"oids": ["o2"], "reason": "matched", "polarity": {"way": "opposite", "engine": "jev", "p": 0.88}}})
    assert ops(out, "s") == ["map", "polarity", "pick", "choose"]
    polarity, pick = traced(out, "s")["steps"][1:3]
    assert polarity == {"op": "polarity", "way": "opposite", "engine": "jev", "p": 0.88}
    assert pick["option"] == 1


def test_a_trace_marks_a_wasted_gesture_no_effect_and_the_second_kind_refused(page, load):
    state = {"candidates": [{"mid": "click:o1", "describe": 'Click the option "Yes"'},
                            {"mid": "open", "describe": "Open the dropdown"}, GIVE_UP]}
    out = run(page, load, frames=[[f("d", "popup", "Relocate?")]] * 3,
              map={"d": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "Yes"}},
              explore={"d": {"options": [], "complete": False, "error": "no_popup"}},
              apply={"click:o1": {"outcome": "unexpected", "reason": "no_effect", "gestures": ["pointer"]},
                     "open": {"outcome": "unexpected", "reason": "no_effect", "gestures": ["keyboard"]}},
              step={"states": [state, dict(state)],
                    "moves": [{"mid": "click:o1", "reason": "progress"}, {"mid": "open", "reason": "progress"}]})
    assert statuses(out) == {"d": "unsupported"}
    steps = traced(out, "d")["steps"]
    assert [s["op"] for s in steps] == ["map", "explore", "step", "move", "step", "move"]
    assert (steps[1]["effect"], steps[1]["word"]) == ("no_effect", "no_popup")
    assert [(s["move"], s["effect"], s["word"]) for s in steps if s["op"] == "move"] == [
        ("click:o1", "no_effect", "no_effect"), ("open", "refused", "no_effect")]
    assert [s["move"] for s in steps if s["op"] == "step"] == ["click:o1", "open"]


def test_a_trace_has_a_step_per_attempt_and_the_round_it_ended_in(page, load):
    out = run(page, load, frames=[[f("n", question="Years")]] * 3,
              map={"n": {"route": "slot", "slot": "custom.years", "value": "ten"}},
              apply={"ten": [{"outcome": "reverted", "reason": "no_effect", "gestures": ["type"]}, {"outcome": "verified"}]})
    assert [(s["op"], s.get("effect")) for s in traced(out, "n")["steps"]] == [
        ("map", None), ("write", "no_effect"), ("write", "progress")]
    assert (traced(out, "n")["round"], trace_of(out)["rounds"]) == (2, 3)


def test_a_stopped_runs_trace_says_so_and_a_cancelled_action_is_no_attempt(page, load):
    out = run(page, load, frames=[[f("a", question="City"), f("b", question="State")]], stopAfterApply=True,
              map={"a": {"route": "slot", "slot": "personal.city", "value": "Springfield"},
                   "b": {"route": "slot", "slot": "personal.state", "value": "Ohio"}})
    assert out["report"]["stopped"] is True
    assert (trace_of(out)["halted"], trace_of(out)["rounds"]) == ("stopped", 1)
    assert (traced(out, "a")["round"], ops(out, "a")) == (1, ["map", "write"])
    assert ops(out, "b") == ["map"] and traced(out, "b")["round"] == 0  # never worked
    cancelled = run(page, load, frames=[[f("a", question="City")]], stopAfterApply=True,
                    map={"a": {"route": "slot", "slot": "personal.city", "value": "Springfield"}},
                    apply={"Springfield": {"outcome": "cancelled"}})
    assert ops(cancelled, "a") == ["map"]  # Stop is not an attempt


def test_a_timed_out_runs_trace_says_timeout(page, load):
    out = run(page, load, frames=[[f("a", question="City")]], limits={"RUN_MS": 100},
              map={"a": {"route": "slot", "slot": "personal.city", "value": "Springfield"}},
              apiDelay={"/api/autofill/map": 300})  # the clock runs out inside /map, after the page was read
    assert trace_of(out)["halted"] == "timeout"


SENTINELS = ["SENTINEL-TYPED-77", "SENTINEL-COMMITTED-91", "SENTINEL-HELP-33", "SENTINEL-EXPLORE-55",
             "555-0100", "Acme Corp", "Springfield"]


def sentinel_run(page, load):
    """Every channel a value could take: the profile's answers, a typed value (which lands in
    row.ignored), the page's current value (field.committed), its help text, a label that echoes
    the written value, and a search explore's rows."""
    out = run(page, load,
              frames=[[f("p", question="Phone 555-0100"),
                       f("y", question="Years"),
                       f("c", question="Nickname", committed="SENTINEL-COMMITTED-91"),
                       f("h", question="City", help="SENTINEL-HELP-33"),
                       f("e", "search", "Employer"),
                       f("d", "select", "Disability",
                         options=[opt("o1", "No, I do not have a disability"), opt("o2", "Yes, I have a disability")],
                         optionsComplete=True)]] * 3,
              map={"p": {"route": "slot", "slot": "personal.phone", "value": "555-0100"},
                   "y": {"route": "slot", "slot": "custom.years", "value": "SENTINEL-TYPED-77"},
                   "c": {"route": "slot", "slot": "custom.nick", "value": "Joe"},
                   "h": {"route": "slot", "slot": "personal.city", "value": "Springfield"},
                   "e": {"route": "slot", "slot": "experience.0.company", "value": "Acme Corp"},
                   "d": {"route": "slot", "slot": "eeo.disability", "value": "No, I do not have a disability"}},
              apply={"SENTINEL-TYPED-77": [{"outcome": "reverted", "reason": "no_effect", "gestures": ["type"]},
                                           {"outcome": "verified"}]},
              explore={"Acme Corp": {"options": [opt("o9", "SENTINEL-EXPLORE-55 Inc")], "complete": True, "multi": False}},
              pick={"e": {"oids": ["o9"], "reason": "matched"},
                    "d": {"oids": ["o1"], "reason": "matched"}})
    assert set(statuses(out).values()) == {"verified"}
    return out


def test_no_value_reaches_the_trace(page, load):
    wire = json.dumps(trace_of(sentinel_run(page, load)))
    assert [s for s in SENTINELS if s in wire] == []


def test_what_the_trace_keeps_of_the_page_is_its_labels_and_options(page, load):
    out = sentinel_run(page, load)
    assert traced(out, "p")["label"] == ""  # a label that holds the written value is blank
    assert (traced(out, "c")["label"], traced(out, "h")["label"]) == ("Nickname", "City")
    # The page's own option texts are kept, the chosen one included (owner decision, 2026-10-03).
    assert (traced(out, "d")["options"], traced(out, "d")["option_count"]) == (
        ["No, I do not have a disability", "Yes, I have a disability"], 2)
    assert (traced(out, "e")["options"], "explore" in ops(out, "e")) == (None, True)  # a search lists rows only on explore


def test_a_field_trace_keeps_to_the_schemas_caps_and_patterns(page, load):
    many = [opt(f"o{i}", f"Option {i}") for i in range(45)]
    out = run(page, load,
              frames=[[f("s", "select", "Pick one " + "x" * 300, options=many, optionsComplete=True, section="S" * 300,
                         source="Weird_Source", recipe={"family": "f:ABC", "site": "s:x"}, required=True)]],
              map={"s": {"route": "low_stakes"}}, pick={"s": {"oids": [], "reason": "abstained"}})
    t = traced(out, "s")
    assert len(t["label"]) == 200 and len(t["section"]) == 200
    assert (len(t["options"]), t["option_count"]) == (30, 45)
    assert (t["label_source"], t.get("family"), t["required"]) == (None, None, True)
    assert [s["option"] for s in t["steps"] if s["op"] == "pick"] == [None]
    out = run(page, load, frames=[[f("s", "select", "Pick", options=many[:2], optionsComplete=True, source="aria-label",
                                     recipe={"family": "f:abc12", "site": "s:x"})]],
              map={"s": {"route": "low_stakes"}}, pick={"s": {"oids": ["o1"], "reason": "assumed"}})
    assert (traced(out, "s")["label_source"], traced(out, "s")["family"]) == ("aria-label", "f:abc12")


def test_a_trace_cut_through_an_emoji_keeps_whole_characters(page, load):
    """The 200th UTF-16 unit of "L"*199 + an emoji is half of it; a lone surrogate would 422 the run."""
    split = "L" * 199 + "\U0001F600"
    out = run(page, load, frames=[[f("s", "select", split, options=[opt("o1", split), opt("o2", "No")],
                                    optionsComplete=True, section=split)]],
              map={"s": {"route": "low_stakes"}}, pick={"s": {"oids": [], "reason": "abstained"}})
    t = traced(out, "s")
    assert (t["label"], t["section"], t["options"]) == ("L" * 199, "L" * 199, ["L" * 199, "No"])
    json.dumps(t, ensure_ascii=False).encode("utf-8")


def test_a_huge_option_list_reports_a_count_the_schema_accepts(page, load):
    many = [opt(f"o{i}", f"Option {i}") for i in range(5200)]
    out = run(page, load, frames=[[f("s", "select", "Pick one", options=many, optionsComplete=True)]],
              map={"s": {"route": "low_stakes"}}, pick={"s": {"oids": [], "reason": "abstained"}})
    t = traced(out, "s")
    assert (len(t["options"]), t["option_count"]) == (30, 5000)


def test_a_fields_trace_path_keeps_its_first_and_last_twenty_steps(page, load):
    """A popup scrolled 30 times: 62 steps happen. The first 20 show how the field began and the
    last 20 how it ended; each /step answer is marked by its p so the two ends can be told apart."""
    state = {"candidates": [{"mid": "scroll", "describe": "Scroll the list"}, GIVE_UP]}
    moves = [{"mid": "scroll", "reason": "progress", "trace": {"p": i / 100}} for i in range(30)]
    out = run(page, load, frames=[[f("d", "popup", "Company")]] * 2, limits={"MAX_STEPS": 30},
              map={"d": {"route": "slot", "slot": "experience.0.company", "value": "Acme"}},
              explore={"d": {"options": [], "complete": False, "error": "no_popup"}},
              apply={"scroll": {"outcome": "progressed"}},
              step={"states": [state] * 30, "moves": moves})
    assert len(actions(out, "move")) == 31  # 30 scrolls and the closing give_up
    steps = traced(out, "d")["steps"]
    assert len(steps) == 40
    assert [s["op"] for s in steps[:4]] == ["map", "explore", "step", "move"]
    assert steps[-1]["op"] == "move"
    asked = [round(s["p"] * 100) for s in steps if s["op"] == "step"]
    assert asked == [*range(0, 9), *range(20, 30)]


def test_a_trace_notes_a_recipe_hit_and_a_sweep_revert(page, load):
    out = run(page, load, frames=[[f("d", "popup", "Relocate?", recipe=RECIPE)]] * 3,
              recipes={"book": LEARNED},
              map={"d": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "Yes"}},
              explore={"d": {"options": [opt("o1", "Yes")], "complete": True}},
              pick={"d": {"oids": ["o1"], "reason": "matched"}},
              sweep=[[{"fid": "d", "outcome": "reverted"}], []])
    steps = traced(out, "d")["steps"]
    assert steps[1]["op"] == "recipe" and set(steps[1]) == {"op"}
    assert {"op": "sweep", "effect": "reverted", "word": "reverted"} in steps
    assert traced(out, "d")["family"] == "f:fam1"


EFFECTS_OF_PAGE_WORDS = {
    "verified": "progress", "partial": "progress", "progressed": "progress", "closed": "progress",
    "unexpected": "unexpected", "reverted": "reverted", "unconfirmed": "unconfirmed",
    "yours": "refused", "blocked": "refused", "unsupported": "refused", "refused": "refused",
    "timeout": "late", "late": "late", "stale": "error", "halted": None, "cancelled": None,
}


def _header_words():
    """The page outcomes and act() words the fill-loop.js header lists (its vocabularies block)."""
    def found(pattern, text, what):
        hit = re.search(pattern, text, re.S)
        assert hit, f"the fill-loop.js header's {what} moved: update _header_words"
        return hit.group(0 if what == "vocabularies block" else 1)

    block = found(r"THE OUTCOME VOCABULARIES.*?\n \*   row status", SOURCE, "vocabularies block")
    page = found(r"page outcome\s+(.*?);\s+reason", block, "page outcome list")
    acts = found(r"act\(\)\s+(.*?)\s+→ the caller", block, "act() list")
    words = set()
    for chunk in (page, acts):
        chunk = re.sub(r"\([^()]*\)", " ", re.sub(r"\n \*\s+", " ", chunk))
        for alt in chunk.split("|"):
            alt = alt.strip()
            alt = re.sub(r"^the page's outcome, or ", "", alt)
            words.add(re.match(r"[a-z_]+", alt).group(0))
    return words


def test_every_outcome_the_header_lists_has_a_trace_effect_row(page, load):
    listed = _header_words()
    assert {"verified", "unconfirmed", "progressed", "timeout", "halted", "late", "refused", "stale"} <= listed, listed
    assert listed <= set(EFFECTS_OF_PAGE_WORDS), f"the header lists a word effectOf has no row for: {listed - set(EFFECTS_OF_PAGE_WORDS)}"
    load(page, "<div></div>", sources=LOOP_SOURCES)
    got = page.evaluate("(words) => Object.fromEntries(words.map((w) => [w, window.careerStudioCompanion.fillLoop.effectOf({outcome: w})]))",
                        sorted(EFFECTS_OF_PAGE_WORDS))
    assert got == EFFECTS_OF_PAGE_WORDS


def test_a_trace_effect_is_read_reason_first_and_act_refusals_win(page, load):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    effect = "([r, g]) => window.careerStudioCompanion.fillLoop.effectOf(r, g)"
    for result, got, want in [
        ({"outcome": "unexpected", "reason": "no_effect"}, None, "no_effect"),
        ({"outcome": "reverted", "reason": "no_effect"}, None, "no_effect"),
        ({"outcome": "unexpected", "reason": "group_committed"}, None, "progress"),
        ({"outcome": "unexpected", "reason": "search_committed"}, None, "progress"),
        ({"outcome": "unexpected", "reason": "unsettled"}, None, "unexpected"),
        ({"outcome": "refused"}, {"outcome": "unexpected", "reason": "no_effect"}, "refused"),
        ({"outcome": "refused"}, {"outcome": "unexpected", "reason": "committed_while_opening"}, "refused"),
        ({"outcome": "halted"}, {"outcome": "cancelled"}, None),
        ({"outcome": "late"}, None, "late"),
        ({"outcome": "stale"}, None, "error"),
        ({"outcome": "surprise"}, None, "error"),
    ]:
        assert page.evaluate(effect, [result, got]) == want, (result, got)


def test_a_trace_explore_effect_is_read_by_error_word_and_option_count(page, load):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    explore = "(g) => window.careerStudioCompanion.fillLoop.exploreEffect(g)"
    for got, want in [
        ({"options": [{"oid": "o1"}]}, "progress"), ({"options": []}, "no_effect"),
        ({"options": [], "error": "no_effect"}, "no_effect"), ({"options": [], "error": "yours"}, "refused"),
        ({"options": [], "error": "blocked"}, "refused"), ({"options": [], "error": "unsupported"}, "refused"),
        ({"options": [], "error": "committed_while_exploring"}, "unexpected"),
        ({"options": [], "error": "stale"}, "error"), ({"options": [], "error": "cancelled"}, None),
        ({"options": [], "error": "timeout"}, "late"),
        ({"options": [], "error": "no_popup"}, "no_effect"), ({"options": [], "error": "unsettled"}, "no_effect"),
    ]:
        assert page.evaluate(explore, got) == want, got


# ---------- blanking, run-wide, on rows built by hand (buildRunTrace takes the report and the rows)


def build_trace(page, load, rows):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    trace = page.evaluate("""(rows) => {
      const report = {runId: "abcdefgh-1", host: "X.Test", stopped: false, timedOut: false, rounds: 1,
                      fields: rows.map((r) => ({fid: r.fid, status: r.status ?? "verified"}))};
      return window.careerStudioCompanion.fillLoop.buildRunTrace(report, new Map(rows.map((r) => [r.fid, r])),
                                                                 {startedAt: new Date(), endedAt: new Date()});
    }""", rows)
    RunTrace.model_validate(trace)
    return trace


def brow(fid, question="Q", shape="text", **kw):
    options = [o if isinstance(o, dict) else {"oid": f"o{i}", "text": o} for i, o in enumerate(kw.pop("options", None) or [])] or None
    field = {"question": question, "shape": shape, "section": kw.pop("section", ""), "options": options,
             "committed": kw.pop("committed", ""), "required": False}
    return {"fid": fid, "field": field, "steps": [], "round": 1} | kw


def labels(trace):
    return {t["fid"]: (t["label"], t["section"]) for t in trace["fields"]}


def test_a_row_blanks_its_own_label_and_section_by_its_answer_write_value_or_leftover(page, load):
    trace = build_trace(page, load, [
        brow("a", "Employer Acme Corp", answer='Searching picked "Acme Corp". Check it.'),
        brow("b", "Phone", section="Reach me at 555-0100", value="555-0100"),
        brow("c", "Old Zed Corp entry", leftover="Zed Corp"),
        brow("d", "Where is Hooli", wrote="Hooli"),
        brow("e", "Nickname", value="Joe", committed="Springfield"),
        brow("f", "City Springfield", committed="Springfield")])
    assert labels(trace) == {"a": ("", None), "b": ("Phone", ""), "c": ("", None), "d": ("", None),
                             "e": ("Nickname", None), "f": ("", None)}


def test_a_siblings_value_blanks_another_rows_label_and_section(page, load):
    trace = build_trace(page, load, [
        brow("a", "Company", value="Hooli"),
        brow("b", "Hooli details", section="About Hooli"),
        brow("c", "Years", "select", value="Maybe"),
        brow("d", "Maybe later")])
    assert labels(trace) == {"a": ("Company", None), "b": ("", ""), "c": ("Years", None), "d": ("", None)}


def test_a_short_choice_answer_does_not_blank_every_label_that_says_it(page, load):
    trace = build_trace(page, load, [
        brow("a", "Employed?", "select", value="No"),
        brow("b", "No longer employed?", section="No section"),
        brow("c", "Authorized?", "select", value="Yes"),
        brow("d", "Yes or maybe?"),
        brow("e", "Own answer: No", "select", value="No")])
    assert labels(trace) == {"a": ("Employed?", None), "b": ("No longer employed?", "No section"),
                             "c": ("Authorized?", None), "d": ("Yes or maybe?", None), "e": ("", None)}


def test_a_typed_siblings_key_counts_from_two_characters(page, load):
    trace = build_trace(page, load, [
        brow("a", "Years", value="2"),
        brow("b", "Experience 2"),
        brow("c", "State", value="OH"),
        brow("d", "Lives in OH")])
    assert labels(trace) == {"a": ("Years", None), "b": ("Experience 2", None), "c": ("State", None), "d": ("", None)}


def test_a_four_character_choice_answer_blanks_a_sibling_label(page, load):
    trace = build_trace(page, load, [brow("a", "Pick", "select", value="Maybe"), brow("b", "Maybe later")])
    assert labels(trace) == {"a": ("Pick", None), "b": ("", None)}


def test_an_answer_equal_to_the_rows_own_option_is_not_a_deny_key(page, load):
    """A country select answered "United States" would blank "authorized to work in the United
    States?" on every US form; typed into a text box the same value still does."""
    label = "Authorized to work in the United States?"
    chosen = build_trace(page, load, [
        brow("a", "Country", "select", value="United States", options=["united states ", "Canada"]), brow("b", label)])
    typed = build_trace(page, load, [brow("a", "Country", value="United States"), brow("b", label)])
    assert labels(chosen) == {"a": ("Country", None), "b": (label, None)}
    assert labels(typed) == {"a": ("Country", None), "b": ("", None)}


def test_a_lone_checkboxs_yes_or_no_is_not_a_deny_key(page, load):
    """A lone checkbox reads "Yes" or "No" (oids yes and no): its own label keeps the word. The
    option texts here are another language's, so only the lone-checkbox rule can keep it."""
    lone = [{"oid": "yes", "text": "Oui"}, {"oid": "no", "text": "Non"}]
    trace = build_trace(page, load, [brow("a", "Yes, email me offers", "group", options=lone, committed="Yes"),
                                     brow("b", "Say yes to updates")])
    assert labels(trace) == {"a": ("Yes, email me offers", None), "b": ("Say yes to updates", None)}


def test_an_already_filled_rows_committed_value_blanks_a_sibling_label_and_is_never_emitted(page, load):
    trace = build_trace(page, load, [
        brow("a", "Phone", status="already", committed="555-0100"),
        brow("b", "Call 555-0100 after five")])
    assert labels(trace) == {"a": ("Phone", None), "b": ("", None)}
    assert "555-0100" not in json.dumps(trace)


def test_a_trace_that_cannot_be_built_is_null_and_warns_with_fixed_text(page, load):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    got = page.evaluate("""() => {
      const warned = [];
      console.warn = (...a) => warned.push(a);
      const bad = {runId: "abcdefgh-1", host: "x.test", fields: [{fid: "a", status: "verified"}]};
      const rows = new Map([["a", {fid: "a", get field() { throw new Error("secret-value"); }}]]);
      const trace = window.careerStudioCompanion.fillLoop.buildRunTrace(bad, rows, {startedAt: new Date(), endedAt: new Date()});
      return {trace, warned};
    }""")
    assert got == {"trace": None, "warned": [["[maestro-cs] the run trace could not be built"]]}


# ---------- measured and failed calls


def test_a_trace_times_the_calls_and_page_actions_it_made(page, load):
    out = run(page, load, frames=[[f("t", question="City")]],
              map={"t": {"route": "slot", "slot": "personal.city", "value": "Springfield"}},
              apiDelay={"/api/autofill/map": 80}, pageDelay={"Springfield": 80})
    mapped, written = traced(out, "t")["steps"]
    assert mapped["ms"] >= 70 and written["ms"] >= 70


def _pick_ms(out, fid):
    return next(s["ms"] for s in traced(out, fid)["steps"] if s["op"] == "pick")


def _selects(*fids):
    return [f(fid, "select", "Pick " + fid, options=[opt("o1", "Yes"), opt("o2", "No")], optionsComplete=True) for fid in fids]


def test_a_batch_pick_charges_each_field_its_even_share_of_the_call(page, load):
    out = run(page, load, frames=[_selects("a", "b")], apiDelay={"/api/autofill/pick": 100},
              map={"a": {"route": "low_stakes"}, "b": {"route": "low_stakes"}},
              pick={"a": {"oids": ["o1"], "reason": "assumed"}, "b": {"oids": ["o1"], "reason": "assumed"}})
    one = run(page, load, frames=[_selects("a")], apiDelay={"/api/autofill/pick": 100},
              map={"a": {"route": "low_stakes"}}, pick={"a": {"oids": ["o1"], "reason": "assumed"}})
    # Half of the call each: equal shares, at least half the delay, and less than one field alone is charged.
    assert _pick_ms(out, "a") == _pick_ms(out, "b")
    assert 40 <= _pick_ms(out, "a") < _pick_ms(one, "a")


def test_a_single_picks_ms_is_the_whole_call(page, load):
    out = run(page, load, frames=[_selects("a")], apiDelay={"/api/autofill/pick": 100},
              map={"a": {"route": "low_stakes"}}, pick={"a": {"oids": ["o1"], "reason": "assumed"}})
    assert _pick_ms(out, "a") >= 90


def test_a_failed_pick_still_notes_its_time(page, load):
    out = run(page, load, frames=[[f("s", "select", "Pick", options=[opt("o1", "Yes")], optionsComplete=True)]],
              limits={"API_MS": 60}, apiHang=["/api/autofill/pick"], map={"s": {"route": "low_stakes"}})
    [pick] = [s for s in traced(out, "s")["steps"] if s["op"] == "pick"]
    assert set(pick) == {"op", "ms"} and pick["ms"] >= 50


def test_a_failed_map_notes_its_time_on_each_field(page, load):
    out = run(page, load, frames=[[f("a", question="City"), f("b", question="State")]],
              limits={"API_MS": 60}, apiHang=["/api/autofill/map"])
    maps = [s for fid in ("a", "b") for s in traced(out, fid)["steps"]]
    assert {frozenset(s) for s in maps} == {frozenset({"op", "ms"})} and {s["op"] for s in maps} == {"map"}


def test_a_failed_step_notes_its_time(page, load):
    state = {"candidates": [{"mid": "open", "describe": "Open the dropdown"}, GIVE_UP]}
    out = run(page, load, frames=[[f("d", "popup", "Relocate?")]] * 2, limits={"API_MS": 60}, apiHang=["/api/autofill/step"],
              map={"d": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "Yes"}},
              explore={"d": {"options": [], "complete": False, "error": "no_popup"}}, step={"states": [state], "moves": []})
    [step] = [s for s in traced(out, "d")["steps"] if s["op"] == "step"]
    assert set(step) == {"op", "ms"} and step["ms"] >= 50


def test_a_step_that_chose_give_up_records_the_move(page, load):
    state = {"candidates": [{"mid": "open", "describe": "Open the dropdown"}, GIVE_UP]}
    out = run(page, load, frames=[[f("d", "popup", "Relocate?")]] * 2,
              map={"d": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "Yes"}},
              explore={"d": {"options": [], "complete": False, "error": "no_popup"}},
              step={"states": [state], "moves": [{"mid": "give_up", "reason": "abstained"}]})
    [step] = [s for s in traced(out, "d")["steps"] if s["op"] == "step"]
    assert (step["move"], step["reason"]) == ("give_up", "abstained")


# ---------- what a pick's index means, and a set's picks


def test_a_picks_option_index_counts_the_offered_options_not_the_pages(page, load):
    """A placeholder row and a never-fill option are never offered, so the chosen option's index is
    among the two that were; the page's own list (kept whole, option_count 4) still shows all four."""
    options = [opt("o0", "Select One"), opt("o1", "Never fill", blocked=True), opt("o2", "Yes"), opt("o3", "No")]
    out = run(page, load, frames=[[f("s", "select", "Pick", options=options, optionsComplete=True)]],
              map={"s": {"route": "low_stakes"}}, pick={"s": {"oids": ["o3"], "reason": "assumed"}})
    t = traced(out, "s")
    assert [s["option"] for s in t["steps"] if s["op"] == "pick"] == [1]
    assert (t["options"], t["option_count"]) == (["Select One", "Never fill", "Yes", "No"], 4)


def test_a_set_notes_a_pick_per_item_and_one_set_action(page, load):
    options = [opt("o1", "SQL"), opt("o2", "Python")]
    out = run(page, load, frames=[[f("k", "select", "Skills", multi=True, options=options, optionsComplete=True)]],
              map={"k": {"route": "slot", "slot": "skills", "value": ["SQL", "Python"]}},
              pick={"k:SQL": {"oids": ["o1"], "reason": "matched"}, "k:Python": {"oids": ["o2"], "reason": "matched"}},
              apply={"SQL+Python": {"outcome": "verified", "added": ["SQL", "Python"], "missing": []}})
    steps = traced(out, "k")["steps"]
    assert [s["op"] for s in steps] == ["map", "pick", "pick", "set"]
    assert ([s["option"] for s in steps[1:3]], steps[3]["effect"]) == ([0, 1], "progress")


# ---------- the loop's trace limits mirror the backend schema's


def _const(name, text=SOURCE):
    hit = re.search(rf"const {name} = ([^\n]*?);(?: *//[^\n]*)?\n", text)
    assert hit, f"fill-loop.js no longer defines {name}"
    return hit.group(1)


def _set_of(name):
    return set(re.findall(r'"([^"]+)"', re.search(rf"const {name} = new Set\(\[(.*?)\]\);", SOURCE, re.S).group(1)))


def _meta(model, field, attr):
    return next(getattr(m, attr) for m in model.model_fields[field].metadata if getattr(m, attr, None) is not None)


def test_the_loops_trace_limits_and_patterns_mirror_the_backends():
    from app.schemas import autofill_fill as F
    from app.schemas import autofill_trace as T

    regex = lambda name: re.fullmatch(r"/(.*)/", _const(name)).group(1)  # noqa: E731
    assert [int(_const(n)) for n in ("TRACE_STEPS", "MAX_RUN_FIELDS", "TRACE_FIELD_OPTIONS", "TRACE_TEXT", "MAX_TRACE_ROUNDS")] == [
        T.MAX_FIELD_STEPS, T.MAX_RUN_FIELDS, _meta(T.TraceField, "options", "max_length"), T.LABEL_MAX,
        _meta(T.TraceField, "round", "le")] == [40, 200, 30, 200, 10]
    assert _meta(T.RunTrace, "rounds", "le") == int(_const("MAX_TRACE_ROUNDS"))
    assert [regex(n) for n in ("TRACE_WORD", "TRACE_SLOT", "MOVE_ID", "TRACE_HOST", "TRACE_FAMILY", "TRACE_SOURCE", "FID")] == [
        T.WORD, T.SLOT, F.MOVE_ID, _meta(T.RunTrace, "host", "pattern"), _meta(T.TraceField, "family", "pattern"),
        _meta(T.TraceField, "label_source", "pattern"), F.FID]
    assert int(_const("TRACE_COUNT_MAX")) == T.MAX_OPTION_COUNT == _meta(T.TraceField, "option_count", "le")
    assert int(_const("TRACE_MOVE_MAX")) == _meta(T.TraceStep, "move", "max_length") == _meta(F.StepCandidate, "mid", "max_length")
    assert re.search(r"s\.length <= (\d+) && TRACE_SLOT", SOURCE).group(1) == str(_meta(T.TraceStep, "slot", "max_length"))
    assert re.search(r"Math\.min\((\d+), Math\.max\(0, Math\.round", SOURCE).group(1) == str(_meta(T.TraceStep, "ms", "le"))


def test_the_loops_trace_vocabularies_mirror_the_backends():
    from typing import get_args

    from app.schemas import autofill_fill as F
    from app.schemas import autofill_trace as T

    for name, literal in [("TRACE_SHAPES", F.Shape), ("TRACE_ROUTES", F.Route), ("TRACE_ENGINES", F.Engine),
                          ("TRACE_SECONDS", F.Second), ("TRACE_WAYS", F.PolarityWay), ("TRACE_REASONS", F.StepReason)]:
        assert _set_of(name) == set(get_args(literal)), name
    checks = re.search(r"const DECISION_CHECKS = \{(.*?)\n  \};", SOURCE, re.S).group(1)
    assert set(re.findall(r"(?:^|,)\s*([a-z_]+):", checks)) == set(F.DecisionTrace.model_fields)
    outcome_effects = re.search(r"const OUTCOME_EFFECT = \{(.*?)\};", SOURCE, re.S).group(1)
    returned = " ".join(re.search(rf"const {fn} = .*?\n  \}};", SOURCE, re.S).group(0) for fn in ("effectOf", "exploreEffect"))
    assert set(re.findall(r':\s*"([a-z_]+)"', outcome_effects)) | set(re.findall(r'(?:return|\?|:) "([a-z_]+)"', returned)) <= set(get_args(T.Effect))
