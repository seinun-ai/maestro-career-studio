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
 * cannot reach a Submit). The ATS table's verdict (shared/ats-buttons.js) joins the sort both
 * times, re-read from the button itself at click time. Every label a person or a screen reader
 * could read counts; if any one of them carries a Submit word the button is a Submit.
 *
 * The Apply of a POSTING is the one narrow exception, and it is its own call: `advance(id, {apply:
 * true})`. "Apply" is a Submit word, so the plain call still refuses it. The apply call presses only
 * what `summary().applyId` named, on a page with no fillable control, and only when EVERY label the
 * control answers to is exactly an apply wording (APPLY_TEXT): "Apply", "Apply now", "Apply for this
 * job". Whether the run may ask (the first page, nothing filled yet, the apply link's own host) is
 * the driver's (shared/queue-run.js); the page re-checks what it can see.
 *
 * `signIn` is the one place the saved job-site login is typed (design Part 4,
 * inv-job-site-password-local). It runs in the TOP frame only, on the host the run reached from the
 * job's apply link, on a page with exactly one plain password box; account creation, email codes and
 * CAPTCHAs are refused and park. The password is a parameter of that one call: never stored, never
 * logged, never in the return value (a fixed reason word, nothing else).
 *
 * `applyLink` / `applyTarget` read the EMPLOYER's apply link off the posting page the user is
 * viewing (design Part 7): an absolute http(s) link to another site, never fetched, never followed.
 *
 * WHAT THIS FILE PUBLISHES: ns.pageReader = { summary, advance, signIn, applyUrl, applyLink, applyTarget }.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  const BUTTONS = 'button, input[type="submit"], input[type="button"], a[role="button"]';
  const APPLY_TEXT = /^\s*apply( now| for this job)?\s*$/i;
  const CONFIRMATION = /thank you for (applying|your application)|application (was )?(submitted|received)|we('ve| have) received your application/i;
  const CLOSED = /no longer (accepting applications|available)|this (job|position) (has been|is) (closed|filled)/i;
  // An external Apply link often says where it goes ("Apply on company site"), which APPLY_TEXT
  // alone would not match; the link reader accepts either.
  const APPLY_OFFSITE_TEXT = /^\s*apply\b[^.]{0,30}\b(company|employer)(?:'s|\u2019s)?\s+(?:web)?site\s*$/i;
  // The backend's ceiling on `apply_url` (a longer one is a 422 that would lose the whole save).
  const MAX_APPLY_URL = 2048;
  const BOARD_HOST = /(^|\.)(linkedin|indeed)\.com$/i;
  const CONFIRM_PASSWORD = /confirm|re-?enter|re-?type|repeat|verify/i;
  const ONE_TIME_CODE = /\botp\b|one[- ]?time|verification code|security code|confirmation code|authentication code|passcode/i;
  // Site chrome: a "Continue" in a header or nav is the site's, never the application step's.
  const CHROME = 'header, nav, [role="banner"], [role="navigation"], [role="search"], [role="contentinfo"], [role="menubar"]';
  const FORM = 'form, [role="form"]';
  // "Continue" is allowed here: pressing it on a sign-in page is not a submit of the application.
  const SIGN_IN_BUTTON = /^\s*(sign in|log in|login|continue|next)\s*$/i;
  const EMAIL_LABEL = /e-?mail|user ?name/i;
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

  /** What this vendor's table (shared/ats-buttons.js) says of the button, read from its own
   * markers on the page's host. Re-derived wherever it is used: `advance` never trusts a verdict
   * it was handed. Null for an unlisted host or marker, and then the text alone decides. */
  const verdictOf = (el) => ns.atsButtons.knownSort(location.hostname, {
    id: el.getAttribute("id"),
    qa: el.getAttribute("data-qa"),
    automationId: el.getAttribute("data-automation-id"),
  });
  // What the sort is handed: "text" (the vendor's navigation button, whose own label decides)
  // hands it nothing, so the text alone decides Next or Submit.
  const knownOf = (el) => {
    const verdict = verdictOf(el);
    return verdict === "text" ? null : verdict;
  };
  /** The vendor's own navigation button, wherever it sits: it counts as the step's even when a
   * site-wide form elsewhere (a newsletter box in the footer) made that form "the form". */
  const isNavigation = (el) => verdictOf(el) === "text";

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
    // A token LIST ("section-signup new-password") counts: the token, not the whole attribute.
    if ((el.getAttribute("autocomplete") ?? "").toLowerCase().split(/\s+/).includes("new-password")) return true;
    const own = [el.name, el.id, el.placeholder, el.getAttribute("aria-label"), ...[...(el.labels ?? [])].map((l) => l.textContent)];
    return own.some((s) => CONFIRM_PASSWORD.test(s ?? ""));
  };

  const isCodeInput = (el) => {
    if ((el.getAttribute("autocomplete") ?? "").toLowerCase().includes("one-time-code")) return true;
    const own = [el.name, el.id, el.placeholder, el.getAttribute("aria-label"), ...[...(el.labels ?? [])].map((l) => l.textContent)];
    return own.some((s) => ONE_TIME_CODE.test(s ?? ""));
  };

  const tag = (el) => {
    const id = `${FRAME_TAG}-${++seq}`;
    el.setAttribute("data-maestro-btn", id);
    return id;
  };

  // Every label is an apply wording, nothing more: "Apply for Staff Engineer" in an aria-label is
  // not "Apply", and a control that answers to a second wording is not the plain posting Apply.
  const isApply = (el) => {
    const all = labels(el);
    return all.length > 0 && all.every((t) => APPLY_TEXT.test(t));
  };

  /** A short, stable key for the step's heading (the page's first visible h1 or h2): the same step
   * reads the same, another step differs, and the heading itself never leaves the page (the summary
   * carries no prose). It tells two wizard steps apart that share a URL and a button row. */
  function stepKey() {
    const heading = [...document.querySelectorAll("h1, h2")].find((el) => shown(el) && !el.closest(CHROME) && squash(el.textContent));
    if (!heading) return "";
    let hash = 0x811c9dc5;
    for (const ch of squash(heading.textContent).toLowerCase()) hash = Math.imul(hash ^ ch.charCodeAt(0), 0x01000193) >>> 0;
    return hash.toString(36);
  }

  /** The page, as plain data for `ns.pageKind.classify`. Re-tags every button (`data-maestro-btn`)
   * so an id from an earlier call stops naming anything. */
  function summary() {
    for (const old of document.querySelectorAll("[data-maestro-btn]")) old.removeAttribute("data-maestro-btn");
    const inForm = inFormOf(fieldForms());
    const buttons = [...document.querySelectorAll(BUTTONS)].map((el) => {
      const id = tag(el);
      const known = knownOf(el);
      return {
        id,
        text: clip(labelOf(el)),
        type: el.tagName === "A" ? "link" : (el.getAttribute("type") || (el.tagName === "BUTTON" ? "submit" : "text")).toLowerCase(),
        marker: el.getAttribute("data-automation-id") ?? "",
        inForm: inForm(el) || isNavigation(el),
        visible: shown(el),
        enabled: enabled(el),
        ...(known ? { known } : {}),
      };
    });
    const bodyText = (document.body?.innerText ?? "").slice(0, BODY_SLICE);
    const passwords = passwordInputs();
    // The posting's plain Apply, named for the one narrow `advance(id, {apply: true})` call. A link
    // is not in `buttons`, so it is tagged here (a button keeps the id it was given above).
    const applyEl = [...document.querySelectorAll(`a[href], ${BUTTONS}`)].find((el) => shown(el) && enabled(el) && isApply(el));
    return {
      host: location.hostname,
      stepKey: stepKey(),
      applyId: applyEl ? applyEl.getAttribute("data-maestro-btn") ?? tag(applyEl) : null,
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

  const withoutWww = (host) => String(host ?? "").toLowerCase().replace(/^www\./, "");

  const sendable = (raw) => /^https?:\/\/[^\s/?#]\S*$/i.test(raw) && raw.length <= MAX_APPLY_URL;

  /** LinkedIn sends an external Apply through its own interstitial,
   * `https://www.linkedin.com/safety/go/?url=<the employer's address, encoded>`. The employer's
   * address is the `url` parameter, decoded. This one known shape and nothing generic, and only
   * one level deep: what it carries still goes through every check `applyTarget` makes. */
  function linkedinRedirectTarget(raw) {
    try {
      const url = new URL(raw);
      if (/(^|\.)linkedin\.com$/i.test(url.hostname) && /^\/safety\/go\/?$/.test(url.pathname)) {
        return (url.searchParams.get("url") ?? "").trim();
      }
    } catch (_) { /* not an address at all; the caller's checks say so */ }
    return raw;
  }

  /** `href` when it is an absolute http(s) address on a DIFFERENT site from this page's, else
   * null. Relative, `javascript:`, `mailto:` and same-site addresses are not an employer's link:
   * a board's own Apply (LinkedIn Easy Apply, Indeed Apply) stays on the board and has none.
   * LinkedIn's `/safety/go/?url=` redirect is read through to the address it carries.
   * Returned as written (trimmed, tracking parameters and all): the backend owns what counts as
   * the same posting. */
  function applyTarget(href) {
    const given = typeof href === "string" ? href.trim() : "";
    // A host straight after the slashes: the backend rejects `http://` and `https:///x` outright.
    if (!sendable(given)) return null;
    const raw = linkedinRedirectTarget(given);
    if (!sendable(raw)) return null;
    try {
      return withoutWww(new URL(raw).hostname) === withoutWww(location.hostname) ? null : raw;
    } catch (_) {
      return null;
    }
  }

  /** The employer's apply link off this page: the first visible link worded as Apply whose href
   * `applyTarget` accepts. Reads the document only; a button has no address to read. */
  function applyLink() {
    for (const el of document.querySelectorAll("a[href]")) {
      if (!shown(el) || !labels(el).some((t) => APPLY_TEXT.test(t) || APPLY_OFFSITE_TEXT.test(t))) continue;
      const target = applyTarget(el.getAttribute("href"));
      if (target) return target;
    }
    return null;
  }

  /** The employer's apply link for a posting page, or null: the posting's structured `url` when
   * it points off this site, else a visible external Apply link. Board-native apply has none, and
   * the panel then omits `apply_url`. Read from the page the user is on and nothing else. */
  const applyUrl = (posting) => applyTarget(posting?.url) ?? applyLink();

  /** The posting's Apply, pressed on the driver's say-so and the page's own re-check: the control
   * the last `summary()` named `applyId`, no fillable control anywhere on the page, and every label
   * exactly an apply wording. `{clicked: true}` or `{clicked: false, why}`: "not_apply" (not that
   * control, or not plainly worded as Apply), "not_posting" (the page has fields: it is a form, and
   * its Apply-worded button is a Submit), "submit" (the vendor's table calls it one). */
  function pressApply(id) {
    const el = typeof id === "string" && id ? document.querySelector(`[data-maestro-btn="${CSS.escape(id)}"]`) : null;
    if (!el || !el.matches(`a[href], ${BUTTONS}`)) return { clicked: false, why: "not_apply" };
    if (ns.fillableControls() > 0) return { clicked: false, why: "not_posting" };
    if (knownOf(el) === "submit") return { clicked: false, why: "submit" };
    if (!shown(el) || !enabled(el) || !isApply(el)) return { clicked: false, why: "not_apply" };
    el.click();
    return { clicked: true };
  }

  /** Press the Next button the last `summary()` named `id`, if it is still one. Returns
   * `{clicked: true}` or `{clicked: false, why}`: "submit" (its text now carries a Submit word),
   * "not_next" (no such tagged button, or it is hidden, disabled or not worded as a Next).
   * `{apply: true}` is the posting's Apply instead (pressApply), and only that. */
  function advance(id, { apply = false } = {}) {
    if (apply === true) return pressApply(id);
    if (typeof id !== "string" || !id) return { clicked: false, why: "not_next" };
    const el = document.querySelector(`[data-maestro-btn="${CSS.escape(id)}"]`);
    if (!el || !el.matches(BUTTONS)) return { clicked: false, why: "not_next" };
    // Re-sorted from the CURRENT labels and the table's verdict for this very button, before any
    // other check: the Submit refusal never depends on what the panel was told earlier. A Submit
    // word in the text beats the table's "next"; the table's "submit" beats a Next-worded text.
    const sort = ns.pageKind.sortButton({ text: labelOf(el), known: knownOf(el) });
    if (sort === "submit") return { clicked: false, why: "submit" };
    if (sort !== "next" || !shown(el) || !enabled(el)) return { clicked: false, why: "not_next" };
    el.click();
    return { clicked: true };
  }

  // The email or username box of the sign-in form: by type, then by autocomplete token, then by a
  // label (or name, placeholder, aria-label) that says so. Only a text-like input that can be typed in.
  const emailBox = (scope) => {
    const boxes = [...scope.querySelectorAll("input")].filter((el) => shown(el) && enabled(el) && !el.readOnly
      && !/^(password|hidden|checkbox|radio|file|submit|button|reset|image|search)$/.test(el.type));
    const named = (el) => [el.name, el.placeholder, el.getAttribute("aria-label"), ...[...(el.labels ?? [])].map((l) => l.textContent)]
      .some((text) => EMAIL_LABEL.test(text ?? ""));
    return boxes.find((el) => el.type === "email")
      ?? boxes.find((el) => (el.getAttribute("autocomplete") ?? "").toLowerCase().split(/\s+/).includes("username"))
      ?? boxes.find(named) ?? null;
  };

  /** Type the saved login into the sign-in form and press its Sign in. `{signedIn: "clicked"}` when
   * the button was pressed (whether the site accepted the login is the next page's business), else
   * `{signedIn: false, why}`: "frame", "missing", "host", "captcha", "no_form", "create_account",
   * "verify", "no_email", "locked", "no_button", then after typing began "typing", "button" (the
   * button changed while typing) and "click". The button is found before the first key, so a page
   * with no safe button never holds the password.
   *
   * NEVER THROWS, and never returns an error's text: page script runs during typing and the click
   * (input and submit handlers), and its exception message could be the value just typed. Every
   * failure is a fixed word, so nothing downstream (agent.js's reply, the service worker, the
   * panel) can carry the password. */
  function signIn(args) {
    try {
      return signInOnce(args ?? {});
    } catch {
      return { signedIn: false, why: "error" };
    }
  }

  function signInOnce({ email, password, allowedHost }) {
    if (window.top !== window.self) return { signedIn: false, why: "frame" };
    const text = (v) => typeof v === "string" && v !== "";
    if (!text(email) || !text(password) || !text(allowedHost)) return { signedIn: false, why: "missing" };
    if (location.hostname.toLowerCase() !== allowedHost.toLowerCase()) return { signedIn: false, why: "host" };
    if ([...document.querySelectorAll("iframe")].some(challengeFrame)) return { signedIn: false, why: "captcha" };
    const passwords = passwordInputs();
    if (!passwords.length) return { signedIn: false, why: "no_form" };
    if (passwords.length > 1 || isConfirmPassword(passwords[0])) return { signedIn: false, why: "create_account" };
    if ([...document.querySelectorAll("input")].some((el) => el.type !== "password" && shown(el) && isCodeInput(el))) {
      return { signedIn: false, why: "verify" };
    }
    const box = passwords[0];
    if (!enabled(box) || box.readOnly) return { signedIn: false, why: "locked" };
    const scope = box.form ?? box.closest(FORM) ?? document;
    const emailEl = emailBox(scope);
    if (!emailEl) return { signedIn: false, why: "no_email" };
    const plain = (el) => el.isConnected && !el.closest(CHROME) && shown(el) && enabled(el)
      && SIGN_IN_BUTTON.test(labelOf(el)) && sortOf(labelOf(el)) !== "submit";
    const go = [...scope.querySelectorAll(BUTTONS)].find(plain);
    if (!go) return { signedIn: false, why: "no_button" };

    const { typeText, enter, leave } = ns.fillBase;
    try {
      for (const [el, value] of [[emailEl, email], [box, password]]) {
        enter(el);
        typeText(el, value);
        leave(el);
        if (el.value !== value) return { signedIn: false, why: "typing" };
      }
    } catch {
      return { signedIn: false, why: "typing" };   // a fixed word: an error's text could carry a value
    }
    // Typing ran the page's own input handlers, which can relabel or remove the button: judged again.
    if (!plain(go)) return { signedIn: false, why: "button" };
    try {
      go.click();
    } catch {
      return { signedIn: false, why: "click" };
    }
    return { signedIn: "clicked" };
  }

  ns.pageReader = { summary, advance, signIn, applyUrl, applyLink, applyTarget };
})();
