"""Pages and helpers shared by the browser tests.

`oracle(page, key)` reads a fixture's `window.__oracle` (fixtures/browser/
README.md): the value the fake app HOLDS. A missing key raises — a typo or a
fixture that no longer sets it must not read as "nothing committed".

`in_both_windows` runs a test on a focused page and on `page_unfocused`
(conftest.UNFOCUSED_WINDOW), the live condition where programmatic focus
changes fire nothing.
"""

import pytest


def in_both_windows(unfocused_xfail=None):
    """Parametrize a test over the two window modes; the test takes `window`
    and `request` and gets its page with `request.getfixturevalue(window)`.
    `unfocused_xfail` names the task that makes the unfocused run pass."""
    unfocused = "page_unfocused" if unfocused_xfail is None else pytest.param(
        "page_unfocused", marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason=unfocused_xfail))
    return pytest.mark.parametrize("window", ["page", unfocused], ids=["focused", "unfocused"])


def oracle(page, key):
    return page.evaluate("""(k) => {
      const o = window.__oracle;
      if (!o || !Object.prototype.hasOwnProperty.call(o, k)) throw new Error(`no __oracle key ${JSON.stringify(k)}`);
      return o[k];
    }""", key)


def list_shown(page, list_id="portal"):
    """Whether anything inside `list_id` is VISIBLE: live Workday keeps a
    closed popup's list in the DOM, hidden (notes §8a), so presence is not "open"."""
    return page.evaluate("""(id) => [...document.getElementById(id).children]
        .some((c) => c.offsetParent !== null)""", list_id)


# A GENERIC popup whose options open sub-lists (categories → leaves), plus a
# plain Yes/No popup and a hidden stale list. Not a Workday reproduction — live
# "How did you hear about us?" is a search box (notes §2, workday_search.html)
# — so it is a test page, not a fixture: it guards the engine's category
# handling for any vendor that does render popup trees.
CATEGORY_POPUP = """<fieldset><legend>How did you hear about us?</legend>
  <button id="heard" aria-haspopup="listbox" aria-label=" Select One Required">Select One</button></fieldset>
<fieldset><legend>Are you legally authorized to work in the United States?</legend>
  <button id="auth" aria-haspopup="listbox" aria-label=" Select One Required">Select One</button></fieldset>
<ul role="listbox" id="stale" style="display:none"><li role="option" id="stale-ca">Canada</li></ul>
<div id="portal"></div>
<script>
(() => {
  const TREES = {
    heard: [["Job Board", ["LinkedIn", "Indeed"]], ["Social Media", ["Twitter"]], ["Employee Referral", null]],
    auth: [["Yes", null], ["No", null]],
  };
  const portal = document.getElementById("portal");
  let open = null;
  const close = () => { portal.innerHTML = ""; open = null; };
  const render = (btn, items) => {
    portal.innerHTML = "";
    const ul = document.createElement("ul");
    ul.setAttribute("role", "listbox");
    for (const [label, kids] of items) {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.textContent = label;
      li.addEventListener("click", (e) => {
        e.stopPropagation();
        if (kids) render(btn, kids.map((k) => [k, null]));
        // Live Workday's aria-label is "<question> <value> Required": the value
        // part follows the pick (the question part is empty on this step).
        else { btn.textContent = label; btn.setAttribute("aria-label", ` ${label} Required`); close(); }
      });
      ul.append(li);
    }
    portal.append(ul);
    open = btn;
  };
  for (const id of Object.keys(TREES)) {
    const btn = document.getElementById(id);
    btn.addEventListener("click", (e) => { e.stopPropagation(); render(btn, TREES[id]); });
  }
  document.addEventListener("click", () => { if (open) close(); });
  document.getElementById("stale-ca").addEventListener("click", () => { window.staleHit = true; });
})();
</script>"""


# Consent-like options in a group, a set and a popup (the policy tests).
POLICY_PAGE = """
<fieldset><legend>Before you continue</legend>
  <label><input type='radio' name='c' value='a'>Email me updates</label>
  <label><input type='radio' name='c' value='b'>I certify that the above is true</label></fieldset>
<fieldset><legend>Topics</legend>
  <label><input type='checkbox' name='t' value='1'>Data</label>
  <label><input type='checkbox' name='t' value='2'>I agree to the privacy policy</label></fieldset>
<label id='src-l'>Where did you find us?</label>
<button id='src' aria-haspopup='listbox' aria-labelledby='src-l'>Select One</button>
<div id='portal'></div>
<script>
(() => {
  const btn = document.getElementById('src');
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    document.getElementById('portal').innerHTML =
      "<ul role='listbox'><li role='option'>Website</li><li role='option'>I consent to the terms of use</li></ul>";
    for (const li of document.querySelectorAll('#portal li')) {
      li.addEventListener('click', (ev) => { ev.stopPropagation(); btn.textContent = li.textContent; document.getElementById('portal').innerHTML = ''; });
    }
  });
  document.addEventListener('click', () => { document.getElementById('portal').innerHTML = ''; });
})();
</script>"""


