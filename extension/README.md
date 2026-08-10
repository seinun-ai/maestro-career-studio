# Maestro CS Companion (Chrome extension)

A floating in-page widget for the local Maestro CS app. It appears on job
postings and application forms, and nowhere else.

There is no side panel and no popup. The extension is a small set of ordered
content-script modules plus a service worker:

| file | runs | does |
|---|---|---|
| `content/job-posting.js` | every frame, every page | the shared JSON-LD JobPosting walk |
| `content/policy.js` | every frame | the shared never-fill policy |
| `content/eeo.js` | every frame | voluntary EEO rules and protected-class control handling |
| `content/autofill.js` | every frame | profile field matching and fill engine |
| `content/open-questions.js` | every frame | open-question collection and answer injection |
| `content/detect.js` | every frame, every page | the detection gate — reads, scores, returns |
| `content/agent.js` | every frame | page RPC front door, extraction wrapper, resume attach |
| `content/widget.js` | the top frame only | the bubble and the card |
| `sw.js` | the extension | every backend call, the frame fan-out, the toolbar icon and the hotkey |

## The gate

The shared modules are injected before `detect.js`, but their IIFEs only publish
functions. `detect.js` is the first decision point and, on almost every page on
the web, the last code the widget calls. On a miss the extension mounts nothing,
stores nothing and sends nothing — not even a dot. The gate holds no state,
registers no observer and touches nothing on the page.

On a hit you get a 44px bubble docked to the edge. **It never auto-expands.**
Detection changes the dot's colour and nothing else; the card opens only when
you click.

| dot | means | the one primary button |
|---|---|---|
| grey | job page, not in your library | **Add job** |
| blue | in your library, not tailored | **Fast tailor** |
| green | application ready | **Autofill this form** |
| amber | filled or attached, still a draft | (nudge: mark as applied) |

## What the card does

- **Add job** — grabs the page's link and job description (schema.org
  `JobPosting` JSON-LD when the site provides it, visible text otherwise) and
  saves it. The backend extracts the JD immediately, so the job lands parsed and
  ready for ATS scoring. Duplicate saves are deduped by content hash and the
  card says "already tracked" rather than pretending it saved something new.
- **Fast tailor** — `POST /api/jobs/{id}/quick-tailor` with a base resume you
  pick. Returns the ATS lift (`61 → 78`) and the changes applied, both
  **rendered from the response and never recomputed here**. A health warning is
  shown as a caution; a 409 (health gate, or a session already in progress) is
  shown verbatim, because the two share a status code and inventing a heading
  for each would be a claim about which one happened. Custom tailoring stays in
  the web app — and whenever Fast tailor is on offer, a **Custom tailor in
  Maestro CS** link under it opens the job's Score & Tailor tab
  (`/jobs/{id}?tab=fit`), where the full gap-analysis session lives.
- **Autofill this form** — best-effort fill of personal details, education, work
  history, work authorization, preferences and your custom Q&A presets, in every
  frame of the tab (Greenhouse and Lever put the form in a subframe). See
  "How the fill behaves" below.
- **The base-resume dropdown is RANKED by this job's own ATS scores**, best
  first, each option showing its number. The app has always scored every base
  resume against a job — it is what the Score & Tailor tab is built on — and
  the card simply never asked, so it listed them in library order and the pick
  was blind. Fast tailor then built on whatever that pick was, and the single
  number it reported afterwards belonged to a resume nobody had reason to
  believe was the right one. Scores are READ on open (cheap, computes nothing);
  where a job has never been scored the card offers **Score my resumes against
  this job**, as a button rather than something that happens on open, because
  it is the one compute call the card makes. A resume with no score says
  nothing rather than zero, and sorts last. Picking one by hand wins over the
  ranking permanently.
- **Autofill works from a base resume, with no application at all.** Filling a
  form is a question about the PAGE; the Add job → Fast tailor → Autofill flow
  is a question about the library, and conflating them left Base mode with
  nothing to press: the primary reached Autofill only through a tracked job
  with a tailored PDF, while the escape hatch could already ATTACH that same
  base resume with no job and no application. Choosing **Base** on a page that
  holds a form now offers **Autofill this form** directly. It cannot fire in
  Tailored mode, so it never pre-empts tailoring, and it cannot fire on a
  posting with no form.
- **Resume: Base / Tailored** — one segmented control that decides which
  resume the card is armed with. **Base** picks from your base resumes and
  targets no application; **Tailored** picks the application whose tailored PDF
  you want, and is preselected whenever `/api/jobs/match` already recognised
  the posting. Both states are visible at once, so you can see which one is
  armed without opening anything.
  This replaced a `Base` dropdown stacked above a truncated status line whose
  only affordance was a lowercase `change` link at its end — which read as
  "base is the answer" and made picking a tailored application after a custom
  tailor a hunt for a link you had to already know was there. Auto-targeting
  still never *guesses*: `/api/jobs/match` either recognises the posting or it
  does not.
