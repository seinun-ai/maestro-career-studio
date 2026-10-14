/* Maestro CS Companion — the queued run's driver: ONE job, in ONE tab, from its link to Ready to submit.
 *
 * Panel-side and pure, as shared/fill-loop.js is: it touches no `chrome`, `document` or network
 * call. Everything it does to a browser arrives as a dependency (`deps`), so node drives the whole
 * state machine with fakes, and a later move of the host (service worker, offscreen document) is a
 * change of host, not a rewrite (design Part 1). `pageOps` below builds the three page-facing deps
 * from a message transport; the rest (open a tab, fill, save) are the host's.
 *
 * THE STATE MACHINE (record.status; saved at every change and every page boundary)
 *   opening → [signing_in] → filling → advancing → (next page: filling → advancing …)
 *     → ready        a review page, filled; the user's Submit is the only thing left. Only with
 *                    evidence it was the application: a step behind it, or a field this page's fill
 *                    wrote or confirmed. A start chooser or a posting with a stray control parks
 *                    `unknown_page` instead. A field-less page with a lone Next after step 0 is
 *                    treated as review too (when unsure whether it is Next or Submit, stop).
 *     → confirming   a ready tab that now shows the confirmation page (Task 20 marks it applied)
 *     → parked       the run needs the user or hit a wall; `why` says which:
 *         captcha | create_account | verify | board_native   the page kind, a wall by design
 *         sign_in_failed   the saved login did not work; never retried (a lockout)
 *         sign_in_yourself the sign-in page is on a host that is not a known ATS (shared/ats-hosts.js):
 *                          the saved password is not typed there; the user signs in and presses Resume
 *         open_questions   required fields it could not answer or operate; `open` lists them
 *         no_change        Next did nothing, even after one refill
 *         loop | step_limit   the same page again, or more than LIMITS.stepMax steps
 *         posting          an Apply it may not press (see below); unknown_page  nothing it knows
 *         already_applied  a "thank you" page BEFORE the run reached review: not this run's Submit
 *         moved_away       a Resume found the tab on a host the run never navigated to: another
 *                          page must not be filled with this job's answers
 *     → stopped      closed | bad_link | error | user (a Stop; nothing is called after it)
 *   Resume re-enters `drive` on a parked record: the open tab is kept, the page is read again.
 *
 * SETTLING. A page the run has just arrived at (the opened tab, an Apply or Next that moved it, a
 * sign-in) is often not drawn yet: the content scripts load at document_idle, and a client-rendered
 * wizard answers with a skeleton. When such a read finds no frame or a page classed unknown, the
 * driver re-reads every POLL_MS until the page stops looking blank, for at most LIMITS.changeMs. A
 * field-less page with a lone Next after step 0 (a step half drawn looks exactly like an "are you
 * sure" page) must also hold still for LONE_STABLE reads in a row before it is judged final.
 * The rule lives here, not in pageOps().waitForChange, so it also covers the first read of a
 * freshly opened tab whatever the host's openTab resolves on.
 *
 * THE RULES IT KEEPS
 * - SUBMIT IS NEVER CLICKED. Only a button `ns.pageKind.classify` named the page's Next is ever
 *   pressed, and the page re-sorts it at click time (content/page-reader.js). A review page, or a
 *   page it cannot sort, ends the run as `ready`. The posting's Apply is the one narrow exception,
 *   pressed ONLY while: the page classified as a posting (no fillable control), this is the record's
 *   step 0, nothing has been filled in this record, and the tab is still on the host the apply link
 *   led to, AND it is the FIRST page this drive() call read after opening the tab itself. Never on a
 *   Resume, never after a sign-in: a site that restores a saved draft lands on its review page, which
 *   has no fillable control and an "Apply" that is a Submit. The page refuses a control that would
 *   submit a form, and the press goes to the one frame that named the control. A field-less page
 *   after a fill is the review page, so its "Apply" button is never pressed.
 * - STOP IS HONOURED: `cancelled(record)` is asked before AND after every dep call. Once it is true
 *   the driver calls nothing else (not an advance, not a sign-in) and ends `stopped/user`.
 * - NO PASSWORD PASSES THROUGH THE DRIVER. `signIn(record, {allowedHost})` is a dep; the driver
 *   holds no credential, and the record has no field for one. `pageOps().signIn` fetches the login
 *   and types it in ONE call, the password a local that goes out of scope with it: not on the
 *   record, in a log, a result, a card, a receipt or an error.
 * - The sign-in host is a host the RUN reached (the apply link and the navigations it caused,
 *   read from the tab's address), never what the page says about itself; the page re-checks it.
 * - `openUrl` is re-checked here (http or https only) before any navigation: a value that arrived
 *   by sync skipped the server's validation.
 * - A required field the fill reports `unconfirmed` does not park (the owner's "park less"): the
 *   advance and the page's own validation decide, and a page that does not move is refilled once.
 *
 * THE DEPS (all required, each a function; a missing one is a TypeError before anything runs)
 *   openTab(url, stop) → tabId  resolves once the tab exists (the driver waits for the page to be
 *                               readable itself, see SETTLING); `stop()` is the Stop check, so a
 *                               long load can be abandoned
 *   classify(tabId) → [{frameId, result: {summary, top}}]      tabUrl(tabId) → the tab's address
 *   advance(tabId, frameId, id, opts) → {clicked, why}         opts is {apply: true} or absent
 *   fill(record, {limits}) → the fill-loop report              signIn(record, {allowedHost, stop}) → {signedIn}
 *   waitForChange(tabId, before, ms, stop) → {changed, url}
 *   sleep(ms) · save(record) · onUpdate(record) · now() · cancelled(record)
 *                                (save is the host's: it owns the list)
 *   pageOps() builds classify, advance, signIn and waitForChange from a message transport.
 *
 * ONE DEVIATION FROM A STRAIGHT READING: after a clean fill the page is read AGAIN before it is
 * judged. A Next that stays disabled until the form validates is enabled only afterwards, and the
 * button ids are minted per read; judging the pre-fill read would stop every such wizard on its
 * first page as "review".
 *
 * WHAT THIS FILE PUBLISHES: ns.queueRun = { drive, pageOps, fingerprint, pickFrame, LIMITS,
 * RUN_LIMITS, HIDDEN_TABS_OK }. The scheduler (`next`, the record list, pacing) is not here.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  const LIMITS = { parallel: 3, waitingMax: 10, stepMax: 15, changeMs: 15000, paceMs: [2000, 6000] };
  // The fill's budget in a run (design Part 8.1): nobody is watching a queued run, so a stubborn
  // field gets a longer clock and more steps than the user's own Autofill (fill-loop's defaults).
  // RUN_MS is per page: a long page (a Workday skills list) must not be cut off at the 180 s the
  // field clocks would otherwise outgrow.
  const RUN_LIMITS = Object.freeze({ FIELD_MS: 60000, MAX_STEPS: 12, RUN_MS: 600000 });
  // Task 1a's spike: a fill in a background tab of the run window works.
  const HIDDEN_TABS_OK = true;
  const POLL_MS = 500;
  const LONE_STABLE = 4;   // reads in a row (about 2 s) before a field-less lone-Next page counts as final
  const MAX_QUESTION = 200;
  const OPEN_STATUSES = new Set(["needs_answer", "cannot_operate"]);
  // A fill "wrote or confirmed" a field when it ended in one of these (not unconfirmed, yours, blocked).
  const WROTE_STATUSES = new Set(["verified", "closest", "assumed", "already", "partial"]);
  const WALLS = new Set(["captcha", "create_account", "verify", "board_native"]);
  const DEPS = ["openTab", "classify", "advance", "fill", "signIn", "waitForChange", "tabUrl",
    "sleep", "save", "onUpdate", "now", "cancelled"];
  const HALT = Symbol("halt");

  /** The hostname of an http(s) address, lower-cased, else null (any other scheme, or not an address). */
  function hostOf(url) {
    try {
      const u = new URL(url);
      return u.protocol === "http:" || u.protocol === "https:" ? u.hostname.toLowerCase() : null;
    } catch {
      return null;
    }
  }
  const bare = (host) => String(host ?? "").toLowerCase().replace(/^www\./, "");
  const sameSite = (a, b) => Boolean(a) && Boolean(b) && bare(a) === bare(b);

  /** One string for "which page is this": the address (no hash), the step heading's key, the
   * visible button texts sorted, and how many controls a fill could answer. Value-free by
   * construction. The host's waitForChange compares these, so there is exactly one definition. */
  function fingerprint(url, summary) {
    let where = "";
    try {
      const u = new URL(url);
      where = u.origin + u.pathname + u.search;
    } catch {
      // No address known: the page alone tells.
    }
    const buttons = (summary?.buttons ?? []).filter((b) => b.visible !== false).map((b) => b.text).sort().join(",");
    return [where, summary?.stepKey ?? "", buttons, summary?.fillable ?? 0].join("\n");
  }

  // A wall shows in whichever frame holds it (a challenge in the embedded form's own iframe).
  // These only mean something in the top document: the page around everything else.
  const WALL_ANYWHERE = new Set(["captcha", "create_account", "verify"]);
  const TOP_ONLY = new Set(["sign_in", "closed", "confirmation", "board_native"]);

  /** The frame to judge the tab by. Only frames that answered with a summary count (a frame with
   * no form evidence says null). In order: the top document's own sign-in, closed, confirmation or
   * board page, or a wall in any frame; then any frame with a visible Submit, because one is
   * enough to make the TAB the review page (a Next in a carousel at the top must not outvote the
   * form's Submit in an embedded frame); then the top frame if it has fields to fill; then the
   * frame with the most fillable controls (a careers page embedding the ATS form); else the top. */
  function pickFrame(frames) {
    const usable = (Array.isArray(frames) ? frames : []).filter((f) => f?.result?.summary);
    const top = usable.find((f) => f.result.top);
    const kindOf = (f) => ns.pageKind.classify(f.result.summary).kind;
    const fillable = (f) => f.result.summary.fillable ?? 0;
    // A posting's own "Apply" is Submit-worded too, but the page it sits on classifies as a posting
    // before any button is read: only a frame that classifies as a review by its Submit counts.
    // Every Submit signal the reader has counts: a Submit-worded button, one the button list could
    // not see (`submitSeen`), or a dialog asking about submitting (`submitContext`).
    const showsSubmit = (f) => kindOf(f) === "review" && (
      f.result.summary.submitSeen === true || f.result.summary.submitContext === true
      || (f.result.summary.buttons ?? []).some((b) => b.visible !== false && ns.pageKind.sortButton(b) === "submit"));
    const fullest = usable.reduce((best, f) => (!best || fillable(f) > fillable(best) ? f : best), null);
    if (top && (WALL_ANYWHERE.has(kindOf(top)) || TOP_ONLY.has(kindOf(top)))) return top;
    const wall = usable.find((f) => WALL_ANYWHERE.has(kindOf(f)));
    if (wall) return wall;
    if (top && showsSubmit(top)) return top;
    const submitting = usable.find(showsSubmit);
    if (submitting) return submitting;
    if (top && fillable(top) > 0) return top;
    if (fullest && fillable(fullest) > 0) return fullest;
    return top ?? fullest;
  }

  const openQuestions = (report) => report.fields
    .filter((f) => f.required && OPEN_STATUSES.has(f.status))
    .map((f) => ({ fid: f.fid, question: String(f.question ?? "").slice(0, MAX_QUESTION), required: true }));

  /** Run one record to a stop. Returns the record; its `status` and `why` say where it got to. */
  async function drive(record, deps, options = {}) {
    for (const name of DEPS) {
      if (typeof deps?.[name] !== "function") throw new TypeError(`queue-run: missing dep ${name}`);
    }
    record.hosts ??= [];
    record.seen ??= [];
    record.step ??= 0;

    // A hook never stops a run (as fill-loop's onProgress): a failing save is the host's to notice.
    const touch = async () => {
      for (const hook of [deps.onUpdate, deps.save]) {
        try {
          await hook(record);
        } catch {
          // See above.
        }
      }
    };
    const update = async (patch) => {
      Object.assign(record, patch);
      await touch();
    };
    const finish = async (status, why, extra = {}) => {
      await update({ status, why, ...extra });
      return record;
    };
    const park = (why, extra = {}) => finish("parked", why, { open: [], ...extra });

    const gate = () => {
      if (deps.cancelled(record)) throw HALT;
    };
    // Every browser or panel effect goes through here: Stop is asked before it and after it.
    const act = async (fn, ...args) => {
      gate();
      const out = await fn(...args);
      gate();
      return out;
    };
    const stopping = () => deps.cancelled(record);

    let applyOk = false;     // this call opened the tab itself and has not read its first page yet
    let navigated = false;   // the last thing the run did moved the tab: its address is the run's own
    let pageFilled = false;  // this page has had its fill (judged afresh after it)
    let tried = 0;           // Next presses on this page that did nothing
    let movedChecked = false;  // a Resume's first read has been checked against the hosts the run reached

    const noteHost = async (url) => {
      const host = hostOf(url);
      if (host && host !== record.hosts.at(-1)) await update({ hosts: [...record.hosts, host] });
    };
    const waitChange = async (before) => {
      const waited = await act(deps.waitForChange, record.tabId, before, LIMITS.changeMs, stopping);
      return waited?.changed === true;
    };
    // "refused" (the page would not press it: the button went, or turned into a Submit), "same"
    // (pressed, the page did not change) or "moved". The wait is skipped for a refusal.
    const press = async (frame, id, before, opts) => {
      const pressed = await act(deps.advance, record.tabId, frame.frameId, id, opts);
      if (pressed?.clicked !== true) return "refused";
      return await waitChange(before) ? "moved" : "same";
    };
    const moved = () => {
      navigated = true;
      pageFilled = false;
      tried = 0;
    };

    // A read of the page that looks unfinished is repeated, for a page the run has just arrived at.
    //   "blank"  no frame answering, or a page classed unknown (a skeleton, a spinner): re-read until
    //            it stops looking blank or the cap runs out. A matching pair proves nothing, a
    //            spinner can hold for seconds.
    //   "lone"   after step 0, nothing fillable and a lone Next. A step whose fields have not
    //            arrived looks exactly like an "are you sure" page, so it must hold still for
    //            LONE_STABLE reads in a row (about 2 s) before it is judged to be one.
    const unfinished = (frame) => {
      if (!frame) return "blank";
      const summary = frame.result.summary;
      const kind = ns.pageKind.classify(summary).kind;
      if (kind === "unknown") return "blank";
      return record.step > 0 && kind === "form_step" && (summary.fillable ?? 0) === 0 ? "lone" : null;
    };
    const readPage = async (settle) => {
      const startedAt = deps.now();
      let previous = null;
      let agreeing = 0;
      for (;;) {
        const frame = pickFrame(await act(deps.classify, record.tabId));
        const url = await act(deps.tabUrl, record.tabId);
        const why = settle ? unfinished(frame) : null;
        if (!why) return { frame, url };
        const print = frame ? fingerprint(url, frame.result.summary) : null;
        agreeing = print !== null && print === previous ? agreeing + 1 : 1;
        previous = print;
        if (why === "lone" && agreeing >= LONE_STABLE) return { frame, url };
        if (deps.now() - startedAt >= LIMITS.changeMs) return { frame, url };
        await act(deps.sleep, POLL_MS);
      }
    };

    try {
      gate();
      const resumed = record.tabId != null;
      const userNavigates = record.why === "sign_in_yourself" || record.why === "verify";
      if (record.tabId == null) {
        const host = hostOf(record.openUrl);
        if (!host) return await finish("stopped", "bad_link");
        await update({ status: "opening", why: null, open: [], startedAt: record.startedAt ?? deps.now(), hosts: [host] });
        gate();
        // The tab id is kept before Stop is asked again: a tab the run opened must stay findable.
        await update({ tabId: await deps.openTab(record.openUrl, stopping) });
        gate();
        navigated = true;
        applyOk = true;
      } else if (record.readyAt == null) {
        await update({ status: "filling", why: null, open: [] });
      }

      for (;;) {
        const arrived = navigated;
        const { frame, url } = await readPage(arrived);
        // A finished run is only watching for the confirmation: a page not readable yet changes nothing.
        if (!frame) return record.readyAt != null ? record : await park("unknown_page");
        const summary = frame.result.summary;
        // Spent on this first read, whatever it finds: a later page (after a sign-in, a Resume, a
        // step) may be a saved draft's review page, and its "Apply" is a Submit.
        const mayApply = applyOk;
        applyOk = false;
        if (arrived) {
          navigated = false;
          await noteHost(url);
        }
        // A Resume finds the tab where the user left it. On a host the run never navigated to it is
        // another page, and it is not filled with this job's answers. (A ready tab is only watched,
        // and a park that asked the user to navigate, to sign in or enter a code, is exempt:
        // where they land is theirs.)
        if (resumed && !arrived && record.readyAt == null && !movedChecked) {
          movedChecked = true;
          if (!userNavigates && url && record.hosts.length && !record.hosts.includes(hostOf(url))) return await park("moved_away");
        }
        const verdict = ns.pageKind.classify(summary);
        let kind = verdict.kind;

        // A finished run only watches for the confirmation of the user's own Submit.
        if (record.readyAt != null) {
          return kind === "confirmation" ? await finish("confirming", null) : record;
        }
        // A "thank you" page before the run reached review is an application someone else sent
        // (a draft this browser's session already submitted): not ready, not this run's to mark.
        if (kind === "confirmation") return await park("already_applied");
        // A field-less page with an Apply after a fill (or after a step) is the review page.
        if (kind === "posting" && (record.filled === true || record.step > 0)) kind = "review";
        // Later than the first page, a page with nothing to fill and a lone Next may be a final
        // "are you sure" page: when unsure whether a button is Next or Submit, stop. (An intro page
        // at step 0 still advances.)
        if (kind === "form_step" && record.step > 0 && (summary.fillable ?? 0) === 0) kind = "review";

        if (WALLS.has(kind)) return await park(kind);
        if (kind === "closed") return await finish("stopped", "closed");
        if (kind === "unknown") return await park("unknown_page");

        if (kind === "sign_in") {
          // Marked BEFORE the attempt: whatever happens, the login is tried once.
          if (record.signedIn === true) return await park("sign_in_failed");
          // The saved password is typed only on a known ATS host (the owner's decision); anywhere
          // else the user signs in and presses Resume. Nothing is fetched or marked as tried.
          const allowedHost = record.hosts.at(-1);
          if (!ns.atsHosts.isKnown(allowedHost)) return await park("sign_in_yourself");
          await update({ status: "signing_in", signedIn: true });
          const result = await act(deps.signIn, record, { allowedHost, stop: stopping });
          if (!result?.signedIn) return await park("sign_in_failed");
          await waitChange(fingerprint(url, summary));
          moved();
          continue;
        }

        if (kind === "posting") {
          const mine = sameSite(record.hosts.at(-1), hostOf(record.openUrl)) && sameSite(summary.host, hostOf(record.openUrl));
          if (!mayApply || !mine || !summary.applyId) return await park("posting");
          await update({ status: "advancing" });
          const outcome = await press(frame, summary.applyId, fingerprint(url, summary), { apply: true });
          if (outcome !== "moved") return await park(outcome === "refused" ? "posting" : "no_change");
          moved();
          continue;
        }

        // form_step | review: fill the page, read it again, then judge it.
        if (!pageFilled) {
          // A review page at the first step with nothing on it to fill and no Next is not the end
          // of an application (a chooser, a posting): it is not filled, and not "ready".
          if (kind === "review" && record.step === 0 && record.wrote !== true && (summary.fillable ?? 0) === 0) {
            return await park("unknown_page");
          }
          // `filled` before the fill: one that types and then throws or is stopped has still filled.
          await update({ status: "filling", filled: true });
          const report = await act(deps.fill, record, { limits: { ...RUN_LIMITS, ...options.fillLimits } });
          if (!Array.isArray(report?.fields)) throw new Error("the fill gave no report");
          if (report.stopped) throw HALT;
          if (report.fields.some((f) => WROTE_STATUSES.has(f.status))) await update({ wrote: true });
          const open = openQuestions(report);
          if (open.length) return await park("open_questions", { open });
          pageFilled = true;
          continue;
        }

        if (kind === "review") {
          // "Ready to submit" needs evidence this was the application: a step behind it, or a field
          // this page's fill wrote or confirmed. A start chooser or a posting with a stray control
          // (a job-alert box) has neither.
          if (record.step === 0 && record.wrote !== true) return await park("unknown_page");
          return await finish("ready", null, { readyAt: deps.now(), open: [] });
        }

        const here = fingerprint(url, summary);
        if (tried === 0) {
          if (record.seen.includes(here)) return await park("loop");
          if (record.step >= LIMITS.stepMax) return await park("step_limit");
          await update({ fingerprint: here });
        }
        await update({ status: "advancing" });
        if (await press(frame, verdict.next, here) === "moved") {
          // Remembered only once it moved the page: a press that did nothing leaves this page
          // unseen, so a Resume on it is not mistaken for coming back to it.
          await update({ step: record.step + 1, seen: [...record.seen, here] });
          moved();
          continue;
        }
        // The page may now show errors a fill can fix: refill once, press once more.
        if (tried > 0) return await park("no_change");
        tried = 1;
        pageFilled = false;
      }
    } catch (err) {
      // The reason is a fixed word: an error's text could carry a value from the page or the login.
      return await finish("stopped", err === HALT ? "user" : "error");
    }
  }

  /** The three page-facing deps and the change wait, built from a transport:
   *   broadcast(tabId, message, frameId?) → [{frameId, result}]   every frame of that tab, or just
 *                                                     `frameId` when given (page_broadcast);
 *                                                     a press (Next or Apply) always names its frame
   *   frame0(tabId, message) → result                   the top document only (panel_frame0)
   *   api(path, init) → the parsed JSON body            the backend
   *   tabUrl(tabId), sleep(ms), now()                   the host's
   * `classify` and `advance` carry no user data. `signIn` carries the saved login, and only it. */
  function pageOps({ broadcast, frame0, api, tabUrl, sleep, now }) {
    for (const [name, dep] of Object.entries({ broadcast, frame0, api, tabUrl, sleep, now })) {
      if (typeof dep !== "function") throw new TypeError(`queue-run: missing dep ${name}`);
    }

    const classify = (tabId) => broadcast(tabId, { type: "page_classify" });

    // The press goes to the one frame that named the button (ids are frame-tagged as well).
    async function advance(tabId, frameId, id, opts) {
      const apply = opts?.apply === true;
      const frames = await broadcast(tabId, { type: "page_advance", id, ...(apply ? { apply: true } : {}) }, frameId);
      const answer = (Array.isArray(frames) ? frames : []).find((f) => f.frameId === frameId)?.result;
      return answer?.clicked === true ? { clicked: true } : { clicked: false, why: typeof answer?.why === "string" ? answer.why : "gate" };
    }

    /** Fetch the saved login for this record's job and type it in. The password is a local of this
     * call. Every failure is a fixed word, so no error text can carry a value out. */
    async function signIn(record, { allowedHost, stop } = {}) {
      let login = null;
      try {
        login = await api("/api/companion/job-site-login", {
          method: "POST", body: JSON.stringify({ proposal_id: record.proposalId }),
        });
        if (typeof login?.email !== "string" || typeof login?.password !== "string") {
          return { signedIn: false, why: "login_unavailable" };
        }
      } catch {
        return { signedIn: false, why: "login_unavailable" };
      }
      // A Stop pressed during the fetch must not type the login or press Sign in.
      if (stop?.()) return { signedIn: false, why: "stopped" };
      try {
        const result = await frame0(record.tabId, {
          type: "page_sign_in", email: login.email, password: login.password, allowedHost,
        });
        return result?.signedIn === "clicked" ? { signedIn: true } : { signedIn: false, why: typeof result?.why === "string" ? result.why : "refused" };
      } catch {
        return { signedIn: false, why: "unreachable" };
      } finally {
        login = null;
      }
    }

    /** Poll until the tab's fingerprint differs from `before` (or, with the page unreadable, its
     * address does), `ms` runs out, or `stop()` says so. `{changed, url}`. */
    async function waitForChange(tabId, before, ms, stop) {
      const wasAt = String(before).split("\n")[0];
      const startedAt = now();
      for (;;) {
        const url = await tabUrl(tabId);
        let summary = null;
        try {
          summary = pickFrame(await classify(tabId))?.result.summary ?? null;
        } catch {
          // Mid-navigation: no page to read yet.
        }
        const here = fingerprint(url, summary);
        if (summary ? here !== before : here.split("\n")[0] !== wasAt) return { changed: true, url };
        if (stop?.() || now() - startedAt >= ms) return { changed: false, url };
        await sleep(POLL_MS);
      }
    }

    return { classify, advance, signIn, waitForChange };
  }

  ns.queueRun = { drive, pageOps, fingerprint, pickFrame, LIMITS, RUN_LIMITS, HIDDEN_TABS_OK };
})();
