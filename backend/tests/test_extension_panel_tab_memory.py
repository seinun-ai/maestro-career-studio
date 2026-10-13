"""The panel's job memory is one entry PER TAB, and it lasts as long as the tab.

`widget.session` used to be one key per browser with a 30-minute life, so a long
wizard forgot its job and a second tab's pick overwrote the first. It is now a
map in `chrome.storage.session` (`widget.sessions`, tab id to entry): a tab's
entry is written by that tab's panel, read back only for that tab, and deleted
when the tab closes. There is no clock. What still drops an entry are the three
guards of `restorableSession` (origin, tenant, the backend naming another job)
and the one this task added: a page that is a SIBLING posting of the one the pick
was made on.

THE APPARATUS is `extension_panel_harness.py`; its "pick shorthand" note says how
the older tests in the suite (`stored={"widget.session": entry}`) mean "the pick
of the tab the panel is bound to". The tests here are the ones about the map
itself, so they speak in `sessionStored["widget.sessions"]`, `picks` and
`pickWrites` and fire the tab events a browser would.
"""
import time

from tests.extension_fixtures import (
    COHERE_TENANT,
    GREENHOUSE_ORIGIN,
    LIGHTNING_APPLY_URL,
    LIGHTNING_TENANT,
    POSTING_URL,
    entry,
)
from tests.extension_harness import run_node
from tests.extension_panel_harness import (
    APP_URL,
    BASE_RESUMES,
    PANEL_SOURCE,
    SCORES,
    SETTINGS_REPLY,
    _PANEL_FAKES_JS,
    _by_class,
    _load,
    _reply,
)

MINUTE_MS = 60_000
OTHER_APPLY_URL = f"{GREENHOUSE_ORIGIN}/lightningai/jobs/100/apply"
COHERE_APPLY_URL = f"{GREENHOUSE_ORIGIN}/cohere/jobs/5/apply"

_UNMATCHED = _reply({"match": "none", "job": None, "application": None})
_API = {
    "greenhouse.io": _UNMATCHED,
    "/api/base-resumes": _reply(BASE_RESUMES),
    "/api/ats-scores": _reply(SCORES),
    "/api/applications/app-remembered": _reply({"pdf_path": "renders/r.pdf", "status": "draft"}),
    "/api/applications/app-other": _reply({"pdf_path": "renders/o.pdf", "status": "draft"}),
}


def _now_ms():
    return int(time.time() * 1000)


def _armed(identity):
    """The application id the header link points at, or None when nothing is armed."""
    for link in _by_class(identity, "linkish"):
        before, sep, app_id = link["href"].partition(f"{APP_URL}/applications/")
        if sep and not before:
            return app_id
    return None


def _seeded(**tabs):
    """`widget.sessions` as the browser holds it: tab id to entry."""
    return {"widget.sessions": {str(tab): one for tab, one in tabs.items()}}


