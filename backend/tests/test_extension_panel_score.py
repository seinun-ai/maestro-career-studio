"""The SCORE stage: every base ranked, and one of them picked.

The ranked list is the RANKING and never the library order; the pick is the
user's answer and completes the stage, is written down scoped to the tenant it
was made on, and comes back on the next page of the wizard; `sessionEntryFrom`
is driven as a table against the widget's own field list, because the two
surfaces read ONE entry; and `scoreAllBases` is driven through its busy,
failure, race and success paths.

THE APPARATUS IS `tests/extension_panel_harness.py` — the faked `chrome`, the
faked document tree, the DOM readers and the spec starters every stage driver
builds on. It is a MODULE rather than a copy per file because a fake that has
to agree with panel.js about what a render leaves behind must not exist five
times; read its header before adding to it.

THE MAP IS `test_extension_panel.py`'s docstring, which lists every file this
subject is now spread across. A section that is not on that list is a section
the next author will not find.
"""
import json
import re
import time

import pytest

from tests.extension_fixtures import (
    COHERE_TENANT,
    GREENHOUSE_ORIGIN,
    LIGHTNING_APPLY_URL,
    LIGHTNING_TENANT,
    POSTING_URL,
)
from tests.extension_harness import js_code, run_node
from tests.extension_panel_harness import (
    EXTENSION,
    LIGHTNING_JOB,
    PANEL_SOURCE,
    SCORE_RESUMES,
    SCORE_ROWS,
    SETTINGS_REPLY,
    _by_class,
    _load,
    _PANEL_FAKES_JS,
    _panel_script,
    _rail_rows,
    _reply,
    _rows,
    _text,
    _walk,
)

# Read for ONE assertion: that the ranked list is fed by the SHARED ranking
# rather than by a second copy that happened to arrive sorted.
SCORE_BODY_CODE = js_code(_panel_script("stages/score.js"))


# ---------- the Score stage: every base ranked, and one of them picked ----------
#
# Three separable things again: what the list SHOWS (the shared ranking, whose
# order is presentation and whose numbers are the backend's), what a pick DOES
# (the store, the ring, and a memory that outlives the page), and what the one
# compute call this surface makes does while it is open.

_SCORE_STAGE_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
const baseRows = () => withClass(REGIONS.rail, "baserow");
main(async () => {
  await settle();
  const loaded = regions();
  let picked = null;
  if (spec.pick !== undefined) {
    // Clicked by INDEX in the rendered order, which is the only order a user
    // has: naming the slug here would let a wrongly ordered list still pass.
    const row = baseRows()[spec.pick];
    if (!row) throw new Error(`no base row at index ${spec.pick}`);
    row.click();
    await settle();
    picked = regions();
  }
  let clicked = null;
  if (spec.click === true) {
    withClass(REGIONS.foot, "cta")[0].click();
    // Synchronous, and deliberately: `scoreAllBases` sets `busy` and paints
    // before its first await, so this is the surface as the user sees it while
    // the scoring is open.
    clicked = regions();
    if (spec.switchTo !== undefined) {
      await onActivated({ tabId: spec.switchTo });
      await settle();
    }
    release();
    await settle();
  }
  emit({ loaded, picked, clicked, settled: regions(), sent, writes });
});
"""


def _score(tmp_path, **spec):
    """Boot on a posting the library already knows, with nothing picked yet —
    which is exactly what the Score stage is."""
    spec.setdefault("tabs", [{"id": 7, "url": POSTING_URL}])
    spec.setdefault("replies", {"read_settings": SETTINGS_REPLY})
    api = {"lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                                  "application": None}),
           "/api/base-resumes": _reply(SCORE_RESUMES),
           "GET /api/ats-scores": _reply(SCORE_ROWS)}
    api.update(spec.pop("api", {}))
    return run_node(_SCORE_STAGE_DRIVER_JS, {**spec, "api": api}, tmp_path,
                    source=PANEL_SOURCE)


def _base_rows(region):
    """Each rendered base row as the user reads it: name, then its chip."""
    return [(_text(row), _by_class(row, "score")[0]["class"])
            for row in _by_class(region, "baserow")]


def test_the_ranked_list_is_the_ranking_and_never_the_library_order(tmp_path):
    """The list is `rankBaseResumes`' answer, rendered.

    The library's own order is the order the resumes were CREATED in, which is
    what made the card's dropdown a blind pick (decisions.js records the cost:
    fast tailor then built on whatever that pick was). Best first, unscored
    last — "not scored yet" is not a bad score, and sorting it as one would be
    the panel inventing a judgement.
    """
    out = _score(tmp_path)
    assert _base_rows(out["loaded"]["rail"]) == [
        ("AI/ML Engineer 72", "score good"),   # 71.8, rounded, and the best
        ("Data Scientist 64", "score"),        # 63.6
        ("Backend Engineer not scored", "score"),
    ]
    # The ranking's own answer is what starts selected, and it says so in a way
    # a screen reader reaches — the tint and the border reach nobody.
    [selected] = [row for row in _by_class(out["loaded"]["rail"], "baserow")
                  if "sel" in row["class"].split()]
    assert _text(selected) == "AI/ML Engineer 72"
    assert selected["attrs"]["aria-checked"] == "true"
    assert [row["attrs"]["role"] for row in _by_class(out["loaded"]["rail"], "baserow")] == [
        "radio", "radio", "radio"]
    # …and the line under it says how much of the list is real, with the engine
    # that produced the numbers: a stored score outlives the scorer that made
    # it, and re-running is the button in the footer.
    assert _by_class(out["loaded"]["rail"], "sub")[0]["text"] == (
        "2 base resumes scored against this JD · engine ats-2.3.0")


def test_the_ranked_list_is_fed_by_the_shared_ranking(tmp_path):
    """A pin, because the ORDER is the one thing a body could get right by
    accident: a list that happened to arrive sorted would pass the test above
    while owning a second, drifting copy of the ranking rule. There is one
    ranking, it lives in `shared/decisions.js`, and the body reads it."""
    body = SCORE_BODY_CODE[SCORE_BODY_CODE.index("function scoreBody("):
                           SCORE_BODY_CODE.index("ns.panelStageScore")]
    assert "rankBaseResumes(ctx.facts.resumes, ctx.facts.scores)" in body


@pytest.fixture(scope="module")
def picked(tmp_path_factory):
    """The second row clicked: `data_scientist`, which is neither the library's
    first row nor the ranking's best. Every assertion below distinguishes the
    user's answer from both."""
    return _score(tmp_path_factory.mktemp("panel_pick"), pick=1)


