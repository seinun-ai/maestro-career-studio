"""Remembering which moves worked (fill-engine revision Task 11).

A RECIPE is a learned ORDER of the engine's own variants for one widget
family — `open: press|keys`, `search: enter|debounce` — never a selector, a
label, a value or a URL. Four layers, each tested here:

- the SIGNATURE (content/recipes.js): a hash of the widget's structure, the
  same for the same kind of control whatever it asks or holds;
- the ENGINE (fill-core via fill-ops): an explore, choose or set takes a
  `variant` order and reports the variant that worked; the generic order is
  unchanged, and no order bypasses the Enter gate or the `reacted` lockout;
- the BOOK (shared/recipe-book.js): value-free, bounded, expiring, with the
  lifecycle probation → trusted, demoted on a contradiction, quarantined on a
  structural mismatch;
- the whole loop, twice over one book: a warm run tries the learned move
  first, and a verify the final sweep found reverted is never learned.
"""

import json
import re
import time

import pytest

from tests.browser.conftest import ENGINE_SOURCES, EXTENSION, fixture_html
from tests.browser.pages import oracle
from tests.browser.test_fill_core import ENTER_PICKS, apply, explore, inv
from tests.browser.test_fill_end_to_end import _finish, _start

BOOK = "window.careerStudioCompanion.recipeBook"
DAY = 20000   # a fixed "today", in days since the epoch

# A popup that ignores a press and opens from the keyboard (ArrowDown), with a
# backing input beside it; `presses` counts the pointer presses it was sent.
# No vendor is modelled (so it is a test page, not a fixture): it is the widget
# class the engine's keyboard fallback exists for.
KEYBOARD_ONLY = """<label id='l'>Willing to travel?</label>
<div><button id='kb' aria-haspopup='listbox' aria-labelledby='l' aria-controls='kb-list'>Select One</button><input type='hidden' value=''></div>
<ul id='kb-list' role='listbox' hidden><li role='option'>Yes</li><li role='option'>No</li></ul>
<script>
(() => {
  const oracle = (window.__oracle = window.__oracle || {});
  oracle.travel = "";
  window.presses = 0;
  const btn = document.getElementById('kb');
  const ul = document.getElementById('kb-list');
  btn.addEventListener('pointerdown', () => { window.presses += 1; });
  btn.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') ul.hidden = false;
    if (e.key === 'Escape') ul.hidden = true;
  });
  for (const li of ul.children) li.addEventListener('click', () => {
    btn.textContent = li.textContent; btn.nextElementSibling.value = li.textContent;
    oracle.travel = li.textContent; ul.hidden = true;
  });
  document.addEventListener('click', (e) => { if (!btn.contains(e.target) && !ul.contains(e.target)) ul.hidden = true; });
})();
</script>"""

# A combobox that filters on its own, SLOWLY (a 800 ms debounce): typing shows
# nothing for longer than the engine's 300 ms, so the generic order sends its
# Enter. The Enter does nothing here but be counted.
SLOW_FILTER = """<label for='city'>Location</label>
<div class='w'><input id='city' role='combobox' aria-autocomplete='list' aria-controls='city-list' aria-expanded='false'>
<span class='single-value'></span></div>
<ul id='city-list' role='listbox' hidden></ul>
<script>
(() => {
  const oracle = (window.__oracle = window.__oracle || {});
  oracle.city = "";
  window.enters = 0;
  const box = document.getElementById('city');
  const ul = document.getElementById('city-list');
  const shown = document.querySelector('.single-value');
  let timer = null;
  box.addEventListener('keydown', (e) => { if (e.key === 'Enter') window.enters += 1; });
  box.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      ul.innerHTML = '';
      for (const town of ['Austin', 'Boston'].filter((t) => t.toLowerCase().startsWith(box.value.toLowerCase()))) {
        const li = document.createElement('li');
        li.setAttribute('role', 'option');
        li.textContent = town;
        li.addEventListener('click', () => { shown.textContent = town; oracle.city = town; box.value = ''; ul.hidden = true; });
        ul.append(li);
      }
      ul.hidden = false;
      box.setAttribute('aria-expanded', 'true');
    }, 800);
  });
  document.addEventListener('click', (e) => { if (e.target !== box && !ul.contains(e.target)) ul.hidden = true; });
})();
</script>"""