- **Attach resume** — one button, labelled by whatever the switch above says it
  will attach: **Attach base resume**, or **Attach tailored resume** when a
  targeted application has a rendered PDF (the base attach moves under `⋯` for
  that state). If the targeted application has no rendered PDF the card says so
  and the button falls back to the base resume, rather than silently attaching
  something you did not pick. Either way attaching **writes nothing**: no job,
  no application, no status. "Track this application" in the nudge is where the
  write lives, and only if you ask for it.
- **Answer questions** — scans the page for unanswered fields the profile did
  not cover (free text, textareas, dropdowns, radio groups — the model is told
  the exact options and must pick one), answers up to 8 through the app's Q&A
  endpoint, and fills them for review. It is a separate, explicit click and is
  never folded into Autofill. Identity, work-authorization and EEO fields are
  never AI-guessed. Answers land in the app's Q&A history; the full transcript
  lives in the web app, which the card links to.
- **The reconciliation strip** after any fill or attach —
  `14 filled · 2 corrected · 3 already filled · 1 didn't stick · 3 skipped`,
  the first six field names, and a disclosure for the rest. Every number comes
  from the fill engine's own per-field outcome; nothing is judged twice.
  **Already filled** is the fields that turned out to need nothing — the
  control already held the profile's answer, usually because you ran Autofill
  on this page before. They are counted so a re-run on a wizard step says
  "nothing new to fill" instead of the old lie, "0 filled".
- **The armed application survives the next page load.** An ATS application is
  a multi-step wizard and every step is a page load, so the tailored
  application you picked used to be gone by the following step — and with it
  the "Mark as applied" nudge, which only appears once this widget has filled
  or attached here. The choice is remembered for 30 minutes, per origin, and is
  used only when `/api/jobs/match` cannot name the page itself: if the backend
  recognises a *different* job, the remembered pick is discarded rather than
  offered on someone else's posting. Switching the segmented control back to
  **Base** forgets it immediately.
- **"Mark as applied" is on the card whenever a targeted application is still
  a draft** — you picked it, it is not applied yet, and that is the whole
  precondition. It used to require that this widget had filled or attached on
  the page you are looking at, which hid it on the submission-confirmation
  page (the one moment it is most wanted) and on any re-run where every field
  already held the right value. The wording changes with what we can honestly
  claim: after a fill here it asks **"Submitted it? Mark as applied"**; arriving
  cold it simply offers **"Mark as applied"**. The amber DOT keeps the stricter
  rule, because it means "filled here". It is a button you press; nothing detects or records a
  submission for you. (An automatic applied-detection watcher existed briefly
  and was retired 2026-07-28 — marking an application applied is now always
  your click.)
- **More** (`⋯`) — status beyond the one-tap `applied` flip, the backend/web-app
  URLs, the telemetry toggle, and "hide the widget on this site". (The EEO
  toggle is not in here: it sits on the main card, above the secondary row.)

## How the fill behaves

- **Checkboxes are left alone except in two authorised cases.** The default is
  to recognise a checkbox and skip it (outcome `skipped_checkbox`) — consent and
  subscribe traps are not worth guessing at. The exceptions:
  1. **EEO "select all that apply"** — only while the EEO opt-in is on, and only
     for the exact category names you supplied. One box per category is the only
     control shape that can carry a multi-category answer at all.
  2. **A box whose answer was derived** — today, "I currently work here" when the
     resume entry has no end date. The permission lives on the rule
     (`tickWhenYes`), so no other rule can acquire it by accident.

  Both cases look before they click, because `click()` toggles: a box that
  arrives ticked is your own answer and is never cleared. A click a framework
  cancels is reported as "didn't stick", never as filled.
