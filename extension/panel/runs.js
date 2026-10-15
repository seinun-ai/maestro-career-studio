/* Maestro CS Companion — a queued run in the Next card: what one job's record looks like, in words.
 *
 * A RENDERER, like the stage bodies, and under their rule: NOTHING HERE REACHES FOR ANYTHING. No
 * `card`, no `chrome`, no network. It is handed the stage context (`stageContext()` in panel.js)
 * and builds elements with the builders it is handed; the record it draws is `ctx.facts.run`, a
 * copy of the plain data `shared/queue-run.js` keeps and `actions/run.js` mutates, and a button
 * changes anything only by firing a callback on `ctx.act`. The Fill body (`stages/fill.js`) calls
 * `render` instead of its own report while the bound tab has a run, and `renderRail` takes the
 * card's title and eyebrow from `title` and `working`.
 *
 * ONE CARD, FIVE KINDS OF STATE (design Part 5, direction C's "one next step"):
 *   working     opening, signing in, filling page N: a progress bar, the pages so far, Stop; while the reasoning step
 *               works, its live line (`run.thinking`), and after it moved the run on, one sentence (`run.sorted`)
 *   Needs you   parked: why in the user's words, what to do, Resume, Skip this job; after the reasoning step, its note,
 *               what it asked of the user and what it tried (`run.thought`), as plain text
 *   Ready       a review page, filled: the answers to check; the Submit press is the user's (Done
               ends the record without marking anything)
 *   Marking     the confirmation page was seen: "Marking applied in 8 s · Undo"
 *   finished    Applied, or Stopped with the reason
 * There is no Submit control anywhere in it. Nothing the Companion does ever presses one, and the
 * card never offers the user a way to ask it to.
 *
 * `canResume` and `canSkip` are the Resume/Skip rule for every `why` the driver can park or stop
 * with (and the three the host adds), in one table with the copy beside it, so the words and the
 * buttons cannot drift apart. `actions/run.js` asks the same two functions before it acts.
 *
 * WHAT THIS FILE PUBLISHES: ns.panelRuns = { render, title, working, canResume, canSkip, REASONS }.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  const FIXED_LINE = "It clicks Next for you. It never clicks Submit.";
  const WALL_STEP = "Do this step in the tab, then Resume.";

  // why → [the short reason, what to do]. The short words are the ones the run list (Phase 3) will
  // reuse; the second string is the card's sentence.
  const PARKS = {
    open_questions: ["Questions on this page",
      "Answer them in the page, then press Resume. Your answers are saved to your profile."],
    page_errors: ["The page asks for more",
      "The page wouldn't move on and names what it needs. Fix those in the tab, then press Resume."],
    upload: ["Resume not attached",
      "The page needs a file in the upload box below, and the Companion couldn't attach your resume. Attach it in the tab, then press Resume."],
    captcha: ["CAPTCHA", WALL_STEP],
    create_account: ["Create an account", WALL_STEP],
    verify: ["Email code", WALL_STEP],
    sign_in_failed: ["Sign-in didn't work", WALL_STEP],
    create_account_failed: ["Account not created",
      "The site didn't take the new account (a password rule, or an account that already exists). "
      + "Create it or sign in yourself in the tab, then press Resume."],
    sign_in_yourself: ["Sign in yourself",
      "This isn't a site the Companion signs in to. Sign in in the tab, then press Resume."],
    posting: ["Apply yourself",
      "The Companion didn't press this page's Apply. Open the application form in the tab, then press Resume."],
    // The default, for a record that names no `lastBy`; UNSURE says it per reason.
    unsure_page: ["Not sure about this page",
      "The Companion isn't sure what this page is. Check it in the tab, then press Resume. Submit stays yours."],
    confirm_page: ["Check this page",
      "This page has only a Continue button, and the Companion can't tell whether it sends the application. "
      + "Check it in the tab, then press Resume or go on yourself."],
    chooser: ["Choose how to apply",
      "Press Apply Manually in the tab, then Resume."],
    unknown_page: ["Page not recognised",
      "The Companion doesn't recognise this page. Get to the application form in the tab, then press Resume."],
    // The extension was updated while this page was open: its old and new scripts disagree until the page is reloaded.
    page_stale: ["Reload the page",
      "The Companion was updated while this page was open. Reload the page, then press Resume."],
    already_applied: ["Already sent?",
      "This page says an application was sent, but the Companion hadn't got that far. "
      + "Check it in the tab. Press Resume if this is the wrong page."],
    moved_away: ["Left the application",
      "The tab is on a different site now. Go back to the application, then press Resume."],
    loop: ["The same page again",
      "The Companion came back to a page it had already filled. Go to the next page yourself, then press Resume."],
    step_limit: ["Too many steps",
      "This application has more pages than one run goes through. Finish it in the tab yourself."],
    no_change: ["The page didn't move on",
      "Next did nothing. Fix what the page asks for, or go to the next page yourself, then press Resume."],
    board_native: ["Apply on the job board",
      "This job board has its own apply button, and the Companion doesn't use it. Apply there yourself."],
  };
  // An unsure page, per why the reader was unsure (`run.lastBy`). Never "the last page" while a real Next is visible.
  const SUBMIT_MAY = ["May send the application",
    "This page may send the application, so the Companion stopped. If it is the last page, check it and press Resume. Submit stays yours."];
  const UNSURE = {
    several_next: ["More than one Next",
      "Several buttons on this page could move on, so the Companion pressed none. Press the right one in the tab, then press Resume."],
    submit_seen: SUBMIT_MAY,
    submit_context: SUBMIT_MAY,
    fields_no_next: ["No Next button found",
      "No Next button found on this page. If it is the last page, press Resume. Otherwise go on in the tab yourself. Submit stays yours."],
  };
  const STOPS = {
    closed: ["Position closed", "This job is no longer taking applications. Not closed? Open the application in the tab, then press Resume."],
    bad_link: ["Bad link", "The saved apply link isn't a web address the Companion can open."],
    error: ["Something went wrong", "The Companion stopped. Nothing was submitted. You can carry on in the tab yourself."],
    user: ["Stopped", "You stopped it. Nothing was submitted."],
    tab_closed: ["Tab closed", "The tab was closed, so the run ended."],
    interrupted: ["Interrupted", "The panel was closed while this ran, so it stopped. Nothing was submitted."],
  };
  const parkWords = (run) => (run.why === "unsure_page" ? UNSURE[run.lastBy] ?? PARKS.unsure_page : PARKS[run.why]);
  const REASONS = Object.fromEntries([...Object.entries(PARKS), ...Object.entries(STOPS)]
    .map(([why, [reason]]) => [why, reason]));

  // Parked: no Resume where the user cannot fix it in the tab (the run has hit its own limit, or the
  // job board's button is the site's). Stopped: only the ones a user may take back.
  const NO_RESUME = new Set(["step_limit", "board_native"]);
  const RESUMABLE_STOPS = new Set(["error", "user", "interrupted", "closed"]);
  // A ready tab the user took back to a form step (`movedOn`) can be resumed to fill that page.
  const canResume = (run) => (run.status === "parked" ? !NO_RESUME.has(run.why)
    : run.status === "ready" ? run.movedOn === true
      : run.status === "stopped" && RESUMABLE_STOPS.has(run.why));
  const canSkip = (run) => run.status === "parked";

  // The walls that stop a run by design, named in a line under each of them.
  const WALLS = [["captcha", "a CAPTCHA"], ["create_account", "creating an account"], ["verify", "an email code"],
    ["sign_in_failed", "a sign-in that didn't work"], ["board_native", "apply on a job board"]];

  const WORKING = new Set(["opening", "signing_in", "creating_account", "filling", "advancing"]);
  const working = (run) => WORKING.has(run.status);

  /** The card's title: the status word. */
  function title(run) {
    switch (run.status) {
      case "opening": return "Opening";
      case "signing_in": return "Signing in";
      case "creating_account": return "Creating account";
      case "filling": case "advancing": return `Filling page ${(run.step ?? 0) + 1}`;
      case "parked": return "Needs you";
      case "ready": return "Ready to submit";
      case "confirming": return "Marking applied";
      case "applied": return "Applied";
      case "stopped": return "Stopped";
      default: return "Waiting";
    }
  }

  function button(ctx, className, id, label, onClick) {
    const el = ctx.build.node("button", className, label);
    el.type = "button";
    el.id = id;
    el.addEventListener("click", onClick);
    return el;
  }

  /** How the resume attach went, in a sentence for the page line; "" before it has tried anything. An
   * "unconfirmed" write already says what to check, so it is shown as it is. */
  function attachLine(attach) {
    if (!attach?.outcome) return "";
    if (attach.outcome === "attached") return "Resume attached";
    if (attach.outcome === "unconfirmed") return attach.text ?? "Couldn't confirm the resume upload.";
    // The run left a box that already held a file: nothing went wrong.
    if (attach.reason === "occupied") return "A file was already attached";
    return `Couldn't attach the resume: ${attach.text ?? "the upload box was left for you."}`;
  }

  /** The bar and the pages so far: a tick and the filled count for each finished page, "k of n" on the
   * one in hand. The bar is the current page's fields, which is all the Companion knows of the length. */
  function pagesList(ctx, run) {
    const { node, attach, icon } = ctx.build;
    const progress = run.progress ?? { done: 0, total: 0 };
    const known = progress.total > 0;
    const bar = node("div", "run-bar");
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-label", "This page");
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", "100");
    const percent = known ? Math.min(100, Math.round((progress.done / progress.total) * 100)) : 0;
    if (known) bar.setAttribute("aria-valuenow", String(percent));
    const fill = node("span", "run-fill");
    fill.style.setProperty("--v", String(percent));
    attach(bar, fill);
    const list = node("ul", "run-pages");
    list.setAttribute("aria-label", "Pages");
    for (const page of run.pages ?? []) {
      if (page.n === (run.step ?? 0) + 1 && working(run)) continue;
      attach(list, attach(node("li", "done"), icon("circle-check", { size: 14 }),
        node("span", null, `Page ${page.n} · ${page.filled} filled`)));
    }
    if (working(run) && run.status !== "opening") {
      attach(list, node("li", "now", `Page ${(run.step ?? 0) + 1}${known ? ` · ${progress.done} of ${progress.total} answered` : ""}`));
    }
    const line = attachLine(run.attach);
    return line ? [bar, list, ctx.build.node("div", "sub", line)] : [bar, list];
  }

  const MAX_NOTE = 200;
  const MAX_LINE = 300;
  const cut = (text, n) => String(text ?? "").slice(0, n);

  const WORKING_LINES = {
    opening: "Opening the employer's application page.",
    signing_in: "Signing in with your saved job-site login.",
    creating_account: "Creating your account with your saved job-site login.",
  };

  function workingBody(ctx, run) {
    const { node, attach } = ctx.build;
    const body = [];
    if (WORKING_LINES[run.status]) body.push(node("div", "sub", WORKING_LINES[run.status]));
    else body.push(...pagesList(ctx, run));
    // The reasoning step's live line, else the one sentence it leaves when it moved the run on. Plain text, and no live
    // region here: the rail is rebuilt on every paint, so the footer note (set as the line changes) is the announcement.
    if (run.thinking) body.push(node("div", "sub run-thinking", cut(run.thinking, MAX_LINE)));
    else if (run.sorted) body.push(node("div", "sub run-sorted", cut(run.sorted, MAX_LINE)));
    body.push(node("div", "sub", FIXED_LINE));
    const stop = button(ctx, "stop", "run-stop", run.stopRequested ? "Stopping…" : "Stop", () => ctx.act.stopRun(run.id));
    stop.disabled = run.stopRequested === true;
    stop.setAttribute("aria-label", "Stop applying");
    return [...body, attach(node("div", "run-actions"), stop)];
  }

  /** The open questions as jump links: the page holds the field, so the link takes the user to it. */
  function questions(ctx, run) {
    const { node, attach } = ctx.build;
    if (!(run.open ?? []).length) return null;
    const list = node("ul", "resid");
    list.setAttribute("aria-label", run.why === "open_questions" ? "Questions on this page" : "What the page asks for");
    for (const one of run.open) {
      const label = one.question || "A field with no label";
      // A field the page named by its words only (an upload box) has nothing to jump to.
      if (!one.fid) {
        attach(list, node("li", null, label));
        continue;
      }
      const jump = node("button", null, label);
      jump.type = "button";
      jump.addEventListener("click", () => ctx.act.focusField(one.fid));
      attach(list, attach(node("li"), jump));
    }
    return list;
  }

  /** What the reasoning step made of a park, in the code's words: what it asked of the user, else what it tried and how each
   * attempt went ("It tried How Did You Hear About Us? a second way; it didn't take."). The model's own note is not shown
   * here (it is on the live Thinking line and in the fill log). What it asked is untrusted text, so it goes in through the
   * builder (textContent), cut, never as markup. */
  function thoughtLines(ctx, thought) {
    const { node } = ctx.build;
    if (!thought || typeof thought !== "object") return [];
    const ask = cut(thought.ask, MAX_NOTE);
    if (ask) return [node("div", "opts run-ask", ask)];
    const tried = (Array.isArray(thought.tried) ? thought.tried : []).slice(0, 6).map((one) => cut(one, 100)).filter(Boolean);
    return tried.map((one) => node("div", "opts run-tried", `It tried ${one}.`));
  }

  function parkedBody(ctx, run) {
    const { node, attach } = ctx.build;
    const [reason, say] = parkWords(run) ?? ["Needs you", "Do this step in the tab, then press Resume."];
    // A run that followed the user into this tab waits for one press here; it never carries on by itself.
    const moved = run.moved === true ? "The run moved to this tab. Press Continue here when this is the page to fill. " : "";
    // After a follow from a tab on another site, "the tab is on a different site" is no longer true: the move says it.
    const said = run.moved === true && run.why === "moved_away" ? "" : say;
    const box = attach(node("div", "needs run-needs"), node("div", "run-reason", reason), node("div", "opts", `${moved}${said}`.trim()),
      ...thoughtLines(ctx, run.thought),
      ["open_questions", "page_errors", "upload"].includes(run.why) ? questions(ctx, run) : null);
    const actions = node("div", "run-actions");
    if (canResume(run)) {
      attach(actions, button(ctx, "save", "run-resume", run.moved === true ? "Continue here" : "Resume", () => ctx.act.resumeRun(run.id)));
    }
    attach(box, actions);
    const out = [box];
    if (canSkip(run)) {
      out.push(button(ctx, "unpick", "run-skip", "Skip this job", () => ctx.act.skipRun(run.id)));
    }
    if (WALLS.some(([why]) => why === run.why)) {
      const others = WALLS.filter(([why]) => why !== run.why).map(([, words]) => words);
      out.push(node("div", "sub count", `It also stops here for: ${others.join(" · ")}`));
    }
    return out;
  }

  /** The rows of "Check before you submit": the last receipt's flags, then the answers the run made for the
   * user on any page (a draft, a date set to the 1st) that the receipt did not name; one that it did gains
   * its note. A row from another page is a name only: its field id means nothing on this one. */
  function checkRows(run) {
    const rows = (run.flags ?? []).map((row) => ({ ...row }));
    for (const one of run.assumedRows ?? []) {
      const same = rows.find((row) => row.question === one.question);
      if (same) {
        if (!same.note && one.note) same.note = one.note;
      } else {
        rows.push({ fid: one.step === (run.step ?? 0) ? one.fid : null, question: one.question,
                    reason: "Answered for you", ...(one.note ? { note: one.note } : {}) });
      }
    }
    return rows;
  }

  /** "Check before you submit": the rows above, each a jump where the field is on this page. */
  function flagsBlock(ctx, run) {
    const { node, attach } = ctx.build;
    const rows = checkRows(run);
    if (!rows.length) return null;
    const head = node("div", "grp", "Check before you submit");
    head.setAttribute("role", "heading");
    head.setAttribute("aria-level", "3");
    const list = node("ul", "resid flags");
    list.setAttribute("aria-label", "Check before you submit");
    for (const row of rows) {
      const name = node(row.fid ? "button" : "span", null, row.question || "A field with no label");
      if (row.fid) {
        name.type = "button";
        name.addEventListener("click", () => ctx.act.focusField(row.fid));
      }
      const note = ns.fillLoop.knownNote(row.note);
      attach(list, attach(node("li"), name, node("span", "kindmark", ` · ${row.reason} `),
        note ? node("span", "row-note", note) : null));
    }
    return attach(node("div", "flagged"), head, list);
  }

  /** When the fill log last recorded a run, in the user's own locale: "Oct 13, 6:27 AM". */
  function whenWords(iso) {
    const at = new Date(iso);
    return Number.isNaN(at.getTime()) ? ""
      : at.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  /** One line when the fill log is off, shown once a run has ended: the log is what lets Maestro CS see what each
   * field tried, and it is the user's switch (Options). It says when the log last recorded a run, if it ever did. */
  function logOffLine(ctx, run) {
    if (run.logOff !== true) return null;
    const when = run.logLast ? whenWords(run.logLast) : "";
    return ctx.build.node("div", "sub run-log-off",
      `Fill log is off. Turn it on in Options to let Maestro CS see what each field tried.${when ? ` Last trace: ${when}.` : ""}`);
  }

  function readyBody(ctx, run) {
    const { node, attach } = ctx.build;
    // Where the resume stands is said whenever it did not simply attach (a box left for the user, a write
    // that could not be confirmed): the user is about to Submit.
    const attachSaid = run.attach?.outcome && run.attach.outcome !== "attached" ? attachLine(run.attach) : "";
    const out = [node("div", "sub", "Check the page, then press Submit in the tab. The Companion never presses it for you."),
      attachSaid ? node("div", "sub run-attach", attachSaid) : null,
      flagsBlock(ctx, run), logOffLine(ctx, run)];
    if (run.markNote) out.push(node("div", "sub run-mark-note", run.markNote));
    if (run.movedOn === true) out.push(node("div", "sub run-moved-on", "You moved on. Press Resume to fill this page."));
    // Done: not submitting this one. It ends the record and writes nothing, so the tab is free again.
    const actions = node("div", "run-actions");
    if (run.movedOn === true) attach(actions, button(ctx, "save", "run-resume", "Resume", () => ctx.act.resumeRun(run.id)));
    // After an Undo, a page that was not the confirmation, or when Maestro CS would not take the
    // automatic mark: the user's own press.
    if (run.noAutoMark) {
      attach(actions, button(ctx, "save", "run-mark", "Mark applied", () => ctx.act.markApplied(run.id)));
    }
    attach(actions, button(ctx, "unpick", "run-done", "Done", () => ctx.act.closeRun(run.id)));
    out.push(actions);
    return out;
  }

  function confirmingBody(ctx, run) {
    const { node, attach } = ctx.build;
    const row = attach(node("div", "sub run-marking"), node("span", null, "Marking applied in 8 s · "),
      button(ctx, "linkish", "run-undo", "Undo", () => ctx.act.undoMark(run.id)));
    return [row];
  }

  function finishedBody(ctx, run) {
    const { node, attach } = ctx.build;
    const actions = node("div", "run-actions");
    const out = [];
    if (run.status === "applied") {
      out.push(node("div", "sub", "Recorded as applied in Maestro CS."));
    } else {
      const [reason, say] = STOPS[run.why] ?? parkWords(run) ?? ["Stopped", "Nothing was submitted."];
      out.push(attach(node("div", "needs run-needs"), node("div", "run-reason", reason), node("div", "opts", say)));
      // A tab closed on a confirmation the mark then failed on: the one place the user hears it.
      if (run.markNote) out.push(node("div", "sub run-mark-note", run.markNote));
    }
    out.push(logOffLine(ctx, run));
    if (canResume(run)) attach(actions, button(ctx, "save", "run-resume", "Resume", () => ctx.act.resumeRun(run.id)));
    attach(actions, button(ctx, "save", "run-done", "Done", () => ctx.act.closeRun(run.id)));
    return [...out, actions];
  }

  /** "Saved N answers to your profile · Undo", or what became of them. */
  function learnedLine(ctx, run) {
    const { node, attach } = ctx.build;
    const learned = run.learned;
    if (!learned) return null;
    if (learned.failed) return node("div", "sub run-learned", "Couldn't save your answers, so the Companion will ask again.");
    const count = ctx.build.plural(learned.count, "answer");
    if (learned.undone) return node("div", "sub run-learned", `Undid ${count}.`);
    if (!learned.count) return null;
    return attach(node("div", "sub run-learned"), node("span", null, `Saved ${count} to your profile · `),
      button(ctx, "linkish", "run-undo-saved", "Undo", () => ctx.act.undoLearned(run.id)));
  }

  /** The body of the Next card for a bound run. */
  function render(ctx) {
    const run = ctx.facts.run;
    const { node, attach } = ctx.build;
    const body = node("div", "stg-body run");
    const parts = working(run) ? workingBody(ctx, run)
      : run.status === "parked" ? parkedBody(ctx, run)
        : run.status === "ready" ? readyBody(ctx, run)
          : run.status === "confirming" ? confirmingBody(ctx, run)
            : finishedBody(ctx, run);
    return attach(body, ...parts, learnedLine(ctx, run));
  }

  ns.panelRuns = { render, title, working, canResume, canSkip, REASONS };
})();
