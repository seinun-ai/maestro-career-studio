"""The reasoning loop (shared/reason-loop.js), pure: a fake page and a scripted reasoner drive it in node.

Pins: the snapshot is value-free and capped; at most 3 rounds, 3 actions each, 60 s a page; a signature that
failed twice is sent back as excluded; a field with no effect twice is dropped; a round that changes nothing ends
it; ask_user, a missing reply and Stop end it; press_next goes only through the driver's own press."""

import json
import re

from app.schemas import autofill_reason as R
from tests.extension_harness import ROOT, run_node

SOURCE = "\n".join((ROOT / "extension" / "shared" / name).read_text(encoding="utf-8")
                   for name in ("decisions.js", "fill-loop.js", "page-kind.js", "queue-run.js", "reason-loop.js"))

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
  read: async () => (spec.noRead ? null : JSON.parse(JSON.stringify(page))),
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
    assert out["out"]["wrote"] == [{"fid": "f1", "question": "Q", "note": "Written for you: read it"}] and "Mathematics" not in str(out["out"])
    assert out["out"]["tried"] == ["answering Field of study; it took"]


def test_each_field_action_runs_through_the_fill_loops_own_options(tmp_path):
    cases = [
        (act(type="fill", fids=["f1"]), {}),
        (act(type="answer_from", fid="f1", slot="preferences.how_heard"), {"slotHints": {"f1": "preferences.how_heard"}, "redo": ["f1"], "reasoned": "answer_from"}),
        (act(type="choose", fid="f1", basis="history"), {"routes": {"f1": "reasoned"}, "reasoned": "choose"}),
        (act(type="choose", fid="f1", basis="default"), {"routes": {"f1": "low_stakes"}, "reasoned": "choose"}),
        (act(type="retry", fid="f1", technique="open_with_keys"), {"variants": {"f1": {"open": "keys"}}}),
        (act(type="retry", fid="f1", technique="search_and_wait"), {"variants": {"f1": {"search": "debounce"}}}),
        (act(type="retry", fid="f1", technique="step_by_step"), {"stepByStep": ["f1"]}),
        (act(type="retry", fid="f1", technique="clear_and_set"), {"redo": ["f1"], "reasoned": "redo"}),
        (act(type="redo", fid="f2"), {"redo": ["f2"], "reasoned": "redo"}),
    ]
    for reply, scope in cases:
        assert think(tmp_path, replies=[reply])["done"][0][2] == scope


def test_what_it_tried_reads_after_it_tried_and_says_how_each_attempt_went(tmp_path):
    cases = [
        (act(type="retry", fid="f1", technique="search_with_enter"), "Field of study a second way; it didn't take", {}),
        (act(type="retry", fid="f1", technique="step_by_step"), "Field of study a second way; it didn't take", {}),
        (act(type="fill", fids=["f1"]), "filling 1 field; it took", {"fixes": ["f1"]}),
        (act(type="choose", fid="f1", basis="history"), "choosing an option for Field of study; it didn't take", {}),
        (act(type="redo", fid="f2"), "First name again; it didn't take", {}),
    ]
    for reply, tried, spec in cases:
        out = think(tmp_path, replies=[reply], **spec)
        assert out["out"]["tried"] == [tried], (reply, out["out"]["tried"])
    pressed = think(tmp_path, replies=[act(type="press_next", button="b1")], why="no_change")
    assert pressed["out"]["tried"] == ["pressing Save and Continue; it took"]


def test_a_long_question_is_cut_so_the_outcome_of_the_attempt_always_survives_the_cards_cut(tmp_path):
    long = "Please tell us which of the following best describes where you first heard about this job opening today"[:80]
    assert len(long) == 80
    page = {**PAGE, "fields": [{**PAGE["fields"][0], "question": long}, PAGE["fields"][1]]}
    for reply in (act(type="retry", fid="f1", technique="step_by_step"), act(type="choose", fid="f1", basis="history"),
                  act(type="press_next", button="b1")):
        out = run_node(_DRIVER, {"page": page, "replies": [reply], "why": "no_change"}, tmp_path, source=SOURCE)
        [one] = out["out"]["tried"]
        assert len(one) <= 100 and one.endswith(("; it didn't take", "; it took")), one