def test_a_pick_is_the_users_answer_and_the_ranking_never_argues_with_it(picked):
    """Clicking a row is the Score stage's whole point, and the stage completes
    BECAUSE the user answered — not because the numbers arrived.

    `loadBaseScores` moves `baseSlug` by ranking and leaves `baseSelected`
    alone for exactly this reason; the click is what sets it. So the rail moves
    on, the Before ring becomes the picked resume's composite (72 is the
    ranking's answer and 64 is the user's — the two are different numbers on
    purpose), and the list goes with the step it belonged to.
    """
    ring = _by_class(picked["loaded"]["identity"], "ring")[0]["text"]
    assert ring == "72"                                    # before the click
    after = picked["picked"]
    assert _by_class(after["identity"], "ring")[0]["text"] == "64"
    rows = _rows(_rail_rows({"regions": after}))
    assert rows["score"]["state"] == "done"
    assert rows["resume"]["state"] == "active"
    # A done row is a tick and a summary: nothing offers the choice again one
    # line under the panel's own claim that it was made.
    assert _by_class(after["rail"], "baserow") == []


def test_the_pick_is_written_down_scoped_to_the_tenant_it_was_made_on(picked):
    """An ATS wizard is six page loads and each one rebuilds this panel's facts
    from scratch — `resetPageFacts` clears `baseSlug` and `baseSelected` both —
    so a pick that lived only in the store would be made again on every step.

    THE TENANT is what keeps it from travelling: job-boards.greenhouse.io
    serves thousands of companies from one origin, and the 2026-08-16 live
    bleed was a Cohere pick offered on a Lightning posting. It comes from the
    TAB's url, which is the only url this document can ask about.
    """
    assert len(picked["writes"]) == 1
    [write] = picked["writes"]
    # THE SHARED KEY, and since Task 9 that is true of an application-less
    # entry too. It used to land on a key of the panel's own, because the
    # widget's `restoreSession` would have restored `{id: undefined}` as an
    # application and forced `match: "exact"`; that restore now carries the
    # same `if (entry.applicationId)` guard this panel has always had, so one
    # key holds both kinds again and a pick made here reaches the card. See
    # `KEY` in panel.js for the decision.
    assert list(write) == ["widget.session"]
    entry = write["widget.session"]
    assert entry["tenant"] == LIGHTNING_TENANT
    assert entry["origin"] == GREENHOUSE_ORIGIN
    assert entry["baseSlug"] == "data_scientist"
    assert entry["applicationId"] is None
    assert entry["jobId"] == "job-lightning"
    # A live clock, because freshness is one of the guards on the way back in.
    assert abs(entry["at"] - int(time.time() * 1000)) < 120_000


