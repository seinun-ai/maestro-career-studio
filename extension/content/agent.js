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

  /** Prefer a described schema.org JobPosting; otherwise use visible content. */
  function extractJobPosting() {
    const stripHtml = (html) => {
      const div = document.createElement("div");
      div.innerHTML = html;
      return div.innerText;
    };

    const posting = ns.findJobPostingInDocument({ presenceOnly: false });
    if (posting) {
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

    const candidates = [
      ...document.querySelectorAll(
        '[class*="job-description" i], [class*="jobDescription" i], [id*="job-description" i], '
        + '[class*="description" i][class*="job" i], [data-testid*="description" i]'
      ),
      document.querySelector("main"),
      document.querySelector("article"),
    ].filter(Boolean);
    let best = null;
    for (const node of candidates) {
      const text = node.innerText?.trim() ?? "";
      if (text.length > 300 && (!best || text.length > best.length)) best = text;
    }
    const text = (best ?? document.body.innerText ?? "").trim().slice(0, 60000);
    return {
      url: location.href,
      title: document.title,
      text,
      source: best ? "content" : "body",
    };
  }

  /** Whether THIS frame may receive anything derived from the user's profile.
   *
   * The service worker's fan-out is authorized at the SENDER (top frame only,
   * same tab, allow-listed type) but its targets are every frame in the tab —
   * `broadcastToFrames` asks `webNavigation.getAllFrames`. A job page carries
   * ad, analytics and chat-widget iframes, and the isolated world does not help
   * here: it protects the message in transit, not the DOM the engine then
   * writes into. A third-party frame owns its DOM, so a profile value written
   * into its input is readable by its own script immediately. `input[name*=
   * "email"]` in a newsletter iframe is not a hypothetical shape.
   *
   * The top frame is always allowed: it is the frame the user is looking at,
   * the only one the widget mounts in, and the one whose button they clicked.
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

  /** Attach a PDF to every compatible VISIBLE file input in this frame.
   *
   * Visibility is the same test `collectOpenQuestions` applies, and it belongs
   * here for a stronger reason: a file input's `files` is readable by the
   * page's own script the moment it is set, with no submit and no user
   * gesture. An off-screen input in a third-party frame is therefore a silent
   * copy of the résumé — name, address, phone and full history — to whoever
   * served that frame. A real uploader is on screen when you are asked to
   * upload. */
  function attachResumePdf(b64, filename) {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const file = new File([bytes], filename, { type: "application/pdf" });
    const dt = new DataTransfer();
    dt.items.add(file);
    let attached = 0;
    for (const input of document.querySelectorAll('input[type="file"]')) {
      const accept = (input.getAttribute("accept") ?? "").toLowerCase();
      if (accept && !accept.includes("pdf") && !accept.includes("*")) continue;
      // Drag-and-drop uploaders hide the real input behind a styled label, so
      // the input itself can legitimately have no box — accept it when an
      // ancestor is on screen, and refuse only what is invisible outright.
      if (!isOnScreen(input) && !isOnScreen(input.parentElement)) continue;
      input.files = dt.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      attached += 1;
    }
    return attached;
  }

  function isOnScreen(el) {
    return !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects?.().length));
  }

  /** Preserve the message names, positional profile-fill call, and output shapes.
   *
   * The four gated entries are exactly the fan-out set: three broadcastable
   * types plus attach. Each returns its normal EMPTY shape when the frame is
   * refused rather than throwing — `broadcastToFrames` turns a throw into a
   * per-frame `error`, and the widget's reconciliation strip would then report
   * "1 didn't stick" for an ad iframe that was never a target. Nothing to do
   * here is not a failure.
   *
   * `extract_job_posting` is ungated: it READS the page it already runs on and
   * returns nothing derived from the user. It is also not broadcastable. */
  const PAGE_HANDLERS = {
    extract_job_posting: () => extractJobPosting(),
    profile_fill: (msg) => (frameMayReceiveUserData()
      ? ns.fillFormFromProfile(msg.profile, msg.employment, msg.eeoEnabled === true,
        msg.skills, msg.consentForms === true)
      : { filled: [], eeoFilled: [], corrected: [], already: [], seen: 0, observations: [] }),
    collect_open_questions: () => (frameMayReceiveUserData()
      ? ns.collectOpenQuestions()
      : { questions: [], excluded: [], host: location.hostname }),
    fill_answers: (msg) => (frameMayReceiveUserData()
      ? ns.fillAnswersByQid(msg.pairs)
      : []),
    attach_resume_pdf: (msg) => (frameMayReceiveUserData()
      ? attachResumePdf(msg.b64, msg.filename)
      : 0),
  };

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (sender?.id !== chrome.runtime.id) return false;
    if (!Object.hasOwn(PAGE_HANDLERS, msg?.type ?? "")) return false;
    const handler = PAGE_HANDLERS[msg.type];

    (async () => {
      try {
        sendResponse({ ok: true, data: await handler(msg) });
      } catch (err) {
        sendResponse({ ok: false, error: String(err?.message ?? err) });
      }
    })();
    return true;
  });

  ns.pageHandlers = PAGE_HANDLERS;
})();