# A GENERIC search box whose one-hit search commits that hit as a pill on its
# own (the behaviour notes §2 rule 5 saw on live Workday, where the Enter does
# it; here the typing does, so it runs before Task 5's press-and-Enter). The
# list keeps showing the hit. "Field of study" pills carry a remove control;
# "Minor" pills carry none and ignore a click, so what an explore commits there
# cannot be taken back. `__oracle.field_of_study` / `.minor` is what the fake
# app holds. `window.slowRemove` delays what a remove control does.
SINGLE_HIT_SEARCH = """<div class='q'><label for='fos'>Field of study</label>
  <div class='picker'><div class='pills'></div><input id='fos' role='combobox' aria-autocomplete='list'></div></div>
<div class='q'><label for='minor'>Minor</label>
  <div class='picker'><div class='pills'></div><input id='minor' role='combobox' aria-autocomplete='list'></div></div>
<div id='portal'></div>
<script>
(() => {
  const oracle = (window.__oracle = window.__oracle || {});
  const LEAVES = ["Analytics", "Business", "Business Administration", "Business Economics"];
  const KEY = { fos: "field_of_study", minor: "minor" };
  const portal = document.getElementById("portal");
  for (const input of document.querySelectorAll("input[role=combobox]")) {
    const pills = input.parentElement.querySelector(".pills");
    oracle[KEY[input.id]] = "";
    // `window.slowRemove` (ms): the remove control takes effect that late.
    const drop = () => setTimeout(() => { pills.replaceChildren(); oracle[KEY[input.id]] = ""; }, window.slowRemove ?? 0);
    const pick = (text) => {
      const pill = document.createElement("span");
      pill.className = "pill";
      pill.innerHTML = `<span class="multi-value__label"></span>`;
      pill.firstChild.textContent = text;
      if (input.id === "fos") {
        const x = document.createElement("button");
        x.type = "button";
        x.setAttribute("aria-label", `Remove ${text}`);
        x.textContent = "×";
        x.addEventListener("click", drop);
        pill.append(x);
      }
      pills.replaceChildren(pill);
      oracle[KEY[input.id]] = text;
    };
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      if (!q) { portal.replaceChildren(); return; }
      const hits = LEAVES.filter((t) => q.split(/\\s+/).every((w) => t.toLowerCase().includes(w)));
      portal.innerHTML = "<div role='listbox'>" + hits.map((t) => `<div role='option'>${t}</div>`).join("") + "</div>";
      for (const o of portal.querySelectorAll("[role=option]")) o.addEventListener("click", () => pick(o.textContent));
      if (hits.length === 1) pick(hits[0]);   // one hit: picked with no click
    });
  }
  document.addEventListener("mousedown", (e) => { if (!portal.contains(e.target)) portal.replaceChildren(); });
})();
</script>"""


# A GENERIC popup that picks its highlighted row whenever its list closes
# (a "select on blur" dropdown): opening highlights the first real option, so
# merely opening and closing it commits "Yes". Its backing input sits beside
# the button, as on Workday, and is what the fake app holds (`__oracle.move`).
# `window.slowReopen` makes every later open that many ms late.
SELECT_ON_CLOSE = """<label id='l'>Willing to move?</label>
<div><button id='move' aria-haspopup='listbox' aria-labelledby='l'>Select One</button><input type='hidden' value=''></div>
<div id='portal'></div>
<script>
(() => {
  const oracle = (window.__oracle = window.__oracle || {});
  oracle.move = "";
  const OPTIONS = ["Select One", "Yes", "No"];
  const btn = document.getElementById("move");
  const backing = btn.nextElementSibling;
  const portal = document.getElementById("portal");
  let highlighted = null;
  const close = () => {
    if (highlighted === null) return;
    btn.textContent = highlighted;
    backing.value = highlighted === "Select One" ? "" : highlighted;
    oracle.move = backing.value;
    highlighted = null;
    portal.replaceChildren();
  };
  // `window.slowReopen` (ms): every open after the first renders that late.
  let opens = 0;
  const render = () => {
    highlighted = OPTIONS[1];
    portal.innerHTML = "<ul role='listbox'>" + OPTIONS.map((t) => `<li role='option'>${t}</li>`).join("") + "</ul>";
    for (const li of portal.querySelectorAll("li")) {
      li.addEventListener("click", (ev) => { ev.stopPropagation(); highlighted = li.textContent; close(); });
    }
  };
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (highlighted !== null) { close(); return; }
    if (opens++ && window.slowReopen) setTimeout(render, window.slowReopen);
    else render();
  });
  document.addEventListener("click", close);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
})();
</script>"""