def test_a_pick_made_here_comes_back_on_the_next_page_of_the_wizard(picked, tmp_path):
    """The round trip, through the entry the panel ACTUALLY wrote rather than a
    hand-copied one.

    An ATS wizard is six page loads. The panel outlives them, but its facts do
    not — `resetPageFacts` clears `baseSlug` and `baseSelected` on every one —
    so this is what stops the user picking their resume again on each step.
    """
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}],
                stored={"widget.session": picked["writes"][0]["widget.session"]},
                api={"lightningai": _reply({"match": "none", "job": None,
                                            "application": None}),
                     "/api/base-resumes": _reply(SCORE_RESUMES),
                     "/api/ats-scores": _reply(SCORE_ROWS)})
    # What the apply page itself could not say: which job this is…
    assert _by_class(out["regions"]["identity"], "title")[0]["text"] == "Research Engineer"
    # …and which resume was chosen for it. 64 is the user's pick; 72 is what
    # the ranking would put here if the restore had not marked it as theirs.
    assert _by_class(out["regions"]["identity"], "ring")[0]["text"] == "64"


def test_a_base_picked_on_another_company_is_refused_on_this_one(picked, tmp_path):
    """The same entry, one field different, and it must not come back.

    job-boards.greenhouse.io serves thousands of companies from ONE origin, so
    origin alone cannot scope the memory — the 2026-08-16 live bleed was a
    Cohere pick offered on a Lightning posting. The panel writes the tenant it
    made the pick on; drop it and this entry travels.
    """
    entry = {**picked["writes"][0]["widget.session"], "tenant": COHERE_TENANT}
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}],
                stored={"widget.session": entry},
                api={"lightningai": _reply({"match": "none", "job": None,
                                            "application": None}),
                     "/api/base-resumes": _reply(SCORE_RESUMES),
                     "/api/ats-scores": _reply(SCORE_ROWS)})
    # Nothing is claimed about the page: the host, and an empty ring. Not the
    # other company's job title, and not a resume chosen for their posting.
    assert _by_class(out["regions"]["identity"], "title")[0]["text"] == (
        "job-boards.greenhouse.io")
    assert [ring["text"] for ring in _by_class(out["regions"]["identity"], "ring")] == ["–"]


# ---------- restorableSession: may this memory be used on THIS page? --------
#
# ORPHANED BY R-C AND RE-HOMED HERE. The 13-row table that drove this function
# lived in `test_extension_widget.py`, because the floating card was the first
# surface to read the shared key. Deleting that file left every guard below
# covered only INCIDENTALLY, by panel tests that happen to restore — and a
# reviewer proved it: deleting the clock guard AND the different-posting guard
# left the suite green at 875.
#
# DRIVEN DIRECTLY, with a FROZEN `now`, and both halves of that matter. The
# function is pure and total, so a table is the honest shape; and every
# surviving fixture in the suite stamps `at` from a live clock, which means TTL
# expiry is a branch nothing had ever crossed. A frozen clock is the only way
# to be on both sides of it.