# An autocomplete box that names a highlighted option (aria-activedescendant):
# an Enter there would pick it, so the gate never sends one — whatever order.
HIGHLIGHTED = """<label for='team'>Team</label>
<div class='w'><input id='team' role='combobox' aria-autocomplete='list' aria-controls='team-list' aria-activedescendant='t1'>
<span class='single-value'></span></div>
<ul id='team-list' role='listbox'><li id='t1' role='option'>Red</li></ul>
<script>
window.enters = 0;
document.getElementById('team').addEventListener('keydown', (e) => { if (e.key === 'Enter') window.enters += 1; });
</script>"""

# A popup button the keyboard may never be sent to (a submit button in a
# form), which opens on a press like any other.
SUBMIT_POPUP = """<form onsubmit='return false'><label id='l'>Shift</label>
<div><button id='sp' type='submit' aria-haspopup='listbox' aria-labelledby='l' aria-controls='sp-list'>Select One</button></div>
<ul id='sp-list' role='listbox' hidden><li role='option'>Day</li><li role='option'>Night</li></ul></form>
<script>
(() => {
  const btn = document.getElementById('sp');
  const ul = document.getElementById('sp-list');
  btn.addEventListener('click', () => { ul.hidden = !ul.hidden; });
  for (const li of ul.children) li.addEventListener('click', (e) => { e.stopPropagation(); btn.textContent = li.textContent; ul.hidden = true; });
})();
</script>"""


def engine(page, load, html):
    load(page, html, sources=ENGINE_SOURCES)
    return inv(page)


# ---------- the signature: structure, never words


SIGNATURE_PAGE = """
<div data-automation-id="formField-degreeItem"><label id="l1">Degree</label>
  <div><button id="a" aria-haspopup="listbox" aria-labelledby="l1" aria-controls="la"
    data-automation-id="selectWidget-0123456789abcdef0123">Masters</button><input type="hidden" value="x1"></div></div>
<div data-automation-id="formField-degreeItem"><label id="l2">Willing to travel?</label>
  <div><button id="b" aria-haspopup="listbox" aria-labelledby="l2" aria-controls="lb"
    data-automation-id="selectWidget-fedcba9876543210fedc">Select One</button><input type="hidden" value=""></div></div>
<div><label id="l3">Shift</label><div><button id="c" aria-haspopup="menu" aria-labelledby="l3">Select One</button></div></div>
<label for="t">City</label><input id="t" value="Springfield">
<label for="s">Country</label><select id="s"><option>Canada</option><option>Mexico</option></select>
"""


def test_the_same_kind_of_control_has_one_family_whatever_it_asks_or_holds(page, load):
    f = engine(page, load, SIGNATURE_PAGE)
    a, b, c = f["Degree"]["recipe"], f["Willing to travel?"]["recipe"], f["Shift"]["recipe"]
    # Other question, other value, other GUID in its automation id: one family.
    assert a["family"] == b["family"]
    # Another popup kind, no aria-controls, no automation ids: another family.
    assert c["family"] != a["family"]
    assert re.fullmatch(r"f:[0-9a-z]+", a["family"]) and re.fullmatch(r"s:[0-9a-z]+", a["site"])
    assert a["site"] != a["family"].replace("f:", "s:")


def test_only_widgets_with_a_move_to_learn_have_a_recipe(page, load):
    """Text boxes and passive lists (a native select, radios, checkboxes) are
    written in one way: nothing to reorder, so nothing to remember."""
    f = engine(page, load, SIGNATURE_PAGE)
    assert f["City"]["recipe"] is None and f["Country"]["recipe"] is None


def served(page, html, url):
    """`html` at `url` (a real host, so `location.hostname` is not empty),
    with the engine loaded into it."""
    page.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html", body=html))
    page.goto(url)
    for src in ENGINE_SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))


def test_the_site_part_of_a_recipe_follows_the_host(page, load):
    load(page, SIGNATURE_PAGE, sources=ENGINE_SOURCES)
    here = inv(page)["Degree"]["recipe"]
    served(page, SIGNATURE_PAGE, "https://apply.acme-careers.test/job/42")
    there = inv(page)["Degree"]["recipe"]
    assert there["family"] == here["family"] and there["site"] != here["site"]


