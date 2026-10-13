/* Maestro CS Companion — what kind of page is this, and which button moves on?
 *
 * Pure: reads a plain summary built in the page (content/page-reader.js), never the DOM, so
 * node tests it and both worlds load it. THE ONE RULE: a button carrying any Submit word is
 * "submit" and is never clicked, at any setting; when in doubt the page is "review" and the
 * queued run stops there (docs/plans/2026-10-10-companion-queued-run-design.md Part 2).
 *
 * EVERY AMBIGUITY BREAKS TOWARD SUBMIT. A Next that was really a Submit sends an application
 * nobody approved, while a Submit that was really a Next only stops a run early. So the Submit
 * words match as substrings (a "Reapply", an "Incomplete" and a "Submit_application" all stop),
 * the Next words must be the WHOLE label, and a visible-but-disabled Submit still counts.
 *
 * WHAT THIS FILE PUBLISHES: ns.pageKind = { classify, sortButton, KINDS }.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  // Substrings, not words: "Reapply", "Resend" and "Incomplete" are all worth a stop. A false
  // Submit costs a stopped run; a false Next costs an application.
  const SUBMIT_WORDS = /submit|appl(y|ying|ies|ied)|send|sent\b|finish|finali[sz]|complet|confirm/;
  // Whole label only, after decoration ("Next →", "Continue.") is trimmed off the ends.
  const NEXT_WORDS = /^(next( step)?|continue|save\s*(and|&)\s*(continue|next)|proceed|review( (your )?application)?)$/;

  /** Lower-cased, one space between words, invisible characters gone, camelCase and snake_case split. */
  function normalise(text) {
    return String(text == null ? "" : text)
      .normalize("NFKC")
      .replace(/[­​-‏⁠﻿]/g, "")
      .replace(/([a-z])([A-Z])/g, "$1 $2")
      .replace(/[_\s]+/g, " ")
      .trim()
      .toLowerCase();
  }

  /** "submit" | "next" | "unclear" for one button. `known` is the ATS table's say (Task 14). */
  function sortButton({ text, known } = {}) {
    const words = normalise(text);
    if (SUBMIT_WORDS.test(words)) return "submit";   // beats a known "next" too
    if (known === "submit" || known === "next") return known;
    if (NEXT_WORDS.test(words.replace(/^[^a-z]+|[^a-z]+$/g, ""))) return "next";
    return "unclear";
  }

  function classify(s) {
    if (s.captchaVisible) return { kind: "captcha" };
    // Two or more password inputs is a sign-up or a change-password form even when the confirm
    // field is unlabelled: this run never fills a password, so it parks.
    if (s.confirmPassword || (s.passwordInputs ?? 0) > 1) return { kind: "create_account" };
    if (s.otpInput) return { kind: "verify" };
    if (s.passwordInputs === 1) return { kind: "sign_in" };
    if (s.confirmationText && !s.fillable) return { kind: "confirmation" };
    if (s.closedText) return { kind: "closed" };
    if (s.hasApplyLink && !s.fillable) return { kind: s.boardNative ? "board_native" : "posting" };

    const sorted = (s.buttons ?? []).map((b) => ({ ...b, sort: sortButton(b) }));
    // A Submit counts when it can be SEEN, enabled or not: it is often disabled until the form
    // validates, and a Next beside it is then not to be trusted. Outside the form counts too.
    const submit = sorted.some((b) => b.sort === "submit" && b.visible !== false);
    const next = sorted.filter((b) => b.sort === "next" && b.visible && b.enabled && b.inForm !== false);
    if (submit) return { kind: "review" };
    if (s.fillable > 0) {
      // Exactly one Next is the step; none or several is not sure, so the run stops here.
      return next.length === 1 ? { kind: "form_step", next: next[0].id } : { kind: "review" };
    }
    return { kind: "unknown" };
  }

  ns.pageKind = { classify, sortButton, KINDS: ["captcha", "create_account", "verify", "sign_in",
    "confirmation", "closed", "posting", "board_native", "form_step", "review", "unknown"] };
})();
