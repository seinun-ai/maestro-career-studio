"""The adversarial set (fill-engine revision Task 12): widgets and page shapes
the field notes did not observe live but that a real form can present, each
asserted on what the fake app HOLDS (`__oracle`) or on what the loop SENT.

Committed fixtures (`adversarial_*.html`, fixtures/browser/README.md):
revert, same text, recipe poisoning (their tests live beside the code they
exercise), a widget that takes trusted input only (here), and the same text
under another category outside a virtualized list's window (here). Scripted
loop cases (test_fill_loop's driver) cover the carry notes about sections and
reverts. The two engine gaps this set found (a same-text option outside a
virtualized window; two sections read as one kind) were fixed on the owner's
decisions of 2026-09-27, and their tests pass as written.
"""

import pytest

from tests.browser.conftest import fixture_html
from tests.browser.pages import list_shown, oracle
from tests.browser.test_fill_core import apply, explore, inv
from tests.browser.test_fill_end_to_end import _run
from tests.browser.test_fill_loop import JOBS, actions, adds, bodies, f, opt, row, run, section, site, statuses, work


@pytest.fixture
def e2e_page(page):
    page.set_default_timeout(60000)
    return page


# ---------- a widget that ignores synthetic input -> unsupported


SHIFT_PREF = "Which shift do you prefer?"


def test_a_widget_that_takes_only_trusted_input_is_unsupported_never_filled(e2e_page):
    """Every gesture the engine has (a dispatched press, keys, el.click()) is
    untrusted, and this widget ignores all of them: the run says so plainly,
    and the app holds nothing."""
    page = e2e_page
    out = _run(page, fixtures=["adversarial_trusted_only.html"],
               map={SHIFT_PREF: {"route": "slot", "slot": "preferences.shift", "value": "Day"}})
    r = out["by_question"][SHIFT_PREF]
    assert r["status"] == "unsupported", r
    assert oracle(page, "shift_pref") == "" and page.inner_text("#shift-pref") == "Select One"
    assert page.evaluate("window.ignoredEvents") > 0
    obs = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.buildLoopObservations(r)", out["report"])
    assert [o["outcome"] for o in obs if o["label"] == SHIFT_PREF] == ["unsupported"]


# ---------- the same text under another category, outside a virtualized window


def test_explore_scrolls_a_virtualized_list_and_lists_both_others(page, load):
    load(page, fixture_html("adversarial_virtual_same_text.html"))
    f_ = inv(page)["Where did you find this job?"]
    got = explore(page, f_)
    texts = [o["text"] for o in got["options"]]
    assert texts.count("Other") == 2 and "Facebook" in texts and "Indeed" in texts
    assert oracle(page, "found") == "" and not list_shown(page)


FOUND = "Where did you find this job?"


def test_the_same_text_outside_a_virtualized_window_is_still_ambiguous(page, load):
    """A choose by text alone reads the whole list before it commits: the
    second "Other" sits under another category outside the window."""
    load(page, fixture_html("adversarial_virtual_same_text.html"))
    row_ = apply(page, inv(page)[FOUND], op="choose", text="Other")
    assert oracle(page, "found") == "", f"committed {oracle(page, 'found')!r}"
    assert (row_["outcome"], row_["reason"]) == ("unexpected", "ambiguous")
    assert not list_shown(page)


def _others(page):
    got = explore(page, inv(page)[FOUND])
    assert all(isinstance(o.get("where"), str) for o in got["options"])
    return [o for o in got["options"] if o["text"] == "Other"]


@pytest.mark.parametrize("category, at", [("Job Board", 0), ("Social Media", 1)])
def test_a_choice_carrying_its_category_commits_the_option_under_it(page, load, category, at):
    """Explore names each option's category path; a choose that carries it
    commits the option under that path, scrolling the list the way explore read it."""
    load(page, fixture_html("adversarial_virtual_same_text.html"))
    others = _others(page)
    assert len({o["where"] for o in others}) == 2 and category in others[at]["where"]
    row_ = apply(page, inv(page)[FOUND], op="choose", text="Other", where=others[at]["where"])
    assert (row_["outcome"], oracle(page, "found")) == ("verified", f"{category} / Other"), row_
    assert not list_shown(page)