# ---------- the engine: a learned order, and what it may never change


def test_the_generic_order_reports_the_move_that_opened_the_list(page, load):
    f = engine(page, load, KEYBOARD_ONLY)["Willing to travel?"]
    got = explore(page, f)
    assert [o["text"] for o in got["options"]] == ["Yes", "No"] and got["variant"] == {"open": "keys"}
    row = apply(page, f, op="choose", text="Yes")
    assert (row["outcome"], row["variant"]) == ("verified", {"open": "keys"})
    assert oracle(page, "travel") == "Yes" and page.evaluate("window.presses") == 2


def test_a_keyboard_first_order_opens_the_list_with_no_press(page, load):
    f = engine(page, load, KEYBOARD_ONLY)["Willing to travel?"]
    t0 = time.monotonic()
    cold = apply(page, f, op="choose", text="Yes")
    cold_s = time.monotonic() - t0
    f = engine(page, load, KEYBOARD_ONLY)["Willing to travel?"]   # the next application
    t0 = time.monotonic()
    warm = apply(page, f, op="choose", text="Yes", variant={"open": ["keys", "press"]})
    warm_s = time.monotonic() - t0
    assert (warm["outcome"], warm["variant"]) == ("verified", {"open": "keys"}) and cold["outcome"] == "verified"
    assert oracle(page, "travel") == "Yes" and page.evaluate("window.presses") == 0
    assert warm_s < cold_s - 1.5, (cold_s, warm_s)


def test_a_learned_order_that_is_wrong_falls_back_to_the_other_move(page, load):
    """A keys-first order on a widget that opens on a press: the keys change
    nothing, the press opens it, and the report says the press did."""
    f = engine(page, load, SUBMIT_POPUP.replace("type='submit'", "type='button'"))["Shift"]
    row = apply(page, f, op="choose", text="Night", variant={"open": ["keys", "press"]})
    assert (row["outcome"], row["variant"]) == ("verified", {"open": "press"})


def test_a_learned_keys_first_order_never_keys_a_control_that_reacted(page, load):
    """Explore's press opened a role-less list, which stays up. A keys-first
    order on the next operation must not send a key: an Enter would accept
    that list's highlighted row (the `reacted` lockout outranks any recipe)."""
    f = engine(page, load, ENTER_PICKS)["Team"]
    explore(page, f)
    apply(page, f, op="choose", text="Blue", variant={"open": ["keys", "press"]})
    assert oracle(page, "team") == "" and page.evaluate("window.teamKeys") == []


def test_a_learned_order_the_control_cannot_take_is_a_structural_mismatch(page, load):
    """Keys first, on a control the keyboard is never sent to (a submit
    button): nothing is keyed, the press does the work, and the operation
    says the learned move did not fit this control."""
    f = engine(page, load, SUBMIT_POPUP)["Shift"]
    row = apply(page, f, op="choose", text="Day", variant={"open": ["keys", "press"]})
    assert (row["outcome"], row["variant"], row["mismatch"]) == ("verified", {"open": "press"}, "open")


def test_a_debounce_first_order_waits_for_the_list_instead_of_sending_enter(page, load):
    f = engine(page, load, SLOW_FILTER)["Location"]
    cold = apply(page, f, op="choose", text="Austin")
    assert (cold["outcome"], cold["variant"]) == ("verified", {"search": "enter"})
    assert page.evaluate("window.enters") == 1
    f = engine(page, load, SLOW_FILTER)["Location"]
    warm = apply(page, f, op="choose", text="Austin", variant={"search": ["debounce", "enter"]})
    assert (warm["outcome"], warm["variant"]) == ("verified", {"search": "debounce"})
    assert page.evaluate("window.enters") == 0 and oracle(page, "city") == "Austin"


@pytest.mark.parametrize("order", [["enter", "debounce"], ["debounce", "enter"]])
def test_no_learned_order_sends_an_enter_the_gate_refuses(page, load, order):
    f = engine(page, load, HIGHLIGHTED)["Team"]
    apply(page, f, op="choose", text="Blue", variant={"search": order})
    assert page.evaluate("window.enters") == 0


