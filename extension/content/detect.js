// The page-detection gate (design §5).
//
// Shared dependency modules run first but only publish functions. This is the
// extension's first decision point and, on the overwhelming majority of pages,
// the last code that runs at all. It runs IN EVERY FRAME, before any UI exists,
// and answers one question: is there anything here this extension can help with.
//
// The negative answer is the important one. On a miss the caller offers
// nothing, observes nothing, and constructs no telemetry observation. That is
// not politeness; it is the whole difference between this extension and the
// category. A competitor's experimental job detection was
// injected "into multiple webpages rather than only job application sites" and
// broke a video site's own buttons; another is reported maxing CPU
// "regardless of if it can fill out anything" and breaking a chat client.
//
// So the gate holds no state, registers no observer, opens no connection and
// touches nothing on the page. It reads, scores, and returns.

/** Runs IN THE PAGE, once per navigation. Returns `{tier, score, signals, form}`.
 *
 * `tier` is `"A"` (job posting — primary action Add job), `"B"` (application
 * form — primary action Autofill) or `"none"`, which means mount nothing.
 *
 * `score` is the Tier B evidence total. Tier A is a VERDICT rather than a
 * score — a JobPosting record either names this page or it does not — so a
 * posting can come back as `{tier: "A", score: 0}`. Design §5 says the tiers
 * "do not combine into one number" and this is where that shows.
 *
 * `form` is whether the Tier B evidence held, independently of which tier won.
 * A page can be both, and most board pages are; `tier` names the primary
 * action and `form` says whether the other one is also available. Never
 * re-derive it from `score` — the threshold lives here.
 *
 * `signals` is everything that fired, tier boundaries ignored, so the caller
 * can combine this with Tier C (`GET /api/jobs/match?url=`, which the panel
 * asks for and which short-circuits both tiers below it) and still see what
 * the page itself offered. An ATS host arrives as `ats:<vendor>`; that vendor
 * is what selects the per-ATS field map later.
 */
