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
