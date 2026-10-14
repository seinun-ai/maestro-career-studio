/* Maestro CS Companion — the queued run's driver: ONE job, in ONE tab, from its link to Ready to submit.
 *
 * Panel-side and pure, as shared/fill-loop.js is: it touches no `chrome`, `document` or network
 * call. (It reads `ns.decisions.sessionTenant`, which panel.html loads first.) Everything it does to a browser arrives as a dependency (`deps`), so node drives the whole
 * state machine with fakes, and a later move of the host (service worker, offscreen document) is a
 * change of host, not a rewrite (design Part 1). `pageOps` below builds the three page-facing deps
 * from a message transport; the rest (open a tab, fill, save) are the host's.
 *
 * THE STATE MACHINE (record.status; saved at every change and every page boundary)
 *   opening → [signing_in | creating_account] → filling → advancing → (next page: filling → advancing …)
 *     → ready        a review page, filled; the user's Submit is the only thing left. Only with
 *                    evidence it was the application: a step behind it, or a field this page's fill
 *                    wrote or confirmed. A start chooser or a posting with a stray control parks
 *                    `unknown_page` instead. A field-less page with a lone Next after step 0 is
 *                    treated as review too (when unsure whether it is Next or Submit, stop).
 *     → confirming   a ready tab that now shows the confirmation page (Task 20 marks it applied), but
 *                    only on a host the run reached, at the employer (`record.tenant`, as the panel's
 *                    `sessionTenant` reads it) of the page that reached Ready, straight from the
 *                    application's own pages. Any other page the tab moves to, a posting included,
 *                    sets `noAutoMark` (the manual Mark applied is left). A ready tab that shows a form step with a
 *                    real Next again sets `movedOn` (the card offers a Resume that fills it).
 *     → parked       the run needs the user or hit a wall; `why` says which:
 *         captcha | create_account | verify | board_native   the page kind, a wall by design
 *         create_account_failed   the sign-up page did not take the new account (a password rule, an account
 *                          that exists, no change); never retried. After the press the run SETTLES: it reads the page
 *                          every POLL_MS for up to ACCOUNT_SETTLE_MS (the site shows the sign-up form for a while
 *                          before the next page) and calls the account taken as soon as the page reads as anything
 *                          else, failed only for an error that was not there before the press and holds, or a
 *                          sign-up form still showing when the time runs out
 *         sign_in_failed   the saved login did not work; never retried (a lockout)
 *         sign_in_yourself the sign-in page is on a host that is not a known ATS (shared/ats-hosts.js):
 *                          the saved password is not typed there; the user signs in and presses Resume
 *         open_questions   required fields it could not answer or operate; `open` lists them
 *         no_change        Next did nothing, even after one refill
 *         unsure_page      a review page that is not plainly the end (`lastBy`: no real Submit control, or a Next
 *                          still on it), after it held that read for LONE_STABLE reads in a row and its fill and
 *                          scoped fixes were done: never Ready
 *         confirm_page     a page with nothing to fill and only a "Continue" or "Proceed": not pressed
 *         page_errors      the page refused a Next and named what it wants (`open` lists the fields), and
 *                          one repair of exactly those fields did not satisfy it, or none was possible
 *         upload           a required upload box is still empty after the fill and could not be attached
 *                          (Next is never pressed over a known-empty required upload)
 *         loop | step_limit   the same page again, or more than LIMITS.stepMax steps
 *         posting          an Apply it may not press (see below); unknown_page  nothing it knows
 *         chooser          Workday's "Start Your Application" page where the run may not press Apply Manually (below):
 *                          the user presses it in the tab, then Resume
 *         already_applied  a "thank you" page BEFORE the run reached review: not this run's Submit
 *         moved_away       a Resume found the tab on a host the run never navigated to: another
 *                          page must not be filled with this job's answers (not after a park that
 *                          told the user to go somewhere: sign_in_yourself, verify, posting,
 *                          unknown_page; the host they land on joins `hosts`)
 *     → stopped      closed | bad_link | error | user (a Stop; nothing is called after it)
 *   Resume re-enters `drive` on a parked record: the open tab is kept, the page is read again. On the page an
 *   `unsure_page` park named, the Resume FILLS it (the fill never overwrites an answered field) and the user's
 *   word counts as the Ready judgement only for a park whose `lastBy` was a Submit the reader could not be sure of
 *   (`submit_seen`, `submit_context`) or fields with no Next (`fields_no_next`); a page that now reads as a step
 *   is pressed on to its Next, not vouched for. After a
 *   `page_errors` or `upload` park, on the page it parked on (`record.parkedPage`: address and step key), the
 *   page is NOT filled again (the user fixed what was named): after a page_errors park its errors are read and
 *   any that remain get a repair round; after an upload park a required box still empty parks again (a
 *   Resume never attaches); then Next is pressed. On any other page the Resume fills as usual.
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
 *   led to, AND it is the FIRST page this drive() call read after opening the tab itself (a record with `inPlace` did not: its page was the user's, so a posting parks). Never on a
 *   Resume, never after a sign-in: a site that restores a saved draft lands on its review page, which
 *   has no fillable control and an "Apply" that is a Submit. The page refuses a control that would
 *   submit a form, and the press goes to the one frame that named the control. A field-less page
 *   after a fill is the review page, so its "Apply" button is never pressed.
 * - THE START CHOOSER's Apply Manually is the one other link the run follows, by `advance(.., {chooser: true})` (the page
 *   navigates to the checked address; nothing is clicked), and only on the same kind of say-so: the page classified as a
 *   chooser (the reader named exactly that one link, nothing fillable), this is the record's step 0, nothing has been
 *   filled, no sign-in or account was made, the call is not a Resume or a run in place, the page is on the host of the tab
 *   address, and it is either the FIRST page read after the call opened the tab or the ONE read right after the run's own
 *   posting Apply moved the page. The other two links of that page (the resume parser, the last application's answers)
 *   are never named, so never pressed. Any other chooser parks `chooser`.
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
 *   advance(tabId, frameId, id, opts) → {clicked, why}         opts is {apply: true}, {chooser: true} or absent
 *   fill(record, {limits}) → the fill-loop report              signIn(record, {allowedHost, stop}) → {signedIn}
 *   waitForChange(tabId, before, ms, stop, baseline) → {changed, url, errors, sameStep, fresh}
 *                                `baseline`: the error keys the page showed before the press
 *   pageErrors(tabId, frameId) → {count, items: [{label, target, kind}]}   what the page complains about
 *   uploads(record) → [{label, target, kind, required, occupied}]   the page's upload boxes, for a Resume's look
 *   attachTo(record, box) → {attached}   the run's PDF into the one box `{label, target}` names: a box the
 *                                page itself named, or the ONE required empty box the fill's report found
 *                                (never one labelled for another document; at most one write per page)
 *   fix(record, errors, {limits}) → {fixed}  repairs ONLY the fields the errors name; the driver then presses once more
 *   sleep(ms) · save(record) · onUpdate(record) · now() · cancelled(record)
 *                                (save is the host's: it owns the list)
 *   pageOps() builds classify, pageErrors, advance, signIn and waitForChange from a message transport.
 *
 * A REJECTED NEXT IS NOT A MOVE. A press that leaves the address and the step heading where they
 * were while the page shows errors is "rejected": `step` and `seen` do not change (the banner's own
 * buttons are out of the fingerprint, and a rejection is caught even if they were not). The driver
 * reads the errors, hands them to `fix`, and presses once more; the same error again, or one `fix`
 * cannot repair, parks `page_errors` naming the fields. The rest of the page is never refilled. It is a
 * rejection when the error is new on the same step (or nothing else changed); a page that moved past
 * a standing error line is a move.
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
  // The parks a Resume may vouch for: no Next beside the fields, or a Submit the reader could not see or a dialog that asked.
  // Not `several_next`: a real Next is on the page, and pressing it is the user's.
  const VOUCHABLE = new Set(["submit_seen", "submit_context", "fields_no_next"]);
  const OPEN_STATUSES = new Set(["needs_answer", "cannot_operate"]);
  // A fill "wrote or confirmed" a field when it ended in one of these (not unconfirmed, yours, blocked).
  const WROTE_STATUSES = new Set(["verified", "closest", "assumed", "already", "partial"]);
  const WALLS = new Set(["captcha", "create_account", "verify", "board_native"]);
  // The parks whose card tells the user to go somewhere themselves (sign in, enter a code, open the
  // application form): where they land on Resume is theirs, and the run follows them there.
  const USER_NAVIGATES = new Set(["sign_in_yourself", "verify", "posting", "unknown_page", "chooser"]);
  // The pages an application is made of, for a ready tab that stays on them. Not a posting: after
  // Ready that is another job being looked at, and an application sent by hand is not this one's.
  const APPLICATION_PAGES = new Set(["review", "form_step"]);
  const DEPS = ["openTab", "classify", "advance", "fill", "signIn", "waitForChange", "tabUrl",
    "sleep", "save", "onUpdate", "now", "cancelled", "pageErrors", "pageRequired", "fix", "attachTo", "uploads", "createAccount"];
  // The fill just wrote the file: the page may be slow to show its row, and a second copy is what the hedge is for.
  const FILE_WRITTEN = new Set(["attached", "unconfirmed"]);
  const MAX_FIX_ROUNDS = 3;   // repairs on one page; each error is repaired once
  // Errors already on the page before the press must stay this long, the page otherwise unchanged, to
  // count as the press's rejection (a slow save leaves the old banner up for a while).
  const REJECT_HOLD_MS = 3000;
  const REJECT_HOLD_STANDING_MS = 8000;
  // After Create Account the site shows the sign-up form for a while before it shows the next page: the run waits this long
  // for the page to move before it calls the account not created.
  const ACCOUNT_SETTLE_MS = 20000;
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
    // The error summary's own buttons are the banner's, not the step's: a rejected Next adds them.
    const buttons = (summary?.buttons ?? []).filter((b) => b.visible !== false && b.inErrors !== true).map((b) => b.text).sort().join(",");
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
      || (f.result.summary.buttons ?? []).some((b) => b.visible !== false && b.errorLine !== true && b.fieldControl !== true
        && ns.pageKind.sortButton(b) === "submit"));
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

  // A required field it could not answer or operate parks. So does a field the page itself flags
  // invalid that the reader did not see as required (no star, no aria-required): after a Next that
  // did nothing, the page's complaint is the better witness, and the park then names the field
  // instead of ending as `no_change` after a refill.
  const openQuestions = (report) => report.fields
    .filter((f) => OPEN_STATUSES.has(f.status) && (f.required || (f.status === "needs_answer" && f.invalid === true)))
    .map((f) => ({ fid: f.fid, question: String(f.question ?? "").slice(0, MAX_QUESTION), required: Boolean(f.required) }));

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
    const park = (why, extra = {}) => finish("parked", why, { open: [], ...extra,
      ...(why === "page_errors" || why === "upload" || why === "unsure_page" ? { parkedPage: thisPage } : {}) });

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
    let chooserNext = false; // the run's own posting Apply moved the page: the one read after it may be the start chooser
    let inPlaceFirst = false;  // a run in place has not read its first page yet
    let navigated = false;   // the last thing the run did moved the tab: its address is the run's own
    let pageFilled = false;  // this page has had its fill (judged afresh after it)
    let tried = 0;           // Next presses on this page that did nothing
    let movedChecked = false;  // a Resume's first read has been checked against the hosts the run reached
    let fixRounds = 0;       // repairs after a rejected Next on this page
    let listed = null;       // how many fields the last fill on this page reported (null: none yet)
    let hadUpload = false;   // the page held an upload box the fill wrote or listed: it is a step, not an "are you sure" page
    let refilled = false;    // fields that showed up after an empty fill have had their one more fill
    let vouched = false;     // a Resume on the very page that parked "unsure": the user says it is the last one
    let requiredTried = false;  // the one scoped fix for required boxes still empty on this review page
    let unsureRun = { print: null, reads: 0, since: 0 };  // the same not-sure review read, how many times in a row
    let attempted = new Set();  // the errors already repaired on this page (by their label)
    let wroteResume = false; // the resume has been written on this page (by the fill's attach or the gate): never twice
    let resumeWhy = null;    // a Resume after page_errors or upload: decided on the first read, by whether it is the parked page
    let recheck = null;      // ... and then: don't refill, look at the page's errors or upload boxes
    let thisPage = null;     // {where, key} of the page being read: remembered when a park names a page

    const noteHost = async (url) => {
      const host = hostOf(url);
      if (host && host !== record.hosts.at(-1)) await update({ hosts: [...record.hosts, host] });
    };
    const waitFor = (before, baseline = []) => act(deps.waitForChange, record.tabId, before, LIMITS.changeMs, stopping, baseline);
    const waitChange = async (before) => (await waitFor(before))?.changed === true;
    // "refused" (the page would not press it: the button went, or turned into a Submit), "rejected"
    // (the page stayed where it was and shows errors: whatever else changed, this is NOT a move),
    // "same" (pressed, the page did not change) or "moved". The wait is skipped for a refusal.
    const press = async (frame, id, before, opts, baseline = []) => {
      const pressed = await act(deps.advance, record.tabId, frame.frameId, id, opts);
      if (pressed?.clicked !== true) return "refused";
      const waited = await waitFor(before, baseline);
      // Errors on the same step are the press's refusal when one is NEW (not on the page before it) or when
      // nothing else changed. A standing line ("Fields marked * are required") on a page that moved is no refusal.
      if ((waited?.errors ?? 0) > 0 && waited?.sameStep === true && (waited.fresh === true || waited.changed !== true)) return "rejected";
      return waited?.changed === true ? "moved" : "same";
    };
    const moved = () => {
      navigated = true;
      pageFilled = false;
      tried = 0;
      fixRounds = 0;
      requiredTried = false;
      unsureRun = { print: null, reads: 0, since: 0 };
      vouched = false;
      listed = null;
      hadUpload = false;
      refilled = false;
      attempted = new Set();
      wroteResume = false;
      record.attach = null;
      // What the fill learnt on the page it just left is about that page (host sets it again when needed).
      record.memory = null;
    };
    // The page's errors as the park's `open` list: the field's own wording, and the fid when it is a fill field.
    const errorsOpen = (items) => items.map((it) => ({
      fid: it.kind === "field" && typeof it.target === "string" ? it.target : null,   // an upload box has no fid
      question: String(it.label ?? "").slice(0, MAX_QUESTION), required: true,
    }));

    // One repair round for the errors a page names: null to press again, else the park that ends the run. The
    // same error back after a repair, one that cannot be repaired, or too many rounds, parks naming them.
    const repair = async (items) => {
      const open = errorsOpen(items);
      const key = (it) => String(it.label ?? "").toLowerCase();
      if (!items.length || items.some((it) => attempted.has(key(it))) || fixRounds >= MAX_FIX_ROUNDS) {
        return await park("page_errors", { open });
      }
      for (const it of items) attempted.add(key(it));
      fixRounds += 1;
      await update({ status: "filling" });
      const repaired = await act(deps.fix, record, items, { limits: { ...RUN_LIMITS, ...options.fillLimits } });
      return repaired?.fixed === true ? null : await park("page_errors", { open });
    };

    // Read what the page names as wrong in this frame and repair exactly that: null to go on, else the park.
    const repairNamed = async (frame) => {
      const found = await act(deps.pageErrors, record.tabId, frame.frameId);
      return await repair(Array.isArray(found?.items) ? found.items : []);
    };

    // The account settle: after Create Account the site keeps showing the sign-up form (and may show errorish text that
    // was already there) for a while before it shows the next page. Poll every POLL_MS for up to ACCOUNT_SETTLE_MS, the
    // errors of the pre-press read as the baseline. Answers "taken", "failed" or "blank".
    //   taken   a verify, captcha or sign-in page (the main loop parks or signs in as it does for any page); a Workday read
    //           whose header Sign In button is gone with fewer than two password boxes and a Next in the step; or any
    //           other page that is no longer the sign-up form AND has left it (another address or step heading: a failed
    //           sign-up redrawn without its password boxes is the same page).
    //   failed  the sign-up form with an error that was NOT there before the press, held for REJECT_HOLD_MS; or, when the
    //           time runs out, the sign-up form or a page that never left it.
    //   blank   the time ran out on a page that stayed blank: nothing says the site refused, so the main loop judges it
    //           (the old unknown_page park).
    const accountTaken = async (before, beforeUrl) => {
      const baseline = new Set(before.errorKeys ?? []);
      const [wasAt, wasKey] = fingerprint(beforeUrl, before).split("\n");
      const startedAt = deps.now();
      let heldSince = null;
      let last = "blank";
      for (;;) {
        await act(deps.sleep, POLL_MS);
        const read = pickFrame(await act(deps.classify, record.tabId));
        const seen = read?.result.summary ?? null;
        if (seen) {
          const now = ns.pageKind.classify(seen).kind;
          const [at, key] = fingerprint(await act(deps.tabUrl, record.tabId), seen).split("\n");
          last = now === "unknown" ? "blank" : "failed";   // a read that does not return "taken" below is the sign-up page still
          if (["verify", "captcha", "sign_in"].includes(now)) return "taken";
          if (now !== "create_account" && now !== "unknown") {
            // Workday's header drops its Sign In button once signed in; otherwise the page has to have left the sign-up page.
            if (seen.headerSignIn === false || at !== wasAt || key !== wasKey) return "taken";
          }
          if (now === "create_account") {
            if (ns.pageKind.signedUpRead(seen)) return "taken";
            if ((seen.errorKeys ?? []).some((k) => !baseline.has(k))) {
              heldSince ??= deps.now();
              if (deps.now() - heldSince >= REJECT_HOLD_MS) return "failed";
            } else {
              heldSince = null;
            }
          }
        }
        if (deps.now() - startedAt >= ACCOUNT_SETTLE_MS) return last === "blank" ? "blank" : "failed";
      }
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
      const userNavigates = USER_NAVIGATES.has(record.why);
      // After a page_errors or upload park the user fixed what was named: if the tab is still on that page
      // (the first read decides) it is not filled again; its errors or upload boxes are looked at, then Next.
      if (resumed && (record.why === "page_errors" || record.why === "upload" || record.why === "unsure_page")) resumeWhy = record.why;
      if (record.tabId == null) {
        const host = hostOf(record.openUrl);
        if (!host) return await finish("stopped", "bad_link");
        await update({ status: "opening", why: null, open: [], startedAt: record.startedAt ?? deps.now(), hosts: [host] });
        gate();
        // The tab id is kept before Stop is asked again: a tab the run opened must stay findable.
        await update({ tabId: await deps.openTab(record.openUrl, stopping) });
        gate();
        navigated = true;
        // A run in place did not open its tab: the page was the user's, so a posting's Apply is theirs.
        applyOk = record.inPlace !== true;
        inPlaceFirst = record.inPlace === true;
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
        const mayChoose = mayApply || chooserNext;
        chooserNext = false;
        {
          const [where, key] = fingerprint(url, summary).split("\n");
          thisPage = { where, key };
          if (resumeWhy) {
            const parked = record.parkedPage;
            // An empty step key proves nothing (the page named no heading): that page is filled as usual.
            // An empty step key proves nothing for a fix or an upload, but a review page may simply have no
            // heading: the address alone then says it is the page the user was asked to look at.
            const vouching = resumeWhy === "unsure_page";
            if (parked && (vouching || parked.key !== "") && parked.where === where && parked.key === key) {
              recheck = resumeWhy;
              if (vouching) {
                // The page is filled as any Resume's is (the fill answers nothing that already holds an answer); the
                // user's word that it is the last page feeds the Ready judgement only, and only for a park that was
                // about a Submit. What an earlier attach wrote (even one the page never confirmed) is not written twice.
                pageFilled = false;
                vouched = VOUCHABLE.has(record.lastBy);
                wroteResume = FILE_WRITTEN.has(record.attach?.outcome);
              } else {
                pageFilled = true;
              }
            } else {
              // The user moved on by hand: nothing the park learnt is about this page (what moved() clears).
              fixRounds = 0;
              requiredTried = false;
              attempted = new Set();
              wroteResume = false;
              record.attach = null;
              record.memory = null;
            }
            resumeWhy = null;
            record.parkedPage = null;
          }
        }
        // A run in place drives the page the user picked it for. By the first read the tab may have gone
        // elsewhere (the pick, the press and the run are not one instant): that page is not this job's.
        const checkPlace = inPlaceFirst;
        inPlaceFirst = false;
        if (checkPlace && url && !ns.decisions.samePosting(record.openUrl, url)) return await park("moved_away");
        if (arrived) {
          navigated = false;
          await noteHost(url);
        }
        // A Resume finds the tab where the user left it. On a host the run never navigated to it is
        // another page, and it is not filled with this job's answers. (A ready tab is only watched,
        // and a park that asked the user to navigate, to sign in, enter a code or open the
        // application form, is exempt: where they land is theirs, and its host joins the run's.)
        if (resumed && !arrived && record.readyAt == null && !movedChecked) {
          movedChecked = true;
          if (userNavigates) await noteHost(url);
          else if (url && record.hosts.length && !record.hosts.includes(hostOf(url))) return await park("moved_away");
        }
        const verdict = ns.pageKind.classify(summary);
        // A Resume's word that this was the last page is void once the page reads as a step with a real Next.
        if (vouched && verdict.kind === "form_step") vouched = false;
        let kind = verdict.kind;
        let by = verdict.by ?? null;   // why a review is a review (page-kind.js); only a real Submit control ends an application

        // A finished run only watches for the confirmation of the user's own Submit, and only believes
        // one that follows the application itself: on a host the run reached, with every read since
        // Ready on the application's own pages (a page not drawn yet says nothing). Anything else the
        // tab shows (a "thank you" for another employer, a candidate portal, a page the user browsed
        // to after deciding against Submitting) ends the auto-mark; the manual Mark applied is left.
        if (record.readyAt != null) {
          if (record.noAutoMark === true || kind === "unknown") return record;
          // A shared ATS host serves every employer (Greenhouse, Lever, Ashby): the host alone proves
          // nothing, so the page must also be the employer the Ready page was.
          const sameEmployer = !record.tenant || ns.decisions.sessionTenant(url) === record.tenant;
          const here = record.hosts.includes(hostOf(url)) && sameEmployer;
          if (here && kind === "confirmation") return await finish("confirming", null);
          if (here && APPLICATION_PAGES.has(kind)) {
            // A ready tab the user took back to a form step (a real Next on it): the card says so and offers a
            // Resume; coming back to a review clears it.
            const movedOn = kind === "form_step";
            if ((record.movedOn === true) !== movedOn) await update({ movedOn });
            return record;
          }
          await update({ noAutoMark: true });
          return record;
        }
        // A "thank you" page before the run reached review is an application someone else sent
        // (a draft this browser's session already submitted): not ready, not this run's to mark.
        if (kind === "confirmation") return await park("already_applied");
        // A field-less page with an Apply after a fill (or after a step) is the review page.
        if (kind === "posting" && (record.filled === true || record.step > 0)) {
          kind = "review";
          by = "submit_button";   // its Apply is a Submit-worded button
        }
        // A sign-up page on a known ATS host: the run creates the account with the saved login, once (owner
        // decision 2026-10-14). Everywhere else, and for anything the page refuses, it is still a wall.
        if (kind === "create_account") {
          // Seen again after the press: the site did not take it (a password rule, an account that exists). An
          // email-check page that reads as one parks `verify` by itself; nothing here says it was one.
          if (record.accountTried === true) return await park("create_account_failed");
          const allowedHost = record.hosts.at(-1);
          if (!ns.atsHosts.isKnown(allowedHost)) return await park("create_account");
          // Marked BEFORE the press, as the sign-in is: a Stop that lands during it still leaves the attempt
          // made, so a Resume never creates a second account. A refusal that pressed nothing unmarks it.
          await update({ status: "creating_account", accountTried: true });
          const made = await act(deps.createAccount, record, { allowedHost, stop: stopping });
          if (!made?.created) {
            await update({ accountTried: false });
            return await park("create_account");
          }
          if ((await accountTaken(summary, url)) === "failed") return await park("create_account_failed");
          moved();
          continue;
        }
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
          chooserNext = true;
          continue;
        }

        // The start chooser: pressed on the narrow say-so in the header, else it is the user's to press.
        if (kind === "chooser") {
          const allowed = mayChoose && !resumed && record.inPlace !== true && record.step === 0 && record.filled !== true
            && record.signedIn !== true && record.accountTried !== true
            && sameSite(summary.host, hostOf(url)) && record.hosts.includes(hostOf(url));
          if (!allowed) return await park("chooser");
          await update({ status: "advancing" });
          const outcome = await press(frame, summary.chooserId, fingerprint(url, summary), { chooser: true });
          if (outcome !== "moved") return await park(outcome === "refused" ? "chooser" : "no_change");
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
          listed = report.fields.length;
          if (report.fields.some((f) => WROTE_STATUSES.has(f.status))) await update({ wrote: true });
          const open = openQuestions(report);
          if (open.length) return await park("open_questions", { open });
          // Never press Next over a required upload known to be empty, and never write the resume twice on
          // a page. The one box the fill's attach wrote is exempt; of the rest, a lone box that is not
          // labelled for another document gets the targeted attach, and anything else parks naming them.
          const need = report.attach;
          if (FILE_WRITTEN.has(need?.outcome)) wroteResume = true;
          hadUpload = wroteResume || (Array.isArray(need?.boxes) && need.boxes.length > 0);
          const boxes = Array.isArray(need?.boxes) ? need.boxes.filter((box) => box.written !== true) : [];
          if (need?.required === true) {
            const lone = boxes.length === 1 && boxes[0].kind !== "other" && boxes[0].kind !== "parser" && !wroteResume;
            if (!lone) return await park("upload", { open: errorsOpen(boxes) });
            const got = await act(deps.attachTo, record, boxes[0]);
            if (got?.attached !== true) return await park("upload", { open: errorsOpen(boxes) });
            wroteResume = true;
          }
          pageFilled = true;
          continue;
        }

        // A fill that listed nothing on a page that reports fillable controls (Workday's question steps draw their
        // popups after the footer, and a page that showed one other control at the fill still lists none of them) is
        // filled once more before anything else is judged.
        if (listed === 0 && (summary.fillable ?? 0) > 0 && !refilled) {
          refilled = true;
          pageFilled = false;
          continue;
        }

        // Later than the first page, a page the fill found NOTHING on and one button: a plain Next ("Next",
        // "Save and continue") is a step like any other (a page of cards). A bare "Continue" or "Proceed" there
        // may be a final "are you sure" page's, so it parks for the user rather than being pressed. What the fill
        // LISTED decides, not the reader's count, which lags a page that draws its fields late. (An intro page at
        // step 0 still advances.)
        if (kind === "form_step" && record.step > 0 && listed === 0 && !hadUpload) {
          const lone = (summary.buttons ?? []).find((b) => b.id === verdict.next);
          if (!ns.pageKind.isPlainNext(lone?.text)) return await park("confirm_page");
        }

        if (kind === "review") {
          // "Ready to submit" needs evidence this was the application: a step behind it, or a field
          // this page's fill wrote or confirmed. A start chooser or a posting with a stray control
          // (a job-alert box) has neither.
          if (record.step === 0 && record.wrote !== true) return await park("unknown_page");
          // And it needs a page that is the END of one: a real Submit control and no real Next. Every other
          // reason a page reads as a review (a Submit the reader could not see, a dialog that asks, several
          // Nexts, fields and no Next) means "stop, not sure": never Ready.
          await update({ lastBy: by });
          // A vouch is for the reason the Resume was given for: a read that now shows several Nexts is not vouched.
          const unsure = by !== "submit_button" && !(vouched && VOUCHABLE.has(by));
          // The page still complains: one repair of what it names, as after a rejected Next; the same
          // complaint again parks naming it.
          if ((summary.errors ?? 0) > 0) {
            const stop = await repairNamed(frame);
            if (stop) return stop;
            continue;
          }
          // A required box still empty: one scoped fix of exactly those, then they must be filled. The
          // resume this page's attach already wrote is excused (its row may not show a file name). This comes
          // BEFORE an unsure verdict: a page with boxes empty gets its fix (or names them) first.
          if ((summary.requiredEmpty ?? 0) > 0) {
            const found = await act(deps.pageRequired, record.tabId, frame.frameId);
            // ONE box is the resume already written; a second required box is not it, and the user chooses.
            let excused = false;
            const pending = (Array.isArray(found?.items) ? found.items : []).filter((one) => {
              if (one.kind !== "upload" || !wroteResume || one.box === "other" || excused) return true;
              excused = true;
              return false;
            });
            // The resume goes in a resume box and nowhere else: a box for another document (or the site's own
            // import), and a choice between several, are the user's.
            const uploads = pending.filter((one) => one.kind === "upload");
            if (uploads.some((one) => one.box === "other" || one.box === "parser") || uploads.length > (excused ? 0 : 1)) {
              return await park("upload", { open: errorsOpen(pending) });
            }
            if (pending.length) {
              const open = errorsOpen(pending);
              if (requiredTried) return await park("open_questions", { open });
              requiredTried = true;
              await update({ status: "filling" });
              const repaired = await act(deps.fix, record, pending, { limits: { ...RUN_LIMITS, ...options.fillLimits } });
              if (repaired?.fixed !== true) return await park("open_questions", { open });
              continue;
            }
          }
          // Not sure it is the last page: the read must hold, unchanged, for LONE_STABLE reads in a row (about 2 s)
          // before the run stops. A step half drawn reads as fields and no Next for a moment, and the user
          // is asked about a page that is not the last one.
          if (unsure) {
            const print = `${by}\n${fingerprint(url, summary)}`;
            unsureRun = print === unsureRun.print
              ? { ...unsureRun, reads: unsureRun.reads + 1 }
              : { print, reads: 1, since: unsureRun.since || deps.now() };
            if (unsureRun.reads < LONE_STABLE && deps.now() - unsureRun.since < LIMITS.changeMs) {
              await act(deps.sleep, POLL_MS);
              continue;
            }
            return await park("unsure_page");
          }
          return await finish("ready", null, { readyAt: deps.now(), open: [], readyBy: by === "submit_button" ? by : "user", tenant: ns.decisions.sessionTenant(url) });
        }

        const here = fingerprint(url, summary);
        if (tried === 0 && fixRounds === 0) {
          if (record.seen.includes(here)) return await park("loop");
          if (record.step >= LIMITS.stepMax) return await park("step_limit");
          await update({ fingerprint: here });
        }
        await update({ status: "advancing" });
        if (recheck) {
          const was = recheck;
          recheck = null;
          if (was === "upload") {
            // Never attach on a Resume: only look. A required box still empty parks again, naming it.
            const found = await act(deps.uploads, record);
            let empty = (Array.isArray(found) ? found : []).filter((box) => box.required === true && box.occupied !== true);
            // A write the page may have taken but did not show (unconfirmed) leaves its box looking empty: that box
            // is excused, by the tag the write recorded, or, if the page redrew it, when it is the only one left.
            const written = record.attach?.outcome === "unconfirmed" ? record.attach.target : null;
            if (typeof written === "string") {
              const rest = empty.filter((box) => box.target !== written);
              if (rest.length < empty.length) empty = rest;   // found by its tag
              else if (empty.length === 1) empty = [];        // redrawn: the only box left is taken to be it
            }
            if (empty.length) return await park("upload", { open: errorsOpen(empty) });
          }
          if (was === "page_errors") {
            const standing = await act(deps.pageErrors, record.tabId, frame.frameId);
            if (Array.isArray(standing?.items) && standing.items.length) {
              const stop = await repair(standing.items);
              if (stop) return stop;
              continue;
            }
          }
        }
        const outcome = await press(frame, verdict.next, here, undefined, summary.errorKeys ?? []);
        if (outcome === "moved") {
          // Remembered only once it moved the page: a press that did nothing leaves this page
          // unseen, so a Resume on it is not mistaken for coming back to it.
          await update({ step: record.step + 1, seen: [...record.seen, here] });
          moved();
          continue;
        }
        if (outcome === "rejected") {
          // The page refused and says why. Not a step, not a seen page: read what it names, repair
          // exactly that, press again. The same error back, or one that cannot be repaired, parks.
          const stop = await repairNamed(frame);
          if (stop) return stop;
          continue;
        }
        // The page may now show errors a fill can fix: refill once, press once more.
        if (tried > 0) return await park("no_change");
        tried = 1;
        pageFilled = false;
      }
    } catch (err) {
      // A read that fails on a ready tab (mid-navigation, in the middle of the user's own Submit) is
      // not a failed run: it stays ready, unsaved and still vouched for, and the next read tries again.
      if (err !== HALT && record.readyAt != null && record.status === "ready") return record;
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

    /** What the frame that was read says of the page: `{count, items: [{label, target, kind}]}`, words and
     * handles only. A frame that did not answer says there is nothing. */
    async function itemsFrom(tabId, frameId, message) {
      const frames = await broadcast(tabId, message, frameId);
      const answer = (Array.isArray(frames) ? frames : []).find((f) => f.frameId === frameId)?.result;
      return Array.isArray(answer?.items) ? { count: answer.items.length, items: answer.items } : { count: 0, items: [] };
    }
    /** What the page complains about (`page_errors`). */
    const pageErrors = (tabId, frameId) => itemsFrom(tabId, frameId, { type: "page_errors" });
    /** The required boxes still empty (`page_required`). */
    const pageRequired = (tabId, frameId) => itemsFrom(tabId, frameId, { type: "page_required" });

    // The press goes to the one frame that named the button (ids are frame-tagged as well).
    async function advance(tabId, frameId, id, opts) {
      const apply = opts?.apply === true;
      const chooser = opts?.chooser === true;
      const frames = await broadcast(tabId, { type: "page_advance", id, ...(apply ? { apply: true } : {}), ...(chooser ? { chooser: true } : {}) }, frameId);
      const answer = (Array.isArray(frames) ? frames : []).find((f) => f.frameId === frameId)?.result;
      return answer?.clicked === true ? { clicked: true } : { clicked: false, why: typeof answer?.why === "string" ? answer.why : "gate" };
    }

    /** Fetch the saved login for this record's job and send it to the top document in ONE call (`message`: `page_sign_in` or
     * `page_create_account`; `key` is the answer's word for "done": `signedIn` or `created`).
     * The password is a local of this call, never kept. Every failure is a fixed word, so no error text can
     * carry a value out. */
    async function withLogin(record, { allowedHost, stop } = {}, key, message) {
      let login = null;
      const no = (why) => ({ [key]: false, why });
      try {
        login = await api("/api/companion/job-site-login", {
          method: "POST", body: JSON.stringify({ proposal_id: record.proposalId }),
        });
        if (typeof login?.email !== "string" || typeof login?.password !== "string") return no("login_unavailable");
      } catch {
        return no("login_unavailable");
      }
      // A Stop pressed during the fetch must not type the login or press anything.
      if (stop?.()) return no("stopped");
      try {
        const result = await frame0(record.tabId, { ...message, email: login.email, password: login.password, allowedHost });
        return result?.[key] === "clicked" ? { [key]: true } : no(typeof result?.why === "string" ? result.why : "refused");
      } catch {
        return no("unreachable");
      } finally {
        login = null;
      }
    }
    const signIn = (record, options) => withLogin(record, options, "signedIn", { type: "page_sign_in" });
    /** The same login typed to create the account (a sign-up page on a known ATS host). */
    const createAccount = (record, options) => withLogin(record, options, "created", { type: "page_create_account" });

    /** Poll until the tab's fingerprint differs from `before` (or, with the page unreadable, its
     * address does), `ms` runs out, or `stop()` says so. `{changed, url, errors, sameStep, fresh}`:
     * `errors` is what the page shows now, `sameStep` whether its address and step heading are those of
     * `before` (a page with no heading is unknown, not the same), and `fresh` whether it names an error
     * that was not on the page before the press (`baseline`: the error keys the page showed then). A page
     * that stays put with a fresh error is a rejected Next and ends the wait at once; the same errors
     * as before must stay for a while first, since a slow save also leaves the old banner up. */
    async function waitForChange(tabId, before, ms, stop, baseline = []) {
      const [wasAt, wasKey] = String(before).split("\n");
      const known = new Set(Array.isArray(baseline) ? baseline : []);
      const hold = known.size ? REJECT_HOLD_STANDING_MS : REJECT_HOLD_MS;
      const startedAt = now();
      let heldSince = null;
      for (;;) {
        const url = await tabUrl(tabId);
        let summary = null;
        try {
          summary = pickFrame(await classify(tabId))?.result.summary ?? null;
        } catch {
          // Mid-navigation: no page to read yet.
        }
        const here = fingerprint(url, summary);
        const [nowAt, nowKey] = here.split("\n");
        const sameStep = summary !== null && nowAt === wasAt && nowKey !== "" && nowKey === wasKey;
        const errors = summary?.errors ?? 0;
        const fresh = (summary?.errorKeys ?? []).some((key) => !known.has(key));
        if (summary ? here !== before : nowAt !== wasAt) return { changed: true, url, errors, sameStep, fresh };
        if (sameStep && errors > 0) {
          heldSince ??= now();
          if (fresh || now() - heldSince >= hold) return { changed: false, url, errors, sameStep, fresh };
        } else {
          heldSince = null;
        }
        if (stop?.() || now() - startedAt >= ms) return { changed: false, url, errors, sameStep, fresh };
        await sleep(POLL_MS);
      }
    }

    return { classify, pageErrors, pageRequired, advance, signIn, createAccount, waitForChange };
  }

  ns.queueRun = { drive, pageOps, fingerprint, pickFrame, LIMITS, RUN_LIMITS, HIDDEN_TABS_OK };
})();
