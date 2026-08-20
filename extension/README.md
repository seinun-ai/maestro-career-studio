# Maestro CS Companion (Chrome extension)

A side panel for the local Maestro CS app: save the posting in front of you,
pick or tailor a resume against it, fill the application form, and mark it
applied.

There is no popup and no in-page widget. The **side panel** (`panel/`) is the
extension's one surface. Both the toolbar icon (`openPanelOnActionClick`) and
the keyboard shortcut — `Alt+Shift+J` by default — open it, and it binds to the
tab you are on. The extension is that panel document, a set of ordered
content-script modules that read the page and do the field work, and a service
worker:

| file | runs | does |
|---|---|---|
| `shared/decisions.js` | every frame **and** the panel document | the pure decisions the panel renders from — `stageFor`, the base ranking, `reconcileFill`, the session guards, `sanitizeAnswer` |
| `shared/choose.js` | every frame **and** the panel document | the pure half of the open-question path: routing, the ≤40 `/choose` batch, `rest_fill` shaping, and the one `QUESTIONY` |
| `shared/guided-run.js` | every frame **and** the panel document | the guided-fill runner: one sequencing/batching engine, transport injected |
| `shared/policy.js` | every frame **and** the panel document | the shared never-fill policy — read by the fill engine and by the panel's pause row, whose render AND action are the half that is easy to miss |
| `shared/profile-fields.js` | every frame **and** the panel document | the label patterns naming a TYPED home in the autofill profile: one table read by the rule that FILLS the field and by the pause row that decides where an answer is LEARNED |
| `content/job-posting.js` | every frame, every page | the shared JSON-LD JobPosting walk |
| `content/eeo.js` | every frame | voluntary EEO rules and protected-class control handling |
| `content/autofill.js` | every frame | profile field matching and fill engine |
| `content/open-questions.js` | every frame | open-question collection and answer injection |
| `content/detect.js` | every frame, every page | the detection read — reads, scores, returns |
| `content/agent.js` | every frame | page RPC front door, extraction wrapper, resume attach |
| `panel/panel.{html,css,js}` | the side panel | the store, the loaders, the generation guard, the render loop, the tab binding; sends everything through the service worker |
| `panel/stages/*.js` + `panel/stages.js` | the side panel | one file per rail stage — a body is handed a per-render snapshot, never the store — gathered by a roster that throws when a script tag is missing |
| `panel/actions/*.js` + `panel/actions.js` | the side panel | one file per concern (add job, pick a draft, score, quick tailor + base as-is, start fill, submit one pause-row answer, ask one question, mark draft/applied), each handed one `write(patch)` door; `actions/during.js` is the `busy` span they all read, and `busy` covers everything an action writes including its learn tail |
| `sw.js` | the extension | every backend call, the frame fan-out, the one sanctioned injection, the hotkey, and giving the toolbar icon to the side panel |

## The gate

The content scripts are injected into every frame of every page, and on almost
every page on the web that is the whole of what they do: each module is an IIFE
that publishes functions, and `agent.js` registers one message listener. Nothing
detects on load, mounts anything, stores anything or sends anything.

`detect.js` is the decision point and it answers only when asked — the panel
sends `detect_page` to frame 0 of the tab it is bound to, because a panel runs in
no page. It reads, scores and returns four keys: the tier, whether a form's
evidence held, the score behind it, and how many upload boxes a resume could go
into. It holds no state, registers no observer and touches nothing on the page.
Tier A is a JobPosting **verdict** (a page either declares one or it does not),
Tier B is form evidence over a threshold, the two do not combine into one number,
and an ATS host is worth zero points on its own. On a miss the panel offers
nothing and constructs no telemetry observation.

## The rail

Five stages — **Job → Score → Resume → Fill → Track** — and the active one is
**inferred from the store** by `ns.decisions.stageFor` on every render, never set
by what was clicked. An action ends by re-running a load; "advance to Score" is
not a sentence any of them can say. Three rules hold the shape up:

- **ONE row shows a body**: the active one, or a DONE row you reopened. Score,
  Resume and Fill are always reopenable; **Job only when the binding is your own
  pick** (`claimed`), which is where un-pick and switch-draft live. Reopening is
  view state — never persisted, dropped when the stage moves or the page facts
  reset — and it rewinds no tick.
- **The footer holds exactly one primary**, and it follows the OPEN row: Add
  job, Score all bases, Quick tailor, Start fill. Track has none: its way onward
  is the header's link, and its control is the permanent Draft/Applied segment.
- **Nothing is claimed that is not known.** `match !== "exact"` means "we do not
  know", not "none", so an unreachable backend opens the journey at Job rather
  than claiming the job exists. Skipping is not doing: arming a base resume skips
  Score and Resume *visibly* — dashed, "Skipped — using base as-is", never a
  tick. And `done.fill` is this extension's own claim that it filled or attached
  HERE, so an application marked applied inside the web app does not put a
  checkmark on a page the extension never wrote to.

Above the rail sits the panel's whole header, and it is one block: the job's
identity and the match chip, the Before → After ATS rings under them (read from
stored scores, never computed here), and one deep link on the last line,
right-aligned. The link is labelled by the most specific thing we know — "Open
application ↗", else "Open in Maestro CS ↗", and nothing at all until the
service worker has said where the web app is; its `aria-label` spells the
destination out in full, because beside a job title "Open application" would
otherwise read as the posting's own apply page. It gets a line to itself
because it was measured beside the chip first: there it and the job title fight
over one axis, and at 400px — an ordinary side-panel width — the title was left
104px and five wrapped lines.

**There is no brand row**, and its absence is a decision. Chrome draws a
side-panel title bar above this document carrying the extension's name, and it
cannot be removed or retitled — so it IS the panel's title, and a mark plus the
words "Maestro CS" underneath it was the same name a second time, in the
scarcest 50 pixels a 400px-wide surface has. The row's only load-bearing part
was the link, so the link moved down into the identity block and the row went.

The manifest `name` **stays "Maestro CS Companion"** rather than shortening to
match the app. It was worth asking — it is now the only title anywhere on this
surface — but "Companion" is the word that separates the extension from the app
in the one place both are named together: the web app's own consent copy reads
"Allow Maestro CS Companion to fill voluntary EEO…", and "Allow Maestro CS to…"
inside Maestro CS reads as the app asking permission of itself. The repetition
that prompted the change is gone either way; the name is the last thing telling
you which of the two you are looking at.

## What the panel does

- **Add job** — the Job stage shows title, company and the grabbed job
  description in three fields you can correct before anything is saved (schema.org
  `JobPosting` JSON-LD when the site provides it, visible text otherwise). The
  line under them says where the JD came from and how many words it has, because
  three filled boxes over an empty description otherwise looks exactly like a
  successful read; when the page answers nothing at all it says the companion
  cannot see this page and to reload the tab, which is a claim about our reach
  rather than about the page. The backend extracts the JD immediately, so the job
  lands parsed and ready for ATS scoring, and a duplicate save says "Already
  tracked" rather than pretending it saved something new.
- **Pick a draft** — on a page nothing has matched, the Job stage offers your
  recent draft applications and you name the one you are here about. It is an
  OFFER, never a guess — the pick is your claim about the page — so it does not
  require a form to be visible. It used to, and Workday falsified that: its wizard
  urls match no job, its JD is in the DOM of pages that carry no form yet, and the
  form verdict at bind time is false anyway on a late SPA render. The refusal
  fired on exactly the flow the picker was written for.
- **The base resumes are RANKED by this job's own ATS scores**, best first, each
  row showing its number. The app has always scored every base resume against a
  job — it is what the Score & Tailor tab is built on — and the extension simply
  never asked, so it listed them in library order and the pick was blind. Fast
  tailoring then built on whatever that pick was, and the number it reported
  afterwards belonged to a resume nobody had reason to believe was the right one.
  Scores are READ on open (cheap, computes nothing); **Score all bases** is a
  button rather than something that happens on open, because scoring every base
  silently on every panel open is answering a question nobody asked. A resume with
  no score says "not scored" rather than zero and sorts last, a pick made by hand
  wins over the ranking permanently, and the line underneath names the engine
  version behind the numbers, or says nothing when the rows disagree about it —
  stored scores outlive the scorer that made them.
