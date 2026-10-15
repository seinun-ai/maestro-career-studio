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
 * what `summary().applyId` named, on a page with no fillable control, when the VISIBLE text is
 * exactly an apply wording (APPLY_TEXT: "Apply", "Apply now", "Apply for this job") and any other
 * label (aria-label, title) is an apply wording or "Apply for/to/at <something>" that carries no
 * Submit word. And it presses only a real navigation LINK (an <a> with an http(s) href that is not
 * "#", not javascript:, and no target but the same tab; target=_blank is allowed for this call alone, and only to this
 * page's own site or a known applicant system, because the press NAVIGATES this tab and opens nothing). A <button>
 * Apply is never pressed, form or no form: a form-less one is page script (a quick-apply, a
 * draft's review) that may well send the application, so the page parks as a posting. The link is
 * NAVIGATED to (location.assign of its checked address), never clicked: a click would run its
 * onclick or router script, which can send the application too. Whether the run may ask at all
 * (the first page of a tab it opened itself) is the driver's (shared/queue-run.js).
 *
 * A FIELD'S OWN CONTROL IS NEVER AN ACTION. A Workday question popup carries its question in its
 * aria-label ("... would you be willing to submit to a background check? Select One Required"), and a
 * label sorted by its words would make the popup a Submit. So `summary()` marks (`fieldControl`) and
 * leaves out of the Submit/Next sort, and out of `submitSeen`: a popup button, a pill-group member, and a
 * button inside a field holder (a formField wrapper, or a fieldset or group that holds another field)
 * unless it is a form's own submit button (a button with no type inside a form, or `type=submit`) or one the page
 * marks as a submit, or it is a menu button (`aria-haspopup="true"`) or a button in a holder whose SHOWN text says
 * Submit or Send, or a holder button worded as a Next. A listbox popup and a pill (a button holding `aria-pressed` beside others)
 * show the answer picked, which may say those words and is still the field's. The vendor's footer Next (shared/ats-buttons.js, "text") is marked
 * `navigation`: the classifier takes it as the step's Next over a Submit the button list could not see.
 *
 * The Workday START CHOOSER is the second narrow exception, `advance(id, {chooser: true})`. "Apply Manually" is a Submit
 * word too, on a page of three same-tab links of which two do something to the user's data. `summary().chooserId`
 * names a link only when the page has no fillable control and exactly one link matches the recorded row
 * (shared/ats-buttons.js `isChooser`: host, automation id, exact text, end of the path), is a plain same-tab http(s)
 * link on the page's own host, and is not marked as a submit. The press re-checks all of it and NAVIGATES
 * (location.assign of the checked address); it never clicks. Whether the run may ask at all is the driver's.
 *
 * `pageErrors()` reads what the page itself complains about after a Next it refused: its error
 * summary (an alert or live region, or a list headed "Errors Found") and each field it marks
 * invalid, upload boxes and popup buttons included. ONE LINE, ONE NAME: Workday sets the "Error - <question>" button
 * and "The field <question> is required and must have a value." in one list item with no space between, so a line is
 * read from its own button or its own first line, never across the two, and a name that maps to no field is tried
 * again as the name in the "The field X is required" sentence. Words only, never a value: `{count, items: [{label, target, kind}]}`,
 * `label` the page's own wording for the field, `target` the handle of the field it names (a fill
 * field's `fid`, or an upload box's `data-maestro-up` tag), `kind` "field" | "upload" | "unknown".
 * `summary().errors` is the count alone, and the summary's own buttons carry `inErrors` so the
 * driver's page fingerprint ignores them: a banner that adds buttons is not a page that moved.
 *
 * `signIn` is the one place the saved job-site login is typed (design Part 4,
 * inv-job-site-password-local). It runs in the TOP frame only, on the host the run reached from the
 * job's apply link, on a page with exactly one plain password box; account creation, email codes and
 * CAPTCHAs are refused and park. The password is a parameter of that one call: never stored, never
 * logged, never in the return value (a fixed reason word, nothing else).
 *
 * `createAccount` is the second place the saved job-site login is typed (owner decision 2026-10-14): on a
 * known ATS host, in the TOP frame, on a page with exactly one email box and exactly two new-password boxes
 * and nothing else asked (no code box, no CAPTCHA). It types the email and the same password twice,
 * NEVER into a honeypot, ticks only a required checkbox whose own words agree to create the account or to
 * the privacy notice (a marketing opt-in is never ticked), and presses only the button whose whole label is
 * "Create Account". As `signIn`, the password is a parameter of that one call and every outcome is a fixed word.
 *
 * `applyLink` / `applyTarget` read the EMPLOYER's apply link off the posting page the user is
 * viewing (design Part 7): an absolute http(s) link to another site, never fetched, never followed.
 *
 * WHAT THIS FILE PUBLISHES: ns.pageReader = { summary, pageErrors, pageRequired, fieldWords, uploadTag, advance, signIn, createAccount, applyUrl, applyLink, applyTarget }.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  const BUTTONS = 'button, input[type="submit"], input[type="button"], a[role="button"]';
  const APPLY_TEXT = /^\s*apply( now| for this job)?\s*$/i;
  const CONFIRMATION = /thank you for (applying|your application)|application (was )?(submitted|received)|we('ve| have) received your application/i;
  // A closed notice, not a job description's prose ("…the level at which this position is filled"): the page
  // also has to hold nothing fillable and no Apply before the classifier believes it (shared/page-kind.js).
  const CLOSED = /\bthis (?:job|position|posting|requisition) (?:has been|is now|is) closed\b|(?<!\b(?:until|once|when|after|before|if|unless)\b[^.]{0,80})\bhas been filled\b|\b(?:is )?no longer (?:accepting applications|available|open)\b/i;
  // An external Apply link often says where it goes ("Apply on company site"), which APPLY_TEXT
  // alone would not match; the link reader accepts either.
  const APPLY_OFFSITE_TEXT = /^\s*apply\b[^.]{0,30}\b(company|employer)(?:'s|\u2019s)?\s+(?:web)?site\s*$/i;
  // The backend's ceiling on `apply_url` (a longer one is a 422 that would lose the whole save).
  const MAX_APPLY_URL = 2048;
  const BOARD_HOST = /(^|\.)(linkedin|indeed)\.com$/i;
  // "Create a password", "choose a password", "new password", "set your password": a sign-up box
  // with no confirmation field beside it.
  const CONFIRM_PASSWORD = /confirm|re-?enter|re-?type|repeat|verify|\b(create|choose|new|set)[ _-]?(a |your |my )?password/i;
  const ONE_TIME_CODE = /\botp\b|verification code|authentication code|passcode/i;
  // Site chrome: a "Continue" in a header or nav is the site's, never the application step's, and a
  // newsletter form in a footer is not "the form".
  const CHROME = 'header, nav, footer, [role="banner"], [role="navigation"], [role="search"], [role="contentinfo"], [role="menubar"]';
  // A footer inside the application's own content (a wizard's action bar) is not the site's.
  const CONTENT_BOX = 'main, article, section, form, dialog, [role="main"], [role="dialog"], [role="alertdialog"], [role="form"]';
  const inChrome = (el) => {
    for (let n = el.closest(CHROME); n; n = n.parentElement?.closest(CHROME)) {
      if (n.tagName !== "FOOTER" || !n.parentElement?.closest(CONTENT_BOX)) return true;
    }
    return false;
  };
  // Everything on a page a person could press as a button, for the "is there a Submit here" check
  // ONLY (what may be pressed as a Next stays BUTTONS): an ARIA button of any tag, an image input,
  // a plain link.
  const WIDE_BUTTONS = 'button, input[type="submit"], input[type="button"], input[type="image"], [role="button"], a';
  // A progress stepper lists every step by name, the last often "Submit": those are labels, not controls.
  // Only a real button inside one still counts.
  // Named so by its class: "stepper", "...-steps" or "steps-item". A plain "steps" or "nextsteps" is not a
  // stepper, and a container that holds form fields is a form, whatever it is called.
  const STEPPER = '[class*="stepper" i], [class*="-steps" i], [class*="steps-item" i], [role="progressbar"]';
  // A cookie or OneTrust notice is never the application's, whatever it holds. A dialog, an aria-modal overlay or a
  // "consent" container is a notice only while it holds no visible field: a dialog wizard step, or a consent step
  // of checkboxes, is the step itself and keeps its Next.
  const COOKIE_BOX = '[id*="cookie" i], [class*="cookie" i], [id*="onetrust" i], [class*="onetrust" i]';
  const SOFT_BOX = 'dialog, [role="dialog"], [role="alertdialog"], [aria-modal="true"], [id*="consent" i], [class*="consent" i]';
  /** The notice or dialog `el` sits in (null: in none). */
  const overlayBox = (el) => {
    const cookie = el.closest(COOKIE_BOX);
    if (cookie) return cookie;
    const box = el.closest(SOFT_BOX);
    return box !== null && ![...box.querySelectorAll(FIELD)].some((c) => shown(c)) ? box : null;
  };
  const overlayOf = (el) => overlayBox(el) !== null;
  const REAL_BUTTON = 'button, input[type="submit"], input[type="button"], input[type="image"]';
  // A dialog or step heading that asks about submitting. Narrower than the button sort on purpose:
  // "Apply to Acme" and "Complete your application" head ordinary steps.
  const SUBMIT_HEADING = /\bsubmit(ting|ted)?\b|\bsend (your|my) application\b|\bfinali[sz]e\b/i;
  const DIALOG = 'dialog[open], [role="dialog"], [role="alertdialog"], [aria-modal="true"]';
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

  /** What the control shows: its text, or an input's value (an unlabelled submit input reads "Submit"). */
  const shownTextOf = (el) => squash(el instanceof HTMLInputElement
    ? el.value || (el.type === "submit" ? "Submit" : "")
    : el.textContent);
  /** Every text a button answers to: what it shows, its accessible name, its tooltip, an image's alt. */
  const labels = (el) => {
    const named = (el.getAttribute("aria-labelledby") ?? "").split(/\s+/)
      .map((id) => el.ownerDocument.getElementById(id)?.textContent);
    return [shownTextOf(el), ...named, el.getAttribute("aria-label"), el.getAttribute("title"), el.getAttribute("alt")]
      .map(squash).filter(Boolean);
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
  // A form of hidden, display:none or parked-off-page controls (a tracking or CSRF form) is not the
  // page's: counting it would turn off the no-form path and park the real Next.
  const onPage = (el) => {
    const r = el.getBoundingClientRect();
    return r.right + window.scrollX > 0 && r.bottom + window.scrollY > 0;
  };
  const fieldForms = () => [...document.querySelectorAll(FORM)]
    .filter((f) => !inChrome(f) && [...f.querySelectorAll(FIELD)].some((c) => shown(c) && onPage(c)));

  const inFormOf = (forms) => (el) => {
    // No form holds fields: every button outside site chrome is the step's, except a dialog's or a cookie notice's.
    if (!forms.length) return !inChrome(el) && !overlayOf(el);
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

  const passwordInputs = () => [...document.querySelectorAll("input")].filter((el) => ns.fillBase.isPasswordBox(el) && shown(el));

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

  const hasCodeInput = () => [...document.querySelectorAll("input")]
    .some((el) => !ns.fillBase.isPasswordBox(el) && shown(el) && isCodeInput(el));

  const submitMarked = (el) => ns.pageKind.submitMarked(el);

  // A field's own control (see the header): a popup button (the rule `fillableControls` uses), a pill-group member,
  // or a button inside a field holder. Never an action, so never sorted as a Submit or a Next, unless its shown text
  // says Submit or Send, it is a form's submit button, or (in a holder) it is worded as a Next.
  const POPUP_BUTTON = 'button[aria-haspopup="listbox"], button[aria-haspopup="true"], '
    + '[role="button"][aria-haspopup="listbox"]:not(input), [role="button"][aria-haspopup="true"]:not(input)';
  const FIELD_HOLDER = 'fieldset, [role="group"], [data-automation-id^="formField"]';
  const PILL_MEMBER = 'button[aria-pressed], [role="button"][aria-pressed], [role="radio"]:not(input), '
    + 'ul[role="list"][aria-label] > li > button:only-child';
  // Shown words that say Submit or Send make a button an action where it is not a field's own answer: a menu-style
  // `aria-haspopup="true"` button, or a plain button in a field holder. A listbox popup (Workday's) and a pill group SHOW
  // the answer picked ("Yes, I am willing to submit to a background check", "Send me texts"), which is still the field's.
  const ACTION_WORDS = /\b(?:submit|send)\b/i;
  const ACTION_PHRASE = /^\s*(?:submit|send)(?: (?:my|your|the|this))?(?: application| form)?(?: now)?\s*$/i;
  /** Whether another `aria-pressed` button shares this one's group: its parent, or its labelled list, group or fieldset. */
  const pressedGroup = (el) => [el.parentElement, el.closest('fieldset, [role="group"], ul[role="list"][aria-label]')]
    .some((box) => box && [...box.querySelectorAll("[aria-pressed]")].some((other) => other !== el));
  function fieldControl(el) {
    // A real submit control stays one: a form's own submit button (the property, so a button with no type counts), the
    // type attribute, or a submit mark.
    if ((el.type === "submit" && el.form) || el.getAttribute("type")?.toLowerCase() === "submit" || submitMarked(el)) return false;
    if (el.matches(POPUP_BUTTON)) return !(el.getAttribute("aria-haspopup") === "true" && ACTION_WORDS.test(shownTextOf(el)));
    // A toggle in a GROUP of toggles shows an answer, whatever it says ("Send me texts"): never an action. A lone
    // toggle, one that is worded as a Next, and one that is a whole action phrase ("Submit", "Send application") are
    // not: some sites mark every button aria-pressed.
    if (el.matches("[aria-pressed]") && pressedGroup(el)) {
      const shownText = shownTextOf(el);
      if (sortOf(shownText) !== "next" && !ACTION_PHRASE.test(shownText)) return true;
    }
    if (el.matches(PILL_MEMBER)) {
      try {
        if (ns.shapes?.of(el)?.name === "pills") return true;
      } catch {
        // A shape that cannot be read says nothing.
      }
    }
    const holder = el.closest(FIELD_HOLDER);
    if (!holder) return false;
    // A <button> with no type attribute is a form's default submit; a Next of any wording is the step's; Submit or Send
    // shown on it is an action.
    if (el.type === "submit" || ACTION_WORDS.test(shownTextOf(el)) || sortOf(labelOf(el)) === "next") return false;
    // A toolbar group of buttons holds no field. A vendor's formField wrapper always does.
    return holder.matches('[data-automation-id^="formField"]')
      || [...holder.querySelectorAll(FIELD_BOX)].some((c) => c !== el && !el.contains(c));
  }

  /** A Submit anywhere a person could press one (WIDE_BUTTONS), shown, enabled or not. Beyond
   * BUTTONS, site chrome is the site's, and a long block of text in a link is not a button label. */
  const submitSeen = (regions) => [...document.querySelectorAll(WIDE_BUTTONS)].some((el) => {
    if (!shown(el)) return false;
    // A label that sorts as a Submit first (the cheap test): only then are the exemptions asked.
    if (!(submitMarked(el) || labels(el).some((text) => sortOf(text) === "submit"))) return false;
    if (errorLineButton(el, regions) || fieldControl(el)) return false;
    if (!el.matches(REAL_BUTTON) && isStepperLabel(el)) return false;
    const extra = !el.matches(BUTTONS);
    return !(extra && (inChrome(el) || shownTextOf(el).length > MAX_TEXT));
  });

  /** Inside a progress stepper that holds no form field: a step's name, not a control. */
  const isStepperLabel = (el) => {
    const holder = el.closest(STEPPER);
    return holder !== null && !holder.querySelector(FIELD);
  };

  /** The step's first visible h1/h2 text, outside site chrome. */
  let activeRegions = null;   // the error regions of the summary being built, so its headings are read against one set
  const stepHeading = () => {
    // An error summary's own heading ("Please correct the errors below") is not the step's.
    const regions = activeRegions ?? errorRegions();
    const heading = [...document.querySelectorAll("h1, h2")].find((el) => shown(el) && !inChrome(el)
      && squash(el.textContent) && !ERROR_HEADING.test(squash(el.textContent)) && !inErrorRegion(el, regions));
    return heading ? squash(heading.textContent) : "";
  };

  /** True when a visible dialog, or the step's own heading, asks about submitting ("Submit your
   * application?", "Are you sure you want to apply?", "Review and submit"): then its Proceed or
   * Continue is the Submit's. A boolean; the words never leave the page.
   *
   * A DIALOG is judged by the full button sort (any Submit word: apply, send, finish...): a dialog
   * that names its title that way is asking, and the cost of a wrong guess is a stopped run. Its
   * body text counts too (the full sort when it asks a question, the narrow words when it
   * states). The page's own STEP HEADING keeps the narrow SUBMIT_HEADING, since "Apply to Acme" and "Complete your profile" head ordinary steps. */
  const DIALOG_TEXT = 2000;   // a long preamble ends in the question: the whole text is read, not its first lines
  const dialogAsks = (d) => {
    const body = squash((d.textContent ?? "").slice(0, DIALOG_TEXT));
    const named = [
      d.getAttribute("aria-label"), d.getAttribute("title"),
      ...(d.getAttribute("aria-labelledby") ?? "").split(/\s+/).map((id) => d.ownerDocument.getElementById(id)?.textContent),
      ...[...d.querySelectorAll("h1, h2, h3, h4, [role='heading']")].map((h) => h.textContent),
    ].map(squash);
    // The body: a question gets the full sort ("Ready to send?"); a statement only the narrow
    // words ("Your application will be submitted."), so a cookie notice's "confirm" does not park.
    return named.some((text) => text && sortOf(text) === "submit")
      || (body.includes("?") ? sortOf(body) === "submit" : SUBMIT_HEADING.test(body));
  };
  const submitContext = () => [...document.querySelectorAll(DIALOG)].filter(shown).some(dialogAsks)
    || SUBMIT_HEADING.test(stepHeading());


  // ---------- the page's own complaints ----------

  // A heading that says the page has errors (never a line about one field).
  const ERROR_HEADING = /errors? found|please (fix|correct)|there (is|are) \d+ errors?/i;
  const ERRORISH = /error|required|must|invalid|please (fix|correct|enter|select|provide|choose)|can(?:no|['’])t|unable/i;
  const ERROR_LEAD = /^\s*errors?\s*[-:–—]\s*/i;
  // How a line names its field: "The field X is required…", "X: This field is required", "X is
  // required", "X can't be blank". The name is group 1.
  const LINE_NAMES = [
    /^the field\s+(.+?)\s+is required\b.*$/i,
    /^(.+?)\s*:\s*this field is required\b.*$/i,
    /^(.+?)\s+(?:is|are)\s+required\b.*$/i,
    /^(.+?)\s+(?:can(?:['’]t|not)|must not)\s+be\s+(?:blank|empty)\b.*$/i,
  ];
  // A standing hint, not a complaint: "Fields marked * are required", "All questions are required".
  const HINT_NAME = /^(?:all\s+)?(?:required\s+)?(?:fields?|questions?|items?)\b|\bmarked\b|\*\s*$/i;
  const REGION_ITEMS = 'li, a[href], button, [role="button"], [role="link"], [role="listitem"]';
  const LIVE = '[role="alert"], [aria-live]:not([aria-live="off"])';
  const CONTROLS = 'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"])'
    + ':not([type="image"]), select, textarea, [role="combobox"]';
  // What the run says when the page's own words might carry something of the user's.
  const UNNAMED = "Something the page names";
  const FILE_NAME = /[\w-]+\.(?:pdf|docx?|png|jpe?g|gif|txt|rtf|odt|pages|zip|csv|xlsx?)\b/i;
  const QUOTED = /["“”]|(?:^|\s)['‘][^'’]+['’](?:\s|$)/;

  const normal = (text) => squash(text).replace(/\*/g, "").replace(/[\s.:]+$/, "").toLowerCase();
  const keyOf = (text) => {
    let hash = 0x811c9dc5;
    for (const ch of normal(text)) hash = Math.imul(hash ^ ch.charCodeAt(0), 0x01000193) >>> 0;
    return hash.toString(36);
  };

  /** What field an error line names, or null when the text is not an error line at all: a lead
   * ("Error - X", "Error: X") or one of LINE_NAMES. Headings and standing hints are not lines. */
  function errorLineOf(raw) {
    const text = squash(raw);
    if (!text || ERROR_HEADING.test(text)) return null;
    const lead = ERROR_LEAD.test(text);
    const bare = text.replace(ERROR_LEAD, "");
    let name = lead ? bare : null;
    for (const pattern of LINE_NAMES) {
      const m = pattern.exec(bare);
      if (m) {
        name = m[1];
        break;
      }
    }
    if (!name || HINT_NAME.test(name)) return null;
    return { name: name.replace(/[\s.:]+$/, "").slice(0, MAX_TEXT * 2) };
  }
  /** Whether a button's own text reads as one of the error summary's lines or its heading. */
  const isErrorText = (text) => ERROR_HEADING.test(squash(text)) || errorLineOf(text) !== null;

  const byId = (id) => (id ? document.getElementById(id) : null);
  const isFileInput = (el) => el instanceof HTMLInputElement && el.type === "file";
  const upTags = new WeakMap();
  /** An upload box's handle: set once and kept, so the one `page_errors` names stays valid until the page redraws it. */
  const upTagOf = (input) => {
    if (!upTags.has(input)) {
      const id = `${FRAME_TAG}-u${++seq}`;
      input.setAttribute("data-maestro-up", id);
      upTags.set(input, id);
    }
    return upTags.get(input);
  };

  /** The error summaries on the page: a visible alert or live region that reads like an error, or
   * the nearest block around a short element headed "Errors Found" and the like. A region that holds
   * a field is the step around it, not a summary, and a block around a heading that also holds a
   * button which is no error line (a Submit under "Please correct any errors before submitting") is
   * not a summary either. */
  function errorRegions() {
    const regions = new Set();
    const hasField = (el) => el.querySelector(CONTROLS) !== null;
    const onlyErrorButtons = (el) => [...el.querySelectorAll(BUTTONS)].every((b) => isErrorText(labelOf(b)));
    for (const el of document.querySelectorAll(LIVE)) {
      if (ERRORISH.test(el.textContent ?? "") && shown(el) && !hasField(el)) regions.add(el);
    }
    for (const el of document.querySelectorAll("body *")) {
      if (el.childElementCount > 1) continue;
      const own = squash(el.textContent);
      if (own.length > 60 || !ERROR_HEADING.test(own) || !shown(el)) continue;
      // The nearest block around the heading that holds more than the heading: the summary.
      let region = el.parentElement;
      for (let level = 0; level < 3 && region; level += 1, region = region.parentElement) {
        if (region === document.body || region.tagName === "FORM" || hasField(region)) break;
        if (squash(region.textContent).length > own.length + 8) {
          if (onlyErrorButtons(region)) regions.add(region);
          break;
        }
      }
    }
    // Outermost only: an alert inside the banner is the banner's.
    return [...regions].filter((r) => ![...regions].some((o) => o !== r && o.contains(r)));
  }

  /** The boxes an upload's own complaint may live in: climb from the input while the ancestor holds no
   * other field, never beyond (a fieldset around City and the upload is City's). */
  function uploadBox(input) {
    const boxes = [];
    for (let n = input.parentElement; n && n !== document.body && n.tagName !== "FORM"; n = n.parentElement) {
      if (n.querySelectorAll(CONTROLS).length > 1) break;
      boxes.push(n);
    }
    return boxes;
  }
  /** Whether an upload box carries the page's complaint: the field reader's own test (its error
   * node, its described-by), or aria-invalid on the input or on the uploader around it alone. */
  const uploadInvalid = (input) => input.getAttribute("aria-invalid") === "true"
    || uploadBox(input).some((n) => n.getAttribute("aria-invalid") === "true") || ns.fillBase.invalid(input);

  const boxShown = (el) => shown(el) || (isFileInput(el) && Boolean(el.parentElement) && shown(el.parentElement));
  /** The page's own words for a control's question, else "". */
  const questionOf = (el) => {
    let question = "";
    try {
      question = squash(ns.readField(el).question);
    } catch {
      question = "";
    }
    if (!question) {
      const named = (el.getAttribute("aria-labelledby") ?? "").split(/\s+/).map((id) => byId(id)?.textContent);
      question = squash([el.getAttribute("aria-label"), ...named].find((t) => squash(t)) ?? "");
    }
    return squash(question).replace(ERROR_LEAD, "").replace(/[\s.:]+$/, "").slice(0, MAX_TEXT * 2);
  };

  /** Every value the page holds right now, lower-cased and at least three characters: text typed in a
   * control and the pills a multi-select shows. An error line that echoes one is the user's. */
  function heldValues() {
    const out = new Set();
    for (const el of document.querySelectorAll("input, textarea, select")) {
      if (isFileInput(el) || ns.fillBase.isPasswordBox(el) || /^(hidden|checkbox|radio|submit|button)$/.test(el.type ?? "")) continue;
      const v = squash(el.value).toLowerCase();
      if (v.length >= 3) out.add(v);
    }
    for (const el of document.querySelectorAll('[data-automation-id="promptOption"], [data-automation-id="selectedItem"]')) {
      const v = squash(el.textContent).toLowerCase();
      if (v.length >= 3 && v.length <= 80) out.add(v);
    }
    return out;
  }

  /** The handle a later op can find `el` by, or null: a fill field's fid (resolving it can re-list the
   * inventory, so the count-only read never asks), or an upload box's tag. */
  function handleOf(el, withTargets) {
    if (isFileInput(el)) return { kind: "upload", target: withTargets ? upTagOf(el) : null };
    return { kind: "field", target: withTargets ? ns.fillInventory?.fidFor(el) ?? null : null };
  }

  /** The control a summary item points at: the target of its link (`href="#id"`), `aria-controls`, or
   * the `for` of a label it holds; the control itself or the first one inside the element named. */
  function linkedControl(item) {
    const link = item.matches("a[href]") ? item : item.querySelector("a[href]");
    const ids = [
      (link?.getAttribute("href") ?? "").startsWith("#") ? link.getAttribute("href").slice(1) : "",
      ...[item, ...item.querySelectorAll("[aria-controls]")].flatMap((n) => (n.getAttribute("aria-controls") ?? "").split(/\s+/)),
      item.querySelector("label[for]")?.getAttribute("for") ?? "",
    ].filter(Boolean);
    for (const id of ids) {
      const hit = byId(id);
      if (!hit) continue;
      if (hit.matches(CONTROLS)) return hit;
      const inside = hit.querySelector(CONTROLS);
      if (inside) return inside;
    }
    return null;
  }

  /** The words a run may say of a field, or UNNAMED when they could carry something of the user's (a
   * file name, an address, a quoted string, a value the page holds). Held values are read once, lazily. */
  function labeller() {
    let held = null;
    return (name) => {
      held ??= heldValues();
      const low = name.toLowerCase();
      if (!name || FILE_NAME.test(name) || name.includes("@") || QUOTED.test(name)
        || [...held].some((value) => low.includes(value))) return UNNAMED;
      return name;
    };
  }

  // A button or link of an error line that is the line's own "Error - <what>" lead.
  const LEAD_ITEM = 'button, a[href], [role="button"], [role="link"]';
  const SENTENCE_NAME = LINE_NAMES[0];   // "The field X is required ..."

  /** One error line, read as ONE line: `{name, control, sentence}` or null when it is no error line. The name comes from
   * the line's own "Error - <what>" button or link when it holds one (its linked control is the field), else from the
   * first non-empty line of its text, never from the text of the whole item run together. `sentence` is the X in a
   * "The field X is required" sentence of the same item, a second name for the same field. */
  function lineParts(line) {
    const lead = [...line.querySelectorAll(LEAD_ITEM)].find((n) => ERROR_LEAD.test(squash(n.textContent)));
    const rows = String(line.innerText ?? line.textContent ?? "").split(/\n+/).map(squash).filter(Boolean);
    const sentence = rows.map((row) => SENTENCE_NAME.exec(row)?.[1]).find(Boolean) ?? "";
    const clip = (name) => name.replace(/[\s.:]+$/, "").slice(0, MAX_TEXT * 2);
    const own = lead ? errorLineOf(lead.textContent) : rows.map((row) => errorLineOf(row)).find(Boolean) ?? null;
    if (!own) return null;
    return { name: own.name, control: lead ? linkedControl(lead) : linkedControl(line), sentence: clip(sentence) };
  }

  /** What the page complains about: `{count, items: [{label, target, kind}], keys}`, one item per field
   * (the summary's line and the field's own mark are one error). A mapped item is worded by the field's
   * own question, never by the error line; an unmapped one by its line's field name, and a name that
   * could carry something of the user's (a file name, an address, a quoted string, a value the page
   * holds) is UNNAMED. `withTargets` false is the cheap read `summary()` makes: no handle, which would
   * re-list the fill inventory. `keys` are hashes of the labels: which errors, never what. */
  function collectErrors(withTargets, regions = errorRegions()) {
    const controls = [...document.querySelectorAll(`${CONTROLS}, input[type="file"], ${POPUP_BUTTON}`)].filter(boxShown);
    const isInvalid = (el) => (isFileInput(el) ? uploadInvalid(el) : ns.fillBase.invalid(el));
    const questions = new Map();   // read lazily: only a control a line may name, or an invalid one
    const questionFor = (el) => {
      if (!questions.has(el)) questions.set(el, questionOf(el));
      return questions.get(el);
    };
    const safe = labeller();

    const items = [];
    const claimed = new Set();
    const add = (name, el) => {
      if (el) {
        if (claimed.has(el)) return;
        claimed.add(el);
        items.push({ label: safe(questionFor(el) || name), ...handleOf(el, withTargets), el });
      } else if (!items.some((one) => !one.el && normal(one.label) === normal(safe(name)))) {
        items.push({ label: safe(name), kind: "unknown", target: null, el: null });
      }
    };

    // The control a name points at: a control whose question is exactly the name, or the one invalid control of those.
    // Both are the same 160-character clip, so a long question still matches.
    const mapName = (name) => {
      const wanted = normal(name);
      if (!wanted) return null;
      const same = controls.filter((c) => normal(questionFor(c)) === wanted);
      const bad = same.filter(isInvalid);
      return same.length === 1 ? same[0] : bad.length === 1 ? bad[0] : null;
    };
    for (const region of regions) {
      const all = [...region.querySelectorAll(REGION_ITEMS)].filter((n) => squash(n.textContent) && shown(n));
      for (const line of all.filter((n) => !all.some((o) => o !== n && o.contains(n)))) {
        const parts = lineParts(line);
        if (!parts) continue;
        const el = parts.control ?? mapName(parts.name) ?? mapName(parts.sentence) ?? linkedControl(line);
        add(parts.name, el);
      }
    }
    for (const el of controls) {
      if (!claimed.has(el) && isInvalid(el)) add(questionFor(el) || "Field", el);
    }
    // A line that names no field the page has, but whose words sit inside a mapped item's label (or the
    // other way round), is the same error said twice.
    const mapped = items.filter((one) => one.el).map((one) => normal(one.label));
    const kept = items.filter((one) => one.el || !mapped.some((m) => m && (normal(one.label).includes(m) || m.includes(normal(one.label)))));
    return { count: kept.length, items: kept.map(({ el, ...item }) => item), keys: kept.map((one) => keyOf(one.label)) };
  }

  const pageErrors = () => {
    const { count, items } = collectErrors(true);
    return { count, items };
  };

  // ---------- what the page needs and does not hold yet ----------
  //
  // A required control that is still empty. "Required" is read from the page itself, whatever the field
  // reader makes of the label: the `required` attribute, `aria-required`, the field reader's own verdict,
  // or a star (or the word) in the text just before the control's own wrapper. "Empty" is what the control
  // shows: no text, a select on its placeholder, a radio or checkbox group with nothing chosen, an upload
  // with no file. Words and handles only, never a value.

  const STAR = "*\u2731\u2217\uFF0A\uFE61\u204E";
  const STAR_MARK = new RegExp(`(?:^|[^\\p{L}\\p{N}])[${STAR}]|[${STAR}](?:$|[^\\p{L}\\p{N}])`, "u");
  const STAR_CHARS = new RegExp(`[${STAR}]+`, "gu");
  const REQUIRED_WORD = /\(\s*required\s*\)|[-\u2013\u2014|,:]\s*required\s*:?\s*$|(?:^|\s)required\s*:?\s*$/i;
  // A standing hint ("Fields marked * are required"), not a mark on the box that follows it.
  const HINTY = /\b(?:marked|denotes?|indicates?|indicated)\b|^\s*(?:all\s+)?(?:fields?|questions?|items?)\b[^?]*\brequired\b/i;
  const NOT_A_LABEL = '[role="alert"], [aria-live]:not([aria-live="off"]), [class*="error" i], script, style, template';
  const HEADINGS = "h1, h2, h3, h4, h5, h6, [role='heading']";
  // A pill group (buttons that hold `aria-pressed`, ARIA radios that are not inputs, or the buttons of a
  // labelled list of button-only items that carry no ARIA state at all) is a field only when the shape
  // reader says it is a GROUP with a question (`pills`): a lone toggle, a toolbar or a list of files with
  // Remove buttons is not one.
  const PILL_BOX = 'button[aria-pressed], [role="button"][aria-pressed], [role="radio"]:not(input), '
    + 'ul[role="list"][aria-label] > li > button:only-child';
  const FIELD_BOX = `${CONTROLS}, input[type="file"], button[aria-haspopup="listbox"], button[aria-haspopup="true"], ${PILL_BOX}`;
  const MAX_REQUIRED_LABEL = 200;
  const MAX_CLIMB = 6;
  const REMOVE_WORD = /\b(?:remove|delete|replace)\b/i;

  /** Whether a label's text says "required": a star, or the word set off or trailing. */
  const marksRequired = (raw) => {
    const text = squash(raw);
    if (!text || text.length > 400 || HINTY.test(text) || errorLineOf(text) !== null) return false;
    return STAR_MARK.test(text) || (!text.endsWith("?") && REQUIRED_WORD.test(text));
  };

  const edgeOf = (n) => !n || n === document.body || n === document.documentElement || n.tagName === "FORM";
  // A react-select style dummy: an invisible, unfocusable input kept only for form validation.
  const dummyBox = (c) => c.tabIndex === -1 && !isFileInput(c) && getComputedStyle(c).opacity === "0";

  /** The words just before a control's own wrapper, and whether they mark it required. Climb from the
   * control while the parent holds no other field; at each level the nearest earlier sibling with text is
   * the label. It is not a label when a heading or another field comes first. `scan` (an upload's hidden
   * input, which sits inside a dropzone full of its own prompts) keeps looking past text that marks
   * nothing, outward. `{required: false}` when nothing there names the control. */
  function labelBefore(own, { scan = false } = {}) {
    const mine = (c) => own.some((o) => o === c || o.contains(c) || c.contains(o));
    const foreign = (n) => (n.matches(FIELD_BOX) ? [n] : [...n.querySelectorAll(FIELD_BOX)])
      .some((c) => !mine(c) && boxShown(c) && !dummyBox(c));
    for (let node = own[0], depth = 0; node && depth < MAX_CLIMB && !edgeOf(node); depth += 1, node = node.parentElement) {
      for (let sib = node.previousElementSibling; sib; sib = sib.previousElementSibling) {
        if (sib.matches(NOT_A_LABEL) || !shown(sib)) continue;
        if (sib.matches(HEADINGS) || sib.querySelector(HEADINGS) || foreign(sib)) return { required: false, text: "" };
        const text = squash(sib.innerText ?? sib.textContent);
        if (!text) continue;
        if (marksRequired(text)) return { required: true, text };
        if (!scan) return { required: false, text };
      }
      if (edgeOf(node.parentElement) || foreign(node.parentElement)) break;
    }
    return { required: false, text: "" };
  }

  /** Whether the control's own labels say it is required, without the field reader's walk (the count
   * `summary()` takes on every poll stays cheap): a label for it, its aria name, its fieldset's legend. */
  function namedRequired(el) {
    const named = (el.getAttribute("aria-labelledby") ?? "").split(/\s+/).map((id) => byId(id)?.textContent);
    const legend = el.closest("fieldset")?.querySelector(":scope > legend")?.textContent;
    // A popup's aria name ends "<value> Required" (Workday), whatever the question before it says.
    const aria = el.getAttribute("aria-label") ?? "";
    return /\brequired\s*$/i.test(aria) || [...(el.labels ?? [])].some((l) => marksRequired(l.innerText ?? l.textContent))
      || [aria, ...named, legend].some((t) => marksRequired(t));
  }

  const uploadKind = (input) => {
    try {
      return ns.uploadKindOf?.(input) ?? null;
    } catch {
      return null;
    }
  };
  /** A button within a few levels of a file input: part of that uploader, not a field of its own. */
  const insideUploadBox = (button) => {
    let n = button.parentElement;
    for (let depth = 0; n && depth < 4 && !edgeOf(n); depth += 1, n = n.parentElement) {
      if (n.querySelector('input[type="file"]')) return true;
    }
    return false;
  };
  /** A pill group's own verdict: the shape reads the label's required class (a CSS-only star) as well. */
  const pillsRequired = (shape, el) => {
    if (shape?.name !== "pills") return false;
    try {
      return Boolean(shape.describe(el)?.required);
    } catch {
      return false;
    }
  };
  const isChoiceBox = (el) => el instanceof HTMLInputElement && (el.type === "radio" || el.type === "checkbox");
  // Custom radios and checkboxes hide the input and show a label (the inventory's own rule).
  const choiceShown = (el) => shown(el) || [...(el.labels ?? []), el.closest("label"), el.parentElement].some((n) => n && shown(n));
  const hasPopupShape = (shape) => shape?.name === "popup";

  /** Whether an upload box shows a file: the input holds one, or its uploader draws a row naming it (a
   * file name, or a remove or replace control), the way Workday's does while its input reads empty. */
  function fileHeld(input) {
    if ((input.files?.length ?? 0) > 0) return true;
    const box = uploadBox(input).slice(0, 4).at(-1) ?? input.parentElement;
    if (!box) return false;
    if (FILE_NAME.test(box.innerText ?? "")) return true;
    return [...box.querySelectorAll('button, [role="button"]')]
      .some((c) => REMOVE_WORD.test(`${c.textContent} ${c.getAttribute("aria-label") ?? ""}`));
  }

  /** The required, still-empty items of the page: `{count, items: [{label, target, kind}], keys}`, one
   * item per field (a radio group or a split date is one). `withTargets` false is the cheap read
   * `summary()` makes, as for `collectErrors`. */
  function collectRequired(withTargets) {
    const safe = labeller();
    const seen = new Set();
    const items = [];
    for (const el of document.querySelectorAll(FIELD_BOX)) {
      let shape = null;
      try {
        shape = ns.shapes?.of(el) ?? null;
      } catch {
        shape = null;
      }
      const file = isFileInput(el);
      if (el.matches(PILL_BOX) && shape?.name !== "pills") continue;   // a toggle, a toolbar: not an answer
      const box = file ? uploadKind(el) : null;
      if (box === "parser") continue;   // the site's import-from-resume box: never owed a file
      if (el instanceof HTMLButtonElement && shape?.name !== "pills" && insideUploadBox(el)) continue;   // an uploader's own menu is not a question
      if (el.disabled || (el.readOnly && !hasPopupShape(shape)) || ns.fillBase.isPasswordBox(el) || inChrome(el)
        || el.closest('[role="listbox"], [role="menu"], [aria-hidden="true"]')) continue;
      if (!(isChoiceBox(el) ? choiceShown(el) : boxShown(el)) || (!file && dummyBox(el))) continue;
      let key = el;
      let own = [el];
      try {
        key = shape?.groupKey?.(el) ?? el;
        own = shape?.parts?.(el) ?? [el];
      } catch {
        key = el;
        own = [el];
      }
      if (seen.has(key)) continue;
      seen.add(key);

      let empty = false;
      try {
        if (file) empty = !fileHeld(el);
        else if (shape?.name === "group") empty = !own.some((m) => m.checked);
        else {
          const got = shape ? shape.read(el) : el.value;
          empty = Array.isArray(got) ? got.length === 0 : !squash(got) || Boolean(ns.isPlaceholderText?.(squash(got)));
        }
      } catch {
        empty = false;   // unreadable: it cannot be said to be empty
      }
      if (!empty) continue;

      const flagged = own.some((c) => c.required === true || c.getAttribute("aria-required") === "true")
        || el.closest('[role="radiogroup"][aria-required="true"], [role="group"][aria-required="true"]') !== null;
      let said = null;
      const before = () => (said ??= labelBefore(own, { scan: file }));
      let isRequired = flagged || own.some(namedRequired) || pillsRequired(shape, el);
      // The field reader's own verdict costs a walk of the page around the control: only the read that
      // names items (`withTargets`) asks it, never the count `summary()` polls.
      if (!isRequired && withTargets) {
        try {
          isRequired = Boolean(ns.readField(el).required);
        } catch {
          isRequired = false;
        }
      }
      if (!isRequired) isRequired = before().required;
      if (!isRequired) continue;

      const heard = squash(questionOf(el)) || squash(before().text.replace(STAR_CHARS, " ")).replace(/[\s.:]+$/, "");
      const label = safe(heard.slice(0, MAX_REQUIRED_LABEL) || (file ? "Upload" : "Field"));
      // An upload says what kind of box it is, so the run never puts the resume in a cover letter's.
      items.push({ label, ...handleOf(own[0], withTargets), ...(file ? { box: box ?? "unknown" } : {}) });
    }
    return { count: items.length, items, keys: items.map((one) => keyOf(one.label)) };
  }

  const pageRequired = () => {
    const { count, items } = collectRequired(true);
    return { count, items };
  };
  const inErrorRegion = (el, regions) => regions.some((r) => r.contains(el));
  /** A button that is only a line of the error summary ("Error - <what>"): it counts as neither a Next nor a
   * Submit, whatever its words. Not one the page itself marks as a submit, and not one without the lead. */
  const errorLineButton = (el, regions) => inErrorRegion(el, regions) && ERROR_LEAD.test(labelOf(el)) && !submitMarked(el);

  const tag = (el) => {
    const id = `${FRAME_TAG}-${++seq}`;
    el.setAttribute("data-maestro-btn", id);
    return id;
  };

  // "Apply for Staff Engineer" in an aria-label is fine beside a visible "Apply"; "Apply and submit
  // my application" is not (its remainder is a Submit).
  const applyDetail = (text) => {
    const m = /^\s*apply\s+(?:for|to|at|on)\s+(.+)$/i.exec(text);
    return Boolean(m) && sortOf(m[1]) !== "submit";
  };
  const isApply = (el) => APPLY_TEXT.test(shownTextOf(el))
    && labels(el).every((t) => APPLY_TEXT.test(t) || applyDetail(t));

  // Only a real navigation link: an <a href> that goes to an http(s) page in THIS tab. Never a
  // <button>, even one with no form: a form-less button is page script, and script can submit
  // (owner, batch-4 review). The scheme is the PARSED one (`el.protocol`): a raw-text test is beaten by "java&#10;script:", which the
  // parser reads as javascript:. A target other than "" or "_self" (any case, a named window, or a
  // <base target>) opens a tab the run cannot follow. The one exception is the posting's own Apply
  // (`blank: true`): a career site that asks for a NEW TAB is pressed all the same, because the press
  // navigates THIS tab to the checked address and opens nothing; it must go to the page's own site or to
  // a known applicant system (shared/ats-hosts.js), so a new-tab request never carries the run anywhere else.
  const applyPressable = (el, { blank = false } = {}) => {
    if (el.tagName !== "A") return false;
    const href = (el.getAttribute("href") ?? "").trim();
    const target = (el.getAttribute("target") ?? document.querySelector("base[target]")?.getAttribute("target") ?? "").trim().toLowerCase();
    if (href === "" || href.startsWith("#") || !/^https?:$/.test(el.protocol)) return false;
    if (target === "" || target === "_self") return true;
    return blank && target === "_blank"
      && (withoutWww(el.hostname) === withoutWww(location.hostname) || ns.atsHosts.isKnown(el.hostname));
  };

  // The chooser's one allowed link (see the header): the row in shared/ats-buttons.js, a plain same-tab http(s) link
  // on THIS host, every label saying Apply Manually, not marked as a submit, shown and enabled.
  const chooserLink = (el) => el.tagName === "A" && shown(el) && enabled(el) && applyPressable(el) && !submitMarked(el)
    && labels(el).every((t) => /^apply manually$/i.test(t))
    && el.hostname.toLowerCase() === location.hostname.toLowerCase()
    && ns.atsButtons.isChooser(location.hostname, {
      automationId: el.getAttribute("data-automation-id"), text: shownTextOf(el), path: el.pathname });
  /** The chooser page's one allowed link, or null: the page has no fillable control and exactly one link qualifies. */
  const chooserEl = () => {
    if (ns.fillableControls() > 0) return null;
    const found = [...document.querySelectorAll("a[href]")].filter(chooserLink);
    return found.length === 1 ? found[0] : null;
  };

  /** A short, stable key for the step's heading (the page's first visible h1 or h2): the same step
   * reads the same, another step differs, and the heading itself never leaves the page (the summary
   * carries no prose). It tells two wizard steps apart that share a URL and a button row. */
  function stepKey() {
    const heading = stepHeading();
    if (!heading) return "";
    let hash = 0x811c9dc5;
    for (const ch of heading.toLowerCase()) hash = Math.imul(hash ^ ch.charCodeAt(0), 0x01000193) >>> 0;
    return hash.toString(36);
  }

  /** The page, as plain data for `ns.pageKind.classify`. Re-tags every button (`data-maestro-btn`)
   * so an id from an earlier call stops naming anything. */
  function summary() {
    for (const old of document.querySelectorAll("[data-maestro-btn]")) old.removeAttribute("data-maestro-btn");
    const inForm = inFormOf(fieldForms());
    const regions = errorRegions();
    activeRegions = regions;
    const found = collectErrors(false, regions);
    const errorSummary = { errors: found.count, errorKeys: found.keys };
    const needed = collectRequired(false);
    const buttons = [...document.querySelectorAll(BUTTONS)].map((el) => {
      const id = tag(el);
      const known = knownOf(el);
      return {
        id,
        text: clip(labelOf(el)),
        inForm: inForm(el) || isNavigation(el),
        visible: shown(el),
        enabled: enabled(el),
        ...(known ? { known } : {}),
        // Site chrome (header, nav, a site footer): never the application step's Next.
        ...(inChrome(el) ? { chrome: true } : {}),
        // In a dialog or a cookie or consent notice: not the application step's Next unless a form holds it.
        ...(overlayOf(el) ? { overlay: true, ...overlayFlags(el) } : {}),
        // The error summary's own buttons ("Errors Found", "Error - <field>"): not part of the step.
        ...(inErrorRegion(el, regions) && isErrorText(labelOf(el)) ? { inErrors: true } : {}),
        ...(errorLineButton(el, regions) ? { errorLine: true } : {}),
        // A field's own control (a popup, a pill, a button in a field holder): neither a Next nor a Submit.
        ...(fieldControl(el) ? { fieldControl: true } : {}),
        // The vendor's own navigation button (Workday's footer): the step's Next when its own text says so.
        ...(isNavigation(el) ? { navigation: true } : {}),
      };
    });
    const bodyText = (document.body?.innerText ?? "").slice(0, BODY_SLICE);
    const passwords = passwordInputs();
    // The posting's plain Apply, named for the one narrow `advance(id, {apply: true})` call. A link
    // is not in `buttons`, so it is tagged here (a button keeps the id it was given above).
    const applyEl = [...document.querySelectorAll(`a[href], ${BUTTONS}`)].find((el) => shown(el) && enabled(el) && isApply(el) && applyPressable(el, { blank: true }));
    const chooserLinkEl = chooserEl();
    const out = {
      host: location.hostname,
      stepKey: stepKey(),
      applyId: applyEl ? applyEl.getAttribute("data-maestro-btn") ?? tag(applyEl) : null,
      // Where that link goes, address only (no query, no fragment): the driver judges a link that leaves this site.
      applyHref: applyEl?.tagName === "A" ? `${applyEl.origin}${applyEl.pathname}` : null,
      chooserId: chooserLinkEl ? chooserLinkEl.getAttribute("data-maestro-btn") ?? tag(chooserLinkEl) : null,
      buttons,
      passwordInputs: passwords.length,
      confirmPassword: passwords.some(isConfirmPassword),
      otpInput: hasCodeInput(),
      captchaVisible: [...document.querySelectorAll("iframe")].some(challengeFrame),
      fillable: ns.fillableControls(),
      hasApplyLink: [...document.querySelectorAll(`a[href], ${BUTTONS}`)].some((el) => shown(el) && labels(el).some((t) => APPLY_TEXT.test(t))),
      confirmationText: CONFIRMATION.test(bodyText),
      // The matched words alone (the run records them as the confirmation it saw), never the page around them.
      confirmationPhrase: CONFIRMATION.exec(bodyText)?.[0] ?? null,
      closedText: CLOSED.test(bodyText),
      boardNative: BOARD_HOST.test(location.hostname),
      submitSeen: submitSeen(regions),
      submitContext: submitContext(),
      // Workday's header holds the signed-out "Sign In" button (utilityButtonSignIn, recorded in
      // fixtures/browser/workday_chooser.html) and drops it once an account is signed in: the run reads the
      // sign-up as taken from that. Only on the vendor's host; elsewhere the key is absent.
      ...(ns.atsButtons.HOSTS.workday.test(location.hostname)
        ? { headerSignIn: [...document.querySelectorAll('[data-automation-id="utilityButtonSignIn"]')].some(shown) } : {}),
      ...errorSummary,
      // Required boxes still empty: a count and value-free keys, like the errors.
      requiredEmpty: needed.count,
      requiredKeys: needed.keys,
    };
    activeRegions = null;
    return out;
  }

  const withoutWww = (host) => String(host ?? "").toLowerCase().replace(/^www\./, "");

  const shaped = (raw) => /^https?:\/\/[^\s/?#]\S*$/i.test(raw);

  /** Which job board a host belongs to ("linkedin" for www.linkedin.com AND uk.linkedin.com), or
   * null: `boardNative`'s rule. Two hosts of the same board are one site for the apply link. */
  const boardOf = (host) => BOARD_HOST.exec(host)?.[2]?.toLowerCase() ?? null;

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
    if (!shaped(given)) return null;
    const raw = linkedinRedirectTarget(given);
    // The ceiling is on the address that would be STORED, not on the wrapper it came in.
    if (!shaped(raw) || raw.length > MAX_APPLY_URL) return null;
    try {
      const host = new URL(raw).hostname;
      const mine = location.hostname;
      // Another host of the same board (uk.linkedin.com, smartapply.indeed.com) is still the board.
      const onBoard = boardOf(host) !== null && boardOf(host) === boardOf(mine);
      return onBoard || withoutWww(host) === withoutWww(mine) ? null : raw;
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
   * an apply wording. `{clicked: true}` or `{clicked: false, why}`: "not_apply" (not that
   * control, or not plainly worded as Apply), "would_submit" (it is not a real same-tab link: a button, or a link
   * that goes nowhere or opens a new tab), "not_posting" (the page has fields: it is a form, and
   * its Apply-worded button is a Submit), "submit" (the vendor's table calls it one). */
  function pressApply(id, href = null) {
    const el = typeof id === "string" && id ? document.querySelector(`[data-maestro-btn="${CSS.escape(id)}"]`) : null;
    if (!el || !el.matches(`a[href], ${BUTTONS}`)) return { clicked: false, why: "not_apply" };
    if (ns.fillableControls() > 0) return { clicked: false, why: "not_posting" };
    if (knownOf(el) === "submit" || submitMarked(el)) return { clicked: false, why: "submit" };
    if (!shown(el) || !enabled(el) || !isApply(el)) return { clicked: false, why: "not_apply" };
    if (!applyPressable(el, { blank: true })) return { clicked: false, why: "would_submit" };
    // The driver judged THIS address (origin and path): a link the page rewrote since the read is not pressed.
    if (typeof href === "string" && `${el.origin}${el.pathname}` !== href) return { clicked: false, why: "would_submit" };
    // NAVIGATE to the address just checked; do not click. A click runs the link's handlers (an
    // onclick quick-apply, an SPA router), which are page script that can send the application.
    // `el.href` is the parsed, absolute http(s) address `applyPressable` approved.
    location.assign(el.href);
    return { clicked: true };
  }

  /** The start chooser's one link, followed on the driver's say-so and the page's own re-check: the link the last
   * `summary()` named `chooserId`, still the page's ONE allowed link, with no fillable control on the page.
   * `{clicked: true}` or `{clicked: false, why}`: "not_chooser" (not that link, a field has appeared, or it is no longer
   * plainly Apply Manually on this host), "submit" (the page marks it as a submit). NAVIGATES to the checked
   * address; never clicks, because a click runs the page's own script. */
  function pressChooser(id) {
    const el = typeof id === "string" && id ? document.querySelector(`[data-maestro-btn="${CSS.escape(id)}"]`) : null;
    if (!el || el.tagName !== "A" || chooserEl() !== el) return { clicked: false, why: "not_chooser" };
    if (submitMarked(el)) return { clicked: false, why: "submit" };
    location.assign(el.href);
    return { clicked: true };
  }

  /** What a dismiss word needs to know about the popup it is in: a cookie notice (a refusal there is a dismissal), and
   * whether it is more than an acknowledgement (`overlayAsks`: its text holds a "?" or sorts as a Submit under the full
   * sort, or it has a button besides the close words). An OK there answers something; only a lone OK on a plain
   * notice ("Your progress was saved.") closes it. */
  const overlayFlags = (el) => {
    const box = overlayBox(el);
    const text = box ? squash((box.textContent ?? "").slice(0, DIALOG_TEXT)) : "";
    const others = box ? [...box.querySelectorAll(BUTTONS)].filter((b) => b !== el && shown(b)
      && !ns.pageKind.isDismiss(labelOf(b), { asks: true })) : [];
    return {
      ...(el.closest(COOKIE_BOX) ? { cookie: true } : {}),
      ...(box && (text.includes("?") || sortOf(text) === "submit" || others.length) ? { overlayAsks: true } : {}),
    };
  };

  /** A link that goes to a submit address is a Submit whatever it says. */
  const submitLink = (el) => el.tagName === "A" && /submit/i.test(el.getAttribute("href") ?? "");

  /** The reasoning step's close_dialog: the dismiss button of a popup the last `summary()` named `id`. Refused, in this
   * order: no such tagged button → "not_dismiss"; "submit" for a Submit-worded or submit-marked one, a link to a submit
   * address, one in a dialog that asks about submitting, a submit button of a form that sends something (not
   * `method="dialog"`), or ANY button while anything on the page asks about submitting (a model call takes seconds;
   * the page may have changed, and a consent bar's OK sits beside a submit dialog); then "not_dismiss" for one not
   * inside an overlay, not a dismiss word for THIS popup (`isDismiss`), hidden or disabled. Never a Next, never a Submit. */
  function pressDismiss(id) {
    const el = typeof id === "string" && id ? document.querySelector(`[data-maestro-btn="${CSS.escape(id)}"]`) : null;
    if (!el || !el.matches(BUTTONS)) return { clicked: false, why: "not_dismiss" };
    const dialog = el.closest(DIALOG);
    const sends = el.type === "submit" && el.form && (el.getAttribute("formmethod") || el.form.method).toLowerCase() !== "dialog";
    if (ns.pageKind.sortButton({ text: labelOf(el), known: knownOf(el) }) === "submit" || submitMarked(el) || submitLink(el)
      || (dialog && dialogAsks(dialog)) || sends || submitContext()) return { clicked: false, why: "submit" };
    const flags = overlayFlags(el);
    if (!overlayOf(el) || !ns.pageKind.isDismiss(labelOf(el), { cookie: flags.cookie === true, asks: flags.overlayAsks === true })
      || !shown(el) || !enabled(el)) return { clicked: false, why: "not_dismiss" };
    el.click();
    return { clicked: true };
  }

  /** Press the Next button the last `summary()` named `id`, if it is still one. Returns
   * `{clicked: true}` or `{clicked: false, why}`: "submit" (its text now carries a Submit word),
   * "not_next" (no such tagged button, or it is hidden, disabled or not worded as a Next).
   * `{apply: true}` is the posting's Apply instead (pressApply), and `{chooser: true}` the start chooser's one link
   * (pressChooser), and `{dismiss: true}` a popup's dismiss button (pressDismiss); each does only its own thing,
   * and any two together do nothing. */
  function advance(id, { apply = false, chooser = false, dismiss = false, href = null } = {}) {
    if ([apply, chooser, dismiss].filter((mode) => mode === true).length > 1) return { clicked: false, why: "not_next" };
    if (apply === true) return pressApply(id, href);
    if (chooser === true) return pressChooser(id);
    if (dismiss === true) return pressDismiss(id);
    if (typeof id !== "string" || !id) return { clicked: false, why: "not_next" };
    const el = document.querySelector(`[data-maestro-btn="${CSS.escape(id)}"]`);
    if (!el || !el.matches(BUTTONS)) return { clicked: false, why: "not_next" };
    // Re-sorted from the CURRENT labels and the table's verdict for this very button, before any
    // other check: the Submit refusal never depends on what the panel was told earlier. A Submit
    // word in the text beats the table's "next"; the table's "submit" beats a Next-worded text.
    const sort = ns.pageKind.sortButton({ text: labelOf(el), known: knownOf(el) });
    if (sort === "submit" || submitMarked(el)) return { clicked: false, why: "submit" };
    // A field's own control (a popup whose question reads like a Next) is never pressed as one.
    if (fieldControl(el)) return { clicked: false, why: "not_next" };
    if (sort !== "next" || !shown(el) || !enabled(el)) return { clicked: false, why: "not_next" };
    el.click();
    return { clicked: true };
  }

  // The email or username box of the sign-in form: by type, then by autocomplete token, then by a
  // label (or name, placeholder, aria-label) that says so. Only a text-like input that can be typed in.
  const emailBox = (scope) => {
    const boxes = [...scope.querySelectorAll("input")].filter((el) => shown(el) && enabled(el) && !el.readOnly && !ns.fillBase.isPasswordBox(el)
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
    if (hasCodeInput()) {
      return { signedIn: false, why: "verify" };
    }
    const box = passwords[0];
    if (!enabled(box) || box.readOnly) return { signedIn: false, why: "locked" };
    const scope = box.form ?? box.closest(FORM) ?? document;
    const emailEl = emailBox(scope);
    if (!emailEl) return { signedIn: false, why: "no_email" };
    // Found by wording and visibility; ENABLED is asked only at the click (below), because many
    // forms enable Sign in only once both boxes hold a value.
    const worded = (el) => el.isConnected && !inChrome(el) && shown(el)
      && SIGN_IN_BUTTON.test(labelOf(el)) && sortOf(labelOf(el)) !== "submit";
    const plain = (el) => worded(el) && enabled(el);
    const go = [...scope.querySelectorAll(BUTTONS)].find(worded);
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
    // Typing ran the page's own input handlers, which can enable, relabel or remove the button: judged again.
    if (!plain(go)) return { signedIn: false, why: "button" };
    try {
      go.click();
    } catch {
      return { signedIn: false, why: "click" };
    }
    return { signedIn: "clicked" };
  }

  // ---------- creating the account (owner decision 2026-10-14) ----------

  const CREATE_ACCOUNT_BUTTON = /^\s*create (?:an )?account\s*$/i;
  // An account checkbox that agrees to creating the account or to the privacy notice, and nothing broader.
  // "Terms of use/service" counts only in a sentence that also names the account. Anything that certifies an
  // application, consents to a check, shares or sells data, or offers alerts and marketing is refused.
  const AGREES = /\b(?:agree|accept|consent|acknowledge)\b[^.]{0,80}?\b(?:creat\w*\s+(?:this|an|my|the|a)?\s*account|creation of (?:an?|the|my) account|privacy)\b|\bterms\b[^.]{0,60}\baccount\b|\baccount\b[^.]{0,60}\bterms\b/i;
  const DENY = /\b(?:applications?|certify|certification|background|fcra|third[- ]part(?:y|ies)|shar(?:e|ed|es|ing)|sell|sold|alerts?|marketing|newsletters?|promotion\w*|offers?|e-?mail me|emails? (?:me|updates)|text me|sms|receive)\b/i;
  const ACCOUNT_BOX_MARK = /createAccountCheckbox/;
  const HONEY = /beecatcher|honey-?pot/i;

  const labelTextOf = (el) => squash([...(el.labels ?? [])].map((l) => l.textContent).join(" ")
    || el.getAttribute("aria-label") || "");
  /** A box a bot is meant to fill and a person never sees or never types in: named so by the page's words
   * or markup, or drawn off the page. Never typed into, whatever else it looks like. */
  const isHoneypot = (el) => ns.fillBase.robotTrap(el, labelTextOf(el))
    || (el.getAttribute("name") ?? "").toLowerCase() === "website"
    || [el.id, el.getAttribute("name"), el.getAttribute("data-automation-id"), el.className].some((v) => HONEY.test(String(v ?? "")));
  const isAccountEmail = (el) => el.type === "email"
    || (el.getAttribute("autocomplete") ?? "").toLowerCase().split(/\s+/).some((t) => t === "email" || t === "username")
    || [el.name, el.placeholder, el.getAttribute("aria-label"), labelTextOf(el)].some((t) => EMAIL_LABEL.test(t ?? ""));
  const newPasswordBox = (el) => el.type === "password"
    && (el.getAttribute("autocomplete") ?? "").toLowerCase().split(/\s+/).includes("new-password");

  /** The account agreement to tick, if the page asks for one: `{el}`, `null` (none asked), or `{refuse}`. A
   * REQUIRED box left unticked (its words are not the account's or the privacy notice's, or it names a
   * marketing or sharing consent) refuses too: the sign-up could not succeed, and pressing Create Account
   * over it would only burn the attempt. */
  function agreementCheckbox(scope) {
    const boxes = [...scope.querySelectorAll('input[type="checkbox"], [role="checkbox"]')].filter((el) => shown(el) || shown(el.parentElement));
    const ticked = (el) => el.checked === true || el.getAttribute("aria-checked") === "true";
    const wanted = [];
    let blocked = false;
    for (const el of boxes) {
      const words = squash([labelTextOf(el), el.getAttribute("aria-label"), el.closest("label")?.textContent].join(" "));
      const required = el.required === true || el.getAttribute("aria-required") === "true" || marksRequired(words)
        || ACCOUNT_BOX_MARK.test(el.getAttribute("data-automation-id") ?? "");
      if (!required) continue;
      if (AGREES.test(words) && !DENY.test(words)) wanted.push(el);
      else if (!ticked(el)) blocked = true;
    }
    if (blocked || wanted.length > 1) return { refuse: true };
    return wanted.length === 1 ? { el: wanted[0] } : null;
  }

  /** The one control whose whole label is "Create Account": a real button, or the overlay div a vendor lays over a
   * hidden submit (its visible face). Never one marked as a submit by the page, never a hidden one, never one in
   * site chrome, and never one with a Submit word in any label. A tenant whose only such control is the
   * aria-hidden, submit-marked button (no visible overlay) is REFUSED: the user creates that account. */
  function createAccountButton(scope) {
    const found = [...scope.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"]')]
      .filter((el) => shown(el) && !inChrome(el) && !submitMarked(el) && el.getAttribute("aria-hidden") !== "true"
        && labels(el).some((t) => CREATE_ACCOUNT_BUTTON.test(t)) && !labels(el).some((t) => sortOf(t) === "submit"));
    return found.length === 1 ? found[0] : null;
  }

  function createAccount(args) {
    try {
      return createAccountOnce(args ?? {});
    } catch {
      return { created: false, why: "error" };
    }
  }

  function createAccountOnce({ email, password, allowedHost }) {
    if (window.top !== window.self) return { created: false, why: "frame" };
    const text = (v) => typeof v === "string" && v !== "";
    if (!text(email) || !text(password) || !text(allowedHost)) return { created: false, why: "missing" };
    if (location.hostname.toLowerCase() !== allowedHost.toLowerCase()) return { created: false, why: "host" };
    if ([...document.querySelectorAll("iframe")].some(challengeFrame)) return { created: false, why: "captcha" };
    if (hasCodeInput()) return { created: false, why: "verify" };
    // Exactly the shape of a sign-up: two new-password boxes, one email box. Anything else is not asked.
    const passwords = passwordInputs();
    if (passwords.length !== 2 || !passwords.every(newPasswordBox)) return { created: false, why: "not_account_form" };
    if (!passwords.every((box) => enabled(box) && !box.readOnly)) return { created: false, why: "locked" };
    const scope = passwords[0].form ?? passwords[0].closest(FORM) ?? document;
    const emails = [...scope.querySelectorAll("input")].filter((el) => shown(el) && enabled(el) && !el.readOnly
      && !ns.fillBase.isPasswordBox(el) && !/^(hidden|checkbox|radio|file|submit|button|reset|image|search|password)$/.test(el.type)
      && !isHoneypot(el) && isAccountEmail(el));
    if (emails.length !== 1) return { created: false, why: emails.length ? "several_email" : "no_email" };
    const agreement = agreementCheckbox(scope);
    if (agreement?.refuse) return { created: false, why: "agreement" };
    const go = createAccountButton(scope);
    if (!go) return { created: false, why: "no_button" };

    const { typeText, enter, leave } = ns.fillBase;
    try {
      for (const [el, value] of [[emails[0], email], [passwords[0], password], [passwords[1], password]]) {
        enter(el);
        typeText(el, value);
        leave(el);
        if (el.value !== value) return { created: false, why: "typing" };
      }
      if (agreement?.el && !(agreement.el.checked === true || agreement.el.getAttribute("aria-checked") === "true")) {
        agreement.el.click();
        if (!(agreement.el.checked === true || agreement.el.getAttribute("aria-checked") === "true")) {
          return { created: false, why: "agreement" };
        }
      }
    } catch {
      return { created: false, why: "typing" };   // a fixed word: an error's text could carry a value
    }
    // The page's own handlers ran while typing: the button is judged again before it is pressed.
    if (!go.isConnected || !shown(go) || !enabled(go) || !labels(go).some((t) => CREATE_ACCOUNT_BUTTON.test(t))) {
      return { created: false, why: "button" };
    }
    try {
      go.click();
    } catch {
      return { created: false, why: "click" };
    }
    return { created: "clicked" };
  }

  ns.pageReader = { summary, pageErrors, pageRequired, fieldWords: questionOf, uploadTag: upTagOf, advance, signIn, createAccount, applyUrl, applyLink, applyTarget };
})();
