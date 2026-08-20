"""Guided Apply R1 — collection walk, routing, and the /choose batch.

Lane G (collect / ask / orchestrate). The writer (`guidedWrite`, `valueHolds`)
is Lane S: these tests stub it. Collection must see every shape the writer
handles, including Workday's listbox-button dropdowns, without opening closed
popovers and without offering POLICY_BLOCKED fields to the model.
"""

from tests.extension_harness import (
    FORM_MODULE_SOURCES,
    collected_labels,
    rejection_reasons,
    run_node,
    run_open_questions,
)


_HEAR = "How did you hear about us?"
_SHIFT = "What is your preferred shift?"
_INTEREST = "Why are you interested in this role?"
_CONSENT = "I consent to a background check"


def _qids(rows):
    """The stamped ids, in order — the write path's only address."""
    return [row["qid"] for row in rows]


def _labels(rows):
    return [row["label"] for row in rows]


def _kinds(rows):
    return [row["kind"] for row in rows]


def _workday_page():
    """Listbox button + native select + QUESTIONY text — the three shapes the
    widened walk has to return with the right kinds."""
    return [
        {
            "label": _HEAR,
            "kind": "listboxButton",
            "listbox": ["Job Board", "LinkedIn", "Employee Referral"],
        },
        {
            "label": _SHIFT,
            "kind": "select",
            "options": [
                {"value": "day", "textContent": "Day"},
                {"value": "night", "textContent": "Night"},
            ],
        },
        {"label": _INTEREST, "kind": "text"},
    ]


def _by_label(result):
    return {q["label"]: q for q in result["collected"]["questions"]}


def test_a_workday_page_collects_listbox_select_and_text(tmp_path):
    """The fill engine already walks buttons; collection did not. A Workday
    dropdown is `<button aria-haspopup="listbox" type="button">`, mapped to
    kind `combobox` so /choose and guidedWrite share one vocabulary."""
    result = run_open_questions(tmp_path, fields=_workday_page())
    by = _by_label(result)

    assert set(by) == {_HEAR.lower(), _SHIFT.lower(), _INTEREST.lower()}
    assert by[_HEAR.lower()]["kind"] == "combobox"
    assert by[_SHIFT.lower()]["kind"] == "select"
    assert by[_INTEREST.lower()]["kind"] == "text"
    assert result["qids"][_HEAR]
    assert result["qids"][_SHIFT]
    assert result["qids"][_INTEREST]


def test_a_closed_listbox_button_reports_no_options(tmp_path):
    """Collection must not open a popover. Options on a closed Workday
    dropdown are not in the DOM; the writer resolves them at write time."""
    result = run_open_questions(tmp_path, fields=_workday_page())
    hear = _by_label(result)[_HEAR.lower()]
    shift = _by_label(result)[_SHIFT.lower()]

    assert not hear.get("options")
    assert shift["options"] == ["Day", "Night"]


def test_a_policy_blocked_field_is_absent_from_the_collection(tmp_path):
    """POLICY_BLOCKED still runs first. A consent select on the same page as
    collectable fields is never tagged, counted, or offered to /choose."""
    fields = _workday_page() + [{
        "label": _CONSENT,
        "kind": "select",
        "options": [
            {"value": "yes", "textContent": "Yes"},
            {"value": "no", "textContent": "No"},
        ],
    }]
    result = run_open_questions(tmp_path, fields=fields)

    assert _CONSENT.lower() not in collected_labels(result)
    assert result["qids"][_CONSENT] == []
    assert rejection_reasons(result)[_CONSENT.lower()] == "policy_blocked"
    assert {_HEAR.lower(), _SHIFT.lower(), _INTEREST.lower()} <= set(
        collected_labels(result)
    )