- **Use base as-is / Tailor** — the Resume stage is a fork on two levels, because
  the first question is whether to tailor at all and "quick or custom" is only a
  question for the user who said yes. Nothing is pre-selected: choosing a
  tailoring path on your behalf is what the Base/Tailored toggle this fork
  replaced did. *Tailor* discloses **Quick tailor** — the same function the
  footer's primary runs, one behaviour and one label — and **Custom in Studio ↗**,
  a real link to `/jobs/{id}?tab=fit` and never an API call, because the panel has
  no business creating a tailoring session behind your back; it picks the result
  up on the next load instead.
- ***Use base as-is* asks the backend for nothing and arms a fill from your base
  resume, with no application at all.** It is the FIRST rung of `stageFor`, above
  the library ladder, because **filling a form is a question about the PAGE**
  while the Add job → tailor → fill flow is a question about the library.
  Conflating them left a user who had armed a base resume with no way to fill the
  form in front of them: the primary reached a fill only through a tracked job
  with a tailored PDF, while the attach could already put that very resume in the
  page.
- **Quick tailor** — `POST /api/jobs/{id}/quick-tailor` with the base resume you
  picked. The changes applied are rendered from the response and never recomputed
  here; the After ring comes from re-reading the stored scores rather than from
  the response's own comparison, so those numbers have one home. Every failure
  reads the same way, deliberately: a health gate and a session already in
  progress share one status code and one string field, so a heading per code
  would be a claim about which of them happened. A render that fails after the
  tailor committed is not an error path — the application exists either way, and
  is remembered, or the next page of the wizard would offer to tailor a job that
  already has one.
- **Start fill** — the Fill stage runs the hybrid pipeline on this page: the
  profile rule pass, then one batched `/api/autofill/choose` call for everything
  the rules did not cover (chunked at 40 fields), then the sequenced writer. The
  mode segment picks the pass — **Rules only** skips `/choose` entirely,
  **Rules + AI assist** is the default because it answers more of the form — and
  the choice lives in `chrome.storage.sync`, so it follows the profile. Identity
  fields a rule tried and could not land are **retryables**: they re-enter the
  writer with the profile's own value, in memory only, and are never offered to
  the model. Nothing is submitted and no wizard step is advanced for you.
- **The progress rows are the report, and every number is the fill's own** —
  `14 filled · 2 corrected · 3 already filled · 1 didn't stick` for the profile
  pass, written-versus-still-open for the application questions, and one row for
  voluntary disclosures. **Already filled** is the fields that turned out to need
  nothing, usually because you filled this page before; they are counted so a
  re-run on a wizard step reads `0 filled · 12 already filled` — the truth —
  instead of a bare "0 filled", which reads as a pass that failed when in fact
  it found nothing left to do. The three sources are gated independently because they arrive
  independently: gating the whole report on the residue once erased two filled
  fields and printed "Can't reach this page" about a page the panel had just
  written into.
- **"These N fields need you"** — whatever the chooser abstained on, what did not
  stick, and the essays. Click a row to scroll that control into view (the message
  carries a qid and nothing else, which is what makes it safe to broadcast to
  every frame). Where the panel can actually write the answer — text, textarea,
  `select`, `radio`, and never a policy-blocked label — the row carries an inline
  box: type it, press, and **Remember this answer** is on by default, because the
  whole point of pausing once is not pausing again. A retryable arrives prefilled
  with the value the rule already knew, and offers no learn checkbox. A learned
  answer lands in a TYPED profile key when the fill rules have a declared home for
  that question and in the `custom` Q&A list otherwise — never in `qa_entries`,
  which is application-scoped and never read back into a later fill, so an answer
  saved there would pause again on the next application and break the promise the
  feature is named for.
