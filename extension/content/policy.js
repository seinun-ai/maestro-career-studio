/* Maestro CS Companion — never-fill policy shared by both writers. */

// ============================================================
// WHAT THIS FILE PUBLISHES
// ============================================================
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  // NEVER, at any setting. Not a default, not a preference — there is no
  // profile value that authorizes these and no consent that unlocks them.
  //
  // A signature or a set of initials is a distinct ACT rather than an
  // agreement: the field expects you to produce your name, and producing it
  // for you is not the same as ticking a box you were going to tick. The other
  // two are credentials and government identifiers, which are not consent at
  // all — nothing in a settings page makes it right to type a password or an
  // SSN into a page on somebody's behalf.
  const NEVER_FILLED = [
    /signature|\bsign\b|\be-?sign\b|\binitials\b/i,
    /password|passcode/i,
    /social security|\bssn\b|national id|passport number|driver'?s? licen[cs]e number/i,
  ];

  // Agreements: the application's OWN consent boxes. Refused by default and
  // unlocked by a standing consent the user gives once, in Profile — the same
  // shape the EEO opt-in already has, and stored in the same record.
  //
  // Why this stopped being absolute: it is the user's application and their
  // consent, the card never submits anything, and every competitor ticks these.
  // What makes it defensible is that the permission is explicit, recorded with
  // a timestamp and a policy version, and revocable — not that the wording
  // happened to look harmless.
  const CONSENT_FORMS = [
    /\bi\b[^|]{0,25}\b(certify|attest|acknowledge|consent|agree)\b/i,
    /certif(y|ication) that|\b(acknowledge?ment|attestation)\b|\bconsent (to|for)\b|authoriz\w+ (to|for) (release|disclose)/i,
    /\bterms (of|and) (use|service|conditions)\b|terms & conditions|privacy policy|arbitration|waiver|release of liability/i,
  ];

  // What separates a question about YOUR EXPECTATIONS (fillable) from one about
  // what you are paid today (never filled). Published below, because the fill
  // engine's `salary` rule needs exactly this distinction and a second copy of
  // it drifted: the first alternative used to require `desired` ADJACENT to
  // `salary`, so "what is your desired annual base salary or hourly rate?" —
  // live, from the corpus — failed the exemption, matched SALARY_MENTION, and
  // was refused as salary history. One pattern, two consumers, no drift.
  //
  // The run between the two words is bounded on `?` AND `|`, so it cannot reach
  // across a question boundary or between two label sources to manufacture an
  // exemption out of words that were never in the same sentence.
  const SALARY_EXPECTATION =
    /\b(?:expected|desired|target)\b[^?|]{0,30}\b(?:salary|wages?|compensation|pay|rate)\b|\b(?:salary|wages?|compensation|pay)\b[^?|]{0,40}\bexpectations?\b|\b(?:salary|wages?|compensation|pay)\s+(?:expectation|expectations|range)\b/i;
  const SALARY_MENTION = /\b(?:salary|wages?|compensation|ctc)\b/i;

  /** `consentForms` comes from the backend's standing consent and defaults to
   * FALSE — an omitted argument is the absence of permission, never its
   * presence, so a caller that has not been taught about it cannot accidentally
   * unlock anything. */
  const isPolicyBlocked = (labelText, { consentForms = false } = {}) => {
    const label = String(labelText ?? "");
    if (NEVER_FILLED.some((pattern) => pattern.test(label))) return true;
    if (CONSENT_FORMS.some((pattern) => pattern.test(label))) return !consentForms;
    if (SALARY_EXPECTATION.test(label)) return false;
    if (SALARY_MENTION.test(label)) return true;
    return false;
  };

  ns.isPolicyBlocked = isPolicyBlocked;
  // The same family, as one pattern, for the fill rule that ticks these once
  // consent is given. Published rather than restated: the list that REFUSES a
  // field and the list that fills it must be the same list, or a wording will
  // sooner or later be in one and not the other.
  ns.consentFormRe = new RegExp(
    CONSENT_FORMS.map((pattern) => pattern.source).join("|"), "i");
  ns.salaryExpectationRe = SALARY_EXPECTATION;
})();
