/* Maestro CS Companion — the queued run's host: one job, in one tab, driven by shared/queue-run.js.
 *
 * One of the concern files behind `ns.panelActions`; `panel/actions.js` is the joiner and carries
 * the whole contract. This is the run's HOST (design Part 1): `shared/queue-run.js` is the state
 * machine and touches nothing, so everything it needs from a browser arrives here as a dep, built
 * from the handle's `run` door (`actionStore().run` in panel.js, the only place that reaches
 * `chrome.tabs` or a timer). Task 19 grows this file into the Queue view's scheduler; today it is
 * ONE record in the CURRENT tab, started by `startRun`.
 *
 * THE RULES, restated because a file that only POINTS at them half-remembers them:
 * - NOTHING HERE REACHES FOR ANYTHING: no `card`, no `chrome`, no `document`, no `fetch`, no
 *   timers. A tab, a clock, a timer and the page fan-out are `store.run`'s.
 * - A RUN IS NOT THE ACTIVE PAGE. Its record is pinned to its own tab and lives in `card.runs`; a
 *   tab switch or a generation change neither ends nor cancels it (the user's own Autofill keeps
 *   its generation guard, and a run does not use it). What ends a run is Stop (`stopRequested`,
 *   which `cancelled(record)` reads, and `fill_cancel` to the run's own tab), a wall, or a
 *   finished application.
 * - SUBMIT IS NEVER CLICKED, and nothing in this file can ask for it: the only page presses are the
 *   driver's Next (and the posting's Apply under its narrow rule). The "applied" mark is the
 *   Companion RECORDING a Submit the user pressed, seen as a confirmation page, 8 s later and
 *   undoable; it clicks nothing.
 * - NO PASSWORD IS HERE. The saved login is fetched and typed inside `pageOps().signIn`; the
 *   record, the card, the receipt, the trace and every sentence below are built from values that
 *   never include it.
 *
 * THE RECORD is plain data (the driver's header lists its fields). The host adds: `startTabId` (the
 * tab the run began in), `stopRequested`, `pages` (`{n, filled}` per finished page), `progress`
 * (`{done, total}` of the page in hand), `flags` (the last receipt's "Check before you submit"),
 * `parkedAt`/`yourMs` (the user's time), `learned` (what Resume saved), and for the auto-mark
 * `markAt`, `noAutoMark`, `markNote`, `markConflict` and `timeCounted`. Answers never live on it: the receipt's
 * memory of what it posted (values) and Undo's previous profile values stay in this file's maps,
 * which neither the card nor `chrome.storage.session` ever sees.
 *
 * WHAT THIS FILE PUBLISHES: ns.panelActionsRun = { startRun, stopRun, resumeRun, skipRun, closeRun,
 * undoLearned, undoMark, markApplied, restoreRuns }.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const { samePosting } = ns.decisions;

  // 8 s between the confirmation page and the mark, so an Undo is a real chance (`submitted` is
  // terminal on the server: the delay is the undo, not a reversal).
  const AUTO_MARK_MS = 8000;
  // A ready tab's confirmation page may draw a beat after its address changes.
  const CONFIRM_POLLS = 5;
  const CONFIRM_POLL_MS = 1000;
  const LOAD_WAIT_MS = 30000;
  const LOAD_POLL_MS = 250;
  const TERMINAL = new Set(["stopped", "applied"]);
  // The job boards the page reader calls board-native (content/page-reader.js BOARD_HOST).
  const BOARD_HOST = /(^|\.)(linkedin|indeed)\.com$/i;
  const hostOf = (url) => {
    try {
      return new URL(url).hostname;
    } catch {
      return "";
    }
  };
  // A record that was mid-air when the panel closed is not running any more.
  const IN_AIR = new Set(["waiting", "opening", "signing_in", "filling", "advancing"]);
  const MAX_PHRASE = 300;
  // What the fill report counts as filled on a page (the engine wrote it and checked it).
  const WROTE = new Set(["verified", "closest", "assumed"]);
  // The outcomes of a field the engine left that join the known-gaps list.
  const LEFTOVER = new Set(["cannot_operate", "unconfirmed"]);

  // The host's memory, per panel: not on the record, not in storage. `facts` is what the run's
  // own store reads (and the receipt's `receiptSeen`, which holds answers); `undo` is the profile
  // values a Resume replaced; `phrases` the confirmation words the last read matched.
  const state = {
    driving: new Set(), checking: new Set(), marking: new Set(),
    facts: new Map(), undo: new Map(), phrases: new Map(), timers: new Map(), count: 0,
    // Per run: where the confirmation page was SEEN ({host, path}), kept apart from the tab, which
    // may have moved on or closed by the time the mark is made.
    confirmed: new Map(),
    // This panel's own mark on the records it owns. Every window's panel hears every tab, and only
    // the one that owns a ready record may arm its auto-mark (two would each post it, and an Undo in
    // one would not reach the other's timer).
    lease: `panel-${Math.random().toString(36).slice(2)}`,
    // Per run: the fids the page watches for the user's hands, and the gap rows already posted.
    watching: new Map(), gapped: new Map(),
  };

  const tabOf = (record) => record.tabId ?? record.startTabId;
  const live = (record) => !TERMINAL.has(record.status);
  const warn = (what) => (err) => console.warn(`[maestro-cs] ${what}:`, err);

  function recordById(store, id) {
    return store.read().runs.find((record) => record.id === id) ?? null;
  }

  /** Tell the panel the record changed: mirrored to session storage (a reopened panel shows where
   * each run got to) and painted. */
  function persist(store) {
    store.run.save(store.read().runs).catch(warn("could not keep the run"));
    store.render();
  }

  function newRecord(seed, tabId) {
    state.count += 1;
    return {
      id: `run-${Date.now().toString(36)}-${state.count}`, lease: state.lease,
      proposalId: seed.proposalId, jobId: seed.jobId ?? null, applicationId: seed.applicationId ?? null,
      company: seed.company ?? null, location: seed.location ?? null, title: seed.title ?? null,
      baseSlug: seed.baseSlug ?? null,
      openUrl: seed.openUrl, startTabId: tabId, tabId: null,
      status: "waiting", why: null, open: [], hosts: [], seen: [], step: 0, fingerprint: null,
      startedAt: null, readyAt: null, yourMs: 0, flowOrigin: null,
      stopRequested: false, pages: [], progress: null, flags: [], parkedAt: null, learned: null,
      markAt: null, noAutoMark: false, markNote: null, markConflict: false,
    };
  }

  // ---------- the run's own view of its page ----------

  /** The store the fill's helpers (`recordReceipt`, `autoAttachResume`) read and write, bound to
   * the run's tab and held in memory. It is `fill.js`'s `store` contract with a record's facts in
   * place of the card, which is why those functions work unchanged. */
  function runStore(store, record) {
    if (!state.facts.has(record.id)) {
      state.facts.set(record.id, {
        url: "", busy: null, fileInputs: 0, attached: null, autoAttach: null, receiptSeen: null,
        consentForms: false, pdfReady: true,
        job: { id: record.jobId, company: record.company, location: record.location, title: record.title },
        application: { id: record.applicationId, status: "draft" }, baseSlug: record.baseSlug,
      });
    }
    const facts = state.facts.get(record.id);
    const host = store.run;
    return {
      read: () => ({ ...facts, tabId: record.tabId }),
      write: (patch) => Object.assign(facts, patch),
      render: store.render,
      // A run is not a page binding: nothing makes it stale but its own Stop.
      token: () => 0,
      current: () => true,
      api: store.api,
      broadcast: (message) => host.tabBroadcast(record.tabId, message),
      prepare: () => host.prepare(record.tabId),
      attachPdf: (path, filename, expect, resumeOnly = false) =>
        host.attachPdf(record.tabId, path, filename, expect, resumeOnly),
      // The top frame's detect, else the first frame that holds a form (an embedded application).
      detectUploads: async () => {
        let verdict = await host.tabFrame0(record.tabId, { type: "detect_page" }).catch(() => null);
        if (verdict?.form !== true) {
          const frames = await host.tabBroadcast(record.tabId, { type: "detect_page" }).catch(() => []);
          verdict = frames.map((frame) => frame.result).find((one) => one?.form === true) ?? verdict;
        }
        if (!verdict) return null;
        return { fileInputs: Number(verdict.fileInputs) || 0,
                 uploads: Array.isArray(verdict.uploads) ? verdict.uploads : null };
      },
      recipes: store.recipes,
      build: store.build,
    };
  }

  // ---------- the deps the driver is built from ----------

  /** The tab to read and press in: the run's own, opened or reused. A run started on the current
   * tab keeps it WITHOUT navigating while the page is the same posting (or the job the backend
   * matched), so a user part-way through a form, on /apply/step2, keeps their progress. Anything
   * else navigates this tab and waits, bounded and abandonable, until the page is readable.
   * The driver records the hosts it reaches itself. */
  async function openTab(store, record, url, stop) {
    const host = store.run;
    const tabId = record.startTabId;
    const here = await host.tabUrl(tabId).catch(() => "");
    const facts = store.read();
    // The backend's match is honoured wherever the page is: a posting saved from a board, with the run
    // started on the employer's own ATS form, is a different origin from the saved link and still the
    // job. A job BOARD's page is the exception, because there the run's move is to the employer's link.
    const matched = facts.tabId === tabId && facts.job?.id === record.jobId && Boolean(record.jobId)
      && !BOARD_HOST.test(hostOf(here));
    const stays = Boolean(here) && (samePosting(url, here) || matched);
    if (!stays) {
      await host.navigate(tabId, url);
      const until = host.now() + LOAD_WAIT_MS;
      while (!stop() && host.now() < until && !(await host.loaded(tabId))) await host.sleep(LOAD_POLL_MS);
    }
    // The one sanctioned injection: a tab open since before the extension last reloaded has no
    // content scripts, and classify would find nothing to read.
    await host.prepare(tabId).catch(warn("could not prepare the run's tab"));
    return tabId;
  }

  /** What a classify read tells the host: the origin of the frame that holds the form (vouched, so
   * a form in an embedded frame takes the fill, `withFlowOrigin`), the words a confirmation page
   * matched, and where it was (the two things the auto-mark sends of the page: only a page of a host
   * the run reached, in the top document, counts as where). */
  function noteFrames(store, record, frames) {
    const picked = ns.queueRun.pickFrame(frames);
    const summary = picked?.result?.summary;
    if (!summary) return frames;
    let origin = null;
    try {
      origin = new URL(picked.url).origin;
    } catch {
      // A frame with no address: nothing to vouch for.
    }
    if (origin && /^https?:/.test(origin) && (summary.fillable ?? 0) > 0) store.run.vouch(record.tabId, origin);
    if (typeof summary.confirmationPhrase === "string") {
      state.phrases.set(record.id, summary.confirmationPhrase.slice(0, MAX_PHRASE));
      const where = picked.result.top === true ? addressOf(picked.url) : null;
      if (where && (record.hosts ?? []).includes(where.host)) state.confirmed.set(record.id, where);
    }
    return frames;
  }

  function depsFor(store, record) {
    const host = store.run;
    const ops = ns.queueRun.pageOps({
      broadcast: host.tabBroadcast, frame0: host.tabFrame0, api: store.api,
      tabUrl: host.tabUrl, sleep: host.sleep, now: host.now,
    });
    return {
      ...ops,
      classify: async (tabId) => noteFrames(store, record, await ops.classify(tabId)),
      openTab: (url, stop) => openTab(store, record, url, stop),
      tabUrl: host.tabUrl,
      sleep: host.sleep,
      now: host.now,
      save: () => store.run.save(store.read().runs).catch(warn("could not keep the run")),
      onUpdate: (one) => onUpdate(store, one),
      cancelled: (one) => one.stopRequested === true,
      fill: (one, { limits }) => fillPage(store, one, limits),
    };
  }

  /** Every change the driver makes: the user's time starts when it parks, a finished run stops being
   * vouched for, and the panel paints. */
  function onUpdate(store, record) {
    if (record.status === "parked" && record.parkedAt == null) record.parkedAt = store.run.now();
    if (record.status === "parked" && record.why === "open_questions") watchParked(store, record);
    if (TERMINAL.has(record.status)) store.run.unvouch(tabOf(record));
    store.render();
  }

  // ---------- learning from the user's fix, and the known-gaps list (design Part 8.2-8.3) ----------

  /** A park on open questions: have the page watch what the user does to those fields, so Resume can
   * tell which of the engine's moves they used. Once per set of fields; the page answers with event
   * types and a few key names, never what was typed (content/recipes.js). */
  function watchParked(store, record) {
    const fids = (record.open ?? []).map((one) => one.fid).filter((fid) => typeof fid === "string");
    const key = fids.join(",");
    if (!fids.length || state.watching.get(record.id) === key) return;
    state.watching.set(record.id, key);
    store.run.tabBroadcast(tabOf(record), { type: "fill_watch", fids }).catch(warn("could not watch the parked fields"));
  }

  /** The gap rows not posted yet for this run, marked posted. Each row posted adds one to the stored
   * count, so a row goes once per field and outcome and is never sent again, whatever happens. */
  function freshGaps(record, rows) {
    const done = state.gapped.get(record.id) ?? new Set();
    state.gapped.set(record.id, done);
    return rows.filter((row) => {
      if (done.has(row.key)) return false;
      done.add(row.key);
      return true;
    }).map(({ gap }) => gap);
  }

  /** Hand rows to the service worker, which posts them only for a user who turned the fill log on. */
  function postGaps(store, record, rows) {
    const gaps = freshGaps(record, rows);
    if (gaps.length) store.run.gaps(gaps);
  }

  const bare = (family) => String(family).replace(/^f:/, "");

  /** The engine's leftovers on a page (a widget it could not operate, a value the page took back) as
   * gap rows: the trace is value-free and already names the family, shape and outcome of each. */
  function leftovers(trace) {
    const host = typeof trace?.host === "string" ? trace.host : "";
    return (trace?.fields ?? []).filter((one) => LEFTOVER.has(one.outcome) && typeof one.family === "string")
      .map((one) => ({ key: `${one.fid}:${one.outcome}`,
                       gap: { family: bare(one.family), host, shape: one.shape, outcome: one.outcome } }));
  }

  /** Resume after the user fixed parked fields by hand: ask the page what they did to each (the
   * watcher's report), and for every field that now holds a value (the user's hand on it was seen, or
   * the page marked it touched) post a `user_fixed` gap. A move the engine knows teaches the recipe
   * book for that site (a demonstration: probation, never trusted from one); no known move is a
   * `missing_technique` gap. The recipe book is local and is taught whatever the fill log says; the
   * gap rows are the service worker's to gate. Never throws into Resume. */
  async function learnFromFix(store, record, fields, host) {
    const watched = (record.open ?? []).map((one) => one.fid);
    state.watching.delete(record.id);
    if (!watched.length) return;
    const frames = await host.tabBroadcast(tabOf(record), { type: "fill_watch_report", fids: watched });
    const seen = Object.assign({}, ...frames.map((frame) => frame.result).filter((one) => one && typeof one === "object"));
    const pageHost = hostOf(await host.tabUrl(tabOf(record)).catch(() => ""));
    const rows = [];
    const lessons = [];
    for (const fid of watched) {
      const got = seen[fid];
      const field = fields.get(fid);
      if (!got?.family || !got.site || !field || field.policyBlocked === true || !answerText(field.committed)) continue;
      const gestures = Array.isArray(got.gestures) ? got.gestures : [];
      if (field.touched !== true && !gestures.length) continue;
      const gap = (outcome) => ({ key: `${fid}:${outcome}`,
                                  gap: { family: bare(got.family), host: pageHost, shape: field.shape, outcome } });
      rows.push(gap("user_fixed"));
      const moves = movesOf(gestures);
      if (!Object.keys(moves).length) rows.push(gap("missing_technique"));
      const teach = teachable(moves);
      if (Object.keys(teach).length) lessons.push({ recipe: { family: got.family, site: got.site }, moves: teach });
    }
    if (lessons.length) await store.recipes().recordDemonstration(lessons);
    postGaps(store, record, rows);
  }

  /** The recipe book's moves a gesture list names: `open:keys` is `{open: "keys"}`. Only the words
   * the book knows survive. */
  function movesOf(gestures) {
    const moves = {};
    for (const one of gestures) {
      const [axis, move] = String(one).split(":");
      if (ns.recipeBook.AXES[axis]?.includes(move)) moves[axis] = move;
    }
    return moves;
  }

  /** Of those moves, the ones worth teaching: the generic move (the first of its axis) is what the
   * engine does anyway, and a recipe is never judged by it. */
  function teachable(moves) {
    return Object.fromEntries(Object.entries(moves).filter(([axis, move]) => move !== ns.recipeBook.AXES[axis][0]));
  }

  /** The fill of one page, pinned to the run's tab: its job and application from the record, the
   * run's limits, and a `cancelled` that only the run's own Stop moves. Posts the answer receipt,
   * tries the resume attach as Autofill does, and sends the same value-free telemetry and trace. */
  async function fillPage(store, record, limits) {
    const host = store.run;
    const rs = runStore(store, record);
    const url = await host.tabUrl(record.tabId);
    rs.write({ url });
    const stopped = () => record.stopRequested === true;
    const finished = new Set();
    let total = 0;
    let auto = null;
    record.progress = { done: 0, total: 0 };
    const report = await ns.fillLoop.runFill({
      broadcast: async (message) => {
        const frames = await host.tabBroadcast(record.tabId, message);
        // The page's field count is the length of the page: a full inventory (not a peek, not the
        // receipt's read) names every field the loop is about to work.
        if (message.type === "fill_inventory" && !message.peek && !message.readOnly) {
          total = frames.reduce((n, frame) => n + (frame.result?.fields?.length ?? 0), 0);
          record.progress = { done: finished.size, total };
          store.render();
        }
        return frames;
      },
      api: store.api,
      recipes: store.recipes(),
      cancelled: stopped,
      beforeSweep: async () => {
        auto = await ns.panelRunAttach.attach(rs, 0, stopped);
        return ns.panelRunAttach.wrote(auto) ? ns.panelRunAttach.settleMs : 0;
      },
      onProgress: (update) => {
        if (update.phase !== "field") return;
        finished.add(update.fid);
        record.progress = { done: finished.size, total: Math.max(total, finished.size) };
        store.render();
      },
    }, {
      applicationId: record.applicationId,
      base: record.applicationId ? null : record.baseSlug,
      sourceHint: ns.fillLoop.sourceHintOf(url),
      pageUrl: ns.fillLoop.pageUrlOf(url),
      limits,
    });
    ns.panelRunAttach.land(rs, auto);
    rs.write({ consentForms: report.consentForms === true });
    const flags = await ns.panelRecordReceipt(rs, rs.read(), 0,
      (frames) => ns.receipt.fromLoop(report, frames, auto, rs.read().receiptSeen?.fids),
      { consentForms: report.consentForms === true });
    if (flags !== null) record.flags = flags;
    host.telemetry("loop_fill", ns.fillLoop.buildLoopObservations(report), url);
    if (report.trace) store.trace(report.trace);
    postGaps(store, record, leftovers(report.trace));
    if (!report.stopped) {
      const filled = report.fields.filter((row) => WROTE.has(row.status)).length;
      const n = (record.step ?? 0) + 1;
      record.pages = [...(record.pages ?? []).filter((page) => page.n !== n), { n, filled }];
    }
    return report;
  }

  // ---------- starting, stopping, resuming ----------

  /** Run the driver on a record to its next stop. One drive at a time per record. */
  async function drive(store, record) {
    if (state.driving.has(record.id)) return record;
    state.driving.add(record.id);
    try {
      await ns.queueRun.drive(record, depsFor(store, record));
    } finally {
      state.driving.delete(record.id);
    }
    afterDrive(store, record);
    persist(store);
    return record;
  }

  function afterDrive(store, record) {
    if (record.status === "confirming") armAutoMark(store, record);
    // A tab closed under a drive ends it through Stop's own path (`why: "user"`); the reason is the tab.
    if (record.tabClosed) record.why = "tab_closed";
  }

  /** Apply to one job in the CURRENT tab, from its employer link through every page to the review.
   * `seed` is `{proposalId, jobId, applicationId, company, location, title, baseSlug, openUrl}`; the Job
   * step's Apply (Task 20a) builds it after the job is queued and its resume is ready. A tab with a
   * run that has not finished is not started again. */
  async function startRun(store, seed) {
    const facts = store.read();
    const tabId = facts.tabId;
    if (tabId === null || !seed?.proposalId || !seed?.openUrl) return null;
    if (facts.runs.some((one) => tabOf(one) === tabId && live(one))) return null;
    const record = newRecord(seed, tabId);
    store.write({ runs: [...facts.runs.filter((one) => tabOf(one) !== tabId), record] });
    persist(store);
    return drive(store, record);
  }

  /** Stop: the flag `cancelled(record)` reads, AND `fill_cancel` to the run's own tab, so a fill in
   * flight ends at once instead of after its field's clock. */
  function stopRun(store, id) {
    const record = recordById(store, id);
    if (!record || !live(record) || record.stopRequested) return;
    record.stopRequested = true;
    persist(store);
    store.run.tabBroadcast(tabOf(record), { type: "fill_cancel" }).catch(warn("could not stop the fill"));
  }

  /** Skip this job: ends the record and nothing else. The job stays Queued (no request is made;
   * skipping or rejecting it on the server is the user's, in the web app). */
  function skipRun(store, id) {
    const record = recordById(store, id);
    if (!record || record.status !== "parked") return;
    Object.assign(record, { status: "stopped", why: "user", stopRequested: true, open: [], parkedAt: null });
    // The page stops watching the fields this run parked on (an empty watch replaces the last).
    state.watching.delete(record.id);
    store.run.tabBroadcast(tabOf(record), { type: "fill_watch", fids: [] }).catch(warn("could not stop watching"));
    store.run.unvouch(tabOf(record));
    persist(store);
  }

  /** Done: take a finished or stopped record off the tab, so the page's own steps show again. A
   * ready one too (the user is not submitting this job): it ends as stopped first, so a read of the
   * tab already in flight cannot start a countdown for a record that is gone. Nothing is written. */
  function closeRun(store, id) {
    const record = recordById(store, id);
    if (!record || (live(record) && record.status !== "ready")) return;
    if (record.status === "ready") {
      state.timers.get(record.id)?.();
      state.timers.delete(record.id);
      Object.assign(record, { status: "stopped", why: "user", stopRequested: true, markAt: null });
    }
    state.facts.delete(record.id);
    state.undo.delete(record.id);
    state.phrases.delete(record.id);
    state.confirmed.delete(record.id);
    state.watching.delete(record.id);
    state.gapped.delete(record.id);
    store.write({ runs: store.read().runs.filter((one) => one.id !== id) });
    store.run.unvouch(tabOf(record));
    persist(store);
    if (store.read().tabId === tabOf(record)) store.loadContext(store.token());
  }

  /** The text a field holds, as an answer to save; empty when it holds none (a lone checkbox's
   * yes/no is a tick, not an answer to a question). */
  function answerText(value) {
    if (Array.isArray(value)) return value.map((one) => String(one).trim()).filter(Boolean).join(", ");
    if (typeof value === "string") return value.trim();
    if (typeof value === "number") return String(value);
    return "";
  }

  /** What the user typed while the run waited, read once from the page: the answer record gets it as
   * `you` (the receipt), and every open question they answered becomes a standing answer, always
   * (owner, 2026-10-11: no checkbox), except prose boxes and anything the policy never fills. */
  async function afterTyping(store, record) {
    const rs = runStore(store, record);
    const host = store.run;
    try {
      const frames = await host.tabBroadcast(record.tabId,
        { type: "fill_inventory", readOnly: true, consentForms: rs.read().consentForms === true });
      const seen = rs.read().receiptSeen?.fids;
      await ns.panelRecordReceipt(rs, rs.read(), 0, () => ns.receipt.fromEdits(frames, seen),
        { inventory: false, consentForms: rs.read().consentForms === true });
      const fields = new Map(frames.flatMap((frame) => frame.result?.fields ?? []).map((one) => [one.fid, one]));
      // The fix itself, apart from the answers: what the user did teaches the recipe book.
      await learnFromFix(store, record, fields, host).catch(warn("could not learn from the fix"));
      const items = [];
      for (const one of record.open ?? []) {
        const field = fields.get(one.fid);
        const answer = answerText(field?.committed);
        if (!field || field.touched !== true || field.multiline === true || field.policyBlocked === true
          || ns.isPolicyBlocked(one.question) || !answer) continue;
        items.push({ label: one.question, answer });
      }
      if (!items.length) return;
      try {
        state.undo.set(record.id, await ns.panelLearn.learnAnswers(store, items,
          { company: record.company, location: record.location }));
        record.learned = { count: items.length, undone: false, failed: false };
      } catch (err) {
        console.warn("[maestro-cs] learning the answers failed:", err);
        record.learned = { count: 0, undone: false, failed: true };
      }
    } finally {
      // The read failed before the report was asked for: the page is not left watching.
      if (state.watching.has(record.id)) {
        state.watching.delete(record.id);
        host.tabBroadcast(tabOf(record), { type: "fill_watch", fids: [] }).catch(warn("could not stop watching"));
      }
    }
  }

  /** Resume: the user did what the card asked. An open-questions park reads what they typed first;
   * a wall just goes round again. The driver re-reads the page, refills, and moves on or stops.
   * The record turns `filling` BEFORE the first await: until the driver takes it, the card would
   * otherwise still read parked, with Resume and Skip pressable, while the page is read and the
   * receipt posted (a second Resume would post it twice and overwrite Undo's memory; a Skip would
   * be driven over). `why` and `open` stay, since the read below and the driver's park-aware rules
   * (a user who navigated) go by them. */
  async function resumeRun(store, id) {
    const record = recordById(store, id);
    if (!record || !ns.panelRuns.canResume(record) || state.driving.has(record.id)) return;
    if (record.parkedAt != null) {
      record.yourMs += Math.max(0, store.run.now() - record.parkedAt);
      record.parkedAt = null;
    }
    const wasQuestions = record.status === "parked" && record.why === "open_questions";
    Object.assign(record, { status: "filling", stopRequested: false, learned: null });
    persist(store);
    try {
      if (wasQuestions) await afterTyping(store, record);
    } catch (err) {
      console.warn("[maestro-cs] could not read what you typed:", err);
    }
    // A tab closed or a panel reopened under the read ended the record: nothing is driven.
    if (!live(record)) return;
    await drive(store, record);
  }

  /** Undo the standing answers Resume just saved: the profile gets back what it had. */
  async function undoLearned(store, id) {
    const record = recordById(store, id);
    const saved = state.undo.get(id);
    if (!record?.learned || record.learned.undone || !saved) return;
    try {
      await ns.panelLearn.unlearnAnswers(store, saved);
      record.learned = { ...record.learned, undone: true };
      state.undo.delete(id);
    } catch (err) {
      console.warn("[maestro-cs] could not undo the saved answers:", err);
    }
    persist(store);
  }

  // ---------- the confirmation: a Submit the user pressed, seen, and marked 8 s later ----------

  function onTabUpdated(store, tabId, change) {
    for (const record of store.read().runs) {
      if (record.tabId !== tabId || !live(record)) continue;
      // A tab that went to a host the run never reached is no longer the run's page: its vouch (the
      // origin a subframe may take a fill from) goes with it. A Resume reads the page again and
      // vouches for what it finds if it is the application.
      if (change.url && !(record.hosts ?? []).includes(hostOf(change.url))) store.run.unvouch(tabId);
    }
    if (!change.url && change.status !== "complete") return;
    for (const record of store.read().runs) {
      if (record.tabId === tabId && record.status === "ready" && !record.noAutoMark && ownedHere(record)) {
        checkConfirmation(store, record).catch(warn("could not read the page after Submit"));
      }
    }
  }

  // A record with no lease predates the field (or was made by a test): this panel's to watch.
  const ownedHere = (record) => record.lease == null || record.lease === state.lease;

  function onTabRemoved(store, tabId) {
    for (const record of store.read().runs) {
      if (tabOf(record) !== tabId || !live(record)) continue;
      state.timers.get(record.id)?.();
      state.timers.delete(record.id);
      store.run.unvouch(tabId);
      if (record.status === "confirming") {
        // The user's Submit went through and the page said so: closing the tab is not a cancel. The
        // mark is made now (an Undo window has no tab to look at), from the page the run saw.
        Object.assign(record, { tabClosed: true, markAt: null });
        recordSubmitted(store, record).catch(warn("could not mark applied")).finally(() => {
          if (record.status === "ready") Object.assign(record, { status: "stopped", why: "tab_closed", stopRequested: true });
          persist(store);
        });
        continue;
      }
      Object.assign(record, { status: "stopped", why: "tab_closed", stopRequested: true, tabClosed: true, markAt: null });
      persist(store);
    }
  }

  /** Read a ready tab after its address changed: the driver names a confirmation page, and the
   * countdown starts. A tab that is mid-navigation is read a few times (the driver keeps a ready run
   * ready when a read fails: an error in the middle of the user's own Submit is not a failed run). */
  async function checkConfirmation(store, record) {
    if (state.checking.has(record.id) || state.driving.has(record.id)) return;
    state.checking.add(record.id);
    try {
      for (let i = 0; i < CONFIRM_POLLS && record.status === "ready" && !record.noAutoMark; i += 1) {
        await drive(store, record);
        if (record.status !== "ready") break;
        await store.run.sleep(CONFIRM_POLL_MS);
      }
    } finally {
      state.checking.delete(record.id);
    }
  }

  function armAutoMark(store, record) {
    // The user's time ends when the confirmation is SEEN: not the 8 s delay, the network, or an Undo.
    if (!record.timeCounted && record.readyAt != null) {
      record.yourMs += Math.max(0, store.run.now() - record.readyAt);
      record.timeCounted = true;
    }
    state.timers.get(record.id)?.();
    record.markAt = store.run.now() + AUTO_MARK_MS;
    state.timers.set(record.id, store.run.after(AUTO_MARK_MS, () => {
      state.timers.delete(record.id);
      if (record.status === "confirming") recordSubmitted(store, record).catch(warn("could not mark applied"));
    }));
  }

  /** Undo, inside the 8 s: back to ready, nothing posted, and the mark is the user's to press. */
  function undoMark(store, id) {
    const record = recordById(store, id);
    if (!record || record.status !== "confirming") return;
    state.timers.get(id)?.();
    state.timers.delete(id);
    Object.assign(record, { status: "ready", why: null, markAt: null, noAutoMark: true });
    persist(store);
  }

  /** `{host, path}` of an address, or null when it names no host. */
  function addressOf(url) {
    try {
      const { hostname, pathname } = new URL(url);
      return hostname ? { host: hostname, path: pathname || "/" } : null;
    } catch {
      return null;
    }
  }

  /** `{host, path, text}` for the confirmation: the page the run SAW say so, else (a manual mark on a
   * record that never read one) the tab's address now, plus the matched words. */
  async function confirmationFor(store, record) {
    const text = String(state.phrases.get(record.id) ?? "").slice(0, MAX_PHRASE);
    const seen = state.confirmed.get(record.id);
    if (seen) return { ...seen, text };
    const where = addressOf(await store.run.tabUrl(tabOf(record)).catch(() => ""));
    return where ? { ...where, text } : null;
  }

  /** Mark applied. Normally the proposal's own endpoint, which approves and submits under the
   * Companion's consent in one commit. When it answered 409 (Maestro CS already holds the job in a
   * state it will not move from) the manual route is the application's status, the same write as
   * the footer's Applied. A failure is a sentence on the card and the user's button, never a retry
   * loop. */
  async function recordSubmitted(store, record) {
    if (state.marking.has(record.id)) return;
    state.marking.add(record.id);
    try {
      let confirmation = null;
      if (!record.markConflict) {
        confirmation = await confirmationFor(store, record);
        if (!confirmation) {
          Object.assign(record, { status: "ready", why: null, markAt: null, noAutoMark: true,
            markNote: "Couldn't read the page's address, so it wasn't marked applied. Mark it yourself once it went through." });
          return;
        }
      }
      if (confirmation) {
        await store.api(`/api/proposals/${encodeURIComponent(record.proposalId)}/companion-submitted`,
          { method: "POST", body: JSON.stringify({ confirmation }) });
      } else {
        await store.api(`/api/applications/${encodeURIComponent(record.applicationId)}`,
          { method: "PATCH", body: JSON.stringify({ status: "applied" }) });
      }
      Object.assign(record, { status: "applied", why: null, markAt: null, markNote: null });
      store.run.unvouch(tabOf(record));
    } catch (err) {
      const conflict = err?.status === 409;
      Object.assign(record, { status: "ready", why: null, markAt: null, noAutoMark: true,
        markConflict: conflict || record.markConflict,
        // The server's own sentence for a 409 (it says why the proposal would not move), through
        // `failureNote`; the fallback is the application's status, since a retry would be refused again.
        markNote: ns.panelFailureNote({ what: "Couldn't mark this applied.",
          answered: (failure) => (failure.status === 409 ? String(failure.message) : null) }, err) });
    } finally {
      state.marking.delete(record.id);
      persist(store);
    }
    if (record.status === "applied" && store.read().tabId === tabOf(record)) store.loadContext(store.token());
  }

  function markApplied(store, id) {
    const record = recordById(store, id);
    if (!record || record.status !== "ready") return Promise.resolve();
    return recordSubmitted(store, record);
  }

  // ---------- a reopened panel ----------

  /** Read the records the last panel left (status only: a reopened panel does not resume driving,
   * design Part 1) and start listening to the tabs they live in. A record that was mid-air is
   * stopped as interrupted; a countdown that was running is the user's to finish by hand. */
  async function restoreRuns(store) {
    store.run.watch({ updated: (tabId, change) => onTabUpdated(store, tabId, change),
                      removed: (tabId) => onTabRemoved(store, tabId) });
    const saved = await store.run.load().catch(() => []);
    const kept = (Array.isArray(saved) ? saved : []).filter((one) => one && typeof one.id === "string");
    // A reopened panel takes over the records on tabs of ITS window; another window's stay that
    // panel's (this one shows them and arms nothing for them).
    const records = await Promise.all(kept.map(async (one) => {
      const ours = await store.run.ownsTab(tabOf(one)).catch(() => true);
      const mine = ours ? { ...one, lease: state.lease } : one;
      if (IN_AIR.has(mine.status)) return { ...mine, status: "stopped", why: "interrupted", stopRequested: false };
      if (mine.status === "confirming") return { ...mine, status: "ready", markAt: null, noAutoMark: true };
      return mine;
    }));
    if (!records.length) return;
    store.write({ runs: records });
    store.render();
  }

  ns.panelActionsRun = { startRun, stopRun, resumeRun, skipRun, closeRun, undoLearned, undoMark,
                         markApplied, restoreRuns };
})();