- **Ask one question** — the QnA drawer at the foot of the Fill stage. Paste any
  question, get one grounded paragraph back from `/api/qa`, and copy it; essay
  rows in the still-open list carry an **Ask below** button that fills the
  composer with that question. The answer is deliberately **not** written into
  the page: an essay is the one thing on an application a person should read
  before it is submitted in their name. Grounding is the most specific thing we
  hold — the application, else the job plus your chosen base resume, else
  nothing, in which case the panel says so rather than sending a body the route
  would refuse.
- **Attach resume** — the tailored PDF into this page's own upload box.
  **Offered, never taken**: the panel does not attach during a fill and does not
  attach on a load, because a fill writes text you can read back at a glance and
  an upload is a whole document going to an employer. Three states off the page's
  own count of boxes a resume could go into: one box is the offer, naming the
  file; none is nothing at all; **more than one is a sentence and a dead button**,
  because the panel cannot tell a resume box from a cover-letter box and the page
  would look like it worked. The offer's own count travels with the write and
  every frame refuses if its list no longer says the same thing: without that the
  refusal was decoration, and a Workday step that revealed a cover-letter uploader
  between the detect and the press put the resume in both. The count reported
  afterwards is the engine's readback of `input.files`, and there is no second
  press.
- **Mark applied** — the Draft/Applied segment lives in the footer permanently,
  so there is no nudge to hunt for. It is withheld for a status outside that pair,
  because pressing Draft on an `interviewing` application would silently walk the
  record backwards past three states. It is the one PATCH this extension makes,
  and it is **never automatic in either direction**: `applied_at` is stamped by
  the backend on entry to applied and consumed by the analytics series as a fact
  about the past, so a false positive silently corrupts a record while a false
  negative costs one click. (An automatic applied-detection watcher existed
  briefly and was retired 2026-07-28.) The Track body renders no second status
  control — two Draft/Applied pairs on one screen are two writers for one field —
  and shows the evidence instead: the PDF that was rendered and the day it went
  out, or no line at all when neither.
- **The armed application survives the next page load**, and so does a finished
  fill. An ATS application is a multi-step wizard and every step is a page load,
  so the application you picked used to be gone by the following step. The choice
  is remembered for 30 minutes, in `chrome.storage.local`, scoped to the origin
  **and the tenant** — origin alone cannot scope it, because multi-tenant boards
  put thousands of companies on one origin and a Cohere pick restored onto a
  Lightning posting said "application ready" about an application that does not
  belong to the page (observed live 2026-08-16). A cross-tenant entry is trusted
  only when the backend matched this page to the very job the entry names, and a
  backend that recognises a *different* job discards the memory rather than
  offering it. `done.fill` rides the same entry, which is why reopening the
  ticked Fill row is how you reach Start fill again on page three of a form the
  extension has already finished once.

## How the fill behaves

- **Checkboxes are left alone except in two authorised cases.** The default is
  to recognise a checkbox and skip it (outcome `skipped_checkbox`) — consent and
  subscribe traps are not worth guessing at. The exceptions:
  1. **EEO "select all that apply"** — only while the standing EEO consent is
     on, and only for the exact category names you supplied. One box per
     category is the only control shape that can carry a multi-category answer
     at all.
  2. **A box whose answer was derived** — today, "I currently work here" when the
     resume entry has no end date. The permission lives on the rule
     (`tickWhenYes`), so no other rule can acquire it by accident.

  Both cases look before they click, because `click()` toggles: a box that
  arrives ticked is your own answer and is never cleared. A click a framework
  cancels is reported as "didn't stick", never as filled.
