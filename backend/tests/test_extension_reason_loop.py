"""The reasoning loop (shared/reason-loop.js), pure: a fake page and a scripted reasoner drive it in node.

Pins: the snapshot is value-free and capped; at most 3 rounds, 3 actions each, 60 s a page; a signature that
failed twice is sent back as excluded; a field with no effect twice is dropped; a round that changes nothing ends
it; ask_user, a missing reply and Stop end it; press_next goes only through the driver's own press."""

import re

from app.schemas import autofill_reason as R
from tests.extension_harness import ROOT, run_node

SOURCE = "\n".join((ROOT / "extension" / "shared" / name).read_text(encoding="utf-8")
                   for name in ("decisions.js", "page-kind.js", "queue-run.js", "reason-loop.js"))

_DRIVER = r"""
const ns = loadModules();
let clock = 0;
const asks = [];
const done = [];
const lines = [];
let page = JSON.parse(JSON.stringify(spec.page));
const ops = {
  now: () => clock,
  cancelled: () => spec.stopAt != null && asks.length >= spec.stopAt,
  onLine: (text) => lines.push(text),
  read: async () => JSON.parse(JSON.stringify(page)),
  ask: async (body) => {
    asks.push(body);
    clock += spec.askMs ?? 1000;
    const r = (spec.replies ?? []).shift();
    return r === undefined ? null : r;
  },
  fill: async (fids, scope) => {
    done.push(["fill", fids, scope]);
    for (const fid of fids) if ((spec.fixes ?? []).includes(fid)) page.fields.find((f) => f.fid === fid).answered = true;
    if (spec.afterFill) page.summary = JSON.parse(JSON.stringify(spec.afterFill));
    if (spec.flipEveryFill) page.summary.stepKey = `k${done.length}`;
    clock += spec.fillMs ?? 0;
    return { fields: fids.map((fid) => ({ fid, question: "Q", status: (spec.fixes ?? []).includes(fid) ? "assumed" : "needs_answer",
                                          answer: (spec.fixes ?? []).includes(fid) ? "Mathematics" : null })) };
  },
  dismiss: async (frameId, id) => { done.push(["dismiss", frameId, id]); return { clicked: spec.dismissClicks ?? true }; },
  follow: async (tabId) => { done.push(["follow", tabId]); return true; },
};
const ctx = { why: spec.why ?? "open_questions", open: spec.open ?? [], recent: spec.recent ?? [],
  press: async (frameId, id, before, baseline) => { done.push(["press", frameId, id, before]); return spec.pressOutcome ?? "moved"; } };
main(async () => {
  const out = await ns.reasonLoop.think(ctx, ops);
  emit({ out, asks, done, lines });
});
"""

PAGE = {"frameId": 0, "url": "https://acme.wd5.myworkdayjobs.test/apply/questions",
        "summary": {"host": "acme.wd5.myworkdayjobs.test", "stepKey": "k0", "fillable": 2, "errors": 0,
                    "buttons": [{"id": "fx-1", "text": "Save and Continue", "type": "button", "visible": True, "enabled": True},
                                {"id": "fx-2", "text": "Close", "type": "button", "visible": True, "enabled": True, "overlay": True}]},
        "fields": [{"fid": "f1", "question": "Field of study", "shape": "text", "kind": "text", "required": True,
                    "answered": False, "committed": "", "options": None},
                   {"fid": "f2", "question": "First name", "shape": "text", "kind": "text", "required": True,
                    "answered": True, "committed": "Ada Lovelace", "options": None}],
        "errors": [], "tabs": [], "lastFill": {"f2": {"status": "verified", "slot": "personal.first_name"}}}


def think(tmp_path, **spec):
    return run_node(_DRIVER, {"page": PAGE, **spec}, tmp_path, source=SOURCE)


def act(**kw):
    return {"note": "Field of study is empty.", "actions": [kw], "rejected": [], "model": "m", "ms": 5}


def test_the_snapshot_is_value_free_capped_and_a_valid_request(tmp_path):
    many = {**PAGE, "fields": [{**PAGE["fields"][0], "fid": f"f{i}", "options": [{"oid": f"o{j}", "text": f"Opt {j}"}
                                                                                   for j in range(25)]} for i in range(70)]}
    out = run_node(_DRIVER, {"page": many, "recent": ["press_next -> rejected"] * 10}, tmp_path, source=SOURCE)
    [body] = out["asks"]
    R.ReasonRequest.model_validate(body)
    assert len(body["fields"]) == 60 and all(len(f["options"]) <= 20 and f["option_count"] == 25 for f in body["fields"])
    assert len(body["history"]) == 8 and "Ada" not in str(out)