def test_a_field_with_no_question_is_called_a_field(tmp_path):
    page = {**PAGE, "fields": [{**PAGE["fields"][0], "question": ""}, PAGE["fields"][1]]}
    out = run_node(_DRIVER, {"page": page, "replies": [act(type="retry", fid="f1", technique="step_by_step")]}, tmp_path, source=SOURCE)
    assert out["out"]["tried"] == ["a field a second way; it didn't take"]
    out = run_node(_DRIVER, {"page": page, "replies": [act(type="write", fid="f1")]}, tmp_path, source=SOURCE)
    assert out["out"]["tried"][0].startswith("answering a field;")


def test_each_attempt_is_a_phrase_to_follow_it_tried_not_a_sentence_with_its_own_verb(tmp_path):
    out = think(tmp_path, replies=[act(type="retry", fid="f1", technique="clear_and_set")], fixes=["f1"])
    [one] = out["out"]["tried"]
    assert not re.match(r"(tried|filled|answered|chose|pressed|closed)\b", one)


def test_the_trace_keeps_the_retry_technique_and_the_choose_basis_and_nothing_else_about_them(tmp_path):
    from app.schemas.autofill_trace import RunTrace

    retry = think(tmp_path, replies=[act(type="retry", fid="f1", technique="step_by_step")])["out"]["rounds"]
    choose = think(tmp_path, replies=[act(type="choose", fid="f1", basis="history")])["out"]["rounds"]
    assert retry[0]["actions"][0]["technique"] == "step_by_step" and "basis" not in retry[0]["actions"][0]
    assert choose[0]["actions"][0]["basis"] == "history" and "technique" not in choose[0]["actions"][0]
    for rounds, key, word in ((retry, "technique", "step_by_step"), (choose, "basis", "history")):
        [round_] = RunTrace.model_validate(trace_of(tmp_path, rounds)).reasoning
        assert getattr(round_.actions[0], key) == word


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


_TRACE = r"""const ns = loadModules(); emit(ns.reasonLoop.traceOf(spec.rounds, { host: spec.host ?? "acme.wd5.myworkdayjobs.test",
  startedAt: new Date(0), endedAt: new Date(1000) }));"""


def trace_of(tmp_path, rounds, **spec):
    return run_node(_TRACE, {"rounds": rounds, **spec}, tmp_path, source=SOURCE)


def test_the_trace_rounds_post_as_a_run_the_backend_accepts_and_hold_no_value(tmp_path):
    out = think(tmp_path, open=[{"fid": "f1"}], fixes=["f1"], replies=[act(type="write", fid="f1")])
    trace = trace_of(tmp_path, out["out"]["rounds"])
    from app.schemas.autofill_trace import RunTrace
    run = RunTrace.model_validate(trace)
    assert run.fields == [] and run.reasoning[0].actions[0].written == 11 and "Mathematics" not in str(trace)
    assert run.reasoning[0].model == "m" and run.reasoning[0].stopped == "resolved" and run.host == "acme.wd5.myworkdayjobs.test"
    assert re.fullmatch(r"[0-9a-z-]{8,64}", run.run_id)


def test_each_round_keeps_what_the_model_was_shown_without_the_jobs_selectors(tmp_path):
    driver = _DRIVER.replace("const ctx = {", "const ctx = { applicationId: 'app-1', pageUrl: 'https://acme.test/apply?x=1', ")
    out = run_node(driver, {"page": PAGE, "open": [{"fid": "f1"}], "replies": [act(type="fill", fids=["f1"])]}, tmp_path,
                   source=SOURCE)
    trace = trace_of(tmp_path, out["out"]["rounds"])
    from app.schemas.autofill_trace import RunTrace
    [round_] = RunTrace.model_validate(trace).reasoning
    assert [f.fid for f in round_.snapshot.fields] == ["f1", "f2"] and round_.snapshot.buttons[0].role == "next"
    assert not {"application_id", "base", "page_url", "today", "why", "round"} & set(trace["reasoning"][0]["snapshot"])
    assert "app-1" not in str(trace) and "x=1" not in str(trace)