function detectPage() {
  const signals = [];

  // ---------- Tier 0: free, every page ----------
  //
  // Two checks, one of them a single querySelector. The host list is shared
  // (shared/ats-hosts.js: anchored at a dot or the start, never a substring).
  const host = (location.hostname || "").toLowerCase();
  const vendor = window.careerStudioCompanion.atsHosts.vendorOf(host);
  // A host hit says WHICH ATS, never that we should be here: design §5, "it is
  // never sufficient alone". It is deliberately worth zero points below —
  // scoring it would put the host plus the per-ATS DOM marker at the threshold
  // on every page of a Workday tenant, search results included, which is the
  // rule it would be enforcing the opposite of.
  if (vendor) signals.push(`ats:${vendor}`);

  const LD_SELECTOR = 'script[type="application/ld+json"]';
  // The presence check is the gate on Tier A's parse, and nothing else. Almost
  // every commercial page carries JSON-LD; only its CONTENT can say job page.
  const hasJsonLd = document.querySelector(LD_SELECTOR) !== null;
  if (hasJsonLd) signals.push("jsonld");

  // ---------- Tier A: job posting ----------
  //
  // Detection asks only whether the page declares a JobPosting. Extraction
  // uses the same walk in description-required mode before reading content.
  const posting = hasJsonLd && Boolean(
    window.careerStudioCompanion.findJobPostingInDocument({ presenceOnly: true }));
  if (posting) signals.push("job-posting");

  // ---------- Tier B: application form ----------
  //
  // Six weighted signals, threshold 2.
  //
  // WHAT A MISS COSTS, since this is the path almost every page takes: on a
  // page with no identity fields, five `querySelector` calls — three fixed
  // probes plus two of the four identity ones, which bail early below — and
  // one `querySelectorAll` over the page's buttons. Six reads here, seven
  // counting Tier 0's, measured rather than estimated: the exact list is
  // asserted in `test_a_miss_reads_the_page_exactly_this_many_times`, so it is
  // a decision someone has to change on purpose rather than a number that
  // drifts. A `querySelector` stops at its first match, and the worst case is
  // seven of them, when the identity probes keep half-matching.
  //
  // What is NOT paid: no text read — the one probe that flattens the whole
  // document into a string is behind a gate below — no observer, no timer, no
  // allocation that outlives the call. And nothing is amortized across calls,
  // because the service worker re-runs this on every SPA route change.
  //
  // OPEN SHADOW ROOTS (a page of web components, live check 8): `document.querySelector` does not enter them, so a form built of
  // them scored nothing and the panel withheld its manual Autofill. A probe that misses in the light DOM is asked again of
  // each open shadow root. The roots are found ONCE, by the first miss (one pass over the page's elements, `ns.deep.roots`):
  // a probe that hits in the light DOM never looks, and the page text below stays the light DOM's `body.textContent`.
  let inner = null;
  const roots = () => (inner ??= window.careerStudioCompanion.deep.roots());
  const present = (selector) => document.querySelector(selector) !== null
    || roots().some((root) => root.querySelector(selector) !== null);
  const evidence = [];

  // The strongest single signal, and every clause is scoped to a FILE input on
  // purpose. Unscoped, `[name*="cv" i]` matches `cardCvv`/`cvc` and
  // `[name*="resume" i]` matches an `<a name="resume">` bookmark — which had
  // this extension offering to help on payment pages and personal sites. The `accept` clause is
  // separate because a drag-and-drop uploader often declares no `accept` at
  // all, and the name is the only thing left saying what it wants.
  if (present('input[type="file"][accept*="pdf" i], input[type="file"][name*="resume" i], '
      + 'input[type="file"][name*="cv" i]')) {
    evidence.push(["resume-input", 1]);
  }

  // Three DIFFERENT identity fields, not three fields — and three is a floor,
  // not a verdict. A checkout collects exactly this set, which is why this is
  // worth one point rather than being decisive: name, email and phone say a
  // person is filling something in, never what. The autocomplete tokens sit
  // beside the name attributes rather than counting separately, because a
  // field carrying both is still one field.
  const IDENTITY = [
    'input[name*="first_name" i], input[name*="firstname" i], [autocomplete="given-name"]',
    'input[name*="last_name" i], input[name*="lastname" i], [autocomplete="family-name"]',
    'input[type="email"]',
    'input[type="tel"]',
  ];
  const IDENTITY_CLUSTER = 3;
  let identity = 0;
  for (let i = 0; i < IDENTITY.length; i += 1) {
    if (present(IDENTITY[i])) identity += 1;
    // Stop as soon as the answer cannot change — either it is already yes, or
    // too few probes remain to reach it. A page with no identity fields at all
    // pays for two of these four rather than all of them.
    if (identity >= IDENTITY_CLUSTER
        || identity + (IDENTITY.length - 1 - i) < IDENTITY_CLUSTER) break;
  }
  if (identity >= IDENTITY_CLUSTER) evidence.push(["identity-cluster", 1]);

  // The page's text, read at most once, and only behind a cheap gate: a page
  // with neither a <form> nor a <select> is not an application form, and
  // reading `textContent` flattens the entire document into a string. That is
  // the single most expensive thing this module can do, so it does not happen
  // on the miss path at all.
  //
  // `textContent`, not `innerText`: innerText is specified in terms of
  // RENDERED text, so it answers a question about layout, and a self-
  // identification block that has not been expanded yet would not be in it.
  //
  // `document.body` is null in a frame that has not built one yet, and this
  // runs in every frame — including the ad and srcdoc frames that never will.
  const text = present("form, select") && document.body
    ? document.body.textContent || ""
    : "";

  // Two strengths, because these phrases are not equally informative and
  // treating them alike made every page of a company that carries one line in
  // its footer look like an application form.
  //
  // The self-identification block is near-certain and decisive on its own: a
  // page asking whether you are a protected veteran, or how you would describe
  // your disability status, is asking an applicant and nobody else.
  //
  // "Equal employment opportunity" and the bare acronym score NOTHING — the
  // same treatment `ats:<vendor>` gets, and for the same reason. They are the
  // boilerplate that follows a job description, sits in a corporate footer and
  // fills a blog post explaining the law, so they say something true about the
  // page and nothing about whether there is a form on it. At weight 1 they
  // reached the threshold in company with any single weak partner, which made
  // a careers site's contact page read as an application form. They are never load-bearing
  // for a real application form, which arrives at the threshold three other
  // ways: an upload plus an identity cluster, a vendor marker plus an apply
  // control, or the self-identification block by itself.
  //
  // `\bEEO\b`, because three unbounded letters appear inside longer runs —
  // brand names, identifiers, base64 — and none of those is about hiring.
  const SELF_ID_TEXT = /voluntary self-identification|veteran status|disability status/i;
  const EEO_BOILERPLATE = /equal employment opportunity|\bEEO\b/i;
  if (SELF_ID_TEXT.test(text)) evidence.push(["self-identification", 2]);
  else if (EEO_BOILERPLATE.test(text)) evidence.push(["eeo-boilerplate", 0]);

  // The knockout questions — age, work authorization, sponsorship — decisive
  // on their own for the self-identification block's reason: they are asked of
  // an applicant and nobody else. iCIMS's Candidate Questions step is three of
  // them and a Submit button in the page's own iframe, and every other signal
  // here is blind to it, so it scored 0 and the frame refused its own writes
  // (live, Global Medical Response, 2026-10-01).
  //
  // ASKED, not mentioned. A job description's requirements carry every one of
  // these words as statements ("must be authorized to work", "unable to offer
  // sponsorship"), so the match is a question to "you" — opened by are / will /
  // do / would / can you, with the subject reached before the sentence ends,
  // and closed by a question mark. The tail may cross a period, because
  // "(e.g., H-1B visa status)?" sits between the subject and the mark. No new
  // read: this is the string the self-identification test already took.
  const SCREENING_QUESTION = new RegExp(
    String.raw`\b(?:are|will|do|would|can)\s+you\b[^.?!]{0,160}?`
    + String.raw`\b(?:(?:eligible|authori[sz]ed|permitted)\s+(?:for\s+employment|to\s+work)`
    + String.raw`|sponsorship|1[68]\s+years)\b[^?]{0,120}\?`, "i");
  if (SCREENING_QUESTION.test(text)) evidence.push(["screening-question", 2]);

  if (present('#application_form, [data-ui="job-post"], [data-automation-id]')) {
    evidence.push(["ats-dom-marker", 1]);
  }

  // Workday's apply flow, by its ROUTE. Every step after Apply lives under
  // `…/apply/…`, and nothing else on a tenant does — search and posting pages
  // never carry it — so this is the flow and not the host, and the
  // host-is-never-enough rule above still holds. It exists because the other
  // signals cannot see these steps: Workday renders no <form> and no <select>
  // (so the text gate below never opens and the self-identification block
  // cannot count), its phone box is `type="text"` and My Information asks no
  // email (so the identity cluster stops at two), and its button says "Save
  // and Continue". Every step but the résumé upload used to score 1, and the
  // panel withheld Fill over a full form (live, pg.wd5, 2026-09-25). A
  // location read, not a DOM read, and only on a Workday host.
  if (vendor === "workday" && /\/apply(\/|$)/i.test(location.pathname || "")) {
    evidence.push(["workday-apply-route", 1]);
  }

  // Anchored at the start of the control's own text, so this means "the
  // control that applies" and not "the word appears somewhere" — the second
  // reading fires on every "How to apply" heading on the web.
  //
  // `continue` is deliberately NOT here. It is the label on every wizard,
  // checkout and onboarding step ever built. An ATS application step that says
  // Continue is recognised another way — its vendor's marker plus its identity
  // fields, or, on Workday, where neither of those is enough, the apply route.
  const APPLY_TEXT = /^\s*(apply|submit application)\b/i;
  const APPLY_CONTROLS = 'button, input[type="submit"], input[type="button"], a[role="button"]';
  // `value` first: a submit INPUT carries its visible text there and has no text between its tags at all.
  const affords = (root) => [...root.querySelectorAll(APPLY_CONTROLS)].some((el) => APPLY_TEXT.test(el.value || el.textContent || ""));
  if (affords(document) || roots().some(affords)) evidence.push(["apply-affordance", 1]);

  for (const [name] of evidence) signals.push(name);
  const score = evidence.reduce((total, [, weight]) => total + weight, 0);

  // A posting outranks form-shaped evidence on the same page, and not because
  // postings matter more. Tier B evidence is circumstantial and a posting page
  // can carry it without holding a form: an ATS posting stamps its vendor's
  // marker on every node and renders an Apply control, which is the threshold
  // reached on a page with no fields at all. A JobPosting record is a
  // declaration by the page about itself and nothing else can produce one.
  //
  // Which is why `form` is returned beside `tier` rather than left to be
  // re-derived from `score`. Every Greenhouse and Lever board page is BOTH a
  // posting and a form, so "A" is a tiebreak and not an exclusive label, and a
  // caller that had to rediscover the threshold below to learn the other half
  // would be the fourth copy of a constant in this repo.
  const TIER_B_THRESHOLD = 2;
  const form = score >= TIER_B_THRESHOLD;
  const tier = posting ? "A" : form ? "B" : "none";
  return { tier, score, signals, form };
}
// ---- end detectPage ----