def test_the_first_names_field_is_filled_and_by_the_run_and_buttons_are_refs(tmp_path):
    out = think(tmp_path)
    [body] = out["asks"]
    R.ReasonRequest.model_validate(body)
    assert {f["fid"]: (f["filled"], f["by_run"]) for f in body["fields"]} == {"f1": (False, False), "f2": (True, True)}
    assert body["buttons"] == [{"ref": "b1", "text": "Save and Continue", "role": "next"},
                               {"ref": "b2", "text": "Close", "role": "dialog"}]


def test_a_field_says_single_line_touched_and_the_fact_name_but_never_what_it_holds(tmp_path):
    page = {**PAGE, "fields": [{**PAGE["fields"][0], "multiline": True, "touched": True, "committed": "Secret essay"},
                               PAGE["fields"][1], {**PAGE["fields"][1], "fid": "f3", "policyBlocked": True}]}
    out = run_node(_DRIVER, {"page": page}, tmp_path, source=SOURCE)
    by_fid = {f["fid"]: f for f in out["asks"][0]["fields"]}
    assert set(by_fid) == {"f1", "f2"}                                    # a policy-blocked field is not offered
    assert (by_fid["f1"]["multiline"], by_fid["f1"]["touched"]) == (True, True)
    assert (by_fid["f2"]["multiline"], by_fid["f2"]["slot"]) == (False, "personal.first_name")
    assert "Secret" not in str(out) and "Ada" not in str(out)


def test_a_moved_away_snapshot_carries_no_fields_buttons_or_errors(tmp_path):
    page = {**PAGE, "errors": [{"label": "Name", "kind": "field", "target": "f1"}],
            "tabs": [{"tabId": 7, "host": "Jobs.Acme.test"}, {"tabId": 8, "host": "not a host"}]}
    out = run_node(_DRIVER, {"page": page, "why": "moved_away"}, tmp_path, source=SOURCE)
    [body] = out["asks"]
    R.ReasonRequest.model_validate(body)
    assert (body["fields"], body["buttons"], body["errors"]) == ([], [], [])
    assert body["tabs"] == [{"ref": "t1", "host": "jobs.acme.test"}]


def test_an_error_names_its_field_only_when_it_is_one(tmp_path):
    page = {**PAGE, "errors": [{"label": "Name", "kind": "field", "target": "f1"}, {"label": "Resume", "kind": "upload", "target": "f9"}]}
    [body] = run_node(_DRIVER, {"page": page}, tmp_path, source=SOURCE)["asks"]
    assert body["errors"] == [{"text": "Name", "fid": "f1"}, {"text": "Resume"}]


def test_an_action_that_answers_the_open_question_moves_the_run_on(tmp_path):
    out = think(tmp_path, open=[{"fid": "f1"}], fixes=["f1"], replies=[act(type="write", fid="f1")])
    assert out["out"]["moved"] is True and len(out["asks"]) == 1
    assert out["done"][0][2]["routes"] == {"f1": "free_text"} and out["done"][0][2]["reasoner"] == {"f1": "short"}
    [entry] = out["out"]["rounds"]
    assert entry["actions"] == [{"type": "write", "target": "f1", "outcome": "progress", "written": 11}]
    assert out["out"]["wrote"] == [{"fid": "f1", "question": "Q", "note": None}] and "Mathematics" not in str(out["out"])
    assert out["out"]["tried"] == ["answered Field of study"]


def test_each_field_action_runs_through_the_fill_loops_own_options(tmp_path):
    cases = [
        (act(type="fill", fids=["f1"]), {}),
        (act(type="answer_from", fid="f1", slot="preferences.how_heard"), {"slotHints": {"f1": "preferences.how_heard"}, "redo": ["f1"], "reasoned": "answer_from"}),
        (act(type="choose", fid="f1", basis="history"), {"routes": {"f1": "reasoned"}, "reasoned": "choose"}),
        (act(type="choose", fid="f1", basis="default"), {"routes": {"f1": "low_stakes"}, "reasoned": "choose"}),
        (act(type="retry", fid="f1", technique="open_with_keys"), {"variants": {"f1": {"open": "keys"}}}),
        (act(type="retry", fid="f1", technique="search_and_wait"), {"variants": {"f1": {"search": "debounce"}}}),
        (act(type="retry", fid="f1", technique="clear_and_set"), {"redo": ["f1"], "reasoned": "redo"}),
        (act(type="redo", fid="f2"), {"redo": ["f2"], "reasoned": "redo"}),
    ]
    for reply, scope in cases:
        assert think(tmp_path, replies=[reply])["done"][0][2] == scope