def test_a_category_no_option_sits_under_is_never_guessed(page, load):
    load(page, fixture_html("adversarial_virtual_same_text.html"))
    row_ = apply(page, inv(page)[FOUND], op="choose", text="Other", where="\u203aEvents")
    assert (row_["outcome"], row_["reason"]) == ("unexpected", "ambiguous")
    assert oracle(page, "found") == "" and not list_shown(page)


def test_an_option_whose_header_scrolled_out_of_the_window_is_read_once(page, load):
    """A page step shorter than the rendered window (one row of overscan)
    starts the next window below its first rows' header: those rows still
    read under it — one option is never listed, or chosen, as two."""
    load(page, fixture_html("adversarial_virtual_same_text.html"))
    page.add_style_tag(content="#found-list { height: 210px; }")
    got = explore(page, inv(page)[FOUND])
    texts = [o["text"] for o in got["options"]]
    assert len(texts) == len(set(texts)) + 1 and texts.count("Other") == 2
    assert [o["where"] for o in got["options"] if o["text"] == "Randstad"] == [
        next(o["where"] for o in got["options"] if o["text"] == "Robert Half")]
    row_ = apply(page, inv(page)[FOUND], op="choose", text="Randstad")
    assert (row_["outcome"], oracle(page, "found")) == ("verified", "Agency / Randstad"), row_


def test_a_hidden_row_is_never_a_header(page, load):
    """One visibility rule for header rows, in the window and down the list: a
    hidden row between a window's first options and its top is not their header."""
    load(page, fixture_html("adversarial_virtual_same_text.html"))
    page.evaluate("""() => {
      const ul = document.getElementById("found-list");
      const ghost = document.createElement("li");
      ghost.textContent = "Ghost";
      ghost.style.display = "none";
      ul.firstElementChild.after(ghost);
    }""")
    got = explore(page, inv(page)[FOUND])
    assert not [o for o in got["options"] if "Ghost" in o["where"]]
    assert "Agency" in next(o["where"] for o in got["options"] if o["text"] == "Adecco")


def test_a_unique_option_in_a_virtualized_list_is_committed_as_before(page, load):
    load(page, fixture_html("adversarial_virtual_same_text.html"))
    row_ = apply(page, inv(page)[FOUND], op="choose", text="Instagram")
    assert (row_["outcome"], oracle(page, "found")) == ("verified", "Social Media / Instagram"), row_


def test_the_loop_carries_the_picked_options_category_into_its_choose(page, load):
    """/pick sees oids and texts only; the choose names the picked option's path."""
    options = [{**opt("o1", "Other"), "where": "\u203aJob Board"}, {**opt("o2", "Other"), "where": "\u203aSocial Media"}]
    out = run(page, load, frames=[[f("d", "popup", FOUND)]],
              map={"d": {"route": "slot", "slot": "preferences.how_heard", "value": "Facebook"}},
              explore={"d": {"options": options, "complete": True}},
              pick={"d": {"oids": ["o2"], "reason": "closest"}})
    [body] = bodies(out, "/api/autofill/pick")
    assert body["fields"][0]["options"] == [{"oid": "o1", "text": "Other"}, {"oid": "o2", "text": "Other"}]
    [choose] = actions(out, "choose")
    assert (choose["text"], choose["where"]) == ("Other", "\u203aSocial Media")


ARRANGEMENT = "Preferred work arrangement"


def test_a_search_explored_without_a_term_commits_its_unique_option(e2e_page):
    """A search box explored without a term reads its default list, whose
    header rows give each option a path; the choose then types the option
    and sees flat results with no header. That is not the view explore read,
    so the choose carries no path: the unique option commits."""
    page = e2e_page
    out = _run(page, fixtures=["adversarial_search_headers.html"], map={ARRANGEMENT: {"route": "low_stakes"}},
               picks={ARRANGEMENT: {"text": "Remote", "reason": "assumed"}})
    assert oracle(page, "arrangement") == "Remote", out["by_question"][ARRANGEMENT]
    assert out["by_question"][ARRANGEMENT]["status"] == "assumed"
    [choose] = [a for m in out["sent"] if m["type"] == "fill_apply" for a in m["actions"] if a["op"] == "choose"]
    assert (choose["text"], choose["term"], "where" in choose) == ("Remote", "Remote", False)