_RESTORABLE_DRIVER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
main(async () => {
  await settle();
  const out = {};
  for (const [name, c] of Object.entries(spec.cases)) {
    // The IDENTITY of what comes back, not just its truthiness: this function
    // returns the entry itself, and a version that built a new object would be
    // a different contract even when every field matched.
    const got = ns.decisions.restorableSession(c.entry, c.scope);
    out[name] = got === null ? null : got.jobId ?? "(no jobId)";
  }
  emit(out);
});
"""

TTL_MS = 30 * 60 * 1000
OTHER_TENANT = "https://job-boards.greenhouse.io/cohere"


def _entry(**over):
    """A pick made on this tenant, one minute ago on the frozen clock."""
    return {
        "origin": GREENHOUSE_ORIGIN,
        "tenant": LIGHTNING_TENANT,
        "at": FROZEN_NOW - 60_000,
        "applicationId": "app-1",
        "jobId": "job-lightning",
        "baseSlug": "ai_ml_engineer",
        **over,
    }


def _scope(**over):
    return {
        "now": FROZEN_NOW,
        "origin": GREENHOUSE_ORIGIN,
        "tenant": LIGHTNING_TENANT,
        "matchedJobId": None,
        "ttlMs": TTL_MS,
        **over,
    }


@pytest.fixture(scope="module")
def restorable(tmp_path_factory):
    cases = {
        # --- the ordinary case, and the two shapes of "nothing to restore" ---
        "fresh_same_tenant": {"entry": _entry(), "scope": _scope()},
        "no_entry": {"entry": None, "scope": _scope()},
        "other_origin": {"entry": _entry(origin="https://jobs.lever.co"),
                         "scope": _scope()},

        # --- THE CLOCK GUARD (`age >= 0`) --------------------------------
        # An entry stamped in the FUTURE is what a clock that jumped backwards
        # leaves behind — a DST change, an NTP correction, a laptop resuming.
        # It is not fresh; it is unreadable, and `age < ttlMs` alone calls it
        # fresh forever because a negative age is less than anything.
        "stamped_in_the_future": {"entry": _entry(at=FROZEN_NOW + 60_000),
                                  "scope": _scope()},
        "stamped_far_in_the_future": {
            "entry": _entry(at=FROZEN_NOW + (365 * 24 * 3600 * 1000)),
            "scope": _scope()},

        # --- TTL EXPIRY, on both sides of the boundary -------------------
        "one_ms_inside_the_ttl": {"entry": _entry(at=FROZEN_NOW - (TTL_MS - 1)),
                                  "scope": _scope()},
        "exactly_at_the_ttl": {"entry": _entry(at=FROZEN_NOW - TTL_MS),
                               "scope": _scope()},
        "past_the_ttl": {"entry": _entry(at=FROZEN_NOW - (TTL_MS + 1)),
                         "scope": _scope()},
        "no_at_at_all": {"entry": _entry(at=None), "scope": _scope()},

        # --- TENANT SCOPING on a shared origin ---------------------------
        "other_tenant_same_origin": {"entry": _entry(tenant=OTHER_TENANT),
                                     "scope": _scope()},
        # …unless the BACKEND names the entry's own job. That is the one
        # signal stronger than the memory, and it is what lets a pre-tenant
        # legacy entry still work.
        "other_tenant_but_backend_confirms": {
            "entry": _entry(tenant=OTHER_TENANT),
            "scope": _scope(matchedJobId="job-lightning")},
        "legacy_entry_with_no_tenant_but_backend_confirms": {
            "entry": _entry(tenant=None),
            "scope": _scope(matchedJobId="job-lightning")},
        "legacy_entry_with_no_tenant_and_no_backend_answer": {
            "entry": _entry(tenant=None), "scope": _scope()},

        # --- THE DIFFERENT-POSTING GUARD ---------------------------------
        # Same origin, same tenant, fresh — and the backend says this page is
        # a DIFFERENT job. A Workday tenant serves every one of its jobs from
        # one origin, so without this the pick made for one posting is offered
        # on the next, which is the most confident wrong thing this surface can
        # say.
        "backend_names_a_different_job": {
            "entry": _entry(), "scope": _scope(matchedJobId="job-other")},
        # `null`/`none` is the backend NOT KNOWING, which is the ordinary case
        # on an apply url and precisely when the memory is worth having.
        "backend_knows_nothing": {"entry": _entry(),
                                  "scope": _scope(matchedJobId=None)},
        # An entry that names no job cannot contradict a match.
        "entry_names_no_job": {"entry": _entry(jobId=None),
                               "scope": _scope(matchedJobId="job-other")},
    }
    return run_node(_RESTORABLE_DRIVER_JS, {"cases": cases},
                    tmp_path_factory.mktemp("restorable"), source=PANEL_SOURCE)


def test_a_fresh_pick_on_its_own_tenant_restores(restorable):
    assert restorable["fresh_same_tenant"] == "job-lightning"
    assert restorable["no_entry"] is None
    assert restorable["other_origin"] is None


def test_an_entry_from_the_future_is_not_fresh_it_is_unreadable(restorable):
    """THE CLOCK GUARD, and the reason it is a RANGE test rather than
    `age < ttlMs`.

    EXPLOIT THIS PIN EXISTS FOR: deleting `age >= 0` left the suite green. A
    negative age is less than every TTL, so a clock that jumped backwards —
    DST, an NTP correction, a laptop resuming from sleep — turns a stale pick
    into one that never expires. The failure is silent and outlives the
    session it belongs to.
    """
    assert restorable["stamped_in_the_future"] is None
    assert restorable["stamped_far_in_the_future"] is None


def test_the_ttl_is_a_boundary_and_the_table_sits_on_both_sides(restorable):
    """Half-open: inside the window restores, ON the boundary does not.

    Every other restore fixture in this suite stamps `at` from a live clock and
    therefore never crosses this at all — the frozen clock here is the whole
    reason these three rows can exist.
    """
    assert restorable["one_ms_inside_the_ttl"] == "job-lightning"
    assert restorable["exactly_at_the_ttl"] is None
    assert restorable["past_the_ttl"] is None
    # `?? 0` inside the function: an entry with no timestamp is age-of-the-epoch
    # old, which is refused rather than treated as brand new.
    assert restorable["no_at_at_all"] is None


def test_a_pick_does_not_cross_tenants_on_a_shared_origin(restorable):
    """The 2026-08-16 live bleed: job-boards.greenhouse.io puts thousands of
    companies on ONE origin, and a Cohere pick restored onto a Lightning
    posting said "Application ready" about an application that does not belong
    to the page.
    """
    assert restorable["other_tenant_same_origin"] is None


def test_the_backend_naming_the_entrys_own_job_outranks_the_tenant(restorable):
    """The escape hatch, and the only thing that may overrule tenant scoping.

    It is what keeps a PRE-TENANT legacy entry usable: those carry no tenant at
    all, so without this every one of them would be refused for good — but only
    when the backend independently confirms the very job the entry names, which
    is a stronger signal than the memory being checked.
    """
    assert restorable["other_tenant_but_backend_confirms"] == "job-lightning"
    assert restorable["legacy_entry_with_no_tenant_but_backend_confirms"] == "job-lightning"
    assert restorable["legacy_entry_with_no_tenant_and_no_backend_answer"] is None


def test_a_pick_is_never_offered_on_a_posting_the_backend_calls_different(restorable):
    """THE DIFFERENT-POSTING GUARD.

    EXPLOIT THIS PIN EXISTS FOR: deleting
    `if (matchedJobId && entry.jobId && matchedJobId !== entry.jobId) return null;`
    left the suite green. A Workday tenant serves every one of its jobs from one
    origin and one tenant slug, so the tenant check above cannot catch this —
    the pick made for one posting would be offered on the next, with a real
    application behind it and nothing on screen saying it is the wrong one.

    The two rows underneath are what stop the guard being written too wide: a
    backend that answered nothing, and an entry that names no job, are both
    "no contradiction" rather than "contradiction".
    """
    assert restorable["backend_names_a_different_job"] is None
    assert restorable["backend_knows_nothing"] == "job-lightning"
    assert restorable["entry_names_no_job"] == "(no jobId)"


_SESSION_ENTRY_DRIVER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
main(async () => {
  await settle();
  const out = {};
  for (const [name, store] of Object.entries(spec.cases)) {
    out[name] = ns.panel.sessionEntryFrom(store, spec.now);
  }
  emit(out);
});
"""

