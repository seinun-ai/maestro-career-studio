"""Autofill's resume attach, inside the real fill loop, in real Chromium.

Lever and Ashby parse an uploaded resume into the form's own fields (name,
email, city…) AFTER the engine verified them. So the panel attaches through
the loop's `beforeSweep` hook: once, before the final sweep, which then
re-reads every field the engine verified and gives a changed one its one
re-commit per run. These tests run `shared/fill-loop.js` with the content
scripts in the manifest's order; the hook sends `attach_resume_pdf` through
`agent.js`'s real message door, as the panel's fan-out does.
"""

import pytest

from tests.browser.conftest import EXTENSION
from tests.browser.test_fill_end_to_end import SOURCES

PDF = "JVBERi0xLjQKJSVFT0YK"  # %PDF-1.4 %%EOF

# One text field and a Workday-shaped upload box whose page, once the upload
# is in, writes what it "parsed" over City: once (`parse: "once"`), or on
# every later change too (`parse: "always"`, a page that never lets go).
PAGE = """<form>
  <div><label for="city">City</label><input id="city" type="text"></div>
  <div data-automation-id="formField-resume">
    <h4 id="rh">Resume/CV</h4>
    <div data-automation-id="attachments-FileUpload" aria-labelledby="rh">
      <p>Drop file here</p>
      <input type="file" data-automation-id="file-upload-input-ref" multiple style="display:none">
      <div id="uploaded"></div>
    </div>
  </div>
</form>
<script>
(() => {
  const input = document.querySelector('[data-automation-id="file-upload-input-ref"]');
  const city = document.getElementById("city");
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  const parse = () => {
    setter.call(city, "Parsed City");
    city.dispatchEvent(new Event("input", { bubbles: true }));
    city.dispatchEvent(new Event("change", { bubbles: true }));
  };
  window.__parses = 0;
  input.addEventListener("change", () => {
    const names = [...input.files].map((f) => f.name);
    input.value = "";
    setTimeout(() => {
      for (const name of names) {
        const row = document.createElement("div");
        row.setAttribute("data-automation-id", "file-upload-item");
        row.textContent = name;
        document.getElementById("uploaded").append(row);
      }
      window.__parses += 1;
      parse();
      if (window.__parseMode === "always") {
        city.addEventListener("blur", () => setTimeout(parse, 50));
      }
    }, 150);
  });
})();
</script>"""

DRIVER = """(spec) => {
  const ns = window.careerStudioCompanion;
  const sent = [];
  let hooks = 0;
  const deliver = (msg) => new Promise((resolve) => {
    const open = window.__pageListener(msg, { id: "t" }, (reply) =>
      resolve(reply?.ok ? [{ frameId: 0, result: reply.data }] : [{ frameId: 0, error: reply?.error }]));
    if (open !== true) resolve([]);
  });
  const broadcast = async (msg) => { sent.push(JSON.parse(JSON.stringify(msg))); return deliver(msg); };
  const api = async (path, init) => {
    const body = init?.body ? JSON.parse(init.body) : null;
    if (path === "/api/autofill/map") {
      return { fields: Object.fromEntries(body.fields.map((f) => [f.fid, f.question === "City"
        ? { route: "slot", slot: "personal.city", value: "Springfield" } : { route: "none" }])) };
    }
    if (path === "/api/autofill/sections") {
      return { sections: Object.fromEntries(body.sections.map((x) => [x.sid, { kind: "none", wanted: 0 }])) };
    }
    if (path === "/api/autofill/pick") {
      return { picks: Object.fromEntries(body.fields.map((f) => [f.fid, { oids: [], reason: "abstained" }])) };
    }
    if (path === "/api/autofill/step") return { mid: "give_up", reason: "abstained" };
    throw Object.assign(new Error(path), { status: 404 });
  };
  const deps = { broadcast, api, cancelled: () => false };
  if (spec.hook) {
    deps.beforeSweep = async () => {
      hooks += 1;
      const [frame] = await deliver({ type: "attach_resume_pdf", b64: spec.pdf,
        filename: "Jane_Doe_Resume.pdf", expect: 1, resumeOnly: true });
      window.__attach = frame?.result ?? null;
    };
  }
  window.__run = ns.fillLoop.runFill(deps, { sourceHint: null })
    .then((report) => ({ report, sent, hooks, attach: window.__attach ?? null }));
  return true;
}"""


def _run(page, hook=True, parse="once"):
    page.set_content(PAGE)
    page.evaluate("(mode) => { window.__parseMode = mode; }", parse)
    page.evaluate("""() => {
      window.chrome = window.chrome || {};
      Object.defineProperty(window.chrome, "runtime", { configurable: true, value: {
        id: "t", onMessage: { addListener: (fn) => { window.__pageListener = fn; } } } });
    }""")
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))
    page.evaluate(DRIVER, {"hook": hook, "pdf": PDF})
    out = page.evaluate("() => window.__run")
    out["city"] = next(r for r in out["report"]["fields"] if r["question"] == "City")
    out["writes"] = [a for m in out["sent"] if m["type"] == "fill_apply" for a in m["actions"]
                     if a.get("value") == "Springfield"]
    return out


@pytest.fixture
def blank(page):
    page.set_default_timeout(30000)
    return page


def test_a_field_the_upload_overwrote_is_caught_by_the_sweep_and_filled_again(blank):
    out = _run(blank)
    assert out["hooks"] == 1
    assert out["attach"] == {"written": 1, "proven": 1}
    assert blank.evaluate("window.__parses") == 1
    # Written, overwritten by the page's parse, found by the sweep, written once more.
    assert len(out["writes"]) == 2
    assert blank.input_value("#city") == "Springfield"
    assert out["city"]["status"] == "verified"


def test_a_page_that_keeps_overwriting_is_never_reported_verified(blank):
    """One re-commit per run: a page that takes the value back again is
    reported unconfirmed, and its value is never called filled."""
    out = _run(blank, parse="always")
    # The sweep's one re-commit, and the write's own attempts: at least two.
    assert len(out["writes"]) >= 2
    assert blank.input_value("#city") == "Parsed City"
    assert out["city"]["status"] != "verified"


def test_without_the_hook_the_loop_is_unchanged(blank):
    out = _run(blank, hook=False)
    assert out["hooks"] == 0
    assert out["attach"] is None
    assert blank.evaluate("window.__parses") == 0
    assert len(out["writes"]) == 1
    assert out["city"]["status"] == "verified"
