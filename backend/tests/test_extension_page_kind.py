"""The page-kind classifier and the button sort (queued-run plan Task 12).

`extension/shared/page-kind.js` is PURE: it reads a plain summary the page builds, so these
tests drive it in node with no DOM. The one rule they hold: a button carrying any Submit word
sorts "submit", is never offered as the Next to click, and turns a page into "review" (the run
stops); every ambiguity breaks toward "submit" or "unclear", never toward "next". A Next that
was really a Submit is the worst bug this feature could have.
"""

import itertools
from pathlib import Path

import pytest

from tests.extension_harness import run_node

PAGE_KIND_JS = (Path(__file__).resolve().parents[2] / "extension" / "shared" / "page-kind.js").read_text(
    encoding="utf-8")

_DRIVER = r"""
const ns = loadModules();
emit({
  sorted: (spec.buttons || []).map((b) => ns.pageKind.sortButton(b)),
  classified: (spec.summaries || []).map((s) => ns.pageKind.classify(s)),
  kinds: ns.pageKind.KINDS,
  plain: (spec.plain || []).map((t) => ns.pageKind.isPlainNext(t)),
});
"""


def _run(tmp_path, buttons=(), summaries=(), plain=()):
    return run_node(_DRIVER, {"buttons": list(buttons), "summaries": list(summaries), "plain": list(plain)}, tmp_path,
                    source=PAGE_KIND_JS)


def sort_all(tmp_path, texts, **extra):
    return _run(tmp_path, [{"text": t, **extra} for t in texts])["sorted"]


def sort(tmp_path, text, **extra):
    return sort_all(tmp_path, [text], **extra)[0]


NEXT = ["Next", "Continue", "Save and Continue", "Save & continue", "Review", "Review application",
        "Proceed", "Next step"]
SUBMIT = ["Submit", "Submit application", "Apply", "Apply now", "Send application", "Finish", "Complete",
          "Confirm", "Continue to submit", "Submit and continue", "Review and submit"]


@pytest.mark.parametrize("text", NEXT)
def test_next_words_sort_as_next(tmp_path, text):
    assert sort(tmp_path, text) == "next"


@pytest.mark.parametrize("text", SUBMIT)
def test_any_submit_word_sorts_as_submit_even_beside_a_next_word(tmp_path, text):
    assert sort(tmp_path, text) == "submit"


def test_a_submit_type_button_is_decided_by_its_text_not_its_type(tmp_path):
    """Many wizards use <button type="submit">Next</button> for every step, so the type alone says
    nothing; the text decides, and a Submit word in it still wins."""
    assert sort(tmp_path, "Next", type="submit") == "next"
    assert sort(tmp_path, "Submit application", type="button") == "submit"
    assert sort(tmp_path, "Go", type="submit") == "unclear"


def test_unlabelled_or_odd_buttons_are_unclear(tmp_path):
    texts = ["", "   ", "Go", "Save", "Done", "→", "Back", "Cancel", "Add another", "Upload", None]
    assert sort_all(tmp_path, texts) == ["unclear"] * len(texts)


def test_a_missing_text_is_unclear(tmp_path):
    assert _run(tmp_path, [{}])["sorted"] == ["unclear"]


@pytest.mark.parametrize("text", [
    "SUBMIT", "submit", "  Submit  ", "Sub­mit", "Submit application", "Submit\n application",
    "Submit!", "(Submit)", "Submit →", "Submit_application", "submitApplication", "Apply-now",
    "Next: Review & Submit", "Applying…", "Sending", "Completed", "Finish & submit", "Confirm and apply",
    "Finalize", "Finalise application", "Send", "Reapply",
])
def test_submit_wording_variants_still_sort_as_submit(tmp_path, text):
    assert sort(tmp_path, text) == "submit"


@pytest.mark.parametrize("text", ["Next →", "Next >", "Continue »", "NEXT", "  next  ", "Next step",
                                  "Save and Next", "Review your application", "Continue."])
def test_next_with_decoration_or_case_is_still_next(tmp_path, text):
    assert sort(tmp_path, text) == "next"