PANEL_JS = (EXTENSION / "panel" / "panel.js").read_text(encoding="utf-8")
FROZEN_NOW = 1_760_000_000_000


@pytest.fixture(scope="module")
def entries(tmp_path_factory):
    cases = {
        "picked": {"url": POSTING_URL, "job": LIGHTNING_JOB, "application": None,
                   "baseSlug": "data_scientist", "pdfReady": False, "touched": False},
        "tailored": {"url": POSTING_URL, "job": LIGHTNING_JOB,
                     "application": {"id": "app-1", "status": "applied"},
                     "baseSlug": "ai_ml_engineer", "pdfReady": True, "touched": True},
        # The SAME store twice, once carrying the panel's in-memory
        # `claimed` flag and once not. The entries must be identical: the
        # flag is a fact this surface renders from, never one it persists.
        "claimed": {"url": POSTING_URL, "job": LIGHTNING_JOB,
                    "application": {"id": "app-1", "status": "draft"},
                    "baseSlug": "ai_ml_engineer", "pdfReady": True, "touched": False,
                    "claimed": True},
        "claimed_absent": {"url": POSTING_URL, "job": LIGHTNING_JOB,
                           "application": {"id": "app-1", "status": "draft"},
                           "baseSlug": "ai_ml_engineer", "pdfReady": True,
                           "touched": False},
        # A tab that has not committed a url. `new URL("")` throws, which is
        # why both `sessionTenant` and `originOf` are total.
        "no_url": {"url": "", "job": None, "application": None, "baseSlug": "x"},
    }
    return run_node(_SESSION_ENTRY_DRIVER_JS, {"cases": cases, "now": FROZEN_NOW},
                    tmp_path_factory.mktemp("panel_entry"),
                    source=PANEL_SOURCE)