- **EEO/voluntary disclosure fields are off by default**, and the answer is the
  BACKEND's standing consent (`/api/settings/eeo-consent`, read off
  `/api/autofill/context`) — you grant it in Profile in the web app, and this
  extension offers no toggle that could turn it on. While it is off, those fields
  are seen and skipped and the Fill stage says "skipped — EEO off", so the
  silence does not read as a fill that missed a whole section. While it is on,
  writes are **exact or
  nothing**: a control that already carries an answer is never written over (a
  "decline to self-identify" is a real answer), and an option is chosen only by
  an exact normalized match or by a curated word list. The generic fuzzy scorer
  used for ordinary fields is deliberately not used here — it rated "Asian
  Indian" 72.5% against "Asian".
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
  protection does not depend on its label reading like a password. The panel's
  pause rows consult the same deny list rather than trusting that collection
  already refused it.
- **An application's own agreement boxes** — "Yes, I have read and consent to
  the terms and conditions", acknowledgements, attestations, arbitration and
  waiver boxes — are **refused by default and unlocked by a standing consent**
  you give in Profile, beside the EEO opt-in. Two switches side by side, because
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
  back: a click the page cancelled is reported as a snap failure, never as
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
- **Every writer commits the way a human would.** A `<select>` set through the
  native setter and a radio driven by `click()` fire no focus events, so
  Workday's required-field validation never ran over answers the page was
  visibly holding. Everything that is not a plain text commit is wrapped in one
  visit/leave gesture.
- Identity fields (name, email, phone) overwrite a wrong ATS prefill and are
  reported under "corrected"; identity **comboboxes** are fill-only-if-empty.
- Hidden clone fields are skipped, a write a controlled input rejected is
  reported as "didn't stick" rather than as done, and a write whose readback
  could not be confirmed in budget is `filled_unverified` — never `not_stuck`,
  because "we could not see it land" is a different claim from "it did not".
- **Nothing is ever submitted automatically.** Always review before submitting.

## Telemetry — what leaves the page

On by default (`telemetryEnabled` in `chrome.storage.sync`, gated and defaulted
in the service worker). It is fire-and-forget: it can never surface an error to
you or delay a fill. **There is no UI switch for it since the floating card
went** — the panel's only stored preference is the fill mode — so turning it off
means clearing that key or flipping the default in `sw.js`.

A batch only ever exists on a page you pointed the panel at: the fill engine is
the only thing that constructs an observation, and nothing runs it without your
click. This is the complete list of what is posted to
`POST /api/autofill/telemetry` — there is nothing else:

**Per batch**

| field | value |
|---|---|
| `page_host` | the hostname of the top frame (e.g. `boards.greenhouse.io`), capped at 255 chars |
| `action` | `profile_fill` (the rule pass) or `rest_fill` (the remainder pass). The backend's frozen vocabulary is wider than what this extension now sends |
| `observations` | up to 200 of the rows below |

**Per observation** — exactly six keys, and the service worker drops everything
else before posting:

| field | value |
|---|---|
| `label` | the field's visible label text, capped at 160 chars |
| `kind` | the control shape: `text`, `textarea`, `select`, `radio`, `checkbox`, or `combobox` |
| `host` | the hostname of **the frame the field was in** — not the top frame, so an embedded Greenhouse form is attributed to `boards.greenhouse.io` |
| `outcome` | what happened: `filled`, `corrected`, `filled_normalized`, `filled_unverified`, `not_stuck`, `combobox_snap_failed`, `no_rule`, `missing_source`, `skip_rule`, `skipped_checkbox`, `hidden`, `policy_blocked`, `eeo_disabled`, `retry_filled`, `match_recovered`, `ai_abstained`. (The backend also accepts `ai_answered`, `ai_no_stick`, `ai_unanswered` and `ai_unaligned` — stored rows carry them — but nothing emits one since the floating card was retired: its AI write-back path was their only source.) |
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

Two things bound that:

1. **It stays on your machine.** The service worker posts to the configured
   backend URL, which defaults to `http://localhost:8001`. There is no remote
   collector in this repository and no code path that would reach one, so a
   contributor mining telemetry to improve the fill rules — which is how the
   three standing-eligibility fields were chosen — can only ever mine *their
   own*.
2. **`DELETE /api/autofill/telemetry` erases it**, surfaced in the web app as
   **Analytics → Autofill coverage → Clear data**. It reports how many rows went
   and it does *not* turn capture off — clearing history and opting out are two
   different decisions, and the button only makes the one you asked for.