@pytest.mark.parametrize("text", [
    "Next, then submit", "Continue or apply", "Next / Submit", "Review application and send",
])
def test_a_next_word_never_launders_a_submit_word(tmp_path, text):
    assert sort(tmp_path, text) == "submit"


@pytest.mark.parametrize("text", [
    "Next section of the application questions", "Continue editing", "Review later", "Please continue",
])
def test_next_must_be_the_whole_button_not_a_prefix(tmp_path, text):
    """Anchored: a longer sentence that merely contains "continue" is not known to be a Next."""
    assert sort(tmp_path, text) == "unclear"


@pytest.mark.parametrize("text", ["Consent", "I consent", "Present", "Represent", "Apple", "Applicant info",
                                  "Applications"])
def test_words_that_merely_contain_a_submit_stem_are_unclear(tmp_path, text):
    """"sent" ends Consent/Present/Represent and "appl" starts Apple/Applicant. Not submit, and not
    next either: an exact "unclear" so neither error can hide behind the other."""
    assert sort(tmp_path, text) == "unclear"


@pytest.mark.parametrize("text", ["Send", "Sent", "Send application", "Resend", "send_application",
                                  "sendApplication", "I consent and send"])
def test_send_and_sent_as_whole_words_still_submit(tmp_path, text):
    assert sort(tmp_path, text) == "submit"


def test_a_consent_step_is_a_form_step_not_a_review(tmp_path):
    out = kind(tmp_path, fillable=1, buttons=[btn("I consent", id="x"), btn("Continue", id="n")])
    assert out == {"kind": "form_step", "next": "n"}


def test_application_is_not_the_word_apply(tmp_path):
    assert sort(tmp_path, "Review application") == "next"
    assert sort(tmp_path, "Applications") == "unclear"


def test_known_marker_table_can_name_next_but_never_beats_a_submit_word(tmp_path):
    """`known` is Task 14's table. It may promote an unclear button either way, but a Submit word
    in the text forces "submit" whatever it says."""
    out = _run(tmp_path, [
        {"text": "Go", "known": "next"},
        {"text": "Go", "known": "submit"},
        {"text": "Next", "known": "submit"},
        {"text": "Submit", "known": "next"},
        {"text": "Submit application", "known": "next"},
        {"text": "Go", "known": "something else"},
        {"text": "Go", "known": None},
    ])
    assert out["sorted"] == ["next", "submit", "submit", "submit", "submit", "unclear", "unclear"]


# ---------- page kinds ----------

def btn(text, *, id=None, visible=True, enabled=True, in_form=True, known=None, chrome=False, overlay=False):
    out = {"id": id or text, "text": text, "type": "button", "marker": "", "inForm": in_form,
           "visible": visible, "enabled": enabled}
    if known:
        out["known"] = known
    if chrome:
        out["chrome"] = True
    if overlay:
        out["overlay"] = True
    return out


def summary(**kw):
    base = {"host": "jobs.acme.example", "buttons": [], "passwordInputs": 0, "confirmPassword": False,
            "otpInput": False, "captchaVisible": False, "fillable": 0, "hasApplyLink": False,
            "confirmationText": False, "closedText": False, "boardNative": False}
    return {**base, **kw}


def kind(tmp_path, **kw):
    return _run(tmp_path, summaries=[summary(**kw)])["classified"][0]


def test_the_kinds_roster_is_pinned(tmp_path):
    assert _run(tmp_path)["kinds"] == [
        "captcha", "create_account", "verify", "sign_in", "confirmation", "closed", "posting",
        "board_native", "form_step", "review", "unknown"]


def test_captcha_beats_everything(tmp_path):
    out = kind(tmp_path, captchaVisible=True, passwordInputs=1, confirmPassword=True, otpInput=True,
               confirmationText=True, closedText=True, hasApplyLink=True, fillable=3,
               buttons=[btn("Next")])
    assert out["kind"] == "captcha"