// ---- open shadow roots ----
//
// A page built from web components (a hosted one-click application, live check 8) keeps its native inputs, file inputs and
// buttons inside OPEN shadow roots, which `querySelectorAll`, `closest` and `contains` do not cross: such a page read as
// "nothing to fill" while the fill inventory (content/inventory.js, its own walk) listed nine fields. These four are the
// composed-tree versions the page reader, the fillable count and the upload reader share (`ns.deep`). They live in THIS file,
// which every injection runs again, so a re-run file may call them without a fallback (a load-once file's newer export is
// what tests/test_extension_manifest.py forbids); a page without a shadow root pays one extra pass over its elements.
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  /** The parent in the composed tree: the element's parent, else the host of the shadow root it sits at the top of. */
  const up = (n) => n.parentElement ?? hostOf(n);
  const hostOf = (n) => n.getRootNode?.().host ?? null;
  /** `el.closest(sel)` through shadow boundaries: the DOM's own closest, then again from the host of the shadow root it stopped at. */
  const closest = (el, sel) => {
    for (let n = el; n; n = hostOf(n)) {
      const hit = n.closest?.(sel);
      if (hit) return hit;
    }
    return null;
  };
  /** `box.contains(el)` through shadow boundaries. */
  const contains = (box, el) => {
    for (let n = el; n; n = hostOf(n)) if (box.contains(n)) return true;
    return false;
  };
  /** Every match of `sel` under `root` (the document, a shadow root or an element), in document order, the open shadow
   * roots below it (and the element's own) included in place. The light query alone when none is there. */
  const all = (sel, root = document) => {
    if (!root.shadowRoot && ![...root.querySelectorAll("*")].some((el) => el.shadowRoot)) return [...root.querySelectorAll(sel)];
    const out = [];
    const walk = (at) => {
      for (const el of at.querySelectorAll("*")) {
        if (el.matches(sel)) out.push(el);
        if (el.shadowRoot) walk(el.shadowRoot);
      }
    };
    if (root.shadowRoot) walk(root.shadowRoot);
    walk(root);
    return out;
  };
  /** Every open shadow root under the document (nested ones included), in document order. */
  const roots = () => {
    const out = [];
    const walk = (at) => {
      for (const el of at.querySelectorAll("*")) {
        if (el.shadowRoot) {
          out.push(el.shadowRoot);
          walk(el.shadowRoot);
        }
      }
    };
    walk(document);
    return out;
  };
  ns.deep = { all, closest, contains, up, roots };
})();