def test_a_mixed_page_routes_essays_to_qa_and_short_fields_to_choose(tmp_path):
    """Essay-length QUESTIONY textareas keep /api/qa. Everything else — short
    text, select, combobox — becomes a ChooseField. qids stay unique and the
    same tokens collection stamped, so the two paths cannot swap answers."""
    essay = "Why do you want to work here?"
    fields = _workday_page() + [{"label": essay, "kind": "textarea"}]
    result = run_open_questions(tmp_path, fields=fields)
    routed = result["routed"]

    essay_qids = _qids(routed["essays"])
    choose_qids = _qids(routed["chooseFields"])
    collected_qids = _qids(result["collected"]["questions"])

    assert _labels(routed["essays"]) == [essay.lower()]
    assert set(_labels(routed["chooseFields"])) == {
        _HEAR.lower(), _SHIFT.lower(), _INTEREST.lower(),
    }
    assert set(essay_qids) | set(choose_qids) == set(collected_qids)
    assert not (set(essay_qids) & set(choose_qids))
    assert len(collected_qids) == len(set(collected_qids))
    assert "textarea" not in _kinds(routed["chooseFields"])


def test_a_mechanical_miss_carries_known_value_onto_the_choose_field(tmp_path):
    """When the rule pass had a profile candidate that failed to snap, the
    choose ask is 'which of these IS this value', not a blank question."""
    result = run_open_questions(
        tmp_path,
        fields=_workday_page(),
        known_values={_HEAR.lower(): "LinkedIn"},
    )
    hear = next(q for q in result["routed"]["chooseFields"]
                if q["label"] == _HEAR.lower())
    assert hear["known_value"] == "LinkedIn"
    assert all("known_value" not in q or q["known_value"] is None
               for q in result["routed"]["chooseFields"]
               if q["label"] != _HEAR.lower())


def test_header_chrome_listbox_buttons_are_not_collected(tmp_path):
    """Same discriminator as the fill walk: Settings/account menus carry
    aria-haspopup too, but type=submit and a data-automation-id."""
    result = run_open_questions(
        tmp_path,
        fields=[{
            "label": "Settings",
            "kind": "listboxButton",
            "type": "submit",
            "automationId": "utilityMenuButton",
            "listbox": ["Sign Out"],
        }],
    )
    assert collected_labels(result) == []
    assert result["qids"]["Settings"] == []


_FORM_SOURCE = "\n".join(path.read_text(encoding="utf-8") for path in FORM_MODULE_SOURCES)

_CHOOSE_DRIVER_JS = r"""
const ns = loadModules();
const calls = [];
const priorFills = spec.priorFills ?? [];
const postChoose = async (body) => {
  calls.push(body);
  if (spec.failStatus) {
    throw new Error(String(spec.failStatus));
  }
  const choices = {};
  for (const field of body.fields) {
    choices[field.qid] = spec.abstainAll
      ? { answer: null, reason: "abstained" }
      : { answer: "Yes", reason: "matched" };
  }
  return { choices };
};
main(async () => {
  const out = await ns.requestChoose(spec.fields, {
    postChoose,
    applicationId: spec.applicationId ?? null,
  });
  emit({ choices: out.choices, residue: out.residue, calls, priorFills });
});
"""


def _run_choose(tmp_path, **spec):
    return run_node(_CHOOSE_DRIVER_JS, spec, tmp_path, source=_FORM_SOURCE)


def _choose_fields(n):
    return [
        {"qid": f"q{i}", "label": f"Question {i}?", "kind": "text", "options": []}
        for i in range(n)
    ]


def test_forty_one_fields_make_two_choose_calls_and_merge_choices(tmp_path):
    """The 40-field cap is a request size, not a page size. Rule-sparse forms
    send the whole remainder through /choose, so 41 fields is two calls whose
    choices merge by qid."""
    result = _run_choose(tmp_path, fields=_choose_fields(41))
    assert len(result["calls"]) == 2
    assert len(result["calls"][0]["fields"]) == 40
    assert len(result["calls"][1]["fields"]) == 1
    assert set(result["choices"]) == {f"q{i}" for i in range(41)}
    assert all(c["reason"] == "matched" for c in result["choices"].values())
    assert "application_id" not in result["calls"][0]


