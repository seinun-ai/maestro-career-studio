// The page-detection gate (design §5).
//
// Shared dependency modules run first but only publish functions. This is the
// extension's first decision point and, on the overwhelming majority of pages,
// the last code the widget calls. It runs IN EVERY FRAME, before any UI exists,
// and answers one question: is there anything here this extension can help with.
//
// The negative answer is the important one. On a miss the caller mounts
// nothing, observes nothing, and constructs no telemetry observation — not
// even a dot. That is not politeness; it is the whole difference between this
// widget and the category. A competitor's experimental job detection was
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
 * can combine this with Tier C (`GET /api/jobs/match?url=`, which the widget
 * asks for and which short-circuits both tiers below it) and still see what
 * the page itself offered. An ATS host arrives as `ats:<vendor>`; that vendor
 * is what selects the per-ATS field map later.
 */
function detectPage() {
  const signals = [];

  // ---------- Tier 0: free, every page ----------
  //
  // Two checks, one of them a single querySelector. Anchored at a dot or at
  // the start of the host, never a substring: `greenhouse.io.attacker.test`
  // contains every ATS name you could want it to.
  const ATS_HOSTS = [
    ["workday", /(^|\.)myworkdayjobs\.com$/],
    ["greenhouse", /(^|\.)greenhouse\.io$/],
    ["lever", /^jobs\.lever\.co$/],
    ["ashby", /^jobs\.ashbyhq\.com$/],
    ["smartrecruiters", /(^|\.)smartrecruiters\.com$/],
    ["workable", /^apply\.workable\.com$/],
    ["recruitee", /(^|\.)recruitee\.com$/],
    ["bamboohr", /(^|\.)bamboohr\.com$/],
    ["rippling", /^ats\.rippling\.com$|(^|\.)rippling-ats\.com$/],
    ["jobvite", /(^|\.)jobvite\.com$/],
    ["icims", /(^|\.)icims\.com$/],
    ["taleo", /(^|\.)taleo\.net$/],
    ["successfactors", /(^|\.)successfactors\.com$/],
  ];
  const host = (location.hostname || "").toLowerCase();
  const vendor = (ATS_HOSTS.find(([, pattern]) => pattern.test(host)) || [])[0];
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
  const present = (selector) => document.querySelector(selector) !== null;
  const evidence = [];

  // The strongest single signal, and every clause is scoped to a FILE input on
  // purpose. Unscoped, `[name*="cv" i]` matches `cardCvv`/`cvc` and
  // `[name*="resume" i]` matches an `<a name="resume">` bookmark — which put
  // this widget on payment pages and personal sites. The `accept` clause is
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
  // treating them alike put the widget on every page of a company that carries
  // one line in its footer.
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
  // reached the threshold in company with any single weak partner, which put
  // the widget on a careers site's contact page. They are never load-bearing
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

  if (present('#application_form, [data-ui="job-post"], [data-automation-id]')) {
    evidence.push(["ats-dom-marker", 1]);
  }

  // Anchored at the start of the control's own text, so this means "the
  // control that applies" and not "the word appears somewhere" — the second
  // reading fires on every "How to apply" heading on the web.
  //
  // `continue` is deliberately NOT here. It is the label on every wizard,
  // checkout and onboarding step ever built, and it buys nothing: an ATS
  // application step that says Continue also carries its vendor's DOM marker
  // and its identity fields, so the page is already recognised without it.
  const APPLY_TEXT = /^\s*(apply|submit application)\b/i;
  let affordance = false;
  for (const el of document.querySelectorAll(
    'button, input[type="submit"], input[type="button"], a[role="button"]'
  )) {
    // `value` first: a submit INPUT carries its visible text there and has no
    // text between its tags at all.
    if (APPLY_TEXT.test(el.value || el.textContent || "")) { affordance = true; break; }
  }
  if (affordance) evidence.push(["apply-affordance", 1]);

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
})();