def test_a_multiline_write_asks_for_an_essay(tmp_path):
    page = {**PAGE, "fields": [{**PAGE["fields"][0], "multiline": True}, PAGE["fields"][1]]}
    out = run_node(_DRIVER, {"page": page, "replies": [act(type="write", fid="f1")]}, tmp_path, source=SOURCE)
    assert out["done"][0][2]["reasoner"] == {"f1": "essay"}


def test_a_round_that_leaves_the_page_unchanged_stops_the_loop(tmp_path):
    out = think(tmp_path, replies=[act(type="fill", fids=["f1"])] * 3)
    assert len(out["asks"]) == 1 and out["out"]["moved"] is False and out["out"]["rounds"][0]["stopped"] == "same_page"


def test_three_rounds_at_most_and_a_failed_signature_twice_is_excluded(tmp_path):
    out = think(tmp_path, open=[{"fid": "f1"}], flipEveryFill=True, replies=[act(type="fill", fids=["f1"])] * 5)
    assert len(out["asks"]) == 3     # round 3 asks for the excluded fill: it is refused, the page is unchanged, the loop ends
    assert out["out"]["rounds"][2]["actions"][0]["outcome"] == "rejected"
    assert [a["excluded"] for a in out["asks"]] == [[], [], ["fill:f1"]]
    assert [a["history"] for a in out["asks"]][2] == ["fill:f1 -> no_effect"] * 2


def test_a_fill_is_judged_per_field(tmp_path):
    out = think(tmp_path, open=[{"fid": "f1"}], flipEveryFill=True, fixes=["f2"], replies=[act(type="fill", fids=["f2", "f1"])] * 5)
    assert [a["excluded"] for a in out["asks"]] == [[], [], ["fill:f1"]]


def test_a_field_with_no_effect_twice_is_dropped_from_the_snapshot(tmp_path):
    out = think(tmp_path, open=[{"fid": "f1"}], flipEveryFill=True, replies=[act(type="fill", fids=["f1"])] * 3)
    assert "f1" in [f["fid"] for f in out["asks"][1]["fields"]] and "f1" not in [f["fid"] for f in out["asks"][2]["fields"]]


def test_the_page_clock_ends_the_loop(tmp_path):
    out = think(tmp_path, open=[{"fid": "f1"}], flipEveryFill=True, askMs=31000, replies=[act(type="fill", fids=["f1"])] * 3)
    assert len(out["asks"]) == 2


def test_ask_user_a_missing_reply_and_stop_each_end_it(tmp_path):
    asked = think(tmp_path, replies=[act(type="ask_user", fids=["f1"], note="Pick your degree.")])
    assert asked["out"]["moved"] is False and asked["out"]["note"] == "Field of study is empty." and asked["done"] == []
    assert asked["out"]["ask"] == "Pick your degree." and asked["out"]["rounds"][0]["stopped"] == "asked"
    assert think(tmp_path, replies=[])["out"]["rounds"][0]["stopped"] == "no_reply"
    stopped = think(tmp_path, stopAt=1, replies=[act(type="fill", fids=["f1"])])
    assert stopped["done"] == [] and stopped["out"]["rounds"][0]["stopped"] == "stopped"


def test_an_ask_user_beside_other_actions_runs_none_of_them(tmp_path):
    reply = {**act(type="fill", fids=["f1"]), "actions": [{"type": "fill", "fids": ["f1"]}, {"type": "ask_user", "fids": [], "note": "Help."}]}
    assert think(tmp_path, replies=[reply])["done"] == []


def test_press_next_goes_through_the_drivers_press_with_the_reads_own_id(tmp_path):
    out = think(tmp_path, replies=[act(type="press_next", button="b1")])
    assert out["done"] == [["press", 0, "fx-1", out["done"][0][3]]] and out["out"]["advanced"] == out["done"][0][3]
    assert out["out"]["moved"] is True and out["out"]["rounds"][0]["stopped"] == "moved"


def test_a_press_the_page_refused_or_rejected_is_a_failed_action_not_a_move(tmp_path):
    for outcome, word in (("refused", "refused"), ("rejected", "rejected"), ("same", "no_effect")):
        out = think(tmp_path, pressOutcome=outcome, replies=[act(type="press_next", button="b1")])
        assert out["out"]["moved"] is False and out["out"]["rounds"][0]["actions"][0]["outcome"] == word


