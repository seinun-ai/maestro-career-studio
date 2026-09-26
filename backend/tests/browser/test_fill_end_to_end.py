"""The fill engine end to end, on real widget behaviour: the gate before the
owner's live checkpoint (fill-engine plan Task 8).

ONE PAGE holds the body of every committed fixture, so the widgets meet each
other the way a real form's do (shared outside-click listeners, several popups,
one field's typing next to another's search). The content scripts load in the
manifest's order, and the loop (`shared/fill-loop.js`) runs in the same page
with the panel's two dependencies scripted:

- `broadcast` goes through the REAL page handlers — `agent.js`'s
  `chrome.runtime.onMessage` listener, captured by a stubbed `chrome.runtime` —
  and answers in `page_broadcast`'s shape, so a handler that drops a field of
  its message fails here;
- `api` is a scripted backend keyed by question text: `/map` from a table,
  `/pick` by exact text equality with the fact, `/step` clicking the candidate
  whose description names the fact, else `search:value` when a search box is
  offered, else a category scripted per question, else `open` when the popup is
  closed, else `give_up`. Every body is validated against the real endpoint's
  request model.

Fixture composition: the pages that render popups share the id `portal`, so
each page's portal is renamed to its own (`portal-<fixture>`) when composed.
The widgets themselves are unchanged.
"""

import json
import time

import pytest

from app.schemas.autofill_fill import MapRequest, PickRequest, StepRequest
from tests.browser.conftest import EXTENSION, fixture_html

MODELS = {"/api/autofill/map": MapRequest, "/api/autofill/pick": PickRequest,
          "/api/autofill/step": StepRequest}
FIXTURES = ["workday_text.html", "workday_listbox.html", "workday_search.html",
            "popup_with_search.html", "native.html", "workday_date.html", "react_select.html"]
# The manifest's content scripts, in its order, then the panel-side loop.
SOURCES = [*json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
           ["content_scripts"][0]["js"], "shared/fill-loop.js"]

# What the backend's /map answers, by question: the fact each field's slot holds.
MAP = {
    "City": {"route": "slot", "slot": "personal.city", "value": "Springfield"},
    "Postal Code": {"route": "slot", "slot": "personal.postal_code", "value": "12345"},
    "Are you legally authorized to work in the United States?":
        {"route": "slot", "slot": "work_auth.authorized_now", "value": "Yes"},
    "How did you hear about us?": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"},
    "School or University": {"route": "slot", "slot": "education.0.school",
                             "value": "University of Texas at Dallas"},
    "Type to Add Skills": {"route": "slot", "slot": "skills", "value": ["SQL", "Python", "Tableau"]},
    "Highest degree": {"route": "slot", "slot": "education.0.degree", "value": "Master's"},
    "Field of study": {"route": "slot", "slot": "education.0.discipline", "value": "Information Systems"},
    "Which days can you work?": {"route": "none"},
}
# The category a question's answer sits under, when no option names it.
CATEGORIES = {"How did you hear about us?": "Job Board"}

DRIVER = """(spec) => {
  const ns = window.careerStudioCompanion;
  Object.assign(ns.fillLoop.limits, spec.limits ?? {});
  const sent = [];
  const posts = [];
  let applies = 0;
  let stop = false;
  const deliver = (msg) => new Promise((resolve) => {
    const open = window.__pageListener(msg, { id: "t" }, (reply) =>
      resolve(reply?.ok ? [{ frameId: 0, result: reply.data }] : [{ frameId: 0, error: reply?.error }]));
    if (open !== true) resolve([]);
  });
  const broadcast = async (msg) => {
    sent.push(JSON.parse(JSON.stringify(msg)));
    const frames = await deliver(msg);
    if (msg.type === "fill_apply" && (applies += 1) === spec.stopAfterApplies) {
      // The panel's Stop: the flag the loop reads, and fill_cancel to the page.
      stop = true;
      await deliver({ type: "fill_cancel" });
    }
    return frames;
  };
  const factOf = (question, item) => item ?? spec.map[question]?.value;
  const named = (candidates, text) => candidates.find((c) => c.mid.startsWith("click:")
    && typeof text === "string" && c.describe.includes(JSON.stringify(text)));
  const click = (c) => ({ mid: c.mid, reason: c.describe.startsWith("Open the group") ? "progress" : "matched" });
  const api = async (path, init) => {
    const body = init?.body ? JSON.parse(init.body) : null;
    posts.push({ path: path.split("?")[0], body });
    if (path.startsWith("/api/autofill/context")) return { eeo_consent: { consent_forms: false } };
    if (path === "/api/autofill/map") {
      if (spec.holdMap) {
        window.__mapHeld = true;
        await new Promise((resolve) => { window.__openMap = resolve; });
      }
      return { fields: Object.fromEntries(body.fields.map((f) => [f.fid, spec.map[f.question] ?? { route: "none" }])) };
    }
    if (path === "/api/autofill/pick") {
      return { picks: Object.fromEntries(body.fields.map((f) => {
        const fact = factOf(f.question, f.item);
        const o = f.options.find((one) => one.text === fact);
        return [f.fid, o ? { oids: [o.oid], reason: "matched" } : { oids: [], reason: "abstained" }];
      })) };
    }
    if (path === "/api/autofill/step") {
      const c = body.candidates;
      const hit = named(c, factOf(body.question, body.item))
        ?? (c.some((one) => one.mid === "search:value") ? null : named(c, spec.categories[body.question]));
      if (hit) return click(hit);
      for (const mid of ["search:value", "open"]) {
        if (c.some((one) => one.mid === mid)) return { mid, reason: "progress" };
      }
      return { mid: "give_up", reason: "abstained" };
    }
    if (path === "/api/autofill/choose") return { choices: {} };
    throw Object.assign(new Error(path), { status: 404 });
  };
  const t0 = Date.now();
  window.__run = ns.fillLoop.runFill({ broadcast, api, cancelled: () => stop }, { sourceHint: null })
    .then((report) => ({ report, sent, posts, ms: Date.now() - t0 }));
  return true;
}"""