## Install (unpacked)

1. Run the app: `docker compose up` (backend on `:8001`, frontend on `:3000`).
2. Open `chrome://extensions`, enable **Developer mode**.
3. **Load unpacked** → select this `extension/` directory.
4. Pin the extension. Click the toolbar icon on a job posting or an application
   form: the side panel opens, binds to that tab, and shows the five-stage rail.
   `Alt+Shift+J` does the same — rebind it at `chrome://extensions/shortcuts`,
   where Chrome silently drops a suggested key another extension already claimed.
5. **The shortcut needs Chrome 116**, where `chrome.sidePanel.open()` landed,
   while `minimum_chrome_version` is 114: everything else including the toolbar
   click works on 114, and raising the minimum would lock out a browser whose
   only missing piece is this one route. On 114–115 the hotkey logs a warning
   naming the toolbar icon rather than failing as a bare TypeError.
6. If your ports differ, edit `DEFAULTS` in `sw.js` — the one place a default
   lives (the panel asks for them over `read_settings` rather than keeping a
   copy), and there is no settings screen in the panel to change them from.
7. **A tab that was already open when you reloaded the extension has no content
   script**, because a content script only enters a page when that page loads —
   and every MV3 reload orphans the scripts in every open tab, which shows up as
   "No job description found on this page" over a visible JD, forever. The panel
   injects them (`panel_prepare`, `chrome.scripting`) on three routes and no
   others: Start fill and Attach resume, both user gestures, and once per page
   after a posting read has come back silent. Never speculatively on a load —
   injecting into a page nobody asked about is exactly the always-on cost the
   detection gate exists to avoid — so anywhere else the panel says it cannot see
   the page and to reload the tab, rather than claiming it had nothing on it.

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
> symptom is a panel that cannot reach the backend. On `chrome://extensions`
> press **Remove**, then **Load unpacked** on this directory again, and confirm
> the id shown matches the one above.

That replaced a four-step dance (load unpacked → copy the id Chrome generated →
put it in `.env` → restart the backend) whose failure mode was silent: until you
got it right every call was refused by CORS and the UI showed nothing but
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
  origin, which the backend's CORS list does not admit — and widening it to admit
  arbitrary ATS hosts is the trade this avoids. The panel is an extension page
  and *could* fetch directly; it routes through the same door anyway, so there is
  one fetch site and one place the backend URL is read. Nothing leaves your
  machine except the LLM calls the backend itself makes.
- The panel runs in no page at all; the fill engine runs in **every** frame. One
  dead frame (an ad iframe, a frame that navigated away) does not fail the run,
  and the reason it failed is kept in the console.
- `host_permissions` is broad (`http(s)://*/*`) so the modules are present and
  the panel can reach whatever tab you point it at, without per-site prompts.
  What keeps that cheap is that they do nothing until asked, and that the first
  thing they are asked — the detection read — is synchronous and
  side-effect-free. This is a personal, locally loaded extension — narrow it if
  that bothers you.
- **The per-application Q&A transcript is not in the panel** — a chat log is
  list-shaped, versioned and re-readable, and a 400px rail is the wrong place
  for it. The composer for the question in front of you stays; the header's
  "Open application ↗" is the route to the rest.
- **Two identifiers keep historical names on purpose.** The command key is still
  `toggle-widget`, because Chrome keys a user's rebinding by the command NAME and
  renaming it silently discards every custom binding anyone has made; what a user
  sees is its description, "Open the Maestro CS panel on this page". The
  `widget.session` storage key is the same trade — renaming it drops every live
  entry, stranding a user mid-wizard. Three orphan keys the floating card left
  behind (`widget.dock`, `widget.hiddenOrigins`, `widget.hiddenGlobally`) plus
  `panel.pick` are swept once on panel boot.
- The hotkey cannot close the panel: `chrome.sidePanel` has an `open` and no
  counterpart, so the close affordance is the browser's own.
- Multi-step wizards and "Add another" sections may still need manual entry.
