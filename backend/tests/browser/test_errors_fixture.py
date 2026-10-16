"""The Workday-style errors page (fixtures/browser/workday_errors.html) in real Chromium: a Next the
page rejects, and the repair that touches only the field its error named.

The loop runs in the page with the real content scripts behind a captured `chrome.runtime` listener
(the door `test_fill_end_to_end.py` uses) and a scripted backend. The backend is told every field a
fill could map, so a field that is touched anyway is the loop's doing, not the script's.
"""


from tests.browser.conftest import EXTENSION, fixture_html
from tests.browser.test_fill_end_to_end import SOURCES

DRIVER = """async (spec) => {
  const ns = window.careerStudioCompanion;
  const sent = [];
  const posts = [];
  const deliver = (msg) => new Promise((resolve) => {
    const open = window.__pageListener(msg, { id: "t" }, (reply) =>
      resolve(reply?.ok ? [{ frameId: 0, result: reply.data }] : [{ frameId: 0, error: reply?.error }]));
    if (open !== true) resolve([]);
  });
  const broadcast = async (msg) => { sent.push(JSON.parse(JSON.stringify(msg))); return deliver(msg); };
  const api = async (path, init) => {
    const body = init?.body ? JSON.parse(init.body) : null;
    posts.push({ path: path.split("?")[0], body });
    if (path.startsWith("/api/autofill/context")) return { eeo_consent: { consent_forms: false } };
    // Every field the loop sends gets a fact, so only `only` can keep a field out of it.
    if (path === "/api/autofill/map") {
      return { fields: Object.fromEntries(body.fields.map((f) => [f.fid, spec.map[f.question] ?? { route: "none" }])) };
    }
    if (path === "/api/autofill/pick") return { picks: Object.fromEntries(body.fields.map((f) => [f.fid, { oids: [], reason: "abstained" }])) };
    if (path === "/api/autofill/step") return { mid: "give_up", reason: "abstained" };
    if (path === "/api/autofill/sections") return { sections: {} };
    if (path === "/api/autofill/choose") return { choices: {} };
    throw Object.assign(new Error(path), { status: 404 });
  };
  Object.assign(ns.fillLoop.limits, { QUIET_MS: 0 });
  const fields = (await deliver({ type: "fill_inventory" }))[0].result.fields;
  const fid = (q) => fields.find((f) => f.question === q)?.fid ?? null;
  const report = await ns.fillLoop.runFill({ broadcast, api, cancelled: () => false },
    { sourceHint: null, ...(spec.only ? { only: spec.only.map(fid) } : {}) });
  return { report, sent, posts, fids: Object.fromEntries(fields.map((f) => [f.question, f.fid])) };
}"""

MAP = {
    "Skills": {"route": "slot", "slot": "skills", "value": ["SQL", "Python", "Go", "Rust"]},
    "Field of Study": {"route": "slot", "slot": "education.0.discipline", "value": "Information Systems"},
}


def _load(page):
    page.set_content(fixture_html("workday_errors.html"))
    page.evaluate("""() => {
      window.chrome = window.chrome || {};
      Object.defineProperty(window.chrome, "runtime", { configurable: true, value: {
        id: "t", onMessage: { addListener: (fn) => { window.__pageListener = fn; } } } });
    }""")
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))
    assert page.evaluate("typeof window.__pageListener") == "function"


def _pills(page):
    return page.evaluate("[...document.querySelectorAll('[data-automation-id=selectedItem]')].length")


def test_a_repair_of_the_field_the_error_named_never_touches_the_skills_box(page):
    page.set_default_timeout(60000)
    _load(page)
    out = page.evaluate(DRIVER, {"map": MAP, "only": ["Field of Study"]})
    skills = out["fids"]["Skills"]
    # Only Field of Study is read into a row, mapped, explored or written.
    assert [row["fid"] for row in out["report"]["fields"]] == [out["fids"]["Field of Study"]]
    mapped = [f["fid"] for p in out["posts"] if p["path"] == "/api/autofill/map" for f in p["body"]["fields"]]
    assert skills not in mapped
    explored = [r["fid"] for m in out["sent"] if m["type"] == "fill_explore" for r in m["requests"]]
    applied = [a["fid"] for m in out["sent"] if m["type"] == "fill_apply" for a in m["actions"]]
    assert skills not in explored and skills not in applied
    # The skills it already held are the skills it still holds.
    assert _pills(page) == 15


def test_the_same_run_without_only_does_work_the_skills_box(page):
    """The control: the scripted backend does offer the skills box a fact, so the test above is not vacuous."""
    page.set_default_timeout(60000)
    _load(page)
    out = page.evaluate(DRIVER, {"map": MAP, "only": None})
    mapped = [f["fid"] for p in out["posts"] if p["path"] == "/api/autofill/map" for f in p["body"]["fields"]]
    assert out["fids"]["Skills"] in mapped