# A driver for the events a map is about: a tab becomes the active one, navigates
# in place, or closes. One panel, many tabs; each step reports what the panel
# shows and what the map holds afterwards.
_TABS_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
const findTag = (node, tag) => [
  ...(node.tagName === tag ? [node] : []),
  ...node.children.flatMap((kid) => findTag(kid, tag)),
];
// ANOTHER WINDOW'S PANEL, caught in the act. When armed, the first read of the
// map hands this panel its snapshot and then holds it for a while; meanwhile the
// rival does what a second panel does, a read-modify-write of the whole map under
// the same Web Lock. Whether the rival's tab survives is whether the panel's
// write was exclusive of it.
let rivalArmed = false;
let rivalDone = null;
const readPicks = chrome.storage.session.get;
const writePicks = chrome.storage.session.set;
chrome.storage.session.get = async (key) => {
  const snapshot = await readPicks(key);
  if (key === "widget.sessions" && rivalArmed) {
    rivalArmed = false;
    rivalDone = navigator.locks.request("maestro.widget.sessions", async () => {
      const map = (await readPicks(key))[key];
      await writePicks({ [key]: { ...map, [spec.rival.tab]: spec.rival.entry } });
    });
    await new Promise((resolve) => setTimeout(resolve, 30));
  }
  return snapshot;
};
main(async () => {
  await settle();
  const shots = [{ regions: regions(), picks: JSON.parse(JSON.stringify(pickMapNow())) }];
  for (const step of spec.steps) {
    if (step.activate !== undefined) await onActivated({ tabId: step.activate });
    if (step.navigate) await onUpdated(step.tab, { url: step.navigate });
    if (step.close !== undefined) await onRemoved(step.close);
    await settle();
    if (step.armRival) rivalArmed = true;
    if (step.pickDraft !== undefined) {
      const [select] = findTag(REGIONS.rail, "SELECT");
      select.value = select.children.filter((option) => option.value)[step.pickDraft].value;
      select.dispatch("change");
      await settle();
      if (rivalDone) await rivalDone;
      await settle();
    }
    shots.push({ regions: regions(), picks: JSON.parse(JSON.stringify(pickMapNow())) });
  }
  emit({ shots, pickWrites, pickEntries, writes, removals, allTabQueries, locksAsked });
});
"""


def _tabs(tmp_path, **spec):
    spec.setdefault("replies", {"read_settings": SETTINGS_REPLY})
    spec.setdefault("api", _API)
    return run_node(_TABS_DRIVER_JS, spec, tmp_path, source=PANEL_SOURCE)


# ---------- no clock ----------


def test_a_pick_comes_back_in_its_own_tab_however_long_ago_it_was_made(tmp_path):
    """The 30-minute window is gone: a wizard a user walks away from for an hour
    is still on the job it was started for. The entry here is stamped 40 minutes
    ago (the shape every profile that ran an earlier build holds), and it is
    restored on the next page of the same posting."""
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}], api=_API,
                sessionStored=_seeded(**{"7": entry(at=_now_ms() - 40 * MINUTE_MS,
                                                    link=POSTING_URL)}))
    assert _armed(out["regions"]["identity"]) == "app-remembered"


def test_a_restored_wizard_page_is_not_a_new_write(tmp_path):
    """Reading the memory back costs no write: the entry is rewritten when the
    user changes something, not when a page loads."""
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}], api=_API,
                sessionStored=_seeded(**{"7": entry(link=POSTING_URL)}))
    assert out["pickWrites"] == []


# ---------- one entry per tab ----------


def test_another_tabs_pick_never_shows_in_this_tab(tmp_path):
    """Two tabs on the SAME employer: tab 7 has a pick, tab 8 is a different
    posting the user opened beside it. With one key, whichever pick was written
    last won both; with a map, tab 8 has no entry and tab 7 keeps its own."""
    out = _tabs(tmp_path, tabs=[{"id": 8, "url": OTHER_APPLY_URL}],
                tabUrls={"7": LIGHTNING_APPLY_URL, "8": OTHER_APPLY_URL},
                sessionStored=_seeded(**{"7": entry(link=POSTING_URL)}),
                steps=[{"activate": 7}, {"activate": 8}, {"activate": 7}])
    on_8_first, on_7, on_8, back_on_7 = out["shots"]
    assert _armed(on_8_first["regions"]["identity"]) is None
    assert _armed(on_7["regions"]["identity"]) == "app-remembered"
    assert _armed(on_8["regions"]["identity"]) is None
    assert _armed(back_on_7["regions"]["identity"]) == "app-remembered"
    assert out["pickWrites"] == []


def test_a_pick_in_a_second_tab_leaves_the_first_tabs_entry_alone(tmp_path):
    """The write is a merge into the map, not a replacement of it, and the new
    entry is keyed by the tab it was made in, with the page's address trimmed to
    the part that names the posting (no query, no fragment: a referral id is not
    a posting)."""
    first = entry(link=POSTING_URL)
    draft = {"id": "app-1", "job_id": "job-1", "base_resume": "ai_ml_engineer",
             "status": "draft", "job_company": "Cohere", "job_title": "Research Engineer 1"}
    cohere_page = f"{COHERE_APPLY_URL}?gh_src=abc#form"
    out = _tabs(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}],
                tabUrls={"7": LIGHTNING_APPLY_URL, "8": cohere_page},
                page={"detect_page": _reply({"tier": "B", "form": True, "score": 2}),
                      "extract_job_posting": _reply(
                          {"url": cohere_page, "title": "Apply", "text": "", "source": "body"})},
                api={**_API, "GET /api/applications?": _reply([draft]),
                     "GET /api/applications/app-1": _reply({"pdf_path": None, "status": "draft"})},
                sessionStored=_seeded(**{"7": first}),
                steps=[{"activate": 8, "pickDraft": 0}, {"activate": 7}])
    picked, back_on_7 = out["shots"][1], out["shots"][2]
    assert set(picked["picks"]) == {"7", "8"}
    assert picked["picks"]["7"] == first
    assert picked["picks"]["8"]["applicationId"] == "app-1"
    assert picked["picks"]["8"]["tenant"] == COHERE_TENANT
    assert picked["picks"]["8"]["link"] == f"{GREENHOUSE_ORIGIN}/cohere/jobs/5/apply"
    assert back_on_7["picks"]["7"] == first
    assert _armed(back_on_7["regions"]["identity"]) == "app-remembered"


# ---------- the tab closes ----------


def test_closing_a_tab_forgets_its_job_and_only_its_job(tmp_path):
    out = _tabs(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}],
                sessionStored=_seeded(**{"7": entry(link=POSTING_URL),
                                         "8": entry(applicationId="app-other")}),
                steps=[{"close": 7}])
    booted, closed = out["shots"]
    assert set(booted["picks"]) == {"7", "8"}
    assert set(closed["picks"]) == {"8"}
    assert closed["picks"]["8"]["applicationId"] == "app-other"


def test_closing_a_tab_that_had_no_entry_writes_nothing(tmp_path):
    out = _tabs(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}],
                sessionStored=_seeded(**{"7": entry(link=POSTING_URL)}),
                steps=[{"close": 99}])
    assert out["pickWrites"] == []


# ---------- the guards that stay ----------


def test_a_tab_that_moves_to_another_employer_stops_restoring_the_pick(tmp_path):
    """The tenant guard, in the one place it now matters most: the same tab,
    navigated in place. The entry is not deleted (the user may come back), it is
    simply not offered on a page that is not the posting's employer."""
    out = _tabs(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}],
                sessionStored=_seeded(**{"7": entry(link=POSTING_URL)}),
                steps=[{"tab": 7, "navigate": COHERE_APPLY_URL},
                       {"tab": 7, "navigate": LIGHTNING_APPLY_URL}])
    on_lightning, on_cohere, back = out["shots"]
    assert _armed(on_lightning["regions"]["identity"]) == "app-remembered"
    assert _armed(on_cohere["regions"]["identity"]) is None
    assert _armed(back["regions"]["identity"]) == "app-remembered"