def test_a_next_after_a_fill_is_found_again_in_a_fresh_read(tmp_path):
    reply = {**act(type="fill", fids=["f1"]), "actions": [{"type": "fill", "fids": ["f1"]}, {"type": "press_next", "button": "b1"}]}
    out = think(tmp_path, flipEveryFill=True, replies=[reply])
    assert [d[0] for d in out["done"]] == ["fill", "press"]
    assert out["done"][1][3] != "https://acme.wd5.myworkdayjobs.test/apply/questions\nk0\nClose,Save and Continue\n2"   # the page after the fill


def test_a_press_next_that_is_not_last_is_not_run(tmp_path):
    reply = {**act(type="fill", fids=["f1"]), "actions": [{"type": "press_next", "button": "b1"}, {"type": "fill", "fids": ["f1"]}]}
    out = think(tmp_path, replies=[reply])
    assert [d[0] for d in out["done"]] == ["fill"] and out["out"]["rounds"][0]["actions"][0]["outcome"] == "rejected"


def test_close_dialog_goes_through_the_hosts_guarded_dismiss(tmp_path):
    out = think(tmp_path, why="unknown_page", replies=[act(type="close_dialog", button="b2")])
    assert out["done"][0] == ["dismiss", 0, "fx-2"]


def test_a_dismiss_the_page_refused_is_a_refusal(tmp_path):
    out = think(tmp_path, dismissClicks=False, replies=[act(type="close_dialog", button="b2")])
    assert out["out"]["rounds"][0]["actions"][0]["outcome"] == "refused"


def test_an_action_naming_an_id_the_snapshot_never_carried_or_the_wrong_role_is_not_run(tmp_path):
    for bad in (act(type="fill", fids=["nope"]), act(type="press_next", button="b2"), act(type="close_dialog", button="b1"),
                act(type="press_next", button="b9"), act(type="follow_tab", tab="t1"), act(type="retry", fid="f1", technique="teleport")):
        out = think(tmp_path, replies=[bad])
        assert out["done"] == [] and out["out"]["rounds"][0]["actions"][0]["outcome"] == "rejected"


def test_a_page_it_cannot_read_allows_only_a_dialog_a_tab_or_a_question(tmp_path):
    assert think(tmp_path, why="unknown_page", replies=[act(type="press_next", button="b1")])["done"] == []
    assert think(tmp_path, why="unknown_page", replies=[act(type="fill", fids=["f1"])])["done"] == []
    away = {**PAGE, "tabs": [{"tabId": 7, "host": "jobs.acme.test"}]}
    out = run_node(_DRIVER, {"page": away, "why": "moved_away", "replies": [act(type="follow_tab", tab="t1")]}, tmp_path, source=SOURCE)
    assert out["done"] == [["follow", 7]] and out["out"]["followed"] is True and out["out"]["moved"] is False


def test_the_live_line_says_what_it_is_doing_in_the_pages_words(tmp_path):
    out = think(tmp_path, replies=[act(type="press_next", button="b1")])
    assert "Thinking: Field of study is empty." in out["lines"] and "Pressing Save and Continue…" in out["lines"]
    wrote = think(tmp_path, replies=[act(type="write", fid="f1")])
    assert "Answering Field of study…" in wrote["lines"]


def test_a_reply_that_is_not_a_reply_ends_the_round_as_no_reply(tmp_path):
    for junk in ({"note": "x", "actions": []}, {"note": "x", "actions": [{"type": "launch_missiles"}]}, "text"):
        assert think(tmp_path, replies=[junk])["out"]["rounds"][0]["stopped"] == "no_reply"


def button(id, text, **kw):
    return {"id": id, "text": text, "type": "button", "visible": True, "enabled": True, **kw}


def with_buttons(*buttons, **summary):
    return {**PAGE, "summary": {**PAGE["summary"], "buttons": list(buttons), **summary}}


def test_a_fill_that_turns_the_page_into_a_submit_question_ends_the_step_with_no_second_ask(tmp_path):
    asking = {**PAGE["summary"], "stepKey": "k9", "submitContext": True,
              "buttons": [button("fx-1", "Save and Continue", inForm=True), button("d-ok", "OK", overlay=True, inForm=False),
                          button("d-go", "Continue", overlay=True, inForm=False)]}
    for follow_up in (act(type="close_dialog", button="b2"), act(type="press_next", button="b3")):
        out = think(tmp_path, open=[{"fid": "f1"}], afterFill=asking, replies=[act(type="fill", fids=["f1"]), follow_up])
        assert len(out["asks"]) == 1 and [d[0] for d in out["done"]] == ["fill"]
        assert out["out"]["moved"] is False and out["out"]["rounds"][0]["stopped"] == "wall"


