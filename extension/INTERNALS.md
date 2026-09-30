# Maestro CS Companion — internals

How the Chrome extension is built and the rules its code depends on, for
contributors and agents changing `extension/`. If you only want to install and
use it, read [README.md](README.md) instead. SYSTEM.md §7 owns the panel's
shape; this file owns the mechanics, and each rule here was learned from a live
failure.

## Surfaces and files

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
| `shared/recipe-book.js` | the panel document | the recipe book: which of the engine's own moves worked per widget family, its lifecycle and bounds; the loop's `deps.recipes` |
| `shared/profile-fields.js` | every frame **and** the panel document | the label patterns naming a TYPED home in the autofill profile: one table read by the rule that FILLS the field and by the pause row that decides where an answer is LEARNED |
| `content/field-reader.js` | every frame | the new fill engine's one answer to "what is this field asking" (label-for → … → nearby → preceding: the visible text right before the field, when nothing names it — never a radio's or checkbox's, and only text that passes the label test: short, no sentence, no error, no heading before it, no other text or trailing label beside it), with its source. `readField(container)` runs it too, so a nameless group container or date wrapper can take its question from it; `ns.precedingLabel` is also a group's question with no container |
| `content/fill-base.js` | every frame | the engine's page primitives: budgets with real cancellation and a latched Stop, validation state, popup ownership, human typing, closing only popups the engine opened |
| `content/shapes.js` | every frame | widget shapes: recognise, group (a nameless radio outside any container joins its own run of nameless radios under the nearest ancestor holding no other kind of control — cut at visible text that is no option's label, never two options reading the same; a nameless checkbox stays alone; a named checkbox's same-name set stops at its nearest grouping container, since live Workday names every work entry's "I currently work here" box alike), read what is COMMITTED, how a choice widget opens |
| `content/recipes.js` | every frame | a popup or search widget's recipe keys: value-free hashes of its STRUCTURE (its family) and of that family on this host |
| `content/inventory.js` | every frame | every fillable control as a field with an element-bound fid and a fingerprint; marks fields the user changed |
| `content/fill-core.js` | every frame | the generic mechanics: write / explore / choose / set / recommit, verified after the final blur; the adaptive step's versioned state and code-generated moves (stepState / move) |
| `content/fill-ops.js` | every frame | the engine's page operations behind agent.js's `fill_*` handlers — fingerprint, touched and policy re-checked at execution; every throw returned as an outcome |
| `content/sections.js` | every frame | repeating sections (Work Experience, Education, Websites…): their headings, entry counts and which entries hold a value, and one press of a section's OWN Add — never a Delete |
| `content/job-posting.js` | every frame, every page | the shared JSON-LD JobPosting walk |
| `content/eeo.js` | every frame | voluntary EEO rules and protected-class control handling |
| `content/autofill.js` | every frame | profile field matching and fill engine |
| `content/open-questions.js` | every frame | open-question collection and answer injection |
| `content/detect.js` | every frame, every page | the detection read — reads, scores, returns |
| `content/agent.js` | every frame | page RPC front door, extraction wrapper, resume attach |
| `panel/panel.{html,css,js}` | the side panel | the store, the loaders, the generation guard, the render loop, the tab binding; sends everything through the service worker |
| `panel/stages/*.js` + `panel/stages.js` | the side panel | one file per rail stage — a body is handed a per-render snapshot (`stageContext`), never the store, and `card` is never published — gathered by a roster that throws when a script tag is missing |
| `panel/actions/*.js` + `panel/actions.js` | the side panel | one file per concern (save job and score its bases, pick a draft, quick tailor + base as is, fill this form, submit one pause-row answer, ask one question, mark draft/applied), each handed one `write(patch)` door (`actionStore` refuses a key the store lacks); `actions/during.js` is the `busy` span they all read, and `busy` covers everything an action writes including its learn tail |
| `sw.js` | the extension | every backend call, the frame fan-out, the one sanctioned injection, the hotkey, and giving the toolbar icon to the side panel |

## The gate

The content scripts are injected into every frame of every page, and on almost
every page on the web that is the whole of what they do: each module is an IIFE
that publishes functions, and `agent.js` registers one message listener. Nothing
detects on load, mounts anything, stores anything or sends anything. The one
other thing that runs at load is `inventory.js`'s capture listener for trusted
`input`/`change` events: it remembers WHICH element the user changed (a weak
reference, never a value) so the engine never overwrites it.

`detect.js` is the decision point and it answers only when asked — the panel
sends `detect_page` to frame 0 of the tab it is bound to, because a panel runs in
no page, and, when frame 0 has no form, to every frame (`page_broadcast`). An
application form can be an embedded cross-origin iframe (Greenhouse's embed on
block.xyz, inserted when the Apply tab opens), so a subframe's `form` counts —
at a stricter bar, score 3 or more, because an ad or offer iframe with identity
fields and an "Apply now" button can score 2. Only the offer reads that bar;
`frameMayReceiveUserData` still admits each frame by its own verdict. A subframe
of the bound tab that finishes loading (`webNavigation.onCompleted`) asks again,
debounced, while no form is known and nothing is running, at most five times
per page binding (a tab switch or Refresh starts over); Refresh covers it by
hand. A url change inside the bound tab (`tabs.onUpdated` with a url, which
an SPA's pushState also fires) rebinds at once, while an SPA still shows the
step being left, so after one the ladder runs every rung even over a yes and
re-reads the upload count on each: a Workday step change otherwise kept the
previous step's count, and the attach offer came one step late (CarMax). It reads,
scores and returns four keys: the tier, whether a form's evidence held, the
score behind it, and how many upload boxes a resume could go into (frame 0's
count only, so the attach offer is unchanged). It holds no state, registers no observer and touches nothing on the page.
Tier A is a JobPosting **verdict** (a page either declares one or it does not),
Tier B is form evidence over a threshold, the two do not combine into one number,
and an ATS host is worth zero points on its own. On a miss the panel offers
nothing and constructs no telemetry observation.

## The rail

Four stages — **Job → Resume → Fill → Track** — and the active one is
**inferred from the store** by `ns.decisions.stageFor` on every render, never set
by what was clicked. An action ends by re-running a load; "advance to Resume" is
not a sentence any of them can say. **Job asks two questions**: is the job
saved, and which base resume goes with it (Score merged into Job on
2026-09-27). It is done when the job is saved AND a base is chosen: picked by
you, or the ranking's scored best, preselected; an application bound to the page
answers with its own `base_resume`, and so does a base-as-is claim with the base
it armed. Three rules hold the shape up:

- **ONE row shows a body**: the active one, or a DONE row you reopened. Job,
  Resume and Fill are always reopenable: a done Job row opens onto the ranked
  base list, or, when the binding is your own pick (`claimed`), onto the
  switcher and the un-pick, never onto the Save job preview. Reopening is
  view state — never persisted, dropped when the stage moves or the page facts
  reset — and it rewinds no tick. In code the reopened row is `card.revisit`; a
  row skipped by a CLAIM (`choiceSkipped`: base as is' Resume row names the
  choice and carries its withdraw) reopens too, a skip the path computed does
  not, and the active row keeps its styling while another is open — and is
  itself a button then, the way back, which closes the reopened view. A base
  pick in a reopened Job row closes it too (`pickBase`): switching base from
  Resume leaves the stage on Resume, so nothing else would. A control that
  leaves with its body hands focus to that row's door (`withPlaceKept`).
- **A done row says what it settled** (`stageSummaries`): the chosen base and
  its score on Job ("AI/ML Engineer · 72"), which is what makes a preselected
  best an answer you can see rather than one made for you.
- **The footer holds exactly one primary**, and it follows the OPEN row: Save
  job (Update scores once the job is saved: the retry, and the re-run on
  a reopened row; none on a bound application's read-only Job row), Quick
  tailor, Autofill (withheld by
  `primaryRefused` on a page with no form; a late detect yes gives it back,
  moving no stage). Track has none: its way
  onward is the header's link, and its control is the permanent Draft/Applied
  segment.
- **Nothing is claimed that is not known.** `match !== "exact"` means "we do not
  know", not "none", so an unreachable backend opens the journey at Job rather
  than claiming the job exists. Skipping is not doing: arming a base resume skips
  Resume *visibly* — dashed, "Using your base resume as is.", never a
  tick, and never the word "Skipped" (it reads as declined, and it is the Agent
  inbox's word for a rejected job; a screen reader hears "not needed"). And `done.fill` is this extension's own claim that it filled or
  attached HERE, so an application marked applied inside the web app does not
  put a checkmark on a page the extension never wrote to.

Above the rail sits the panel's whole header, and it is one block: the job's
identity and the match chip ("Not saved yet" for a job Maestro CS does not
have, "Saved", or the application's status), the Base → Tailored ATS rings
under them (read from stored scores, never computed here; with one ring, "Base
resume score" and "Tailoring can raise it."; with none, "Not scored yet."), and
one deep link on the last line, right-aligned, with **Refresh** at that line's
left. The link is labelled by the most specific thing we know — "Open
application ↗", else "Open in Maestro CS ↗", and nothing at all until the
service worker has said where the web app is; its `aria-label` spells the
destination out in full, because beside a job title "Open application" would
otherwise read as the posting's own apply page. It stays off the title's line
because beside the chip it and the job title fight over one axis: at 400px — an
ordinary side-panel width — the title was left 104px and five wrapped lines.

**There is no brand row**, and its absence is a decision. Chrome draws a
side-panel title bar above this document carrying the extension's name, and it
cannot be removed or retitled — so it IS the panel's title, and a mark plus the
words "Maestro CS" underneath it would be the same name a second time, in the
scarcest 50 pixels a 400px-wide surface has.

The manifest `name` **stays "Maestro CS Companion"** rather than shortening to
match the app. "Companion" is the word that separates the extension from the app
in the one place both are named together: the web app's own consent copy reads
"Maestro CS Companion will fill race, ethnicity, gender, veteran and disability
questions…", and "Maestro CS will fill…" inside Maestro CS reads as the app
asking permission of itself.

## What the panel does

- **Save job** — the Job stage shows title, company and the grabbed job
  description in three fields you can correct before anything is saved (schema.org
  `JobPosting` JSON-LD when the site provides it, visible text otherwise). The
  line under them says "Job description found (N words)" only for a job signal
  (`source` `json-ld`, or `content`: a job-description container), because
  three filled boxes over an empty description otherwise looks exactly like a
  successful read; a long `<main>` (`page`) or the whole page (`body`) is only
  the page's text, still editable and saved as it is, and the line says "No job
  description found on this page"; when the page answers nothing at all it says the Companion
  can't read this page and to reload the tab, which is a claim about our reach
  rather than about the page. The backend extracts the JD immediately, so the job
  lands parsed and ready for ATS scoring, and a duplicate save says "Already
  saved in Maestro CS" rather than pretending it saved something new.
- **Refresh** — re-reads the backend's facts about this tab through a tab
  switch's own path (`bindPage`: reset, generation bump, `loadContext`), plus
  the drafts list and the base resumes, so a job or draft added in the web app
  or by a connected agent shows without leaving the tab. It keeps the work done
  on the page (`PAGE_WORK`: typed Job fields, the Fill report, typed answers,
  the drawer, a reopened row) and writes a pick down again first, so the pick
  survives. Only a real pick, claim or armed base is written: a bound
  application's own base is `baseFromApplication`, a backend fact re-read on
  every load and never saved as a pick. The attach and the drawer's answer show only beside the
  application they were made for (`sameApplication`), since the re-read can
  bind another. Disabled while any action runs, so it never interrupts a fill.
- **Pick a draft** — on a page nothing has matched, the Job stage asks
  "Applying for one of these?" over your recent draft applications and you name
  the one you are here about. It is an
  OFFER, never a guess — the pick is your claim about the page — so it does not
  require a form to be visible: Workday's wizard urls match no job, its JD is in
  the DOM of pages that carry no form yet, and the form verdict at bind time is
  false anyway on a late SPA render, so requiring a form would refuse exactly
  the flow the picker exists for.
- **The base resumes are RANKED by this job's own ATS scores**, best first, each
  row showing its number — the same per-base scores the Score and tailor tab is
  built on, so the choice (and the number Quick tailor reports afterwards) is not
  blind. **Saving the job scores the bases in the same press** (`addJob` then
  `scoreAllBases`, one `busy` span), and a saved job that no base has a score for
  is scored when its Job step opens, quietly (no red note, and never over a
  note already there) and once per panel and job (`autoScored`), so a failure
  never loops and a tab round trip never re-asks; Refresh asks again. The cost is the deterministic ATS engine, one local pass
  per base resume and no model call; the web app's Score and tailor tab spends
  it the same way on a first visit. Scores are otherwise READ (cheap, computes
  nothing). The base list is also where the panel says, once, what an ATS score
  is: the web app's `ATS_SCORE_LEAD` sentence, our estimate and not an
  employer's reading. A resume with no score says "not scored" rather than zero
  and sorts last, the scored best is preselected until you pick another, and a
  pick made by hand wins over the ranking permanently. For a saved job with no
  application the scores are a stage input, so `loadContext` reads them before
  the first render of the matched page (no Job-then-Resume flash). **Beside a
  bound application the reopened Job row is read-only**: one line, "Resume
  from Data Scientist · 64" (the application's own base), and the ranked list
  as information, with no pick and no change to the Before ring.
- **The Resume step is short, and keyed on what is true** (owner-approved copy,
  2026-09-27). With no application it asks one question: **Use my base resume**
  or **Tailor to this job**, with one muted line ("Base: your resume unchanged.
  Tailor: fit it to this job first."). Nothing is pre-selected. *Tailor to this
  job* discloses **Quick tailor** — the same function the footer's primary runs,
  one behaviour and one label — and **Tailor in Maestro CS ↗**, a real link to
  `/jobs/{id}?tab=fit` and never an API call (the panel has no business creating
  a gap analysis behind your back), with one line: "Quick tailor makes the PDF
  here. A PDF you make in Maestro CS shows up here when you select Refresh."
  (the second sentence only beside the link; the panel reads the backend on
  load and on Refresh, never on a timer). With an application and its PDF the
  step is simply done, its row reading "Resume ready · 77" (the application's
  score when stored); reopened, it offers one small **Tailor in Maestro CS ↗**
  link and no footer primary, because Quick tailor there would replace the
  draft unasked. **The panel never says "tailored" about an application's
  resume**: a track-this application holds the base unchanged, and the panel
  cannot tell the two apart.
- **An application with no PDF yet gets Create PDF, never Quick tailor.** Its
  resume is stored and only the PDF is missing, so Quick tailor would run a
  fresh tailor (the "asks to tailor again" report). The body says "This
  application's resume has no PDF yet." beside the same Tailor in Maestro CS
  link, and the footer's primary is **Create PDF** (`createPdf`: `POST
  /api/applications/{id}/render`, the web app's own endpoint, deterministic).
  Fill stays locked until the PDF exists: the rule that Resume is done only
  with a PDF is unchanged. *Use my base resume* shows off beside it
  (`aria-disabled`, so the keyboard reaches it), `aria-describedby` one
  sentence: "This job already has a draft application, so it uses that
  resume." (a backend match) or "You picked a draft for this page, so it uses
  that resume." (your own pick; Stop using this draft under Job is the way
  back to the base). `stageFor`'s shortcut needs no application, so armed
  beside one the claim would change nothing, and `useBaseAsIs` ignores it.
- **A page filled from the base never sends the rail back to Resume.** With
  an application bound and no PDF, `touched` and `baseArmed` together (track
  this's signature) make Resume skipped, never done, and the rail moves on to
  Track: armed, filled, then Track this stays at Track. `touched` alone is not
  enough — filling with one draft and switching to one with no PDF is Resume.
  The skipped row is still a door, onto Create PDF and Tailor in Maestro CS.
- **A limb locked while an action runs is `aria-disabled`, not `disabled`**, so
  the pressed control keeps focus across the rebuild its own busy causes.
- ***Use my base resume* asks the backend for nothing and arms a fill from
  your base resume, with no application at all.** It is the FIRST rung of `stageFor`, above
  the library ladder, because **filling a form is a question about the PAGE**
  while the Save job → tailor → fill flow is a question about the library.
  Conflating them leaves a user who armed a base resume with no way to fill the
  form in front of them.
- **Quick tailor** — `POST /api/jobs/{id}/quick-tailor` with the base resume you
  picked. The changes applied are rendered from the response and never recomputed
  here; the After ring comes from re-reading the stored scores rather than from
  the response's own comparison, so those numbers have one home. Every failure
  reads the same way, deliberately: a health gate and a session already in
  progress share one status code and one string field, so a heading per code
  would be a claim about which of them happened. A render that fails after the
  tailor committed is not an error path — the application exists either way, and
  is remembered, or the next page of the wizard would offer to tailor a job that
  already has one; the step then offers Create PDF.
- **Autofill, "Saved answers + AI"** — the fill loop (`shared/fill-loop.js`),
  reported in groups by what happened to each field, with **Stop** in the footer
  while it runs. A tab switch or a same-tab url change also ends a run, as it does
  the rule pass's: the panel half by the generation check, the page half by
  `fill_cancel` to the tab being left.
- **Autofill, "Saved answers only"** — the Fill stage runs the hybrid pipeline on this page: the
  profile rule pass, then one batched `/api/autofill/choose` call for everything
  the rules did not cover (chunked at 40 fields), then the sequenced writer. The
  AI pass's prompt carries your saved answers and your career history; the EEO
  answers go only under the standing consent, through the one gate
  (`eeo_consent.withhold_unconsented` in `backend/app/services/eeo_consent.py`)
  that `GET /api/autofill/context` goes through as well, so which path asks
  never decides what is disclosed. The panel now runs this pipeline rules only
  (`/choose` skipped; the AI half described here is no longer reached from the
  panel and goes when the loop replaces this pass). The mode segment picks the
  run — **Saved answers + AI**, the loop above, is the default because it
  answers more of the form — and the choice lives in
  `chrome.storage.sync` under `fillMode`, so it follows the profile. Identity
  fields a rule tried and could not land are **retryables**: they re-enter the
  writer with the profile's own value, in memory only, and are never offered to
  the model, so their values are the one thing that stays out of `/choose`.
  `/choose` answers `matched`, `abstained` or — on the Jev engine only, for a
  factual field whose value the page has no exact option for — `closest`: the
  runner WRITES a closest answer like a matched one and hands it back as
  `closest`, and the Fill body lists those under **Closest matches to check**
  (written fields, never open ones; a closest write that did not stick is
  residue instead). A finished fill ticks the step and hides that list, so its
  note names each pick instead ("Fill finished. Check the closest match before
  you submit: major (Information Systems)."). Nothing is submitted and no wizard step is advanced for you.
- **The progress rows are the report, and every number is the fill's own** —
  `14 filled · 2 corrected · 3 already filled · 1 not accepted` for the profile
  pass, written-versus-still-open for the application questions, and one row for
  voluntary disclosures. **Already filled** is the fields that turned out to need
  nothing, usually because you filled this page before; they are counted so a
  re-run on a wizard step reads `0 filled · 12 already filled` — the truth —
  instead of a bare "0 filled", which reads as a pass that failed. The three
  sources are gated independently because they arrive independently: gating the
  whole report on the residue erases filled fields and prints "Couldn't reach
  this page" about a page the panel just wrote into.
- **"Fields that still need you"** — whatever the chooser abstained on, what
  did not stick, and the essays, each named as the page wrote it (the
  collector's `text`; its `label` is lowercased for matching). The note counts
  them beside every BLANK field the collect did not take (the collector's
  `blank`: rule territory left empty, a consent box, a text box with no
  question in its label), so it reads "9 fields are blank and 1 needs your
  answer" rather than one number over nine empty boxes. A `/choose` failure
  still degrades to this list, and the Fill body now says why under the
  questions row: "AI help is off until you add an API key …" for a missing
  key (the runner's `aiFailure`, read with `failureNote`'s key matching). Click a row to scroll that control into view (the message
  carries a qid and nothing else, which is what makes it safe to broadcast to
  every frame). Where the panel can actually write the answer — text, textarea,
  `select`, `radio`, and never a policy-blocked label — the row carries an inline
  box: type it, press, and **Remember this answer** is on by default, because the
  whole point of pausing once is not pausing again. A retryable arrives prefilled
  with the value the rule already knew, and offers no learn checkbox. A learned
  answer lands in a TYPED profile key when the fill rules have a declared home for
  that question and in the `custom` Q&A list otherwise — never in `qa_entries`,
  which is application-scoped and never read back into a later fill, so an answer
  saved there would pause again on the next application.
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
  every frame refuses if its list no longer says the same thing — otherwise a
  Workday step that reveals a cover-letter uploader between the detect and the
  press puts the resume in both. The count reported afterwards is the engine's
  readback: a box counts when its input still holds the file, OR when the page's
  own file row appeared — Workday uploads the file and empties `input.files` in
  the same tick, so `files` alone reported "No upload box took the file" over a
  page where it worked. The row must be NEW (more on-screen elements naming the
  file than before the write, so an earlier upload of the same name proves
  nothing), inside that input's own widget (at most three levels up, never an
  ancestor holding another file input or any other field, never the whole
  document), with no new error words (a live region's text included) and no new
  on-screen alert or invalid-marked element with text in the widget, no error
  words in the row itself, and still there a beat later; the page gets up to 3 s
  to show it. A row shown mid-upload that fails later still counts, which is why
  the panel says "Check the upload before you submit." A detached input counts
  only by that row. A zero on the same boxes is hedged — "Couldn't confirm the
  upload. Check the upload box, and attach your resume only if it isn't
  listed." — because a page can take the file without either proof, and a
  second press there is a second copy. There is no second press.
- **Mark applied** — the Draft/Applied segment lives in the footer permanently,
  so there is no nudge to hunt for. It is withheld for a status outside that pair,
  because pressing Draft on an `interviewing` application would silently walk the
  record backwards past three states. It is the one PATCH this extension makes,
  and it is **never automatic in either direction** (there is no applied-detection
  watcher): `applied_at` is stamped by the backend on entry to applied and
  consumed by the analytics series as a fact about the past, so a false positive
  silently corrupts a record while a false negative costs one click. The Track
  body renders no second status control — two Draft/Applied pairs on one screen
  are two writers for one field — and shows the evidence instead: the PDF that
  was rendered and the day it went out, or no line at all when neither.
- **The armed application survives the next page load**, and so does a finished
  fill. An ATS application is a multi-step wizard and every step is a page load.
  The choice is remembered for 30 minutes, in `chrome.storage.local`, scoped to
  the origin **and the tenant** — origin alone cannot scope it, because
  multi-tenant boards put thousands of companies on one origin, and a pick
  restored onto another tenant's posting offers an application that does not
  belong to the page. A cross-tenant entry is trusted only when the backend
  matched this page to the very job the entry names, and a backend that
  recognises a *different* job discards the memory rather than offering it.
  `done.fill` rides the same entry, which is why reopening the ticked Fill row is
  how you reach Autofill again on page three of a form the extension has
  already finished once.

## Rules the code depends on

Extracted from SYSTEM.md §7 (which still owns the panel's shape); these are the
mechanics a reader of `sw.js`, `content/agent.js` and the fill engine has to
know, and each one was learned from a live failure.

- **Sender model.** A panel has no `sender.tab` (that is the discriminator) and
  NAMES its bound tab, so sw.js's `sender.id !== chrome.runtime.id` is the WHOLE
  of provenance for a tab-less sender; `detect_page` joins `extract_job_posting`
  as a frame-0 read because the panel runs in no page. Content scripts are the
  fill engine and the field work and NOTHING else since R-C deleted the floating
  card, so `fanoutTab`'s content-script branch is a written rule with no caller.
- **The COMMIT GESTURE.** `visitControl`/`leaveControl` (plus the
  `guided`-prefixed and injected copies) wrap everything that is not a text
  commit, because a `<select>` set through the native setter and a radio driven
  by `click()` fire no focus events, so Workday's required-field validation
  never ran.
- **ONE definition of "a box a résumé could go into".** `agent.js`'s
  `attachableFileInputs` is read by `attachResumePdf` AND by `detect_page`'s
  `fileInputs` count, which is what lets the panel offer an attach it can honour.
- **Posting identity is one table in two languages.** `shared/decisions.js`
  `postingId` mirrors the backend's `job_url_match.posting_id` (query keys
  `currentJobId`, `jk`, `vjk`, `gh_jid`; LinkedIn's `/jobs/view/<id>` path). The
  tenant scope, the backend match and `agent.js`'s stale-JSON-LD guard all read
  it; `backend/tests/test_extension_posting_identity.py` pins the two copies.
- **A failed round trip never prints the server's own text.**
  `actions/during.js`' `failureNote` writes the call site's "Couldn't <what>." and then a next step
  chosen by `err.status` and the key: no status means no answer came back, so
  check that Maestro CS is running; a missing key ("Add an API key in Maestro CS
  under Settings › AI & models.") and a refused one or any 502 ("Check your API
  key …") are told apart by `MISSING_KEY`/`REFUSED_KEY`, the web app's own
  patterns (`frontend/lib/error-text.ts`, pinned equal); any other status gets
  the call site's own sentence, else "Try again."
  The raw message goes to the console. A run with no saved answers leads its
  note with "No saved answers yet …", and `sw.js`' `attach_pdf` puts the status
  on its error the way `api()` does, so a failed PDF fetch reads as the backend
  answering rather than as an app that is not running.

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
  cancels is reported as "not accepted", never as filled. (Agreement boxes under
  the standing agreement consent follow the same look-first rule; see below.)
- **EEO/voluntary disclosure fields are off by default**, and the answer is the
  BACKEND's standing consent (`/api/settings/eeo-consent`, read off
  `/api/autofill/context`) — you grant it in Profile in the web app, and this
  extension offers no toggle that could turn it on. While it is off, those fields
  are seen and skipped and the Fill stage's Diversity questions row says
  "turned off in Profile › Autofill", so the silence does not read as a fill
  that missed a whole section. While it is on,
  writes are **exact or nothing**: a control that already carries an answer is
  never written over (a "decline to self-identify" is a real answer), and an
  option is chosen only by an exact normalized match or by a curated word list.
  The generic fuzzy scorer used for ordinary fields is deliberately not used
  here — it rated "Asian Indian" 72.5% against "Asian".
  **Gender** has five stored answers (`content/eeo.js`): male, female,
  non_binary, self_describe and decline. Non-binary matches only an option that
  says non-binary (its spellings included); a form offering only "Gender
  non-conforming" is left for the user, never answered with a stand-in; a
  radio is judged on its own words, never
  its legend's; a single-choice checkbox is never ticked for the two
  unanchored answers. A value without a list (a hand-edited "Woman") is
  matched exactly or not at all: it used to borrow the decline words. The
  self-description (`gender_self_describe`) goes only into a text box that
  asks for one ("please specify", "self-describe"), which no other answer
  may take; a "Please self-describe" box naming no question is EEO territory
  that nothing fills and `/choose` never sees.
- **Repeated blocks (education, work history) are resolved by block, not by
  DOM order.** Each repeated block's position among the **visible** blocks of
  its family picks the resume entry, so a hidden prototype block does not shift
  every later entry. DOM order survives only as the fallback for pages that
  publish no block identity at all.
- **Entries are added only for what the profile can fill.** A repeating
  section (Work Experience, Education, Languages, Websites) grows only by
  its own Add, and on Workday an added entry's fields are REQUIRED, so an
  entry nothing can fill blocks the page. Before anything is mapped, the fill loop reads
  each section's heading and entry count (`fill_sections`), and the backend
  (`/api/autofill/sections`, headings and counts in, kinds, counts and
  profile entry numbers out)
  names the profile list it holds and how many profile entries have every
  fact an entry requires: a job its employer and title, a school its name,
  a language its name and its read, speak and write levels (Workday
  requires all three), a website its address (the LinkedIn box is not a
  section; certifications have no profile facts yet, so none is added).
  Add is pressed for the difference and never beyond it, one section per list.
  Entries already on the page count, whatever they hold, and one holding an
  answer keeps it. A press is a deliberate write, not a trial: once per
  wanted entry, on the view it was decided from (a changed heading or count
  presses nothing), never after Stop, and counted only when the entry count
  grew; a press that added nothing is not repeated in that run. The
  section's own Add is the only control pressed: never one inside an entry,
  a submit, a control inside a link, the page's header or footer, or
  anything whose words, name or automation id say delete, remove or trash
  (a button with no type counts outside a form; inside one it would submit).
  Entries are PLACED before anything is added: an entry already holding data
  is matched to the profile job, school or language it holds (on the
  employer, and the title when two jobs share an employer, the school, or
  the language, ignoring case and punctuation, and for an employer its
  company suffix such as Inc, LLC, Ltd, Corp, Co and GmbH); empty entries,
  then added ones, take the profile entries no entry holds, in order. /map
  is told each field's place (`profile_entry`) and writes that profile
  entry's facts there, whatever order the page's entries are in — so
  an empty entry above a pre-filled job #1 gets job #2, never job #1 again,
  and a job the resume parser dropped is added in its own place. An entry
  holding something the profile does not have may be a profile job spelled
  another way, so its whole section is left to you: nothing placed, nothing
  added, and the report says so. Two entries holding the same one add
  nothing. When two sections read as one job, school or language list (a
  "Volunteer Experience" misread above the real Work Experience), which one
  is misread cannot be told, so neither is placed and neither grows: both
  are left to you, and the report says so for each, naming the other
  ("this section looks like the same kind of list as "Work Experience"").
  /sections says so itself
  (`ambiguous_kind`, every entry placed nowhere), and the Companion checks
  again across frames and rounds: a section that appears after its kind was
  placed in an earlier round is left to you too, and what was done in the
  first stands. Sections of other kinds are unaffected. An entry fact of another kind than its
  section's is never written there (a language's answers only inside a
  placed Languages entry, and its name never as a closest match), and a
  section whose order cannot be read, or whose entry titles do not run 1,
  2, 3… down the page (the backend places entries by their place, the
  Companion finds an entry by its title's number), is left to you rather than filled in page order. A
  section the backend could not place at all (the ask failed or was slow,
  its heading was read as no profile list) is filled in page order only
  while every entry is empty; if one holds data the section is left to you.
  Each of these says so in the report, and a section left to you still
  counts as its kind's one section: a second section read as the same kind
  never gets an Add. An added entry never takes a profile
  entry missing a fact it requires (a school with no name): it is skipped,
  and the next complete one is added. What the entries hold goes to the
  local backend for
  that match only, never to a model. Within one section the page
  listed, a fact is written into one entry only: a website that one entry
  was given, or already holds in a text box, is left for you in another. A
  numbered title that is not such a section ("Question 2", "Step 2") is not
  an entry, and none of this applies there. A section is known by its
  frame and heading: its kind and count are asked once per run (a failed or
  slow ask means nothing is added this run), and a press that added
  nothing is not repeated even when the page re-renders the section. A
  section without a labelled group runs from its heading to the next
  heading of its level or higher, so two such sections can share one
  container. Sections inside a shadow root are not seen (the search is the
  document's own), so nothing is added there. The Fill report names every section still short
  of what your profile can fill ("Work Experience: 1 of 2 added. Add the
  rest yourself.") and keeps the step open.
- **Without the standing agreement permission, signatures, initials,
  passwords and government IDs** (SSN, passport, licence numbers) are refused by
  label (`NEVER_FILLED` in `shared/policy.js`). A `type="password"` input is
  refused on its TYPE as well, at every setting, so that protection does not
  depend on its label reading like a password. The panel's pause rows consult
  the same deny list (with no permission argument, so always refusing) rather
  than trusting that collection already refused it.
- **An application's own agreement boxes** — "Yes, I have read and consent to
  the terms and conditions", acknowledgements, attestations, arbitration and
  waiver boxes (`CONSENT_FORMS`) — are also refused without that permission.
  **With it** (an explicit `consentForms: true`) `isPolicyBlocked` refuses NO
  label: every field above, agreement boxes and salary history become fillable
  (owner's decision, 2026-09-26: it is your application and your recorded,
  revocable consent). Next / Save and Continue and Submit are never clicked at
  any setting. It is a switch you give in Profile beside the EEO opt-in: two
  switches, because opting into EEO fill must not also opt you into agreeing to
  terms. A box is looked at before it is clicked, never re-ticked, and a
  cancelled click is "not accepted", not agreed. Only callers that pass the
  permission get it: `fillFormFromProfile` and the fill loop's inventory; the
  old engine's model path (`collectOpenQuestions`) and the pause rows never do.
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
  not true, change it by hand before filling. For an application whose
  company your work history lists, the backend derives "previously employed
  here" — "Yes, currently" when that job is current, else "Yes, previously",
  so a pick between "Current Associate" and "Former Associate" has the words
  to choose by — and drops the standing answer for that application (company
  names match the way section entries do, ignoring case, punctuation, a
  leading "The" and suffixes such as Inc or Ltd — otherwise exactly, so
  "Amazon" in the history against a job at "Amazon Web Services" derives
  nothing and the standing answer stays); it only ever derives Yes,
  and while it stands the low-stakes scope below loses "previously employed
  by the company (No)" and names it as never. The one exception
  to "never guessed" is yours to switch on: with low-stakes answers on
  (below), a "previously employed by" or "related to an employee" question no
  answer covers is answered No.
- **Salary history is refused without the agreement permission.**
  Current/present/previous salary, last drawn salary, current CTC, salary
  history, wage history, compensation history, and an unqualified
  salary/wage/compensation label are blocked by the shared policy. Explicit expectations such as expected, desired, target, or salary
  range may fill `preferences.desired_salary`; an expectation phrase never
  overrides another policy block such as signature, consent, terms, credentials,
  or government-ID wording. With the permission, "salary requirements" and
  "compensation" questions fill from the same fact.
- **The phone and street address say which boxes they never answer.** /map
  offers them as "the whole number; never a phone extension, a fax number, a
  country calling code or a phone type" and "street address, line 1 (never a
  second address line, an apartment, suite or unit, or a county)" — no label
  rule decides it. Offered as "personal: phone" and "personal: address", Fill
  typed the phone number into Workday's "Phone Extension" and "Country Phone
  Code" and line 1 into "Address Line 2", and verification passed them
  (2026-09-27). `backend/scripts/fill_map_cases.json` holds these labels for
  the evaluation.
- **Some answers are derived, never stored.** The backend adds facts computed
  from the profile (`derived.*`, described to the model as derived): your
  full legal name (first and last, for name and signature boxes), today's
  date (the browser's, so an evening in the US is not already tomorrow),
  whether you are a US citizen (from the work-authorization status: a
  citizen is Yes, a green card or any visa No, no status nothing), whether
  you will need visa sponsorship now or in the future — the wording most
  forms use — (Yes when your now or your later answer is Yes, No only when
  both are No), and —
  when your earliest start date says immediately or ASAP — that date as
  today, for a date box. Each is absent when what it comes from is.
- **A Yes or No is picked by what the question asks, in three steps.** A
  reversed or negated question ("are you authorized to work WITHOUT
  sponsorship?", "are you under 18?") maps to the same slot on /map as the
  plain one; the answer flips later, and never in one model call (asked
  to judge, flip and pick at once, both engines answered knockout
  questions backwards). For a fact whose answer is itself a Yes or a No
  (`Fact.yes_no`, however it was stored: "yes", "TRUE" and "y" are a Yes,
  a veteran or disability answer reads "No, I am not…"):
  1. **Polarity** (`autofill_polarity`): the model judges only whether
     the question asks the SAME thing as the fact's value-free
     description (an undirected label — "Protected veteran status", "Age
     requirement" — counts as same, unless its words negate or reverse
     the fact: "Unrestricted work authorization (no sponsorship
     required)" is opposite), the OPPOSITE (a reverse or a negation), or
     neither (it asks about something else). The
     value is not sent, and every Yes/No description is a proposition
     with a direction ("has a disability", "is a protected veteran",
     never "disability status"). Jev first, over code-owned keys, at the
     slot's floor but never under 0.8 (exact 0.9; a preference is not
     flipped at its 0.5). A confident Jev "neither" leaves the field
     yours; where Jev is unsure (under the floor, or no readable answer),
     ONE fast second opinion at the same floor. Its call is capped at
     2 s and ends by 2 s into the request, so Jev's pick (2 s), the
     pick's second opinion and the reasoning call (a second each) still
     start before 6 s. On the fast engine, or when the Jev call fails,
     the fast model decides. Still unsure: the field is yours. Which
     engine decided is logged. A confident answer is remembered in the
     backend for 10 minutes (at most 500, by question, description and
     policy: page text, never a value), so a /step after a /pick, or the
     next run on the form, does not ask again; an unsure one never is, so
     a /step may ask again and give up (within the same 2 s cap).
  2. **Code flips**: same keeps the value; opposite turns a plain Yes
     into No and No into Yes. A wordy value ("No, I do not have a
     disability", "Yes, previously") is never rewritten, so an opposite
     question about one is yours.
  3. **A literal pick**: "the applicant's answer to this question is
     Yes: which option states that answer?" After a flip it carries no
     fact description, so nothing can flip it back. A same answer that
     is a plain Yes or No also says what it is about, in the
     description's words ("No; that is, for the applicant, "will need
     visa sponsorship in the future" is not true"), so an undirected
     label over statement options can be read; nothing was flipped
     there. /pick's Jev pick, its fast fallback and
     its second opinion all ask that; /step names the answer in its goal
     and decides the polarity itself (unsure, it gives up).
  Any other fact is picked against its description and value, and the
  question says a status, list or name value is never turned into a Yes
  or No, so "do you require sponsorship?" mapped to an "F-1 OPT" status
  stays yours. No other value travels: a description names the question,
  never an answer.
- **Which engine decides.** On the Jev engine (Settings › AI & models ›
  Form filling), /map, /pick and /step ask Jev first. The fast model
  decides a request's fields in two cases, always at the same floors:
  when the Jev call fails, and as ONE second opinion per request for the
  fields Jev was unsure of. For /map, "unsure" means no readable answer,
  "no fact", or a fact under its slot's floor. For /pick it means a
  fact pick Jev abstained on; `exact` still refuses a near miss and a
  flag slot's nearest option is still `closest`. For /step it means a
  slot field whose move Jev gave up on or chose under its floor. The
  second opinion is sent the same data as Jev and the same question:
  labels and fact descriptions for /map; for /pick and /step the slot's
  own value with its description (a Yes/No fact: only its computed
  answer, asked which option states it), the options or moves, and the
  job (its /pick prompt carries the low-stakes paragraph only when
  the batch holds a low-stakes field, which a second opinion never does).
  It is one call, with no retries, on what is left of the request's one
  `Budget`, and never longer than 4 s (`SECOND_OPINION_MAX_S`). The fast
  engine's own map, pick and step (and Jev's failure fallback) are one call
  of what is left of the 9 s too, asked once more after a malformed reply
  or a transient failure only while at least 2 s are left (never for a
  missing or refused key). Where an
  optional pass may follow (/map's low-stakes and reasoning passes,
  /pick's reasoning call), it also ends a second before the 6 s after
  which no optional pass starts, so the next optional pass still has time
  to start. Only the next one: with low-stakes on and a slow second
  opinion, the low-stakes pass can use the time the reasoning pass needed,
  and that pass is skipped (its fields stay yours). A give-up
  step therefore costs at most Jev's 2 s plus 4 s against the field's
  clock. Out of time or failed, Jev's none stands. Jev's own protected,
  history, EEO and free-text answers are never asked again, and an entry
  field /sections placed nowhere is never asked at all. On /map the
  second opinion may decide only a fact (placed by the same
  `profile_entry` rule) or an EEO block, never a free-text answer. A field
  it names as anything but "no fact" never becomes a low-stakes guess, and
  never a reasoned one either, unless what it names is the history
  sentinel (a history question no fact answers), which keeps a reasoning
  candidate one. The low-stakes and reasoned routes keep their engines.
  Which engine decided is logged, not reported: no response or telemetry
  field carries an engine.
- **Two kinds of answer are the Companion's own**, both listed under
  "Answered for you: check each one" (`assumed`). Both are for a CHOICE only
  (a list, radios, a dropdown: nothing is typed), and only when /map's answer
  was an explicit, confident "no fact of yours answers this" — a profile
  answer always wins. The model decides which kind a question is; there are
  no label rules.
  1. **Low-stakes** — off by default; the web app's "Answer low-stakes
     questions for me" in Profile › Autofill (`/api/settings/autofill-options`),
     re-read server-side by /map, /pick and /step, never trusted from the
     Companion. Answered the way an applicant keen on this job would: how you
     heard about the job or a referral source, preferred contact method,
     willingness or comfort (relocate, travel, on site, shifts, overtime, a
     drug test), openness to other roles, "related to or previously employed
     by the company" (No), "if you become employed by …" (in the job's
     favor), SMS, automated-call and marketing consents, and yes/no
     self-assessments against the job description ("do you have the required
     experience", "do you meet the educational requirement"). Never: factual
     education or experience questions, work authorization, sponsorship, age
     or eligibility facts, EEO, background or criminal history, security
     clearance, salary, legal attestations and signatures. Both lists are
     `_LOW_STAKES` / `_NEVER_LOW_STAKES` (`backend/app/services/autofill_map.py`),
     stated in every question; a field the map named a protected, EEO or
     history question is never a candidate. The pick needs 0.4.
  2. **Reasoned** (`reasoned`, at every setting) — a choice the work and
     education history answers: "employed by a US government agency in the
     last five years", "do you hold a US security clearance", "years of
     experience with X". Only a field the map called "no fact" or a HISTORY
     question no fact answers (its own sentinel, `history_unanswered`: past
     employment by a KIND of organization, a clearance, years of experience)
     is a candidate — never a protected question (work authorization, sponsorship,
     age or eligibility, background), an EEO one, or a fact below its floor,
     so the history can never answer sponsorship or age. Whether you worked
     for, or are related to someone at, the company applied to is on the
     reasoning never-list (that is the derived fact above, or yours), and a
     reasoned field that NAMES the company applied to — in its question or
     any option ("Former Associate of The Home Depot") — is refused before
     any model sees it; a generic wording ("the company", "us") is held back
     by the never-list alone, in the prompt. The fast model
     judges it answerable from a DESCRIPTION of the history (no values). Jev
     is not used for this route: /pick's answer needs the history as values,
     which Jev's state would then carry. /pick answers
     a batch's reasoned fields in ONE fast-model call given each job's
     employer, title, dates, current flag and description, each school's
     name, degree, major and years, and today's date — never a name, contact
     detail, address, job location, GPA, work-authorization or EEO answer. An
     answer counts only when it names an offered option, clears 0.85 and
     cites (`shown_by`) at least one job or school of the history, every one
     real. Silence is not No: a clearance the history never mentions is no
     answer. "Not employed by that kind of organization" is shown only by
     dated jobs over the period asked at clearly private companies. A
     NEGATIVE answer — an option reading as a refusal (No, None, Not, Never,
     N/A, Zero, Under, Less or Fewer than, "I have not", "Does not apply",
     "<"…), OR one the model marks `negative`, since either side may only
     withhold — speaks for a period, so the model also names its first month
     (`since`), and code takes it only when every job overlapping [start,
     today] (start: `since` or 12 months ago, whichever is earlier) is dated
     and cited, and the cited jobs reach back to that start (a 2024 job
     cannot speak for 2021): a skipped job, an undated one, or a history cut
     at the catalog's 8-job limit means no answer. A gap between listed jobs
     is taken as not employed then: the resume is treated as the complete
     record of its dated periods, and the answer is `assumed`, listed for you
     to check. /pick trusts the Companion's
     `reasoned` route as it trusts a low-stakes one — the classification is
     /map's, the setting and the answer are the server's. A reasoned field is
     never handed to the adaptive step (/step has no history): its abstain,
     or a list that showed no options, is yours; a surprise on commit is
     retried like a native list's.
  Both passes, like the second opinion above, are optional and bounded
  by the request's one `Budget` (`autofill_map`): once a request has spent 6 s
  (`OPTIONAL_PASS_BUDGET_S`), a pass not yet begun is skipped and its fields
  stay yours, and one that runs is a single request with no retries and a
  real timeout of what is left of 9 s (`REQUEST_BUDGET_S`), so /map,
  /pick and /step answer inside the Companion's 10 s wait. /pick makes its fact picks
  first and the reasoning call after, so a slow or failed reasoning call
  never costs them.
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
  the committed value, so a walk of only `input, select, textarea` leaves
  Country, State, Phone Device Type, the work-authorization questions, "How did
  you hear about us" and every voluntary-disclosure dropdown unfillable and
  emitting no telemetry. The rule pass's writer opens the popup, picks by the
  same scorer, and reads the BUTTON'S OWN TEXT back: a click the page cancelled
  is reported as a snap failure, never as filled (the fill loop reads the
  backing input instead — see "A fill is proven by what the app saved"). A
  button already showing an answer is left alone. The header's own menus
  (Settings, the account menu) carry `aria-haspopup` too and are excluded by
  their automation id. A list is open only while it is VISIBLE: an outside
  click hides Workday's list but leaves `aria-expanded="true"` on its button
  (and the list in the DOM), so that attribute is never read — a hidden list
  is not "closed" again, and the next press opens it.
- **A popup write stays inside its own control.** `[role="option"]` is
  document-wide, so an unscoped read collects every open popup on the page —
  and Workday marks a multiselect's already-chosen chips as options too, where
  the only thing a click can do is un-pick a committed value. Options come from
  the control's own `aria-controls` list where there is one; the fallback
  refuses chips. A popup's own "Select One" row — live Workday lists it as
  an option — is never offered as an answer: explore, a choose's surprise
  options, the adaptive step's options and click moves, and what the loop
  sends to /pick and /map all drop it, and an empty or dash-only row with it
  (only those rows: oids keep numbering the list as shown). Choosing it is
  the engine's own undo alone; explore remembers the row so that undo can
  still find it.
  Token inputs (Workday Skills) are typed one token at a time. Date controls
  receive only the part they asked for, in the format their own options use.
- **A search box is searched the way a person does it** (`fill-core`'s
  `search`, shared by explore, choose, a set's items and the adaptive step's
  `search:*` moves). Press the box and wait for its list (on Workday, typing
  into a closed box opens nothing, and an Enter sent before the list exists
  is lost; a box whose list opened on focus is not pressed shut); type the
  term over any query already there; press Enter (keydown and keyup —
  Workday searches on the key-up); then wait until the row TEXTS (not the
  nodes: Workday reuses its rows) have changed from what the list showed
  before the search and then held still for 500 ms — results arrive in
  stages. A list that never changes (School opens empty; a search may
  rightly answer with the default list) is taken only after 2.5 s, so a slow
  answer is never read as empty. A declared size (`aria-setsize`,
  `aria-rowcount`, every row in the DOM) only holds the wait longer while
  fewer rows are shown — never a shortcut. A list still changing, or still
  short of its declared size, when time runs out is not picked from by any
  caller: explore, choose and the search move report it `unsettled`. The
  same query typed again over the list the engine already settled for it is
  not searched again. The Enter is the search's own step, not the keyboard
  fallback: it goes to a Workday box always, to a combobox or autocomplete
  box only when its typing showed nothing new (a widget that filters as you
  type would take an Enter as a pick), and never to a plain text box, a
  button, anything inside a link, or a combobox naming a highlighted
  option (`aria-activedescendant`, where an Enter picks; Workday's Enter
  searches either way). An Enter that finds one hit may commit it on
  its own: the pills are read before anything is clicked (the answer:
  verified, unclicked; anything else: taken back, or — from an adaptive
  search move — left and named "Searching picked …", never filled). The
  click goes to the radio or checkbox inside the result row, once (a click
  on the row only highlights it; a tick is a toggle, redrawn a frame later,
  so it is never repeated), after the option is found again by its text; a
  row's own tick, not its `aria-selected` (Workday's keyboard highlight),
  says whether it is held. A long list is scrolled a page and a frame at a
  time (Workday keeps eight rows in the DOM); an adaptive click whose row the
  list redrew for another option on the way into view is `stale`, never
  clicked. Two options with the same text are one option — the first — only
  when they sit under the same visible category path; otherwise explore
  lists both, each with its path (`where`), and the adaptive step's click
  moves name each one's place (`Click the option "Other" (under "Job
  Board")`). A long list is read from its top, and its header rows are
  remembered by their place in the list, so an option whose header has
  scrolled out of a virtualized window still reads under it (one option,
  never two). The loop carries the picked option's path into its choose,
  which commits only an option under that path, scrolling the list the way
  explore read it — and only when the choose opens the view explore read:
  a search box explored without the term its choose types (its default
  list may group options under headers its search results lack), or rows
  explore found by one word of the term, carry no path. A set carries each
  item's path the same way. The text under no such path is `ambiguous`,
  nothing clicked. A header row is a visible non-option row with text. A choose by text alone reads a long list whole before it
  commits, so the same text under another category outside the window is
  `ambiguous` too. A set's items share one open list: each is
  typed over the last query, and the next waits for the last one's pill. A
  Workday box not yet known to take one answer or several is tried as a
  set; radio rows end it before any click. UNMEASURED: the 500 ms quiet
  period, the 300 ms a combobox's typing gets before it is sent the Enter,
  and the 2.5 s bound on an unchanged list come from the fixtures, not from
  live timings — the Task 13 live check measures them.
- **A split date is written whole before anything blurs out of it.** Workday
  renders a date as several `spinbutton` inputs inside one widget, and the
  widget validates when focus leaves the WIDGET, not the section — so blurring
  after the month, while the year is still empty, hands it a half-written date
  and it discards the month (the `MM/2006` / "Invalid Date" failure). Every
  section of a date is written first and the blur happens once, when the fill
  moves to a different date or reaches the end of the run. Measured on a live
  form, the same writes hold six sections across three dates with no error on
  the page. Trusted input is NOT what was missing — the identical untrusted
  write holds once the blur moves. The leave blurs whichever section holds
  focus by then (the widget moves focus back to Month after a full Year), not
  the section last typed in.
- **"I currently work here" is ticked before its entry's dates, and a commit
  that adds or removes fields is looked at before the next field.** Ticking
  it removes the entry's To date a frame later. The loop works a choice whose
  MAPPED SLOT is an entry's `.current` first (by the slot, never the label),
  then text and dates, then the other choices; the leads' picks are one
  call, the others' another. After any choice that changed the page (a
  commit, or a value an explore left) it peeks at the frames' fids
  (`fill_inventory` with `peek`: no field is read; one frame is waited first
  unless the tab is hidden); if a field came or went, a full inventory comes
  before the next field: one that went is dropped — never written after it
  went, and not reported — and one that came (an "Other, please specify"
  box) is mapped and filled in the same round. A free-text answer whose box
  a commit re-rendered is written to the new box next round. A typed value
  is not followed by a peek: text almost never reshapes a form, and a peek
  per field would cost a page pass each.
- **Entering and leaving a field are reported by hand when the browser will
  not.** While the Chrome window is not focused (you are looking at the panel
  or another window), `focus()`/`blur()` move focus but fire no events, so
  Workday never took a typed City or date even though the box showed it.
  `fillBase.enter`/`leave` send focus + focusin / blur + focusout themselves,
  only when the browser stayed silent, so the page hears each once — including
  the leave of the field focus came from. Salary slots compare as numbers only
  when both sides are a single amount (`$80,000` is 80000; a range, `80k` or
  two different currencies are not); like phone numbers, the slot decides
  that (/map says which, `format`), never the characters.
- **Every writer commits the way a human would.** A `<select>` set through the
  native setter and a radio driven by `click()` fire no focus events, so
  Workday's required-field validation never runs over answers the page is
  visibly holding. Everything that is not a plain text commit is wrapped in one
  visit/leave gesture.
- **A fill is proven by what the app saved, not by what the widget shows.**
  Each shape reports `evidence` (`content/shapes.js`): the display, and the
  proof where the page exposes it. A Workday popup shows a pick at once, but
  the app has it only when the hidden input beside the button (a direct
  sibling, the only one) holds a value (live, picks that showed later went
  back to "Select One" with that input still empty); a hidden input further
  out — an "Other" text box in the question's wrapper, a search box inside a
  closed menu — is never taken for it. A Workday search box's proof is its
  pills, read from the `multiselect` container around the input (the
  `selectinput` marker sits on the input itself, which holds no pills). A pick
  is verified when the display states it AND the proof holds something that
  moved since before the click (or the field already held that answer); a
  display over unmoved proof is `unconfirmed` — listed under **Filled but not
  confirmed**, never counted as filled, and never clicked a second time. A
  one-answer widget that already shows and holds the answer is not clicked at
  all. Choosing the placeholder is the engine's own undo (an opt-in no page
  action carries) and must empty the proof; a decision that names a
  placeholder is refused unclicked, and the loop never reports an empty or
  placeholder value as filled. The final sweep (after a quiet 600 ms) re-reads
  the proof, so a backing input that empties later is a reversion: a field the
  engine wrote gets ONE re-commit per run, and if it goes back again it is
  reported `unconfirmed` (unstable), never filled. One that reverted and was
  not re-committed — the rounds ran out, or its budget did — is `unconfirmed`
  too ("Companion filled … then the page took it back"), never "couldn't
  operate". A popup with no
  discoverable backing input is judged by its display alone, which is weaker.
  Whether a Workday search box takes one answer or several shows only in its
  open list — radio rows or checkbox rows, under the same container — so it is
  learnt from the first list the engine opens for it (or several pills, or
  `aria-multiselectable`); until then the inventory reports `multi: null`,
  its one pill reads as a list, the field is not "answered", and the loop
  explores a several-item fact's first item before choosing between one
  answer and a set (a box known to take one answer is not explored for it). A box whose rows turn out to
  be radios and that already holds a value is left as it stands (`already`),
  never overwritten — unless the engine itself wrote it earlier in the run (a
  re-render forgot what its rows said), which stays the engine's `verified`.
- **One controller per field.** The generic commit, the adaptive step and a
  re-commit are ways of proposing the field's next move to ONE controller, not
  separate executors: they share one budget (`FIELD_MS`, charged only while the
  field is worked, across rounds — a retry or a re-commit runs on what is left,
  never on a fresh clock), and a move that failed is never sent again for the
  same value from a state that looks the same — same options, same moves on
  offer (the model is told `already_failed` and chooses again; a lazy list
  that grew, or a set's next item, is a different state). **Exploring can
  commit** — a search that finds one hit picks it (live on Workday's Field of
  Study): the committed value is snapshot before an explore, and anything the
  explore added is taken back under an allowance of its own (`budgets.undo`,
  so a slow explore never eats it): a pill by its remove control, a popup's
  pick by choosing the placeholder with the engine's own undo. One it cannot
  take back leaves the field to the user, named ("Searching picked … and
  Companion couldn't take it back"). BLIND SPOT: a search box whose only
  display is its own input (a free-text autocomplete, no pill, no
  single-value node, no backing input) cannot have an explore commit noticed —
  that text is the query the engine typed and takes back, so it is not read
  as a commit. **A widget that ignores the engine** — an operation after
  which nothing moved: not the committed value, the open popups, the box's
  own value or its `aria-expanded` / `aria-activedescendant`, and no node
  changed in the field's box or was added to `<body>` (`no_effect`, judged on
  the page, with the KINDS of gesture tried). A press that did nothing at all
  on a button or combobox is followed by the keyboard: ArrowDown, then Enter
  only if ArrowDown changed nothing anywhere under `<body>` — never on a plain
  text box, a submit button or inside a link, and never after anything
  reacted, including an earlier press or keyboard open of the same control
  (an Enter would accept the row a role-less list highlighted). Pills and a popup's pick
  that an explore committed are taken back by fill-ops alone. A value the keys committed is taken back; one the page will
  not give back leaves the field to the user, named ("Opening the list
  picked …"). Only when two DIFFERENT kinds have had no effect since anything
  last did is the field `unsupported`, listed under Couldn't operate as
  "doesn't accept automated input": the Companion has no trusted input to try
  instead. The same press ignored twice is not enough, and a re-proposed move
  refused twice in a row as already failed ends the adaptive step. Typing
  counts per VALUE (insertText and its setter fallback are one gesture): a
  box that takes neither may be refusing that value — a type=number box given
  text refuses it every time — so the same value twice never counts twice,
  and such a box ends "couldn't operate" after its attempts, as before. A
  re-commit that ends anywhere but a fill — out of time, not committed, no
  answer — is reported as the page having taken the value back.
- **What worked is remembered, per kind of control, and only as an order.**
  The engine knows two moves on each of two axes: it opens a list with a
  press, or from the keyboard when a press did nothing (`open: press|keys`),
  and it follows a search's typing with an Enter, or waits for the widget's
  own filter (`search: enter|debounce`). The panel keeps a recipe book
  (`shared/recipe-book.js`, `chrome.storage.local` key `fill.recipes`) keyed,
  for a popup or search field only, by value-free hashes (`content/recipes.js`)
  of the widget's structure (its shape, tag and role, the names of its and its
  ancestors' automation ids up to the field box with GUIDs stripped, whether
  it names its list, the popup kind, one answer or several, the kind of
  committed evidence, the engine version) and of that family on this host.
  No label, value, option text or URL is in it, but it is not nothing: the
  site hash can be matched against public lists of employers' application
  hosts, so the book can show which employers' sites were used, and its day
  numbers and counts show roughly when each was last used and how often. A
  recipe only puts the move that worked FIRST: the other stays the fallback,
  and every gate still decides. The keys go only to a control the keyboard may
  reach, never after anything on it reacted, and the Enter only after an
  ArrowDown that changed nothing. A learned debounce only waits longer for the
  widget's filter (2.5 s rather than 0.3 s) before the Enter the gate allows,
  and never sends one it refuses. Verification, the field's one budget and its
  failed moves are unchanged. Clicking an option (its tick, once) and leaving a
  field (from inside its widget) have no fallback, so they are never
  reordered, and text boxes and passive choices (a signature, a consent tick)
  are never looked up. A move is learned only from a commit whose moves
  verified, that nothing reverted, and that the final sweep re-checked and
  found holding: a value the sweep found reverted teaches nothing, even one
  re-committed that then held (`adversarial_recipe_poison.html`). A value the
  final sweep could not re-check (its element gone) is never kept, though a
  revert or an unconfirmed commit seen earlier still counts against the move;
  a run whose final sweep reached no frame (the page went away) records
  nothing. The first such run puts the recipe on
  probation, tried on its own site only; a second run on that site trusts it;
  its family is tried on a new site only once two sites kept it. A
  contradiction (an unconfirmed commit, a revert, the other move winning)
  demotes it, and a learned move the control cannot take (the keys on a submit
  button) quarantines it: neither is tried again. The book holds 200 entries at
  most, the least recently kept going first, and an entry is gone after 60 days
  unused. **Forget learned widget moves**, at the foot of the Fill body while
  the book holds anything, removes the key. A store that fails costs the fill
  nothing. A recipe does not know whether a Workday search box takes one answer
  or several, so a box already holding one still gets its first item typed and
  taken back before it is left as it stands.
- Identity fields (name, email, phone) overwrite a wrong ATS prefill and are
  reported under "corrected"; identity **comboboxes** are fill-only-if-empty.
- Hidden clone fields are skipped, a write a controlled input rejected is
  reported as "not accepted" rather than as done, and a write whose readback
  could not be confirmed in budget is `filled_unverified` — never `not_stuck`,
  because "we could not see it land" is a different claim from "it did not".
- **Nothing is ever submitted automatically.** Always review before submitting.

## Telemetry — what leaves the page

On by default (`telemetryEnabled` in `chrome.storage.sync`, defaulted in
`sw.js` `DEFAULTS` and gated in its `telemetry` handler, which posts nothing when
the key is `false`). It is fire-and-forget: it can never surface an error to you
or delay a fill. **There is no UI switch for it** — the panel's only stored
preference is the fill mode — so turning it off means setting that key to
`false` (the user-facing one-liner is in [README.md](README.md#privacy-and-telemetry))
or flipping the default in `sw.js`. Removing the key does not turn it off: the
default comes back.

A batch only ever exists on a page you pointed the panel at: the fill engine is
the only thing that constructs an observation, and nothing runs it without your
click. This is the complete list of what is posted to
`POST /api/autofill/telemetry` — there is nothing else:

**Per batch**

| field | value |
|---|---|
| `page_host` | the hostname of the top frame (e.g. `boards.greenhouse.io`), capped at 255 chars |
| `action` | `profile_fill` (the rule pass, "Saved answers only"), `rest_fill` (its remainder pass) or `loop_fill` (the fill loop, "Saved answers + AI": one row per field it reported). The backend's frozen vocabulary is wider than what this extension now sends |
| `observations` | up to 200 of the rows below |

**Per observation** — exactly six keys, and the service worker drops everything
else before posting:

| field | value |
|---|---|
| `label` | the field's visible label text, capped at 160 chars |
| `kind` | the control shape: `text`, `textarea`, `select`, `radio`, `checkbox`, or `combobox` |
| `host` | the hostname of **the frame the field was in** — not the top frame, so an embedded Greenhouse form is attributed to `boards.greenhouse.io` (a `loop_fill` row: the first frame the loop found fields in) |
| `outcome` | what happened: `filled`, `corrected`, `filled_normalized`, `filled_unverified`, `not_stuck`, `combobox_snap_failed`, `no_rule`, `missing_source`, `skip_rule`, `skipped_checkbox`, `hidden`, `policy_blocked`, `eeo_disabled`, `retry_filled`, `match_recovered`, `ai_abstained`; on a `loop_fill` row the loop's report status: `verified`, `closest_filled`, `assumed_filled`, `partial`, `unconfirmed` (a value the page shows but never confirmed, or that reverted after its one re-commit), `needs_answer`, `cannot_operate`, `unsupported` (the control ignored every synthetic input), `prefilled`, `blocked`, `user_edited`, or `filled_unverified` for a value that landed without being chosen as the answer — a group click that committed one, a search that picked while exploring (`buildLoopObservations` in `shared/fill-loop.js`). (The backend also accepts `ai_answered`, `ai_no_stick`, `ai_unanswered` and `ai_unaligned` — stored rows carry them — but nothing emits one since the floating card was retired: its AI write-back path was their only source.) |
| `rule_id` | which fill rule matched, or null; on a `loop_fill` row the slot the AI mapped the question to (`slot:…`) or its route (`route:…`) |
| `options` | for a `select`, a `radio` group, or a Workday listbox-button dropdown whose popup was open at the time, **the option texts as the page renders them** — up to 30, each capped at 160 chars. This is the one field that carries page content, and it is here because a dropdown that could not be matched is unfixable without knowing what its options said. Nothing is ever opened in order to collect them: a telemetry read may not drive the page, so a closed popup reports no options rather than being poked into rendering. A `loop_fill` row carries none |

**What is never sent:** the value typed into any field, the value that was there
before, any AI answer text or value the fill loop chose, and the contents of any
other field on the page. A field that already held its answer is never written:
the rule pass sends no row for it, the loop sends one (`prefilled`) with the label
and nothing else. A loop row's label is sent blank when it contains the value the
loop wrote. The backend has
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

## Install internals

- **Settings have one home.** `DEFAULTS` in `sw.js` (`backendUrl`, `appUrl`,
  `telemetryEnabled`, `fillMode`, plus the legacy `eeoAutofillEnabled`, which
  fill decisions no longer read) is the one place a default lives; stored values
  in `chrome.storage.sync` override it. The panel asks for them over
  `read_settings` rather than keeping a copy, and there is no settings screen in
  the panel. The panel writes `fillMode` to `chrome.storage.sync` directly —
  writes need no defaults.
- **The shortcut needs Chrome 116**, where `chrome.sidePanel.open()` landed,
  while `minimum_chrome_version` is 114: everything else including the toolbar
  click works on 114, and raising the minimum would lock out a browser whose
  only missing piece is this one route. On 114–115 the hotkey logs a warning
  naming the toolbar icon rather than failing as a bare TypeError. Chrome
  silently drops a suggested key another extension already claimed; rebinding
  lives at `chrome://extensions/shortcuts`.
- **A tab that was already open when the extension reloaded has no content
  script**, because a content script only enters a page when that page loads —
  and every MV3 reload orphans the scripts in every open tab, which shows up as
  "No job description found on this page" over a visible JD, forever. The panel
  injects them (`panel_prepare`, `chrome.scripting`) on three routes and no
  others: Autofill and Attach resume, both user gestures, and once per page
  after a posting read has come back silent. In a tab that already HAS them
  (every Autofill does this) the files re-run in the same isolated world:
  the fill engine's modules and `agent.js`'s message listener load once
  (`ns.loadedOnce`), so the user's edits, a latched Stop and the verified-value
  memory survive and every message is still handled exactly once. Never speculatively on a load —
  injecting into a page nobody asked about is exactly the always-on cost the
  detection gate exists to avoid — so anywhere else the panel says it cannot see
  the page and to reload the tab, rather than claiming it had nothing on it.

### The pinned id and the CORS allowlist

`manifest.json` pins a `key`, so this extension hashes to the same id —
**`pjmfonfapjdabkoicnelpflpjojdjgan`** — on every machine that loads it, and
`app/config.py` defaults its CORS allowlist to exactly that
(`backend/tests/test_extension_manifest.py` derives the id from the key and
asserts it is in the default; README.md's install section carries it for users).
Chrome assigns an unpacked extension's id at install and keeps it, so Reload
picks up new code but never re-derives the id: an install that predates the
`key` keeps its old path-derived id indefinitely, the backend refuses it by
CORS, and the only symptom is a panel that cannot reach the backend. The fix is
Remove + Load unpacked.

The allowlist is **exact ids only** — never a `chrome-extension://.*` pattern,
which would let *any* installed extension read the whole career record out of
an API that has no authentication. Pinning the id keeps the one admitted id
known rather than whatever Chrome happened to generate. Set
`MAESTRO_CS_EXTENSION_IDS` only to admit a *different* build: a fork you
re-keyed, or a Web Store install (Google assigns that id and it will not match
this one). The variable **replaces** the default, so list every id you want,
comma-separated.

- The pinned key is a **public** key and identifies the extension; it is not a
  secret and is meant to be committed. The matching private key is not in this
  repo and is not needed to load, run or develop the extension.
- Because the id does not depend on the directory path, **moving your clone
  does not change it**, so the allowlist cannot silently break that way.

## Maintainer notes

- **Every fetch goes through the service worker**, because a content script's
  fetch presents the *page's* origin, which the backend's CORS list does not
  admit — and widening it to admit arbitrary ATS hosts is the trade this avoids.
  The panel is an extension page and *could* fetch directly; it routes through
  the same door anyway, so there is one fetch site and one place the backend URL
  is read. Nothing leaves the machine except the LLM calls the backend itself
  makes.
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
  entry, stranding a user mid-wizard; `restoreSession`'s `if (entry.applicationId)`
  guard is the condition of writing an application-less entry at all. Three orphan keys the floating card left
  behind (`widget.dock`, `widget.hiddenOrigins`, `widget.hiddenGlobally`) plus
  `panel.pick` are swept once on panel boot.
- The hotkey cannot close the panel: `chrome.sidePanel` has an `open` and no
  counterpart, so the close affordance is the browser's own.
