/* Maestro CS Companion — the floating widget.
 *
 * Tasks 10-17 of the extension-simplification plan (`git show
 * 1db5ca2:docs/plans/2026-07-27-extension-simplification-plan.md`): the
 * shell, the collapsed bubble, submit-collision avoidance, the three levels of
 * dismissal, and the expanded card.
 *
 * Five rules this file exists to keep, all from design §3.3/§4.1/§4.2, all
 * written because of a failure somebody documented:
 *
 * 1. The page must not be able to hide, restyle or reach into this UI, and this
 *    UI must not be able to break the page's. Every line of `mountShell` is
 *    that rule; none of it is decoration.
 * 2. It NEVER auto-expands. Detection changes the dot and nothing else. A
 *    competitor's auto-expanding panel is the single most-upvoted complaint in
 *    the research corpus ("covers about half of the job posting").
 * 3. It gets out of the way of the host's own submit button, and it can be
 *    dismissed AND brought back. A user pressing X on this widget in order to
 *    reach Workday's Save-and-Continue is the failure Task 12 exists for.
 * 4. ONE card, no tab bar, ONE primary button. The flow is sequential, so the
 *    old tablist becomes states of one surface (design §4.2).
 * 5. Every number on that surface is RENDERED, never recomputed. The fit score
 *    comes from the tailor response, the reconciliation counts from the fill
 *    engine's own per-field outcomes. A competitor's extension score
 *    disagreeing with its own platform score is the failure this avoids.
 *
 * The whole file is one IIFE, so it declares nothing at the top level — see the
 * publish block at the end of `content/detect.js` for why that matters while
 * cross-file scope is unverified.
 */
