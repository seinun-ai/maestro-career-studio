/* Maestro CS Companion — which questions have a TYPED home in the profile.
 *
 * ONE table of label patterns, TWO readers, and the second one is why this file
 * exists:
 *
 * 1. `content/autofill.js`'s rule table spreads each entry's pattern into the
 *    rule that FILLS the field from the profile;
 * 2. the side panel's pause row asks `profileFieldFor(label)` where a submitted
 *    answer should be LEARNED — a typed key, or the `custom` Q&A list.
 *
 * Those two have to be the same question. A pause row that saved "what is your
 * notice period?" to `custom` while the engine fills that field from
 * `preferences.notice_period` would write the user's answer to a place the
 * rules do not read as a notice period, and the same question would pause
 * again on the next application — which is the whole of the feature failing
 * silently. Two tables that agree today is how that happens; one table is the
 * only arrangement in which it cannot.
 *
 * WHAT IS IN THE TABLE, and what is deliberately not. Only fields whose answer
 * is a SCALAR the user could type into a pause row and that the profile has a
 * declared key for: the standing eligibility answers and the preferences.
 * Everything else in the engine's rule table stays there, because none of it is
 * a pause row's to learn — identity and contact come from the profile's own
 * form, employment and skills are STRUCTURED (a block index, a token list) and
 * derived from the resume rather than typed, EEO answers are the backend's
 * standing consent and never this surface's, and the never-fill families are
 * `shared/policy.js`'s refusal rather than anybody's storage.
 *
 * WHAT DID NOT TRAVEL WITH THE PATTERNS. `not:`, `kind:` and the value lookup
 * stay in `content/autofill.js`. Each is about FILLING a control — which page
 * widgets a rule must not capture, whether a yes/no needs option matching,
 * which profile read supplies the answer — and none of them changes where an
 * answer is stored. `earliest-start-date`'s `not: ANY_DATE_PART_RE` is the
 * clearest case: it exists so the rule cannot capture a Workday day-select, and
 * the router has no controls to capture.
 *
 * SO THERE ARE TWO SCANNERS OVER ONE TABLE, stated rather than discovered.
 * `matchRule` (autofill.js) knows about values and scans PAST a rule with no
 * answer behind it so a valueless rule cannot shadow one that could fill the
 * field; `profileFieldFor` below has no values to know about and answers a
 * narrower question — "does a typed home exist for this label". Two scans, one
 * vocabulary. The vocabulary is what drifts; a scan that answers a different
 * question is not a copy of one that answers this one.
 *
 * ORDER MATTERS and it is the engine's: specific before broad, first match
 * wins. `sponsorship-now` before `sponsorship-future` is that convention and it
 * lives in autofill.js; here the only pair it decides is nothing yet, and the
 * order is kept faithful to the engine's so that a future entry cannot mean two
 * different things on the two sides.
 *
 * LOADS AFTER `shared/policy.js`, which publishes `ns.salaryExpectationRe` —
 * the salary pattern is READ from the policy rather than restated, because
 * "this asks what you want, not what you earn" is one decision and the copy
 * that used to live in autofill.js had already drifted from it (see that rule's
 * comment). The order is pinned by the manifest test and by panel.html's own
 * load-order test.
 *
 * No `document`, no `location`, no `chrome`, no network — the test of whether a
 * module belongs in `shared/` at all.
 *
 * WHAT THIS FILE PUBLISHES: ns.profileFields, ns.profileFieldFor,
 * ns.normLabel.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  // Present-tense sponsorship, and ONLY present-tense. "Now or in the future"
  // belongs to the future answer: any later need makes that question yes.
  const NOW_WORDS = "currently|presently|at this time|\\bnow\\b(?!\\s+or\\b)";
  const SPONSORSHIP_NOW_RE = new RegExp(
    `(${NOW_WORDS})[^|]*sponsor|sponsor[^|]*(${NOW_WORDS})`, "i");

  const PROFILE_FIELDS = [
    // ---- standing eligibility answers (profile.eligibility) ----
    //
    // Each is a knockout question on a real application, and each is UNSET by
    // default — which is exactly why a pause row that learns one is worth
    // having: the field reports `missing_source` and is left blank today, and
    // the user answering it once turns every later occurrence into a rule hit.
    //
    // "Are you 18 years of age or older?" — the wording is remarkably stable,
    // but the number has to be bounded on both sides. `\b18\b` alone matches
    // "18 months of experience" and a 2018 date fragment; requiring the age
    // noun beside it is what keeps this off every other field with an 18 in it.
    { id: "over-18", path: ["eligibility", "over_18"],
      re: /\b(?:are|am)\s+you\b[^?|]{0,40}\b18\b|\b18\s*(?:\+|years?|yrs?)\b[^?|]{0,20}\b(?:of\s*age|old(?:er)?)\b|\bat\s*least\s*18\b|\blegal\s*working\s*age\b/i },
    // "Have you previously been employed by <this employer>?" — the single most
    // common unanswered question in the corpus, seen on six hosts and worded
    // differently on every one: "have you worked with us before", "are you
    // currently or have you previously been employed by Doosan", "do you
    // currently work for PwC", plus Workday's own `candidateIsPreviousWorker`.
    //
    // A conjunction, not an alternation, and that is what makes it safe. It
    // needs the employment word, a time marker AND a question addressed to the
    // applicant — so "I currently work here" (the work-history tick box, which
    // has its own rule and its own derived answer) is missing the third and
    // cannot be captured. Getting that wrong would tick a box about a past job
    // using an answer about this employer.
    { id: "previously-employed-here",
      path: ["eligibility", "previously_employed_here"],
      all: [/\b(?:employ|work)/i,
        /\b(?:previously|formerly|ever|before|current\s+or\s+former|currently|past)\b|previousworker/i,
        /\b(?:have|has|are|did|do)\s+you\b|candidateispreviousworker|previousworker/i] },
    // Non-competes and the family of agreements asked about in the same breath.
    { id: "non-compete", path: ["eligibility", "non_compete"],
      re: /non-?\s?compete|non-?\s?solicit|restrictive\s+(?:covenant|employment\s+agreement)/i },
    // Work authorization is stored under `work_auth`, not `eligibility`, but
    // it is the same standing-answer family: the engine fills it and a pause
    // row must learn it back into the exact key that engine reads.
    { id: "sponsorship-now", path: ["work_auth", "sponsorship_now"],
      re: SPONSORSHIP_NOW_RE },
    { id: "sponsorship-future", path: ["work_auth", "sponsorship_future"],
      re: /sponsor/i },
    { id: "work-auth", path: ["work_auth", "authorized_now"],
      re: /authoriz|legally\s.*work|eligible\s.*work|right to work/i },

    // ---- preferences (profile.preferences) ----
    //
    // The SAME pattern the never-fill policy uses to admit the salary field,
    // read from it rather than restated. They are one decision — "this asks
    // what you want, not what you earn" — and the copy that lived in
    // autofill.js had already drifted from the policy's: "what is your desired
    // annual base salary or hourly rate?" was blocked by the policy AND
    // unmatched by the rule, so the field was refused twice for the same
    // missing wording. A THIRD copy here would be the same bug again.
    { id: "salary", path: ["preferences", "desired_salary"],
      re: ns.salaryExpectationRe },
    { id: "notice-period", path: ["preferences", "notice_period"],
      re: /notice\s*period/i },
    // Never reachable from a pause row today and kept anyway: collection's
    // EXCLUDE list holds `date`, so an availability question is not offered as
    // an open question at all. It is in the table because the table is the
    // ENGINE's vocabulary and a row missing from it would be a rule the router
    // cannot see — and because the day EXCLUDE narrows, this must already be
    // right. The `not: ANY_DATE_PART_RE` guard that keeps the rule off a
    // Workday day-select stays in autofill.js: it is about controls.
    { id: "earliest-start-date", path: ["preferences", "earliest_start_date"],
      re: /start\s*date|available.*start|availability date/i },
    { id: "willing-to-relocate", path: ["preferences", "willing_to_relocate"],
      re: /relocat/i },
    { id: "how-heard", path: ["preferences", "how_heard"],
      re: /hear(d)?\s*about/i },
  ];

  /** The label, normalised the way BOTH sides already normalise one.
   *
   * `collectOpenQuestions` runs its labels through this exact shape before
   * they leave the page, and `labelFor` does the same before the engine matches
   * one — so a router that lower-cased differently would be matching a string
   * neither of them produced. */
  const norm = (s) => (s ?? "").toLowerCase().replace(/\s+/g, " ").trim();

  /** Does this question have a typed home in the autofill profile, and where?
   *
   * Returns the entry (`{id, path, …}`) or `null`. FIRST MATCH WINS, which is
   * `matchRule`'s rule and the reason the table's order is the engine's.
   *
   * NULL IS THE ORDINARY ANSWER and it is not a failure: most application
   * questions have no typed key and belong in the profile's `custom` Q&A list,
   * which the engine matches by label substring. The caller's job is to route,
   * not to insist. */
  function profileFieldFor(label, fields = PROFILE_FIELDS) {
    const text = norm(label);
    if (!text) return null;
    for (const field of fields) {
      if (field.re?.test(text)) return field;
      if (field.all?.every((re) => re.test(text))) return field;
    }
    return null;
  }

  // LOUD, at load, for `pf()`'s reason from the other end. `salaryExpectationRe`
  // is `shared/policy.js`'s and is read at TABLE-BUILD time, so a document that
  // loads this file first gets `re: undefined` on the salary row — and an
  // undefined pattern does not throw, it simply never matches. The engine would
  // then report `missing_source` for every desired-salary field on every ATS,
  // and the router would send salary expectations to the `custom` list, both
  // silently and both for as long as nobody looked. A load order is a fact
  // about a document, so it is checked where the document is wrong rather than
  // where the symptom appears.
  if (!(ns.salaryExpectationRe instanceof RegExp)) {
    throw new Error("profile-fields: shared/policy.js must load first");
  }

  ns.profileFields = PROFILE_FIELDS;
  ns.profileFieldFor = profileFieldFor;
  // Published because the CUSTOM Q&A list is matched the same way and by
  // another file: `content/autofill.js` builds its custom rules with
  // `norm(c.question)` and the panel has to normalise identically before it can
  // ask whether a question is already in that list. Two normalisers would put a
  // near-duplicate question in the list every time the label's whitespace
  // changed, which is the dedup failing silently.
  ns.normLabel = norm;
})();