/** How many on-screen fields this frame has that a fill could answer.
 *
 * NOT PART OF `detectPage`, and never on its miss path: the panel asks for it
 * (`detect_page`, content/agent.js) to decide one thing, whether a later step
 * of an application already confirmed on this host is a form (`askDetect`'s
 * flow rule, panel.js). Those steps, iCIMS's EEO and Candidate Questions, are
 * a few selects and a Submit and score nothing above. Search boxes do not
 * count, so a careers search page reached after the last step does not offer
 * Autofill over its keyword box. A popup button that picks a value counts (Workday's
 * "Select One"), a site menu or a Search button does not. Capped: the answer only has to be "more than
 * none". */
function fillableControls() {
  const { all, closest } = window.careerStudioCompanion.deep;
  const CAP = 20;
  const SEARCH_NAME = /^(q|query)$|search|keyword/i;
  const SKIPPED_TYPES = ["hidden", "submit", "button", "reset", "image", "search", "password"];
  let count = 0;
  // A POPUP BUTTON is a field too: Workday's question steps are made of them ("Select One"), and a step of
  // nothing else read as having nothing to fill. A `listbox` popup is a value picker. A bare `true` is a menu
  // as often as a picker (Share, More), so it counts only inside a form field (a fieldset, a group, a
  // formField wrapper) or while it shows a placeholder ("Select One"). Never in the site's own header,
  // navigation or footer: those are language and account menus.
  const POPUP = 'button[aria-haspopup="listbox"], button[aria-haspopup="true"], '
    + '[role="button"][aria-haspopup="listbox"]:not(input), [role="button"][aria-haspopup="true"]:not(input)';
  const SITE_CHROME = 'header, nav, footer, [role="banner"], [role="navigation"], [role="contentinfo"], [role="menubar"]';
  // Not `form`: an ASP.NET page wraps the whole page, in-content menus included, in one.
  const FIELD_HOLDER = 'fieldset, [role="group"], [data-automation-id^="formField"]';
  const asksForAnAnswer = (el) => {
    if (el.getAttribute("aria-haspopup") === "listbox") return true;
    if (closest(el, FIELD_HOLDER)) return true;
    return window.careerStudioCompanion?.isPlaceholderText?.((el.textContent || "").trim()) === true;
  };
  for (const el of all(
    `input, select, textarea, [role="combobox"], [role="radio"], [role="checkbox"], ${POPUP}`)) {
    if (el.matches?.(POPUP) && (closest(el, SITE_CHROME) || SEARCH_NAME.test(el.textContent || "") || !asksForAnAnswer(el))) continue;
    const type = (el.getAttribute("type") || "text").toLowerCase();
    if (el.tagName === "INPUT" && SKIPPED_TYPES.includes(type)) continue;
    const words = ["name", "id", "aria-label", "placeholder"].map((key) => el.getAttribute(key) || "");
    if (words.some((word) => SEARCH_NAME.test(word))
        || el.getAttribute("role") === "searchbox"
        || closest(el, '[role="search"]')) continue;
    const onScreen = el.offsetWidth || el.offsetHeight || el.getClientRects?.().length;
    if (el.disabled || el.readOnly || el.getAttribute("aria-disabled") === "true"
        || !onScreen) continue;
    count += 1;
    if (count >= CAP) break;
  }
  // A PILL GROUP (Yes/No buttons that hold aria-pressed, or a labelled list of button-only items) is a field
  // too, ONE per group: a step made of nothing else read as having nothing to fill.
  const groups = new Set();
  const shapes = window.careerStudioCompanion?.shapes;
  const PILLS = 'button[aria-pressed], [role="button"][aria-pressed], ul[role="list"][aria-label] > li > button:only-child';
  if (shapes) {
    for (const el of all(PILLS)) {
      if (count >= CAP) break;
      if (closest(el, SITE_CHROME) || shapes.of(el)?.name !== "pills") continue;
      const key = shapes.of(el).groupKey(el);
      if (groups.has(key)) continue;
      groups.add(key);
      if (el.disabled || el.getAttribute("aria-disabled") === "true" || !(el.offsetWidth || el.offsetHeight || el.getClientRects?.().length)) continue;
      count += 1;
    }
  }
  return count;
}