def test_create_account_is_a_confirm_password_field(tmp_path):
    assert kind(tmp_path, passwordInputs=2, confirmPassword=True, otpInput=True)["kind"] == "create_account"
    # The flag alone, with one password input (a confirm field the counter missed), still parks.
    assert kind(tmp_path, passwordInputs=1, confirmPassword=True)["kind"] == "create_account"


def test_two_password_inputs_without_a_confirm_flag_still_park_as_create_account(tmp_path):
    """Never a form_step: filling a password field is not this run's to attempt."""
    assert kind(tmp_path, passwordInputs=2, fillable=2, buttons=[btn("Next")])["kind"] == "create_account"
    assert kind(tmp_path, passwordInputs=3, fillable=2, buttons=[btn("Next")])["kind"] == "create_account"


def test_verify_is_a_one_time_code_input(tmp_path):
    assert kind(tmp_path, otpInput=True, fillable=1, buttons=[btn("Continue")])["kind"] == "verify"


def test_sign_in_is_exactly_one_password_input_and_no_confirm(tmp_path):
    assert kind(tmp_path, passwordInputs=1, fillable=2, buttons=[btn("Continue")])["kind"] == "sign_in"


def test_confirmation_needs_the_text_and_no_fillable_field(tmp_path):
    assert kind(tmp_path, confirmationText=True)["kind"] == "confirmation"
    assert kind(tmp_path, confirmationText=True, fillable=2, buttons=[btn("Next")])["kind"] != "confirmation"


def test_closed_is_the_closed_text_on_a_page_with_nothing_to_fill_and_no_apply(tmp_path):
    assert kind(tmp_path, closedText=True)["kind"] == "closed"
    assert kind(tmp_path, closedText=True, buttons=[btn("Back")])["kind"] == "closed"


def test_the_closed_words_in_a_posting_that_still_has_an_apply_or_a_form_are_not_a_closed_page(tmp_path):
    """A job description can say "this position is filled…" in its prose; an Apply or a form says it is open."""
    assert kind(tmp_path, closedText=True, hasApplyLink=True)["kind"] == "posting"
    assert kind(tmp_path, closedText=True, fillable=2, buttons=[btn("Next", id="n")]) == {"kind": "form_step", "next": "n"}


def test_posting_is_an_apply_link_and_nothing_to_fill(tmp_path):
    assert kind(tmp_path, hasApplyLink=True)["kind"] == "posting"
    assert kind(tmp_path, hasApplyLink=True, boardNative=True)["kind"] == "board_native"


def test_an_apply_link_beside_a_fillable_form_is_not_a_posting(tmp_path):
    assert kind(tmp_path, hasApplyLink=True, fillable=3, buttons=[btn("Next")])["kind"] == "form_step"


def test_a_job_boards_own_page_is_board_native_whatever_else_is_on_it(tmp_path):
    """Easy Apply is no "Apply" link, a stray control must not make it a form, and the board's
    sign-in must never be read as an employer's (the saved password is not the board's)."""
    assert kind(tmp_path, boardNative=True)["kind"] == "board_native"
    assert kind(tmp_path, boardNative=True, buttons=[btn("Easy Apply")], fillable=0)["kind"] == "board_native"
    assert kind(tmp_path, boardNative=True, fillable=1, buttons=[btn("Next")])["kind"] == "board_native"
    assert kind(tmp_path, boardNative=True, passwordInputs=1)["kind"] == "board_native"
    assert kind(tmp_path, boardNative=True, passwordInputs=2, confirmPassword=True)["kind"] == "board_native"
    assert kind(tmp_path, boardNative=True, captchaVisible=True)["kind"] == "captcha"


def test_a_dialog_or_heading_that_asks_about_submitting_makes_its_proceed_a_review(tmp_path):
    """{Proceed, Cancel} in a "Submit your application?" dialog: Proceed sorts "next", and was a
    form_step."""
    buttons = [btn("Proceed", id="p"), btn("Cancel")]
    assert kind(tmp_path, fillable=0, buttons=buttons)["kind"] == "form_step"
    assert kind(tmp_path, fillable=0, buttons=buttons, submitContext=True)["kind"] == "review"
    assert kind(tmp_path, fillable=3, buttons=buttons, submitContext=True)["kind"] == "review"


