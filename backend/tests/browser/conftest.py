"""Real Chromium for the fill engine.

The fake-DOM harness (tests/extension_harness.py) cannot tell whether a
React-controlled box accepted a value, whether a popup belongs to the widget
that opened it, or whether a click committed. These tests load the REAL content
scripts (main world, via add_script_tag, as the research probe did) into
offline fixture pages. agent.js (the only chrome.* user) is never loaded.

Skip locally without Playwright/Chromium; FAIL in CI (tests/node_ts.py rule).
"""

import os
from pathlib import Path

import pytest

EXTENSION = Path(__file__).resolve().parents[3] / "extension"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "browser"

# Dependency order, mirrors manifest.json. Tasks append as files land.
ENGINE_SOURCES: list[str] = [
    "shared/policy.js",
    "content/field-reader.js",
    "content/fill-base.js",
    "content/shapes.js",
    "content/inventory.js",
    "content/fill-core.js",
    "content/fill-ops.js",
]


def _unavailable(why: str):
    if os.environ.get("CI"):
        pytest.fail(why)
    pytest.skip(why)


# Package scope, not session: while sync_playwright() is open its event loop
# counts as RUNNING on this thread, so every later test calling asyncio.run()
# fails ("cannot be called from a running event loop"). One Chromium for this
# package, closed before the rest of tests/ runs. Tests in tests/browser must
# stay synchronous: no async tests or asyncio.run() here while that loop is open.
@pytest.fixture(scope="package")
def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _unavailable("playwright is not installed")
    with sync_playwright() as p:
        try:
            chromium = p.chromium.launch(headless=True)
        except Exception as exc:
            _unavailable(f"chromium is not installed: {exc}")
        yield chromium
        chromium.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900}, offline=True)
    pg = context.new_page()
    yield pg
    context.close()


# UNFOCUSED-WINDOW MODE (notes §1, §6): live, while the browser window is not
# focused, `el.focus()` / `el.blur()` still move focus but fire NO focus, blur,
# focusin or focusout events — which is why text and dates never committed. The
# test page's window IS focused, so this recreates it: during a native
# focus()/blur() call every focus event is stopped at the window, in capture.
# Trusted Playwright input and events the engine dispatches itself still pass.
# Idempotent: set_content's document.open drops window listeners, so
# `page_unfocused` wraps its set_content to install it again after every page
# — `load` or a direct call (the end-to-end `_start`) alike.
UNFOCUSED_WINDOW = """(() => {
  const KEY = Symbol.for("careerStudioTests.unfocusedWindow");
  const state = (HTMLElement.prototype[KEY] ??= { muted: 0, wrapped: false });
  if (!state.wrapped) {
    state.wrapped = true;
    for (const name of ["focus", "blur"]) {
      const native = HTMLElement.prototype[name];
      HTMLElement.prototype[name] = function (...args) {
        state.muted += 1;
        try { return native.apply(this, args); } finally { state.muted -= 1; }
      };
    }
  }
  for (const type of ["focus", "blur", "focusin", "focusout"]) {
    window.addEventListener(type, (e) => { if (state.muted) e.stopImmediatePropagation(); }, true);
  }
})();"""


@pytest.fixture
def page_unfocused(browser):
    """A page whose window behaves as if the browser were not focused (see
    UNFOCUSED_WINDOW). Opt in per test; every set_content keeps the mode."""
    context = browser.new_context(viewport={"width": 1280, "height": 900}, offline=True)
    context.add_init_script(UNFOCUSED_WINDOW)
    pg = context.new_page()
    set_content = pg.set_content

    def _set_content(*args, **kwargs):
        set_content(*args, **kwargs)
        pg.evaluate(UNFOCUSED_WINDOW)

    pg.set_content = _set_content
    yield pg
    context.close()


def fixture_html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def load():
    def _load(pg, html: str, sources: list[str] | None = None):
        pg.set_content(html)
        for src in sources if sources is not None else ENGINE_SOURCES:
            pg.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))
        return pg

    return _load