def test_rows_an_explore_found_by_a_word_carry_no_path(page, load):
    """A term with no results is searched again by one of its words: those
    rows are not the view a choose typing the term opens, so they name no path."""
    load(page, fixture_html("adversarial_search_headers.html"))
    got = explore(page, inv(page)[ARRANGEMENT], term="Remote nowhere")
    assert [o["text"] for o in got["options"]] == ["Remote", "Remote with travel"]
    assert not [o for o in got["options"] if "where" in o]
    default = explore(page, inv(page)[ARRANGEMENT])
    assert all("where" in o for o in default["options"])


@pytest.mark.parametrize("value, carried", [(None, False), ("Remote", True)])
def test_a_search_choose_carries_a_path_only_from_the_view_it_opens(page, load, value, carried):
    """Explored with the term the choose types (a fact's value), the view is
    the same and the path travels; explored without one, it does not."""
    options = [{**opt("o1", "Remote"), "where": "\u203aAway from office"}]
    route = {"route": "slot", "slot": "preferences.arrangement", "value": value} if value else {"route": "low_stakes"}
    out = run(page, load, frames=[[f("a", "search", ARRANGEMENT)]], map={"a": route},
              explore={("Remote" if value else "a"): {"options": options, "complete": False, "multi": False}},
              pick={"a": {"oids": ["o1"], "reason": "matched" if value else "assumed"}})
    [choose] = actions(out, "choose")
    assert ("where" in choose) is carried and choose["term"] == "Remote"


def test_a_set_carries_each_items_path_when_explore_read_one(page, load):
    """Each item's option was explored with the term the set types for it:
    its path travels, so the set does not read a long list whole per item.
    An item explore gave no path for is carried as null (read whole)."""
    out = run(page, load, frames=[[f("k", "search", "Skills", multi=None)]],
              map={"k": {"route": "slot", "slot": "skills", "value": ["SQL", "Python"]}},
              explore={"SQL": {"options": [{**opt("o1", "SQL"), "where": "\u203aData"}], "multi": True},
                       "Python": {"options": [opt("o1", "Python")], "multi": True}},
              pick={"k:SQL": {"oids": ["o1"], "reason": "matched"}, "k:Python": {"oids": ["o1"], "reason": "matched"}},
              apply={"SQL+Python": {"outcome": "verified", "added": ["SQL", "Python"], "missing": []}})
    [s] = actions(out, "set")
    assert (s["texts"], s["terms"], s["wheres"]) == (["SQL", "Python"], ["SQL", "Python"], ["\u203aData", None])


def test_a_set_item_commits_by_its_path_on_a_long_list(page, load):
    """The skills box of workday_search.html (a virtualized result list): an
    item carrying the path explore read commits."""
    load(page, fixture_html("workday_search.html"))
    skills = inv(page)["Type to Add Skills"]
    got = explore(page, skills, term="Python")
    where = next(o["where"] for o in got["options"] if o["text"] == "Python")
    row_ = apply(page, inv(page)["Type to Add Skills"], op="set", texts=["Python"], terms=["Python"], wheres=[where])
    assert row_["outcome"] == "verified" and oracle(page, "skills") == ["SQL", "Python"]


# ---------- a revert, then a re-commit that ends in another status


YES_NO = [opt("o1", "Yes"), opt("o2", "No")]
RELOCATE = {"d": {"route": "slot", "slot": "preferences.willing_to_relocate", "value": "Yes"}}
TOOK_BACK = 'Companion filled "Yes", then the page took it back. Check it.'


def test_a_revert_stays_reported_when_the_recommit_abstains(page, load):
    """The pick verified, the final sweep found it taken back, and the one
    re-commit's pick abstained: the field is not reported as a plain "needs
    your answer" — it stays unconfirmed, saying the page took the value back."""
    out = run(page, load, frames=[[f("d", "popup", "Willing to relocate?")]] * 4, map=RELOCATE,
              explore={"d": {"options": YES_NO, "complete": True}},
              pick={"d": [{"oids": ["o1"], "reason": "matched"}, {"oids": [], "reason": "abstained"}]},
              sweep=[[{"fid": "d", "outcome": "reverted"}], []])
    r = row(out, "d")
    assert (r["status"], r["answer"]) == ("unconfirmed", TOOK_BACK), r