def test_a_page_that_is_already_a_review_or_a_wall_is_not_asked_about(tmp_path):
    for kind in (with_buttons(button("s", "Submit application", inForm=True)), with_buttons(button("n", "Next"), captchaVisible=True)):
        out = run_node(_DRIVER, {"page": kind, "replies": [act(type="fill", fids=["f1"])]}, tmp_path, source=SOURCE)
        assert out["asks"] == [] and out["done"] == [] and out["out"]["rounds"][0]["stopped"] == "wall"


def test_only_the_next_the_classifier_names_is_offered_and_a_submit_question_offers_no_dialog_button(tmp_path):
    page = with_buttons(button("dis", "Next", enabled=False, inForm=True), button("go", "Save and Continue", inForm=True),
                        button("tour", "Continue", overlay=True, inForm=False), button("x", "Close", overlay=True, inForm=False))
    [body] = run_node(_DRIVER, {"page": page}, tmp_path, source=SOURCE)["asks"]
    assert body["buttons"] == [{"ref": "b1", "text": "Save and Continue", "role": "next"}, {"ref": "b2", "text": "Close", "role": "dialog"}]


def test_a_refusal_is_a_dialog_button_only_in_a_cookie_notice_and_an_ok_only_when_it_asks_nothing(tmp_path):
    page = with_buttons(button("go", "Save and Continue", inForm=True),
                        button("a", "Decline", overlay=True, inForm=False), button("b", "Decline", overlay=True, cookie=True, inForm=False),
                        button("c", "OK", overlay=True, overlayAsks=True, inForm=False), button("d", "OK", overlay=True, inForm=False))
    [body] = run_node(_DRIVER, {"page": page}, tmp_path, source=SOURCE)["asks"]
    assert [(b["text"], b["role"]) for b in body["buttons"]] == [("Save and Continue", "next"), ("Decline", "dialog"), ("OK", "dialog")]


def test_a_next_after_a_fill_is_the_one_the_classifier_names_not_the_first_with_the_same_words(tmp_path):
    before = with_buttons(button("form-next", "Next", inForm=True))
    after = {**before["summary"], "buttons": [button("tour-next", "Next", overlay=True, inForm=False), button("form-next-2", "Next", inForm=True)]}
    reply = {**act(type="fill", fids=["f1"]), "actions": [{"type": "fill", "fids": ["f1"]}, {"type": "press_next", "button": "b1"}]}
    out = run_node(_DRIVER, {"page": before, "afterFill": after, "replies": [reply]}, tmp_path, source=SOURCE)
    assert out["done"][1][:3] == ["press", 0, "form-next-2"]


def test_a_dialog_button_found_again_must_be_the_only_one_with_its_words(tmp_path):
    before = with_buttons(button("go", "Save and Continue", inForm=True), button("c1", "Close", overlay=True, inForm=False))
    twice = {**before["summary"], "buttons": [*before["summary"]["buttons"], button("c2", "Close", overlay=True, inForm=False)]}
    reply = {**act(type="fill", fids=["f1"]), "actions": [{"type": "fill", "fids": ["f1"]}, {"type": "close_dialog", "button": "b2"}]}
    assert [d[0] for d in run_node(_DRIVER, {"page": before, "afterFill": twice, "replies": [reply]}, tmp_path, source=SOURCE)["done"]] == ["fill"]
    once = run_node(_DRIVER, {"page": before, "afterFill": before["summary"], "replies": [reply]}, tmp_path, source=SOURCE)
    assert once["done"][1] == ["dismiss", 0, "c1"]


def test_the_page_clock_is_checked_before_every_action(tmp_path):
    reply = {**act(type="fill", fids=["f1"]), "actions": [{"type": "fill", "fids": ["f1"]}, {"type": "fill", "fids": ["f2"]}]}
    out = think(tmp_path, fillMs=61000, replies=[reply])
    assert [d[1] for d in out["done"]] == [["f1"]] and out["out"]["rounds"][0]["stopped"] == "clock"