def test_a_submit_the_button_list_could_not_see_stops_the_run(tmp_path):
    buttons = [btn("Next", id="n")]
    assert kind(tmp_path, fillable=2, buttons=buttons)["kind"] == "form_step"
    assert kind(tmp_path, fillable=2, buttons=buttons, submitSeen=True)["kind"] == "review"


def test_the_submit_context_never_hides_a_confirmation_or_a_closed_page(tmp_path):
    assert kind(tmp_path, confirmationText=True, submitContext=True)["kind"] == "confirmation"
    assert kind(tmp_path, closedText=True, submitContext=True)["kind"] == "closed"


def test_form_step_carries_the_one_next_button_id(tmp_path):
    out = kind(tmp_path, fillable=4, buttons=[btn("Back"), btn("Save and Continue", id="b7")])
    assert out == {"kind": "form_step", "next": "b7"}


def test_form_step_with_a_next_the_model_would_not_see_unclear_buttons_ignored(tmp_path):
    out = kind(tmp_path, fillable=1, buttons=[btn("Next", id="n"), btn("Save draft"), btn("Cancel")])
    assert out == {"kind": "form_step", "next": "n"}


def test_review_is_a_submit_button_and_no_next_one(tmp_path):
    assert kind(tmp_path, fillable=2, buttons=[btn("Submit application")])["kind"] == "review"
    assert kind(tmp_path, fillable=0, buttons=[btn("Submit application")])["kind"] == "review"


def test_review_is_also_an_unclear_advance_button_only(tmp_path):
    assert kind(tmp_path, fillable=2, buttons=[btn("Done")])["kind"] == "review"
    assert kind(tmp_path, fillable=2, buttons=[])["kind"] == "review"


def test_a_submit_beside_a_next_is_review_never_form_step(tmp_path):
    out = kind(tmp_path, fillable=2, buttons=[btn("Next"), btn("Submit")])
    assert out == {"kind": "review", "by": "several_next"}


def test_several_nexts_are_not_sure_so_the_page_is_review(tmp_path):
    assert kind(tmp_path, fillable=2, buttons=[btn("Next"), btn("Continue")]) == {"kind": "review", "by": "several_next"}


def test_a_visible_but_disabled_submit_still_stops_the_run(tmp_path):
    """Submit is often disabled until the form validates. A Next beside it must not be trusted."""
    out = kind(tmp_path, fillable=2, buttons=[btn("Next"), btn("Submit", enabled=False)])
    assert out["kind"] == "review"


def test_hidden_buttons_are_ignored_for_both_next_and_submit(tmp_path):
    hidden_submit = btn("Submit", visible=False)
    hidden_next = btn("Next", visible=False)
    assert kind(tmp_path, fillable=2, buttons=[btn("Next", id="n"), hidden_submit])["kind"] == "form_step"
    assert kind(tmp_path, fillable=2, buttons=[hidden_next])["kind"] == "review"


def test_a_disabled_next_is_not_clickable(tmp_path):
    assert kind(tmp_path, fillable=2, buttons=[btn("Next", enabled=False)])["kind"] == "review"


def test_a_next_in_site_chrome_is_never_the_steps_next(tmp_path):
    """Header, nav and site-footer buttons are the site's: a Continue there is not the step's."""
    assert kind(tmp_path, fillable=2, buttons=[btn("Next", in_form=False, chrome=True)]) == {
        "kind": "review", "by": "fields_no_next"}
    assert kind(tmp_path, fillable=2, buttons=[btn("Next", chrome=True)]) == {"kind": "review", "by": "fields_no_next"}
    out = kind(tmp_path, fillable=2, buttons=[btn("Continue", id="site", chrome=True, in_form=False), btn("Next", id="step")])
    assert out == {"kind": "form_step", "next": "step"}


