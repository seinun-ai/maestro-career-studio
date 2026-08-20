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

  /** Attach a PDF to every attachable file input in this frame, and report how
   * many of them actually took it.
   *
   * THE READBACK IS NEW and it is the same honesty the fill engine's `not_stuck`
   * carries: `input.files = …` is an assignment a page can refuse — a control
   * the framework has replaced, a sandboxed input, a `files` property the site
   * has redefined — and the old loop counted the attempt. A count is the whole
   * of what the surface above reports to the user ("Attached … to this page"),
   * so counting a write that did not land is the surface claiming an upload
   * that is not there. `length === 1` and not `> 0`: we put exactly one file in
   * the DataTransfer, so anything else means the input holds something other
   * than what we handed it.
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
   * exists to prevent.
   *
   * ABSENT MEANS UNCHECKED, and the option is kept for a caller that makes no
   * such promise to its user: it passes no `expect` and gets the old
   * behaviour. The panel always passes one, because its offer is a sentence
   * about a count it showed the user.
   * `Number.isInteger` rather than a truthiness test — `expect: 0` is a real
   * claim ("this page had no box"), and it must refuse rather than fall through
   * to unchecked. */
  async function attachResumePdf(b64, filename, expect) {
    const inputs = attachableFileInputs();
    if (Number.isInteger(expect) && inputs.length !== expect) return 0;
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const file = new File([bytes], filename, { type: "application/pdf" });
    const dt = new DataTransfer();
    dt.items.add(file);
    const written = [];
    for (const input of inputs) {
      input.files = dt.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      if (input.files?.length === 1) written.push(input);
    }
    if (!written.length) return 0;
    // THE SETTLE, and it is `valueHolds`' banner applied to the one writer that
    // did not have it. Reading `input.files` on the tick that assigned it reads
    // back our own write and says "stuck" almost always — a controlled uploader
    // (React/Angular) that rejects or discards the file does it on a LATER
    // render, exactly as a controlled text input does. 50ms then 150ms are
    // `valueHolds`' own first two samples, for its reason: timers keep running
    // in a hidden tab where requestAnimationFrame is starved.
    await new Promise((resolve) => setTimeout(resolve, 50));
    await new Promise((resolve) => setTimeout(resolve, 100));
    // A DETACHED NODE IS NOT COUNTED, `valueHolds`' first check and the same
    // argument: a node the uploader re-rendered away keeps whatever we assigned
    // it forever, so `files` alone would report a box the user sees empty.
    //
    // THE TRADE, stated because it is real and the next author should not have
    // to rediscover it: an uploader that accepts the file and then replaces its
    // own input (printing the filename in a new node) is under-counted here,
    // and the panel will say "No upload box took the file. Attach it by hand."
    // over a page where it worked. That is the SAFE direction — the user looks
    // and sees it is fine — where over-counting is the panel claiming an upload
    // that is not there, which is the defect this whole readback exists for.
    return written.filter(
      (input) => input.isConnected && input.files?.length === 1).length;
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
   * The six gated entries are exactly the fan-out set: five broadcastable
   * types plus attach. Each returns its normal EMPTY shape when the frame is
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
     * FOUR keys and no more. `detectPage` also returns `signals`, which names
     * the hosts, selectors and phrases that fired on this document: that is
     * page content by another route, and the panel has no use for it. What
     * crosses the boundary is the verdict — the tier, whether a form is here,
     * the score behind it, and how many upload boxes a résumé could go into.
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
     * WHAT IT IS NOT: a promise about the frame the form is in. This handler
     * only ever answers for frame 0 (`panel_frame0`), so on a Greenhouse or
     * Lever posting — where the form is a subframe — it honestly reports zero
     * and the panel offers nothing. The attach fan-out still reaches those
     * frames; the OFFER does not, and that is the conservative direction.
     *
     * Ungated for `extract_job_posting`'s reason and no other: it reads the
     * frame it already runs in and returns nothing derived from the user. The
     * panel only ever asks frame 0, where `frameMayReceiveUserData` would pass
     * it anyway — so the gate is not what is being skipped here, it is what
     * this answer has no business consulting. */
    detect_page: () => {
      const { tier, form, score } = ns.detectPage();
      return { tier, form, score, fileInputs: attachableFileInputs().length };
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
      ? attachResumePdf(msg.b64, msg.filename, msg.expect)
      : 0),
  };

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
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
  });

  ns.pageHandlers = PAGE_HANDLERS;
})();
