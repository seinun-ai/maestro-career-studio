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
 * `assumedRows` (every page's answered-for-you rows, `{fid, question, step, note}`, never a value),
 * `parkedAt`/`yourMs` (the user's time), `learned` (what Resume saved), and for the auto-mark
 * `markAt`, `noAutoMark`, `markNote`, `markConflict` and `timeCounted`. Answers never live on it: the receipt's
 * memory of what it posted (values) and Undo's previous profile values stay in this file's maps,
 * which neither the card nor `chrome.storage.session` ever sees.
 *
 * WHAT THIS FILE PUBLISHES: ns.panelActionsRun = { startRun, runningHere, stopRun, resumeRun, skipRun,
 * closeRun, moveRun, movable, movableFor, undoLearned, undoMark, markApplied, restoreRuns, TERMINAL }. `TERMINAL` is the set of run
 * statuses that are over, read by the Job step's Apply to see whether another tab's run holds a job.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const { samePosting, boardHost } = ns.decisions;

  // 8 s between the confirmation page and the mark, so an Undo is a real chance (`submitted` is
  // terminal on the server: the delay is the undo, not a reversal).
  const AUTO_MARK_MS = 8000;
  // A ready tab's confirmation page may draw a beat after its address changes.
  const CONFIRM_POLLS = 5;
  const CONFIRM_POLL_MS = 1000;
  const LOAD_WAIT_MS = 30000;
  const LOAD_POLL_MS = 250;
  const TERMINAL = new Set(["stopped", "applied"]);
  const hostOf = (url) => {
    try {
      return new URL(url).hostname;
    } catch {
      return "";
    }
  };
  // A record that was mid-air when the panel closed is not running any more.
  const IN_AIR = new Set(["waiting", "opening", "signing_in", "creating_account", "filling", "advancing"]);
  const MAX_PHRASE = 300;
  const MAX_LOOKED = 50;
  // What the fill report counts as filled on a page (the engine wrote it and checked it).
  const WROTE = new Set(["verified", "closest", "assumed"]);
  // What the card counts as answered: filled and verified, or found answered or the user's own (kept).
  const ANSWERED = new Set([...WROTE, "already", "yours"]);
  // The parks after which Resume reads what the user typed into the page (`afterTyping`).
  const LEARNS = new Set(["open_questions", "page_errors", "upload"]);
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
    // New tabs a parked run's tab opened whose address has not arrived (tab id -> run id), and the
    // tab+address pairs already asked the backend about (one lookup each).
    openers: new Map(), looked: new Set(),
    // Per run: what the last fills ended in, by field (`{step, rows: {fid: {status, slot}}}`): the reasoning step's
    // "the run filled it" and "which fact answered it". Never a value; reset when the step changes.
    lastFill: new Map(),
  };

  const tabOf = (record) => record.tabId ?? record.startTabId;
  /** An address without its query or fragment: the page's own place. */
  const pathOf = (url) => String(url ?? "").split(/[?#]/)[0];
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
      openUrl: seed.openUrl, sourceUrl: seed.sourceUrl ?? null, inPlace: seed.inPlace === true,
      startTabId: tabId, tabId: null,
      status: "waiting", why: null, open: [], hosts: [], seen: [], step: 0, fingerprint: null,
      startedAt: null, readyAt: null, yourMs: 0, flowOrigin: null,
      stopRequested: false, pages: [], progress: null, flags: [], assumedRows: [], parkedAt: null, learned: null,
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
    // The top frame's detect, else the first frame that holds a form (an embedded application).
    const detectUploads = async () => {
      let verdict = await host.tabFrame0(record.tabId, { type: "detect_page" }).catch(() => null);
      if (verdict?.form !== true) {
        const frames = await host.tabBroadcast(record.tabId, { type: "detect_page" }).catch(() => []);
        verdict = frames.map((frame) => frame.result).find((one) => one?.form === true) ?? verdict;
      }
      if (!verdict) return null;
      return { fileInputs: Number(verdict.fileInputs) || 0,
               uploads: Array.isArray(verdict.uploads) ? verdict.uploads : null };
    };
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
      attachPdf: (path, filename, expect, resumeOnly = false, target = null) =>
        host.attachPdf(record.tabId, path, filename, expect, resumeOnly, target),
      detectUploads,
      // `sendResume` asks this after a write it could not prove, to tell "the page grew a box" from "the
      // boxes took nothing"; without it that path threw and read as a write that never happened.
      detectFileInputs: async () => (await detectUploads())?.fileInputs ?? 0,
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
      && !boardHost(hostOf(here));
    // ... except when the matched page is the job's saved POSTING and the job has a different saved
    // application link: the posting is where the user found the job, the link is where the form is.
    const onPostingOnly = Boolean(record.sourceUrl) && !samePosting(url, here) && samePosting(record.sourceUrl, here);
    // A run in place is on the page the user picked for it: that page is never navigated. If the tab
    // has gone elsewhere, the driver's first read parks it.
    const stays = record.inPlace === true || (Boolean(here) && (samePosting(url, here) || (matched && !onPostingOnly)));
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
      fix: (one, errors, { limits }) => fixPage(store, one, errors, limits),
      attachTo: (one, box) => attachBox(store, one, box.target),
      uploads: (one) => uploadBoxes(host, one),
      // The reasoning step runs only under its setting (Think when stuck on, Stop after each step off, full automation on).
      ...(ns.panelRunReason.enabled(store.read()) ? { reason: (one, ctx) => think(store, one, ctx) } : {}),
    };
  }

  /** Every change the driver makes: the user's time starts when it parks, a finished run stops being
   * vouched for, and the panel paints. */
  function onUpdate(store, record) {
    if (record.sorted && (record.step ?? 0) !== record.sortedStep) record.sorted = null;
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

  /** The run's answered-for-you rows, kept across pages (Ready lists them whatever page it lands on): a
   * drafted answer or a date set to the 1st, by its question and fixed note, never its value. One row per
   * question and step. */
  function keepAssumed(record, report) {
    const rows = record.assumedRows ?? [];
    const step = record.step ?? 0;
    for (const row of report.fields) {
      // A value the engine landed without choosing it (a search's one hit) is the user's to check: a fixed
      // sentence, never the text the page took.
      const landed = ns.queueRun.landedToCheck(row);
      if ((row.status !== "assumed" && !landed) || !row.question
          || rows.some((one) => one.question === row.question && one.step === step)) continue;
      rows.push({ fid: row.fid, question: row.question, step,
                  note: landed ? ns.fillLoop.landedNote(null, row.lastOutcome) : ns.fillLoop.knownNote(row.note) });
    }
    record.assumedRows = rows;
  }

  /** What a fill ended in, by field: the reasoning step reads "the run filled it" and the fact that answered it. */
  function noteFill(record, report, url) {
    const step = record.step ?? 0;
    const page = pathOf(url);
    let kept = state.lastFill.get(record.id);
    // What was filled on another page, or another step, says nothing about this one.
    if (kept?.step !== step || kept.page !== page) kept = { step, page, rows: {} };
    for (const row of report.fields ?? []) {
      if (row?.fid && row.status) kept.rows[row.fid] = { status: row.status, ...(typeof row.slot === "string" ? { slot: row.slot } : {}) };
    }
    state.lastFill.set(record.id, kept);
  }

  /** The fill of one page, pinned to the run's tab: its job and application from the record, the
   * run's limits, and a `cancelled` that only the run's own Stop moves. Posts the answer receipt,
   * tries the resume attach as Autofill does, and sends the same value-free telemetry and trace. */
  async function fillPage(store, record, limits, scope = {}) {
    const host = store.run;
    // A repair of the fields a page's errors named (`scope.only`): only those are worked, the page's
    // progress count and page row stay as the full fill left them, and the resume attach is not repeated.
    const scoped = Array.isArray(scope.only);
    const rs = runStore(store, record);
    const url = await host.tabUrl(record.tabId);
    rs.write({ url });
    const stopped = () => record.stopRequested === true;
    const finished = new Set();   // every field that reached a final status
    const answered = new Set();   // those that ended filled, verified or kept
    let total = 0;
    let auto = null;
    if (!scoped) record.progress = { done: 0, total: 0 };
    const report = await ns.fillLoop.runFill({
      broadcast: async (message) => {
        const frames = await host.tabBroadcast(record.tabId, message);
        // The page's field count is the length of the page: a full inventory (not a peek, not the
        // receipt's read) names every field the loop is about to work.
        if (!scoped && message.type === "fill_inventory" && !message.peek && !message.readOnly) {
          total = frames.reduce((n, frame) => n + (frame.result?.fields?.length ?? 0), 0);
          record.progress = { done: answered.size, total };
          store.render();
        }
        return frames;
      },
      api: store.api,
      recipes: store.recipes(),
      cancelled: stopped,
      beforeSweep: async () => {
        if (scoped) return 0;
        auto = await ns.panelRunAttach.attach(rs, 0, stopped);
        return ns.panelRunAttach.wrote(auto) ? ns.panelRunAttach.settleMs : 0;
      },
      onProgress: (update) => {
        if (update.phase !== "field" || scoped) return;
        finished.add(update.fid);
        if (ANSWERED.has(update.status)) answered.add(update.fid);
        record.progress = { done: answered.size, total: Math.max(total, finished.size) };
        store.render();
      },
    }, {
      applicationId: record.applicationId,
      base: record.applicationId ? null : record.baseSlug,
      sourceHint: ns.fillLoop.sourceHintOf(url),
      pageUrl: ns.fillLoop.pageUrlOf(url),
      limits,
      // Nobody is waiting on an optional skills box in a run, and it is the slowest field of a page.
      // (A repair of fields the page named is not it: a skills box the page asks for is worked.)
      skipOptionalSkills: !scoped,
      // What the loop learnt on this page (moves that failed, terms tried) survives to the next call on
      // it. The record owns it; the driver clears it when the step changes, and it never reaches storage.
      memory: (record.memory ??= ns.fillLoop.newMemory()),
      ...(scoped ? { only: scope.only } : {}),
      // The reasoning step's levers (shared/reason-loop.js): which route, fact, voice, redo or move order a field gets.
      ...Object.fromEntries(["routes", "slotHints", "reasoner", "redo", "variants"]
        .filter((key) => scope[key] !== undefined).map((key) => [key, scope[key]])),
    });
    ns.panelRunAttach.land(rs, auto);
    noteFill(record, report, url);
    if (auto) record.attach = attachNote(auto);
    if (!scoped) {
      // The page's upload boxes, after the attach: one field each in the page's count, and a required
      // one still empty is the driver's to attach to (or park on) before it presses Next. The box the
      // attach above wrote (a resume box, when it wrote) is marked `written` and exempt.
      const boxes = await uploadBoxes(host, record);
      const wrote = ns.panelRunAttach.wrote(auto);
      const empty = boxes.filter((box) => box.required && !box.occupied)
        .map(({ label, target, kind }) => ({ label, target, kind, written: wrote && kind === "resume" }));
      const taken = boxes.filter((box) => box.occupied).length;
      record.progress = { done: answered.size + taken, total: Math.max(total, finished.size) + boxes.length };
      report.attach = { outcome: auto?.outcome ?? null, reason: auto?.reason ?? null,
                        required: empty.some((box) => !box.written), boxes: empty };
      rs.write({ consentForms: report.consentForms === true });
      const flags = await ns.panelRecordReceipt(rs, rs.read(), 0,
        (frames) => ns.receipt.fromLoop(report, frames, auto, rs.read().receiptSeen?.fids),
        { consentForms: report.consentForms === true, fields: report.fields });
      // This page's flags only: a page whose receipt is null must not show the previous page's.
      record.flags = flags ?? [];
      keepAssumed(record, report);
      postGaps(store, record, leftovers(report.trace));
    }
    // A repair of named fields posts no receipt and no gap rows: the page's own fill already did. What the reasoning step
    // wrote does post one, so What was submitted holds it; the page's own flags stay as the full fill left them.
    if (scoped && scope.reasoned && report.fields.some((row) => WROTE.has(row.status))) {
      await ns.panelRecordReceipt(rs, rs.read(), 0,
        (frames) => ns.receipt.fromLoop(report, frames, null, rs.read().receiptSeen?.fids),
        { consentForms: rs.read().consentForms === true, fields: report.fields });
    }
    host.telemetry("loop_fill", ns.fillLoop.buildLoopObservations(report), url);
    if (report.trace) noteLog(store, record, store.trace(report.trace));
    if (!report.stopped && !scoped) {
      const filled = report.fields.filter((row) => WROTE.has(row.status)).length;
      const n = (record.step ?? 0) + 1;
      record.pages = [...(record.pages ?? []).filter((page) => page.n !== n), { n, filled }];
    }
    return report;
  }

  // What counts as a field repaired: the engine wrote it and checked it, or found it answered.
  const REPAIRED = new Set([...WROTE, "already", "yours"]);

  /** The repair after the page refused a Next, by what its errors named (`pageErrors`): ONLY those
   * fields, never the rest of the page. A fill field is worked again with `only` (and the page's
   * memory); an upload box gets the run's PDF. An error that names nothing the run can work (an unmapped
   * label) stays the user's, and so does one the repair did not fix: `{fixed, remaining}` says which are
   * left, so the park names only those. A banner left up over boxes already holding their file is repaired by
   * writing nothing; the driver then reads the page again to see where it is. */
  async function fixPage(store, record, errors, limits) {
    const mapped = (one) => one.target && (one.kind === "field" || one.kind === "upload");
    const remaining = errors.filter((one) => !mapped(one));
    // An upload box the page named gets the run's PDF, whatever the box looks like to the run's own attach,
    // but only ONE box: two named uploads cannot both be the resume's, so the user is asked.
    const uploads = errors.filter((one) => mapped(one) && one.kind === "upload");
    if (uploads.length > 1) remaining.push(...uploads);
    else {
      for (const one of uploads) {
        // A banner left up over a box the user filled by hand is a stale line: that box is repaired.
        if ((await uploadBoxes(store.run, record)).some((box) => box.target === one.target && box.occupied)) continue;
        if (record.stopRequested === true || !(await attachBox(store, record, one.target)).attached) remaining.push(one);
      }
    }
    const fields = errors.filter((one) => mapped(one) && one.kind === "field");
    if (fields.length && record.stopRequested !== true) {
      const report = await fillPage(store, record, limits, { only: fields.map((one) => one.target) });
      if (report.stopped) return { fixed: false, remaining: [...remaining, ...fields] };
      const byFid = new Map(report.fields.map((row) => [row.fid, row]));
      for (const one of fields) {
        if (!REPAIRED.has(byFid.get(one.target)?.status)) remaining.push(one);
      }
    } else {
      remaining.push(...fields);
    }
    return { fixed: remaining.length === 0, remaining };
  }

  /** The one sentence the card shows when the reasoning step moved the run on. */
  function sortedLine(out) {
    const n = out.wrote.length;
    return `Sorted it out${n ? `: answered ${n} question${n === 1 ? "" : "s"}` : ""} and moved on.`;
  }

  /** The reasoning step (shared/reason-loop.js) at a park the driver may think about: the loop gets this run's tab, the
   * fill, the follow and the api door through `opsFor`, and the card gets a live line (`thinking`) while it works. What it
   * wrote or chose joins "Check before you submit" as answered for you (a row per question and step, never a value);
   * the one sentence (`sorted`) says it moved the run on. */
  async function think(store, record, ctx) {
    const host = store.run;
    const calm = { moved: false, advanced: null, followed: false, note: "", ask: null, tried: [], rounds: [], wrote: [] };
    const url = await host.tabUrl(tabOf(record)).catch(() => "");
    const day = new Date(host.now());
    const today = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
    record.sorted = null;
    const ops = ns.panelRunReason.opsFor(store, record, {
      fill: (fids, scope) => fillPage(store, record, ns.queueRun.RUN_LIMITS, { only: fids, ...scope }),
      rebind: async (tabId) => rebind(store, record, tabId, await host.tabUrl(tabId).catch(() => ""),
        () => record.stopRequested !== true),
      isTheApplication: (address) => isTheApplication(record, address),
      occupied: (tabId) => store.read().runs.some((one) => one !== record && tabOf(one) === tabId && live(one)),
      lastFill: (address) => {
        const kept = state.lastFill.get(record.id);
        return kept && kept.step === (record.step ?? 0) && kept.page === pathOf(address) ? { ...kept.rows } : {};
      },
      consent: () => runStore(store, record).read().consentForms === true,
    });
    let out = calm;
    try {
      // A tab on another site is not this application's page: its address is not sent.
      out = await ns.reasonLoop.think({ ...ctx, applicationId: record.applicationId,
        base: record.applicationId ? null : record.baseSlug, today,
        pageUrl: ctx.why === "moved_away" ? null : ns.fillLoop.pageUrlOf(url) }, ops);
    } catch (err) {
      // A fault in the step is the normal park, never the run's end. The message may quote the page: not logged.
      console.warn("[maestro-cs] the reasoning step failed:", err?.name ?? "error");
    } finally {
      // The footer note says the live line while it lasts and goes with it; any other note is not ours to clear.
      if (record.thinking && store.read().note?.text === record.thinking) store.write({ note: null });
      record.thinking = null;
    }
    const step = record.step ?? 0;
    const rows = record.assumedRows ?? [];
    for (const one of out.wrote) {
      // By field and step: the run's own row may carry the whole question, this one is cut. The step's note is the true one.
      const same = rows.find((row) => row.fid === one.fid && row.step === step);
      if (same) same.note = one.note;
      else rows.push({ fid: one.fid, question: one.question, step, note: one.note });
    }
    record.assumedRows = rows;
    // The sentence belongs to the page the run is on when the thought ends (the next one, if it pressed Next).
    if (out.moved) Object.assign(record, { sorted: sortedLine(out), sortedStep: step + (out.advanced ? 1 : 0) });
    return out;
  }

  /** Whether the worker posted the run's trace: it answers `why: "off"` when the fill log is off, and the card
   * then says so. Never awaited (a fill is not delayed by its own log), and never throws. */
  function noteLog(store, record, reply) {
    Promise.resolve(reply).then((got) => {
      if (got === undefined || got === null) return;
      const off = got.why === "off";
      // The time the log last recorded a run (an ISO time from the worker), kept to date a gap.
      const last = off && typeof got.lastAt === "string" ? got.lastAt.slice(0, 30) : null;
      if (record.logOff === off && (record.logLast ?? null) === last) return;
      record.logOff = off;
      record.logLast = last;
      persist(store);   // kept with the record, so a reopened panel still says it
    }).catch(warn("could not read the fill log's answer"));
  }

  /** The run's PDF into the one upload box `target` names; the card's attach line follows the result. */
  async function attachBox(store, record, target) {
    // The resume was written on this page already (and may be there, only unseen): never a second copy.
    if (record.attach?.outcome === "attached" || record.attach?.outcome === "unconfirmed") return { attached: false };
    const rs = runStore(store, record);
    const got = await ns.panelRunAttach.attachTo(rs, 0, () => record.stopRequested === true, target);
    if (!got) return { attached: false };
    ns.panelRunAttach.land(rs, got);
    // The box written is remembered by its opaque tag (no value), so a Resume can tell it from one left empty.
    record.attach = { ...attachNote(got), target };
    if (got.outcome === "attached" && record.progress?.total > record.progress.done) {
      record.progress = { ...record.progress, done: record.progress.done + 1 };
    }
    store.render();
    return { attached: got.outcome === "attached" };
  }

  /** The attach as the card keeps it: the outcome, and its sentence unless it is the one that names the
   * file ("attached"), so the record holds no filename. */
  function attachNote(auto) {
    return { outcome: auto.outcome, ...(auto.reason ? { reason: String(auto.reason).slice(0, 40) } : {}),
             ...(auto.outcome !== "attached" && auto.text ? { text: String(auto.text).slice(0, MAX_PHRASE) } : {}) };
  }

  /** The page's upload boxes in its own words (`page_uploads`), from every frame that answers; a box
   * is `{label, target, required, occupied}` and nothing else crosses. */
  async function uploadBoxes(host, record) {
    try {
      const frames = await host.tabBroadcast(record.tabId, { type: "page_uploads" });
      return frames.flatMap((frame) => (Array.isArray(frame.result) ? frame.result : []))
        .filter((box) => box && typeof box.target === "string" && box.target)
        .map((box) => ({ label: String(box.label ?? "").slice(0, 160), target: box.target, kind: String(box.kind ?? "unknown"),
                         required: box.required === true, occupied: box.occupied === true }));
    } catch {
      return [];
    }
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

  /** Whether the bound tab has a run that has not finished: the Job step's Apply asks this BEFORE it
   * writes anything, since `startRun` refuses such a tab only after the job was queued and tailored. */
  function runningHere(store) {
    const facts = store.read();
    return facts.tabId !== null && facts.runs.some((one) => tabOf(one) === facts.tabId && live(one));
  }

  /** Apply to one job in the CURRENT tab, from its employer link through every page to the review.
   * `seed` is `{proposalId, jobId, applicationId, company, location, title, baseSlug, openUrl, sourceUrl, inPlace}`
   * (`inPlace`: the user picked the job for this very page, so `openUrl` is this page); the Job
   * step's Apply (Task 20a) builds it after the job is queued and its resume is ready. A tab with a
   * run that has not finished is not started again. */
  async function startRun(store, seed) {
    const facts = store.read();
    const tabId = facts.tabId;
    if (tabId === null || !seed?.proposalId || !seed?.openUrl) return null;
    if (runningHere(store)) return null;
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
    state.lastFill.delete(record.id);
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
    // The parks the user fixed by hand in the page: the questions they typed over, the fields the page named
    // as wrong, the upload boxes (a field among them is an answer like any other). Walls and navigation are not.
    const handFixed = record.status === "parked" && LEARNS.has(record.why);
    // Resume is this panel taking the record over (it may have been left by another window's panel and
    // moved here): the mark after the user's Submit then has exactly one owner.
    // A ready tab taken back to a form step is a new fill: it is no longer vouched for as the finished application.
    const wasReady = record.status === "ready";
    Object.assign(record, { status: "filling", stopRequested: false, learned: null, moved: false, lease: state.lease,
      thought: null, thinking: null, sorted: null },
      wasReady ? { readyAt: null, readyBy: null, movedOn: false } : {});
    persist(store);
    try {
      if (handFixed) await afterTyping(store, record);
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

  // ---------- a parked run follows the user into the tab they open ----------

  // A record with no lease predates the field (or was made by a test): this panel's to watch.
  const ownedHere = (record) => record.lease == null || record.lease === state.lease;

  /** Whether the record may be moved to another tab: parked on a step the user does by hand (the posting's
   * Apply, the start chooser, a sign-in, a code, a page it does not know), owned by this panel and not being
   * driven. A run that is filling or advancing never moves; neither does one waiting for an answer or a wall. */
  const movable = (record) => record.status === "parked" && ns.queueRun.USER_NAVIGATES.has(record.why)
    && record.stopRequested !== true && !state.driving.has(record.id) && ownedHere(record);

  /** The record that could come to the tab the facts are bound to: this job's, in another tab, movable. */
  function movableFor(facts) {
    const jobId = facts.job?.id;
    if (!jobId || facts.tabId == null || !Array.isArray(facts.runs)) return null;
    if (facts.runs.some((one) => tabOf(one) === facts.tabId && live(one))) return null;
    return facts.runs.find((one) => one.jobId === jobId && tabOf(one) !== facts.tabId && movable(one)) ?? null;
  }

  /** Whether `url` lies under `base`: the same origin and one path the prefix of the other (a posting and its
   * apply or step pages), two segments at least. Another job of the same tenant, or a policy page, is not. */
  function underPath(base, url) {
    try {
      const [a, b] = [new URL(base), new URL(url)];
      if (a.origin !== b.origin) return false;
      const [x, y] = ns.decisions.withoutLocale(...[a, b].map((one) => one.pathname.split("/").filter(Boolean)));
      const n = Math.min(x.length, y.length);
      return n >= 2 && x.slice(0, n).every((segment, i) => segment === y[i]);
    } catch {
      return false;
    }
  }

  /** The record's own application: under the link it was queued for, or under the Apply link its posting showed. */
  const isTheApplication = (record, url) => underPath(record.openUrl, url)
    || (Boolean(record.applyHref) && underPath(record.applyHref, url));

  /** Rebind the record to `tabId`. It stays parked where it was parked and does nothing by itself: the card
   * on the new tab offers Continue here. Its old tab loses the vouch, and the new tab's host joins the run's. */
  async function followTo(store, record, tabId, url) {
    if (!movable(record) || tabOf(record) === tabId) return false;
    return rebind(store, record, tabId, url, () => movable(record));
  }

  /** The move itself, for a follow and for the reasoning step's: not onto a tab another live run holds, nor one outside
   * this panel's window; `still` is asked again once the window is known. */
  async function rebind(store, record, tabId, url, still = () => true) {
    if (store.read().runs.some((one) => one !== record && tabOf(one) === tabId && live(one))) return false;
    // A side panel is one per window and every panel hears every tab: only the window's own tab is ours.
    if (!(await store.run.ownsTab(tabId).catch(() => false)) || !still()) return false;
    const old = tabOf(record);
    const host = hostOf(url);
    const hosts = record.hosts ?? [];
    Object.assign(record, { tabId, startTabId: tabId, moved: true,
      hosts: host && !hosts.includes(host) ? [...hosts, host] : hosts });
    store.run.unvouch(old);
    persist(store);
    return true;
  }

  /** The tab a parked run's page opened: followed at once when its address is the application's, else when the
   * address arrives (`followOpened`). Any other page, however it was opened, needs the backend to say it is this job. */
  function onTabCreated(store, tab) {
    if (!Number.isInteger(tab?.id) || !Number.isInteger(tab.openerTabId)) return;
    const record = store.read().runs.find((one) => tabOf(one) === tab.openerTabId && movable(one));
    if (!record) return;
    const url = tab.pendingUrl || tab.url || "";
    if (!/^https?:/.test(url)) {
      state.openers.set(tab.id, record.id);
      return;
    }
    if (isTheApplication(record, url)) followTo(store, record, tab.id, url).catch(warn("could not follow the new tab"));
    else followOpened(store, tab.id, url);
  }

  /** A tab's address arrived or changed. A tab a parked run's page opened is followed when it is the application's;
   * any other page only when the backend says it is this very job, and only on the apply link's host or a known
   * ATS (one lookup per address). */
  function followOpened(store, tabId, url) {
    if (!/^https?:/.test(url)) return;
    const runs = store.read().runs;
    if (runs.some((one) => tabOf(one) === tabId && live(one))) return;
    const pending = state.openers.get(tabId);
    if (pending) {
      state.openers.delete(tabId);
      const opener = recordById(store, pending);
      if (opener && movable(opener) && isTheApplication(opener, url)) {
        followTo(store, opener, tabId, url).catch(warn("could not follow the new tab"));
        return;
      }
    }
    const key = `${tabId} ${url}`;
    if (state.looked.has(key)) return;
    const host = hostOf(url);
    const record = runs.find((one) => one.jobId && movable(one) && tabOf(one) !== tabId
      && (host === hostOf(one.openUrl) || ns.atsHosts.isKnown(host)));
    if (!record) return;
    state.looked.add(key);
    // The last fifty addresses only: a long session with the run parked must not grow this without end.
    if (state.looked.size > MAX_LOOKED) state.looked.delete(state.looked.values().next().value);
    store.api(`/api/jobs/match?url=${encodeURIComponent(url)}`)
      .then((found) => (found?.job?.id === record.jobId ? followTo(store, record, tabId, url) : false))
      .catch(warn("could not tell whether the new tab is this job"));
  }

  /** The offer on the tab the user is looking at: bring the parked run here. Nothing is driven. */
  function moveRun(store, id) {
    const record = recordById(store, id);
    const facts = store.read();
    if (!record || facts.tabId == null || movableFor(facts)?.id !== record.id) return Promise.resolve();
    return followTo(store, record, facts.tabId, facts.url ?? "").then(() => undefined);
  }

  function onTabUpdated(store, tabId, change) {
    if (change.url) followOpened(store, tabId, change.url);
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

  function onTabRemoved(store, tabId) {
    state.openers.delete(tabId);
    for (const record of store.read().runs) {
      if (tabOf(record) !== tabId || !live(record)) continue;
      state.timers.get(record.id)?.();
      state.timers.delete(record.id);
      store.run.unvouch(tabId);
      if (record.status === "confirming") {
        // The user's Submit went through and the page said so: closing the tab is not a cancel. The
        // mark is made now (an Undo window has no tab to look at), from the page the run saw.
        Object.assign(record, { tabClosed: true, markAt: null });
        recordSubmitted(store, record).catch(warn("could not mark applied"));
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
      // A failed mark on a closed tab (also one already in flight when the tab went) is not a ready
      // card: nobody would see it. It ends stopped, where its note is read.
      if (record.tabClosed && record.status === "ready") {
        Object.assign(record, { status: "stopped", why: "tab_closed", stopRequested: true });
      }
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
                      removed: (tabId) => onTabRemoved(store, tabId),
                      created: (tab) => onTabCreated(store, tab) });
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

  ns.panelActionsRun = { startRun, runningHere, stopRun, resumeRun, skipRun, closeRun, moveRun, movable, movableFor,
                         undoLearned, undoMark, markApplied, restoreRuns, TERMINAL };
})();