def test_the_stored_snapshot_is_capped_far_under_the_schemas_size(tmp_path):
    many = {**PAGE, "fields": [{**PAGE["fields"][0], "fid": f"f{i}", "question": "q" * 400,
                                "options": [{"oid": f"o{j}", "text": "t" * 400} for j in range(25)]} for i in range(70)]}
    out = run_node(_DRIVER, {"page": many, "replies": [act(type="fill", fids=["f0"])]}, tmp_path, source=SOURCE)
    trace = trace_of(tmp_path, out["out"]["rounds"])
    from app.schemas.autofill_trace import RunTrace
    snap = RunTrace.model_validate(trace).reasoning[0].snapshot
    assert len(snap.fields) == 30 and all(len(f.options) == 8 and f.option_count == 25 for f in snap.fields)
    assert len(snap.model_dump_json()) < 80_000


def test_a_round_records_the_fact_name_an_answer_from_chose_and_never_a_value(tmp_path):
    out = think(tmp_path, replies=[act(type="answer_from", fid="f1", slot="preferences.how_heard")])
    [round_] = trace_of(tmp_path, out["out"]["rounds"])["reasoning"]
    assert round_["actions"][0] == {"type": "answer_from", "target": "f1", "outcome": "no_effect", "slot": "preferences.how_heard"}


def test_a_step_with_no_rounds_or_no_usable_host_posts_no_trace(tmp_path):
    clock = [{"round": 1, "why": "page_errors", "model": None, "ms": 0, "note": "", "actions": [], "rejected": [], "stopped": "clock"}]
    assert trace_of(tmp_path, clock) is None and trace_of(tmp_path, []) is None
    asked = think(tmp_path, replies=[act(type="fill", fids=["f1"])])["out"]["rounds"]
    assert trace_of(tmp_path, asked, host="not a host") is None and trace_of(tmp_path, asked, host="") is None


def test_a_step_that_could_not_read_the_page_leaves_a_round_that_says_so(tmp_path):
    out = think(tmp_path, noRead=True, replies=[act(type="fill", fids=["f1"])])
    assert out["asks"] == [] and out["done"] == []
    [round_] = out["out"]["rounds"]
    assert (round_["stopped"], round_["model"], round_["why"]) == ("no_read", None, "open_questions")


def test_an_exit_with_no_model_call_still_posts_a_trace_row_the_backend_accepts(tmp_path):
    from app.schemas.autofill_trace import RunTrace
    unread = think(tmp_path, noRead=True)["out"]["rounds"]
    walled = think(tmp_path, page=with_buttons(button("n", "Next"), captchaVisible=True))["out"]["rounds"]
    for rounds, stop in ((unread, "no_read"), (walled, "wall")):
        trace = trace_of(tmp_path, rounds)
        run = RunTrace.model_validate(trace)
        assert run.fields == [] and [r.stopped for r in run.reasoning] == [stop] and run.reasoning[0].model is None


def _globex(**over):
    """A page where the user typed an employer, and the page says it back in a sibling's question, an option list and an error."""
    fields = [
        {"fid": "e1", "question": "Employer", "shape": "text", "kind": "text", "required": True, "answered": True,
         "committed": "Globex Corp", "options": None},
        {"fid": "e2", "question": "Do you still work at Globex Corp?", "shape": "text", "kind": "text", "required": True,
         "answered": False, "committed": "", "options": None},
        {"fid": "e3", "question": "Which employer was your longest?", "shape": "select", "kind": "select", "required": True,
         "answered": False, "committed": "", "options": [{"oid": "o1", "text": "Globex Corp"}, {"oid": "o2", "text": "Initech"}]},
        {"fid": "e4", "question": "Field of study", "shape": "text", "kind": "text", "required": True, "answered": False,
         "committed": "", "options": None},
    ]
    return {**PAGE, "fields": fields, "errors": [{"label": "Globex Corp is invalid", "kind": "other", "target": None}],
            "lastFill": {}, **over}


