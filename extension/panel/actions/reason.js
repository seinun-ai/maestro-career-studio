/* Maestro CS Companion — the reasoning step's host ops: what shared/reason-loop.js may do to the run's tab and the
 * backend. One of the concern files behind `panel/actions`; under their rule, nothing here reaches for the browser, the
 * network or a timer: the run door (`store.run`) has the tabs and the clock, `store.api` the backend.
 *
 * POST /api/autofill/reason goes through the panel's ONE api door (the service worker is the only place that talks to the
 * network: backend URL, error shape) on ITS OWN clock, REASON_MS, not the fill loop's 10 s: the backend gives the model 25 s.
 * A late or failed reply is dropped, and the run parks as it would have.
 *
 * VALUE-FREE: `read` hands the loop questions, option words, button words and booleans. The inventory it reads carries
 * what the fields hold (the loop's snapshot drops it before anything is sent), and nothing here keeps it.
 *
 * WHAT THIS FILE PUBLISHES: ns.panelRunReason = { opsFor, enabled, REASON_MS }.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const REASON_MS = 30000;
  const MAX_TABS = 5;
  // The parks a tab to follow can help: the page is not the application (unknown), or the tab left it.
  const FOLLOWS = new Set(["unknown_page", "moved_away"]);

  /** "Think when stuck" on, "Stop after each step" off, full automation on: the only setting the step runs under. */
  const enabled = (facts) => facts?.fullAutomation === true && facts.companionApply?.thinkWhenStuck !== false
    && facts.companionApply?.stopEachStep !== true;

  /** `promise`, or null once `ms` ran out or it failed (never throws). */
  const within = (promise, ms, after) => new Promise((resolve) => {
    const cancel = after(ms, () => resolve(null));
    promise.then((value) => {
      cancel();
      resolve(value ?? null);
    }, () => {
      cancel();
      resolve(null);
    });
  });

  const addressHost = (url) => {
    try {
      return new URL(url).host.toLowerCase();
    } catch {
      return "";
    }
  };

  /** `host`: { fill(fids, scope) → report, rebind(tabId) → bool, isTheApplication(url) → bool, occupied(tabId) → bool,
   * lastFill() → {fid: {status, slot}}, consent() → bool } from actions/run.js. */
  function opsFor(store, record, host) {
    const run = store.run;
    const answer = (frames, frameId) => (Array.isArray(frames) ? frames : []).find((frame) => frame.frameId === frameId)?.result;

    // The tabs of this window that the run may move to: this job's own application, in no other run's hands. Only where a
    // move can help; everywhere else the model is offered none, so a Next-less page never follows a stranger.
    const tabsFor = async (why) => {
      if (!FOLLOWS.has(why)) return [];
      const open = await run.windowTabs().catch(() => []);
      return open.filter((tab) => tab.id !== record.tabId && host.isTheApplication(tab.url) && !host.occupied(tab.id))
        .map((tab) => ({ tabId: tab.id, host: addressHost(tab.url) })).filter((tab) => tab.host).slice(0, MAX_TABS);
    };

    const read = async (why) => {
      const tabs = await tabsFor(why);
      const url = await run.tabUrl(record.tabId);
      // A tab on another site carries none of its page into the snapshot; with no tab to move to there is nothing to ask.
      if (why === "moved_away") return tabs.length ? { frameId: 0, url, summary: null, fields: [], errors: [], tabs, lastFill: {} } : null;
      const picked = ns.queueRun.pickFrame(await run.tabBroadcast(record.tabId, { type: "page_classify" }));
      if (!picked) return null;
      const inventory = await run.tabBroadcast(record.tabId, { type: "fill_inventory", readOnly: true, consentForms: host.consent() });
      const errors = answer(await run.tabBroadcast(record.tabId, { type: "page_errors" }, picked.frameId), picked.frameId);
      return { frameId: picked.frameId, url, summary: picked.result.summary, tabs,
        fields: (Array.isArray(inventory) ? inventory : []).flatMap((frame) => frame.result?.fields ?? []),
        errors: Array.isArray(errors?.items) ? errors.items : [], lastFill: host.lastFill() };
    };

    return {
      now: run.now,
      cancelled: () => record.stopRequested === true,
      // The card shows the line; the footer note (the panel's one live region: the rail is rebuilt on every paint) says it
      // for the run on the tab in view.
      onLine: (text) => {
        record.thinking = String(text).slice(0, 300);
        if (store.read().tabId === record.tabId) store.write({ note: { text: record.thinking } });
        store.render();
      },
      read,
      ask: (body, ms) => within(store.api("/api/autofill/reason", { method: "POST", body: JSON.stringify(body) }),
        Math.min(ms, REASON_MS), run.after),
      fill: (fids, scope) => host.fill(fids, scope),
      // The guarded dismiss: the page refuses any button that asks about submitting (content/page-reader.js).
      dismiss: async (frameId, id) => answer(await run.tabBroadcast(record.tabId, { type: "page_advance", id, dismiss: true }, frameId),
        frameId) ?? { clicked: false },
      follow: (tabId) => host.rebind(tabId),
    };
  }

  ns.panelRunReason = { opsFor, enabled, REASON_MS };
})();
