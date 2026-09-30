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
- `api` is a scripted backend keyed by question text: `/map` from a table
  (by "<section>/<question>" first, so repeated entries can differ),
  `/sections` by heading (default: no profile list),
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
import re
from collections import Counter

import pytest

from app.schemas.autofill_fill import MapRequest, PickRequest, SectionsRequest, StepRequest
from tests.browser.conftest import EXTENSION, fixture_html
from tests.browser.pages import CATEGORY_POPUP, oracle

MODELS = {"/api/autofill/map": MapRequest, "/api/autofill/pick": PickRequest,
          "/api/autofill/step": StepRequest, "/api/autofill/sections": SectionsRequest}
FIXTURES = ["workday_text.html", "workday_listbox.html", "workday_search.html",
            "popup_with_search.html", "native.html", "workday_date.html", "react_select.html"]
# The manifest's content scripts, in its order, then the panel-side loop and
# the recipe book the panel hands it.
SOURCES = [*json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
           ["content_scripts"][0]["js"], "shared/fill-loop.js", "shared/recipe-book.js"]

# What the backend's /map answers, by question: the fact each field's slot holds.
MAP = {
    "City": {"route": "slot", "slot": "personal.city", "value": "Springfield"},
    "Postal Code": {"route": "slot", "slot": "personal.postal_code", "value": "12345"},
    "Are you legally authorized to work in the United States?":
        {"route": "slot", "slot": "work_auth.authorized_now", "value": "Yes"},
    "Degree": {"route": "slot", "slot": "education.0.degree", "value": "Masters"},
    "How Did You Hear About Us?": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"},
    "School or University": {"route": "slot", "slot": "education.0.school",
                             "value": "The University of Texas at Arlington"},
    "Type to Add Skills": {"route": "slot", "slot": "skills", "value": ["SQL", "Python", "Tableau"]},
    "Highest degree": {"route": "slot", "slot": "education.0.degree", "value": "Master's"},
    "Field of study": {"route": "slot", "slot": "education.0.discipline", "value": "Information Systems"},
    "Which days can you work?": {"route": "none"},
}
# The category a question's answer sits under, when no option names it: the
# generic popup tree (tests/browser/pages.CATEGORY_POPUP). The live Workday
# "How Did You Hear About Us?" is a search box instead (notes §2).
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
  // The fact a /pick or /step names: its set item, else the value scripted
  // for its question, else the value /map gave its slot (two entries asking
  // one question are scripted by "<section>/<question>", each its own slot).
  const factOf = (body) => body.item ?? spec.map[body.question]?.value
    ?? Object.values(spec.map).find((m) => body.slot && m.slot === body.slot)?.value;
  const named = (candidates, text) => candidates.find((c) => c.mid.startsWith("click:")
    && typeof text === "string" && c.describe.includes(JSON.stringify(text)));
  const click = (c) => ({ mid: c.mid, reason: c.describe.startsWith("Open the group") ? "progress" : "matched" });
  const api = async (path, init) => {
    const body = init?.body ? JSON.parse(init.body) : null;
    posts.push({ path: path.split("?")[0], body });
    // `backend`: /sections and /map are the REAL services (`real_backend`),
    // with only their model calls scripted.
    if (spec.backend && ["/api/autofill/map", "/api/autofill/sections"].includes(path)) {
      return window.__backend(path, body);
    }
    if (path.startsWith("/api/autofill/context")) return { eeo_consent: { consent_forms: spec.consentForms === true } };
    if (path === "/api/autofill/map") {
      if (spec.holdMap && !window.__mapHeld) {
        window.__mapHeld = true;
        await new Promise((resolve) => { window.__openMap = resolve; });
      }
      return { fields: Object.fromEntries(body.fields.map((f) => [f.fid,
        spec.map[`${f.section}/${f.question}`] ?? spec.map[f.question] ?? { route: "none" }])) };
    }
    if (path === "/api/autofill/sections") {
      return { sections: Object.fromEntries(body.sections.map((x) => [x.sid, spec.kinds?.[x.heading] ?? { kind: "none", wanted: 0 }])) };
    }
    if (path === "/api/autofill/pick") {
      return { picks: Object.fromEntries(body.fields.map((f) => {
        // `picks[question]`: { text, reason } for a field with no fact (a low-stakes one).
        const scripted = spec.picks?.[f.question];
        const fact = scripted ? scripted.text : factOf(f);
        const o = f.options.find((one) => one.text === fact);
        return [f.fid, o ? { oids: [o.oid], reason: scripted?.reason ?? "matched" } : { oids: [], reason: "abstained" }];
      })) };
    }
    if (path === "/api/autofill/step") {
      const c = body.candidates;
      const hit = named(c, factOf(body))
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
  // `book` (opt-in): the panel's recipe store for this run, over a book the
  // spec hands in (null: none yet); the book the run left comes back.
  const book = { current: spec.book ?? null };
  const recipes = "book" in spec ? ns.recipeBook.store({
    read: async () => book.current,
    write: async (next) => { book.current = next; },
    today: () => spec.today,
  }) : undefined;
  const t0 = Date.now();
  window.__run = ns.fillLoop.runFill({ broadcast, api, cancelled: () => stop, ...(recipes ? { recipes } : {}) },
    { sourceHint: null })
    .then((report) => ({ report, sent, posts, ms: Date.now() - t0, book: book.current }));
  return true;
}"""


def real_backend(page, monkeypatch, facts, kinds, keys):
    """Serve /sections and /map from the real services over `facts` (run with
    `backend=True`): code places entries and routes facts as production does,
    and only the model is scripted — `kinds` by heading, `keys` (the fact a
    field's label names, or none) by question."""
    from app.schemas.autofill_fill import MapResponse, SectionsResponse
    from app.services import autofill_map, autofill_sections, model_settings

    monkeypatch.setattr(model_settings, "get_autofill_engine", lambda session: "fast")
    monkeypatch.setattr(autofill_sections, "_with_llm", lambda sections, session: {
        s.sid: (kinds.get(s.heading, "none"), 0.95) for s in sections})
    monkeypatch.setattr(autofill_map, "_with_llm", lambda fields, criteria, session, *a, **kw: {
        f.fid: (keys.get(f.question, "none"), 0.95) for f in fields})

    def serve(path, body):
        if path == "/api/autofill/sections":
            req = MODELS[path].model_validate(body)
            return SectionsResponse(sections=autofill_sections.plan(req.sections, facts, None)).model_dump(mode="json")
        req = MODELS[path].model_validate(body)
        return MapResponse(fields=autofill_map.map_fields(req.fields, facts, None, eeo_consented=False,
                                                          low_stakes=False)).model_dump(mode="json")

    page.expose_function("__backend", serve)


def _page_of(fixtures) -> str:
    parts = []
    for name in fixtures:
        html = fixture_html(name)
        own = f"portal-{name.removesuffix('.html')}"
        html = html.replace('id="portal"', f'id="{own}"').replace(
            'getElementById("portal")', f'getElementById("{own}")')
        parts.append(f"<div>{html}</div>")
    return "\n".join(parts)


def _start(page, page_js=None, fresh=True, fixtures=FIXTURES, html=None, url=None, **spec):
    """Load the page composed of `fixtures` — or `html` as it is — (unless
    `fresh` is False: the same page, a second run) and start one run, left in
    flight as `window.__run`. `url`: served at that address (a real host)
    rather than set into a blank page."""
    if fresh:
        content = html if html is not None else _page_of(fixtures)
        if url is None:
            page.set_content(content)
        else:
            page.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html", body=content))
            page.goto(url)
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


def _run(page, page_js=None, fresh=True, fixtures=FIXTURES, html=None, **spec):
    _start(page, page_js, fresh, fixtures, html, **spec)
    return _finish(page)


def _open_popups(page):
    """Every popup or menu still SHOWING: a portal or the react-select menu with
    a visible child, and any visible listbox (a search widget's pill list is
    not a popup). Live Workday keeps a closed popup's list in the DOM, hidden
    (notes §8a), so presence is not "open"."""
    return page.evaluate("""() => [
      ...[...document.querySelectorAll('[id^="portal-"], #menu-root')]
        .filter((p) => [...p.children].some((c) => c.offsetParent !== null)).map((p) => p.id),
      ...[...document.querySelectorAll('[role=listbox], [role=dialog]')]
        .filter((el) => el.offsetParent !== null && el.id !== 'stale' && el.dataset.automationId !== 'selectedItemList')
        .map((el) => el.outerHTML.slice(0, 60)),
    ]""")


def test_the_composed_page_keeps_every_fixture_apart():
    """The composition renames each popup portal to its own: no id is left
    shared (a shared id would hand one fixture's list to another's script),
    and no page still reaches for the plain "portal"."""
    html = _page_of(FIXTURES)
    ids = Counter(re.findall(r"""(?<![\w-])id=["']([^"'$]+)["']""", html))
    assert {"heard", "school", "degree", "city", "portal-workday_search"} <= set(ids)
    assert [i for i, n in ids.items() if n > 1] == []
    assert '"portal"' not in html and "'portal'" not in html


@pytest.fixture
def e2e_page(page):
    page.set_default_timeout(60000)
    return page


def test_the_engine_fills_every_fixture_on_one_page(e2e_page):
    """Every widget the engine operates today, on one page."""
    page = e2e_page
    out = _run(page)
    status = {q: r["status"] for q, r in out["by_question"].items()}

    # Workday text: committed on leaving the box, and no field error left.
    assert (oracle(page, "city"), oracle(page, "zip")) == ("Springfield", "12345")
    assert page.input_value("#city") == "Springfield" and page.input_value("#zip") == "12345"
    assert page.evaluate("document.querySelectorAll('[aria-invalid=\"true\"]').length") == 0
    # Workday popups: the app took each pick (the backing input), not just the button text.
    assert page.inner_text("#auth") == "Yes" and oracle(page, "auth") == "Yes"
    assert page.inner_text("#degree") == "Masters" and oracle(page, "degree") == "Masters"
    # Native select.
    assert page.input_value("#deg") == "Master's"
    # Workday search boxes (notes §2): two identical LinkedIn leaves are one
    # option, the school is read after the staged results settle, and every
    # skill lands (SQL was already there; "Python" sits below the fold of a
    # virtualized list; "Tableau" is a single hit its Enter commits).
    assert oracle(page, "heard") == "LinkedIn"
    assert oracle(page, "school") == "The University of Texas at Arlington"
    assert oracle(page, "skills") == ["SQL", "Python", "Tableau"]
    assert [page.input_value(f"#{i}") for i in ("heard", "school", "skills")] == ["", "", ""]
    # A popup that needs its own search: open → search → click.
    assert page.inner_text("#fos") == "Information Systems"
    fos = [p["body"] for p in out["posts"] if p["path"] == "/api/autofill/step"
           and p["body"]["question"] == "Field of study"]
    assert fos, "Field of study was not reached through the adaptive step"
    assert [b["history"][-1] for b in fos[1:]] == ["open -> progressed", "search:value -> progressed"]
    # Reported as the page says: verified, and nothing guessed where no fact was.
    for question in ("City", "Postal Code", "Are you legally authorized to work in the United States?", "Degree",
                     "Highest degree", "Field of study", "How Did You Hear About Us?", "School or University",
                     "Type to Add Skills"):
        assert status[question] == "verified", (question, out["by_question"][question])
    assert status["Which days can you work?"] == "needs_answer"
    assert page.evaluate("[...document.querySelectorAll('input[name=days]:checked')].map((i) => i.value)") == ["mon"]
    # Telemetry for the filled widgets names the question, never the value.
    obs = page.evaluate("(r) => window.careerStudioCompanion.fillLoop.buildLoopObservations(r)", out["report"])
    by_label = {o["label"]: o for o in obs}
    for question in ("Are you legally authorized to work in the United States?", "Field of study",
                     "How Did You Hear About Us?"):
        assert by_label[question]["outcome"] == "verified"
    assert not any(v.lower() in o["label"].lower() for o in obs
                   for v in ("Information Systems", "Springfield", "Master's", "Masters", "LinkedIn",
                             "University of Texas"))
    # Nothing left open, and the whole run inside its budget.
    assert _open_popups(page) == []
    assert out["report"]["stopped"] is False and out["report"]["timedOut"] is False
    assert out["ms"] < 30000, out["ms"]
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
    assert page.inner_text("#auth") == "Select One" and oracle(page, "auth") == ""
    assert oracle(page, "heard") == "" and oracle(page, "school") == ""
    assert page.input_value("#deg") == ""
    assert _open_popups(page) == []
    assert out["by_question"]["City"]["status"] == "verified"
    assert out["by_question"]["Postal Code"]["status"] == "needs_answer"

    # The Stop latched the page; the next run's inventory releases it — which
    # only works if the real handler forwards the run's id — and fills the rest.
    again = _run(page, fresh=False)
    assert again["report"]["stopped"] is False
    assert page.input_value("#zip") == "12345" and oracle(page, "zip") == "12345"
    assert page.inner_text("#auth") == "Yes" and oracle(page, "auth") == "Yes"
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


def test_a_workday_dropdown_whose_label_never_updates_keeps_its_question(e2e_page):
    """Not every widget updates its aria-label after a pick: with the static
    " Select One Required" left over the value, the field must still ask its
    legend, so its fingerprint holds across the pick and the filled value is
    reported verified — never re-mapped as a new question "Select One" with a
    "wrote here for an earlier question" note."""
    page = e2e_page
    out = _run(page, page_js="""() => {
      const set = Element.prototype.setAttribute;
      Element.prototype.setAttribute = function (name, value) {
        if (name === "aria-label" && (this.id === "degree" || this.id === "auth")) return;
        return set.call(this, name, value);
      };
    }""")
    assert page.get_attribute("#auth", "aria-label") == " Select One Required"
    assert page.inner_text("#auth") == "Yes" and page.inner_text("#degree") == "Masters"
    assert (oracle(page, "auth"), oracle(page, "degree")) == ("Yes", "Masters")
    for question, answer in (("Are you legally authorized to work in the United States?", "Yes"), ("Degree", "Masters")):
        row = out["by_question"][question]
        assert (row["status"], row["answer"]) == ("verified", answer)
    mapped = [f["question"] for p in out["posts"] if p["path"] == "/api/autofill/map" for f in p["body"]["fields"]]
    assert "Select One" not in mapped
    assert not any("earlier question" in (r["answer"] or "") for r in out["report"]["fields"])


def test_the_category_path_runs_end_to_end(e2e_page):
    """A generic popup tree: no option names "LinkedIn", so /pick abstains and
    the adaptive step opens the list, steps into "Job Board" and clicks the
    leaf, through the real /step driver with both halves running."""
    page = e2e_page
    out = _run(page, html=CATEGORY_POPUP,
               map={"How did you hear about us?": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"},
                    "Are you legally authorized to work in the United States?":
                        {"route": "slot", "slot": "work_auth.authorized_now", "value": "Yes"}})
    assert page.inner_text("#heard") == "LinkedIn" and page.inner_text("#auth") == "Yes"
    heard = out["by_question"]["How did you hear about us?"]
    assert (heard["status"], heard["answer"]) == ("verified", "LinkedIn")
    assert out["by_question"]["Are you legally authorized to work in the United States?"]["status"] == "verified"
    steps = [p["body"] for p in out["posts"] if p["path"] == "/api/autofill/step"]
    assert [b["history"][-1] for b in steps] == ["choose -> abstained", "open -> progressed", "click:o1 -> progressed"]
    assert not page.evaluate("window.staleHit === true")
    assert _open_popups(page) == []


# workday_sections.html's first work entry, and the facts /map holds for it.
SECTIONS_MAP = {
    "Job Title": {"route": "slot", "slot": "experience.0.title", "value": "Analyst"},
    "Company": {"route": "slot", "slot": "experience.0.company", "value": "Acme"},
    "I currently work here": {"route": "slot", "slot": "experience.0.current", "value": "Yes"},
    "From": {"route": "slot", "slot": "experience.0.start_date", "value": "2021-05"},
    "To": {"route": "slot", "slot": "experience.0.end_date", "value": "2023-01"},
}


def test_currently_employed_is_ticked_before_the_dates(e2e_page):
    """Ticking "I currently work here" removes the entry's To date a frame
    later (notes §4). The tick is committed first (by its mapped slot), the
    loop sees the To date go before it reaches the dates, never writes to it,
    and the report has no row for it."""
    page = e2e_page
    out = _run(page, fixtures=["workday_sections.html"], map=SECTIONS_MAP)
    entry = "Work Experience 1"
    assert oracle(page, f"{entry}/I currently work here") is True
    assert page.locator('[aria-labelledby="Work-Experience-1-panel"] [data-automation-id="formField-endDate"]').count() == 0
    assert (oracle(page, f"{entry}/Job Title"), oracle(page, f"{entry}/Company"), oracle(page, f"{entry}/From")) == (
        "Analyst", "Acme", "2021-05")
    applies = [a for m in out["sent"] if m["type"] == "fill_apply" for a in m["actions"]]
    questions = {r["fid"]: r["question"] for r in out["report"]["fields"]}
    assert questions[applies[0]["fid"]] == "I currently work here"
    # The To date got no write at all: every action names a field still reported.
    assert all(a["fid"] in questions for a in applies)
    assert "To" not in out["by_question"]
    assert not any(r["status"] == "stale" or r["lastOutcome"] == "stale" for r in out["report"]["fields"])
    for question in ("I currently work here", "Job Title", "Company", "From"):
        assert out["by_question"][question]["status"] == "verified", out["by_question"][question]


def test_only_the_current_jobs_entry_has_currently_work_here_ticked(e2e_page):
    """Live Workday names every entry's box `currentlyWorkHere` (CarMax,
    2026-09-30): each entry's box is still its own question, so job #1 (the
    current one) is ticked and job #2 is not."""
    page = e2e_page
    slot = lambda s, v: {"route": "slot", "slot": s, "value": v}  # noqa: E731
    out = _run(page, fixtures=["workday_sections.html"],
               kinds={"Work Experience": {"kind": "experience", "wanted": 2, "order": [0, 1]}},
               map={"Work Experience 1/I currently work here": slot("experience.0.current", "Yes"),
                    "Work Experience 2/I currently work here": slot("experience.1.current", "No")})
    assert oracle(page, "entries")["Work Experience"] == 2
    assert oracle(page, "Work Experience 1/I currently work here") is True
    assert page.evaluate("window.__oracle['Work Experience 2/I currently work here'] ?? false") is False
    assert not page.locator("#Work-Experience-2-current").is_checked()
    ticks = {r["section"]: r["status"] for r in out["report"]["fields"] if r["question"] == "I currently work here"}
    assert ticks["Work Experience 1"] == "verified", ticks


def test_the_loop_adds_the_entries_the_profile_can_fill_and_fills_them(e2e_page):
    """workday_sections.html through the real handlers (notes §5): the profile
    has two jobs, one school and one website; the page shows one Work
    Experience entry, one Education entry and no Websites entry. Each
    section's OWN Add is pressed as often as the profile can fill (never
    Education's: its one entry is enough), never a Delete, and the new
    entries are filled in the same run."""
    page = e2e_page
    text = lambda slot, value: {"route": "slot", "slot": slot, "value": value}  # noqa: E731
    out = _run(page, fixtures=["workday_sections.html"],
               kinds={"Work Experience": {"kind": "experience", "wanted": 2, "order": [0, 1]},
                      "Education": {"kind": "education", "wanted": 1, "order": [0]},
                      "Websites": {"kind": "websites", "wanted": 1, "order": [0]}},
               map={"Work Experience 1/Job Title": text("experience.0.title", "Analyst"),
                    "Work Experience 1/Company": text("experience.0.employer", "Acme"),
                    "Work Experience 2/Job Title": text("experience.1.title", "Intern"),
                    "Work Experience 2/Company": text("experience.1.employer", "Initech"),
                    "Education 1/School or University": text("education.0.school", "State University"),
                    "Websites 1/URL": text("personal.website", "https://ada.dev")})
    assert oracle(page, "entries") == {"Work Experience": 2, "Education": 1, "Websites": 1}
    assert oracle(page, "deleted") == 0
    assert [oracle(page, f"Work Experience {n}/{q}") for n in (1, 2) for q in ("Job Title", "Company")] == [
        "Analyst", "Acme", "Intern", "Initech"]
    assert oracle(page, "Education 1/School or University") == "State University"
    assert oracle(page, "Websites 1/URL") == "https://ada.dev"
    adds = [m for m in out["sent"] if m["type"] == "fill_add"]
    assert [(m["heading"], m["entries"]) for m in adds] == [("Work Experience", 1), ("Websites", 0)]
    assert out["report"]["sections"] == [
        {"heading": "Work Experience", "kind": "experience", "wanted": 2, "entries": 2, "added": 1, "outcome": "added",
         "reason": None},
        {"heading": "Education", "kind": "education", "wanted": 1, "entries": 1, "added": 0, "outcome": None,
         "reason": None},
        {"heading": "Websites", "kind": "websites", "wanted": 1, "entries": 1, "added": 1, "outcome": "added",
         "reason": None},
    ]
    filled = {(r["section"], r["question"]): r["status"] for r in out["report"]["fields"]}
    for key in (("Work Experience 2", "Job Title"), ("Work Experience 2", "Company"), ("Websites 1", "URL")):
        assert filled[key] == "verified", key


# A Workday-style text box asking the owner's Guidehouse salary question
# (notes §8): the app takes the amount on leaving the box and shows it back
# re-punctuated, "$80,000.00" for 80000.
SALARY = "What are your annual salary requirements?"
SALARY_PAGE = """
<div data-automation-id="formField-salary">
  <label for="sal">What are your annual salary requirements?*</label>
  <input id="sal" type="text" aria-required="true">
</div>
<script>
(() => {
  const oracle = (window.__oracle = window.__oracle || {});
  oracle.salary = null;
  const input = document.getElementById("sal");
  input.addEventListener("focusout", () => {
    if (document.activeElement === input) return;
    const n = Number(input.value.replace(/[^0-9.]/g, ""));
    oracle.salary = n || null;
    if (n) input.value = "$" + n.toLocaleString("en-US") + ".00";
  });
})();
</script>
"""


def test_salary_requirements_are_filled_only_with_the_agreement_permission(e2e_page):
    """Without the standing agreement permission a salary question is refused
    by its label and never reaches /map. With it, /map answers it with the
    desired-salary fact (its description names "salary requirements") and
    the money format the backend chose for that slot, so the app's own
    "$80,000.00" reads back as the 80000 written."""
    page = e2e_page
    salary = {SALARY: {"route": "slot", "slot": "preferences.desired_salary", "value": "80000", "format": "money"}}
    off = _run(page, html=SALARY_PAGE, map=salary)
    assert off["by_question"][SALARY]["status"] == "blocked"
    assert not [f for p in off["posts"] if p["path"] == "/api/autofill/map" for f in p["body"]["fields"]]
    assert oracle(page, "salary") is None and page.input_value("#sal") == ""

    on = _run(page, html=SALARY_PAGE, map=salary, consentForms=True)
    assert on["by_question"][SALARY]["status"] == "verified", on["by_question"][SALARY]
    assert oracle(page, "salary") == 80000 and page.input_value("#sal") == "$80,000.00"
    [write] = [a for m in on["sent"] if m["type"] == "fill_apply" for a in m["actions"] if a["op"] == "write"]
    assert (write["value"], write["format"]) == ("80000", "money")


# Live CarMax Workday's terms box (2026-09-30): one checkbox, its label the agreement.
TERMS = "Yes, I have read and consent to all the terms and conditions"
TERMS_PAGE = f"""<div data-automation-id="formField-agreementCheckbox">
  <input type="checkbox" id="terms" aria-required="true"><label for="terms">{TERMS}</label></div>"""


def test_a_terms_box_is_ticked_only_while_agreeing_to_terms_is_a_fact(e2e_page, monkeypatch):
    """With the agreement permission on, the label policy lets the box
    through, and the REAL /map ties it to `derived.agrees_to_terms` — which
    the catalog holds only while that permission is served on. Without the
    fact (a lapsed agreement) nothing answers the box and it is left."""
    from app.services import autofill_catalog

    page = e2e_page
    facts = autofill_catalog.with_agreement(autofill_catalog.build({}, [], []), True)
    real_backend(page, monkeypatch, facts, kinds={}, keys={TERMS: "derived.agrees_to_terms"})
    # /pick stays scripted: the option whose text is the fact's value ("Yes").
    pick_by = {TERMS: {"route": "slot", "slot": "derived.agrees_to_terms", "value": "Yes"}}
    on = _run(page, html=TERMS_PAGE, backend=True, consentForms=True, map=pick_by)
    assert page.is_checked("#terms")
    assert on["by_question"][TERMS]["status"] == "verified", on["by_question"][TERMS]

    facts.pop("derived.agrees_to_terms")
    off = _run(page, html=TERMS_PAGE, backend=True, consentForms=True, map=pick_by)
    assert not page.is_checked("#terms")
    assert off["by_question"][TERMS]["status"] == "needs_answer"
    assert not [a for m in off["sent"] if m["type"] == "fill_apply" for a in m["actions"]]


GEM_MAP = {
    "First name": {"route": "slot", "slot": "personal.first_name", "value": "Ada"},
    "Last name": {"route": "slot", "slot": "personal.last_name", "value": "Lovelace"},
    "Email": {"route": "slot", "slot": "personal.email", "value": "ada@example.com"},
    "LinkedIn URL": {"route": "slot", "slot": "personal.linkedin", "value": "https://example.com/ada"},
    "Are you graduating in 2027?": {"route": "slot", "slot": "education.0.graduating", "value": "No"},
    "Is your degree in Computer Science?": {"route": "slot", "slot": "education.0.discipline_cs", "value": "Yes"},
}


def test_a_gem_form_is_filled_by_the_text_before_each_field(e2e_page):
    """gem_form.html (jobs.gem.com, live 2026-09-27): nothing names a box but
    the text before it, and each Yes/No question is two nameless radios. Every
    box is written, and each question gets exactly one answer — the one its
    fact states, not merely the first option."""
    page = e2e_page
    out = _run(page, fixtures=["gem_form.html"], map=GEM_MAP)
    assert [oracle(page, k) for k in ("gem_first_name", "gem_last_name", "gem_email", "gem_linkedin")] == [
        "Ada", "Lovelace", "ada@example.com", "https://example.com/ada"]
    assert (oracle(page, "gem_graduating"), oracle(page, "gem_cs_degree")) == ("No", "Yes")
    assert page.evaluate("[...document.querySelectorAll('#gem-form input[type=radio]:checked')].map((r) => r.id)") == [
        "r7c1f0-no", "r2e9b4-yes"]
    for question in GEM_MAP:
        assert out["by_question"][question]["status"] == "verified", out["by_question"].get(question)
    assert "" not in out["by_question"]


def _checked(page):
    return page.evaluate("[...document.querySelectorAll('input:checked')].map((i) => i.id)")


def test_options_labelled_after_them_are_never_chosen_by_their_neighbours_text(e2e_page):
    """Reviewer probe (2026-09-28): options whose labels are spans AFTER them
    read no text, so the fact "Yes" matches none of them. Nothing is checked
    and the question is left for the user — never "No" checked and reported
    verified because its option read the previous option's "Yes"."""
    page = e2e_page
    out = _run(page, html="<p>Intro to the application</p><div role=radiogroup aria-label='Willing to relocate?'>"
                          "<input type=radio name=q id=y><span>Yes</span><input type=radio name=q id=n><span>No</span></div>",
               map={"Willing to relocate?": {"route": "slot", "slot": "work_auth.relocate", "value": "Yes"}})
    assert _checked(page) == []
    assert out["by_question"]["Willing to relocate?"]["status"] == "needs_answer"


def test_two_nameless_questions_under_one_wrapper_are_both_filled(e2e_page):
    page = e2e_page
    out = _run(page, html="<div><span>Need sponsorship?</span>"
               "<div><input type=radio id=a><label for=a>Yes</label></div><div><input type=radio id=b><label for=b>No</label></div>"
               "<span>Over 18?</span>"
               "<div><input type=radio id=c><label for=c>Yes</label></div><div><input type=radio id=d><label for=d>No</label></div></div>",
               map={"Need sponsorship?": {"route": "slot", "slot": "work_auth.sponsorship", "value": "No"},
                    "Over 18?": {"route": "slot", "slot": "work_auth.over_18", "value": "Yes"}})
    assert _checked(page) == ["b", "c"]
    assert {q: r["status"] for q, r in out["by_question"].items()} == {
        "Need sponsorship?": "verified", "Over 18?": "verified"}