def test_a_value_the_user_typed_is_blanked_from_every_sibling_question_option_and_error_line(tmp_path):
    out = run_node(_DRIVER, {"page": _globex(), "replies": [act(type="fill", fids=["e4"])]}, tmp_path, source=SOURCE)
    [body] = out["asks"]
    R.ReasonRequest.model_validate(body)
    by_fid = {f["fid"]: f for f in body["fields"]}
    assert by_fid["e1"]["question"] == "Employer"                # the field's own question holds no value
    assert by_fid["e2"]["question"] == "Do you still work at [your answer]?"   # only the value goes, the words stay
    assert [o["text"] for o in by_fid["e3"]["options"]] == ["", "Initech"]
    assert by_fid["e4"]["question"] == "Field of study"           # nothing else is touched
    assert body["errors"] == [{"text": "[your answer] is invalid"}]
    trace = trace_of(tmp_path, out["out"]["rounds"])
    assert "Globex" not in json.dumps(body) and "Globex" not in json.dumps(trace) and "Globex" not in json.dumps(out["out"])


def test_the_screens_leave_the_pages_own_words_and_common_option_words_alone(tmp_path):
    page = _globex(fields=[
        {"fid": "e1", "question": "Phone type", "shape": "select", "kind": "select", "required": True, "answered": True,
         "committed": "Mobile", "options": [{"oid": "o1", "text": "Mobile"}, {"oid": "o2", "text": "Home"}]},
        {"fid": "e2", "question": "Do you use T-Mobile?", "shape": "text", "kind": "text", "required": False, "answered": False,
         "committed": "", "options": None}], errors=[{"label": "Phone type is required", "kind": "other", "target": None}])
    [body] = run_node(_DRIVER, {"page": page, "replies": [act(type="fill", fids=["e2"])]}, tmp_path, source=SOURCE)["asks"]
    assert [f["question"] for f in body["fields"]] == ["Phone type", "Do you use T-Mobile?"]
    assert [o["text"] for o in body["fields"][0]["options"]] == ["Mobile", "Home"]
    assert body["errors"] == [{"text": "Phone type is required"}]


def test_a_protected_question_keeps_its_words_when_a_sibling_holds_a_value_it_names(tmp_path):
    fields = [
        {"fid": "c1", "question": "Country", "shape": "text", "kind": "text", "required": True, "answered": True,
         "committed": "United States", "options": None},
        {"fid": "c2", "question": "Are you legally authorized to work in the United States?", "shape": "select", "kind": "select",
         "required": True, "answered": False, "committed": "", "options": [{"oid": "o1", "text": "Yes"}, {"oid": "o2", "text": "No"}]}]
    [body] = run_node(_DRIVER, {"page": _globex(fields=fields, errors=[]), "replies": [act(type="fill", fids=["c2"])]}, tmp_path,
                      source=SOURCE)["asks"]
    question = {f["fid"]: f for f in body["fields"]}["c2"]["question"]
    assert question == "Are you legally authorized to work in the [your answer]?"
    from app.schemas.autofill_reason import SnapField
    from app.services import autofill_reason
    assert autofill_reason.protected(SnapField(fid="c2", question=question, shape="select"))     # the backend still sees the words


def test_an_error_line_is_screened_with_the_sibling_floors_so_a_step_number_survives(tmp_path):
    fields = [
        {"fid": "n1", "question": "Years of experience", "shape": "text", "kind": "text", "required": True, "answered": True,
         "committed": "5", "options": None},
        {"fid": "n2", "question": "Hours", "shape": "text", "kind": "text", "required": True, "answered": True,
         "committed": "Yes", "options": None},
        {"fid": "n3", "question": "Employer", "shape": "text", "kind": "text", "required": True, "answered": True,
         "committed": "Globex Corp", "options": None}]
    errors = [{"label": "Error - Step 5 of 7: Source is required. Yes. Globex Corp too.", "kind": "other", "target": None}]
    [body] = run_node(_DRIVER, {"page": _globex(fields=fields, errors=errors), "replies": [act(type="fill", fids=["n1"])]}, tmp_path,
                      source=SOURCE)["asks"]
    assert body["errors"] == [{"text": "Error - Step 5 of 7: Source is required. Yes. [your answer] too."}]
