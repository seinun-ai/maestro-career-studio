/* Maestro CS Companion — read the page for the queued run, and press its Next.
 *
 * `summary()` turns the document into the plain object `shared/page-kind.js` classifies: counts,
 * button texts and booleans, NEVER an input's value or the page's prose (inv-autofill-telemetry-
 * no-values). `advance(id)` is the one place in the extension that presses a navigation button,
 * and it presses a button only when that button's text, read AGAIN right now, sorts "next".
 *
 * THE ONE RULE (design Part 2): a Submit-worded button is never clicked, at any setting. The
 * sort happens twice on purpose: once to classify (so a Submit never becomes the offered Next),
 * once here at click time (so a page that relabelled the button, or a stale or forged id, still
 * cannot reach a Submit). Every label a person or a screen reader could read counts; if any one of
 * them carries a Submit word the button is a Submit.
 *
 * WHAT THIS FILE PUBLISHES: ns.pageReader = { summary, advance }.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  const BUTTONS = 'button, input[type="submit"], input[type="button"], a[role="button"]';
  const APPLY_TEXT = /^\s*apply( now| for this job)?\s*$/i;
  const CONFIRMATION = /thank you for (applying|your application)|application (was )?(submitted|received)|we('ve| have) received your application/i;
  const CLOSED = /no longer (accepting applications|available)|this (job|position) (has been|is) (closed|filled)/i;
  const BOARD_HOST = /(^|\.)(linkedin|indeed)\.com$/i;
  const CONFIRM_PASSWORD = /confirm|re-?enter|re-?type|repeat|verify/i;
  const ONE_TIME_CODE = /\botp\b|one[- ]?time|verification code|security code|confirmation code|authentication code|passcode/i;
  // Site chrome: a "Continue" in a header or nav is the site's, never the application step's.
  const CHROME = 'header, nav, [role="banner"], [role="navigation"], [role="search"], [role="contentinfo"], [role="menubar"]';
  const FORM = 'form, [role="form"]';
  const FIELD = 'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"])'
    + ':not([type="image"]):not([type="search"]), select, textarea';
  const MAX_TEXT = 80;
  const BODY_SLICE = 20000;

  // Per frame, so the panel's broadcast of one id can match a button in at most this frame:
  // another frame's ids carry its own tag and answer "not_next".
  const FRAME_TAG = Math.random().toString(36).slice(2, 6);
  let seq = 0;

  const squash = (s) => String(s ?? "").replace(/\s+/g, " ").trim();
  const sortOf = (text) => ns.pageKind.sortButton({ text });

  // Non-zero box and not visibility:hidden. A Submit that is only display:none is not one the
  // person can press; a Next that is would be a click on nothing.
  const shown = (el) => {
    if (!el.isConnected) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
  };
  const enabled = (el) => !el.matches(":disabled") && el.getAttribute("aria-disabled") !== "true";

  /** Every text a button answers to: what it shows, its accessible name, its tooltip. */
  const labels = (el) => {
    const named = (el.getAttribute("aria-labelledby") ?? "").split(/\s+/)
      .map((id) => el.ownerDocument.getElementById(id)?.textContent);
    const shownText = el instanceof HTMLInputElement
      ? el.value || (el.type === "submit" ? "Submit" : "")   // an unlabelled submit input reads "Submit"
      : el.textContent;
    return [shownText, ...named, el.getAttribute("aria-label"), el.getAttribute("title")].map(squash).filter(Boolean);
  };
  /** The one label the sort reads: a Submit-worded one if ANY label is, else the shown text. */
  const labelOf = (el) => {
    const all = labels(el);
    return all.find((text) => sortOf(text) === "submit") ?? all[0] ?? "";
  };

  /** The label clipped for the summary. A Submit word the clip would cut off stays visible to the
   * classifier, which sees only these 80 characters. */
  const clip = (label) => {
    if (label.length <= MAX_TEXT) return label;
    const cut = label.slice(0, MAX_TEXT);
    return sortOf(label) === "submit" && sortOf(cut) !== "submit" ? `Submit ${label.slice(0, MAX_TEXT - 7)}` : cut;
  };

  // The forms that hold the application's own fields. A header search form does not count, and
  // when no form holds fields (some wizards render none) every non-chrome button is the step's.
  const fieldForms = () => [...document.querySelectorAll(FORM)]
    .filter((f) => !f.closest(CHROME) && f.querySelector(FIELD));

  const inFormOf = (forms) => (el) => {
    if (!forms.length) return !el.closest(CHROME);
    const form = el.form ?? el.closest(FORM);
    return forms.some((f) => f === form || f.contains(el));
  };

  const challengeFrame = (iframe) => {
    const src = iframe.getAttribute("src") ?? "";
    const r = iframe.getBoundingClientRect();
    if (r.width < 50 || r.height < 50) return false;
    // Parked out of sight (the usual home of a challenge that is not asked yet).
    if (r.right + window.scrollX <= 0 || r.bottom + window.scrollY <= 0) return false;
    for (let n = iframe; n; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.visibility === "hidden" || s.display === "none" || Number(s.opacity) === 0) return false;
    }
    if (/recaptcha\/api2\/bframe|hcaptcha\.com|challenges\.cloudflare\.com/.test(src)) return true;
    // The "I'm not a robot" box. The invisible variant sits in a badge, or says size=invisible.
    return /recaptcha\/api2\/anchor/.test(src) && !/size=invisible/.test(src) && !iframe.closest(".grecaptcha-badge");
  };

  const passwordInputs = () => [...document.querySelectorAll('input[type="password"]')].filter(shown);

  const isConfirmPassword = (el) => {
    if ((el.getAttribute("autocomplete") ?? "").toLowerCase() === "new-password") return true;
    const own = [el.name, el.id, el.placeholder, el.getAttribute("aria-label"), ...[...(el.labels ?? [])].map((l) => l.textContent)];
    return own.some((s) => CONFIRM_PASSWORD.test(s ?? ""));
  };

  const isCodeInput = (el) => {
    if ((el.getAttribute("autocomplete") ?? "").toLowerCase().includes("one-time-code")) return true;
    const own = [el.name, el.id, el.placeholder, el.getAttribute("aria-label"), ...[...(el.labels ?? [])].map((l) => l.textContent)];
    return own.some((s) => ONE_TIME_CODE.test(s ?? ""));
  };

  /** The page, as plain data for `ns.pageKind.classify`. Re-tags every button (`data-maestro-btn`)
   * so an id from an earlier call stops naming anything. */
  function summary() {
    for (const old of document.querySelectorAll("[data-maestro-btn]")) old.removeAttribute("data-maestro-btn");
    const inForm = inFormOf(fieldForms());
    const buttons = [...document.querySelectorAll(BUTTONS)].map((el) => {
      const id = `${FRAME_TAG}-${++seq}`;
      el.setAttribute("data-maestro-btn", id);
      return {
        id,
        text: clip(labelOf(el)),
        type: el.tagName === "A" ? "link" : (el.getAttribute("type") || (el.tagName === "BUTTON" ? "submit" : "text")).toLowerCase(),
        marker: el.getAttribute("data-automation-id") ?? "",
        inForm: inForm(el),
        visible: shown(el),
        enabled: enabled(el),
      };
    });
    const bodyText = (document.body?.innerText ?? "").slice(0, BODY_SLICE);
    const passwords = passwordInputs();
    return {
      host: location.hostname,
      buttons,
      passwordInputs: passwords.length,
      confirmPassword: passwords.some(isConfirmPassword),
      otpInput: [...document.querySelectorAll("input")].some((el) => el.type !== "password" && shown(el) && isCodeInput(el)),
      captchaVisible: [...document.querySelectorAll("iframe")].some(challengeFrame),
      fillable: ns.fillableControls(),
      hasApplyLink: [...document.querySelectorAll(`a[href], ${BUTTONS}`)].some((el) => shown(el) && labels(el).some((t) => APPLY_TEXT.test(t))),
      confirmationText: CONFIRMATION.test(bodyText),
      closedText: CLOSED.test(bodyText),
      boardNative: BOARD_HOST.test(location.hostname),
    };
  }

  /** Press the Next button the last `summary()` named `id`, if it is still one. Returns
   * `{clicked: true}` or `{clicked: false, why}`: "submit" (its text now carries a Submit word),
   * "not_next" (no such tagged button, or it is hidden, disabled or not worded as a Next). */
  function advance(id) {
    if (typeof id !== "string" || !id) return { clicked: false, why: "not_next" };
    const el = document.querySelector(`[data-maestro-btn="${CSS.escape(id)}"]`);
    if (!el || !el.matches(BUTTONS)) return { clicked: false, why: "not_next" };
    // Re-sorted from the CURRENT labels, before any other check: the Submit refusal never
    // depends on what the panel was told earlier.
    const sort = sortOf(labelOf(el));
    if (sort === "submit") return { clicked: false, why: "submit" };
    if (sort !== "next" || !shown(el) || !enabled(el)) return { clicked: false, why: "not_next" };
    el.click();
    return { clicked: true };
  }

  ns.pageReader = { summary, advance };
})();