def test_a_different_posting_on_the_same_employer_does_not_inherit_the_pick(tmp_path):
    """With no clock, the tenant (origin plus first path segment) is all that
    scoped a pick on a board that serves every job of an employer from one path
    prefix, so a later posting opened in the same tab would have been handed the
    earlier job's application. The entry remembers the address it was made on,
    and a page whose path parts from it at an id on both sides is a sibling
    (`jobs/99` against `jobs/100`); a page above or below it is the same posting."""
    out = _tabs(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}],
                sessionStored=_seeded(**{"7": entry(link=POSTING_URL)}),
                steps=[{"tab": 7, "navigate": OTHER_APPLY_URL}])
    on_99, on_100 = out["shots"]
    assert _armed(on_99["regions"]["identity"]) == "app-remembered"
    assert _armed(on_100["regions"]["identity"]) is None


# ---------- the old single key ----------


def test_the_old_single_key_is_adopted_by_the_active_tab_once_and_removed(tmp_path):
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}], api=_API,
                legacySession=entry(at=_now_ms() - 10 * MINUTE_MS))
    assert _armed(out["regions"]["identity"]) == "app-remembered"
    assert out["removals"] == ["widget.session"]
    assert list(out["picks"]) == ["7"]


def test_an_old_key_past_its_thirty_minutes_is_removed_and_not_adopted(tmp_path):
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}], api=_API,
                legacySession=entry(at=_now_ms() - 31 * MINUTE_MS))
    assert _armed(out["regions"]["identity"]) is None
    assert out["removals"] == ["widget.session"]
    assert out["picks"] == {}


def test_an_old_key_from_another_site_is_removed_and_not_adopted(tmp_path):
    out = _load(tmp_path, tabs=[{"id": 7, "url": "https://jobs.lever.co/globex/abc/apply"}],
                api={**_API, "lever.co": _UNMATCHED},
                legacySession=entry(at=_now_ms() - MINUTE_MS))
    assert out["removals"] == ["widget.session"]
    assert out["picks"] == {}


def test_a_profile_with_no_old_key_has_nothing_to_remove(tmp_path):
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}], api=_API)
    assert out["removals"] == []