def test_a_revert_stays_reported_when_the_recommit_cannot_find_its_option(page, load):
    out = run(page, load, frames=[[f("d", "popup", "Willing to relocate?")]] * 4, map=RELOCATE,
              explore={"d": {"options": YES_NO, "complete": True}},
              pick={"d": {"oids": ["o1"], "reason": "matched"}},
              apply={"Yes": [{"outcome": "verified"}, {"outcome": "unexpected", "reason": "option_missing"}]},
              sweep=[[{"fid": "d", "outcome": "reverted"}], []])
    r = row(out, "d")
    assert (r["status"], r["answer"]) == ("unconfirmed", TOOK_BACK), r


# ---------- "Volunteer Experience" above "Work Experience": which section wins one-section-per-kind


VOLUNTEER = [f("v1", question="Organization", section="Volunteer Experience 1")]


def test_volunteer_experience_read_as_none_leaves_work_experience_placed(page, load):
    out = run(page, load, frames=[VOLUNTEER + work(1)],
              sections=[[section("f-s4", "Volunteer Experience", 1), section("f-s1", entries=1)]],
              kinds={"f-s4": {"kind": "none", "wanted": 0}, "f-s1": {"kind": "experience", "wanted": 1, "order": [0]}},
              map=JOBS)
    [body] = bodies(out, "/api/autofill/map")
    placed = {x["fid"]: x.get("profile_entry", "absent") for x in body["fields"]}
    assert placed == {"v1": "absent", "t1": 0, "c1": 0}
    assert statuses(out) == {"v1": "needs_answer", "t1": "verified", "c1": "verified"}
    assert adds(out) == []


def test_two_sections_read_as_work_experience_never_double_a_job(page, load):
    """Volunteer Experience above Work Experience, both misread as work
    experience: job #1 is never written twice and nothing is added (the
    test below: neither section is placed)."""
    out = run(page, load, frames=[VOLUNTEER + work(1)],
              sections=[[section("f-s4", "Volunteer Experience", 1), section("f-s1", entries=1)]],
              kinds={"f-s4": {"kind": "experience", "wanted": 1, "order": [0]},
                     "f-s1": {"kind": "experience", "wanted": 1, "order": [0]}},
              map=JOBS | {"v1": {"route": "slot", "slot": "experience.0.employer", "value": "Acme"}})
    [body] = bodies(out, "/api/autofill/map")
    placed = [x.get("profile_entry", "absent") for x in body["fields"] if x["fid"] in ("v1", "c1")]
    assert placed.count(0) <= 1   # one section's entry holds job #1, never both
    written = [a["value"] for a in actions(out, "write")]
    assert written.count("Acme") <= 1 and adds(out) == []


AMBIGUOUS_LINE = '{}: this section looks like the same kind of list as "{}", so it was left for you.'


def test_a_misread_volunteer_section_above_work_experience_is_not_given_a_job(page, load):
    """Which of two sections read as one kind is misread cannot be told:
    neither is placed, neither grows, and the report says so for each."""
    out = run(page, load, frames=[VOLUNTEER + work(1)],
              sections=[[section("f-s4", "Volunteer Experience", 1), section("f-s1", entries=1)]],
              kinds={"f-s4": {"kind": "experience", "wanted": 1, "order": [0]},
                     "f-s1": {"kind": "experience", "wanted": 1, "order": [0]}},
              map=JOBS | {"v1": {"route": "slot", "slot": "experience.0.employer", "value": "Acme"}})
    assert "v1" not in {a["fid"] for a in actions(out)}
    assert actions(out) == [] and adds(out) == []
    [body] = bodies(out, "/api/autofill/map")
    assert {x["fid"]: x.get("profile_entry", "absent") for x in body["fields"]} == {"v1": None, "t1": None, "c1": None}
    assert statuses(out) == {"v1": "needs_answer", "t1": "needs_answer", "c1": "needs_answer"}
    assert [(s["heading"], s["reason"], s["added"]) for s in out["report"]["sections"]] == [
        ("Volunteer Experience", "ambiguous_kind", 0), ("Work Experience", "ambiguous_kind", 0)]
    lines = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.sectionLines(r)", out["report"])
    assert lines == [AMBIGUOUS_LINE.format("Volunteer Experience", "Work Experience"),
                     AMBIGUOUS_LINE.format("Work Experience", "Volunteer Experience")]