def _page_of_every_fixture() -> str:
    parts = []
    for name in FIXTURES:
        html = fixture_html(name)
        own = f"portal-{name.removesuffix('.html')}"
        html = html.replace('id="portal"', f'id="{own}"').replace(
            'getElementById("portal")', f'getElementById("{own}")')
        parts.append(f"<div>{html}</div>")
    return "\n".join(parts)


def _start(page, page_js=None, fresh=True, **spec):
    """Load the page (unless `fresh` is False: the same page, a second run) and
    start one run, left in flight as `window.__run`."""
    if fresh:
        page.set_content(_page_of_every_fixture())
        if page_js:
            page.evaluate(page_js)
        # The listener agent.js registers is the page's whole message door.
        page.evaluate("""() => {
          window.chrome = window.chrome || {};
          Object.defineProperty(window.chrome, "runtime", { configurable: true, value: {
            id: "t", onMessage: { addListener: (fn) => { window.__pageListener = fn; } } } });
        }""")
        for src in SOURCES:
            page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))
        assert page.evaluate("typeof window.__pageListener") == "function"
    page.evaluate(DRIVER, {"map": MAP, "categories": CATEGORIES, **spec})


def _finish(page):
    out = page.evaluate("() => window.__run")
    for post in out["posts"]:
        if post["path"] in MODELS:
            MODELS[post["path"]].model_validate(post["body"])
    out["by_question"] = {r["question"]: r for r in out["report"]["fields"]}
    return out


def _run(page, page_js=None, fresh=True, **spec):
    _start(page, page_js, fresh, **spec)
    return _finish(page)


def _open_popups(page):
    """Every popup or menu still showing: the portals, the react-select menu,
    and any visible listbox on the page."""
    return page.evaluate("""() => [
      ...[...document.querySelectorAll('[id^="portal-"], #menu-root')].filter((p) => p.children.length).map((p) => p.id),
      ...[...document.querySelectorAll('[role=listbox], [role=dialog]')]
        .filter((el) => el.offsetParent !== null && el.id !== 'stale').map((el) => el.outerHTML.slice(0, 60)),
    ]""")


def _pills(page, list_id):
    return page.evaluate(f"[...document.querySelectorAll('#{list_id} [data-automation-id=selectedItem]')]"
                         ".map((p) => p.textContent)")


@pytest.fixture
def e2e_page(page):
    page.set_default_timeout(60000)
    return page