def test_a_next_outside_every_form_and_outside_chrome_is_the_step(tmp_path):
    """Dayforce: four <form>s hold the fields and the footer Next is a plain bar outside them. The one
    visible, enabled Next that is no site chrome is the step's."""
    out = kind(tmp_path, fillable=2, buttons=[btn("Next", id="n", in_form=False), btn("Cancel", in_form=False)])
    assert out == {"kind": "form_step", "next": "n"}


def test_two_nexts_outside_every_form_are_not_sure(tmp_path):
    out = kind(tmp_path, fillable=2, buttons=[btn("Next", in_form=False), btn("Continue", in_form=False)])
    assert out == {"kind": "review", "by": "several_next"}


def test_a_next_outside_the_form_that_is_an_error_summary_button_is_not_the_step(tmp_path):
    bad = btn("Next", in_form=False)
    bad["inErrors"] = True
    assert kind(tmp_path, fillable=2, buttons=[bad]) == {"kind": "review", "by": "fields_no_next"}


def test_a_disabled_next_outside_the_form_is_not_taken(tmp_path):
    assert kind(tmp_path, fillable=2, buttons=[btn("Next", in_form=False, enabled=False)])["kind"] == "review"


def test_review_says_why_it_is_review(tmp_path):
    """`by` is the reason: only a real Submit control and no real Next is the end of the application."""
    assert kind(tmp_path, fillable=2, buttons=[btn("Submit application")]) == {"kind": "review", "by": "submit_button"}
    assert kind(tmp_path, fillable=0, buttons=[btn("Submit application"), btn("Back")])["by"] == "submit_button"
    assert kind(tmp_path, fillable=2, buttons=[btn("Next"), btn("Submit")])["by"] == "several_next"
    assert kind(tmp_path, fillable=2, buttons=[btn("Next", enabled=False), btn("Submit")])["by"] == "several_next"
    assert kind(tmp_path, fillable=2, buttons=[btn("Next"), btn("Continue")])["by"] == "several_next"
    assert kind(tmp_path, fillable=2, buttons=[btn("Done")])["by"] == "fields_no_next"
    assert kind(tmp_path, fillable=2, buttons=[])["by"] == "fields_no_next"
    assert kind(tmp_path, fillable=2, buttons=[btn("Back")], submitSeen=True)["by"] == "submit_seen"
    assert kind(tmp_path, fillable=0, buttons=[btn("Proceed"), btn("Cancel")], submitContext=True)["by"] == "submit_context"
    assert kind(tmp_path, fillable=0, buttons=[btn("Cancel")], submitContext=True)["by"] == "submit_context"


def test_a_next_in_chrome_does_not_turn_a_real_submit_into_a_mixed_page(tmp_path):
    out = kind(tmp_path, fillable=2, buttons=[btn("Submit application"), btn("Continue", chrome=True, in_form=False)])
    assert out == {"kind": "review", "by": "submit_button"}


def test_a_submit_in_site_chrome_alone_is_not_a_real_submit_control(tmp_path):
    """It still stops the run (the one rule), but it is not the application's own Submit."""
    out = kind(tmp_path, fillable=2, buttons=[btn("Apply now", chrome=True, in_form=False)])
    assert out == {"kind": "review", "by": "submit_seen"}


def test_only_review_carries_a_by(tmp_path):
    assert "by" not in kind(tmp_path, fillable=2, buttons=[btn("Next", id="n")])
    assert "by" not in kind(tmp_path)


def test_a_submit_outside_the_form_still_counts_as_a_submit(tmp_path):
    out = kind(tmp_path, fillable=2, buttons=[btn("Next"), btn("Submit", in_form=False)])
    assert out["kind"] == "review"


def test_unknown_is_nothing_at_all(tmp_path):
    assert kind(tmp_path) == {"kind": "unknown"}
    assert kind(tmp_path, buttons=[btn("Cancel")]) == {"kind": "unknown"}


def test_a_lone_next_with_nothing_to_fill_advances(tmp_path):
    """An intro or "before you apply" page has no fields and one Continue: that is the step."""
    assert kind(tmp_path, buttons=[btn("Continue", id="c")]) == {"kind": "form_step", "next": "c"}


