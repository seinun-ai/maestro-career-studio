/* Maestro CS Companion — never-fill policy shared by both writers. */

// ============================================================
// WHAT THIS FILE PUBLISHES
// ============================================================
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  // THE RULE (owner's decision, 2026-09-26). Without the standing
  // `consent_forms` permission, the two lists below and the salary rule refuse
  // a field by its label. With it, NOTHING is refused by label: it is the
  // user's application and their recorded, revocable consent, and the
  // extension never clicks Next / Save and Continue or Submit — those stay the
  // user's at every setting, enforced by the engines, not here. Consent removes
  // the refusal; it does not invent a value — an engine still writes only what
  // it has a fact for.
  //
  // Without the permission these are fields the user produces themselves: a
  // signature or a set of initials (an act, not a box to tick), credentials,
  // and government identifiers.
  const NEVER_FILLED = [
    /signature|\bsign\b|\be-?sign\b|\binitials\b/i,
    /password|passcode/i,
    /social security|\bssn\b|national id|passport number|driver'?s? licen[cs]e number/i,
  ];

  // Agreements: the application's OWN consent boxes. Refused without the
  // permission, which the user gives once in Profile, stored in the same record
  // as the EEO opt-in. What makes unlocking them (and everything above)
  // defensible is that the permission is explicit, recorded with a timestamp
  // and a policy version, and revocable — not that the wording happened to
  // look harmless.
  const CONSENT_FORMS = [
    /\bi\b[^|]{0,25}\b(certify|attest|acknowledge|consent|agree)\b/i,
    /certif(y|ication) that|\b(acknowledge?ment|attestation)\b|\bconsent (to|for)\b|authoriz\w+ (to|for) (release|disclose)/i,
    /\bterms (of|and) (use|service|conditions)\b|terms & conditions|privacy policy|arbitration|waiver|release of liability/i,
  ];

  // What separates a question about YOUR EXPECTATIONS (fillable) from one about
  // what you are paid today (refused without the permission). Published below,
  // because the fill engine's `salary` rule needs exactly this distinction and
  // a second copy of it drifted: the first alternative used to require
  // `desired` ADJACENT to `salary`, so "what is your desired annual base
  // salary or hourly rate?" —
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
   * unlock anything. Only a literal `true` is the permission; a truthy
   * stand-in (a "true" string, a 1) is not. */
  const isPolicyBlocked = (labelText, { consentForms = false } = {}) => {
    if (consentForms === true) return false;
    const label = String(labelText ?? "");
    if (NEVER_FILLED.some((pattern) => pattern.test(label))) return true;
    if (CONSENT_FORMS.some((pattern) => pattern.test(label))) return true;
    if (SALARY_EXPECTATION.test(label)) return false;
    if (SALARY_MENTION.test(label)) return true;
    return false;
  };

  ns.isPolicyBlocked = isPolicyBlocked;
  // The agreement family, as one pattern, for the old engine's rule that ticks
  // these once consent is given. Published rather than restated: the list that
  // REFUSES a field and the list that fills it must be the same list, or a
  // wording will sooner or later be in one and not the other.
  ns.consentFormRe = new RegExp(
    CONSENT_FORMS.map((pattern) => pattern.source).join("|"), "i");
  ns.salaryExpectationRe = SALARY_EXPECTATION;
  // A popup's "choose something" text ("Select One", "Select…", "-- Select --",
  // "Please choose an option", iCIMS's "— Make a Selection —" and "Please
  // select a country"): never a question and never a value. ONE definition,
  // read by the field reader and shapes (a popup showing it holds nothing),
  // fill-core (it is never chosen as an answer) and the fill loop (it is never
  // reported filled). Shape only: an article or "your" and one or two words
  // after the verb, so "Select Medical" or "Choose Health" (an answer) never
  // reads as one.
  const PLACEHOLDER = new RegExp("^[-–—\\s]*(?:(?:\\.{2,}|…)\\s*)?(?:(?:please\\s+)?(?:make\\s+a\\s+selection"
    + "|(?:select|choose|pick)(?:\\s+(?:one(?:\\s+or\\s+more)?|all\\s+that\\s+apply"
    + "|(?:an?|your)\\s+\\p{L}+(?:[\\s/]\\p{L}+)?))?))?\\s*(?:\\.{2,}|…)?[-–—\\s]*$", "iu");
  ns.isPlaceholderText = (s) => PLACEHOLDER.test(String(s ?? ""));
})();