def test_the_backends_ambiguous_kind_leaves_both_sections_and_others_are_placed(page, load):
    """/sections says so itself (every entry null, nothing to add): the loop
    adds nothing there and places an Education section as ever."""
    school = [f("s1", question="School", section="Education 1")]
    both = {"kind": "experience", "wanted": 1, "reason": "ambiguous_kind", "order": [None]}
    out = run(page, load, frames=[VOLUNTEER + work(1) + school],
              sections=[[section("f-s4", "Volunteer Experience", 1), section("f-s1", entries=1),
                         section("f-s5", "Education", 1)]],
              kinds={"f-s4": both, "f-s1": both, "f-s5": {"kind": "education", "wanted": 2, "order": [0]}},
              map=JOBS | {"s1": {"route": "slot", "slot": "education.0.school", "value": "State University"}})
    [body] = bodies(out, "/api/autofill/map")
    placed = {x["fid"]: (x.get("profile_entry", "absent"), x.get("entry_kind")) for x in body["fields"]}
    assert placed == {"v1": (None, None), "t1": (None, None), "c1": (None, None), "s1": (0, "education")}
    assert adds(out) and {a["sid"] for a in adds(out)} == {"f-s5"}
    assert {s["heading"]: s["reason"] for s in out["report"]["sections"]} == {
        "Volunteer Experience": "ambiguous_kind", "Work Experience": "ambiguous_kind", "Education": None}


def test_a_second_section_of_a_kind_placed_in_an_earlier_round_is_left_alone(page, load):
    """Work Experience was placed and filled before "Volunteer Experience"
    (read as the same kind) appeared: what was done stands, and the late
    section is never given a job or an Add."""
    out = run(page, load, frames=[work(1), work(1) + VOLUNTEER],
              sections=[[section("f-s1", entries=1)],
                        [section("f-s1", entries=1), section("f-s4", "Volunteer Experience", 1)]],
              kinds={"f-s1": {"kind": "experience", "wanted": 1, "order": [0]},
                     "f-s4": {"kind": "experience", "wanted": 2, "order": [0]}},
              map=JOBS | {"v1": {"route": "slot", "slot": "experience.0.employer", "value": "Acme"}})
    assert "v1" not in {a["fid"] for a in actions(out)} and adds(out) == []
    assert {s["heading"]: s["reason"] for s in out["report"]["sections"]}["Volunteer Experience"] == "ambiguous_kind"
    # Work Experience's writes, made in the first round, stand.
    assert [(a["fid"], a["value"]) for a in actions(out, "write")] == [("t1", "Analyst"), ("c1", "Acme")]
    assert (statuses(out)["t1"], statuses(out)["c1"]) == ("verified", "verified")
    lines = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.sectionLines(r)", out["report"])
    assert lines == [AMBIGUOUS_LINE.format("Volunteer Experience", "Work Experience")]


# ---------- two Websites entries


def test_two_website_entries_are_added_and_each_gets_its_own_fact(e2e_page):
    """workday_sections.html through the real handlers: the profile has a
    website and a GitHub; Websites shows no entry. Two presses of its own Add,
    one fact in each entry."""
    page = e2e_page
    text = lambda slot, value: {"route": "slot", "slot": slot, "value": value}  # noqa: E731
    out = _run(page, fixtures=["workday_sections.html"],
               kinds={"Websites": {"kind": "websites", "wanted": 2}},
               map={"Websites 1/URL": text("personal.website", "https://ada.dev"),
                    "Websites 2/URL": text("personal.github", "https://github.com/ada")})
    assert oracle(page, "entries")["Websites"] == 2 and oracle(page, "deleted") == 0
    assert (oracle(page, "Websites 1/URL"), oracle(page, "Websites 2/URL")) == ("https://ada.dev", "https://github.com/ada")
    assert [(m["heading"], m["entries"]) for m in out["sent"] if m["type"] == "fill_add"] == [
        ("Websites", 0), ("Websites", 1)]
    for n in (1, 2):
        assert out["report"]["fields"] and any(
            r["section"] == f"Websites {n}" and r["question"] == "URL" and r["status"] == "verified"
            for r in out["report"]["fields"]), n