- **EEO/voluntary disclosure fields are off by default.** The toggle is on the
  main card, directly above the secondary row ("Fill voluntary EEO fields — off
  by default"), rather than buried under `⋯`. While it is off, those
  fields are seen and skipped. While it is on, writes are **exact or nothing**:
  a control that already carries an answer is never written over (a "decline to
  self-identify" is a real answer), and an option is chosen only by an exact
  normalized match or by a curated word list. The generic fuzzy scorer used for
  ordinary fields is deliberately not used here — it rated "Asian Indian" 72.5%
  against "Asian".
- **Repeated blocks (education, work history) are resolved by block, not by
  DOM order.** Each repeated block's position among the **visible** blocks of
  its family picks the resume entry, so a hidden prototype block no longer
  shifts every later entry. DOM order survives only as the fallback for pages
  that publish no block identity at all. The extension cannot click "Add
  another" for you — add the blocks first, then fill.
- **Never-filled at any setting: signatures, initials, passwords and
  government IDs** (SSN, passport, licence numbers). There is no profile value
  and no consent that unlocks these. A signature field asks you to produce your
  name, which is an ACT rather than an agreement; the others are credentials,
  not consent. A `type="password"` input is refused on its TYPE as well, so the
  protection does not depend on its label reading like a password.
- **An application's own agreement boxes** — "Yes, I have read and consent to
  the terms and conditions", acknowledgements, attestations, arbitration and
  waiver boxes — are **refused by default and unlocked by a standing consent**
  you give in Profile, beside the EEO opt-in. Two switches in one card, because
  they are one question to you ("what may this fill answer for me") and two
  decisions: a single switch would mean opting into EEO fill also opted you
  into agreeing to terms. Consent is recorded with a timestamp and a policy
  version and can be withdrawn. Even then it only ever TICKS A BOX: it looks
  before it clicks, never re-ticks a box that already carries your answer,
  reports a cancelled click as "didn't stick" rather than as agreed, and never
  submits. The AI path is unaffected — a consent field is still never offered
  to a model, because authorizing this engine to tick a box you decided to tick
  is not a licence for a model to decide what to agree to.
- **Standing eligibility answers** (Profile → Eligibility) cover the three
  questions nearly every US application asks that nothing else in the profile
  can derive: *are you 18 or older*, *have you previously been employed by this
  company*, and *are you subject to a non-compete or restrictive covenant*.
  They are structured fields rather than custom Q&A presets because every
  employer words them differently — "have you worked with us before", "are you
  currently or have you previously been employed by Doosan", "do you currently
  work for PwC" are one question, and a preset matches by substring so it would
  need one entry per employer. Each is **unset until you set it**: an
  eligibility answer the profile does not carry is reported as
  `missing_source` and the control is left blank, never guessed and never
  handed to a model — these are knockout answers, and one you did not give is
  one nobody may supply for you. "Previously employed here" is stored as a
  single standing answer even though it is per-employer by nature; where it is
  not true, change it by hand before filling.
- **Salary history is never filled.** Current/present/previous salary, last
  drawn salary, current CTC, salary history, wage history, compensation history,
  and an unqualified salary/wage/compensation label are blocked by the shared
  policy. Explicit expectations such as expected, desired, target, or salary
  range may fill `preferences.desired_salary`; an expectation phrase never
  overrides another policy block such as signature, consent, terms, credentials,
  or government-ID wording.
- **A subframe has to look like an application form before it gets anything.**
  The fill and attach fan-out reaches every frame in the tab — that is why a
  Greenhouse or Lever form in a subframe works at all — so an ad, analytics or
  chat-widget iframe on the same page would otherwise receive your profile
  values in its own DOM, where its own script can read them. The top frame (the
  one you are looking at) always qualifies; a subframe must show application-form
  evidence. Attach also skips inputs that are not on screen, because a file
  input's contents are readable the moment they are set, with no submit.
- Native `<select>`s get their best-matching option by length-aware scoring
  ("United States" picks "United States of America", not "…Minor Outlying
  Islands"). Custom comboboxes are typed into and the matching option clicked.
- **Workday's dropdowns are buttons, and they are filled.** Workday renders
  every dropdown as `<button aria-haspopup="listbox">` whose visible text is
  the committed value, and the engine used to walk only `input, select,
  textarea` — so Country, State, Phone Device Type, the work-authorization
  questions, "How did you hear about us" and every voluntary-disclosure
  dropdown were unfillable, and emitted no telemetry in any outcome. The writer
  opens the popup, picks by the same scorer, and reads the BUTTON'S OWN TEXT
  back: a click the widget cancelled is reported as a snap failure, never as
  filled. A button already showing an answer is left alone. The header's own
  menus (Settings, the account menu) carry `aria-haspopup` too and are excluded
  by their automation id.
- **A popup write stays inside its own control.** `[role="option"]` is
  document-wide, so an unscoped read collects every open popup on the page —
  and Workday marks a multiselect's already-chosen chips as options too, where
  the only thing a click can do is un-pick a committed value. Options come from
  the control's own `aria-controls` list where there is one; the fallback
  refuses chips. A popup's own "Select One" row is never chosen.
  Token inputs (Workday Skills) are typed one token at a time. Date controls
  receive only the part they asked for, in the format their own options use.
- **A split date is written whole before anything blurs out of it.** Workday
  renders a date as several `spinbutton` inputs inside one widget, and the
  widget validates when focus leaves the WIDGET, not the section — so blurring
  after the month, while the year is still empty, handed it a half-written date
  and it discarded the month. That was the `MM/2006` / "Invalid Date" failure.
  Every section of a date is written first and the blur happens once, when the
  fill moves to a different date or reaches the end of the run. Measured on a
  live form: the same writes that produced `MM/2006` now hold six sections
  across three dates with no error on the page. Trusted input is NOT what was
  missing — the identical untrusted write holds once the blur moves.
- Identity fields (name, email, phone) overwrite a wrong ATS prefill and are
  reported under "corrected"; identity **comboboxes** are fill-only-if-empty.
- Hidden clone fields are skipped, and a write a controlled input rejected is
  reported as "didn't stick" rather than as done.
- **Nothing is ever submitted automatically.** Always review before submitting.

## Reaching the widget again after you hide it

Three levels of dismissal, all reversible:

1. **X on the card** — collapses back to the bubble. The bubble stays; nothing
   is persisted.
2. **"Hide the widget on this site"** (under `⋯`) — no widget on this origin,
   persisted.
3. **The hotkey** (`Alt+Shift+J` by default) — a global on/off toggle.

The card prints the shortcut **as the browser currently has it bound**, asked
for at mount rather than hard-coded: you can rebind it at
`chrome://extensions/shortcuts`, and Chrome silently drops a suggested key
another extension already claimed.

**Clicking the toolbar icon** re-mounts the widget on the current page and
overrides a per-origin hide for that session. Both routes bypass the dismissal
check on purpose — the origin you hid is exactly the one you press the button
on. (The toolbar route is registered and the side panel that used to intercept
the click is gone; that it fires has not been confirmed in a browser. If the
icon does nothing, use the hotkey and please say so.)

## Telemetry — what leaves the page

On by default. **Toggle:** open the card → `⋯` → "Capture autofill telemetry".
It is fire-and-forget: it can never surface an error to you or delay a fill.

It is sent only from a page that passed the detection gate, only after a fill
or an AI answer. This is the complete list of what is posted to
`POST /api/autofill/telemetry` — there is nothing else:

**Per batch**

| field | value |
|---|---|
| `page_host` | the hostname of the top frame (e.g. `boards.greenhouse.io`), capped at 255 chars |
| `action` | one of `profile_fill`, `ai_fill` |
| `observations` | up to 200 of the rows below |

**Per observation** — exactly six keys, and the service worker drops everything
else before posting:

| field | value |
|---|---|
| `label` | the field's visible label text, capped at 160 chars |
| `kind` | the control shape: `text`, `textarea`, `select`, `radio`, `checkbox`, or `combobox` |
| `host` | the hostname of **the frame the field was in** — not the top frame, so an embedded Greenhouse form is attributed to `boards.greenhouse.io` |
| `outcome` | what happened: `filled`, `corrected`, `filled_normalized`, `not_stuck`, `combobox_snap_failed`, `no_rule`, `missing_source`, `skip_rule`, `skipped_checkbox`, `hidden`, `policy_blocked`, `eeo_disabled`, `ai_answered`, `ai_no_stick`, `ai_unanswered`, `ai_unaligned` |
| `rule_id` | which fill rule matched, or null |
| `options` | for a `select`, a `radio` group, or a Workday listbox-button dropdown whose popup was open at the time, **the option texts as the page renders them** — up to 30, each capped at 160 chars. This is the one field that carries page content, and it is here because a dropdown that could not be matched is unfixable without knowing what its options said. Nothing is ever opened in order to collect them: a telemetry read may not drive the page, so a closed popup reports no options rather than being poked into rendering |

**What is never sent:** the value typed into any field, the value that was there
before, any AI answer text, a field that already held its answer (no write, no
observation), and the contents of any other field on the page. The backend has
no column for a value and rejects unknown keys outright (`422`), so an
accidental extra key fails loudly rather than being stored.

### What it DOES hold — and how to get rid of it

The list above is complete, and "no values" is still not the same as "nothing
personal". `host` is in it, and the stored row stamps `first_seen_at`. So the
table that accumulates over a few months of applying is, read plainly, **a
record of which companies you applied to and when** — even though not one cell
says what you told them.

Three things bound that, and the third is the one that was missing until
2026-08-08:

1. **It stays on your machine.** The service worker posts to the backend URL on
   the card, which defaults to `http://localhost:8001`. There is no remote
   collector in this repository and no code path that would reach one, so a
   contributor mining telemetry to improve the fill rules — which is how the
   three standing-eligibility fields were chosen — can only ever mine *their
   own*.
2. **Capture is a toggle**, `⋯` → "Capture autofill telemetry". The summary
   endpoint will eventually tell you to use it: once the new-field share flattens
   it reports `coverage saturated — capture adds little`.
3. **`DELETE /api/autofill/telemetry` erases it**, surfaced in the web app as
   **Analytics → Autofill coverage → Clear data**. It reports how many rows went
   and it does *not* turn capture off — clearing history and opting out are two
   different decisions, and the button only makes the one you asked for.

## Install (unpacked)

1. Run the app: `docker compose up` (backend on `:8001`, frontend on `:3000`).
2. Open `chrome://extensions`, enable **Developer mode**.
3. **Load unpacked** → select this `extension/` directory.
4. Pin the extension. Open a job posting: the bubble appears by itself. Clicking
   the toolbar icon brings it back if you have hidden it.
5. If your ports differ, set the backend/web-app URLs under `⋯` on the card.
6. **A tab that was already open when you reloaded the extension has no
   content script**, because a content script only enters a page when that page
   loads. Clicking the toolbar icon or pressing the hotkey now injects the
   scripts into that tab and retries, so both routes work without a refresh.
   Anything else on such a tab — including the card's own buttons, if it was
   left open — still needs the page reloaded, and says so rather than claiming
   the page had nothing on it.

### There is no id to copy

`manifest.json` pins a `key`, so this extension hashes to the same id —
**`pjmfonfapjdabkoicnelpflpjojdjgan`** — on every machine that loads it, and
`app/config.py` already defaults its CORS allowlist to exactly that. Nothing to
paste, no backend restart.

> **Upgrading from a version before the key? Remove the extension and load it
> again — reloading is not enough.** Chrome assigns an unpacked extension's id
> when you install it and then keeps it, so the ↻ Reload button picks up new
> code but never re-derives the id. An install that predates the `key` keeps its
> old path-derived id indefinitely, the backend refuses it by CORS, and the only
> symptom is a card that cannot reach the backend. On `chrome://extensions`
> press **Remove**, then **Load unpacked** on this directory again, and confirm
> the id shown matches the one above.

That replaced a four-step dance (load unpacked → copy the id Chrome generated →
put it in `.env` → restart the backend) whose failure mode was silent: until you
got it right every call was refused by CORS and the card showed nothing but
connection errors.

The allowlist is still **exact ids only**. It used to be `chrome-extension://.*`,
which let *any* extension you had installed read the whole career record out of
an API that has no authentication — pinning the id narrows that further rather
than loosening it, because the one admitted id is now known rather than
whatever Chrome happened to generate. Set `MAESTRO_CS_EXTENSION_IDS` only to
admit a *different* build: a fork you re-keyed, or a Web Store install (Google
assigns that id and it will not match this one). The variable **replaces** the
default, so list every id you want, comma-separated.

Two consequences worth knowing:

- The pinned key is a **public** key and identifies the extension; it is not a
  secret and is meant to be committed. The matching private key is not in this
  repo and is not needed to load, run or develop the extension.
- Because the id no longer depends on the directory path, **moving your clone no
  longer changes it**. That used to silently break the allowlist.

## Notes & limitations

- The extension talks directly to your local backend. **Every fetch goes through
  the service worker**, because a content script's fetch presents the *page's*
  origin, which the backend's CORS list does not admit — and widening it to
  admit arbitrary ATS hosts is the trade this avoids. Nothing leaves your
  machine except the LLM calls the backend itself makes.
- The widget mounts in the **top frame only**; the fill engine runs in **every**
  frame. One dead frame (an ad iframe, a frame that navigated away) does not
  fail the run, and the reason it failed is kept in the console.
- `host_permissions` is broad (`http(s)://*/*`) so the gate can run anywhere
  without per-site prompts. The gate is what keeps that cheap: it is a
  synchronous, side-effect-free read that stops on the first line for almost
  every page. This is a personal, locally loaded extension — narrow it if that
  bothers you.
- **The per-application Q&A transcript is not in the widget** — a chat
  log is list-shaped, versioned and re-readable, and a 340px card is the wrong
  place for it. The composer for the question in front of you stays; the card
  links to `/jobs/{id}?tab=qa` for the rest.
- Multi-step wizards and "Add another" sections may still need manual entry.
- `extension/dev/preview.html` is a dev harness: it loads the ordered content
  modules against a synthetic application form with a stubbed service worker, so
  the card and the detection gate can be driven without loading the extension or
  running a backend. It is not shipped behaviour and not part of the extension.