def test_an_order_naming_no_known_move_is_the_generic_order(page, load):
    f = engine(page, load, KEYBOARD_ONLY)["Willing to travel?"]
    row = apply(page, f, op="choose", text="No", variant={"open": ["click-twice"], "leave": ["self"]})
    assert (row["outcome"], row["variant"]) == ("verified", {"open": "keys"})
    assert page.evaluate("window.presses") == 1


# ---------- the book: value-free, bounded, and slow to trust


def book_page(page, load):
    load(page, "<div></div>", sources=["shared/recipe-book.js"])


def learn(page, book, lessons, day=DAY):
    return page.evaluate(f"([b, l, d]) => {BOOK}.learn(b, l, d)", [book, lessons, day])


def consult(page, book, recipe, day=DAY):
    return page.evaluate(f"([b, r, d]) => {BOOK}.consult(b, r, d)", [book, recipe, day])


A = {"family": "f:fam1", "site": "s:sitea"}
B = {"family": "f:fam1", "site": "s:siteb"}
C = {"family": "f:fam1", "site": "s:sitec"}
KEYS = {"open": "keys"}
KEYS_FIRST = {"open": ["keys", "press"]}


def kept(recipe, used=None, moves=KEYS):
    return {"recipe": recipe, "used": used, "moves": moves, "outcome": "kept"}


def state(book, key):
    return book["entries"][key]["state"]


def test_one_kept_success_is_probation_and_is_tried_on_its_own_site_only(page, load):
    book_page(page, load)
    b = learn(page, None, [kept(A)])
    assert (state(b, "s:sitea"), state(b, "f:fam1")) == ("probation", "probation")
    assert consult(page, b, A) == {"key": "s:sitea", "variant": KEYS_FIRST}
    # Another site starts from the generic order: a family is not trusted on one site's word.
    assert consult(page, b, B) is None


def test_two_runs_kept_on_one_site_make_it_trusted_and_one_run_counts_once(page, load):
    book_page(page, load)
    b = learn(page, None, [kept(A), kept(A)])   # two fields in ONE run: one success
    assert state(b, "s:sitea") == "probation"
    b = learn(page, b, [kept(A, used="s:sitea")], DAY + 1)
    assert state(b, "s:sitea") == "trusted" and state(b, "f:fam1") == "probation"


def test_a_family_is_trusted_only_after_successes_on_two_sites(page, load):
    book_page(page, load)
    b = learn(page, None, [kept(A)])
    b = learn(page, b, [kept(A, used="s:sitea")], DAY + 1)
    assert consult(page, b, C) is None
    b = learn(page, b, [kept(B)], DAY + 2)
    assert state(b, "f:fam1") == "trusted"
    assert consult(page, b, C) == {"key": "f:fam1", "variant": KEYS_FIRST}


def test_a_contradiction_demotes_and_a_demoted_recipe_is_never_tried(page, load):
    book_page(page, load)
    b = learn(page, None, [kept(A)])
    b = learn(page, b, [{"recipe": A, "used": "s:sitea", "moves": KEYS, "outcome": "contradicted"}], DAY + 1)
    assert (state(b, "s:sitea"), state(b, "f:fam1")) == ("demoted", "demoted")
    assert consult(page, b, A) is None and consult(page, b, B) is None
    # A later success does not revive it: demoted stays demoted until it expires.
    b = learn(page, b, [kept(A)], DAY + 2)
    assert state(b, "s:sitea") == "demoted"


def test_a_recipe_whose_move_did_not_win_is_demoted(page, load):
    book_page(page, load)
    b = learn(page, None, [kept(A)])
    b = learn(page, b, [kept(A, used="s:sitea", moves={"open": "press"})], DAY + 1)
    assert state(b, "s:sitea") == "demoted" and consult(page, b, A) is None


def test_a_structural_mismatch_quarantines(page, load):
    book_page(page, load)
    b = learn(page, None, [kept(A)])
    b = learn(page, b, [{"recipe": A, "used": "s:sitea", "moves": {"open": "press"}, "outcome": "mismatch"}], DAY + 1)
    assert state(b, "s:sitea") == "quarantined" and consult(page, b, A) is None


