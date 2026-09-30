/* Maestro CS Companion — page RPC front door.
 *
 * Runs in every frame. Shared modules own the JobPosting walk, profile fill,
 * EEO handling, and open questions; this file preserves the extraction wrapper,
 * five PAGE_HANDLERS and their wire shapes, plus page-local PDF attachment.
 */

// ============================================================
// WHAT THIS FILE PUBLISHES
// ============================================================
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  /** JSON-LD that names a DIFFERENT posting than the page's own url.
   *
   * A single-page job board rewrites the url and the visible pane when the
   * user picks another job, but the `<head>` JSON-LD it shipped with is not
   * re-rendered — so the walk above keeps returning the first job's title and
   * description under the second job's url, and "Add job" would file A's text
   * as B. Only decidable when BOTH sides carry a posting id
   * (`decisions.postingId`); a JSON-LD block without a `url`, or a board whose
   * ids live nowhere we know, is trusted as before. */
  function postingIsForAnotherJob(posting) {
    const postingId = ns.decisions?.postingId;
    if (typeof postingId !== "function" || typeof posting.url !== "string") return false;
    const declared = postingId(posting.url);
    const here = postingId(location.href);
    return Boolean(declared && here
      && (declared.host !== here.host || declared.id !== here.id));
  }

  /** Prefer a described schema.org JobPosting; otherwise use visible content. */
  function extractJobPosting() {
    const stripHtml = (html) => {
      const div = document.createElement("div");
      div.innerHTML = html;
      return div.innerText;
    };

    const posting = ns.findJobPostingInDocument({ presenceOnly: false });
    if (posting && !postingIsForAnotherJob(posting)) {
      const org = posting.hiringOrganization;
      const company = typeof org === "string" ? org : org?.name;
      const parts = [];
      if (posting.title) parts.push(`Title: ${posting.title}`);
      if (company) parts.push(`Company: ${company}`);
      const loc = posting.jobLocation?.address?.addressLocality
        ? `${posting.jobLocation.address.addressLocality}, ${posting.jobLocation.address.addressRegion ?? ""}`
        : null;
      if (loc) parts.push(`Location: ${loc}`);
      parts.push("", stripHtml(posting.description).trim());
      return {
        url: location.href,
        title: document.title,
        text: parts.join("\n").slice(0, 60000),
        source: "json-ld",
      };
    }

    const described = [...document.querySelectorAll(
      '[class*="job-description" i], [class*="jobDescription" i], [id*="job-description" i], '
      + '[class*="description" i][class*="job" i], [data-testid*="description" i]'
    )];
    const candidates = [
      ...described,
      document.querySelector("main"),
      document.querySelector("article"),
    ].filter(Boolean);
    const usable = (node) => (node.innerText?.trim() ?? "").length > 300;
    let best = null;
    for (const node of candidates) {
      const text = node.innerText?.trim() ?? "";
      if (usable(node) && (!best || text.length > best.length)) best = text;
    }
    const text = (best ?? document.body.innerText ?? "").trim().slice(0, 60000);
    // WHERE the text came from, which is what the panel may claim about it:
    // `content` only when a job-description container on this page held a
    // usable description, `page` for a long <main>/<article> with none (a
    // blog, a recipe), `body` for the whole page. The TEXT is chosen exactly
    // as before (the longest usable candidate), so what a save sends has not
    // changed; only "Job description found" is now said about a job signal.
    return {
      url: location.href,
      title: document.title,
      text,
      source: !best ? "body" : described.some(usable) ? "content" : "page",
    };
  }

  /** Whether THIS frame may receive anything derived from the user's profile.
   *
   * The service worker's fan-out is authorized at the SENDER (top frame only,
   * same tab, allow-listed type) but its targets are every frame in the tab —
   * `broadcastToFrames` asks `webNavigation.getAllFrames`. A job page carries
   * ad, analytics and chat iframes, and the isolated world does not help
   * here: it protects the message in transit, not the DOM the engine then
   * writes into. A third-party frame owns its DOM, so a profile value written
   * into its input is readable by its own script immediately. `input[name*=
   * "email"]` in a newsletter iframe is not a hypothetical shape.
   *
   * The top frame is always allowed: it is the frame the user is looking at,
   * and the one the panel is bound to.
   * Gating it would also break pages recognised only by Tier C
   * (`/api/jobs/match`), which short-circuits detection.
   *
   * A SUBFRAME has to earn it, with the gate that already exists and already
   * runs here: `detectPage().form` is Tier B evidence at threshold 2 — exactly
   * "there is an application form in this document". A Greenhouse or Lever form
   * subframe clears it on resume-input plus identity-cluster, which is why
   * fan-out exists at all. A newsletter iframe holding one email field scores
   * 0, because the identity cluster wants three DIFFERENT fields.
   *
   * Fails CLOSED: a frame whose detection throws does not get the data. */
  function frameMayReceiveUserData() {
    if (window.top === window.self) return true;
    try {
      return ns.detectPage().form === true;
    } catch (_) {
      return false;
    }
  }

  /** The file inputs in this frame a résumé could actually go into.
   *
   * ONE DEFINITION, and that is why it is a function rather than the loop it
   * used to be inline. The side panel now OFFERS an attach on the strength of
   * how many of these a page reports (`detect_page` below), and the write picks
   * its targets by the same rule — so a count taken any other way would be an
   * offer about a page other than the one being written to, which is the exact
   * shape of promise this extension keeps refusing to make.
   *
   * TWO FILTERS, each with its own reason.
   *
   * `accept`, when the input declares one: a box that wants a photo is not the
   * résumé box. A drag-and-drop uploader often declares none at all, which is
   * why an empty `accept` passes rather than failing.
   *
   * VISIBILITY is the same test `collectOpenQuestions` applies, and it belongs
   * here for a stronger reason: a file input's `files` is readable by the
   * page's own script the moment it is set, with no submit and no user gesture.
   * An off-screen input in a third-party frame is therefore a silent copy of
   * the résumé — name, address, phone and full history — to whoever served that
   * frame. A real uploader is on screen when you are asked to upload.
   * Drag-and-drop uploaders hide the real input behind a styled label, so the
   * input itself can legitimately have no box — an ancestor on screen is
   * accepted, and only what is invisible outright is refused. */
  function attachableFileInputs() {
    return [...document.querySelectorAll('input[type="file"]')].filter((input) => {
      const accept = (input.getAttribute("accept") ?? "").toLowerCase();
      if (accept && !accept.includes("pdf") && !accept.includes("*")) return false;
      return isOnScreen(input) || isOnScreen(input.parentElement);
    });
  }

  // The row proof's bounds (`attachResumePdf`): how long the page gets to show
  // its file row, how often we look, and how long a proof must keep holding.
  const ATTACH_PROOF_WAIT_MS = 3000;
  const ATTACH_POLL_MS = 100;
  const ATTACH_HOLD_MS = 300;

  // What an upload widget says when the file did NOT go. Counted before and
  // after the write, so standing help text ("Files that exceed 5 MB are not
  // supported") is not news; only an error that APPEARS voids a row proof. A
  // WIDE list on purpose: a phrasing it misses is the panel saying "Attached"
  // over a refused upload, while a false hit only sends the user to look —
  // which is why some SUCCESS copy ("No errors", "0 failed") appearing after
  // the write errs to zero, by design. Apostrophes both straight and curly
  // ("can’t").
  const UPLOAD_ERROR = new RegExp(String.raw`\b(?:${[
    String.raw`errors?`, String.raw`fail(?:s|ed|ure|ing)?`, "invalid", "unable",
    "rejected", "denied", "disallowed", "unsupported", String.raw`unsuccessful(?:ly)?`,
    String.raw`exceed(?:s|ed|ing)?`, String.raw`went\s+wrong`, String.raw`corrupt(?:ed)?`,
    String.raw`virus(?:es)?`, "malware", String.raw`could\s*n(?:o|['’])t`,
    String.raw`can(?:\s*not|['’]t)`, String.raw`too\s+(?:large|big)`,
    String.raw`not\s+(?:allowed|supported|accepted|permitted)`, String.raw`try\s+again`,
  ].join("|")})\b`, "gi");

  // An element that ALARMS: a new ON-SCREEN alert, or an element marked
  // invalid, with text in the widget is the page objecting to the write, so it
  // voids the row proof even when its words ("Please choose another file.")
  // are on no list. NOT `[aria-live]`: a polite live region that GAINS text is
  // the standard upload-status pattern ("Successfully Uploaded!" into an empty
  // region), and reading that as an error told the user to attach it again —
  // a second copy on Workday's `multiple` uploader. A live region's words are
  // still read, as part of the widget's text, against `UPLOAD_ERROR`.
  const UPLOAD_ALERT = '[role="alert"], [aria-invalid="true"]';

  // What an uploader never holds: a field of its own. An ancestor holding one
  // is the application step around the uploader, not the uploader. Hidden
  // inputs are left out — an uploader may keep the uploaded file's id in one.
  const NOT_AN_UPLOADER = 'input:not([type="file"]):not([type="hidden"]), select, textarea, [role="combobox"]';

  /** The part of the page that belongs to ONE file input: where its uploader
   * would print the row for a file it took.
   *
   * THE CLIMB is from the input's parent up to three levels, and the widget is
   * the highest level reached. It stops BELOW an ancestor that holds any OTHER
   * file input — so the cover-letter box's row can never vouch for the résumé
   * box's write — below one that holds any other field (`NOT_AN_UPLOADER`), so
   * a whole step container never becomes the widget, and below `<body>`,
   * `<html>` and a `<form>`, because those are the page or the application
   * rather than the uploader: the proof is never a search of the whole
   * document. A parent that already holds another
   * file input leaves NO widget, and that box can then prove itself only by
   * `files`. Three levels covers Workday (the input sits directly in
   * `attachments-FileUpload`, the row a level below it) with room for a
   * wrapper or two. */
  function uploadWidgetOf(input) {
    let widget = null;
    let el = input.parentElement;
    for (let level = 0; el && level < 3; level += 1, el = el.parentElement) {
      if (el === document.body || el === document.documentElement || el.tagName === "FORM") break;
      if ([...el.querySelectorAll('input[type="file"]')].some((other) => other !== input)) break;
      if (el.querySelector(NOT_AN_UPLOADER)) break;
      widget = el;
    }
    return widget;
  }

  /** What an upload box is FOR, and whether it holds a file: `{kind,
   * occupied}`, what Autofill's own attach decides with (`resumeOnly`,
   * `detect_page`'s `uploads`). A narrow rule on the box's own words, not the
   * AI mapping (the inventory skips file inputs); a miss costs a press of
   * Attach resume. `kind` ("resume", "other", "unknown"): the nearest level
   * with a word decides, the box's own label (field reader, aria labels, name,
   * id, automation id), then its uploader's text, then its section heading
   * (the uploader's own: h2–h6 in its form, never the page's h1). Another
   * document's word beats "resume" at a level. Words end at letters and
   * digits, not `\b`, which ends at an accent ("Résumé"). `occupied`: files in
   * the input, a file row in the uploader ("Resume (1).pdf" included), or a
   * remove, delete or replace control there. INTERNALS.md has the reasons. */
  const WORD = (body) => new RegExp(String.raw`(?<![\p{L}\p{N}])(?:${body})(?![\p{L}\p{N}])`, "iu");
  const RESUME_WORDS = WORD(String.raw`r[eé]sum[eé]s?|cv|curriculum\s+vitae`);
  const OTHER_DOC_WORDS = WORD([
    String.raw`cover\s*letters?`, String.raw`motivation(?:al)?\s+letters?`,
    "transcripts?", "portfolios?", String.raw`writing\s+samples?`, "references?",
    "certificat(?:e|es|ion|ions)", "diplomas?", "licen[cs]es?", "photos?", "headshots?",
    "additional", "supporting",
    String.raw`other\s+(?:documents?|files?|attachments?)`,
  ].join("|"));
  // A name before the extension, however it is spelled; help text listing
  // types ("(.pdf, .docx)") has a bracket, comma or space there instead.
  const FILE_ROW = /[^\s/\\:*?"<>|(,]\.(?:pdf|docx?|rtf|odt|txt|pages)(?![\p{L}\p{N}])/iu;
  const REMOVE_CONTROL = /(?<![\p{L}\p{N}])(?:remove|delete|replace)(?![\p{L}\p{N}])/iu;
  const SECTION_HEADING = 'h2, h3, h4, h5, h6, [role="heading"]:not([aria-level="1"])';
  const SECTION_CLIMB = 6;
  // "candidate_cv", "resumeUpload" → "candidate cv", "resume Upload".
  const words = (value) => String(value ?? "")
    .replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_\-.]+/g, " ");

  function kindOf(texts) {
    const text = texts.filter(Boolean).join(" ");
    if (OTHER_DOC_WORDS.test(text)) return "other";
    return RESUME_WORDS.test(text) ? "resume" : null;
  }

  /** The uploader's own section heading: see `uploadBoxOf`. */
  function sectionOf(input) {
    let el = input.parentElement;
    for (let level = 0; el && level < SECTION_CLIMB; level += 1, el = el.parentElement) {
      if (el === document.body || el === document.documentElement) break;
      const precedes = (h) => h.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING;
      const before = [...el.querySelectorAll(SECTION_HEADING)]
        .filter((h) => !h.contains(input) && precedes(h));
      if (before.length) return before.at(-1).textContent;
      if (el.tagName === "FORM") break;
    }
    return "";
  }

  function hasFile(input, box) {
    if ((input.files?.length ?? 0) > 0) return true;
    if (!box) return false;
    if (FILE_ROW.test(String(box.innerText ?? ""))) return true;
    if (box.querySelector('[data-automation-id="file-upload-item"]')) return true;
    return [...box.querySelectorAll('button, [role="button"]')].some((control) =>
      REMOVE_CONTROL.test(`${control.textContent} ${control.getAttribute("aria-label") ?? ""}`));
  }

  function uploadBoxOf(input) {
    const box = uploadWidgetOf(input) ?? input.parentElement;
    const read = typeof ns.readField === "function" ? ns.readField(input) : { question: "" };
    const own = [read.question, words(input.id), words(input.name)];
    for (let el = input; el; el = el === box ? null : el.parentElement) {
      own.push(el.getAttribute("aria-label"), words(el.getAttribute("data-automation-id")));
      for (const id of (el.getAttribute("aria-labelledby") ?? "").split(/\s+/).filter(Boolean)) {
        own.push(document.getElementById(id)?.textContent);
      }
    }
    const kind = kindOf(own) ?? kindOf([box?.innerText]) ?? kindOf([sectionOf(input)]) ?? "unknown";
    return { kind, occupied: hasFile(input, box) };
  }

  /** Autofill's one target, re-checked at write time for `expect`'s reason:
   * the page's only resume box, while it holds no file; else none. */
  function theResumeBox(inputs) {
    const resumes = inputs.filter((input) => {
      try {
        return uploadBoxOf(input).kind === "resume";
      } catch (_) {
        return false;
      }
    });
    return resumes.length === 1 && !uploadBoxOf(resumes[0]).occupied ? resumes : [];
  }

  /** `uploadBoxOf` for every box `attachableFileInputs` counts, in its order.
   * A box whose read throws is unknown and occupied: nothing is attached to it. */
  function uploadBoxes() {
    return attachableFileInputs().map((input) => {
      try {
        return uploadBoxOf(input);
      } catch (_) {
        return { kind: "unknown", occupied: true };
      }
    });
  }

  /** Error words in `text`, with the filename cut out first so a file called
   * `error-log.pdf` is not its own failure. */
  function errorWords(text, filename) {
    return String(text ?? "").split(filename).join(" ").match(UPLOAD_ERROR)?.length ?? 0;
  }

  /** How many on-screen elements in `widget` name `filename`: the DEEPEST ones
   * whose text holds it, so a row and the wrappers around it count once. A
   * row whose OWN text carries error words ("resume.pdf failed") is never a
   * success row, even where the widget's error total did not rise because the
   * page cleared an old error as it printed the new one. */
  function rowsNaming(widget, filename) {
    if (!widget.textContent.includes(filename)) return 0;
    return [widget, ...widget.querySelectorAll("*")].filter((el) =>
      el.textContent.includes(filename)
      && ![...el.children].some((child) => child.textContent.includes(filename))
      && isOnScreen(el)
      && errorWords(el.textContent, filename) === 0).length;
  }

  /** The widget's error total: error words in its RENDERED text (a hidden
   * error template is not news until it shows), plus every ON-SCREEN alarming
   * element (`UPLOAD_ALERT`) that holds text — on screen because `innerText`
   * of a hidden element still returns its text, and an alert nobody can see
   * tells the user nothing. */
  function uploadErrors(widget, filename) {
    const alarming = [widget, ...widget.querySelectorAll(UPLOAD_ALERT)].filter((el) =>
      el.matches(UPLOAD_ALERT) && isOnScreen(el) && String(el.innerText ?? "").trim() !== "").length;
    return errorWords(widget.innerText ?? widget.textContent, filename) + alarming;
  }

  /** Attach a PDF to every attachable file input in this frame, and report how
   * many of them actually took it.
   *
   * THE READBACK is the same honesty the fill engine's `not_stuck` carries:
   * `input.files = …` is an assignment a page can refuse — a control the
   * framework has replaced, a sandboxed input, a `files` property the site has
   * redefined — and the loop this replaced counted the attempt. A count is the
   * whole of what the surface above reports to the user ("Attached … to this
   * page"), so counting a write that did not land is the surface claiming an
   * upload that is not there.
   *
   * TWO PROOFS, because `input.files` ALONE UNDER-COUNTS ON WORKDAY. Its
   * uploader takes the file on `change`, starts the upload, and empties its
   * own input in the SAME tick (field notes §7): the upload succeeds —
   * "Successfully Uploaded!" and a row naming the file — while `files` reads
   * 0, so a `files`-only readback told the user "No upload box took the file.
   * Attach it by hand." over a page where it had worked. So a box counts when
   * EITHER holds once the page has settled:
   *
   * - `files` holds exactly our one file (`length === 1`, not `> 0`: anything
   *   else means the input holds something other than what we handed it) on a
   *   node still in the document — a plain input, or one a framework keeps; or
   * - THE PAGE'S OWN FILE ROW: inside this input's upload widget
   *   (`uploadWidgetOf`) there are MORE on-screen elements naming the file
   *   than there were before the write, and no new error text. MORE, not
   *   "any": a résumé of the same name uploaded earlier already shows its row,
   *   and that row says nothing about this write — a page that ignores the
   *   second copy counts zero (the user sees the earlier row and is told to
   *   check it: the safe direction), while Workday's `multiple` uploader adds a
   *   second row and counts. NO NEW ERROR because an error sentence names the
   *   file too ("resume.pdf could not be uploaded"), and a NEW on-screen
   *   alert or invalid-marked element with text counts as an error whatever
   *   it says (a live region only through its words — see `UPLOAD_ALERT`). Counting ELEMENTS
   *   rather than remembering nodes survives a widget that re-renders its old
   *   rows.
   *
   * A ROW STILL IN PROGRESS COUNTS. An uploader that prints the name while the
   * upload runs and fails more than about half a second later (past the hold
   * below) is counted as attached; the panel's "Check the upload before you
   * submit." is the line that covers it.
   *
   * A DETACHED INPUT COUNTS ONLY BY ITS ROW. A node the uploader re-rendered
   * away keeps whatever we assigned it forever, so its `files` is no evidence
   * (`valueHolds`' first check). But Workday may replace its input after taking
   * the file, and the row in the widget — which must itself still be in the
   * document — is the page saying so. A widget that re-renders WHOLE is
   * under-counted; that is the safe direction, where over-counting is the panel
   * claiming an upload that is not there.
   *
   * `expect` IS THE CALLER'S REFUSAL, CHECKED WHERE IT CAN ACTUALLY HOLD. The
   * side panel offers an attach only when the page reports exactly ONE box, and
   * refuses with a sentence when it reports several — but that count is frame
   * 0's, taken at DETECT time, and this runs at PRESS time in every gated
   * frame. Workday reveals a cover-letter uploader when the résumé section
   * expands: the offer said "one box", and without this the write put the
   * résumé in BOTH. The post-hoc report was honest about it, which is not the
   * same as the refusal having held.
   *
   * So the caller states what it believed and this frame refuses the whole
   * write unless its own list still says the same thing. WHOLE, not partial: a
   * frame that has grown a box cannot know which of them the offer was about,
   * and writing to "the one that was there before" is the guess the refusal
   * exists to prevent. The row proof changes nothing here — it is read only
   * for boxes the refusal already let through.
   *
   * ABSENT MEANS UNCHECKED, and the option is kept for a caller that makes no
   * such promise to its user: it passes no `expect` and gets the old
   * behaviour. The panel always passes one, because its offer is a sentence
   * about a count it showed the user.
   * `Number.isInteger` rather than a truthiness test — `expect: 0` is a real
   * claim ("this page had no box"), and it must refuse rather than fall through
   * to unchecked.
   *
   * `resumeOnly` IS AUTOFILL'S WRITE (`theResumeBox`): it answers `{written,
   * proven}`, so "nothing written" differs from "not proven", and a HIDDEN
   * input in an upload widget counts only by its row (a held `files` proves a
   * bare or visible input, whose own control shows it). The button keeps both. */
  async function attachResumePdf(b64, filename, expect, resumeOnly = false) {
    const reply = (written, proven) => (resumeOnly ? { written, proven } : proven);
    const all = attachableFileInputs();
    if (Number.isInteger(expect) && all.length !== expect) return reply(0, 0);
    const inputs = resumeOnly ? theResumeBox(all) : all;
    if (!inputs.length) return reply(0, 0);
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const file = new File([bytes], filename, { type: "application/pdf" });
    // THE BEFORE PICTURE, taken ahead of every write: the row proof is a
    // difference, and a later box's snapshot must not already hold an earlier
    // box's row. An EMPTY filename is in every text, so it proves nothing and
    // leaves such a box to `files` alone.
    const targets = inputs.map((input) => {
      const widget = filename ? uploadWidgetOf(input) : null;
      return {
        input, widget,
        rows: widget ? rowsNaming(widget, filename) : 0,
        errors: widget ? uploadErrors(widget, filename) : 0,
      };
    });
    for (const { input } of targets) {
      // A FRESH DataTransfer PER BOX. The input adopts the very FileList it is
      // handed, and an uploader that clears itself (`value = ""`, Workday's
      // move) empties that list IN PLACE — so a shared one reached every later
      // box empty.
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    const rowProof = (t) => t.widget !== null && t.widget.isConnected
      && rowsNaming(t.widget, filename) > t.rows
      && uploadErrors(t.widget, filename) <= t.errors;
    // Autofill's write takes a held `files` only from an input on screen (the
    // browser's own control shows it); a hidden one's uploader must show a row.
    const proven = (t) => ((t.input.isConnected && t.input.files?.length === 1)
      && !(resumeOnly && t.widget !== null && !isOnScreen(t.input))) || rowProof(t);
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    // THE SETTLE, and it is `valueHolds`' banner applied to the one writer that
    // did not have it. Reading `input.files` on the tick that assigned it reads
    // back our own write and says "stuck" almost always — a controlled uploader
    // (React/Angular) that rejects or discards the file does it on a LATER
    // render, exactly as a controlled text input does. 50ms then 150ms are
    // `valueHolds`' own first two samples, for its reason: timers keep running
    // in a hidden tab where requestAnimationFrame is starved — which is also
    // why every wait below is a timer and the deadline is wall-clock.
    const deadline = Date.now() + ATTACH_PROOF_WAIT_MS;
    await sleep(50);
    await sleep(100);
    // THEN WAIT FOR THE ROW, bounded: Workday renders it ~200ms after
    // `change`, a slow upload later. Only a box that HAS a widget can still
    // prove itself this way, so a page of plain inputs does not wait at all.
    while (Date.now() < deadline && targets.some((t) => t.widget !== null && !proven(t))) {
      await sleep(ATTACH_POLL_MS);
    }
    // THE HOLD: a proof counts only if it held when the wait ended AND is
    // still true a beat later — sampled at both ends, so a proof that merely
    // arrives during the hold is not one that held. A page that shows the row
    // and then withdraws it for an error has not taken the file, and neither
    // has a controlled input that discards it on a later render than the
    // settle's.
    const held = targets.map(proven);
    await sleep(ATTACH_HOLD_MS);
    return reply(targets.length, targets.filter((t, i) => held[i] && proven(t)).length);
  }

  function isOnScreen(el) {
    return !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects?.().length));
  }

  /** Put a field the fill could not answer in front of the user.
   *
   * The panel's residue rows are jumps, and the panel runs in no page — so the
   * scroll has to happen here. It is a FAN-OUT rather than a frame-0 call
   * because the control can be anywhere: on Greenhouse and Lever the form is a
   * subframe, which is the whole reason the fill fans out at all. Every frame
   * that does not hold the qid answers `false` and does nothing, which is what
   * makes broadcasting it correct rather than merely tolerable.
   *
   * `block: "center"` and no focus, deliberately: taking focus would move the
   * caret out of whatever the user was typing into on a form they are working
   * through by hand. */
  function scrollToField(qid) {
    if (!qid) return false;
    const el = document.querySelector(`[data-rt-qid="${CSS.escape(String(qid))}"]`);
    if (!el || typeof el.scrollIntoView !== "function") return false;
    el.scrollIntoView({ block: "center" });
    return true;
  }

  /** Preserve the message names, positional profile-fill call, and output shapes.
   *
   * The gated entries are exactly the fan-out set: the broadcastable types
   * (`fill_cancel` aside — see its note) plus attach. Each returns its normal EMPTY shape when the frame is
   * refused rather than throwing — `broadcastToFrames` turns a throw into a
   * per-frame `error`, and the panel's reconciliation strip would then report
   * "1 didn't stick" for an ad iframe that was never a target. Nothing to do
   * here is not a failure.
   *
   * `scroll_to_field` is gated with them even though a qid is not user data and
   * a frame that never answered a collect holds none anyway. That is the point:
   * the gate costs a refused frame nothing it could have done, so leaving it
   * off would be a fan-out entry with a DIFFERENT rule for no gain — and the
   * next type added here would have two precedents to choose between.
   *
   * `extract_job_posting` and `detect_page` are ungated: each READS the page it
   * already runs on and returns nothing derived from the user. Neither is
   * broadcastable — the side panel reaches both at frame 0. */
  const PAGE_HANDLERS = {
    extract_job_posting: () => extractJobPosting(),
    /** The page's own detection verdict, for the side panel — which runs in no
     * page, so `detectPage()` is not a function it can call.
     *
     * FIVE keys and no more. `detectPage` also returns `signals`, which names
     * the hosts, selectors and phrases that fired on this document: that is
     * page content by another route, and the panel has no use for it. What
     * crosses the boundary is the verdict — the tier, whether a form is here,
     * the score behind it, how many upload boxes a résumé could go into, and
     * per box its kind and whether it holds a file (`uploadBoxOf`): a word and
     * a boolean, never a label or a filename.
     *
     * `fileInputs` RIDES THE DETECT PASS rather than earning a message of its
     * own, and that is the decision rather than a convenience: the panel
     * already asks this exact question of this exact frame at bind and on every
     * retry, so the count arrives with the answer it belongs beside and costs no
     * extra round trip on any page. It is the same KIND of fact as the other
     * three — a count of controls this document renders, nothing derived from
     * the user — which is what keeps this handler ungated (below). It is a
     * COUNT and never the inputs themselves: what the panel decides with it is
     * whether to OFFER an attach, and one number is the whole of that decision.
     *
     * EVERY FRAME ANSWERS IT NOW, not only frame 0: the panel asks frame 0
     * first (`panel_frame0`) and, when frame 0 has no form, every frame
     * (`page_broadcast`), so a form in a subframe — Greenhouse's cross-origin
     * embed — turns the Fill offer on. `form` is folded across frames (any
     * frame true), which is the same verdict `frameMayReceiveUserData` reads.
     * The COUNT is still frame 0's alone: on a posting whose form is a
     * subframe the attach offer stays off. The attach fan-out still reaches
     * those frames; the OFFER does not, and that is the conservative direction.
     *
     * Ungated for `extract_job_posting`'s reason and no other: it reads the
     * frame it already runs in and returns nothing derived from the user — a
     * verdict and a count — so it is safe to fan out to every frame, ad and
     * analytics iframes included, and the gate is not what is being skipped
     * here: it is what this answer has no business consulting. */
    detect_page: () => {
      const { tier, form, score } = ns.detectPage();
      const uploads = uploadBoxes();
      return { tier, form, score, fileInputs: uploads.length, uploads };
    },
    profile_fill: (msg) => (frameMayReceiveUserData()
      ? ns.fillFormFromProfile(msg.profile, msg.employment, msg.eeoEnabled === true,
        msg.skills, msg.consentForms === true)
      : { filled: [], eeoFilled: [], corrected: [], already: [], seen: 0, observations: [] }),
    collect_open_questions: () => (frameMayReceiveUserData()
      ? ns.collectOpenQuestions()
      : { questions: [], excluded: [], retryables: [], host: location.hostname }),
    fill_answers: (msg) => (frameMayReceiveUserData()
      ? ns.fillAnswersByQid(msg.pairs)
      : []),
    guided_write: (msg) => (frameMayReceiveUserData()
      ? ns.applyGuidedChoices(msg.pairs)
      : []),
    scroll_to_field: (msg) => (frameMayReceiveUserData()
      ? scrollToField(msg.qid)
      : false),
    attach_resume_pdf: (msg) => (frameMayReceiveUserData()
      ? attachResumePdf(msg.b64, msg.filename, msg.expect, msg.resumeOnly === true)
      : 0),
    /* The fill engine's page operations (content/fill-ops.js). Gated like
     * `guided_write`, each returning its empty shape in a refused frame: an
     * inventory with no fields, no explored options, no applied rows, no
     * step state, no sweep rows, no focus, no sections, no add. `fill_inventory` forwards the run's standing
     * consent AND its runId — a new runId is what releases a latched Stop — and
     * `peek` (the fids only, after a commit that may add or remove fields).
     * `fill_cancel` is ungated on purpose: it carries nothing and only stops
     * work in flight, and a Stop that could miss a frame would be no Stop. */
    fill_inventory: (msg) => (frameMayReceiveUserData()
      ? ns.fillOps.inventory({ consentForms: msg.consentForms === true, runId: msg.runId, peek: msg.peek === true })
      : { frame: null, host: location.hostname, fields: [] }),
    fill_explore: (msg) => (frameMayReceiveUserData()
      ? ns.fillOps.explore(msg.requests)
      : {}),
    fill_apply: (msg) => (frameMayReceiveUserData()
      ? ns.fillOps.apply(msg.actions)
      : []),
    // The adaptive step's state of ONE field. Broadcast like the rest: only
    // the frame that minted the fid answers, every other frame says null.
    fill_step_state: (msg) => (frameMayReceiveUserData()
      ? ns.fillOps.stepState({ fid: msg.fid, fp: msg.fp, value: msg.value })
      : null),
    fill_sweep: () => (frameMayReceiveUserData()
      ? ns.fillOps.sweep()
      : []),
    fill_focus: (msg) => (frameMayReceiveUserData()
      ? ns.fillOps.focus(msg.fid)
      : false),
    // Repeating sections (content/sections.js): the frame's sections, and one
    // press of ONE section's own Add — the sid, plus the heading and entry
    // count the loop decided from, so a changed view presses nothing. Only
    // the frame that minted the sid answers the add; every other says null.
    fill_sections: () => (frameMayReceiveUserData()
      ? ns.fillOps.sections()
      : []),
    fill_add: (msg) => (frameMayReceiveUserData()
      ? ns.fillOps.add({ sid: msg.sid, heading: msg.heading, entries: msg.entries })
      : null),
    fill_cancel: () => {
      ns.fillOps.cancel();
      return true;
    },
  };

  // ONE LIVE listener per isolated world. panel_prepare re-injects this file
  // into the world that already runs it; a second listener would run every
  // page operation twice, concurrently. The handlers above are re-published
  // (the same code), the registration is not — unless the runtime that
  // registered it is dead (the extension reloaded under the page), whose
  // listener can no longer answer anything.
  const alive = (rt) => {
    try {
      return Boolean(rt?.id);
    } catch {
      return false;
    }
  };
  if (!alive(ns.listenerRuntime)) {
    ns.listenerRuntime = chrome.runtime;
    chrome.runtime.onMessage.addListener(onPageMessage);
  }

  function onPageMessage(msg, sender, sendResponse) {
    // Reading `chrome.runtime.id` THROWS once the extension has been reloaded
    // under a page that is still running this script, so the guard that
    // authorizes the sender is itself a place this can die.
    try {
      if (sender?.id !== chrome.runtime.id) return false;
    } catch (_) {
      return false;
    }
    if (!Object.hasOwn(PAGE_HANDLERS, msg?.type ?? "")) return false;
    const handler = PAGE_HANDLERS[msg.type];

    (async () => {
      // `sendResponse` on a port whose extension is gone throws as well, and
      // it is called from BOTH branches — so the error path was itself an
      // uncaught-exception path. Nothing here can recover a dead channel; what
      // it can do is not make that the page's problem.
      const reply = (payload) => {
        try {
          sendResponse(payload);
        } catch (err) {
          console.warn("[maestro-cs] could not answer", msg?.type, err);
        }
      };
      try {
        reply({ ok: true, data: await handler(msg) });
      } catch (err) {
        reply({ ok: false, error: String(err?.message ?? err) });
      }
    })();
    return true;
  }

  ns.pageHandlers = PAGE_HANDLERS;
})();