def test_the_old_key_does_not_overwrite_a_tabs_own_entry(tmp_path):
    """Both can exist for one boot only if a tab already holds a newer entry
    (a panel of another window was first). The newer one is the tab's."""
    mine = entry(applicationId="app-other", link=POSTING_URL)
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}], api=_API,
                sessionStored=_seeded(**{"7": mine}),
                legacySession=entry(at=_now_ms() - MINUTE_MS))
    assert _armed(out["regions"]["identity"]) == "app-other"
    assert out["picks"]["7"]["applicationId"] == "app-other"
    assert out["removals"] == ["widget.session"]


def test_a_cross_tenant_value_on_the_old_key_still_meets_the_tenant_guard(tmp_path):
    out = _load(tmp_path, tabs=[{"id": 7, "url": COHERE_APPLY_URL}], api=_API,
                legacySession=entry(at=_now_ms() - MINUTE_MS, tenant=LIGHTNING_TENANT))
    assert _armed(out["regions"]["identity"]) is None


# ---------- two windows ----------


def _draft_page(url):
    draft = {"id": "app-1", "job_id": "job-1", "base_resume": "ai_ml_engineer",
             "status": "draft", "job_company": "Cohere", "job_title": "Research Engineer 1"}
    return {
        "tabUrls": {"7": LIGHTNING_APPLY_URL, "8": url},
        "page": {"detect_page": _reply({"tier": "B", "form": True, "score": 2}),
                 "extract_job_posting": _reply({"url": url, "title": "Apply", "text": "",
                                                "source": "body"})},
        "api": {**_API, "GET /api/applications?": _reply([draft]),
                "GET /api/applications/app-1": _reply({"pdf_path": None, "status": "draft"})},
    }


def test_two_panels_writing_at_once_do_not_lose_each_others_tab(tmp_path):
    """The map is one value shared by every window's panel, and each change
    reads it whole and writes it whole. A second panel's write that lands between
    this panel's read and its write would be erased by it, so the pair runs under
    one Web Lock, taken by every panel. Here the rival writes tab 99 exactly in
    that gap; both tabs must be there afterwards."""
    out = _tabs(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}],
                rival={"tab": "99", "entry": entry(applicationId="app-rival")},
                **_draft_page(COHERE_APPLY_URL),
                steps=[{"activate": 8}, {"armRival": True, "pickDraft": 0}])
    final = out["shots"][-1]["picks"]
    assert set(final) == {"8", "99"}
    assert final["99"]["applicationId"] == "app-rival"
    assert final["8"]["applicationId"] == "app-1"
    assert set(out["locksAsked"]) == {"maestro.widget.sessions"}


def test_every_change_to_the_map_is_made_under_the_lock(tmp_path):
    """A pick, a closed tab and the boot sweep all go through `updateSessions`."""
    out = _tabs(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}],
                sessionStored=_seeded(**{"7": entry(link=POSTING_URL), "8": entry()}),
                steps=[{"close": 8}])
    assert out["locksAsked"].count("maestro.widget.sessions") >= 2


# ---------- tabs that closed while no panel was listening ----------


def test_the_boot_sweep_drops_the_entries_of_tabs_that_no_longer_exist(tmp_path):
    """A tab closed while the panel was closed never fired `onRemoved` to
    anyone. The panel asks which tabs exist on boot and drops the rest."""
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}], api=_API,
                openTabs=[7, 8],
                sessionStored=_seeded(**{"7": entry(link=POSTING_URL),
                                         "8": entry(applicationId="app-other"),
                                         "9": entry(applicationId="app-gone"),
                                         "10": entry(applicationId="app-gone")}))
    assert set(out["picks"]) == {"7", "8"}
    assert out["allTabQueries"] == [{}]
    assert _armed(out["regions"]["identity"]) == "app-remembered"


def test_the_sweep_is_one_write_and_none_when_every_tab_is_open(tmp_path):
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}], api=_API,
                sessionStored=_seeded(**{"7": entry(link=POSTING_URL), "8": entry()}))
    assert set(out["picks"]) == {"7", "8"}
    assert out["pickWrites"] == []


def test_a_tab_list_that_cannot_be_read_sweeps_nothing(tmp_path):
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}], api=_API,
                openTabsThrow=True,
                sessionStored=_seeded(**{"7": entry(link=POSTING_URL), "9": entry()}))
    assert set(out["picks"]) == {"7", "9"}
    assert _armed(out["regions"]["identity"]) == "app-remembered"