def test_the_bridge_entry_is_the_shape_its_writer_declares(entries):
    """ONE key, one shape, ONE writer — and the source pin is what keeps the
    literal below from going stale in silence.

    THIS USED TO BE PINNED AGAINST THE WIDGET. There were two surfaces reading
    one key, so the rule was "the panel writes every field the card reads, by
    the card's names", and the field list was parsed out of the card's own
    `rememberSession`. R-C deleted the card and with it the only reason to
    derive this list from somewhere else: `sessionEntryFrom` in `panel.js` is
    now the sole writer AND the sole reader's counterpart, so the pin reads
    ITS literal. What it still catches is the same failure — a field added to
    the writer and forgotten in the expectation below, which would otherwise
    ride along untested and restore as absent the day something reads it.
    """
    written, closed, _rest = PANEL_JS.partition(
        "function sessionEntryFrom(store, now) {")[2].partition("\n    };\n  }")
    # Anchored on the CLOSING delimiter too. Without it a reindentation leaves
    # the scan running on into the rest of panel.js, and the failure arrives as
    # a diff of whatever it found there rather than as the one sentence that is
    # true: the literal moved.
    assert closed, "sessionEntryFrom's entry literal moved — re-anchor this pin"
    # `[:,]` because `origin` and `tenant` are SHORTHAND properties in that
    # literal — a name-only pattern would silently miss exactly the two fields
    # every guard in `restorableSession` is built on.
    fields = {found.group(1) for found in re.finditer(r"^      (\w+)[:,]", written, re.M)}
    assert fields == set(entries["tailored"]), (
        "sessionEntryFrom writes a different set of fields than this test "
        f"expects: {sorted(fields ^ set(entries['tailored']))}")
    assert entries["tailored"] == {
        "origin": GREENHOUSE_ORIGIN, "tenant": LIGHTNING_TENANT, "at": FROZEN_NOW,
        "applicationId": "app-1", "status": "applied", "jobId": "job-lightning",
        "company": "Lightning AI", "title": "Research Engineer",
        "pdfReady": True, "touched": True,
        "baseSlug": "ai_ml_engineer",
        # REMEMBERED, not recomputed. "Use base as-is" is an answer, and an
        # answer made on the posting is spent on the apply page — a
        # different page load, which is what this entry exists to cross.
        "baseArmed": False,
        # AND NOTHING ELSE. R-C dropped three fields that were written on
        # every save and read by nothing (`attachedBase`, `guidedArmed`,
        # `claimed`) — they existed because a second surface shared this key
        # and its reader wanted the shape. There is one reader now, and the
        # source pin above is what keeps this literal and the writer equal.
    }


def test_provenance_rides_the_application_id_and_never_a_field_of_its_own(entries):
    """Page 2 of a wizard has to know the binding was the user's, or the Job
    row has no door back. It learns that from `applicationId` alone.

    The entry used to carry `claimed` beside it — written by this function,
    read by nothing, because `restoreSession` infers the claim and always
    did. Two sources for one fact is the shape that goes wrong quietly, so
    R-C kept the inference and dropped the field. This test is that decision
    held in place: a store WITH `claimed: true` and a store without it
    produce the same entry, because the flag is not part of the shape.

    The inference itself is pinned behaviourally in
    `test_extension_panel_job.py::test_a_restored_pick_is_still_a_claim`.
    """
    assert "claimed" not in entries["claimed"]
    assert entries["claimed"]["applicationId"] == "app-1"
    assert "claimed" not in entries["picked"]
    # THE REAL PIN: the same store with and without the flag produces the
    # SAME entry, byte for byte. Re-add the field to `sessionEntryFrom` and
    # these two diverge immediately.
    assert entries["claimed"] == entries["claimed_absent"]


def test_an_entry_with_no_application_is_still_a_wholeentry(entries):
    """The Score stage's ordinary case: a base picked BEFORE anything has been
    tailored. `applicationId` is null and every other field still says what it
    knows — the pick, the job it was made for, and the tenant it belongs to."""
    assert entries["picked"]["applicationId"] is None
    assert entries["picked"]["status"] == "draft"
    assert entries["picked"]["baseSlug"] == "data_scientist"
    assert entries["picked"]["tenant"] == LIGHTNING_TENANT


def test_a_url_with_no_tenant_identity_is_not_written_at_all(entries):
    """A refusal, not a default. `restorableSession` compares `entry.tenant` on
    the way back in and a real page never produces null, so an entry written
    without one could never be restored by anything — and writing it would
    replace a usable memory with an unusable one."""
    assert entries["no_url"] is None


