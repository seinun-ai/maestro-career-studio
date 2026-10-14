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
 * WHAT THIS FILE PUBLISHES: ns.pageKind = { classify, sortButton, isPlainNext, submitMarked, movesOn, KINDS }.
 * (submitMarked and movesOn read one button element's attributes and words, nothing else of the DOM.)
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  // Mostly substrings, not words: "Reapply", "Incomplete" and "Finished" are all worth a stop. A
  // false Submit costs a stopped run; a false Next costs an application. The exception is
  // send/sent, which are bounded: "sent" ends "Consent", "Present" and "Represent", and a consent
  // step parking every run would be its own bug. ("appl" needs a y/ies/ied after it, so "Apple",
  // "Applicant" and "application" are not Submit words.)
  const SUBMIT_WORDS = /submit|appl(y|ying|ies|ied)|\b(re)?(send|sends|sending|sent)\b|finish|finali[sz]|complet|confirm/;
  // Whole label only, after decoration ("Next →", "Continue.") is trimmed off the ends.
  const NEXT_WORDS = /^(next( step)?|continue|save\s*(and|&)\s*(continue|next)|proceed|review( (your )?application)?)$/;

  // The Next wordings that can only mean "the next page of the form": a page with nothing on it to fill
  // and one of these is a step. A bare "Continue" or "Proceed" there may be the Submit's confirmation.
  const PLAIN_NEXT = /^(next( step)?|save\s*(and|&)\s*(continue|next))$/;

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

  /** Whether a button's text is a plain Next ("Next", "Next step", "Save and continue/next"). */
  function isPlainNext(text) {
    return PLAIN_NEXT.test(normalise(text).replace(/^[^a-z]+|[^a-z]+$/g, ""));
  }

  /** The id, name, data-qa, data-automation-id or formaction says submit. Not the label: a page
   * names its Submit that way when the label is an icon, "Done" or a translation. */
  const SUBMIT_MARK_ATTRS = ["id", "name", "data-qa", "data-automation-id", "formaction"];
  const submitMarked = (el) => SUBMIT_MARK_ATTRS.some((attr) => /submit/i.test(el.getAttribute(attr) ?? ""));

  /** Whether pressing this button element could send the form or move it on: type=submit, a submit
   * mark, or words that sort as a Submit or a Next. A pill group's member never is (a Yes/No answer),
   * and a press of one that is must never happen. */
  function movesOn(el) {
    if (el.getAttribute("type")?.toLowerCase() === "submit" || submitMarked(el)) return true;
    return [el.textContent, el.getAttribute("aria-label"), el.getAttribute("value"), el.getAttribute("title")]
      .some((text) => text && sortButton({ text }) !== "unclear");
  }

  function classify(s) {
    if (s.captchaVisible) return { kind: "captcha" };
    // A job board's own pages are the board's, whatever else is on them: Easy Apply is no "Apply"
    // link, a stray control is no reason to read the page as a form, and the board's sign-in must
    // never be taken for an employer's (the saved employer password is not the board's).
    if (s.boardNative) return { kind: "board_native" };
    // Two or more password inputs is a sign-up or a change-password form even when the confirm
    // field is unlabelled. The page is a wall here; the driver creates the account itself only on a
    // known ATS host (queue-run.js), and the run never types a password anywhere else.
    if (s.confirmPassword || (s.passwordInputs ?? 0) > 1) return { kind: "create_account" };
    if (s.otpInput) return { kind: "verify" };
    if (s.passwordInputs === 1) return { kind: "sign_in" };
    if (s.confirmationText && !s.fillable) return { kind: "confirmation" };
    // The closed words count only on a page with nothing to fill and no Apply: a job description can say
    // "this position has been filled" in its prose, and the form or the Apply beside it says it is open.
    if (s.closedText && !s.fillable && !s.hasApplyLink) return { kind: "closed" };
    if (s.hasApplyLink && !s.fillable) return { kind: "posting" };

    // A button that is only a line of the error summary ("Error - <what>", not marked as a submit by the page)
    // is neither a Next nor a Submit, whatever its words.
    const sorted = (s.buttons ?? []).filter((b) => b.errorLine !== true).map((b) => ({ ...b, sort: sortButton(b) }));
    // A Submit counts when it can be SEEN, enabled or not: it is often disabled until the form
    // validates, and a Next beside it is then not to be trusted. Outside the form counts too.
    const submits = sorted.filter((b) => b.sort === "submit" && b.visible !== false);
    // A Next that could be pressed: visible, enabled, and the step's. The error summary's own buttons
    // ("Errors Found", "Error - <field>") and site chrome (a header Continue) are never the step's Next.
    const pressable = (b) => b.sort === "next" && b.visible && b.enabled && b.inErrors !== true && b.chrome !== true;
    // Inside a form first. A page whose fields sit in several <form>s often keeps its footer Next in a
    // bar outside every one of them (ATS-D): when no Next is inside a form, the ONE pressable Next
    // anywhere in the application (not in chrome) is the step's.
    const inForms = sorted.filter((b) => pressable(b) && b.inForm !== false);
    // The fallback leaves out a dialog's or a cookie notice's Next: it is not the application's unless a form holds it.
    const next = inForms.length ? inForms : sorted.filter((b) => pressable(b) && b.overlay !== true);
    // A Next still on the page, enabled or not: the application is not over while one remains. A cookie
    // notice's or a dialog's Continue outside every form is not the application's.
    const realNext = sorted.some((b) => b.sort === "next" && b.visible && b.inErrors !== true && b.chrome !== true
      && !(b.overlay === true && b.inForm === false));
    // `submitSeen`: a Submit the button list could not see (a div role=button, an image input, a
    // plain link, or a control whose id or name says submit). `submitContext`: a dialog or the
    // step's own heading asks about submitting ("Submit your application?"), so its Proceed is the
    // Submit's. Either one stops the run the way a visible Submit button does.
    //
    // `by` says WHY a page is a review, because only one reason is the end of an application: a real
    // Submit control (inside the application, not the site's header) and no real Next beside it. The
    // others are "stop, don't know": a Submit the list could not see, a dialog that asks, several Nexts,
    // or fields and no Next.
    if (submits.length || s.submitSeen || s.submitContext) {
      const own = submits.some((b) => b.chrome !== true);
      if (own) return { kind: "review", by: realNext ? "several_next" : "submit_button" };
      return { kind: "review", by: submits.length || s.submitSeen ? "submit_seen" : "submit_context" };
    }
    // Exactly one Next is the step, even with nothing to fill (an intro or "before you apply"
    // page should advance). Several, or fields with no Next, is not sure: the run stops here.
    if (next.length === 1) return { kind: "form_step", next: next[0].id };
    if (s.fillable > 0 || next.length > 1) return { kind: "review", by: next.length > 1 ? "several_next" : "fields_no_next" };
    return { kind: "unknown" };
  }

  ns.pageKind = { classify, sortButton, isPlainNext, submitMarked, movesOn, KINDS: ["captcha", "create_account", "verify", "sign_in",
    "confirmation", "closed", "posting", "board_native", "form_step", "review", "unknown"] };
})();