def test_the_engine_fills_every_fixture_on_one_page(e2e_page):
    page = e2e_page
    t0 = time.monotonic()
    out = _run(page)
    elapsed = time.monotonic() - t0
    status = {q: r["status"] for q, r in out["by_question"].items()}

    # Workday text: committed by real typing, and no field error left.
    assert page.evaluate("window.committed") == {"city": "Springfield", "zip": "12345"}
    assert page.input_value("#city") == "Springfield" and page.input_value("#zip") == "12345"
    assert page.evaluate("document.querySelectorAll('[aria-invalid=\"true\"]').length") == 0
    # Workday listboxes: the plain one, and the category one through the adaptive step.
    assert page.inner_text("#auth") == "Yes"
    assert page.inner_text("#heard") == "LinkedIn"
    heard = [p["body"] for p in out["posts"] if p["path"] == "/api/autofill/step"
             and p["body"]["question"] == "How did you hear about us?"]
    assert heard, "LinkedIn was not reached through the adaptive step"
    # The category was offered, clicked, and opened onto LinkedIn.
    assert any(c["describe"] == 'Click the option "Job Board"' for b in heard for c in b["candidates"])
    assert any(c["describe"] == 'Click the option "LinkedIn"' for c in heard[-1]["candidates"])
    assert heard[-1]["history"][-1] == "click:o1 -> progressed"
    # Workday search: the school pill, and every skill (SQL was already there).
    assert _pills(page, "school-pills") == ["University of Texas at Dallas"]
    assert _pills(page, "skills-pills") == ["SQL", "Python", "Tableau"]
    # Native select.
    assert page.input_value("#deg") == "Master's"
    # A popup that needs its own search: open → search → click.
    assert page.inner_text("#fos") == "Information Systems"
    fos = [p["body"] for p in out["posts"] if p["path"] == "/api/autofill/step"
           and p["body"]["question"] == "Field of study"]
    assert fos, "Field of study was not reached through the adaptive step"
    assert [b["history"][-1] for b in fos[1:]] == ["open -> progressed", "search:value -> progressed"]
    # Reported as the page says: verified, and nothing guessed where no fact was.
    for question in ("City", "Postal Code", "Are you legally authorized to work in the United States?",
                     "How did you hear about us?", "School or University", "Type to Add Skills",
                     "Highest degree", "Field of study"):
        assert status[question] == "verified", (question, out["by_question"][question])
    assert status["Which days can you work?"] == "needs_answer"
    assert page.evaluate("[...document.querySelectorAll('input[name=days]:checked')].map((i) => i.value)") == ["mon"]
    # Nothing left open, and the whole run inside its budget.
    assert _open_popups(page) == []
    assert out["report"]["stopped"] is False and out["report"]["timedOut"] is False
    assert elapsed < 30, elapsed
    # Every page message the loop sent went through a real handler: the
    # inventory carried the run's id (the handler must forward it).
    inventories = [m for m in out["sent"] if m["type"] == "fill_inventory"]
    assert inventories and all(m["runId"] == out["report"]["runId"] for m in inventories)


def test_stop_between_two_fields_leaves_the_second_untouched(e2e_page):
    """Stop lands after the first write (City): the loop starts no other page
    action, fill_cancel stops anything in flight, and nothing is left open."""
    page = e2e_page
    out = _run(page, stopAfterApplies=1)
    assert out["report"]["stopped"] is True
    applies = [a for m in out["sent"] if m["type"] == "fill_apply" for a in m["actions"]]
    assert len(applies) == 1
    assert page.input_value("#city") == "Springfield"
    # Postal Code is next in the page: untouched, still the page's own value.
    assert page.input_value("#zip") == "00000"
    assert page.inner_text("#auth") == "Select One" and page.inner_text("#heard") == "Select One"
    assert page.input_value("#deg") == ""
    assert _pills(page, "school-pills") == []
    assert _open_popups(page) == []
    assert out["by_question"]["City"]["status"] == "verified"
    assert out["by_question"]["Postal Code"]["status"] == "needs_answer"

    # The Stop latched the page; the next run's inventory releases it — which
    # only works if the real handler forwards the run's id — and fills the rest.
    again = _run(page, fresh=False)
    assert again["report"]["stopped"] is False
    assert page.input_value("#zip") == "12345" and page.inner_text("#auth") == "Yes"
    assert again["by_question"]["City"]["status"] == "already"

def test_a_value_the_user_types_while_map_is_pending_is_theirs_and_kept(e2e_page):
    page = e2e_page
    _start(page, holdMap=True)
    page.wait_for_function("window.__mapHeld === true")
    page.type("#city", "Shelbyville")
    page.evaluate("window.__openMap()")
    out = _finish(page)
    assert out["by_question"]["City"]["status"] == "yours"
    assert page.input_value("#city") == "Shelbyville"
    writes = [a for m in out["sent"] if m["type"] == "fill_apply" for a in m["actions"]
              if a.get("value") == "Springfield"]
    # Refused at execution, or never sent: either way the page kept the user's.
    assert all(a["op"] == "write" for a in writes)
    # Everything else still filled.
    assert page.input_value("#zip") == "12345"


def test_a_field_that_reverts_after_verifying_is_filled_again(e2e_page):
    """The degree select reverts 400 ms after the engine's value verified —
    past its own readback, inside the loop's sweep and tail — and the next
    round fills it again."""
    page = e2e_page
    out = _run(page, page_js="""() => document.addEventListener("change", (e) => {
      if (e.target?.id !== "deg" || window.__reverted) return;
      window.__reverted = true;
      setTimeout(() => { e.target.value = ""; }, 400);
    }, true)""")
    assert page.evaluate("window.__reverted") is True
    assert page.input_value("#deg") == "Master's"
    degree = [a for m in out["sent"] if m["type"] == "fill_apply" for a in m["actions"]
              if a.get("text") == "Master's"]
    assert len(degree) == 2
    assert out["by_question"]["Highest degree"]["status"] == "verified"