// ============================================================
// WHAT THIS FILE PUBLISHES
// ============================================================
//
// `manifest.json` lists this file and its shared modules before their consumers
// in one `content_scripts.js` array. Chrome documents that such an array injects in
// order into ONE isolated world — but it does not document that the top-level
// declaration above is reachable BY NAME from the next file.
// That is probably true and has never been checked here: the extension has
// never been loaded, and a branded Chrome refuses `--load-extension` ("not
// allowed in Google Chrome, ignoring") with no flag override. The shared
// JobPosting walk now uses this explicit namespace boundary.
//
// So the export is explicit instead. The property below is written on the
// isolated world's own `window`, which is the one object every content script
// in this frame demonstrably shares — under BOTH readings of the scope
// question, because a file with its own private top-level scope still has the
// same global object. The page cannot see it: an isolated world has a separate
// global (documented; not executed here either, and the honest reason it does
// not matter is that nothing secret is on this object).
//
// IIFE rather than a top-level `const ns`, and this is the load-bearing half:
// IF the files do share top-level scope, a second file declaring the same
// `const` is a redeclaration SyntaxError that kills the entire script. The only
// form that is correct under both readings is the one that declares nothing at
// the top level. `??=` creates the namespace if this file happens to run first
// and reuses it otherwise, so injection order does not matter either.
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  ns.detectPage = detectPage;
  ns.fillableControls = fillableControls;
})();