def test_score_all_bases_is_the_one_compute_call_and_it_says_what_it_found(tmp_path):
    """The only thing on this surface that asks the backend to COMPUTE, which
    is why it is a button: scoring every base resume against this job on every
    panel open would spend the user's backend on a question they had not asked.

    Its answer IS the scores — `POST` and `GET /api/ats-scores` both return the
    same rows — so nothing is re-read afterwards, which is the one place this
    action diverges from `addJob`'s shape.
    """
    out = _score(tmp_path, click=True, hold=["POST /api/ats-scores"], api={
        "GET /api/ats-scores": _reply([]),
        "POST /api/ats-scores": _reply(SCORE_ROWS)})
    # Before: the job is in the library and NOTHING is scored, which is the
    # state the button exists for. Every row says so in words, never as a zero.
    assert _base_rows(out["loaded"]["rail"]) == [
        ("Backend Engineer not scored", "score"),
        ("Data Scientist not scored", "score"),
        ("AI/ML Engineer not scored", "score"),
    ]
    assert _by_class(out["loaded"]["rail"], "sub")[0]["text"] == (
        "Not scored against this job yet — “Score all bases” runs it.")
    # While it is open: out of reach, and saying so.
    [cta] = _by_class(out["clicked"]["foot"], "cta")
    assert cta["disabled"] is True
    assert cta["class"] == "cta spin"
    # The widget's endpoint and body, unchanged — a panel that invented a route
    # would 404 in the browser and pass here.
    [post] = [msg for msg in out["sent"] if msg["type"] == "api"
              and (msg.get("init") or {}).get("method") == "POST"]
    assert post["path"] == "/api/ats-scores"
    assert json.loads(post["init"]["body"]) == {"job_id": "job-lightning"}
    # After: the answer is the ranking, and the note names what it found.
    settled = out["settled"]
    assert _base_rows(settled["rail"])[0] == ("AI/ML Engineer 72", "score good")
    assert _by_class(settled["identity"], "ring")[0]["text"] == "72"
    [note] = _by_class(settled["foot"], "note")
    assert note["text"] == "Best match: AI/ML Engineer · ATS 72."
    assert note["class"] == "note"
    # Scoring is not answering: the stage still asks, because the pick is the
    # user's and the numbers only make it an informed one.
    assert _rows(_rail_rows({"regions": settled}))["score"]["state"] == "active"


def test_a_score_that_fails_hands_the_button_back_and_says_why(tmp_path):
    """A failed compute costs the ranking and nothing else. The panel must not
    be left with its one control permanently pressed."""
    out = _score(tmp_path, click=True, api={"GET /api/ats-scores": _reply([])})
    [note] = _by_class(out["settled"]["foot"], "note")
    assert note["text"] == "the backend is unreachable"
    assert note["class"] == "note error"
    [cta] = _by_class(out["settled"]["foot"], "cta")
    assert cta["disabled"] is False
    assert cta["class"] == "cta"


def test_a_score_that_lands_after_you_switch_tabs_paints_nothing(tmp_path):
    """The generation rule applied to the second action, which is where it is
    easiest to forget it a second time: a compute call feels like something the
    user is waiting for rather than a round trip like any other. It is not —
    they are free to leave while it is open, and there is one store for its
    answer to land in."""
    out = _score(tmp_path, click=True, hold=["POST /api/ats-scores"], switchTo=42,
                 tabUrls={"42": "chrome://settings"},
                 api={"GET /api/ats-scores": _reply([]),
                      "POST /api/ats-scores": _reply(SCORE_ROWS)})
    settled = out["settled"]
    assert "Best match" not in _text(settled["foot"])
    assert "ai_ml_engineer" not in json.dumps(settled)
    # The empty ring: a settings tab has no base score, and certainly not the
    # posting's.
    assert [ring["text"] for ring in _by_class(settled["identity"], "ring")] == ["–"]
    assert _by_class(settled["rail"], "baserow") == []


def test_a_score_that_FAILS_after_you_switch_tabs_paints_nothing_either(tmp_path):
    """`scoreAllBases`' failure limb, driven for itself.

    Two of three (see `addJob`'s twin for why the ladder being one function is
    not a substitute for driving each action). A failed compute is the cheapest
    of the three to get wrong and the easiest to excuse — "it only writes a
    note" — but the note is the panel's one line about the page in front of the
    user, and this page is a settings tab that asked for nothing.
    """
    out = _score(tmp_path, click=True, hold=["POST /api/ats-scores"], switchTo=42,
                 tabUrls={"42": "chrome://settings"},
                 api={"GET /api/ats-scores": _reply([]),
                      "POST /api/ats-scores": {"ok": False, "error": "the scorer fell over"}})
    settled = out["settled"]
    assert "the scorer fell over" not in json.dumps(settled)
    # Nothing red, and nothing still spinning: `busy` belongs to the tab that
    # asked, and the early return leaves this one's render untouched.
    assert [n for n in _walk(settled["foot"]) if "error" in str(n.get("class"))] == []
    assert [n for n in _walk(settled["foot"]) if "spin" in str(n.get("class"))] == []