def test_a_generic_win_teaches_nothing(page, load):
    book_page(page, load)
    b = learn(page, None, [kept(A, moves={"open": "press", "search": "enter"}), kept(B, moves={})])
    assert b["entries"] == {}


def test_a_contradiction_on_a_move_never_learned_writes_nothing(page, load):
    book_page(page, load)
    b = learn(page, None, [{"recipe": A, "used": None, "moves": KEYS, "outcome": "contradicted"}])
    assert b["entries"] == {}


def test_the_book_holds_at_most_200_entries_and_drops_the_least_recently_used(page, load):
    book_page(page, load)
    old = [{"family": f"f:old{i}", "site": f"s:old{i}"} for i in range(100)]
    b = learn(page, None, [kept(r) for r in old])
    assert len(b["entries"]) == 200
    # Family 0 is used again (and kept) the next day; ten new families arrive.
    b = learn(page, b, [kept(old[0], used="s:old0"), *[kept({"family": f"f:new{i}", "site": f"s:new{i}"})
                                                       for i in range(10)]], DAY + 1)
    assert len(b["entries"]) == 200
    assert {"s:old0", "f:old0", "s:new9", "f:new9"} <= set(b["entries"])
    assert not {"s:old1", "f:old1", "s:old10", "f:old10"} & set(b["entries"]) and "s:old11" in b["entries"]


def test_entries_unused_for_60_days_expire(page, load):
    book_page(page, load)
    b = learn(page, None, [kept(A)])
    assert consult(page, b, A, DAY + 60) is not None
    assert consult(page, b, A, DAY + 61) is None
    assert learn(page, b, [], DAY + 61)["entries"] == {}


def test_a_book_keeps_only_known_words_and_hashes(page, load):
    """Whatever was stored, only the book's own vocabulary survives a read:
    hashed keys, the four states, the known moves, day numbers."""
    book_page(page, load)
    raw = {"v": 1, "entries": {
        "s:sitea": {"moves": {"open": "keys", "label": "Willing to travel?", "search": "Yes"}, "state": "probation",
                    "wins": 1, "seen": DAY, "value": "Yes", "url": "https://x.test/apply"},
        "https://x.test/apply": {"moves": {"open": "keys"}, "state": "trusted", "wins": 3, "seen": DAY},
        "f:fam1": {"moves": {"open": "keys"}, "state": "trusted", "sites": ["s:sitea", "https://x.test"], "seen": DAY},
        "s:siteb": {"moves": {"open": "keys"}, "state": "adored", "wins": 1, "seen": DAY},
    }}
    got = page.evaluate(f"(b) => {BOOK}.clean(b)", raw)
    assert got == {"v": 1, "entries": {
        "s:sitea": {"moves": {"open": "keys"}, "state": "probation", "wins": 1, "seen": DAY},
        "f:fam1": {"moves": {"open": "keys"}, "state": "trusted", "sites": ["s:sitea"], "seen": DAY},
    }}
    assert page.evaluate(f"() => {BOOK}.clean({{v: 2, entries: {{}}}})") == {"v": 1, "entries": {}}


def test_the_store_reads_the_book_once_per_run_and_writes_what_it_learned(page, load):
    book_page(page, load)
    got = page.evaluate(f"""async (a) => {{
      let stored = null; let reads = 0; const writes = [];
      const store = {BOOK}.store({{
        read: async () => {{ reads += 1; return stored; }},
        write: async (b) => {{ stored = b; writes.push(b); }},
        today: () => {DAY},
      }});
      const before = [await store.get(a), await store.get(a)];
      await store.record([{{recipe: a, used: null, moves: {{open: "keys"}}, outcome: "kept"}}]);
      await store.record([]);   // nothing learned: nothing written
      const next = {BOOK}.store({{ read: async () => stored, write: async () => {{}}, today: () => {DAY} }});
      return {{ before, reads, writes: writes.length, after: await next.get(a) }};
    }}""", A)
    assert got["before"] == [None, None] and got["writes"] == 1
    assert got["reads"] == 2   # once for the run's lookups, once more right before its one write
    assert got["after"] == {"key": "s:sitea", "variant": KEYS_FIRST}