def test_one_website_fact_mapped_to_both_entries_is_written_once(e2e_page):
    page = e2e_page
    same = {"route": "slot", "slot": "personal.website", "value": "https://ada.dev"}
    out = _run(page, fixtures=["workday_sections.html"],
               kinds={"Websites": {"kind": "websites", "wanted": 2}},
               map={"Websites 1/URL": same, "Websites 2/URL": same})
    assert oracle(page, "Websites 1/URL") == "https://ada.dev"
    assert page.evaluate("'Websites 2/URL' in window.__oracle") is False   # never committed
    second = next(r for r in out["report"]["fields"] if r["section"] == "Websites 2" and r["question"] == "URL")
    assert (second["status"], second["lastOutcome"]) == ("needs_answer", "in_another_entry")


def test_two_websites_entries_scripted_take_one_fact_each(page, load):
    out = run(page, load, frames=[[site(1), site(2)]], sections=[[section("f-s2", "Websites", 2)]],
              kinds={"f-s2": {"kind": "websites", "wanted": 2}},
              map={"u1": {"route": "slot", "slot": "personal.website", "value": "https://ada.dev"},
                   "u2": {"route": "slot", "slot": "personal.github", "value": "https://github.com/ada"}})
    assert adds(out) == [] and statuses(out) == {"u1": "verified", "u2": "verified"}


# ---------- entries pre-filled out of profile order; [empty, job #1] with nothing to add


def loc(n):
    return f(f"l{n}", question="Location", section=f"Work Experience {n}", repeatIndex=n - 1)


def test_entries_prefilled_out_of_order_are_filled_from_the_job_each_holds(page, load):
    """Entry 1 holds job #2, entry 2 holds job #1 (/sections placed them
    [1, 0]): the held values stay, nothing is added, and each entry's empty
    field is asked for with its OWN job's number."""
    frames = [work(1, committed="Initech", answered=True) + [loc(1)] + work(2, committed="Acme", answered=True) + [loc(2)]]
    out = run(page, load, frames=frames,
              sections=[[section(entries=2, filled=[True, True], held=[["Intern", "Initech"], ["Analyst", "Acme"]])]],
              kinds={"f-s1": {"kind": "experience", "wanted": 2, "order": [1, 0]}},
              map={"l1": {"route": "slot", "slot": "experience.1.location", "value": "Austin"},
                   "l2": {"route": "slot", "slot": "experience.0.location", "value": "Boston"}})
    [body] = bodies(out, "/api/autofill/map")
    assert {x["fid"]: x.get("profile_entry", "absent") for x in body["fields"]} == {"l1": 1, "l2": 0}
    assert adds(out) == []
    assert {a["fid"]: a["value"] for a in actions(out, "write")} == {"l1": "Austin", "l2": "Boston"}
    assert statuses(out) == {"t1": "already", "c1": "already", "l1": "verified",
                             "t2": "already", "c2": "already", "l2": "verified"}


def test_an_empty_entry_above_job_one_with_nothing_to_add_is_given_job_two(page, load):
    """[empty, job #1], and the page already has as many entries as the
    profile can fill (wanted == entries): no Add, and the empty entry is
    asked for job #2 — never job #1 again."""
    frames = [work(1) + work(2, committed="Acme", answered=True)]
    out = run(page, load, frames=frames,
              sections=[[section(entries=2, filled=[False, True], held=[[], ["Analyst", "Acme"]])]],
              kinds={"f-s1": {"kind": "experience", "wanted": 2, "order": [1, 0]}},
              map={"t1": {"route": "slot", "slot": "experience.1.title", "value": "Intern"},
                   "c1": {"route": "slot", "slot": "experience.1.employer", "value": "Initech"}})
    assert adds(out) == [] and "fill_add" not in out["calls"]
    [body] = bodies(out, "/api/autofill/map")
    assert {x["fid"]: x.get("profile_entry", "absent") for x in body["fields"]} == {"t1": 1, "c1": 1}
    assert {a["fid"]: a["value"] for a in actions(out, "write")} == {"t1": "Intern", "c1": "Initech"}
    assert statuses(out) == {"t1": "verified", "c1": "verified", "t2": "already", "c2": "already"}
