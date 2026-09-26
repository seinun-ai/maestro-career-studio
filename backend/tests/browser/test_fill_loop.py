"""The loop's decisions (shared/fill-loop.js), with the page and the backend
scripted: every page message and every backend call is answered by the spec,
and recorded so a test can pin what the loop SENT."""

import re
from pathlib import Path

import pytest

from app.schemas.autofill_choose import ChooseRequest
from app.schemas.autofill_fill import MapRequest, PickRequest, SectionsRequest, StepRequest
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
    if (msg.type === "fill_sweep") return one(take(spec.sweep) ?? []);
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
    if (path === "/api/autofill/map") return {fields: Object.fromEntries(body.fields.map(f => [f.fid, spec.map[`${f.fid}:${f.question}`] ?? spec.map[f.fid] ?? {route: "none"}]))};
    if (path === "/api/autofill/pick") return {picks: Object.fromEntries(body.fields.map(f => [f.fid, spec.pick[`${f.fid}:${f.item ?? ""}`] ?? spec.pick[f.fid] ?? {oids: [], reason: "abstained"}]))};
    if (path === "/api/autofill/step") return spec.step.moves.shift() ?? {mid: null, reason: "abstained"};
    if (path === "/api/autofill/sections") return {sections: Object.fromEntries(body.sections.map(x => [x.sid, spec.kinds?.[x.sid] ?? {kind: "none", wanted: 0}]))};
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


def test_phone_slots_are_written_with_the_phone_format(page, load):
    out = run(page, load, frames=[[f("p", question="Phone"), f("c", question="City")]],
              map={"p": {"route": "slot", "slot": "personal.phone", "value": "5550100000"},
                   "c": {"route": "slot", "slot": "personal.city", "value": "Springfield"}})
    assert statuses(out) == {"p": "verified", "c": "verified"}
    writes = {a["fid"]: a for a in actions(out, "write")}
    assert writes["p"]["format"] == "phone" and "format" not in writes["c"]


def test_salary_slots_write_with_money_format(page, load):
    """The FACT decides the format: a salary slot compares as a number, a
    number-looking answer in another slot does not."""
    out = run(page, load, frames=[[f("s", question="Desired salary"), f("y", question="Years of experience")]],
              map={"s": {"route": "slot", "slot": "preferences.desired_salary", "value": "80000"},
                   "y": {"route": "slot", "slot": "experience.years", "value": "8"}})
    assert statuses(out) == {"s": "verified", "y": "verified"}
    writes = {a["fid"]: a for a in actions(out, "write")}
    assert writes["s"]["format"] == "money" and "format" not in writes["y"]


def test_only_a_salary_word_in_the_slot_name_makes_it_money(page, load):
    slots = {"a": "preferences.salary", "b": "preferences.expected_compensation", "c": "custom.pay",
             "d": "personal.payroll_id", "e": "personal.paypal_email", "g": "custom.display_name"}
    out = run(page, load, frames=[[f(k, question=f"Q{k}") for k in slots]],
              map={k: {"route": "slot", "slot": v, "value": "1"} for k, v in slots.items()})
    writes = {a["fid"]: a.get("format") for a in actions(out, "write")}
    assert writes == {"a": "money", "b": "money", "c": "money", "d": None, "e": None, "g": None}


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


def section(sid="f-s1", heading="Work Experience", entries=1, filled=None):
    return {"sid": sid, "heading": heading, "entries": entries,
            "filled": filled if filled is not None else [False] * entries, "add": "Add Another"}


JOBS = {"t1": {"route": "slot", "slot": "experience.0.title", "value": "Analyst"},
        "c1": {"route": "slot", "slot": "experience.0.employer", "value": "Acme"},
        "t2": {"route": "slot", "slot": "experience.1.title", "value": "Intern"},
        "c2": {"route": "slot", "slot": "experience.1.employer", "value": "Initech"}}


def adds(out):
    return [{k: m[k] for k in ("sid", "heading", "entries")} for m in out["sent"] if m["type"] == "fill_add"]


def test_the_loop_adds_entries_the_profile_can_fill_then_fills_them(page, load):
    out = run(page, load, frames=[work(1), work(1) + work(2)],
              sections=[[section(entries=1)], [section(entries=2)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 2}}, map=JOBS)
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
    assert ask["sections"] == [{"sid": "f-s1", "heading": "Work Experience", "entries": 1, "filled": [False]}]
    # The report says what was added, by kind (value-free).
    assert out["report"]["sections"] == [{"heading": "Work Experience", "kind": "experience", "wanted": 2,
                                          "entries": 2, "added": 1, "outcome": "added"}]