# The state the merge exists for: a job with a TAILORED application whose base
# has not been picked. `stageFor` puts that on Score — the pick is missing, and
# nothing about having tailored once answers it — so the Score-all button is in
# reach on a page that is already showing a Before -> After pair.
TAILORED_ROW = {"target_type": "application", "target_id": "app-1",
                "phase": "tailored", "composite": 84.2, "engine_version": "ats-2.3.0"}
RESCORED_ROWS = [
    {"target_type": "base_resume", "target_id": "data_scientist", "phase": "base",
     "composite": 63.6, "engine_version": "ats-2.3.0"},
    {"target_type": "base_resume", "target_id": "ai_ml_engineer", "phase": "base",
     "composite": 75.4, "engine_version": "ats-2.3.0"},
]


def test_scoring_the_bases_again_never_costs_the_tailored_ring(tmp_path):
    """`card.scores` has TWO consumers where the widget's had one.

    `POST /api/ats-scores` runs `score_all_bases`, which returns BASE rows only
    (backend/app/services/ats_score.py:128 — one `score_target(…,
    "base_resume", …)` per slug). The GET returns `latest_scores` for every
    target on the job, the tailored application included. The two are
    schema-equal and the POST's answer is a SUBSET — which is exactly why "the
    POST's answer IS the scores" reads true and is not: the ranking is one
    reader of that array and `renderAts`' After ring is the other. Replacing it
    wholesale deletes the tailored composite and puts "tailor to raise it"
    beside an application that already was, until the next navigation.
    """
    out = _score(tmp_path, click=True, api={
        "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                               "application": {"id": "app-1", "status": "draft"}}),
        "/api/applications/app-1": _reply({"pdf_path": "renders/app-1.pdf",
                                           "status": "draft"}),
        "GET /api/ats-scores": _reply([*SCORE_ROWS, TAILORED_ROW]),
        "POST /api/ats-scores": _reply(RESCORED_ROWS)})
    assert [ring["text"] for ring in _by_class(out["loaded"]["identity"], "ring")] == [
        "72", "84"]
    settled = out["settled"]
    # The base number moved, because that is what was re-scored…
    assert _base_rows(settled["rail"])[0] == ("AI/ML Engineer 75", "score good")
    # …and the tailored one survived, because nothing re-scored it.
    assert [ring["text"] for ring in _by_class(settled["identity"], "ring")] == ["75", "84"]
    assert _by_class(settled["identity"], "delta")[0]["text"] == "+9"
    assert "tailor to raise it" not in _text(settled["identity"])


def test_a_library_scored_by_two_engines_names_neither(tmp_path):
    """The provenance line is one engine or none.

    A `config_version` move leaves stored scores from the old scorer beside
    fresh ones from the new — this project's recurring state, and the one the
    line exists to warn about. Printing the first row's version would put one
    scorer's name on numbers that came from both, which is wrong in exactly the
    case it was added for. The count stays; the claim goes.
    """
    mixed = [SCORE_ROWS[0], {**SCORE_ROWS[1], "engine_version": "ats-2.2.0"}]
    out = _score(tmp_path, api={"GET /api/ats-scores": _reply(mixed)})
    assert _by_class(out["loaded"]["rail"], "sub")[0]["text"] == (
        "2 base resumes scored against this JD")


def test_the_engine_is_read_off_the_rows_the_sentence_counts(tmp_path):
    """The two halves of that line describe ONE set.

    `card.scores` is wider than the ranking: it carries the tailored
    application's row, and base rows for slugs that have since left the library
    — a retired resume keeps its score row, and `/api/base-resumes` stops
    listing it. Those rows are not counted, are not rendered, and cannot be
    picked, so an engine scanned over them would refuse to name a scorer
    because of a number nobody can see. Here every VISIBLE row agrees, and the
    line says so.
    """
    out = _score(tmp_path, api={"GET /api/ats-scores": _reply([
        *SCORE_ROWS,
        # Retired from the library, still scored, and scored by an older
        # engine — the exact row a wider scan would trip over.
        {"target_type": "base_resume", "target_id": "product_analyst",
         "phase": "base", "composite": 55.0, "engine_version": "ats-2.2.0"},
        {**TAILORED_ROW, "engine_version": "ats-2.1.0"},
    ])})
    assert _by_class(out["loaded"]["rail"], "sub")[0]["text"] == (
        "2 base resumes scored against this JD · engine ats-2.3.0")
    # …and the retired resume is not in the list either: the ranking is over
    # the LIBRARY, and a row for a resume the user cannot pick is not a row.
    assert [name for name, _chip in _base_rows(out["loaded"]["rail"])] == [
        "AI/ML Engineer 72", "Data Scientist 64", "Backend Engineer not scored"]