def test_several_nexts_with_nothing_to_fill_stop_as_review(tmp_path):
    assert kind(tmp_path, buttons=[btn("Next"), btn("Continue")]) == {"kind": "review", "by": "several_next"}


def test_a_lone_next_with_nothing_to_fill_beside_a_submit_is_review(tmp_path):
    assert kind(tmp_path, buttons=[btn("Next"), btn("Submit", visible=True)])["kind"] == "review"


def test_a_missing_buttons_list_is_tolerated(tmp_path):
    s = summary(fillable=2)
    del s["buttons"]
    assert _run(tmp_path, summaries=[s])["classified"][0] == {"kind": "review", "by": "fields_no_next"}


def test_known_next_marker_makes_an_unclear_label_the_forms_next(tmp_path):
    out = kind(tmp_path, fillable=2, buttons=[btn("Go", id="g", known="next")])
    assert out == {"kind": "form_step", "next": "g"}


def test_known_submit_marker_stops_the_run_whatever_the_wording(tmp_path):
    out = kind(tmp_path, fillable=2, buttons=[btn("Next", known="submit")])
    assert out["kind"] == "review"


def test_known_next_cannot_unmark_a_submit_word(tmp_path):
    out = kind(tmp_path, fillable=2, buttons=[btn("Submit application", known="next")])
    assert out["kind"] == "review"


# ---------- the safety invariant, over a grid ----------

_WORDINGS = ["Next", "Continue", "Review", "Save and Continue", *SUBMIT, "Done", "Go", "Save", "", "→"]


def test_a_submit_worded_live_button_is_never_the_next_to_click(tmp_path):
    """Every pair and triple of buttons from the wordings above, with the first one
    enabled and disabled: if any visible button's text sorts "submit", the verdict is never form_step,
    and the clicked id (when there is one) is never a submit-sorted button."""
    sorted_of = dict(zip(_WORDINGS, sort_all(tmp_path, _WORDINGS), strict=True))
    summaries, meta = [], []
    for combo in [*itertools.combinations(_WORDINGS, 2), *itertools.combinations(_WORDINGS[:12], 3)]:
        for enabled in (True, False):
            buttons = [btn(t, id=f"{i}:{t}", enabled=enabled if i == 0 else True) for i, t in enumerate(combo)]
            summaries.append(summary(fillable=2, buttons=buttons))
            meta.append(combo)
    verdicts = _run(tmp_path, summaries=summaries)["classified"]
    assert len(verdicts) == len(summaries) > 500
    for combo, verdict in zip(meta, verdicts, strict=True):
        if any(sorted_of[t] == "submit" for t in combo):
            assert verdict["kind"] == "review", (combo, verdict)
        if verdict["kind"] == "form_step":
            clicked = verdict["next"].split(":", 1)[1]
            assert sorted_of[clicked] == "next", (combo, verdict)


@pytest.mark.parametrize("text, plain", [
    ("Next", True), ("NEXT", True), ("Next step", True), ("Next →", True), ("Save and continue", True),
    ("Save & next", True), ("Save and Next", True),
    ("Continue", False), ("Proceed", False), ("Review application", False), ("Submit", False), ("", False), (None, False),
])
def test_only_the_plain_next_wordings_count_as_a_plain_next(tmp_path, text, plain):
    assert _run(tmp_path, plain=[text])["plain"] == [plain]


def test_a_next_in_a_dialog_or_cookie_notice_outside_every_form_is_not_taken_as_the_step(tmp_path):
    assert kind(tmp_path, fillable=2, buttons=[btn("Continue", in_form=False, overlay=True)]) == {
        "kind": "review", "by": "fields_no_next"}
    out = kind(tmp_path, fillable=2, buttons=[btn("Continue", id="cookie", in_form=False, overlay=True),
                                              btn("Next", id="step", in_form=False)])
    assert out == {"kind": "form_step", "next": "step"}


def test_a_next_in_a_dialog_that_a_form_holds_is_still_the_step(tmp_path):
    assert kind(tmp_path, fillable=2, buttons=[btn("Next", id="n", overlay=True)]) == {"kind": "form_step", "next": "n"}