def test_an_entry_already_holding_data_is_reconciled_not_duplicated(page, load):
    held = work(1, committed="Someone's job", answered=True)
    out = run(page, load, frames=[held, held + work(2)],
              sections=[[section(entries=1, filled=[True])], [section(entries=2, filled=[True, False])]],
              kinds={"f-s1": {"kind": "experience", "wanted": 2}}, map=JOBS)
    # The held entry counts as one of the two: one Add, never two.
    assert len(adds(out)) == 1
    # What it holds stays: never written over.
    assert statuses(out) == {"t1": "already", "c1": "already", "t2": "verified", "c2": "verified"}
    assert {a["fid"] for a in actions(out)} == {"t2", "c2"}
    # Two entries on the page already, one of them held: nothing to add.
    out = run(page, load, frames=[held + work(2)], sections=[[section(entries=2, filled=[True, False])]],
              kinds={"f-s1": {"kind": "experience", "wanted": 2}}, map=JOBS)
    assert adds(out) == [] and statuses(out)["t2"] == "verified"


def test_add_never_exceeds_what_the_profile_can_fill(page, load):
    # As many entries as the profile can fill: nothing is pressed.
    out = run(page, load, frames=[work(1)], sections=[[section(entries=1)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 1}}, map=JOBS)
    assert adds(out) == [] and "fill_add" not in out["calls"]
    # More on the page than the profile has: never Add, never Delete.
    out = run(page, load, frames=[work(1) + work(2)], sections=[[section(entries=2)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 1}}, map=JOBS)
    assert adds(out) == []
    # Two short: two presses, one at a time, each on the count the last one left.
    out = run(page, load, frames=[work(1), work(1) + work(2), work(1) + work(2) + work(3)],
              sections=[[section(entries=1)], [section(entries=3)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 3}}, map=JOBS)
    assert [a["entries"] for a in adds(out)] == [1, 2]
    assert out["report"]["sections"][0]["added"] == 2
    # A section that is none of the profile's lists, or one the profile has
    # nothing for, gets nothing; a second section of the same kind gets nothing.
    out = run(page, load, frames=[work(1)],
              sections=[[section("f-s1", entries=1), section("f-s2", "Skills", 0), section("f-s3", "Languages", 1),
                         section("f-s4", "Relevant Experience", 0)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 1}, "f-s3": {"kind": "languages", "wanted": 0},
                     "f-s4": {"kind": "experience", "wanted": 1}}, map=JOBS)
    assert adds(out) == []


def test_an_add_that_did_not_grow_the_section_is_pressed_once(page, load):
    """A deliberate write, never a trial: a press that added nothing is not
    pressed again — not for the next wanted entry, not in a later round."""
    out = run(page, load, frames=[work(1)], sections=[[section(entries=1)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 3}},
              add={"f-s1": {"outcome": "not_added", "entries": 1}}, map=JOBS)
    assert len(adds(out)) == 1
    assert out["report"]["sections"] == [{"heading": "Work Experience", "kind": "experience", "wanted": 3,
                                          "entries": 1, "added": 0, "outcome": "not_added"}]
    assert statuses(out) == {"t1": "verified", "c1": "verified"}
    # The page answering "added" without the count growing is not an entry either.
    out = run(page, load, frames=[work(1)], sections=[[section(entries=1)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 2}},
              add={"f-s1": {"outcome": "added", "entries": 1}}, map=JOBS)
    assert len(adds(out)) == 1 and out["report"]["sections"][0]["added"] == 0


def test_a_stopped_run_never_presses_add(page, load):
    out = run(page, load, frames=[work(1)], sections=[[section(entries=1)]], stopOnSections=True,
              kinds={"f-s1": {"kind": "experience", "wanted": 2}}, map=JOBS)
    assert "fill_add" not in out["calls"] and out["report"]["stopped"] is True


def test_sections_the_backend_could_not_classify_add_nothing(page, load):
    out = run(page, load, frames=[work(1)], sections=[[section(entries=1)]], apiHang=["/api/autofill/sections"],
              limits={"API_MS": 200}, map=JOBS)
    assert "fill_add" not in out["calls"]
    assert statuses(out) == {"t1": "verified", "c1": "verified"}


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
