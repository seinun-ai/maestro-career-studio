"""Hidden/covered tabs: no animation frames and timers clamped to one second.

Only the browser scheduling is simulated; the fixtures and engine are real.
The date fixture's own deferred validation remains clamped too.
"""

import time

import pytest

from tests.browser.conftest import UNFOCUSED_WINDOW, fixture_html
from tests.browser.pages import OPS, inv, list_shown, oracle


HIDDEN_TAB = """(() => {
  Object.defineProperty(document, 'hidden', {get: () => true});
  Object.defineProperty(document, 'visibilityState', {get: () => 'hidden'});
  let frame = 0;
  window.requestAnimationFrame = () => ++frame;
  window.cancelAnimationFrame = () => {};
  const timeout = window.setTimeout;
  const interval = window.setInterval;
  window.setTimeout = (fn, ms = 0, ...args) => timeout(fn, Math.max(1000, ms), ...args);
  window.setInterval = (fn, ms = 0, ...args) => interval(fn, Math.max(1000, ms), ...args);
})();"""


@pytest.fixture
def hidden_page(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900}, offline=True)
    context.add_init_script(HIDDEN_TAB)
    context.add_init_script(UNFOCUSED_WINDOW)
    page = context.new_page()
    page.goto("about:blank")
    set_content = page.set_content

    def keep_unfocused(*args, **kwargs):
        set_content(*args, **kwargs)
        page.evaluate(UNFOCUSED_WINDOW)

    page.set_content = keep_unfocused
    yield page
    context.close()


def timed_operation(page, method, request):
    return page.evaluate(f"""async (request) => {{
      const start = performance.now();
      const result = await {OPS}.{method}([request]);
      return {{result, ms: performance.now() - start}};
    }}""", request)


def test_hidden_budget_expires_before_a_sleeping_operation_can_click(hidden_page, load):
    page = hidden_page
    load(page, "<button id='target'>Choose</button>")
    got = page.evaluate("""async () => {
      const base = window.careerStudioCompanion.fillBase;
      let clicks = 0;
      const target = document.getElementById('target');
      target.addEventListener('click', () => { clicks += 1; });
      const start = performance.now();
      const outcome = await base.withinBudget(async (token) => {
        await base.sleep(150);
        base.press(target, token);
        return 'clicked';
      }, 50).catch(error => error.name);
      const ms = performance.now() - start;
      await base.sleep(200);
      return {outcome, ms, clicks};
    }""")
    assert got["outcome"] == "Cancelled", got
    assert got["clicks"] == 0
    assert got["ms"] < 200


@pytest.mark.parametrize(("question", "answer", "key"), [
    ("Degree", "Masters", "degree"),
    ("Are you legally authorized to work in the United States?", "No", "auth"),
])
def test_hidden_listbox_explores_and_commits_within_each_budget(hidden_page, load, question, answer, key):
    page = hidden_page
    load(page, fixture_html("workday_listbox.html"))
    assert page.evaluate("[document.hidden, document.visibilityState]") == [True, "hidden"]
    field = inv(page)[question]
    target = {"fid": field["fid"], "fp": field["fp"]}
    explored = timed_operation(page, "explore", target)
    got = explored["result"][field["fid"]]
    assert got.get("error") is None, got
    assert got["complete"] and answer in [o["text"] for o in got["options"]]
    assert explored["ms"] < page.evaluate(f"{OPS}.budgets.explore")
    assert not list_shown(page)
    assert oracle(page, key) == ""

    chosen = timed_operation(page, "apply", {**target, "op": "choose", "text": answer})
    assert chosen["result"][0]["outcome"] == "verified", chosen
    assert oracle(page, key) == answer
    assert chosen["ms"] < page.evaluate(f"{OPS}.budgets.apply")
    assert not list_shown(page)


@pytest.mark.parametrize(("fixture", "question", "value", "key", "selector", "display"), [
    ("workday_text.html", "City", "Springfield", "city", None, None),
    ("workday_text.html", "Postal Code", "12345", "zip", None, None),
    ("workday_date.html", "From", "2019-08", "from", None, None),
    ("workday_date.html", "Date", "2026-09-26", "signed", None, None),
    ("workday_date.html", "Graduation date", "2021-05", None, "#n", "2021-05"),
    ("workday_date.html", "End date", "2021-05", None, "#p", "05/2021"),
])
def test_hidden_text_and_date_commit_within_the_field_budget(
    hidden_page, load, fixture, question, value, key, selector, display,
):
    page = hidden_page
    load(page, fixture_html(fixture))
    assert page.evaluate("[document.hidden, document.visibilityState]") == [True, "hidden"]
    field = inv(page)[question]
    budget = page.evaluate(f"{OPS}.budgets.apply")
    start = time.monotonic()
    written = timed_operation(page, "apply", {
        "fid": field["fid"], "fp": field["fp"], "op": "write", "value": value,
    })
    assert written["result"][0]["outcome"] == "verified", written
    if key:
        # Date validation is the APP's own timer, also delayed by the simulator.
        page.wait_for_function("([key, value]) => window.__oracle[key] === value",
                               arg=[key, value], polling=50, timeout=budget)
        assert oracle(page, key) == value
    else:
        assert page.input_value(selector) == display
    assert (time.monotonic() - start) * 1000 < budget


def test_hidden_writes_after_a_choice_land_once_on_the_redrawn_boxes(hidden_page, load):
    """A hidden tab clamps the page's 400 ms redraw to a second, so the quiet wait
    after the Country choice can end before it; the field is then found again and
    the write made once more. Every value lands on the new boxes."""
    page = hidden_page
    load(page, fixture_html("workday_misses.html"))
    f = {x["question"]: x for x in page.evaluate(f"async () => (await {OPS}.inventory({{}})).fields")}

    def row(question, **action):
        return page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f[question]["fid"], "fp": f[question]["fp"], **action})[0]

    assert row("Country", op="choose", text="Canada")["outcome"] == "verified"
    got = [row(q, op="write", value=v)["outcome"]
           for q, v in (("Address", "1 Main St"), ("City", "Toronto"), ("Postal Code", "M5V 2T6"))]
    assert got == ["verified"] * 3
    page.wait_for_function("() => window.__oracle.postalCode === 'M5V 2T6'")
    assert [oracle(page, k) for k in ("addressLine", "cityName", "postalCode")] == ["1 Main St", "Toronto", "M5V 2T6"]
