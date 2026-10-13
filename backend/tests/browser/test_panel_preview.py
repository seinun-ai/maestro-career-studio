"""The static panel preview renders every state with the REAL panel code.

scripts/panel_preview.py serves extension/ plus a stubbed `chrome.*`; each
fixture under tests/fixtures/panel_preview/ is one state a reviewer opens in a
browser at 380x760. These tests load each one headless and check the panel
painted (no console errors, four rail rows) and that the footer's primary reads
what the state calls for.
"""

import importlib
import json

import pytest

# `None`: the panel shows no footer primary in that state.
CTA = {
    "job-unsaved": "Save job",
    "job-saved": "Update scores",
    "resume": "Quick tailor",
    "resume-ready": None,
    "fill": "Autofill",
    "fill-report": "Autofill",
    "track-draft": None,
    "track-applied": None,
    "dark-job-saved": "Update scores",
}


def preview():
    return importlib.import_module("scripts.panel_preview")


@pytest.fixture(scope="module")
def server():
    with preview().serve() as running:
        yield running


@pytest.fixture
def panel(browser):
    context = browser.new_context(viewport={"width": 380, "height": 760})
    pg = context.new_page()
    yield pg
    context.close()


def open_state(pg, server, name, scheme="light"):
    errors = []
    pg.on("console", lambda msg: msg.type == "error" and errors.append(msg.text))
    pg.on("pageerror", lambda exc: errors.append(str(exc)))
    pg.emulate_media(color_scheme=scheme)
    pg.goto(server.url(name))
    pg.wait_for_selector("#rail li.stg")
    pg.wait_for_function("document.querySelectorAll('#rail li.stg').length === 4")
    # The fill-report state presses Autofill itself; let that settle.
    pg.wait_for_timeout(600)
    return errors


def test_the_states_are_the_fixtures():
    assert list(preview().STATES) == list(CTA)
    for name in CTA:
        spec = json.loads((preview().FIXTURES / f"{name}.json").read_text())
        assert spec["tabs"], name


@pytest.mark.parametrize("name", list(CTA))
def test_each_state_paints_the_real_panel(panel, server, name):
    errors = open_state(panel, server, name, "dark" if name.startswith("dark") else "light")
    assert errors == []
    assert panel.locator("#rail li.stg").count() == 4
    ctas = panel.locator(".cta")
    if CTA[name] is None:
        assert ctas.count() == 0
    else:
        assert ctas.count() == 1
        assert ctas.inner_text().strip() == CTA[name]


def test_the_fill_report_state_shows_a_finished_loop_report(panel, server):
    open_state(panel, server, "fill-report")
    assert panel.locator("#rail .loop").count() == 1
    assert panel.locator("#rail .loop .grp").count() >= 3


def test_dark_is_a_different_paint_from_light(panel, server):
    open_state(panel, server, "job-saved")
    light = panel.evaluate("getComputedStyle(document.body).backgroundColor")
    open_state(panel, server, "dark-job-saved", "dark")
    dark = panel.evaluate("getComputedStyle(document.body).backgroundColor")
    assert light != dark


def test_each_base_row_wears_its_resumes_square_before_the_name(panel, server):
    """The square is the last child of the name (so the words stay its own text) and CSS puts it first."""
    open_state(panel, server, "job-saved")
    squares = panel.locator(".baserow .swatch")
    assert squares.count() == 4
    first = panel.locator(".baserow").first
    left = first.locator(".swatch").evaluate("el => el.getBoundingClientRect().left")
    name_left = first.locator("b").evaluate(
        "el => { const r = document.createRange(); r.selectNodeContents(el.firstChild);"
        " return r.getBoundingClientRect().left; }")
    assert left < name_left
    width = first.locator(".swatch").evaluate("el => el.getBoundingClientRect().width")
    assert abs(width - 10) < 0.5
    light = squares.first.evaluate("el => getComputedStyle(el).backgroundColor")
    assert light != "rgba(0, 0, 0, 0)"
    open_state(panel, server, "dark-job-saved", "dark")
    assert panel.locator(".baserow .swatch").first.evaluate("el => getComputedStyle(el).backgroundColor") != light


def test_an_unknown_state_is_a_404(server):
    from urllib.error import HTTPError
    from urllib.request import urlopen

    with pytest.raises(HTTPError) as err:
        urlopen(server.url("nope"))
    assert err.value.code == 404