def test_a_choose_500_leaves_prior_fills_and_residues_every_unanswered_field(tmp_path):
    """Network/5xx degrades to the residue list. Rule-pass fills are a
    different list and must not be rolled back — requestChoose never sees them."""
    prior = [{"qid": "filled-by-rules", "label": "First name", "value": "Jordan"}]
    fields = _choose_fields(3)
    result = _run_choose(
        tmp_path, fields=fields, failStatus=500, priorFills=prior)
    assert result["priorFills"] == prior
    assert {r["qid"] for r in result["residue"]} == {"q0", "q1", "q2"}
    assert result["choices"] == {}


def test_an_abstain_becomes_residue_not_a_guess(tmp_path):
    """Abstains are final. The field is listed for the user, never re-asked
    and never filled with a substitute."""
    result = _run_choose(tmp_path, fields=_choose_fields(2), abstainAll=True)
    assert {r["qid"] for r in result["residue"]} == {"q0", "q1"}
    assert all(c["reason"] == "abstained" for c in result["choices"].values())
    assert all(c["answer"] is None for c in result["choices"].values())


def test_a_failed_rule_write_becomes_a_retryable_with_the_known_value(tmp_path):
    """The known_value feeder, end to end in production order: the rule pass
    tries First Name, the controlled input reverts it, and collection turns
    that EXCLUDE'd control into a RETRYABLE carrying the attempted value —
    routed to guidedWrite directly, never offered to /choose."""
    result = run_open_questions(
        tmp_path,
        fields=[
            {"label": "First Name", "kind": "text", "reverts": True},
            {"label": "Why do you want this role?", "kind": "textarea"},
        ],
        profile={"personal": {"first_name": "Sample"}},
    )
    retryables = result["collected"]["retryables"]
    assert _labels(retryables) == ["first name"]
    assert retryables[0]["known_value"] == "Sample"
    assert retryables[0]["kind"] == "text"
    assert retryables[0]["qid"]
    # Not a question (never sent to the model) and not double-listed as an
    # excluded rejection — it was rerouted, not refused.
    assert "first name" not in _labels(result["collected"]["questions"])
    assert "first name" not in _labels(result["collected"]["excluded"])
    assert all("first name" not in label
               for label in _labels(result["routed"]["chooseFields"]))


def test_a_successful_rule_write_is_not_retryable(tmp_path):
    """A First Name the rules landed stays plain EXCLUDE'd territory: filled,
    no retryable, no question."""
    result = run_open_questions(
        tmp_path,
        fields=[{"label": "First Name", "kind": "text"}],
        profile={"personal": {"first_name": "Sample"}},
    )
    assert result["collected"]["retryables"] == []
    assert result["collected"]["questions"] == []


def test_without_a_prior_rule_pass_nothing_is_retryable(tmp_path):
    """No profile run means no attempts map — an excluded empty field is a
    plain rejection, exactly as before the feeder existed."""
    result = run_open_questions(
        tmp_path, fields=[{"label": "First Name", "kind": "text"}])
    assert result["collected"]["retryables"] == []
    assert "first name" in [
        row["label"] for row in result["collected"]["excluded"]]


def test_both_strict_listbox_button_discriminators_stay_identical():
    """The Workday listbox-button discriminator exists twice on purpose: the
    fill engine's copy (autofill.js) and collection's copy (open-questions.js)
    were written in different lanes with a file-ownership boundary between
    them. Nothing but this test stops a detection fix from landing in one walk
    and not the other — which is exactly the fill/collection asymmetry this
    round existed to close. (guidedWrite's own `guidedIsListboxButton` is
    deliberately LOOSER — it rechecks elements collection already vetted — and
    is not part of this pin.)"""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    copies = []
    for name in ("autofill.js", "open-questions.js"):
        src = (root / "extension" / "content" / name).read_text(encoding="utf-8")
        found = re.findall(
            r"const isListboxButton = \(el\) =>.*?;", src, re.S)
        assert len(found) == 1, f"{name}: expected one strict copy, found {len(found)}"
        copies.append(re.sub(r"\s+", " ", found[0]).strip())
    assert copies[0] == copies[1], \
        "the two strict listbox-button discriminators have diverged — fix both or neither"