def test_a_button_that_failed_twice_stays_excluded_when_the_button_list_renumbers(tmp_path):
    before = with_buttons(button("go", "Save and Continue", inForm=True))
    after = {**before["summary"], "buttons": [button("x", "Close", overlay=True, inForm=False), button("go", "Save and Continue", inForm=True)]}
    # Round 1 sees the Next as b1, rounds 2 and 3 as b2.
    first = {**act(type="fill", fids=["f1"]), "actions": [{"type": "fill", "fids": ["f1"]}, {"type": "press_next", "button": "b1"}]}
    later = {**first, "actions": [{"type": "fill", "fids": ["f1"]}, {"type": "press_next", "button": "b2"}]}
    out = run_node(_DRIVER, {"page": before, "open": [{"fid": "f1"}], "flipEveryFill": True, "afterFill": after,
                             "pressOutcome": "refused", "replies": [first, later, later]}, tmp_path, source=SOURCE)
    assert len(out["asks"]) == 3
    assert "press_next:b2" in out["asks"][2]["excluded"] and not any(e.startswith("press_next:b1") for e in out["asks"][2]["excluded"])


def test_a_field_the_user_touched_or_one_the_run_did_not_fill_is_never_redone_or_remapped(tmp_path):
    other = {"fid": "f3", "question": "Town", "shape": "select", "kind": "choice", "required": True, "answered": True, "committed": "x", "options": None}
    page = {**PAGE, "fields": [{**PAGE["fields"][1], "touched": True}, PAGE["fields"][0], other,
                               {**PAGE["fields"][1], "fid": "f4"}], "lastFill": {"f2": {"status": "verified"}, "f4": {"status": "verified"}}}
    for fid in ("f2", "f3"):   # f2 is the user's, f3 was filled by nobody the run knows
        for reply in (act(type="redo", fid=fid), act(type="retry", fid=fid, technique="clear_and_set"),
                      act(type="answer_from", fid=fid, slot="personal.city")):
            out = run_node(_DRIVER, {"page": page, "replies": [reply]}, tmp_path, source=SOURCE)
            assert out["done"] == [] and out["out"]["rounds"][0]["actions"][0]["outcome"] == "rejected"
    ok = run_node(_DRIVER, {"page": page, "replies": [act(type="redo", fid="f4")]}, tmp_path, source=SOURCE)
    assert ok["done"][0][2] == {"redo": ["f4"], "reasoned": "redo"}


def test_answer_from_on_a_multi_value_field_never_asks_for_a_redo(tmp_path):
    page = {**PAGE, "fields": [{**PAGE["fields"][0], "multi": True}, PAGE["fields"][1]]}
    out = run_node(_DRIVER, {"page": page, "replies": [act(type="answer_from", fid="f1", slot="skills")]}, tmp_path, source=SOURCE)
    assert out["done"][0][2] == {"slotHints": {"f1": "skills"}, "reasoned": "answer_from"}


def test_the_limits_and_actions_mirror_the_backends_schema():
    js = (ROOT / "extension" / "shared" / "reason-loop.js").read_text(encoding="utf-8")
    limits = dict(re.findall(r"(\w+): (\d+)", re.search(r"const LIMITS = Object\.freeze\(\{(.*?)\}\)", js, re.S).group(1)))
    assert {k: int(limits[k]) for k in ("rounds", "actions", "fields", "options", "history", "buttons", "errors", "tabs", "excluded", "note", "text")} == {
        "rounds": R.MAX_ROUNDS, "actions": R.MAX_ACTIONS, "fields": R.MAX_FIELDS, "options": R.MAX_OPTIONS,
        "history": R.MAX_HISTORY, "buttons": R.MAX_BUTTONS, "errors": R.MAX_ERRORS, "tabs": R.MAX_TABS,
        "excluded": R.MAX_EXCLUDED, "note": R.NOTE_MAX, "text": R.TEXT_MAX}
    assert re.findall(r'"([a-z_]+)"', re.search(r"const ACTIONS = Object\.freeze\(\[(.*?)\]\)", js, re.S).group(1)) == list(R.ACTION_TYPES)


def test_the_model_is_not_asked_with_less_than_25_seconds_left_on_the_page_clock(tmp_path):
    # The first reply takes 36 s: 24 s remain, too little for a call the backend gives 25 s.
    out = think(tmp_path, open=[{"fid": "f1"}], flipEveryFill=True, askMs=36000, replies=[act(type="fill", fids=["f1"])] * 3)
    assert len(out["asks"]) == 1 and out["out"]["rounds"][-1]["stopped"] == "clock"
