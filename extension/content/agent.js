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
        applyUrl: ns.pageReader?.applyUrl(posting) ?? null, // the employer's link, read off this page only
      };
    }

    const describedNodes = [...document.querySelectorAll(
      '[class*="job-description" i], [class*="jobDescription" i], [id*="job-description" i], '
      + '[class*="description" i][class*="job" i], [data-testid*="description" i]'
    )];
    const candidates = [
      document.querySelector("main"),
      document.querySelector("article"),
    ].filter(Boolean);
    const longest = (nodes) => nodes.filter(ns.usableDescriptionNode).map((node) => node.innerText.trim())
      .reduce((best, text) => (best === null || text.length > best.length ? text : best), null);
    // WHERE the text came from, which is what the panel may claim about it:
    // `content` when a visible job-description container, or the section under
    // a description heading (`descriptionUnderHeading`), held a usable
    // description, `page` for a long <main>/<article> with none (a blog, a
    // recipe), `body` for the whole page.
    //
    // A `content` answer is the CONTAINER'S OWN TEXT, never a longer <main> or
    // <article> around it: a frame can hold the description AND an application
    // form, and a custom widget there shows the user's own value as plain text
    // (a name, an email), which would then ride into the preview and a save.
    const described = longest(describedNodes) ?? ns.descriptionUnderHeading();
    const page = described === null ? longest(candidates) : null;
    const best = described ?? page;
    return {
      url: location.href,
      title: document.title,
      text: (best ?? document.body.innerText ?? "").trim().slice(0, 60000),
      source: described !== null ? "content" : page !== null ? "page" : "body",
      applyUrl: ns.pageReader?.applyUrl(null) ?? null,
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
   * Fails CLOSED: a frame whose detection throws does not get the data. A
   * subframe on exactly the http(s) origin the panel vouches for (`flowOrigin`:
   * its form was confirmed in this tab, panel.js) also passes. */
  function frameMayReceiveUserData(msg) {
    if (window.top === window.self) return true;
    if (/^https?:\/\//.test(msg?.flowOrigin) && msg.flowOrigin === location.origin) return true;
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
  // Ten levels: Workday seats the heading seven wrappers above the box. Past the sixth, the climb also
  // stops at an ancestor holding another field, whose heading is no longer this box's alone.
  const SECTION_CLIMB = 10;
  const NEAR_CLIMB = 6;
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
      if (level >= NEAR_CLIMB && [...el.querySelectorAll(`${NOT_AN_UPLOADER}, input[type="file"]`)]
        .some((other) => other !== input)) break;
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

  // A PARSER BOX is the site's own "fill this form from my resume": it imports, parses or autofills
  // from the file and rewrites fields the Companion filled (live check 2: wrong education rows, a
  // middle name, a cut-off link). It is NEVER written, by any press. The words are an ACTION on the
  // file, the resume noun its object ("Import Resume", "Autofill from resume", "Apply with resume"):
  // "Import from Dropbox" is a file source. The nearest NAME decides, as `kindOf` does: a section
  // heading that plainly names a resume upload outranks its button's "Import Resume" (the live
  // "Resume Upload" box has one), and a parser-worded section never overrides a box that names a
  // plain resume. COMBINED wording ("Resume (we'll use it to fill your profile)") is the resume box
  // when it is the only one, and a parser beside a separate resume box (`readBoxes`).
  const RESUME = String.raw`(?:r[eé]sum[eé]s?|cv|curriculum\s+vitae)(?![\p{L}\p{N}])`;
  const OBJECT = String.raw`(?:(?:your|my|a|the)\s+)?${RESUME}`;
  const PARSER_WORDS = WORD([
    String.raw`(?:import|parse)\s+${OBJECT}`,
    String.raw`(?:auto-?\s?fill|pre-?\s?fill|populate)\b[^.\n]{0,40}?\b(?:from|with|using)\s+${OBJECT}`,
    String.raw`fill\s+(?:in\s+|out\s+)?(?:the\s+|this\s+|your\s+)?(?:form|application|profile|fields?)\b[^.\n]{0,20}?\b(?:from|with|using)\s+${OBJECT}`,
    String.raw`apply\s+with\s+${OBJECT}`,
  ].join("|"));
  const COMBINED_WORDS = WORD(String.raw`${RESUME}[^.\n]{0,30}?\bto\s+(?:auto-?\s?fill|pre-?\s?fill|populate|fill)`);
  const hit = (re, texts) => texts.some((t) => re.test(String(t ?? "")));
  // Boxes whose read threw: unknown and occupied, and no press writes them.
  const UNREAD = new WeakSet();

  /** What the box is called when the field reader gave up at the uploader's own text ("Click to
   * upload"): a react-dropzone's name ("Resume *") is a sibling of the WIDGET. The text before the
   * widget, its star read as required. Empty when the reader already named the box, and for a stray
   * file name (a filename is the user's, never a label). */
  function outsideName(input, read) {
    const none = { text: "", required: false };
    if (read.question || typeof ns.precedingLabel !== "function" || typeof ns.unmark !== "function") return none;
    try {
      const named = ns.unmark(ns.precedingLabel(uploadWidgetOf(input) ?? input, [input]));
      return FILE_ROW.test(named.text) ? none : named;
    } catch (_) {
      return none;
    }
  }

  function uploadBoxOf(input) {
    const widget = uploadWidgetOf(input);
    const box = widget ?? input.parentElement;
    const read = typeof ns.readField === "function" ? ns.readField(input) : { question: "" };
    const outside = outsideName(input, read);
    const labels = [read.question, outside.text];
    for (let el = input; el; el = el === box ? null : el.parentElement) {
      labels.push(el.getAttribute("aria-label"), words(el.getAttribute("data-automation-id")));
      for (const id of (el.getAttribute("aria-labelledby") ?? "").split(/\s+/).filter(Boolean)) {
        labels.push(document.getElementById(id)?.textContent);
      }
    }
    const own = [...labels, words(input.id), words(input.name)];
    const section = sectionOf(input);
    // Only an uploader of its own speaks for the box: a bare input's parent may be the whole form.
    const uploader = [widget?.innerText];
    // A parser-worded label read from INSIDE the widget (the button beside the input) is the
    // uploader's word, not the box's own: it weighs as the uploader's.
    const inside = (t) => Boolean(widget && t && hit(PARSER_WORDS, [t]) && widget.innerText.includes(t));
    const outer = labels.filter((t) => !inside(t));
    const plain = (texts) => kindOf(texts) === "resume" && !hit(PARSER_WORDS, texts);
    const parser = hit(PARSER_WORDS, outer) || (hit(PARSER_WORDS, uploader) && !plain([section]))
      || (hit(PARSER_WORDS, [section]) && !plain(outer) && !plain(uploader));
    const occupied = hasFile(input, box);
    if (parser) return { kind: "parser", occupied };
    let kind = kindOf(own) ?? kindOf([box?.innerText]) ?? kindOf([section]) ?? "unknown";
    // A REQUIRED box that is the page's only upload, and whose words name no document, is the resume's
    // (live Workday: "Upload a file (5MB max)", seven levels under the heading that says resume).
    if (kind === "unknown" && (read.required || outside.required) && attachableFileInputs().length === 1) kind = "resume";
    return { kind, occupied, combined: kind === "resume" && hit(COMBINED_WORDS, [...labels, ...uploader]) };
  }

  /** `uploadBoxOf` for each of `inputs`, in order, as `{kind, occupied}` (a box whose read throws is
   * unknown and occupied, and in `UNREAD`). COMBINED boxes are parsers only beside another resume box.
   * SEVERAL RESUME-LOOKING BOXES: keep the ones whose section names a resume upload and demote the
   * rest to unknown (live ATS-D: "Candidate Info" beside "Resume Upload"). When no section names
   * one, all stay and the callers' "exactly one" rule refuses. */
  function readBoxes(inputs) {
    const raw = inputs.map((input) => {
      try {
        return uploadBoxOf(input);
      } catch (_) {
        return { kind: "unknown", occupied: true, unread: true };
      }
    });
    const boxes = raw.map(({ kind, occupied, combined, unread }, i) => {
      const separate = raw.some((other, j) => j !== i && other.kind === "resume" && !other.combined);
      const box = { kind: combined && separate ? "parser" : kind, occupied };
      if (unread) UNREAD.add(box);
      return box;
    });
    const resumes = boxes.map((box, i) => (box.kind === "resume" ? i : -1)).filter((i) => i >= 0);
    if (resumes.length > 1) {
      const named = resumes.filter((i) => {
        try {
          return kindOf([sectionOf(inputs[i])]) === "resume";
        } catch (_) {
          return false;
        }
      });
      if (named.length) for (const i of resumes) if (!named.includes(i)) boxes[i] = { ...boxes[i], kind: "unknown" };
    }
    return boxes;
  }

  /** The box a page's own error named (`target`: its `data-maestro-up` tag), if this frame holds it,
   * it holds no file, and its words do not name another document. The page chose it, so the "exactly
   * one resume box" rule does not apply; the other refusals do. Two more, for what the user may have
   * done by hand: no other box in the frame holds a file already (the resume is on the page, in the
   * box the error did not name), and among several boxes the named one must read as a resume box. */
  function targetBox(inputs, boxes, target) {
    const at = inputs.findIndex((one) => one.getAttribute("data-maestro-up") === target);
    const box = boxes[at];
    if (!box || box.kind === "other" || box.kind === "parser" || box.occupied) return [];
    if (inputs.length > 1 && (box.kind !== "resume" || boxes.some((one, i) => i !== at && one.occupied))) return [];
    return [inputs[at]];
  }

  /** The page's upload boxes in its own words, for the run: `{label, target, required, occupied,
   * kind}` per attachable box. The label is the field reader's question; the target an opaque tag. */
  function pageUploads() {
    const inputs = attachableFileInputs();
    const boxes = readBoxes(inputs);
    return inputs.map((input, i) => {
      const read = ns.readField?.(input);
      const outside = outsideName(input, read ?? { question: "" });
      // `required` is the page's word, a parser's too: a required parser box parks the run, naming it.
      return { label: ns.pageReader.fieldWords(input) || outside.text, target: ns.pageReader.uploadTag(input),
               required: Boolean(read?.required || outside.required), occupied: boxes[i].occupied, kind: boxes[i].kind };
    });
  }

  /** Autofill's one target, re-checked at write time for `expect`'s reason:
   * the page's only resume box, while it holds no file; else none. */
  function theResumeBox(inputs, boxes) {
    const at = boxes.map((box, i) => (box.kind === "resume" ? i : -1)).filter((i) => i >= 0);
    return at.length === 1 && !boxes[at[0]].occupied ? [inputs[at[0]]] : [];
  }

  /** `readBoxes` for every box `attachableFileInputs` counts, in its order. */
  function uploadBoxes() {
    return readBoxes(attachableFileInputs());
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
  async function attachResumePdf(b64, filename, expect, resumeOnly = false, target = null) {
    // `target`: write the box the page's own error named, and only it (`targetBox`).
    const targeted = typeof target === "string" && target !== "";
    const reply = (written, proven) => (resumeOnly || targeted ? { written, proven } : proven);
    const all = attachableFileInputs();
    if (!targeted && Number.isInteger(expect) && all.length !== expect) return reply(0, 0);
    // The button writes every box but a parser (the site's own fill-from-resume), one for another
    // document (a cover letter) or one it could not read.
    const boxes = readBoxes(all);
    const inputs = targeted ? targetBox(all, boxes, target) : resumeOnly ? theResumeBox(all, boxes)
      : all.filter((_, i) => !["parser", "other"].includes(boxes[i].kind) && !UNREAD.has(boxes[i]));
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

  // The fids a watch message names: strings only, at most a page's worth.
  const fidsOf = (msg) => (Array.isArray(msg?.fids) ? msg.fids.filter((fid) => typeof fid === "string").slice(0, 40) : []);

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
   * already runs on and returns nothing derived from the user. The side panel
   * asks both of frame 0 first (`panel_frame0`) and of every frame
   * (`page_broadcast`) only when frame 0 has no answer: a posting in an iframe
   * (iCIMS), a form in an embed (Greenhouse). */
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
      return { tier, form, score, fileInputs: uploads.length, uploads,
               origin: location.origin, controls: ns.fillableControls() };
    },
    profile_fill: (msg) => (frameMayReceiveUserData(msg)
      ? ns.fillFormFromProfile(msg.profile, msg.employment, msg.eeoEnabled === true, msg.skills, msg.consentForms === true)
      : { filled: [], eeoFilled: [], corrected: [], already: [], seen: 0, observations: [] }),
    collect_open_questions: (msg) => (frameMayReceiveUserData(msg)
      ? ns.collectOpenQuestions()
      : { questions: [], excluded: [], retryables: [], host: location.hostname }),
    fill_answers: (msg) => (frameMayReceiveUserData(msg)
      ? ns.fillAnswersByQid(msg.pairs)
      : []),
    guided_write: (msg) => (frameMayReceiveUserData(msg)
      ? ns.applyGuidedChoices(msg.pairs)
      : []),
    scroll_to_field: (msg) => (frameMayReceiveUserData(msg)
      ? scrollToField(msg.qid)
      : false),
    attach_resume_pdf: (msg) => (frameMayReceiveUserData(msg)
      ? attachResumePdf(msg.b64, msg.filename, msg.expect, msg.resumeOnly === true, msg.target)
      : 0),
    /* The fill engine's page operations (content/fill-ops.js). Gated like
     * `guided_write`, each returning its empty shape in a refused frame: an
     * inventory with no fields, no explored options, no applied rows, no
     * step state, no sweep rows, no focus, no sections, no add. `fill_inventory` forwards the run's standing
     * consent AND its runId — a new runId is what releases a latched Stop — and
     * `peek` (the fids only, after a commit that may add or remove fields).
     * `fill_cancel` is ungated on purpose: it carries nothing and only stops
     * work in flight, and a Stop that could miss a frame would be no Stop. */
    fill_inventory: (msg) => (frameMayReceiveUserData(msg)
      ? ns.fillOps.inventory({ consentForms: msg.consentForms === true, runId: msg.runId, peek: msg.peek === true, readOnly: msg.readOnly === true })
      : { frame: null, host: location.hostname, fields: [] }),
    fill_explore: (msg) => (frameMayReceiveUserData(msg)
      ? ns.fillOps.explore(msg.requests)
      : {}),
    fill_apply: (msg) => (frameMayReceiveUserData(msg)
      ? ns.fillOps.apply(msg.actions)
      : []),
    // The adaptive step's state of ONE field. Broadcast like the rest: only
    // the frame that minted the fid answers, every other frame says null.
    fill_step_state: (msg) => (frameMayReceiveUserData(msg)
      ? ns.fillOps.stepState({ fid: msg.fid, fp: msg.fp, value: msg.value })
      : null),
    fill_sweep: (msg) => (frameMayReceiveUserData(msg)
      ? ns.fillOps.sweep(msg.only)
      : []),
    fill_focus: (msg) => (frameMayReceiveUserData(msg)
      ? ns.fillOps.focus(msg.fid)
      : false),
    // Repeating sections (content/sections.js): the frame's sections, and one
    // press of ONE section's own Add — the sid, plus the heading and entry
    // count the loop decided from, so a changed view presses nothing. Only
    // the frame that minted the sid answers the add; every other says null.
    fill_sections: (msg) => (frameMayReceiveUserData(msg)
      ? ns.fillOps.sections()
      : []),
    fill_add: (msg) => (frameMayReceiveUserData(msg)
      ? ns.fillOps.add({ sid: msg.sid, heading: msg.heading, entries: msg.entries })
      : null),
    fill_cancel: () => {
      ns.fillOps.cancel();
      return true;
    },
    /* Learn from the user's fix (content/recipes.js). `fill_watch` starts watching the parked
     * fields' gestures (a new park replaces the last watch); `fill_watch_report` answers, per
     * fid, which of the engine's moves the user made: `{family, site, gestures}`, event types
     * and a fixed few key names, never what was typed. Gated like the fill operations. */
    fill_watch: (msg) => {
      if (!frameMayReceiveUserData(msg)) return 0;
      ns.recipes.unwatch();
      return fidsOf(msg).filter((fid) => ns.recipes.watch(fid)).length;
    },
    fill_watch_report: (msg) => (frameMayReceiveUserData(msg)
      ? Object.fromEntries(fidsOf(msg).map((fid) => [fid, ns.recipes.report(fid)]).filter(([, one]) => one))
      : {}),
    /* The queued run's eyes and its one hand (content/page-reader.js). Gated like the fill
     * operations, each returning its empty shape in a refused frame. `page_advance` presses a
     * Next button the reader named, re-sorting its text at click time; it never presses a Submit.
     * `apply: true` (a posting's plain Apply) and `chooser: true` (the start chooser's one link) are the two narrow
     * exceptions; see page-reader.js. */
    page_classify: (msg) => (frameMayReceiveUserData(msg)
      ? { summary: ns.pageReader.summary(), top: window.top === window.self }
      : { summary: null }),
    // What the page itself complains about after a refused Next: words and handles, never values.
    page_errors: (msg) => (frameMayReceiveUserData(msg)
      ? ns.pageReader.pageErrors()
      : { count: 0, items: [] }),
    // The required boxes still empty: words and handles, never values (the sibling of `page_errors`).
    page_required: (msg) => (frameMayReceiveUserData(msg)
      ? ns.pageReader.pageRequired()
      : { count: 0, items: [] }),
    page_uploads: (msg) => (frameMayReceiveUserData(msg) ? pageUploads() : []),
    page_advance: (msg) => (frameMayReceiveUserData(msg)
      ? ns.pageReader.advance(msg.id, { apply: msg.apply === true, chooser: msg.chooser === true })
      : { clicked: false, why: "gate" }),
    // The saved login: TOP frame only (a subframe is refused, not asked), via panel_frame0 alone.
    // A fixed word on any failure: an error's text could be the password.
    page_sign_in: (msg) => {
      if (window.top !== window.self) return { signedIn: false, why: "frame" };
      try { return ns.pageReader.signIn({ email: msg.email, password: msg.password, allowedHost: msg.allowedHost }); }
      catch { return { signedIn: false, why: "error" }; }
    },
    // The same login typed to CREATE the account (owner decision 2026-10-14): top frame only, panel_frame0
    // alone, a fixed word on any failure. The reader itself refuses everything but a sign-up page.
    page_create_account: (msg) => {
      if (window.top !== window.self) return { created: false, why: "frame" };
      try { return ns.pageReader.createAccount({ email: msg.email, password: msg.password, allowedHost: msg.allowedHost }); }
      catch { return { created: false, why: "error" }; }
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
  // What kind of upload box an input is ("resume" | "other" | "parser" | "unknown"), for the page reader's
  // required-and-empty count: the site's own import-from-resume box is never a box the run owes a file.
  ns.uploadKindOf = (input) => uploadBoxOf(input).kind;
  ns.frameMayReceiveUserData = frameMayReceiveUserData; // content/touch-notice.js asks it at send time
})();