(() => {
  "use strict";

  // ---------- what this file needs, and what it does when it is missing ----------
  //
  // `detect.js` and `agent.js` publish onto one namespace object. Reading it by
  // name here is the whole reason those publish blocks exist: nothing in this
  // file assumes a `function` in another file is visible by its bare name.
  const ns = (window.careerStudioCompanion ??= {});

  // A previous instance of THIS FILE is already live in this isolated world.
  //
  // That happens on exactly one path, and it is a path this extension now
  // takes on purpose: the toolbar icon and the hotkey inject the content
  // scripts into a tab that has none — which, after an extension reload, is a
  // tab that has ORPHANED ones. Injection cannot tell those apart, and the old
  // instance's widget is still in the page's DOM with its own closure holding
  // its own `host`.
  //
  // Without this the user gets two bubbles: a live one and a ghost that
  // answers every click with "reload this page". Retiring the old one first is
  // the whole fix, and it is safe from here — `unmount` touches only the DOM
  // and its own state, never `chrome.*`, which is exactly the API the orphan
  // has lost.
  try {
    ns.widget?.unmount?.();
  } catch (err) {
    console.warn("[maestro-cs] the previous widget did not retire cleanly:", err);
  }

  // ---------- constants ----------

  const BUBBLE_SIZE = 44; // design §4.1: a circle, not a text pill — a rectangle is what collides.
  const EDGE_MARGIN = 16; // the "≥16px margin" of design §4.1.
  const COLLISION_GAP = 24; // "within ~24px", design §4.1.
  const DRAG_SLOP = 4; // px of movement below which a pointerdown/up pair is a click, not a drag.
  // Below the 2147483647 ceiling on purpose: a page that wants to sit on top of
  // everything usually picks the max, and this is the fallback for browsers or
  // states where the top layer is not in play. The top layer is the real answer.
  const Z_FALLBACK = 2147483000;

  // `chrome.storage.local`, read and written straight from the content script
  // (design §4.1). Dotted keys because this is one flat namespace shared with
  // whatever else the extension stores.
  const KEY = {
    dock: "widget.dock",
    hiddenOrigins: "widget.hiddenOrigins",
    hiddenGlobally: "widget.hiddenGlobally",
    session: "widget.session",
  };

  // How long a hand-picked application outlives the page that picked it.
  //
  // An ATS application is a multi-step wizard and every step is a page load, so
  // without this the pick made on step 1 is gone by step 2 — and so is the
  // `touched` flag, which is what puts the "Mark as applied" nudge on the card.
  // The user reported both as one bug, because from the outside they are one:
  // the card forgets what it was doing.
  //
  // 30 minutes rather than the "a minute or so" that was asked for: a minute
  // survives a refresh and nothing else, and the work this exists to protect —
  // filling six wizard steps — takes longer than that. It is a cache of a
  // choice, not a claim about a job, and the guards below matter more than the
  // number.
  const SESSION_TTL_MS = 30 * 60 * 1000;

  // The four states of design §4.1's dot table. Named after the fact each one
  // asserts rather than after its colour, because the colour is the encoding
  // and in forced-colors mode there is no colour left (see the sheet).
  //
  // `label` is not decoration either: it is the accessible name of the launcher
  // and the only carrier of this information for a screen reader, for a
  // colour-blind user, and in forced-colors mode.
  const DOT_STATES = {
    detected: { label: "Job page. Not in your library yet." },
    saved: { label: "In your library. Not tailored yet." },
    ready: { label: "Application ready. Autofill available." },
    draft: { label: "Filled, still a draft. Mark as applied?" },
  };
  const DEFAULT_STATE = "detected";

  // Design §4.1: bottom-right, ≥16px margin. `offset` is the gap from the
  // viewport's bottom edge to the bubble's, which is what gets persisted —
  // never an absolute y, because the next page is a different window height.
  const DEFAULT_DOCK = { side: "right", offset: EDGE_MARGIN };

  // Design §4.2: the reconciliation strip prints the first six field names and
  // hides the rest behind a disclosure.
  const FIELD_PREVIEW = 6;

  // D2. The AI answer is a distinct, explicit, per-click action and is NEVER
  // folded into the primary Autofill button. The bound is the panel's, and it
  // is a cost bound: eight questions is one model call the user is waiting on
  // inside a timed form.
  const AI_FILL_MAX = 8;

  // The one sentence for "we never got to ask the page", so the three places
  // that can hit it cannot drift into three accounts of one failure. Every
  // other message about the page — "no matching fields", "no open questions",
  // "no PDF input" — is a FINDING, and a finding may not be reported about a
  // page nobody read.
  const NO_FRAME_REACHED =
    "Can't reach this page. Reload the tab, then try again. The page script "
    + "loads with the page, so a tab that was already open when the extension "
    + "last reloaded does not have it.";

  // The OTHER half of that sentence, and the one nothing said out loud.
  //
  // NO_FRAME_REACHED is "this tab never got a page script". This is the
  // reverse: the page script is right here — it drew the card you are reading
  // — but the extension behind it has been reloaded, so its half of the bridge
  // is gone. The card keeps rendering the state it held at that moment, which
  // is what makes it convincing: real numbers, real job title, and not one
  // working button.
  //
  // It says what to do FIRST. The cause is second, because a user who has just
  // pressed a button that did nothing needs the next action, not the
  // architecture.
  const CONTEXT_LOST =
    "Reload this page to reconnect. The extension was reloaded or updated "
    + "since this page was opened, so this card is a leftover from before that "
    + "— everything on it is out of date and none of its buttons will work.";

  // Design §4.1's four selectors, verbatim. `[id*="submit" i]` is deliberately
  // loose: over-matching here costs the widget a hop to the other corner, and
  // under-matching costs the user their application.
  const SUBMIT_SELECTOR = [
    'button[type="submit"]',
    'input[type="submit"]',
    '[data-automation-id*="bottom-navigation"]',
    '[id*="submit" i]',
  ].join(", ");

  // The seven properties design §3.3 requires INLINE and `!important` on the
  // host, as data rather than as seven statements, so that
  // `test_extension_widget.py` can assert the set exists and a later refactor
  // cannot quietly drop one.
  //
  // Inline-important is the top of the author cascade: it beats a page's
  // `div { display: none !important }`, which is the rule that motivated the
  // list. The UA stylesheet for `[popover]` also sets `position: fixed` and
  // hides the element until `showPopover()` — `position` and `display` being on
  // this list is what makes the widget render either way.
  const HOST_INLINE = {
    position: "fixed",
    "z-index": String(Z_FALLBACK),
    display: "block",
    visibility: "visible",
    opacity: "1",
    // The host spans the viewport so the card and the bubble can be placed
    // anywhere in it. It must therefore be transparent to the pointer
    // everywhere except on the controls, which opt back in.
    "pointer-events": "none",
    // Not a performance tweak: it stops our layout and our counters/quotes from
    // participating in the page's.
    contain: "layout style",
  };

  // Design §3.3. UA-dispatched UI events are `composed`, so they cross the
  // shadow boundary and keep going up into the page — which is how an injected
  // widget closes a page's own dialog just by being clicked.
  const SHIELDED_EVENTS = [
    "pointerdown",
    "mousedown",
    "pointerup",
    "mouseup",
    "click",
    "touchstart",
  ];

  // ---------- styles ----------
  //
  // One constructable sheet, adopted by the shadow root. Everything except the
  // seven inline properties lives here.
  const SHEET = `
:host {
  /* Design §3.3. Nothing inherits in from the page: not font, not colour, not
     line-height. It also wipes what the UA's own [popover] rule would impose —
     border, padding, background, width: fit-content — which is why the rest of
     this block is short. It does NOT reset custom properties, so ours are
     namespaced --cs-* and a page's are simply not read. */
  all: initial;
  inset: 0;

  --cs-font: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --cs-surface: oklch(1 0 0);
  --cs-surface-2: oklch(0.97 0 0);
  --cs-text: oklch(0.145 0 0);
  --cs-muted: oklch(0.51 0 0);
  --cs-line: oklch(0.92 0 0);
  --cs-primary: oklch(0.55 0.17 259);
  --cs-on-primary: oklch(0.985 0 0);
  --cs-shadow: 0 2px 6px oklch(0.145 0 0 / 12%), 0 10px 28px oklch(0.145 0 0 / 14%);
  --cs-dot-detected: oklch(0.68 0 0);
  --cs-dot-saved: oklch(0.62 0.16 259);
  --cs-dot-ready: oklch(0.62 0.15 151);
  --cs-dot-draft: oklch(0.76 0.15 75);
  --cs-ease: cubic-bezier(0.23, 1, 0.32, 1);
}

@media (prefers-color-scheme: dark) {
  :host {
    --cs-surface: oklch(0.205 0 0);
    --cs-surface-2: oklch(0.26 0 0);
    --cs-text: oklch(0.985 0 0);
    --cs-muted: oklch(0.72 0 0);
    --cs-line: oklch(0.32 0 0);
    --cs-primary: oklch(0.62 0.16 259);
    --cs-shadow: 0 2px 6px oklch(0 0 0 / 40%), 0 10px 28px oklch(0 0 0 / 34%);
  }
}

.dock {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
  font: 500 13px/1.45 var(--cs-font);
  color: var(--cs-text);
}
.dock[data-side="left"] { align-items: flex-start; }

.bubble {
  position: relative;
  box-sizing: border-box;
  width: ${BUBBLE_SIZE}px;
  height: ${BUBBLE_SIZE}px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  color: var(--cs-on-primary);
  background: var(--cs-primary);
  box-shadow: var(--cs-shadow);
  font: 700 17px/1 var(--cs-font);
  cursor: grab;
  /* The host is pointer-transparent; the controls opt back in. */
  pointer-events: auto;
  touch-action: none; /* the drag is ours, not the page's scroller. */
  transition: transform 160ms var(--cs-ease), box-shadow 160ms var(--cs-ease);
}
.bubble:hover { transform: scale(1.04); }
.bubble:active { cursor: grabbing; transform: scale(0.97); }
.bubble:focus-visible { outline: 3px solid var(--cs-primary); outline-offset: 3px; }
.dock[data-dragging="true"] .bubble { transform: scale(1.06); }

.dot {
  position: absolute;
  right: 1px;
  bottom: 1px;
  box-sizing: border-box;
  width: 10px;
  height: 10px;
  border: 2px solid var(--cs-primary);
  border-radius: 50%;
  background: var(--cs-dot-detected);
}
.dock[data-state="saved"] .dot { background: var(--cs-dot-saved); }
.dock[data-state="ready"] .dot { background: var(--cs-dot-ready); }
.dock[data-state="draft"] .dot { background: var(--cs-dot-draft); }

.card {
  display: none;
  box-sizing: border-box;
  width: 340px;
  max-width: calc(100vw - ${EDGE_MARGIN * 2}px);
  /* Design §4.2 says ~340×480. 520 is that "~", and it was measured rather
     than picked: the header, the pinned action region and the footer take
     ~185px between them, so at 480 the reconciliation strip — the reason this
     card exists — got two visible lines. The second term still wins on a short
     window, and the strip is capped and scrolls inside itself either way. */
  max-height: min(520px, calc(100vh - ${EDGE_MARGIN * 2 + BUBBLE_SIZE + 10}px));
  flex-direction: column;
  /* The CARD does not scroll; its body does (below). The header carries the
     route into the web app and the footer carries the never-submits promise,
     and both have to stay on screen — a promise you have to scroll to find is
     not printed on the surface. */
  overflow: hidden;
  border-radius: 18px;
  background: var(--cs-surface);
  box-shadow: var(--cs-shadow);
  pointer-events: auto;
}
.dock[data-expanded="true"] .card { display: flex; }

.card-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 10px 10px 16px;
  border-bottom: 1px solid var(--cs-line);
  font-weight: 650;
}
.card-head .brand { flex: 1; min-width: 0; }
.card-body {
  flex: 1;
  /* A flex item's default min-height is auto, which refuses to shrink below
     its content — so without this the body pushes the footer off the card
     instead of scrolling. */
  min-height: 0;
  padding: 14px 16px;
  overflow: hidden auto;
}
.card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 9px 12px 11px 16px;
  border-top: 1px solid var(--cs-line);
  color: var(--cs-muted);
  font-size: 11px;
}

.text-button {
  padding: 5px 10px;
  border: 0;
  border-radius: 999px;
  color: var(--cs-muted);
  background: transparent;
  font: 600 12px/1.2 var(--cs-font);
  cursor: pointer;
}
.text-button:hover { color: var(--cs-text); background: var(--cs-surface-2); }
.text-button:focus-visible { outline: 2px solid var(--cs-primary); outline-offset: 2px; }
a.text-button { text-decoration: none; }

/* ---------- the expanded card (design §4.2) ---------- */

.stack { display: flex; flex-direction: column; gap: 9px; }
.stack-tight { display: flex; flex-direction: column; gap: 5px; }
.row-inline { display: flex; align-items: center; gap: 8px; }
.row-inline .field-label { margin: 0; white-space: nowrap; }
.muted { color: var(--cs-muted); }
.small { font-size: 11px; line-height: 1.5; }
[hidden] { display: none !important; }

/* One line, truncating: a job title is arbitrary length and this is 340px. */
.one-line {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.context-line { font-weight: 650; font-size: 13px; }
.context-sub { color: var(--cs-muted); font-size: 11px; }

.primary {
  box-sizing: border-box;
  width: 100%;
  padding: 10px 14px;
  border: 0;
  border-radius: 12px;
  color: var(--cs-on-primary);
  background: var(--cs-primary);
  font: 650 13px/1.3 var(--cs-font);
  cursor: pointer;
}
.primary:hover { filter: brightness(1.06); }
.primary:disabled { cursor: default; opacity: 0.6; }
.primary:focus-visible { outline: 3px solid var(--cs-primary); outline-offset: 2px; }

/* OUTSIDE the scrolling body, and that is a requirement rather than a layout
   preference: design §4.2 says the secondary row is always present, and the
   escape hatch lives in it. A 25-field reconciliation strip is the normal case
   on an ATS, so anything below the strip inside the body is a row the user has
   to go looking for. */
.card-sticky {
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding: 10px 16px;
  border-top: 1px solid var(--cs-line);
}

.secondary { display: flex; gap: 6px; }
/* min-width:0 is the load-bearing half: a flex item's default minimum is its
   content width, so a long job title would push the control beside it off the
   340px card instead of truncating. */
.grow { flex: 1; min-width: 0; }
.secondary .text-button { border: 1px solid var(--cs-line); }

/* The nudge. It is a prompt the card is actively making — "you filled this,
   did you send it?" — so it has to read as pressable at a glance, in the one
   region of the card that is otherwise labels and toggles. Full width and
   accent-coloured, but still not the primary button: that one carries the next
   step of the flow (Autofill again on page two of a wizard) and this must not
   compete with it.

   NO BACKTICKS IN THIS BLOCK. Every comment in it lives inside the SHEET
   template literal, so the prose convention the rest of this file uses —
   backticks around an identifier — terminates the string. That shipped once:
   the stylesheet ended early, the CSS after it parsed as JS, and the widget
   died at load with "….primary is not a function" on every page. */
.nudge-button {
  box-sizing: border-box;
  width: 100%;
  padding: 7px 12px;
  border: 1px solid var(--cs-primary) !important;
  border-radius: 999px;
  color: var(--cs-primary);
  background: transparent;
  font: 650 12px/1.3 var(--cs-font);
  text-align: center;
}
.nudge-button:hover { color: var(--cs-on-primary); background: var(--cs-primary); }

.chip-button {
  padding: 0;
  border: 0;
  color: var(--cs-primary);
  background: transparent;
  font: 600 11px/1.5 var(--cs-font);
  text-decoration: underline;
  cursor: pointer;
}
.chip-button:focus-visible { outline: 2px solid var(--cs-primary); outline-offset: 2px; }

/* The Base/Tailored switch. Two states that are mutually exclusive and both
   worth seeing at once, which is a segmented control rather than a dropdown —
   the point is that you can tell WHICH resume is armed without opening
   anything. */
.segmented {
  display: flex;
  padding: 2px;
  border: 1px solid var(--cs-line);
  border-radius: 999px;
  background: var(--cs-surface-2);
}
.segmented button {
  flex: 1;
  padding: 4px 10px;
  border: 0;
  border-radius: 999px;
  color: var(--cs-muted);
  background: transparent;
  font: 600 11px/1.5 var(--cs-font);
  cursor: pointer;
  white-space: nowrap;
}
.segmented button[aria-pressed="true"] {
  color: var(--cs-text);
  background: var(--cs-surface);
  box-shadow: 0 1px 2px rgb(0 0 0 / 0.08);
}
.segmented button:focus-visible { outline: 2px solid var(--cs-primary); outline-offset: 2px; }

select, input[type="text"], input[type="url"], textarea {
  box-sizing: border-box;
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--cs-line);
  border-radius: 8px;
  color: var(--cs-text);
  background: var(--cs-surface);
  font: 500 12px/1.4 var(--cs-font);
}
textarea { resize: vertical; min-height: 58px; }
label.toggle {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  font-size: 11px;
  line-height: 1.45;
}
label.toggle input { margin: 2px 0 0; accent-color: var(--cs-primary); }
.field-label { display: block; margin-bottom: 3px; color: var(--cs-muted); font-size: 11px; }

/* The fit number. Rendered from the tailor response's compare block, never
   recomputed — see rule 5 in this file's header. */
.fit {
  align-self: flex-start;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--cs-surface-2);
  font: 650 12px/1.4 var(--cs-font);
}

/* The reconciliation strip. No competitor ships an equivalent; this is the
   surface where the project is ahead of the category (design §4.2). */
.strip {
  padding: 9px 11px;
  border: 1px solid var(--cs-line);
  border-radius: 10px;
  background: var(--cs-surface-2);
}
.strip-counts { font: 650 12px/1.4 var(--cs-font); }
.strip ul, .list { margin: 6px 0 0; padding: 0; list-style: none; }
/* Only the NAMES scroll. A 25-field fill is the normal case on an ATS, and an
   uncapped list pushes both the counts and the "show all" disclosure out of
   view — the two things design §4.2 asks for by name. */
.strip ul { max-height: 108px; overflow: hidden auto; }
.strip li, .list li { margin-top: 4px; font-size: 11px; line-height: 1.45; }
.list li { padding-bottom: 4px; border-bottom: 1px solid var(--cs-line); }
.list b { font-weight: 650; }
.was { text-decoration: line-through; color: var(--cs-muted); }

.note { font-size: 11px; line-height: 1.5; }
.note.error { color: oklch(0.52 0.2 27); }
@media (prefers-color-scheme: dark) { .note.error { color: oklch(0.72 0.17 27); } }

.spin::after {
  content: "";
  display: inline-block;
  width: 9px;
  height: 9px;
  margin-left: 6px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: cs-spin 700ms linear infinite;
  vertical-align: -1px;
}
@keyframes cs-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spin::after { animation: none; } }

/* The "did not load" box. Its own class, NOT plain .error: renderNote toggles
   an error modifier on the note line, and a shared name gave that one line a
   320px box with a red border and a shadow of its own (seen in the browser). */
.boot-error {
  box-sizing: border-box;
  width: 320px;
  padding: 14px 16px;
  border: 2px solid oklch(0.52 0.2 27);
  border-radius: 14px;
  color: var(--cs-text);
  background: var(--cs-surface);
  box-shadow: var(--cs-shadow);
  font: 500 12px/1.5 var(--cs-font);
  pointer-events: auto;
}
.boot-error b { display: block; margin-bottom: 4px; }

/* Design §3.3: in forced-colors mode box-shadow is forced to none, so a widget
   whose only edge is a shadow disappears against the page. Every surface gets a
   real border.

   The dot loses its meaning here as well — all four colours are overridden to
   the same forced value — so the border makes it visible and the launcher's
   accessible name (set from DOT_STATES[...].label on every state change) is
   what still carries WHICH state it is. That is the same string a screen reader
   gets, so this is not a special case so much as the general one showing. */
@media (forced-colors: active) {
  .bubble, .card, .boot-error { border: 2px solid CanvasText; }
  .dot { border: 2px solid CanvasText; }
}

@media (prefers-reduced-motion: reduce) {
  .bubble, .card { transition-duration: 0.01ms !important; }
  .bubble:hover, .dock[data-dragging="true"] .bubble { transform: none; }
}
`;

  // ---------- state ----------

  let host = null;
  let root = null; // the CLOSED shadow root; unreachable except through this binding.
  let dockEl = null;
  let bubbleEl = null;
  let cardEl = null;

  let dock = { ...DEFAULT_DOCK }; // dock side + offset, never absolute x/y.
  let dotState = DEFAULT_STATE;
  let expanded = false;

  let collision = null; // {io, mo, near:Set, colliding:bool, evadeSide:string|null} while mounted
  let hotkeyLabel = null; // filled in from the service worker; see askHotkey().
  let suppressClick = false; // a drag ends in a click event that must not toggle the card.

  /** Everything the card renders. One object so that `render()` is a pure
   * function of it plus the DOM, and so the preview page can print it.
   *
   * Nothing here is derived: `resolvePrimary` derives the state and the button
   * from these facts every render, and no field below is a cached copy of that
   * answer. A second home for "which state are we in" is how a widget ends up
   * showing a green dot beside an Add-job button.
   */
  const card = {
    settings: null, // {backendUrl, appUrl, telemetryEnabled} (+ legacy eeoAutofillEnabled ignored for fill)
    // Backend-owned standing consent for deterministic EEO fill. null until
    // loaded from /api/settings/eeo-consent or /api/autofill/context.
    eeoConsent: null, // {enabled, acknowledged_at, policy_version} | null
    // Tier C (design §5): the backend's verdict about THIS url, not a score.
    // null means "not asked yet or the ask failed" — which is not "none".
    match: null,
    job: null, // {id, company, title}
    application: null, // {id, status}
    pdfReady: false, // the application has a rendered PDF (design §4.1's green)
    // Whether the PAGE holds an application form — Tier B evidence, which the
    // gate has always computed and returned beside `tier` and which nothing
    // has ever read. It is what makes "can this be filled" a question about
    // the page rather than about the library.
    hasForm: false,

    baseResumes: null, // the list, loaded on first expand
    // Every base resume's ATS score against THIS job, from the app's own
    // scoring pipeline. null = not asked yet or the ask failed; [] = asked,
    // nothing scored. The two are different and the card says so.
    baseScores: null,
    basePickedByUser: false, // once true, ranking never moves the selection
    baseSlug: "", // the base resume Fast tailor and the escape hatch both use
    applications: null, // loaded only when the user asks to change the target
    picking: false, // D4: the picker appears on "change", never by default

    compare: null, // {before, after} from the tailor response. Rendered only.
    fill: null, // the last reconciled fill result
    attached: null, // {filename, count} from the last attach
    attachedBase: null, // the base slug attached, for D3's deferred "Track this"
    touched: false, // this widget filled or attached on this page, this session
    questions: null, // the open-question queue, once scanned

    view: "main", // main | fields | questions | more — one card, never a tab
    busy: null, // the id of the action currently running
    note: null, // {text, error} — the last thing that happened
  };

  // ---------- geometry ----------
  //
  // The two functions below are `function` declarations with end markers and no
  // free variables, in the self-contained style the rest of this extension uses
  // for anything a test has to reach: `backend/tests/extension_harness.py`
  // slices them out by name and runs them in node.
  //
  // That is not stylistic. The browser half of Task 12 — does
  // IntersectionObserver deliver, does a real Workday footer match the
  // selectors — cannot be executed from a coding session, and it could not even
  // be executed against extension/dev/preview.html, because that pane's tab
  // reports `document.hidden === true` and a hidden tab is never rendered, so
  // neither IntersectionObserver nor requestAnimationFrame ever fires
  // (measured, not assumed). So the half that CAN be executed is pulled out
  // where it can be: the decision itself, as pure geometry.

  /** The saved offset, made safe for THIS window.
   *
   * Design §4.1 persists a dock side plus an offset and re-clamps on every
   * mount, because the next page loads at a different zoom and window size than
   * the one the offset was saved at. `Math.max` on the ceiling is for the
   * window shorter than the bubble plus its margins, where the ceiling would
   * otherwise fall below the floor and `Math.min` would pin the widget
   * off-screen. */
  function clampOffset(offset, viewportHeight, size, margin) {
    const ceiling = Math.max(margin, viewportHeight - size - margin);
    return Math.min(Math.max(Math.round(offset), margin), ceiling);
  }
  // ---- end clampOffset ----

  /** Which corner the bubble should be in, given where the page's submit
   * controls are. Pure: rectangles in, a decision out.
   *
   * It judges both CANDIDATE positions geometrically rather than measuring
   * where the widget currently is, and that is the whole reason it takes a dock
   * instead of a rect. A decision made from the live position oscillates: evade
   * because home is blocked, find home clear *because we are not standing in
   * it*, return, evade again — once per frame, forever. Deciding from the page
   * alone makes the answer stable.
   *
   * Hopping only when the other corner is actually better is the other half.
   * Neither corner is safe on its own — job boards put Apply top-right, ATS
   * forms put Save-and-Continue bottom-right — so a footer bar spanning the
   * full width has to report "blocked, nowhere to go", which is what makes the
   * caller collapse instead of shuffling sideways into the same problem. */
  function chooseEvasion({ dock, viewport, targets, size, margin, gap }) {
    const rectAt = (side) => {
      const bottom = viewport.height - dock.offset;
      const left = side === "right" ? viewport.width - margin - size : margin;
      return { left, right: left + size, top: bottom - size, bottom };
    };
    const hits = (rect) => targets.some((target) =>
      // A zero-area control is display:none, a collapsed wizard step, or a
      // template node. It is on the page and it is not in the way.
      target.width > 0 && target.height > 0
      && rect.left < target.right + gap && rect.right > target.left - gap
      && rect.top < target.bottom + gap && rect.bottom > target.top - gap);

    const away = dock.side === "right" ? "left" : "right";
    const homeBlocked = hits(rectAt(dock.side));
    return { homeBlocked, evadeSide: homeBlocked && !hits(rectAt(away)) ? away : null };
  }
  // ---- end chooseEvasion ----

  const clamp = (offset) =>
    clampOffset(offset, window.innerHeight, BUBBLE_SIZE, EDGE_MARGIN);

  // ---------- the two decisions the card makes (design §4.1, §4.2) ----------
  //
  // Same shape and the same reason as the geometry above: `function`
  // declarations with end markers and no free variables, so
  // `backend/tests/extension_harness.py` can slice them out and run them in
  // node. These two are the whole judgement of the expanded card — everything
  // else in it is layout — and they are the pieces most likely to drift,
  // because both are tables that a later feature edits one row of.

  /** Design §4.1's dot table and design §4.2's one primary button, together.
   *
   * They are ONE function because they are one decision made from one set of
   * facts, and splitting them is how the widget ends up showing a green dot
   * beside an Add-job button.
   *
   * Three returns, deliberately:
   *
   * `state` is the dot — four values, including `draft`, which means "you
   * filled or attached here and the application is still a draft".
   *
   * `action` is the primary button — THREE values, and `Mark as applied` is
   * not one of them. That is not an omission. A Workday application is a
   * multi-step wizard: after filling page one the user needs Autofill again on
   * page two, so replacing the primary with the applied nudge would take the
   * only button they still need. So the amber state changes the DOT and adds
   * the nudge below; the primary keeps offering the next step of the flow.
   *
   * `nudge` is design §6's prompt, and it carries WHICH prompt. With an
   * application it is the one-tap status flip; without one it is D3's deferred
   * "Track this", because the escape hatch attaches with no database write and
   * this click is the first write there is.
   *
   * `match !== "exact"` rather than `=== "none"`: null means the backend was
   * never asked or could not be reached, and an unreachable backend must not
   * claim the page is a job we have (`Add job` re-asks; a wrong `Autofill`
   * would target an application that may not exist).
   */
  function resolvePrimary({
    match, hasApplication, pdfReady, status, touched, hasForm, baseArmed,
  }) {
    const ACTIONS = {
      detected: { id: "add-job", label: "Add job" },
      saved: { id: "fast-tailor", label: "Fast tailor" },
      ready: { id: "autofill", label: "Autofill this form" },
    };
    // Filling a form is a question about the PAGE, and the flow below is a
    // question about the library. Conflating them is what left the card with
    // no way to autofill from a base resume: the primary reached `autofill`
    // only through a tracked job with a tailored PDF, so a user who had chosen
    // Base — deliberately, on the control right above it — was offered Add job
    // or Fast tailor and no way to fill the form in front of them. The escape
    // hatch could already ATTACH that resume without any of that.
    //
    // `baseArmed` is the whole gate: Base mode with a resume actually chosen.
    // It cannot fire in Tailored mode, so it never pre-empts the tailoring
    // flow, and it cannot fire on a posting with no form.
    const fillFromBase = hasForm === true && baseArmed === true && !hasApplication;
    const stage = fillFromBase ? "ready"
      : match !== "exact" ? "detected"
        : !hasApplication || !pdfReady ? "saved"
          : "ready";
    // `?? "draft"` because an application row created and never touched can
    // carry a null status, and because the escape hatch has no row at all.
    const isDraft = (status ?? "draft") === "draft";
    return {
      // The DOT still means "this widget filled or attached HERE". That is a
      // claim about this page, and only `touched` can support it.
      state: touched && isDraft ? "draft" : stage,
      action: ACTIONS[stage],
      // The nudge is NOT that claim, and gating it on `touched` was wrong.
      //
      // A targeted application that is still a draft can be marked applied at
      // any time: you picked it, it is not applied yet, and that is the whole
      // precondition. Requiring `touched` meant the control existed only on a
      // page this widget had just written to — so it was absent on the
      // submission-confirmation page, which is the one moment it is most
      // wanted, and absent again whenever a re-run found every field already
      // correct. Reported twice as "where is the applied button", both times
      // on a card that was otherwise showing the application perfectly.
      //
      // `track-this` KEEPS the `touched` requirement, because it is a
      // different sentence: it exists only after an attach that deliberately
      // wrote nothing down, and before that there is nothing to track.
      nudge: hasApplication
        ? (isDraft ? "mark-applied" : null)
        : (touched && isDraft ? "track-this" : null),
      // Whether we have grounds to PROMPT rather than merely offer. Having
      // filled this page earns "Submitted it?"; arriving cold does not.
      prompted: touched === true,
    };
  }
  // ---- end resolvePrimary ----

  /** Base resumes in the order this JOB ranks them, each carrying its score.
   *
   * The app already scores every base resume against a job — one endpoint,
   * `score_all_bases`, and the Score & Tailor tab is built on it — but the
   * card never asked, so its dropdown listed resumes in library order and the
   * user picked blind. Fast tailor then built on whatever that pick was, and
   * the one number the card showed afterwards was the score of a resume nobody
   * had reason to believe was the right one.
   *
   * Ranked here rather than server-side because the ORDER is a presentation
   * choice and the scores are not: every number below is the backend's, and
   * this function never computes one (design §4.2, "render them; compute
   * nothing new").
   *
   * Unscored resumes keep their library order and sort last — "not scored yet"
   * is not a bad score, and showing it as one would be the card inventing a
   * judgement.
   */
  function rankBaseResumes(resumes, scores) {
    const bySlug = new Map();
    for (const row of scores ?? []) {
      if (row?.target_type !== "base_resume" || row?.phase !== "base") continue;
      const composite = Number(row.composite);
      if (!Number.isFinite(composite)) continue;
      // Latest wins: `latest_scores` already returns one row per target, but a
      // caller that concatenated two reads must not produce two entries.
      if (!bySlug.has(row.target_id)) bySlug.set(row.target_id, composite);
    }
    return (resumes ?? [])
      .map((resume, index) => ({
        ...resume,
        score: bySlug.has(resume.slug) ? bySlug.get(resume.slug) : null,
        index,
      }))
      .sort((a, b) => {
        if (a.score === b.score) return a.index - b.index;
        if (a.score === null) return 1;
        if (b.score === null) return -1;
        return b.score - a.score;
      });
  }
  // ---- end rankBaseResumes ----

  /** The reconciliation strip's numbers, from the fill engine's own output.
   *
   * Design §4.2: "Render them; compute nothing new." Every value below already
   * exists — `filled[]`, `eeoFilled[]`, `corrected[]`, and one observation per
   * field carrying the commit ladder's outcome. This function buckets and
   * concatenates; it does not judge whether a field was filled.
   *
   * It takes the whole per-frame array rather than pre-flattened lists because
   * `reached` has to be decided from the same data. A frame contributes
   * `result: undefined` when it could not be reached or threw, and every
   * sentence the card prints about the page — "no matching fields" — is a lie
   * when NO frame answered. Deciding that here means a caller cannot forget it.
   *
   * Buckets are the frozen outcome vocabulary of
   * `backend/app/schemas/autofill_telemetry.py`. `no_rule` is counted
   * separately and kept OUT of "skipped": an ATS form carries dozens of
   * controls no rule claims, and folding them in would print "38 skipped"
   * beside "14 filled" — a number about the size of the form, not about what
   * we did. The `ai_*` outcomes are absent because a profile fill cannot emit
   * them; an outcome this table does not know is left out of every count
   * rather than guessed into one.
   *
   * `already` is the one count NOT built from observations, because the engine
   * deliberately emits none for a field that already held the answer (the
   * frozen vocabulary has no outcome for a write that never happened). It is
   * the length of the engine's own `already` list — still rendered, never
   * judged here.
   */
  /** May a remembered pick be restored onto THIS page load?
   *
   * Pure, and its own function for the same reason `resolvePrimary` is: it is
   * the whole judgement, and it is the piece that decides whether the card
   * shows an application the user is not looking at. Three guards, each
   * answering a different way of being wrong:
   *
   * ORIGIN. A pick belongs to the site it was made on. Stored per origin
   * rather than per URL because the URL changes on every wizard step, which is
   * exactly the case this exists for.
   *
   * FRESHNESS. An entry past its TTL is not a pick, it is a memory of one.
   * A clock that jumped backwards makes `age` negative, which is not fresh
   * either — hence the range test rather than `age < TTL`.
   *
   * THE BACKEND WINS. If `/api/jobs/match` recognised this page as a job, and
   * it is not the job the pick was made for, the pick is about a different
   * posting and is discarded. A Workday tenant serves every one of its jobs
   * from one origin, so without this the application picked for one posting
   * would be offered on the next — which is the most confident wrong thing
   * this surface could say. A match of `null`/`none` is not a contradiction:
   * it is the backend not knowing, which is the ordinary case on an apply URL,
   * and it is precisely when the remembered pick is worth having.
   */
  function restorableSession(entry, { now, origin, matchedJobId, ttlMs }) {
    if (!entry || entry.origin !== origin) return null;
    const age = now - (entry.at ?? 0);
    if (!(age >= 0 && age < ttlMs)) return null;
    if (matchedJobId && entry.jobId && matchedJobId !== entry.jobId) return null;
    return entry;
  }
  // ---- end restorableSession ----

  function reconcileFill(frames) {
    const BUCKET = {
      filled: "filled",
      filled_normalized: "filled",
      corrected: "corrected",
      not_stuck: "notStuck",
      combobox_snap_failed: "notStuck",
      policy_blocked: "skipped",
      skipped_checkbox: "skipped",
      missing_source: "skipped",
      eeo_disabled: "skipped",
      skip_rule: "skipped",
      hidden: "skipped",
      no_rule: "noRule",
    };
    const answered = frames.filter((frame) => frame.result !== undefined);
    const observations = answered.flatMap((frame) => frame.result.observations ?? []);
    const counts = { filled: 0, corrected: 0, notStuck: 0, skipped: 0, noRule: 0 };
    for (const observation of observations) {
      const bucket = BUCKET[observation.outcome];
      if (bucket) counts[bucket] += 1;
    }
    // Concatenated in frame order, which is the order the fan-out asked in.
    const already = answered.flatMap((frame) => frame.result.already ?? []);
    counts.already = already.length;
    return {
      reached: answered.length > 0,
      counts,
      observations,
      already,
      filled: answered.flatMap((frame) => frame.result.filled ?? []),
      eeoFilled: answered.flatMap((frame) => frame.result.eeoFilled ?? []),
      corrected: answered.flatMap((frame) => frame.result.corrected ?? []),
    };
  }
  // ---- end reconcileFill ----

  // ---------- storage ----------

  const STORE_DEFAULTS = {
    [KEY.dock]: null,
    [KEY.hiddenOrigins]: {},
    [KEY.hiddenGlobally]: false,
    [KEY.session]: null,
  };

  const readStore = async () => {
    try {
      return await chrome.storage.local.get(STORE_DEFAULTS);
    } catch (err) {
      // A storage read that fails must not cost the user the widget: the
      // defaults are a working widget in the default corner.
      console.warn("[maestro-cs] storage read failed:", err);
      return { ...STORE_DEFAULTS };
    }
  };

  const writeStore = (patch) =>
    chrome.storage.local.set(patch).catch((err) => {
      console.warn("[maestro-cs] storage write failed:", err);
    });

  const saveDock = () => writeStore({ [KEY.dock]: { side: dock.side, offset: dock.offset } });

  /** Remember what this card is armed with, so the next page load can pick it
   * up. Called after every change to the ARMED state — the target, the tailor
   * that produced one, the write that made this page touched.
   *
   * ONE entry, not one per origin: the user is filling one application at a
   * time, and a map would keep a pick for every ATS they ever visited until
   * something pruned it. The origin is stored IN the entry and checked on the
   * way out (`restorableSession`), so a stale entry from another site is
   * refused rather than merely unreachable.
   *
   * Deliberately NOT stored: the fill result and the reconciliation strip.
   * Those are facts about a page that no longer exists — re-showing them
   * beside a fresh form would claim a fill that is not on it. What survives is
   * the CHOICE, plus the one bit that outlives the page (`touched`, which is
   * what puts the applied nudge on the card). */
  const rememberSession = () => {
    if (!card.application) return forgetSession();
    return writeStore({
      [KEY.session]: {
        origin: location.origin,
        at: Date.now(),
        applicationId: card.application.id,
        status: card.application.status ?? "draft",
        jobId: card.job?.id ?? null,
        company: card.job?.company ?? null,
        title: card.job?.title ?? null,
        pdfReady: card.pdfReady === true,
        touched: card.touched === true,
        attachedBase: card.attachedBase,
        baseSlug: card.baseSlug,
      },
    });
  };

  const forgetSession = () => writeStore({ [KEY.session]: null });

  // ---------- talking to the service worker (design §3.2) ----------

  /** One message out, one answer back, failure as an exception.
   *
   * The envelope is `sw.js`'s `{ok: true, data}` / `{ok: false, error}`:
   * `sendResponse` has no reject channel, so errors travel as data and every
   * caller here would otherwise have to remember to branch on `ok`. A null
   * reply is its own case — that is the service worker not answering at all
   * (asleep and failing to wake, or a message type it does not handle), and
   * `reply.ok` on it would throw a TypeError instead of saying so. */
  async function ask(type, payload = {}) {
    // `chrome.runtime` is UNDEFINED in a content script whose extension has
    // been reloaded, and `chrome.runtime.id` goes undefined the moment the
    // context is invalidated. Either way this card is a GHOST: still on
    // screen, still rendering the state it had when the world ended, and every
    // button on it dead.
    //
    // Checked rather than left to fail, because of what it failed WITH:
    // "Cannot read properties of undefined (reading 'sendMessage')" printed on
    // the card. That describes one of our own stack frames to somebody who
    // wants to know why a button did nothing, and it never mentions the one
    // action that fixes it. Reported as exactly that, on a real card.
    if (!chrome.runtime?.id) throw new Error(CONTEXT_LOST);
    const reply = await chrome.runtime
      .sendMessage({ type, ...payload })
      .catch((err) => {
        // The same condition arriving the other way: the context can be torn
        // down between the check above and the call landing.
        const message = String(err?.message ?? err);
        if (/context invalidated|receiving end does not exist/i.test(message)) {
          throw new Error(CONTEXT_LOST);
        }
        throw err;
      });
    if (!reply) throw new Error("the extension's background worker did not answer");
    if (!reply.ok) throw new Error(reply.error ?? "the request failed");
    return reply.data;
  }

  /** The backend, through the service worker, which is the only context that
   * may reach it. A content script's cross-origin fetch presents the PAGE's
   * origin — `https://acme.wd5.myworkdayjobs.com` — which the backend's CORS
   * list does not admit, and widening it to admit arbitrary ATS hosts is the
   * trade this routing exists to avoid (design §3.2). */
  const api = (path, init) => ask("api", { path, init });

  /** Every frame of this tab, for the engine calls that must not miss the
   * application iframe. Greenhouse and Lever put the whole form in a subframe
   * while the top frame is marketing (design §3.1).
   *
   * Every call through here is behind a click. */
  const broadcast = (message) => ask("page_broadcast", { message });

  /** Fire and forget, and it must stay that way: telemetry may never surface
   * an error to the user and may never delay a fill.
   *
   * The opt-in check and the key allow-list both live in the service worker,
   * beside the only fetch site, so nothing composed here can leak a value by
   * being posted from somewhere the scrub does not run.
   *
   * Design §8.9's invariant is upheld structurally rather than by a check
   * here: every emitter is a card action, a card action needs a card, and a
   * card needs a mount, which needs a page that passed detection. */
  function sendTelemetry(action, observations) {
    if (!observations?.length) return;
    ask("telemetry", { action, page_host: location.hostname, observations })
      .catch(() => {});
  }

  // ---------- the shell (design §3.3) ----------

  const randomTag = () =>
    // A valid custom element name — one lowercase ASCII letter first, at least
    // one hyphen — with a random tail, so no page stylesheet or querySelector
    // can name this element. It is deliberately NOT registered with
    // customElements.define(): registration buys lifecycle callbacks this
    // widget does not use, and would add a cross-world question (does a
    // definition from an isolated world apply to the page's document?) that
    // cannot be answered from a coding session.
    //
    // An UNREGISTERED custom-named element still takes a shadow root: the
    // attachShadow allow-list is "a valid custom element name", not "a defined
    // one". Executed in a browser against this file — `customElements.get(tag)`
    // is undefined, the root attached, and `host.matches(":popover-open")` was
    // true — rather than read off the spec.
    `cs-${Math.random().toString(36).slice(2, 10)}`;

  function mountShell() {
    host = document.createElement(randomTag());
    for (const [name, value] of Object.entries(HOST_INLINE)) {
      host.style.setProperty(name, value, "important");
    }
    // `manual`, never `auto` (design §3.3): an auto popover light-dismisses, so
    // the widget would vanish on the user's first click anywhere on the page.
    host.setAttribute("popover", "manual");

    // `documentElement`, not `body`. An ancestor with transform/filter/
    // perspective/contain/will-change/content-visibility becomes the containing
    // block for `position: fixed` descendants, and Workday-class SPA shells do
    // exactly that — a widget under <body> silently becomes body-relative and
    // gets clipped or scrolled away (design §3.3).
    document.documentElement.appendChild(host);

    // CLOSED (design §3.3). An open root is the documented DOM-clickjacking
    // vector, it is what Bitwarden and 1Password use, and it strips our
    // internals out of `composedPath()` for anything listening on the page.
    root = host.attachShadow({ mode: "closed" });
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(SHEET);
    root.adoptedStyleSheets = [sheet];

    // Top layer. Everything above still works without it — that is what
    // Z_FALLBACK is for — so a browser that has not shipped popover, or a state
    // where showPopover() is refused, degrades to a very high z-index rather
    // than to nothing.
    try {
      host.showPopover?.();
    } catch (err) {
      console.warn("[maestro-cs] top layer unavailable, using z-index:", err);
    }

    // Design §3.3, with one correction that was MEASURED rather than reasoned:
    // the listener is BUBBLE phase, not capture.
    //
    // Run in a browser, on a host with a closed root and a button inside it,
    // clicking the button:
    //
    //   capture-phase stopPropagation at the host -> inner listener fired 0x
    //   bubble-phase  stopPropagation at the host -> inner listener fired 1x
    //   page listener at document, bubble phase   -> fired 0x in both
    //
    // Capture runs from the window DOWN, so the host is reached BEFORE the
    // control inside it, and `stopPropagation` there ends the dispatch: the
    // capture form makes every control in this widget dead.
    //
    // The bubble form buys the whole point of the rule — a page listener at
    // document/window in the bubble phase never sees the event, and that is
    // where an outside-click dismissal is attached, in Radix, in React portals,
    // in every dropdown on the web.
    //
    // What it does NOT buy, measured in the same run and stated because the
    // next reader will assume otherwise: a page listener at document in the
    // CAPTURE phase still fires, and no listener placed anywhere inside the
    // host can prevent it. What limits it is the closed root — that listener's
    // `event.target` is retargeted to the host and its `composedPath()` begins
    // at the host, so it sees a randomly-named element and a coordinate, and
    // nothing of what is inside.
    for (const type of SHIELDED_EVENTS) {
      host.addEventListener(type, (event) => event.stopPropagation());
    }

    dockEl = document.createElement("div");
    dockEl.className = "dock";
    root.appendChild(dockEl);
  }

  /** The card's skeleton, built ONCE. Everything that changes is a
   * `[data-role]` slot that `render()` refills.
   *
   * `innerHTML` here and nowhere else in this file: this string is a constant,
   * and every value that comes from the page, the backend or the user is
   * written with `textContent` in the renderers below. A job title is attacker-
   * influenced text on an ATS that lets employers write their own postings.
   *
   * No tab bar (design §4.2). The four `data-view` blocks are ONE level down
   * inside the same card, reached from the secondary row and returning with
   * one back button — never a second tab. */
  function buildUi() {
    cardEl = document.createElement("div");
    cardEl.className = "card";
    cardEl.setAttribute("role", "dialog");
    cardEl.setAttribute("aria-label", "Maestro CS Companion");
    // Design §3.3: inert until opened. On the CARD rather than the host —
    // inert on the host would include the launcher, which is the one control
    // that has to work while collapsed.
    cardEl.inert = true;
    cardEl.innerHTML = `
      <div class="card-head">
        <span class="brand one-line">Maestro CS</span>
        <a class="text-button" data-role="open-app" target="_blank" rel="noreferrer" hidden
          >Open in Maestro CS ↗</a>
        <button class="text-button" type="button" data-act="close" aria-label="Collapse">✕</button>
      </div>

      <div class="card-body">
        <div class="stack" data-view="main">
          <div>
            <div class="context-line one-line" data-role="context"></div>
            <div class="context-sub one-line" data-role="context-sub"></div>
          </div>
          <button class="primary" type="button" data-act="primary"></button>
          <a class="chip-button" data-role="custom-tailor" target="_blank" rel="noreferrer" hidden></a>
          <div class="small" data-role="note"></div>
          <div data-role="base"></div>
          <div class="small" data-role="targeting"></div>
          <div class="fit" data-role="fit" hidden></div>
          <div class="strip" data-role="strip" hidden></div>
        </div>

        <div class="stack" data-view="fields" hidden>
          <button class="chip-button" type="button" data-act="back">← Back</button>
          <div data-role="fields"></div>
        </div>

        <div class="stack" data-view="questions" hidden>
          <button class="chip-button" type="button" data-act="back">← Back</button>
          <div data-role="questions"></div>
          <div>
            <label class="field-label" for="cs-ask">Ask about the question in front of you</label>
            <textarea id="cs-ask" data-role="ask" placeholder="Paste one question…"></textarea>
          </div>
          <div class="secondary">
            <button class="text-button grow" type="button" data-act="ask">Ask</button>
            <a class="text-button grow" data-role="qa-link" target="_blank" rel="noreferrer" hidden
              >Full Q&amp;A history ↗</a>
          </div>
          <div class="small" data-role="answer"></div>
        </div>

        <div class="stack" data-view="more" hidden>
          <button class="chip-button" type="button" data-act="back">← Back</button>
          <div data-role="more"></div>
        </div>
      </div>

      <div class="card-sticky" data-role="sticky">
        <div data-role="nudge"></div>
        <label class="toggle">
          <input type="checkbox" data-act="eeo" disabled>
          <span>Fill voluntary EEO fields
            <span class="muted">· set in Profile</span></span>
        </label>
        <div class="secondary">
          <button class="text-button grow" type="button" data-act="attach-base" data-role="attach">Attach base resume</button>
          <button class="text-button grow" type="button" data-act="questions">Answer questions</button>
          <button class="text-button" type="button" data-act="more" aria-label="More">⋯</button>
        </div>
      </div>

      <div class="card-foot">
        <span>Always review before you submit. This companion never submits for you.</span>
      </div>`;

    bubbleEl = document.createElement("button");
    bubbleEl.className = "bubble";
    bubbleEl.type = "button";
    bubbleEl.innerHTML = '<span aria-hidden="true">R</span><span class="dot"></span>';

    dockEl.append(cardEl, bubbleEl);

    // Design §4.1: a CLICK expands it. Never hover — a hover-expand parked over
    // a form is an accidental-cover machine — and never detection, which only
    // ever changes the dot.
    //
    // One handler for pointer and keyboard both. A drag also ends in a click on
    // the captured element, so the drag suppresses exactly the next one rather
    // than each input mode getting its own toggle path.
    bubbleEl.addEventListener("click", () => {
      if (suppressClick) { suppressClick = false; return; }
      setExpanded(!expanded);
    });
    // One delegated listener for the whole card. `closest` rather than the
    // target itself because every button here has a text node inside it, which
    // is what an actual click lands on.
    // Two delegated listeners for the whole card, split by control kind rather
    // than by element: a checkbox click fires BOTH `click` and `change`, so a
    // single handler on either event would run a toggle's action twice.
    // `closest` rather than the target itself, because a click on a button
    // lands on the text node inside it.
    cardEl.addEventListener("click", (event) => {
      const control = event.target.closest?.("[data-act]");
      if (!control || control.matches("input, select, textarea")) return;
      const act = control.dataset.act;
      if (act === "close") { setExpanded(false); return; } // level 1: this page.
      if (act === "hide-origin") { hideHere(); return; } // level 2: this origin.
      runAction(act, control);
    });
    cardEl.addEventListener("change", (event) => {
      const control = event.target.closest?.("input, select, textarea");
      if (control?.dataset.act) runAction(control.dataset.act, control);
    });
    cardEl.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { setExpanded(false); bubbleEl.focus(); }
    });

    installDrag();
    applyDock();
    render();
  }

  // ---------- position + drag (design §4.1) ----------

  function applyDock({ side = null } = {}) {
    const effective = side ?? dock.side;
    dockEl.dataset.side = effective;
    dockEl.style.top = "auto";
    dockEl.style.bottom = `${clamp(dock.offset)}px`;
    dockEl.style.left = effective === "left" ? `${EDGE_MARGIN}px` : "auto";
    dockEl.style.right = effective === "right" ? `${EDGE_MARGIN}px` : "auto";
  }

  function installDrag() {
    let pointerId = null;
    let start = null;
    let moved = false;

    bubbleEl.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      pointerId = event.pointerId;
      const rect = bubbleEl.getBoundingClientRect();
      // Where inside the bubble the pointer grabbed it, so the bubble does not
      // jump to centre itself under the cursor on the first move.
      start = {
        x: event.clientX,
        y: event.clientY,
        grabLeft: event.clientX - rect.left,
        grabBottom: rect.bottom - event.clientY,
      };
      moved = false;
      // setPointerCapture (design §4.1): the drag keeps receiving moves even
      // when the pointer crosses one of the page's own elements, and there is no
      // document-level listener to leak or leave behind.
      bubbleEl.setPointerCapture(pointerId);
      dockEl.dataset.dragging = "true";
    });

    bubbleEl.addEventListener("pointermove", (event) => {
      if (pointerId === null || event.pointerId !== pointerId) return;
      if (!moved
          && Math.abs(event.clientX - start.x) < DRAG_SLOP
          && Math.abs(event.clientY - start.y) < DRAG_SLOP) {
        return; // still a click, not a drag.
      }
      moved = true;
      // Free-dragged in the SAME bottom-anchored model the docked state uses,
      // so nothing re-anchors mid-gesture and the card above the bubble does
      // not flip to the other side of it.
      dockEl.style.right = "auto";
      dockEl.style.left = `${Math.round(event.clientX - start.grabLeft)}px`;
      dockEl.style.bottom = `${Math.round(window.innerHeight - event.clientY - start.grabBottom)}px`;
    });

    const end = (event) => {
      if (pointerId === null || event.pointerId !== pointerId) return;
      bubbleEl.releasePointerCapture?.(pointerId);
      pointerId = null;
      delete dockEl.dataset.dragging;
      if (!moved) return; // a press with no travel is a click; the click handler has it.

      suppressClick = true;
      // Snap to the nearer side and persist SIDE + OFFSET, never x/y: the next
      // page is a different window size, and an absolute x is off-screen there.
      const rect = bubbleEl.getBoundingClientRect();
      dock = {
        side: rect.left + rect.width / 2 < window.innerWidth / 2 ? "left" : "right",
        offset: clamp(window.innerHeight - rect.bottom),
      };
      saveDock();
      evaluateCollision(); // also re-applies the dock, evade side included.
    };
    bubbleEl.addEventListener("pointerup", end);
    bubbleEl.addEventListener("pointercancel", end);
  }

  // ---------- expansion + state ----------

  function setExpanded(next) {
    expanded = next === true;
    dockEl.dataset.expanded = String(expanded);
    cardEl.inert = !expanded;
    bubbleEl.setAttribute("aria-expanded", String(expanded));
    if (!expanded) return;
    // The primary, not the close button: it is the one thing the card exists
    // to offer, and a keyboard user landing on ✕ has to tab past everything to
    // reach it.
    (cardEl.querySelector("[data-act='primary']")
      ?? cardEl.querySelector("[data-act='close']")).focus();
    // Both are lazy on purpose — the collapsed bubble needs neither, and this
    // is the moment the user has asked for the card.
    loadBaseResumes();
    render();
  }

  function applyState() {
    dockEl.dataset.state = dotState;
    bubbleEl.setAttribute(
      "aria-label",
      `Maestro CS Companion — ${DOT_STATES[dotState].label}`,
    );
    // Same string as a title, so the state is recoverable by hovering when the
    // colour is unavailable (forced colors) or unreadable (colour vision).
    bubbleEl.title = DOT_STATES[dotState].label;
  }

  // ============================================================
  // THE EXPANDED CARD (Tasks 14-17, design §4.2)
  // ============================================================
  //
  // `render()` is the only thing that writes to the card, and it rebuilds each
  // `[data-role]` slot from `card` every time. That is deliberately dumber than
  // patching: the card has four views and a dozen slots, and a targeted update
  // that forgets one leaves a stale sentence about a fill that was replaced —
  // which on this surface is a false claim about what landed on the page.

  // ---------- element helpers ----------
  //
  // Everything dynamic goes through `textContent`. A company name, a job title,
  // a field label and a backend error message are all attacker-influenced text
  // on an ATS that lets employers write their own postings, and the shadow root
  // being closed protects the page from us, not us from the page.

  const node = (tag, className, text) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined && text !== null) el.textContent = String(text);
    return el;
  };

  const slot = (role) => cardEl?.querySelector(`[data-role="${role}"]`);

  /** Replace a slot's contents. `null`/`undefined` children are skipped so a
   * renderer can put a conditional inline. */
  function fill(role, ...children) {
    const target = slot(role);
    if (!target) return null;
    target.replaceChildren(...children.filter(Boolean));
    return target;
  }

  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  /** A button that dispatches through the card's delegated listener. */
  function actionButton(act, label, { className = "chip-button", value = null } = {}) {
    const button = node("button", className, label);
    button.type = "button";
    button.dataset.act = act;
    if (value !== null) button.dataset.value = value;
    return button;
  }

  // ---------- render ----------

  /** The dot, the primary button and the nudge, from the card's current facts. */
  const currentDecision = () => resolvePrimary({
    match: card.match,
    hasApplication: card.application !== null,
    pdfReady: card.pdfReady,
    status: card.application?.status,
    touched: card.touched,
    hasForm: card.hasForm,
    // Base mode is "no application targeted"; a resume is armed once the list
    // has loaded and one is selected, which is the same slug Attach spends.
    baseArmed: card.application === null && Boolean(card.baseSlug),
  });

  function render() {
    if (!cardEl) return;

    const decision = currentDecision();
    dotState = decision.state;
    applyState();

    for (const view of cardEl.querySelectorAll("[data-view]")) {
      view.hidden = view.dataset.view !== card.view;
    }

    renderHeader();
    renderContext(decision);
    renderPrimary(decision);
    renderCustomTailor(decision);
    renderNote();
    renderBase();
    renderTargeting();
    renderFit();
    renderStrip();
    renderNudge(decision);
    renderAttach();
    // The sticky region belongs to the main view; the three views one level
    // down each end in their own back button and must not carry it.
    slot("sticky").hidden = card.view !== "main";
    const eeo = cardEl.querySelector("[data-act='eeo']");
    // Backend standing consent is the source of truth; the local chrome.storage
    // toggle is no longer authoritative for fill decisions.
    eeo.checked = card.eeoConsent?.enabled === true;
    eeo.disabled = true;

    if (card.view === "fields") renderFields();
    if (card.view === "questions") renderQuestions();
    if (card.view === "more") renderMore();
  }

  function renderHeader() {
    const link = slot("open-app");
    const appUrl = card.settings?.appUrl;
    // Design §4.2 item 8: the requested route into the web app. Hidden rather
    // than dead when we do not yet know where the web app is — a link that
    // resolves to nothing is the failure this project keeps naming.
    link.hidden = !appUrl;
    if (appUrl) link.href = card.job ? `${appUrl}/jobs/${card.job.id}` : appUrl;
  }

  /** Design §4.2 item 1: `Company · Title`, one line, truncating.
   *
   * Falls back to the page's own title, which is the only thing we honestly
   * know about a page that is not in the library yet — and it is what the
   * extractor will read if the user presses Add job. The state line below it
   * is the dot's accessible name, so the two never disagree. */
  function renderContext(decision) {
    const job = card.job;
    const context = slot("context");
    context.textContent = job
      ? [job.company, job.title].filter(Boolean).join(" · ") || "Untitled job"
      : document.title || location.hostname;
    context.title = context.textContent;
    slot("context-sub").textContent = DOT_STATES[decision.state].label;
  }

  /** Design §4.2 item 2: EXACTLY one primary button. */
  function renderPrimary(decision) {
    const button = cardEl.querySelector("[data-act='primary']");
    button.textContent = decision.action.label;
    button.dataset.primary = decision.action.id;
    button.disabled = card.busy !== null;
    button.classList.toggle("spin", card.busy === decision.action.id);
  }

  function renderNote() {
    const note = slot("note");
    note.textContent = card.note?.text ?? "";
    note.classList.toggle("error", card.note?.error === true);
    note.classList.toggle("muted", card.note?.error !== true);
  }

  /** The OTHER tailoring path, beside Fast tailor and only there: the web
   * app's gap-analysis session (`/jobs/{id}?tab=fit`, the Score & Tailor tab).
   * Quick tailor is the one-shot; custom tailoring — per-gap resolutions, a
   * tailoring note, the compare panel — deliberately stays in the web app, and
   * this link is how the card says so instead of silently offering only the
   * one-shot. An anchor, never a primary action: `resolvePrimary`'s table is
   * pinned to three actions, and this is a route, not an action.
   *
   * Hidden rather than dead when the app URL or the job is unknown — a link
   * that resolves to nothing is the failure this project keeps naming. */
  function renderCustomTailor(decision) {
    const link = slot("custom-tailor");
    const appUrl = card.settings?.appUrl;
    const show = decision.action.id === "fast-tailor"
      && Boolean(appUrl) && card.job !== null;
    link.hidden = !show;
    if (!show) return;
    link.href = `${appUrl}/jobs/${card.job.id}?tab=fit`;
    link.textContent = "Custom tailor in Maestro CS ↗";
  }

  /** The one attach control, labelled by what it will attach. With a targeted
   * application whose tailored PDF is rendered, attaching THAT is what the
   * user means (§11.13a: the side panel could, the widget could not); the
   * base resume stays one level down under ⋯ for that state. Everywhere else
   * the button is the escape hatch it always was. The label and the act move
   * together so the button never claims one PDF and attaches the other. */
  function renderAttach() {
    const button = slot("attach");
    const tailored = card.application !== null && card.pdfReady;
    button.dataset.act = tailored ? "attach-tailored" : "attach-base";
    button.textContent = tailored ? "Attach tailored resume" : "Attach base resume";
  }

  /** Which resume this card is armed with: your base, or the one tailored for
   * this job. ONE control, because it is ONE question — and the answer decides
   * what `Attach` sends, what `Fast tailor` starts from, and which application
   * the Q&A is written against.
   *
   * It used to be two stacked things: a `Base` dropdown, and a truncated status
   * line whose only affordance was a lowercase `change` link at the end of it.
   * That read as "base resume is the answer, and there is some other mode you
   * may go hunting for" — so after tailoring in the web app, coming back to the
   * posting meant finding a link you had to already know was there. Both states
   * are now visible at once and either is one click.
   *
   * Deriving the mode from `card.application` rather than storing it keeps one
   * source of truth: "a tailored application is targeted" IS tailored mode. */
  function resumeMode() {
    return card.picking || card.application !== null ? "tailored" : "base";
  }

  function renderBase() {
    if (card.baseResumes === null) return fill("base");
    if (card.baseResumes.length === 0) {
      return fill("base", node("div", "small muted",
        "No base resumes yet. Create one in Maestro CS."));
    }
    const mode = resumeMode();
    const wrap = node("div", "stack-tight");

    const label = node("div", "field-label", "Resume");
    const segmented = node("div", "segmented");
    segmented.setAttribute("role", "group");
    segmented.setAttribute("aria-label", "Which resume to use");
    for (const [id, text] of [["base", "Base"], ["tailored", "Tailored"]]) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.act = `mode-${id}`;
      button.textContent = text;
      button.setAttribute("aria-pressed", String(mode === id));
      segmented.append(button);
    }
    wrap.append(label, segmented);

    if (mode === "base") {
      const ranked = rankBaseResumes(card.baseResumes, card.baseScores);
      const select = document.createElement("select");
      select.dataset.act = "base";
      select.setAttribute("aria-label", "Base resume");
      for (const resume of ranked) {
        const option = document.createElement("option");
        option.value = resume.slug;
        // The score comes first in the reading order after the name, because
        // it is the thing being compared. A resume with no score says nothing
        // rather than "0" — see rankBaseResumes.
        option.textContent = `${resume.display_name || resume.slug}${
          resume.score === null ? "" : ` · ATS ${Math.round(resume.score)}`}${
          resume.pdf_rendered_at ? "" : " (no PDF yet)"}`;
        select.appendChild(option);
      }
      select.value = card.baseSlug;
      wrap.append(select);

      // The ask, and only where it can be answered: scoring needs a job.
      if (card.job) {
        const scored = ranked.some((resume) => resume.score !== null);
        wrap.append(scored
          ? node("div", "small muted",
            "Ranked by ATS score against this job. Fast tailor builds on the "
            + "one selected.")
          : actionButton("score-bases", "Score my resumes against this job"));
      }
    }
    return fill("base", wrap);
  }

  /** Design §4.2 item 3 and D4: auto-target, SHOW it, allow change.
   *
   * Two states, not three, because `GET /api/jobs/match` answers a yes/no
   * question: either this page is a job we have, or the picker is open. There
   * is no always-visible dropdown and no "probably this one" tier — the tier
   * that used to exist could not tell the apply page of a saved posting from a
   * sibling posting at the same employer (design §7 amendment). */
  function renderTargeting() {
    if (resumeMode() === "base") {
      // Nothing to say. Base mode IS "no application", the segmented control
      // above already shows that, and the line that used to sit here spent a
      // full row restating it.
      return fill("targeting");
    }

    if (card.applications === null && card.picking) {
      return fill("targeting", node("span", "muted", "Loading applications…"));
    }
    if (card.picking && card.applications?.length === 0) {
      return fill("targeting", node("span", "muted",
        "No applications yet. Add the job, then tailor it."));
    }

    // The application picker is a plain, always-visible select in this mode.
    // Auto-targeting still never GUESSES — `/api/jobs/match` either knows this
    // posting or it does not (design §7 amendment) — but once the user has
    // asked for a tailored resume, which one is a question they are entitled
    // to answer without going looking for a link.
    const select = document.createElement("select");
    select.dataset.act = "target";
    select.setAttribute("aria-label", "Tailored for which application");
    const options = card.applications ?? (card.application ? [card.application] : []);
    // A placeholder while nothing is chosen. Without it the select would sit on
    // the first application while `card.application` is still null — the
    // control would be claiming a target the card does not have.
    if (card.application === null) {
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "Choose an application…";
      select.appendChild(blank);
    }
    for (const app of options) {
      const option = document.createElement("option");
      option.value = app.id;
      option.textContent = `${app.job_company ?? card.job?.company ?? "?"} · ${
        app.job_title ?? card.job?.title ?? "Untitled"} (${app.status ?? "draft"})`;
      select.appendChild(option);
    }
    select.value = card.application?.id ?? "";
    const wrap = node("div", "stack-tight");
    wrap.append(select);
    // The one thing the toggle cannot show on its own: a targeted application
    // whose PDF has not rendered. Without this the Attach button silently
    // falls back to the base resume and the card looks like it ignored you.
    if (card.application && !card.pdfReady) {
      wrap.append(node("div", "small muted",
        "No tailored PDF yet. Attach sends your base resume."));
    }
    return fill("targeting", wrap);
  }

  /** Design §4.2 item 4. Rendered from the tailor response's `compare` and
   * never recomputed: a client-side score that disagrees with the platform's
   * own is the category failure this project refuses to ship (§11.7). */
  function renderFit() {
    const fit = slot("fit");
    const compare = card.compare;
    fit.hidden = !compare;
    if (!compare) return;
    fit.textContent = `ATS ${compare.before ?? "—"} → ${compare.after ?? "—"}`;
  }

  /** Design §4.2 item 5, the reconciliation strip. No competitor ships an
   * equivalent — the category's guidance for a wrong value is to eyeball the
   * form — so nothing here may be watered down into "12 fields filled ✓". */
  function renderStrip() {
    const strip = slot("strip");
    const fillResult = card.fill;
    const attached = card.attached;
    strip.hidden = !fillResult && !attached;
    if (strip.hidden) return;
    strip.replaceChildren();

    if (attached) {
      strip.append(node("div", "strip-counts",
        `Attached ${attached.filename} to ${plural(attached.count, "file input")}`));
      strip.append(node("div", "small muted", "Verify the upload took."));
    }
    if (!fillResult) return;

    const { counts } = fillResult;
    const parts = [
      `${counts.filled} filled`,
      counts.corrected ? `${counts.corrected} corrected` : null,
      // The fix for "0 filled" over a visibly full form: a field that already
      // held the answer — a re-run, or an agreeing ATS prefill — is its own
      // count, from the engine's own `already` list, not a judgement made here.
      counts.already ? `${counts.already} already filled` : null,
      counts.notStuck ? `${counts.notStuck} didn't stick` : null,
      counts.skipped ? `${counts.skipped} skipped` : null,
    ].filter(Boolean);

    // The counts and the disclosure share ONE row, above the list rather than
    // below it. The list is capped and scrolls (see the sheet), so a
    // disclosure placed after it is a control the user has to scroll a
    // scrollable box to find.
    const total = fillResult.filled.length + fillResult.corrected.length;
    const head = node("div", "row-inline");
    head.append(
      node("div", "strip-counts grow", parts.join(" · ")),
      actionButton("show-fields", total > FIELD_PREVIEW ? `all ${total}` : "details"),
    );
    strip.append(head);

    const list = node("ul");
    for (const item of fillResult.filled.slice(0, FIELD_PREVIEW)) {
      list.append(fieldLine(item));
    }
    for (const item of fillResult.corrected.slice(0, FIELD_PREVIEW)) {
      list.append(correctedLine(item));
    }
    if (list.childElementCount) strip.append(list);

    if (counts.noRule) {
      strip.append(node("div", "small muted",
        `${counts.noRule} field${counts.noRule === 1 ? "" : "s"} had no rule`));
    }
  }

  /** `label → value`, plus the engine's own hedge when the write may not have
   * registered. The hedge is the engine's string, not ours: it is the only
   * thing that knows whether the value survived two animation frames. */
  function fieldLine(item) {
    const li = node("li");
    li.append(node("span", null, `${item.label} → `), node("b", null, item.value));
    if (item.note) li.append(node("span", "muted", ` (${item.note})`));
    return li;
  }

  function correctedLine(item) {
    const li = node("li");
    li.append(
      node("span", null, `${item.label}: `),
      node("span", "was", item.was),
      node("span", null, " → "),
      node("b", null, item.value),
    );
    return li;
  }

  /** Design §4.2 item 6. TWO things can be true here, and the nudge carries
   * whichever one is:
   *
   * - there is an application and it is still a draft: one tap flips it, and
   *   that button is the ONLY thing in this extension that PATCHes a status.
   *   Never automatic — `applied_at` is stamped on entry to applied and feeds
   *   the analytics series, so a false positive silently corrupts a fact about
   *   the past while a false negative costs one click. (The watcher that once
   *   pre-answered this question is retired; the question, and the click,
   *   stay the user's.)
   * - there is no application at all, because the user took the escape hatch.
   *   D3: the attach wrote nothing, and THIS click is the first write.
   *
   * It renders in the STICKY region rather than under the strip, for the same
   * reason the secondary row does: a 25-field strip is the normal case, and a
   * prompt below it is a prompt nobody sees. Design §4.2 lists it after the
   * strip; the requirement it lists is "on the one visible surface". */
  function renderNudge(decision) {
    if (!decision.nudge) return fill("nudge");
    if (decision.nudge === "track-this") {
      return fill(
        "nudge",
        actionButton("track-this", "Track this application",
          { className: "text-button" }),
        // Still a draft when it lands. "Track this" creates the job and the
        // application the escape hatch skipped; marking it applied is the
        // next click and stays the user's (D3).
        node("div", "small muted",
          "Attaching wrote nothing down. This saves the job and an application "
          + "built from the base resume above."),
      );
    }
    return fill(
      "nudge",
      // `nudge-button`, not the bare `text-button` this used to be. A
      // text-button is grey-on-transparent with no border, which is right for
      // a secondary route and wrong for the one action the card is actively
      // asking you to take: it rendered as a grey SENTENCE, and was reported
      // as the applied button being missing from a card that was showing it.
      //
      // Two labels for two situations, because only one of them is a QUESTION
      // we have standing to ask. Having just filled this page earns "Submitted
      // it?"; arriving on a page we wrote nothing to — the confirmation page,
      // or a re-run where every field already agreed — does not, and asking
      // anyway would be the widget claiming credit for a fill it did not do.
      actionButton(
        "mark-applied",
        decision.prompted ? "Submitted it? Mark as applied" : "Mark as applied",
        { className: "text-button nudge-button" },
      ),
    );
  }

  // ---------- one level down, inside the same card ----------

  /** The full filled-field list, past the first six. Never a second tab. */
  function renderFields() {
    const target = fill("fields");
    const fillResult = card.fill;
    if (!fillResult) {
      target.append(node("p", "small muted", "Nothing filled yet."));
      return;
    }
    const section = (title, items, line) => {
      if (!items.length) return;
      target.append(node("div", "strip-counts", title));
      const list = node("ul", "list");
      for (const item of items) list.append(line(item));
      target.append(list);
    };
    section(`Filled ${fillResult.filled.length}`, fillResult.filled, fieldLine);
    section(`Corrected ${fillResult.corrected.length}`, fillResult.corrected, correctedLine);
    section(`Already filled ${(fillResult.already ?? []).length}`,
      fillResult.already ?? [], fieldLine);
    // Its own section, and it says "with opt-in": an entry here is a claim that
    // a protected characteristic was disclosed, so the engine only lists a
    // field it watched land (design §8.5).
    section(
      `EEO fields filled with opt-in: ${fillResult.eeoFilled.length}`,
      fillResult.eeoFilled,
      (item) => fieldLine({ label: item.label, value: item.value }),
    );
  }

  /** The open-question queue, the explicit AI action (D2), and a composer for
   * the question in front of you.
   *
   * The per-application Q&A TRANSCRIPT is deliberately not here: it is
   * list-shaped, versioned and re-readable, and the web app does it better
   * (design §4.2). The link below is the whole of that feature in the widget. */
  function renderQuestions() {
    const target = fill("questions");
    const appUrl = card.settings?.appUrl;
    const link = slot("qa-link");
    link.hidden = !(appUrl && card.job);
    if (!link.hidden) link.href = `${appUrl}/jobs/${card.job.id}?tab=qa`;

    if (card.questions === null) {
      target.append(node("p", "small muted", "Scanning the page…"));
      return;
    }
    if (card.questions.length === 0) {
      target.append(node("p", "small muted",
        "No open questions found. Unanswered dropdowns, radio groups, textareas "
        + "and question-like text fields get picked up here; identity, "
        + "work-authorization and EEO fields stay with the profile fill."));
      return;
    }
    target.append(node("div", "strip-counts",
      plural(card.questions.length, "open question")));
    const list = node("ul", "list");
    for (const question of card.questions.slice(0, AI_FILL_MAX)) {
      list.append(node("li", null, question.label));
    }
    target.append(list);
    if (card.questions.length > AI_FILL_MAX) {
      target.append(node("p", "small muted",
        `${card.questions.length - AI_FILL_MAX} more will wait for the next run.`));
    }
    // D2: distinct, explicit, opt-in, per click, bounded — and NEVER folded
    // into the primary Autofill button.
    const run = actionButton("ai-answer", "AI-answer remaining questions",
      { className: "text-button" });
    run.disabled = card.busy !== null || !card.application;
    target.append(run);
    if (!card.application) {
      target.append(node("p", "small muted",
        "Pick an application first. The answers are written against it and "
        + "saved to its Q&A history."));
    }
  }

  /** Status beyond the one-tap flip, connection settings, telemetry, and the
   * per-origin hide. One level down, inside the same card. */
  function renderMore() {
    const target = fill("more");

    if (card.application) {
      const label = node("label", "field-label", "Application status");
      label.htmlFor = "cs-status";
      const select = document.createElement("select");
      select.id = "cs-status";
      select.dataset.act = "status";
      // The backend's vocabulary. PATCH rejects anything else, so a status
      // invented here would be a dead control rather than a new feature.
      for (const status of ["draft", "applied", "interviewing", "offered",
        "accepted", "rejected", "withdrawn"]) {
        const option = document.createElement("option");
        option.value = status;
        option.textContent = status[0].toUpperCase() + status.slice(1);
        select.appendChild(option);
      }
      select.value = card.application.status ?? "draft";
      target.append(label, select);
    }

    const telemetry = node("label", "toggle");
    const telemetryBox = document.createElement("input");
    telemetryBox.type = "checkbox";
    telemetryBox.dataset.act = "telemetry";
    telemetryBox.checked = card.settings?.telemetryEnabled !== false;
    telemetryBox.disabled = card.settings === null;
    telemetry.append(telemetryBox, node("span", null,
      "Capture autofill telemetry. Field labels and outcomes only, never "
      + "values, posted to your own backend."));
    target.append(telemetry);

    // §11.4: the only infrastructure failure is "backend not reachable", and it
    // is rendered as one line naming the configured URL. Never a login card —
    // there is no account.
    const connection = node("div", "small muted",
      card.settings
        ? `Backend: ${card.settings.backendUrl} · Web app: ${card.settings.appUrl}`
        : "Connection settings unavailable.");
    target.append(connection);

    // When the secondary row's attach offers the TAILORED PDF, the base
    // resume stays reachable here — it is still the escape hatch, and it
    // still writes nothing (see renderAttach).
    if (card.application !== null && card.pdfReady) {
      target.append(actionButton("attach-base", "Attach base resume",
        { className: "text-button" }));
    }

    target.append(actionButton("hide-origin", "Hide the widget on this site",
      { className: "text-button" }));
    // The CURRENT binding, asked for at mount, never the manifest's suggestion:
    // the user can rebind it and Chrome silently drops a suggested key another
    // extension already claimed (design §4.1).
    target.append(node("div", "small muted",
      hotkeyLabel === null ? ""
        : hotkeyLabel ? `Bring it back: ${hotkeyLabel}`
          : "Bring it back: set a shortcut in chrome://extensions/shortcuts"));
  }

  // ---------- what the buttons do ----------

  /** One entry point for every control on the card.
   *
   * The `busy` guard is not cosmetic: a fill runs the commit ladder over every
   * field on the page and can take seconds, and a second click during it would
   * start a second pass that writes into fields the first is still verifying.
   * The instant actions (view changes, toggles) are exempt because they touch
   * nothing on the page. */
  function runAction(act, control) {
    const INSTANT = {
      back: () => { card.view = "main"; },
      more: () => { card.view = "more"; },
      "show-fields": () => { card.view = "fields"; },
      base: () => {
        card.baseSlug = control.value;
        // Once chosen by hand, a later score load must not move it — the
        // ranking is a suggestion and this was an instruction.
        card.basePickedByUser = true;
      },
      // The segmented control. "Base" means no application — the same state
      // the old picker's "Profile only" blank option produced, said in the
      // user's words instead of the data model's.
      "mode-base": () => {
        card.picking = false;
        card.application = null;
        card.pdfReady = false;
        // An explicit "use my base resume" is the user retracting the pick, so
        // the memory of it goes too — otherwise the next page load would re-arm
        // the application they just stepped away from.
        forgetSession();
      },
      "mode-tailored": () => {
        if (card.application === null) { card.picking = true; loadApplications(); }
      },
      "change-target": () => { card.picking = true; loadApplications(); },
    };
    if (Object.hasOwn(INSTANT, act)) {
      INSTANT[act]();
      render();
      return;
    }

    const RUNNING = {
      primary: () => runPrimary(cardEl.querySelector("[data-act='primary']").dataset.primary),
      "attach-base": attachBaseResume,
      "attach-tailored": attachTailored,
      questions: openQuestions,
      "ai-answer": aiAnswer,
      ask: askOneQuestion,
      "score-bases": scoreBaseResumes,
      "mark-applied": () => setStatus("applied"),
      "track-this": trackThis,
      target: () => pickTarget(control.value),
      status: () => setStatus(control.value),
      eeo: () => {
        // Standing consent is owned by Profile; the checkbox is display-only.
        const appUrl = card.settings?.appUrl;
        if (appUrl) {
          say("Change EEO standing consent under Profile in Maestro CS.");
          window.open(`${appUrl}/profile`, "_blank", "noopener,noreferrer");
        } else {
          say("Change EEO standing consent under Profile in Maestro CS.");
        }
      },
      telemetry: () => saveSetting("telemetryEnabled", control.checked),
    };
    if (!Object.hasOwn(RUNNING, act)) return;
    if (card.busy !== null) return;
    // The primary's id is what the spinner keys on, so the busy marker is the
    // action the user pressed rather than the generic "primary".
    const busyId = act === "primary"
      ? cardEl.querySelector("[data-act='primary']").dataset.primary
      : act;
    card.busy = busyId;
    card.note = null;
    render();
    Promise.resolve()
      .then(RUNNING[act])
      .catch((err) => {
        card.note = { text: String(err?.message ?? err), error: true };
      })
      .finally(() => { card.busy = null; render(); });
  }

  /** The one primary button dispatches by the id `resolvePrimary` gave it, so
   * the table that decides the label and the table that decides the behaviour
   * are keyed on the same three strings. */
  const runPrimary = (id) => ({
    "add-job": addJob,
    "fast-tailor": fastTailor,
    autofill,
  })[id]();

  const say = (text, error = false) => { card.note = { text, error }; };

  // ---------- the primary actions, in flow order ----------

  /** Add job. The extraction runs in THIS frame and only this frame: a
   * posting's JSON-LD is in the top document, and the subframes are the
   * application form's problem.
   *
   * Called directly rather than through the service worker because `agent.js`
   * publishes its handler table onto the same namespace and runs in this frame
   * too — a message to ourselves would be a round trip for nothing. */
  async function addJob() {
    const posting = ns.pageHandlers.extract_job_posting();
    const job = await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify({
        raw_text: posting.text,
        source_url: posting.url || location.href,
      }),
    });
    card.job = { id: job.id, company: job.company, title: job.title };
    // The page IS this job now, whatever the URL matcher would say about it.
    card.match = "exact";
    card.application = null;
    card.pdfReady = false;
    // `already_existed` is a transient instance attribute rather than a column
    // (design §8.14), and it is the difference between "saved" and "you saved
    // this last week" — which is the whole reason the capture card had two
    // states.
    const skills = job.extracted_json?.skills?.length ?? 0;
    say(job.already_existed === true
      ? "Already tracked. This posting was saved earlier."
      : `Saved with ${plural(skills, "skill")} extracted.`);
  }

  /** Fast tailor. One POST, then the fit number and the applied lines.
   *
   * Every failure reads the same way — the backend's own detail, verbatim,
   * plus the route into the web app — because the panel's three-way branch on
   * the status code could not tell the 409s apart either: a health gate and an
   * in-progress session share one status and one string field (design §7 move
   * D, not implemented). Inventing a heading per status would be a claim about
   * which of them happened. */
  async function fastTailor() {
    if (!card.job) throw new Error("Add the job first.");
    if (!card.baseSlug) throw new Error("Pick a base resume first.");
    const out = await api(`/api/jobs/${card.job.id}/quick-tailor`, {
      method: "POST",
      body: JSON.stringify({ base_resume: card.baseSlug }),
    });
    if (out.health_warning) say(`⚠ ${out.health_warning}`);
    if (out.nothing_to_tailor) {
      say("Nothing to tailor. No gap this profile is allowed to resolve. "
        + "Attach the base resume instead, or open it in Maestro CS.");
      return;
    }
    card.compare = out.compare ?? null;
    card.application = {
      id: out.application_id,
      status: "draft",
      job_company: card.job.company,
      job_title: card.job.title,
    };
    // Rendering is server-side and can fail after the tailor has committed. A
    // dead Attach button would be worse than saying so: the web app shows
    // `render_error` and can re-render.
    card.pdfReady = out.pdf_ready !== false;
    if (!card.pdfReady) {
      say("Tailored, but the PDF render failed. Open it in Maestro CS to "
        + "see why and re-render.", true);
      return;
    }
    rememberSession();
    const applied = (out.applied ?? []).length;
    say(applied ? `Tailored. ${plural(applied, "change")} applied.` : "Tailored.");
  }

  /** Autofill. One context payload, one fan-out, one reconciliation.
   *
   * `/api/autofill/context` replaces three always-co-issued round-trips and
   * degrades per section: a skills outage returns `skills: null` rather than
   * failing the request, so the employment fill still runs. A null section is
   * an unavailable feed, which is why it becomes `[]` here and not an error. */
  async function autofill() {
    const context = await api(`/api/autofill/context${resumeQuery()}`);
    if (!context.profile || Object.keys(context.profile).length === 0) {
      throw new Error("No autofill profile yet. Fill it in under Profile in "
        + "Maestro CS.");
    }
    const frames = await broadcast({
      type: "profile_fill",
      profile: context.profile,
      employment: context.employment ?? [],
      // Backend standing consent is the only opt-in that may turn either of
      // these on. Legacy chrome.storage.sync.eeoAutofillEnabled is ignored.
      // Two flags from one record: disclosing protected characteristics and
      // ticking the application's own agreement boxes are different
      // permissions and are asked for separately.
      eeoEnabled: context.eeo_consent?.enabled === true,
      skills: context.skills ?? [],
      // Last, matching the engine's parameter order — the message and the
      // signature are read side by side and a test pins them to the same
      // sequence, because a positional call converted from a keyed message is
      // where a silent argument swap would live.
      consentForms: context.eeo_consent?.consent_forms === true,
    });
    if (context.eeo_consent && typeof context.eeo_consent === "object") {
      card.eeoConsent = {
        enabled: context.eeo_consent.enabled === true,
        consent_forms: context.eeo_consent.consent_forms === true,
        acknowledged_at: context.eeo_consent.acknowledged_at ?? null,
        policy_version: context.eeo_consent.policy_version ?? "",
      };
    }
    const result = reconcileFill(frames);
    // BEFORE the early return: a page full of no_rules is exactly the
    // coverage-gap evidence this channel exists to collect.
    sendTelemetry("profile_fill", result.observations);
    if (!result.reached) throw new Error(NO_FRAME_REACHED);
    if (!result.filled.length && !result.corrected.length) {
      card.fill = result;
      // "No matching fields" was a lie on a re-run: the fields matched, they
      // just already held the answers — usually because this widget wrote
      // them. Two different sentences for two different states.
      say(result.already.length
        ? `Nothing new to fill. ${plural(result.already.length, "field")} `
          + "already held the right values."
        : "No matching fields found on this page.");
      return;
    }
    card.fill = result;
    card.attached = null;
    card.touched = true;
    // `touched` is the bit that outlives this page: it is what puts the "Mark
    // as applied" nudge on the card, and losing it on the next wizard step is
    // why that button kept disappearing.
    rememberSession();
    // No note on success: the strip IS the result, and "review before
    // submitting" is already the last line of the card. A sentence that
    // repeats the footer costs a line the strip needs.
  }

  /** Which resume the fill's employment blocks and skills come from. The
   * application when we have one, else the chosen base, else neither — which
   * the endpoint accepts and answers with a profile-only payload. */
  function resumeQuery() {
    if (card.application) {
      return `?application_id=${encodeURIComponent(card.application.id)}`;
    }
    return card.baseSlug ? `?base=${encodeURIComponent(card.baseSlug)}` : "";
  }

  // ---------- the escape hatch (Task 17, D3) ----------

  /** Attach the base resume and write NOTHING.
   *
   * This is the unclaimed ground the research found: no product surfaces
   * "apply with my base resume" beside the AI action, so it is first-class in
   * the secondary row rather than buried. The whole point is that it costs the
   * user no setup — so it does not create a job, an application, or a status.
   * "Track this" (the nudge above) is where the write lives, and only if the
   * user asks for it. */
  async function attachBaseResume() {
    if (!card.baseSlug) throw new Error("Pick a base resume first.");
    const detail = await api(`/api/base-resumes/${encodeURIComponent(card.baseSlug)}`);
    if (!detail.pdf_path) {
      throw new Error("This base resume has no rendered PDF yet. Render it in "
        + "Maestro CS first.");
    }
    await attachPdf(
      `/api/base-resumes/${encodeURIComponent(card.baseSlug)}/pdf`,
      detail.pdf_path.split(/[\\/]/).pop() ?? `${card.baseSlug}.pdf`,
    );
    card.attachedBase = card.baseSlug;
  }

  /** Attach the targeted application's rendered TAILORED PDF (§11.13a — the
   * one thing the widget lost when the side panel went).
   *
   * Same escape-hatch rule as the base attach, and it matters more here
   * because it is less obvious: the tailored PDF always belongs to a real
   * application, but attaching it still writes NOTHING — no status change, no
   * render, no version. The nudge's "Mark as applied" stays the only write.
   *
   * The detail read re-checks `pdf_path` rather than trusting `card.pdfReady`:
   * that flag was set on a load that may predate a re-render or a draft edit
   * that cleared the artifact, and attaching a PDF that no longer exists would
   * fail with a worse message than this one. */
  async function attachTailored() {
    if (!card.application) throw new Error("Pick an application first.");
    const detail = await api(`/api/applications/${card.application.id}`);
    if (!detail.pdf_path) {
      card.pdfReady = false; // the render() in `finally` flips the button back.
      throw new Error("The tailored PDF is not rendered anymore. Open it in "
        + "Maestro CS and generate it again.");
    }
    await attachPdf(
      `/api/applications/${card.application.id}/pdf`,
      detail.pdf_path.split(/[\\/]/).pop() ?? "tailored-resume.pdf",
    );
  }

  /** The deferred write. Everything the escape hatch skipped, in one click:
   * the job if the page is not tracked yet, then the application built from
   * the base resume that was actually attached. */
  async function trackThis() {
    if (!card.job) await addJob();
    const application = await api("/api/applications/from-base", {
      method: "POST",
      body: JSON.stringify({
        job_id: card.job.id,
        base_resume: card.attachedBase ?? card.baseSlug,
      }),
    });
    card.application = {
      id: application.id,
      status: application.status ?? "draft",
      job_company: card.job.company,
      job_title: card.job.title,
    };
    card.pdfReady = Boolean(application.pdf_path);
    rememberSession();
    say("Tracked. Mark it applied when you have submitted it.");
  }

  /** The SW fetches the PDF, base64s it and fans it out, so the bytes never
   * travel through this frame. A Blob does not survive a message boundary in
   * either direction — both ends serialize, and this one is JSON. */
  async function attachPdf(path, filename) {
    const frames = await ask("attach_pdf", { path, filename });
    const count = frames.reduce((total, frame) => total + (frame.result ?? 0), 0);
    if (!count) {
      // The same distinction the fill path makes: "this page has no PDF input"
      // is a finding, and it may not be reported when no frame was looked at.
      throw new Error(frames.some((frame) => frame.result !== undefined)
        ? "No PDF-accepting file inputs found on this page."
        : NO_FRAME_REACHED);
    }
    card.attached = { filename, count };
    card.touched = true;
    rememberSession();
    say("Attached. Verify the upload took before submitting.");
  }

  // ---------- questions (D2) ----------

  async function openQuestions() {
    card.view = "questions";
    // null is "scanning"; the view says so. Every exit below leaves an ARRAY,
    // including the failures — otherwise a scan that threw leaves the card
    // saying "Scanning the page…" for the rest of the session.
    card.questions = null;
    render();
    let frames;
    try {
      frames = await broadcast({ type: "collect_open_questions" });
    } catch (err) {
      card.questions = [];
      throw err;
    }
    card.questions = frames.flatMap((frame) =>
      (frame.result?.questions ?? []).map((question) => ({
        ...question,
        frameId: frame.frameId,
        host: frame.result.host,
      })));
    // After the assignment, so "no open questions" and "we never got to ask"
    // are two different sentences on two different states.
    if (!frames.some((frame) => frame.result !== undefined)) {
      throw new Error(NO_FRAME_REACHED);
    }
  }

  /** D2, and the guard that makes it safe.
   *
   * The backend does NOT promise one answer per question: when the model's
   * reply carries no numbering, `_split_numbered_answers` falls back to a
   * ONE-element list however many questions were asked. Zipping that onto the
   * batch by index would paste the whole combined reply into the first field
   * and leave the rest silently wrong — so on a length mismatch we write
   * nothing. The reply is already stored as a Q&A entry and is recoverable; a
   * corrupted form field is not. */
  async function aiAnswer() {
    if (!card.application) throw new Error("Pick an application first.");
    const batch = (card.questions ?? []).slice(0, AI_FILL_MAX);
    if (!batch.length) throw new Error("No open questions to answer.");

    const response = await api("/api/qa", {
      method: "POST",
      body: JSON.stringify({
        application_id: card.application.id,
        questions: batch.map((question) => (question.options?.length
          ? `${question.label}\nAnswer with EXACTLY one of these options, `
            + `verbatim and nothing else: ${question.options.join(" | ")}`
          : question.label)),
      }),
    });
    const answers = response.answers ?? [];

    const observationFor = (question, outcome) => {
      const observation = {
        label: question.label.slice(0, 160),
        kind: question.kind,
        rule_id: null,
        host: question.host || location.hostname,
        outcome,
      };
      if (question.options?.length && (question.kind === "select" || question.kind === "radio")) {
        observation.options = question.options.slice(0, 30);
      }
      return observation;
    };

    if (answers.length !== batch.length) {
      // Two different failures, and the telemetry has to tell them apart: an
      // empty reply is honestly `ai_unanswered`, a failure. An unsplittable one
      // is `ai_unaligned`, which is NEUTRAL — the fill path declined, it did
      // not fail, and charging eight rule failures for the model's formatting
      // would move a per-kind rate the summary module declares frozen.
      const produced = answers.some((answer) => String(answer ?? "").trim());
      sendTelemetry("ai_fill",
        batch.map((question) => observationFor(question,
          produced ? "ai_unaligned" : "ai_unanswered")));
      throw new Error(produced
        ? "Nothing filled. The model answered every question in one block, so "
          + "its reply could not be split back into one answer per field. It is "
          + "saved to this application's Q&A history."
        : "Nothing filled. The model returned no answer.");
    }

    const pairs = batch
      .map((question, index) => ({ ...question, answer: sanitizeAnswer(answers[index]) }))
      .filter((question) => question.answer);
    // Broadcast rather than one strict message per frame: every qid was tagged
    // moments ago by `collectOpenQuestions`, whose token is per-frame random,
    // so a frame that does not own a qid simply finds nothing and skips it.
    const written = await broadcast({
      type: "fill_answers",
      pairs: pairs.map(({ qid, answer, kind }) => ({ qid, answer, kind })),
    });
    const reachedFrames = new Set(
      written.filter((frame) => frame.result !== undefined).map((frame) => frame.frameId));
    const stuck = new Set(written.flatMap((frame) => frame.result ?? []));
    const produced = new Set(batch
      .filter((question, index) => String(answers[index] ?? "").trim())
      .map((question) => question.qid));

    // A question whose frame went away between the scan and the write gets NO
    // observation at all. Every outcome available would be a claim about a
    // write nobody attempted, and the panel's alternative — abort the run —
    // cannot be expressed through a fan-out that tolerates a dead frame.
    sendTelemetry("ai_fill", batch
      .filter((question) => reachedFrames.has(question.frameId))
      .map((question) => observationFor(question,
        stuck.has(question.qid) ? "ai_answered"
          : produced.has(question.qid) ? "ai_no_stick" : "ai_unanswered")));

    card.touched = true;
    rememberSession();
    const lost = batch.length - batch.filter((q) => reachedFrames.has(q.frameId)).length;
    say(`AI-answered ${plural(stuck.size, "question")}. Edit on the page before `
      + `submitting.${lost ? ` ${lost} could not be written: that frame is gone.` : ""}`);
    card.view = "main";
  }

  /** The composer, and only the composer. The transcript lives in the web app
   * (design §4.2) — a chat log is list-shaped, versioned and re-readable, and
   * a 340px card is the wrong place for it. */
  async function askOneQuestion() {
    const box = slot("ask");
    const question = box.value.trim();
    if (!question) throw new Error("Paste a question first.");
    if (!card.application) throw new Error("Pick an application first.");
    const response = await api("/api/qa", {
      method: "POST",
      body: JSON.stringify({
        application_id: card.application.id,
        questions: [question],
      }),
    });
    const answer = (response.answers ?? []).join("\n\n");
    fill("answer", node("p", null, answer || "(no answer)"));
    // Cleared only now: a failure above leaves the typed question in place so
    // it is not lost.
    box.value = "";
    say("Saved to this application's Q&A history.");
  }

  /** The panel's `sanitizeAnswer`, which strips the markdown a model reaches
   * for out of text that is going into a plain form field. */
  function sanitizeAnswer(text) {
    return String(text ?? "")
      .replace(/^#{1,6}\s+/gm, "")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/`{1,3}([^`]*)`{1,3}/g, "$1")
      .replace(/^\s*(?:[-*•]|\d+[.)])\s+/gm, "")
      .replace(/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/gm, "")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  // ---------- status, targeting, settings ----------

  /** The one PATCH in this extension. Design §6: never automatic, in either
   * direction — `applied_at` is stamped on entry to applied and consumed by
   * the analytics series as a fact about the past. */
  async function setStatus(status) {
    if (!card.application) throw new Error("No application to update.");
    const updated = await api(`/api/applications/${card.application.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    card.application = { ...card.application, status: updated.status };
    rememberSession();
    say(status === "applied"
      ? "Marked applied. The applied date is recorded."
      : `Status updated to ${status}.`);
  }

  async function pickTarget(applicationId) {
    card.picking = false;
    if (!applicationId) {
      card.application = null;
      card.pdfReady = false;
      say("Using your base resume.");
      return;
    }
    const chosen = (card.applications ?? []).find((app) => app.id === applicationId);
    card.application = chosen ?? { id: applicationId, status: "draft" };
    const detail = await api(`/api/applications/${applicationId}`);
    card.pdfReady = Boolean(detail.pdf_path);
    card.application = { ...card.application, status: detail.status ?? "draft" };
    if (detail.job_id && detail.job) card.job = detail.job;
    // A hand-picked target must survive a re-detect, or the widget would argue
    // with the user about which application they meant.
    card.match = "exact";
    rememberSession();
  }

  async function saveSetting(key, value) {
    // Written straight to `chrome.storage.sync`, which is where the service
    // worker reads it from — one store, one value, no copy to keep in step.
    await chrome.storage.sync.set({ [key]: value });
    card.settings = { ...card.settings, [key]: value };
  }

  // ---------- loading what the card renders ----------

  /** Tier C (design §5), plus the one thing its answer cannot carry.
   *
   * `ApplicationSummary` has no `pdf_path`, and design §4.1's green means the
   * PDF is rendered — so a matched application costs a second read. Both are
   * cheap local reads and both happen at MOUNT rather than on expand, because
   * the dot is the whole point of the collapsed state: a card the user has to
   * open to learn the state would be a dot that says nothing. */
  async function loadContext() {
    try {
      const result = await api(`/api/jobs/match?url=${encodeURIComponent(location.href)}`);
      card.match = result.match;
      card.job = result.job
        ? { id: result.job.id, company: result.job.company, title: result.job.title }
        : null;
      card.application = result.application ?? null;
    } catch (err) {
      // The four facts are CLEARED rather than left alone, which was a real
      // bug found by driving this page: on an SPA route change the ask can
      // fail while the PREVIOUS posting's match is still in `card`, and the
      // widget would then offer to autofill the application belonging to the
      // job the user just navigated away from. `null` is what `resolvePrimary`
      // reads as "we do not know" — not as "none" — and it resolves to
      // `Add job`, which re-asks.
      card.match = null;
      card.job = null;
      card.application = null;
      card.pdfReady = false;
      // §11.4: one line, naming the configured URL. Never a login-shaped card,
      // because there is no account to log in to.
      say(`Maestro CS is not reachable${
        card.settings ? ` at ${card.settings.backendUrl}` : ""}: ${
        String(err?.message ?? err)}`, true);
    }
    // The backend did not put an application on this page. Before falling back
    // to "nothing armed", see whether this browser remembers one being picked
    // here — a wizard step is a fresh page load, and losing the pick on every
    // one of them is what made the card look like it forgot what it was doing.
    // `restorableSession` owns whether the memory may be used; the backend's
    // own answer always wins over it.
    if (!card.application) await restoreSession();

    // Cheap, and it makes the base dropdown a ranking rather than a guess.
    loadBaseScores();

    if (card.application) {
      try {
        const detail = await api(`/api/applications/${card.application.id}`);
        card.pdfReady = Boolean(detail.pdf_path);
        // The status may have moved on since the pick — marked applied in the
        // web app, or in another tab. The row is truth; the memory is a cache.
        card.application = { ...card.application, status: detail.status ?? "draft" };
      } catch (_) {
        card.pdfReady = false; // unknown reads as not-ready: it offers to tailor.
      }
    }
    render();
  }

  /** Re-arm the card from a remembered pick, if one survives the guards.
   *
   * The application is NOT re-fetched here: `loadContext` re-reads it right
   * after, for the pdf and the status, and doing it twice would spend a
   * round-trip to learn the same thing. What is restored is what the page
   * itself cannot say — which application the user chose, and that they have
   * already filled or attached here. */
  async function restoreSession() {
    const stored = await readStore();
    const entry = restorableSession(stored[KEY.session], {
      now: Date.now(),
      origin: location.origin,
      matchedJobId: card.job?.id ?? null,
      ttlMs: SESSION_TTL_MS,
    });
    if (!entry) return;
    card.application = {
      id: entry.applicationId,
      status: entry.status ?? "draft",
      job_company: entry.company,
      job_title: entry.title,
    };
    card.pdfReady = entry.pdfReady === true;
    card.touched = entry.touched === true;
    card.attachedBase = entry.attachedBase ?? null;
    if (entry.baseSlug) card.baseSlug = entry.baseSlug;
    if (!card.job && entry.jobId) {
      card.job = { id: entry.jobId, company: entry.company, title: entry.title };
    }
    // The user chose this target by hand; `resolvePrimary` reads anything but
    // "exact" as "we do not know" and would offer Add job over the top of it.
    card.match = "exact";
  }

  /** Forget what happened on THIS page and ask Tier C again, WITHOUT
   * remounting (design §5's re-detection rule).
   *
   * Everything cleared below is a fact about one posting: the fill that landed
   * on it, the tailor that produced its number, the questions scanned off it.
   * A single-page ATS that swaps postings under a live widget would otherwise
   * show the previous job's reconciliation strip beside the new job's title,
   * which is the most confident wrong thing this surface could say.
   *
   * The dock, the dismissal state and the settings are NOT cleared: none of
   * them is about the posting.
   *
   * STILL NOT WIRED TO ANYTHING IN PRODUCTION, and Task 18 deliberately did
   * not wire it. The obvious caller is the service worker's
   * `webNavigation.onHistoryStateUpdated`; whoever wires it decides what an
   * SPA route change means on a mid-application wizard first — today the
   * preview page is the only caller. */
  async function reDetect() {
    card.fill = null;
    card.attached = null;
    card.attachedBase = null;
    card.touched = false;
    card.compare = null;
    card.questions = null;
    card.applications = null;
    card.picking = false;
    card.note = null;
    card.view = "main";
    render();
    await loadContext();
  }

  async function loadSettings() {
    try {
      card.settings = await ask("widget_settings");
    } catch (_) {
      card.settings = null; // the toggles render disabled rather than lying.
    }
    try {
      const row = await api("/api/settings/eeo-consent");
      card.eeoConsent = row?.value ?? null;
    } catch (_) {
      // Leave prior consent alone on a transient failure; fill still re-reads
      // eeo_consent from /api/autofill/context at fill time.
    }
    render();
  }

  /** Every base resume's score against this job, from the app's own pipeline.
   *
   * A READ, and cheap: `GET /api/ats-scores?job_id=` returns whatever has already
   * been computed and computes nothing. Called whenever a job is known, so a
   * job scored in the web app is already ranked by the time the card opens.
   *
   * Failure is silent on purpose — the dropdown without scores is exactly the
   * dropdown that shipped before, so an outage costs the ranking and nothing
   * else. */
  async function loadBaseScores() {
    if (!card.job) return;
    try {
      card.baseScores = await api(`/api/ats-scores?job_id=${encodeURIComponent(card.job.id)}`);
    } catch (_) {
      card.baseScores = null;
      return;
    }
    // Move the selection onto the best resume, unless the user has picked one:
    // a ranking that quietly overrode an explicit choice would be the card
    // arguing with them.
    if (!card.basePickedByUser) {
      const best = rankBaseResumes(card.baseResumes, card.baseScores)[0];
      if (best && best.score !== null) card.baseSlug = best.slug;
    }
    render();
  }

  /** Run the scoring the card cannot do for itself.
   *
   * This is the one COMPUTE call the card makes, which is why it is a button
   * rather than something that happens on open: it scores every base resume
   * against this job, and doing that silently on every card open would spend
   * the user's machine on a question they had not asked.
   *
   * The response is the scores, so nothing is re-read afterwards. */
  async function scoreBaseResumes() {
    if (!card.job) throw new Error("Add the job first.");
    card.baseScores = await api("/api/ats-scores", {
      method: "POST",
      body: JSON.stringify({ job_id: card.job.id }),
    });
    const ranked = rankBaseResumes(card.baseResumes, card.baseScores);
    const best = ranked[0];
    if (best && best.score !== null) {
      if (!card.basePickedByUser) card.baseSlug = best.slug;
      say(`Best match: ${best.display_name || best.slug} · ATS ${Math.round(best.score)}.`);
    } else {
      say("Scored, but no base resume came back with a number.");
    }
  }

  let baseResumesRequested = false;
  async function loadBaseResumes() {
    if (baseResumesRequested) return;
    baseResumesRequested = true;
    try {
      const rows = await api("/api/base-resumes");
      card.baseResumes = rows;
      // The first row is the default, and it is VISIBLE in the select rather
      // than implied: both Fast tailor and the escape hatch spend it.
      card.baseSlug = rows[0]?.slug ?? "";
    } catch (_) {
      card.baseResumes = [];
      baseResumesRequested = false; // a transient failure may retry on reopen.
    }
    render();
  }

  async function loadApplications() {
    if (card.applications !== null) return;
    try {
      card.applications = await api("/api/applications?limit=100");
    } catch (err) {
      card.applications = [];
      say(String(err?.message ?? err), true);
    }
    render();
  }

  // ---------- submit-collision avoidance (Task 12, design §4.1) ----------

  function evaluateCollision() {
    if (!collision) return;
    // Only the controls the observer says are ON SCREEN. Measuring every submit
    // control in a long ATS form would mean a layout read per control per
    // frame, and one three steps below the fold cannot be in the way.
    const { homeBlocked, evadeSide } = chooseEvasion({
      dock: { side: dock.side, offset: clamp(dock.offset) },
      viewport: { width: window.innerWidth, height: window.innerHeight },
      targets: [...collision.near].map((el) => el.getBoundingClientRect()),
      size: BUBBLE_SIZE,
      margin: EDGE_MARGIN,
      gap: COLLISION_GAP,
    });

    collision.evadeSide = evadeSide;
    // Unconditional, so this is also the one place that re-clamps the offset
    // after a resize — and so the rendered side can never disagree with the
    // evade decision after a drag has moved the home corner.
    applyDock({ side: evadeSide });

    // Collapse on the EDGE into a collision, not on every evaluation: the user
    // is allowed to open the card over a submit button on purpose, and a check
    // that fired continuously would fight them for it.
    if (homeBlocked && !collision.colliding && expanded) setExpanded(false);
    collision.colliding = homeBlocked;
  }

  function watchForSubmitControls() {
    let scheduled = false;
    const schedule = () => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => { scheduled = false; evaluateCollision(); });
    };

    const near = new Set();
    const io = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) near.add(entry.target);
        else near.delete(entry.target);
      }
      evaluateCollision();
    }, { threshold: 0 });

    // `observed` is kept beside the observer because an IntersectionObserver
    // will not tell you what it is watching, and the difference between "found
    // no submit controls" and "found them, none are on screen" is the whole
    // diagnosis when this looks idle. `near` alone cannot tell them apart.
    const observed = new Set();
    collision = { io, near, observed, colliding: false, evadeSide: null };

    // `observe` on an element already observed is a documented no-op, so the
    // rescan below can be as dumb as re-running the query.
    const rescan = () => {
      for (const el of document.querySelectorAll(SUBMIT_SELECTOR)) {
        io.observe(el);
        observed.add(el);
      }
    };
    rescan();

    // An ATS renders its footer late and re-renders it per wizard step, so a
    // one-shot query at mount finds nothing on exactly the pages this exists
    // for. Trailing-debounced to one rescan per idle 400ms — and scoped to
    // pages that already passed detection, which is what design §5's
    // "no observer" rule is about: it forbids observing pages we cannot help
    // with, not the one we mounted on.
    let pending = null;
    const mo = new MutationObserver(() => {
      if (pending) return;
      pending = setTimeout(() => { pending = null; rescan(); evaluateCollision(); }, 400);
    });
    mo.observe(document.documentElement, { childList: true, subtree: true });
    collision.mo = mo;

    // IntersectionObserver answers "is it on screen"; proximity still changes
    // while it stays on screen and the page scrolls under a fixed widget.
    addEventListener("scroll", schedule, { passive: true, capture: true });
    addEventListener("resize", schedule, { passive: true });
    collision.detach = () => {
      removeEventListener("scroll", schedule, { capture: true });
      removeEventListener("resize", schedule);
      clearTimeout(pending);
    };
  }

  // ---------- dismissal (Task 13, design §4.1) ----------

  async function hideHere() {
    const stored = await readStore();
    await writeStore({
      [KEY.hiddenOrigins]: { ...stored[KEY.hiddenOrigins], [location.origin]: true },
    });
    unmount();
  }

  /** Level 3: the `chrome.commands` hotkey, a global toggle.
   *
   * The ON direction always produces a visible widget: it clears the global
   * flag and calls `mount()`, which does NOT consult the per-origin hide. A
   * toggle whose ON direction can leave the screen unchanged is the Jobscan
   * failure design §4.1 names — a control that does not do what its message
   * says — and the origin the user hid is exactly where they would press it. */
  async function toggleGlobally() {
    if (host) {
      await writeStore({ [KEY.hiddenGlobally]: true });
      unmount();
      return;
    }
    await writeStore({ [KEY.hiddenGlobally]: false });
    await mount();
  }

  /** The toolbar action: re-mount here, overriding a per-origin hide for this
   * session (design §4.1). It never hides — a user who clicks the icon is
   * asking for the widget, and the icon is also the only affordance a user who
   * has forgotten the hotkey can find. */
  async function showHere() {
    await writeStore({ [KEY.hiddenGlobally]: false });
    if (!host) await mount();
    setExpanded(true);
  }

  /** The hotkey as the browser has it bound RIGHT NOW, from
   * `chrome.commands.getAll()` in the service worker (`chrome.commands` is not
   * exposed to content scripts).
   *
   * Asked rather than hard-coded because the manifest only SUGGESTS a key: the
   * user can rebind it at chrome://extensions/shortcuts, and Chrome silently
   * drops a suggested key that another extension already claimed. Printing a
   * key that is not bound is the same failure as naming a control that does not
   * exist. */
  async function askHotkey() {
    try {
      hotkeyLabel = (await ask("widget_hotkey"))?.shortcut ?? "";
    } catch (_) {
      hotkeyLabel = ""; // the SW is asleep or gone; say nothing rather than guess.
    }
    render();
  }

  // ---------- mount / unmount ----------

  async function mount() {
    if (host) return;
    // The dock is read from storage every time rather than kept across an
    // unmount, so a mount is a function of what is stored and nothing else.
    // Otherwise clearing the stored position leaves the widget wherever it
    // happened to be, which is a state no reload can reproduce.
    const stored = await readStore();
    const saved = stored[KEY.dock];
    dock = saved && typeof saved.offset === "number"
      ? { side: saved.side === "left" ? "left" : "right", offset: clamp(saved.offset) }
      : { ...DEFAULT_DOCK };
    mountShell();
    buildUi();
    watchForSubmitControls();
    evaluateCollision();
    // Not awaited, and the order matters only for the error line: settings
    // carry the backend URL that an unreachable-backend message names.
    // Each one calls render() when it lands, and none of them expands the card.
    askHotkey();
    loadSettings().then(loadContext);
  }

  function unmount() {
    if (!host) return;
    collision?.io.disconnect();
    collision?.mo?.disconnect();
    collision?.detach?.();
    collision = null;
    try { host.hidePopover?.(); } catch (_) { /* not in the top layer; removing is enough */ }
    host.remove();
    host = root = dockEl = bubbleEl = cardEl = null;
    expanded = false;
    // The card's own state is deliberately NOT cleared. An unmount is a
    // dismissal or a hotkey toggle, not a page load — a user who hides the
    // widget mid-application and brings it back has not undone the fill, and
    // re-rendering an empty reconciliation strip would say they had.
    card.view = "main";
    card.busy = null;
  }

  /** The visible failure, and the reason it is not always visible.
   *
   * A build where the namespace never got populated — a renamed file, a
   * `content_scripts.js` array that lost an entry, a syntax error earlier in
   * the injection order — is invisible otherwise: the widget simply never
   * appears, which is also what a page that scored 0 looks like.
   *
   * So it is loud in the console always, and loud ON SCREEN only when the user
   * explicitly asked for the widget (toolbar action, hotkey). Rendering a
   * banner on page load instead would put an error box on every page on the
   * web, which is design §5's negative rule inverted — and on a page that
   * scored 0 we would be asserting a broken build to somebody reading the news. */
  function mountFailure(missing) {
    if (host) return;
    mountShell();
    const box = document.createElement("div");
    box.className = "boot-error";
    box.setAttribute("role", "alert");
    box.textContent = `Missing: ${missing.join(", ")}. Reload the extension at chrome://extensions.`;
    const title = document.createElement("b");
    title.textContent = "Maestro CS Companion did not load";
    box.prepend(title);
    dockEl.style.right = `${EDGE_MARGIN}px`;
    dockEl.style.bottom = `${EDGE_MARGIN}px`;
    dockEl.appendChild(box);
  }

  const missingExports = () => {
    const required = [
      ["detectPage", "content/detect.js"],
      ["pageHandlers", "content/agent.js"],
    ];
    return required.filter(([name]) => ns[name] === undefined).map(([, file]) => file);
  };

  // ---------- entry ----------
  //
  // TWO WAYS IN, and keeping them apart is the point.
  //
  // `autoMount()` is the page-load path: it gates on detection and on the
  // stored dismissals, and on almost every page on the web it returns without
  // touching anything.
  //
  // `mount()` is the explicit-request path: the toolbar action and the hotkey,
  // where the user has just asked for this widget by name. It consults NO
  // dismissal state, and that is what makes un-dismissal work at all — the
  // origin where the user pressed the button is precisely the origin they hid.
  //
  // Anything that mounts the widget WITHOUT a user gesture behind it must go
  // through `autoMount`. A future re-gate that calls `mount()` on a route
  // change would resurrect the widget on an origin the user hid.

  async function autoMount() {
    const missing = missingExports();
    if (missing.length) {
      // Console only: without detectPage this file cannot tell a job page from
      // any other page, so it has no standing to draw anything here. The hotkey
      // and the toolbar action still reach mountFailure() below.
      console.error(
        "[maestro-cs] the widget cannot start — no exports from:",
        missing.join(", "),
        "\nEach content script publishes onto window.careerStudioCompanion;",
        "an empty namespace means a file did not inject or threw before its",
        "publish block.",
      );
      return;
    }

    // The gate (design §5). Cheap, synchronous, side-effect free, and BEFORE
    // the storage read on purpose: `chrome.storage.local.get` on every page on
    // the web is exactly the always-on cost design §11 rejects, and the
    // overwhelming majority of pages stop on the line below.
    const verdict = ns.detectPage();
    if (verdict.tier === "none") return; // mount nothing, observe nothing, not even a dot.
    // Kept, not just tested: the card needs to know a form is here to offer to
    // fill it from a base resume, with no application in sight.
    card.hasForm = verdict.form === true;

    // Levels 2 and 3 of dismissal. This is the ONLY place they are consulted,
    // and that is what "the toolbar action overrides a per-origin hide for that
    // session" (design §4.1) means in practice: `mount()` is unconditional, so
    // an explicit request always produces a widget, and the hide comes back on
    // the next load of that origin because this function runs again.
    //
    // TRAP FOR TASK 18. The SPA route-change re-gate must not re-run this
    // check blindly on a page where the user asked for the widget by hand —
    // that would silently re-hide it mid-application, which is un-dismissal
    // that only appears to work. Whatever flag it needs belongs here, beside
    // the check it modifies.
    const stored = await readStore();
    if (stored[KEY.hiddenGlobally] === true) return;
    if (stored[KEY.hiddenOrigins]?.[location.origin] === true) return;

    await mount();
  }

  // ---------- top frame only ----------
  //
  // Design §3.1: the engine runs in every frame, the UI in exactly one. This
  // file is in the same `all_frames` array as the other two, so without the
  // guard a Greenhouse application iframe gets its own bubble, docked to that
  // iframe's viewport and holding its own copy of the state.
  //
  // The guard wraps the listener and the publish as well as `autoMount()`. A
  // subframe should not answer the widget's messages, and it should not offer
  // `ns.widget` to a caller that would then be driving a widget nobody can see.
  if (window.top !== window.self) return;

  // The service worker's two un-dismissal routes. Both land here because the SW
  // addresses frame 0, which is the only frame this code runs in.
  chrome.runtime.onMessage.addListener((msg, sender) => {
    if (sender?.id !== chrome.runtime.id) return false;
    if (msg?.type === "widget_toggle" || msg?.type === "widget_show") {
      const missing = missingExports();
      // The visible half of the loud failure: the user just asked for this
      // widget by name, so silence here is the failure design §4.1 rejects.
      if (missing.length) mountFailure(missing);
      else if (msg.type === "widget_toggle") toggleGlobally();
      else showHere();
    }
    // No reply, and no open channel: `agent.js` registers its own listener in
    // this same frame and answers the five page-function types, so returning
    // true here would hold a port open for a message nobody is waiting on.
    return false;
  });

  // ---------- what this file publishes ----------
  //
  // Same namespace, same reasoning as detect.js. `extension/dev/preview.html`
  // drives every one of these to exercise the card without a browser extension
  // and without a backend.
  //
  // `snapshot` exists because the shadow root is closed on purpose: nothing
  // outside this IIFE can read the widget's state from the DOM, so an explicit
  // accessor is the only way for the preview page — or a future browser check —
  // to assert what is on screen. It is safe to expose for the same reason the
  // rest is: the page has a different global and cannot see this object.
  ns.widget = {
    // The two entries, exposed side by side and named after the path they
    // take. `mount` bypasses the dismissal gate ON PURPOSE — see the entry
    // block above. Anything automatic uses `autoMount`.
    autoMount,
    mount,
    unmount,
    /** The dot, set by hand. A DEV affordance only: the real dot is derived by
     * `resolvePrimary` from the library facts on every render, so this holds
     * only until the next one. Nothing in the extension calls it. */
    setState(next) {
      if (!Object.hasOwn(DOT_STATES, next)) throw new Error(`unknown widget state: ${next}`);
      dotState = next;
      if (host) applyState();
    },
    expand: () => host && setExpanded(true),
    collapse: () => host && setExpanded(false),
    // Re-ask Tier C without remounting. The SPA route-change entry point — see
    // the block on `reDetect` for why nothing in production calls it yet.
    reDetect,
    hideHere,
    toggleGlobally,
    showHere,
    snapshot: () => ({
      mounted: host !== null,
      tag: host?.localName ?? null,
      state: dotState,
      expanded,
      view: card.view,
      primary: cardEl?.querySelector("[data-act='primary']")?.textContent ?? null,
      // The nudge as RENDERED, which nothing outside this IIFE can otherwise
      // read — the shadow root is closed.
      nudge: cardEl?.querySelector("[data-role='nudge']")?.textContent ?? null,
      match: card.match,
      job: card.job,
      application: card.application,
      pdfReady: card.pdfReady,
      baseSlug: card.baseSlug,
      compare: card.compare,
      touched: card.touched,
      counts: card.fill?.counts ?? null,
      attached: card.attached,
      note: card.note,
      dock: { ...dock },
      renderedSide: dockEl?.dataset.side ?? null,
      evading: collision?.evadeSide ?? null,
      colliding: collision?.colliding ?? false,
      // Both counts, because one of them cannot be read on its own. A single
      // "watching: 0" is three different situations — the observer never
      // started, the page has no submit controls, or it has them and none are
      // on screen — and only the third is the observer working correctly.
      submitControlsObserved: collision ? collision.observed.size : 0,
      submitControlsOnScreen: collision ? collision.near.size : 0,
      hostInline: host
        ? Object.fromEntries(
            Object.keys(HOST_INLINE).map((name) => [
              name,
              [host.style.getPropertyValue(name), host.style.getPropertyPriority(name)],
            ]),
          )
        : null,
    }),
  };

  autoMount();
})();