def test_a_store_that_cannot_be_read_is_an_empty_book(page, load):
    book_page(page, load)
    got = page.evaluate(f"""async (a) => {{
      const store = {BOOK}.store({{ read: async () => {{ throw new Error("gone"); }}, write: async () => {{}} }});
      return await store.get(a);
    }}""", A)
    assert got is None


# ---------- the whole loop, twice over one book


URL = "https://apply.acme-careers.test/job/42"
TRAVEL = {"Willing to travel?": {"route": "slot", "slot": "preferences.travel", "value": "Yes"}}
SHIFT = {"Preferred shift": {"route": "slot", "slot": "preferences.shift", "value": "Day"}}


def loop_run(page, html, book, mapping, url=URL):
    """One whole run of the real loop through the real page handlers, on a
    fresh load of `html` at `url`, over `book`; the book it left is `book`."""
    _start(page, fresh=True, html=html, url=url, map=mapping, book=book, today=DAY)
    return _finish(page)


@pytest.fixture
def loop_page(page):
    page.set_default_timeout(60000)
    return page


def test_a_verified_variant_is_learned_and_tried_first_next_time(loop_page):
    page = loop_page
    cold = loop_run(page, KEYBOARD_ONLY, None, TRAVEL)
    assert cold["by_question"]["Willing to travel?"]["status"] == "verified" and oracle(page, "travel") == "Yes"
    cold_presses = page.evaluate("window.presses")
    learned = cold["book"]
    assert {e["state"] for e in learned["entries"].values()} == {"probation"}
    # The next application on the same site: the learned move goes first.
    warm = loop_run(page, KEYBOARD_ONLY, learned, TRAVEL)
    assert warm["by_question"]["Willing to travel?"]["status"] == "verified" and oracle(page, "travel") == "Yes"
    assert cold_presses >= 2 and page.evaluate("window.presses") == 0
    assert warm["ms"] < cold["ms"] - 3000, (cold["ms"], warm["ms"])
    # Two runs kept on one site: that site's recipe is trusted now.
    assert "trusted" in {e["state"] for e in warm["book"]["entries"].values()}


def test_a_lucky_false_verify_is_not_learned(loop_page):
    """The poisoned widget verifies its first commit and takes it back inside
    the quiet period. The final sweep sees it: re-committed, the field ends
    verified, and still nothing is learned from it."""
    page = loop_page
    html = fixture_html("adversarial_recipe_poison.html")
    cold = loop_run(page, html, None, SHIFT)
    assert cold["by_question"]["Preferred shift"]["status"] == "verified" and oracle(page, "shift") == "Day"
    assert page.evaluate("window.shiftCommits") == 2
    assert (cold["book"] or {"entries": {}})["entries"] == {}


def test_a_recipe_used_on_a_widget_that_reverts_is_demoted_not_promoted(loop_page):
    page = loop_page
    html = fixture_html("adversarial_recipe_poison.html")
    served(page, html, URL)
    recipe = page.evaluate("window.careerStudioCompanion.fillInventory.list().fields[0].recipe")
    seeded = {"v": 1, "entries": {recipe["site"]: {"moves": {"open": "keys"}, "state": "probation", "wins": 1,
                                                   "seen": DAY}}}
    out = loop_run(page, html, seeded, SHIFT)
    assert page.evaluate("window.shiftPresses") == 0   # the recipe was tried first
    assert out["book"]["entries"][recipe["site"]]["state"] == "demoted"


def test_recipes_hold_no_values_labels_or_urls(loop_page):
    page = loop_page
    out = loop_run(page, KEYBOARD_ONLY, None, TRAVEL)
    stored = json.dumps(out["book"])
    assert out["book"]["entries"], "nothing was learned: this test would prove nothing"
    for word in ("Willing", "travel", "Yes", "No", "Select One", "acme", "careers", "apply", "job/42", "https",
                 ".test", "kb-list"):
        assert word not in stored, word
    for key, entry in out["book"]["entries"].items():
        assert re.fullmatch(r"[sf]:[0-9a-z]+", key)
        assert set(entry) <= {"moves", "state", "wins", "sites", "seen"}
