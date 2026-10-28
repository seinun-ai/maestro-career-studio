# Maestro CS Companion — internals

How the Chrome extension is built and the rules its code depends on, for
contributors and agents changing `extension/`. If you only want to install and
use it, read [README.md](README.md) instead. SYSTEM.md §7 and its reference file
`docs/agent-surfaces.md` own the panel's shape; this file owns the mechanics, and each rule here was learned from a live
failure.

## Surfaces and files

There is no popup or in-page widget. The **side panel** (`panel/`) captures and
fills; the toolbar icon (`openPanelOnActionClick`) and `Alt+Shift+J` open it,
bound to the current tab. **Extension options** edits the connection addresses.
Ordered content scripts read the page and fill fields; the service worker
proxies their API requests:

| file | runs | does |
|---|---|---|
| `shared/decisions.js` | every frame **and** the panel document | the pure decisions the panel renders from — `stageFor`, the base ranking, `reconcileFill`, the session guards, `sanitizeAnswer`, `describesJob` |
| `shared/choose.js` | every frame **and** the panel document | the pure half of the open-question path: routing, the ≤40 `/choose` batch, `rest_fill` shaping, and the one `QUESTIONY` |
| `shared/guided-run.js` | the panel document | the guided-fill runner: one sequencing/batching engine, transport injected |
| `shared/policy.js` | every frame **and** the panel document | the shared never-fill policy — read by the fill engine and by the panel's pause row, whose render AND action are the half that is easy to miss |
| `shared/receipt.js` | the panel document | the answer receipt builder: a run's report plus the post-run `fill_inventory` become the `POST /api/jobs/{id}/filled-answers` fields, each with its source pill; every same-labelled occurrence is kept, never-fill and unrun fields are not recorded, and it names no telemetry or trace channel (SYSTEM.md `{#inv-filled-answers-local}`); posted by `panel/actions/fill.js` `recordReceipt` through the generic `api` door |
| `shared/recipe-book.js` | the panel document | the recipe book: which of the engine's own moves worked per widget family, its lifecycle and bounds; the loop's `deps.recipes` |
| `shared/profile-fields.js` | every frame **and** the panel document | the label patterns naming a TYPED home in the autofill profile: one table read by the rule that FILLS the field and by the pause row that decides where an answer is LEARNED |
| `shared/status-roles.js` | the panel document | an application status's word and colour role (`ns.statusRoles`), the same table as the web `status-chip.tsx` (pinned by `test_extension_status_roles.py`); read by `matchChip` and the Track status segment; `panel.js` throws at boot naming it when the tag is missing |
| `shared/resume-color.js` | the panel document | a base resume's hue to the chroma its square is drawn with (`ns.resumeChroma`): the same ten presets and custom chroma as `frontend/lib/resume-color.ts` and the backend picker (pinned by `test_resume_color_parity.py`); `panel.js` `swatch(hue)` draws the square (`.swatch` in `panel.css`, tones `--cs-resume-*` copied from the app and pinned by `test_extension_status_roles.py`) and throws at boot naming this file when the tag is missing |
| `content/field-reader.js` | every frame | the new fill engine's one answer to "what is this field asking" (label-for → … → nearby → preceding: the visible text right before the field, when nothing names it — never a radio's or checkbox's, and only text that passes the label test: short, no sentence, no error, no heading before it, no other text or trailing label beside it), with its source. `readField(container)` runs it too, so a nameless group container or date wrapper can take its question from it; `ns.precedingLabel` is also a group's question with no container. A label that names only a part ("Month", "Day", "Year", "Type", "Number") is prefixed with its group's question, and a control holding one part of a date says which (`part`). **A written question is the label whole:** a non-choice field takes preceding text that ends in "?" and is at most 200 characters (`MAX_QUESTION`) even when it is a sentence of more than twelve words, and its star marks the field required; the short-label test still governs everything else and every choice field |
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
| `content/touch-notice.js` | every frame | tells the panel THAT you changed a field: one throttled (2 s) `fields_touched` message of fids only, sent only where the frame gate (`ns.frameMayReceiveUserData`) says yes; engine writes never trigger it |
| `content/detect.js` | every frame, every page | the detection read — reads, scores, returns |
| `shared/ats-buttons.js` | every frame | a short table of navigation buttons an ATS names by its own markers (only recorded ones: Workday's footer button, whose own text decides); it never says "next", and the text sort still wins over any verdict |
| `shared/ats-hosts.js` | every frame **and** the panel document | the ONE list of known applicant-tracking hosts, anchored at a dot: `content/detect.js` names the vendor from it, and the queued run types the saved job-site password only on a host listed here |
| `shared/page-kind.js` | every frame **and** the panel document | the pure page-kind classifier and the Next / Submit / unclear button sort (any Submit word wins; a page it cannot sort is the review page) |
| `shared/queue-run.js` | the panel document | the queued run's driver for ONE job in ONE tab: a pure state machine over injected deps, never clicks Submit; see "Queued run" |
| `content/page-reader.js` | every frame | the queued run's eyes and hand: `summary()` (counts, button texts, booleans, never a value) for `shared/page-kind.js`, and `advance(id)`, the only navigation click in the extension — it re-sorts the button's current labels and refuses any Submit-worded one |
| `content/agent.js` | every frame | page RPC front door, extraction wrapper, resume attach |
| `panel/panel.{html,css,js}` | the side panel | the store, the loaders, the generation guard, the render loop, the tab binding; sends everything through the service worker |
| `panel/icons.js` | the side panel | `ns.icon(name, {size, label})`: inline Lucide svg built with `createElementNS` (never `innerHTML`), `aria-hidden` unless labelled, `data-icon` names it; one glyph per concept as in the web app's `lib/concept-icons.ts`; no emoji or text glyph in panel code (`test_extension_panel_icons.py`); `panel.js` throws at boot when it is missing, and stage bodies reach it as `build.icon` |
| `panel/stages/*.js` + `panel/stages.js` | the side panel | one file per rail stage — a body is handed a per-render snapshot (`stageContext`), never the store, and `card` is never published — gathered by a roster that throws when a script tag is missing |
| `panel/runs.js` | the side panel | draws a run's record into the Fill row's Next card (running, Needs you, Ready to submit, Marking applied, finished) and holds the park words with their Resume / Skip rules; reaches for nothing, and has no Submit control |
| `panel/actions/*.js` + `panel/actions.js` | the side panel | one file per concern (save job and score its bases, Apply, the run's host `run.js`, pick a draft, quick tailor + base as is, fill this form, submit one pause-row answer, ask one question, mark draft/applied), each handed one `write(patch)` door (`actionStore` refuses a key the store lacks); `actions/during.js` is the `busy` span they all read, and `busy` covers everything an action writes including its learn tail |
| `sw.js` | the extension | panel/content API calls, frame fan-out, sanctioned injection, hotkey, and toolbar-to-panel binding |
| `options.html`, `options.js` | extension options | load `read_settings`, validate and save `backendUrl`/`appUrl` to `storage.sync`; Test connection fetches `/health` directly, with no new permission (`test_extension_options.py`) |

## The gate

The content scripts are injected into every frame of every page, and on almost
every page on the web that is the whole of what they do: each module is an IIFE
that publishes functions, and `agent.js` registers one message listener. Nothing
detects on load, mounts anything, stores anything or sends anything. The one
other thing that runs at load is `inventory.js`'s capture listener for trusted
`input`/`change` events: it remembers WHICH element the user changed (a weak
reference, never a value) so the engine never overwrites it. That listener has
one hook out, `ns.onFieldTouched(fid)`, which `touch-notice.js` turns into the
only message a content script ever sends on its own (see "The answer receipt").

`detect.js` is the decision point and it answers only when asked — the panel
sends `detect_page` to frame 0 of the tab it is bound to, because a panel runs in
no page, and, when frame 0 has no form, to every frame (`page_broadcast`). An
application form can be a subframe, so a subframe's `form` counts. One on the
tab's own site (`decisions.sameSite`, on the frame url `broadcastToFrames`
attaches) is the page itself and counts at frame 0's bar, score 2: iCIMS
renders its candidate profile in a same-origin iframe (`#icims_content_iframe`).
One from another site (Greenhouse's embed on block.xyz, inserted when the Apply
tab opens) counts only at a stricter bar, score 3 or more, because an ad or
offer iframe with identity fields and an "Apply now" button can score 2. Only
the offer reads that bar; `frameMayReceiveUserData` still admits each frame by
its own verdict (score 2), so every frame the offer counts is one the fill can
reach. A subframe
of the bound tab that finishes loading (`webNavigation.onCompleted`) asks again,
debounced, while no form is known and nothing is running, at most five times
per page binding (a tab switch or Refresh starts over); Refresh covers it by
hand. A url change inside the bound tab (`tabs.onUpdated` with a url, which
an SPA's pushState also fires) rebinds at once, while an SPA still shows the
step being left, so after one that first count is not shown (zero until the
ladder's first rung answers) and the ladder runs every rung even over a yes,
re-reading the count on each: a Workday step change otherwise kept the
previous step's count, and the attach offer came one step late (seen on a live Workday tenant). It reads,
scores and returns seven keys: the tier, whether a form's evidence held, the
score behind it, how many upload boxes a resume could go into (frame 0's
count only, so the attach offer is unchanged), per box its kind and whether it
holds a file, the frame's own origin, and a capped count of fillable fields
(search boxes excluded). It holds no state, registers no observer and touches nothing on the page.

**An application under way.** The later steps of a multi-step ATS (iCIMS's
Candidate Questions and EEO, a review page) are a few selects and a Submit, and
score 0. So once a form is confirmed in a tab, the panel remembers its frame's
origin and the employer it was confirmed under, the top page's origin plus
first path segment (`flowScope`), because Greenhouse, Lever and Ashby serve
every employer from one host. It is kept in `chrome.storage.session` for an
hour from the last step found. While the tab stays on that employer, a later
page with a frame on that exact origin and at least one fillable field is the
form, and every gated page message carries the origin (`withFlowOrigin`), which
`frameMayReceiveUserData` reads to admit a subframe on exactly it. That is what
lets iCIMS's own iframe take the fill on those steps. A form frame 0 answers
never replaces a live flow's origin, since the top frame needs no vouch. Every
other frame keeps its own verdict. When the ladder's read of a step reached by
navigating inside the tab finds the form, after the first step filled (the
rail at Track), the Fill row opens by itself, as a view: no tick moves, and the
first read after the url change (the step being left) never opens it.
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
you, or the ranking's scored best, preselected (with full automation On only on a clear win, by "Choose the base resume for me": Queued run, "The switches"); an application bound to the page
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
- **The paint is direction C; the model above is unchanged.** A `#progress` region over the rail
  draws four segments and "Step N of 4 · Name" from the ACTIVE row (a reopened row never moves it;
  segments before the active one read done by position, the rows keep their own ticks). The active
  row is painted as a "Next" card (the eyebrow is CSS `::before`, so the row's text is still "1 Job"),
  done and skipped rows as compact lines, and locked rows are hidden by CSS but stay in the DOM, so
  every test and the keyboard model see the same four rows. `backend/scripts/panel_preview.py`
  serves the real panel with a stubbed `chrome.*` to look at each state in a normal browser.
- **Nothing is claimed that is not known.** `match !== "exact"` means "we do not
  know", not "none", so an unreachable backend opens the journey at Job rather
  than claiming the job exists. Skipping is not doing: arming a base resume skips
  Resume *visibly* — dashed, "Using your base resume as is.", never a
  tick, and never the word "Skipped" (it reads as declined, and it is the Agent
  inbox's word for a rejected job; the row says "Not needed" in visible words with a minus). And `done.fill` is this extension's own claim that it filled or
  attached HERE, so an application marked applied inside the web app does not
  put a checkmark on a page the extension never wrote to.

Above the rail sits the panel's whole header, and it is one block: the job's
identity and the match chip ("Not saved yet" for a job Maestro CS does not
have, "Saved", or the application's status), the Base → Tailored match score rings
under them (read from stored scores, never computed here; with one ring, "Base
resume score" and "Tailoring can raise it."; with none, "Not scored yet."). The
company and the chip share one muted line under the title. **Refresh** (`rotate-cw`)
and the one deep link (`external-link`) are 32px icon buttons at the title row's
right (`id-tools`); each keeps its words in a visually hidden `span.vh`, so
`textContent` and screen readers read "Refresh" / "Open application" / "Open in
Maestro CS". The link is labelled by the most specific thing we know, and is
absent until the service worker has said where the web app is; its `aria-label`
spells the destination out in full and adds "(opens in a new tab)", because beside
a job title "Open application" would otherwise read as the posting's own apply
page. As text, the link once left the title 104px and five wrapped lines at 400px,
which is why it lived on its own line; as two icons the title keeps about 222px at
320px.

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
  `JobPosting` JSON-LD when the site provides it, visible text otherwise). Visible text
  is read in this order, each candidate only if it is on screen (a hidden duplicate
  never answers): a job-description container; the section under a description
  heading (an element whose whole text is "Job Description", "About the role" and the
  like, climbed to its first ancestor over 300 characters, abandoned at `main`,
  `article`, `body`, `form`, page-level `nav`/`header`/`footer` (a header or footer inside
  a section or article is the section's own), an ancestor holding a form
  control, an ARIA text widget or site chrome, or one holding the same heading twice,
  which is a list of cards; the first heading in document order that gives a section
  answers, and a label or legend is never a heading; the heading's length is measured on
  its normalised text, so an icon and indented markup around it do not disqualify it;
  the list is narrow on purpose, with "Description & Requirements" / "and" and "Job
  Description & Qualifications" in it and never a bare "Description", "Responsibilities"
  or "Requirements", which a product page or a blog post also carries; an `article`
  beside another `article` is one card of a posting drawn as cards and does not stop
  the climb, unless a sibling repeats the heading, which makes them a list);
  then `main`/`article`, then the body. A described page also gets the JSON-LD path's
  `Title:` / `Company:` / `Location:` lines (`postingHeaderLines`, `content/job-posting.js`):
  from the recorded Darwinbox adapter (host `darwinbox.in`/`.com`, path
  `/ms/candidatev2/<x>/careers/jobDetails/<id>`; DOM only: the header's `span.title`,
  the visible Job Snapshot "Location", the company only from the meta description
  "Job Title | <Company>" and not when that holds a translation key), else the first
  visible `h1` outside `nav`/`header`/`footer` for the title (the first such `h2`, a banner, when the page
  has no shown `h1` outside site chrome, as when its only `h1` is the logo's), only when the document title
  or `og:title` contains its text and it is not `og:site_name`, not the last segment of a `Title | Site` title, and not a
  generic banner word (a hero or a "Careers" banner is no title). Darwinbox is not in
  `shared/ats-hosts.js`: its Apply leads to a CAPTCHA'd sign-in, so the run stays out of
  its forms. The
  line under them says "Job description found (N words)" only for a job signal
  (`decisions.describesJob`: `source` `json-ld`, or `content`, a job-description
  container or the section under a description heading), because three filled boxes over an empty description otherwise
  looks exactly like a successful read; a long `<main>` (`page`) or the whole
  page (`body`) is only the page's text, and the line says "No job description
  found on this page"; when the page answers nothing at all it says the Companion
  can't read this page and to reload the tab, which is a claim about our reach
  rather than about the page. **The posting is read from frame 0 first, then
  from every frame** (`askPosting`, `page_broadcast`) when frame 0's answer is
  not a job description: iCIMS serves the careers site's chrome in the top
  document and the posting in a same-origin iframe (`#icims_content_iframe`). A
  subframe's answer is taken only when it is a job description from the tab's
  own site (`decisions.sameSite`: the registrable domain, approximated as the
  host's last two labels, on the frame url `broadcastToFrames` attaches), the
  richest by `landPosting`'s order (provenance, then size); a vendor's
  "similar jobs" widget or an ad frame never supplies it. The first read, every
  retry rung and the reload heal all go through it. A `content` answer is the
  container's (or heading section's) own text, never a longer `<main>` around it,
  which can carry a form's values shown as text. **Save job refuses a blank
  job**: with no title, no job description and nothing typed into the preview
  it posts nothing and says "The Companion couldn't read this job's description
  from the page. Open the job post on its own page, or add the job in Maestro
  CS." The backend
  extracts the JD immediately, so the job lands parsed and ready for ATS
  scoring, and a duplicate save says "Already saved in Maestro CS" rather than
  pretending it saved something new. A job the scorer cannot read yet (422: no
  skills, or no description read) gets "…Open the job in Maestro CS and choose
  Refresh details.", since Refresh details is the web app's control.
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
- **The base resumes are RANKED by this job's own match scores**, best first, each
  row showing its number — the same per-base scores the job page's Resume and
  gaps step is built on, so the choice (and the number Quick tailor reports afterwards) is not
  blind. **Saving the job scores the bases in the same press** (`addJob` then
  `scoreAllBases`, one `busy` span), and a saved job that no base has a score for
  is scored when its Job step opens, quietly (no red note, and never over a
  note already there) and once per panel and job (`autoScored`), so a failure
  never loops and a tab round trip never re-asks; Refresh asks again. The cost is the deterministic ATS engine, one local pass
  per base resume and no model call; the web app spends it the same way when a
  job is saved (every base is scored at save; its Resume and gaps step runs it on
  a first visit only for a job no base has a score for). Scores are otherwise READ (cheap, computes
  nothing). The base list is also where the panel says, once, what a match score
  is: the web app's `ATS_SCORE_LEAD` sentence, a fixed-rules comparison with the
  job description. A resume with no score says "not scored" rather than zero
  and sorts last, the scored best is preselected until you pick another (with full automation On, only on a clear win, or never if the switch is Off), and a
  pick made by hand wins over the ranking permanently. **Bases that were not scored for this job are not listed**: once any base is scored, the list
  shows the scored ones plus the selected one even if it is unscored (`shownBases`; the rest are other-country or off-target bases the scorer
  skipped), with no way to reveal them; with nothing scored (scoring running or failed) every base shows so the pick stays possible. For a saved job with no
  application the scores are a stage input, so `loadContext` reads them before
  the first render of the matched page (no Job-then-Resume flash). **Beside a
  bound application the reopened Job row is read-only**: one line, "Resume
  from Data Scientist · 64" (the application's own base), and the ranked list
  as information, with no pick and no change to the Before ring.
  **A base resume is never named without its square** (identity, never state: the
  stored `color_hue`, drawn by `swatch(hue)` before the name): each base row,
  "Resume from …", "Using … as is" and the Before ring's label wear it; the rings
  stay blue and a one-line summary (`stageSummaries`) stays text. The words stay
  the node's own text and the square is its child, which CSS puts first.
- **The Resume step is short, and keyed on what is true** (owner-approved copy,
  2026-09-27). With no application it asks one question: **Use my base resume**
  or **Tailor to this job**, with one muted line ("Base: your resume unchanged.
  Tailor: fit it to this job first."). Nothing is pre-selected. *Tailor to this
  job* discloses **Quick tailor** — the same function the footer's primary runs,
  one behaviour and one label — and **Tailor in Maestro CS** (with the `external-link` icon), a real link to
  `/jobs/{id}?tab=fit` and never an API call (the panel has no business creating
  a gap analysis behind your back), with one line: "Quick tailor makes the PDF
  here. A PDF you make in Maestro CS shows up here when you select Refresh."
  (the second sentence only beside the link; the panel reads the backend on
  load and on Refresh, never on a timer). With an application and its PDF the
  step is simply done, its row reading "Resume ready · 77" (the application's
  score when stored); reopened, it offers one small **Tailor in Maestro CS**
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
  you submit: major (Information Systems)."). Autofill submits nothing and advances no wizard step; only a run you start with Apply presses Next (see Queued run).
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
  composer with that question. **Under a queued run's card** the drawer
  appears only while the run is paused (`ns.panelRuns.working` false: parked, ready or stopped), with the stable toggle id `qna-toggle` so focus survives a
  repaint; while the run works one line ("Ask opens when the run pauses.") sits in its place, because a page turn wipes the box's draft and a repaint moves
  the caret. The answer is deliberately **not** written into
  the page: an essay is the one thing on an application a person should read
  before it is submitted in their name. Grounding is the most specific thing we
  hold — the application, else the job plus your chosen base resume, else
  nothing, in which case the panel says so rather than sending a body the route
  would refuse.
- **Attach resume** — the tailored PDF into this page's own upload box.
  **Always a press, never a load**: an upload is a whole document going to an
  employer. Autofill is the other press that attaches (below); this button
  covers every case it leaves alone. Three states off the page's
  own count of boxes a resume could go into: one box is the offer, naming the
  file; none is nothing at all (and so is a page whose one box is for another
  document or the site's own import, `otherBox`, from `uploads[0].kind`: the offer is a dead button that says the box is for another document, or, for the import box, that it fills in the form from a resume); **more
  than one is a sentence and a dead button**, because the panel cannot always tell
  a resume box from a cover-letter box and the page would look like it worked.
  The write itself skips every box the page's words rule out: it writes each
  attachable box except a parser (the site's own fill-from-resume), one for
  another document and one whose read threw, and the offer says so. The offer's own count travels with the write and
  every frame refuses if its list no longer says the same thing — otherwise a
  Workday step that reveals a cover-letter uploader between the detect and the
  press puts the resume in both. The count reported afterwards is the engine's
  readback: a box counts when its input still holds the file, OR when the page's
  own file row appeared — Workday uploads the file and empties `input.files` in
  the same tick, so `files` alone reported "No upload box took the file" over a
  page where it worked. The row must be NEW (more on-screen elements naming the
  file than before the write, so an earlier upload of the same name proves
  nothing), inside that input's own widget (never an ancestor holding another
  file input or any other field, never the whole document), with no new error
  words (a live region's text included) and no new on-screen alert or
  invalid-marked element with text in the widget, no error words in the row
  itself, and still there a beat later; the page gets up to 3 s to show it.
  **The upload proof** (`ns.uploadProof`, `content/detect.js`, a re-run file
  because `agent.js` has a size cap; `agent.js` reads it where it is used, never
  at load, so a re-injection of `agent.js` alone still loads): `chain(input)` is
  the input's upload ancestors, nearest first, up to six levels, stopping below
  an ancestor that holds another file input or another field, `<body>`, `<html>`
  or a `<form>`; the widget is the highest of the first three, as before, and
  `levels` watches it and every level above it (with the rows, errors and
  progress each showed BEFORE the write). `seen` reads the DEEPEST watched level
  still in the page: an uploader that replaces its whole button container, input
  included, with the file's chip (Greenhouse) leaves the group around it, and the
  chip is the row. All levels gone: no row. The name counts shown whole, as its
  stem (no extension, six characters or more), or shortened by an ellipsis
  ("Jane_Doe_Re…esume.pdf"): the head starts the name, the tail ends it, the tail
  must reach past the extension into the name (at least two characters of it before ".pdf"; a stem's tail,
  three), head and tail together at least eight characters and shorter than the
  name, so another file's chip or a bare "….pdf" proves nothing; every such
  mention is cut out before error words are read, so a file called
  `error-log.pdf` is not its own failure. A widget that shows PROGRESS (a new
  `aria-busy` mark, progress bar, or the words uploading, parsing, processing,
  scanning, analyzing, counted against what it showed before the write, so
  standing help is not news) gets longer than 3 s, up to 12 s
  (`ATTACH_PROGRESS_WAIT_MS`): a parser that prints the name when it is done
  (a parser-style uploader). A latched Stop ends that extra wait. A row shown mid-upload
  that fails later still counts, which is why the panel says "Check the upload
  before you submit." A detached input counts only by that row. A zero on the
  same boxes is hedged — "Couldn't confirm the upload. Check the upload box, and
  attach your resume only if it isn't listed." — because a page can take the
  file without either proof, and a second press there is a second copy. There is
  no second press. **Hedged, or "boxes changed"**: the panel (`panel/actions/
  fill.js`) says "Couldn't attach your resume. The page's upload boxes changed…"
  only when the count of boxes now differs from the one believed (the offer's
  `expect`, or the last detect's when the write named a box, which states none)
  AND the fall is not explained by the boxes the write reached: every frame
  reports `written` (`reportWritten`, always set by `sw.js`), and a fall of up
  to that many boxes (an uploader that swapped its own box for the chip) is the
  upload taking the file, so it reads "Couldn't confirm". With no count to change
  from, the page cannot be said to have changed; a page that GREW a box is still
  a change.
- **Autofill attaches the resume too** (owner, 2026-09-30), in both fill
  modes (the file is the user's own, not an AI answer), once per run, AFTER
  the fields and inside the run's `busy` span. "Saved answers + AI" attaches
  through the loop's `beforeSweep` hook, before its final sweep: Lever and
  Ashby parse an upload into the form's fields, and Workday re-renders the
  upload section, so the sweep re-reads every field the engine verified and a
  changed one gets its one re-commit per run (a page that takes it back again
  is reported unconfirmed, never filled). A written file makes the hook ask
  for a 3 s settle before that sweep (the parse lands 1-3 s after the file
  row), within the run's clock; a later parse is not seen. When a Stop or the
  clock skips that sweep, the note says "Check the filled fields, since the
  page may have changed them." rather than demoting each verified field,
  since nothing seen changed. "Saved answers only" attaches last. Never after a Stop, a tab change or the run's
  clock running out; Stop and the tab are asked again right before the write,
  after the PDF read. Narrower than the button: the button's own
  source only (the application's tailored PDF; a base used as is has none, so
  nothing is attached and nothing said), a fresh detect, exactly one box
  reading as a resume box, holding no file, and only that box is written
  (beside a cover-letter box, as on Greenhouse, the resume box alone). A box
  already listing a file is left ("A file is already attached; the Companion
  left it."), a cover-letter or other document box is never attached, boxes
  that cannot be told apart are left to the button, and nothing is tried twice
  on one page (not after an attach here, nor after one it could not confirm).
  The write re-checks all of it in each frame (`resumeOnly`, beside `expect`)
  and answers `{written, proven}`; its proof is stricter than the button's: a
  hidden input in an upload widget counts only by the page's own new row, and
  a held `files` proves a bare or visible input (its own control shows it).
  Outcomes: attached; written and not proven (the hedged "Couldn't confirm the
  upload…", which blocks another automatic try on the page), including a
  reply lost after the send (a frame error other than "no receiving end", or
  the channel failing with no HTTP status); nothing written (a refusal at
  write time, no PDF, no frame: "The Companion left the upload box for you.",
  which blocks nothing); or skipped with its reason. The run's note ends with
  it, the Fill body carries it as its own row (`autoAttach`, stamped with the
  application the attach used) with the button still under it, reading
  "Attach anyway" over a box that already holds a file.
- **Mark applied** — the Draft/Applied segment lives in the footer permanently,
  so there is no nudge to hunt for. It is withheld for a status outside that pair,
  because pressing Draft on an `interviewing` application would silently walk the
  record backwards past three states. It is the one status PATCH this extension makes,
  and it is **never automatic outside a run**: there is no applied-detection watcher on an ordinary
  page. `applied_at` is stamped by the backend on entry to applied and
  consumed by the analytics series as a fact about the past, so a false positive
  silently corrupts a record while a false negative costs one click. The one automatic
  path is a run's own tab: a confirmation page seen after a Ready to submit (the user pressed Submit) is
  recorded through `companion-submitted` after an 8 s Undo (Queued run). The Track
  body renders no second status control — two Draft/Applied pairs on one screen
  are two writers for one field — and shows the evidence instead: the PDF that
  was rendered and the day it went out, or no line at all when neither.
- **The armed application survives the next page load**, and so does a finished
  fill. An ATS application is a multi-step wizard and every step is a page load.
  The choice is remembered **per tab, for as long as the tab is open**: a map in
  `chrome.storage.session` (`widget.sessions`, tab id to entry), deleted by
  `chrome.tabs.onRemoved` and cleared when Chrome closes. There is no clock — the
  old single key with a 30-minute life made a long wizard forget its job and let
  a second tab's pick overwrite the first. An entry is scoped to the origin **and
  the tenant** — origin alone cannot scope it, because
  multi-tenant boards put thousands of companies on one origin, and a pick
  restored onto another tenant's posting offers an application that does not
  belong to the page. A cross-tenant entry is trusted only when the backend
  matched this page to the very job the entry names, and a backend that
  recognises a *different* job discards the memory rather than offering it.
  With no clock, a **sibling posting** of the same employer opened later in the
  same tab would inherit the pick, so the entry also keeps the address it was
  made on (`link`: origin and path, no query) and `restorableSession` refuses a
  page that `samePosting` calls a sibling (the backend naming the entry's own job
  outranks it). The rule compares paths from the root: a page above or below the
  link is the same posting; paths that part at a segment that is id-like on both
  sides (digits, a UUID) are two postings; parting at a name or a short step
  counter (`applyManually` to `review`, `step10` to `step11`) is a wizard walking
  and keeps the pick. Siblings whose slugs carry no id, letter-only ids and short
  codes are not caught, which is what the pick did before the guard.
  The map is shared by every window's panel, so each read-edit-write holds the
  Web Lock `maestro.widget.sessions`; a panel's boot also drops entries whose tab
  no longer exists (a tab closed while no panel was open never fired
  `onRemoved`, and `tabs.onReplaced`, a prerender swap, orphans an entry the same
  way until that sweep). `chrome.storage.session` is wiped when the extension is
  updated or reloaded, so a mid-wizard auto-update loses the pick and the user
  picks again. The old `chrome.storage.local` key `widget.session` is read
  once per boot until a later release deletes the migration, adopted by the
  active tab if it is under 30 minutes old and on that tab's site, and removed.
  `done.fill` rides the same entry, which is why reopening the ticked Fill row is
  how you reach Autofill again on page three of a form the extension has
  already finished once. **A run's job is handed to this memory as its record
  leaves the tab** (`closeRun`'s `keptBinding`, the `run.keep` door): while a run
  holds the tab its record is the binding (`bindFromRun`) and nothing is written
  here, so Done on a review page the backend does not match used to leave "Not
  saved yet". A record that reached Ready knows its employer (`tenant`); when the
  tab still shows that employer, Done writes the entry a pick on this page would
  (application, job, base, `pdfReady`, `touched`), so the rail lands on Track
  with Draft/Applied. A tab browsed on to another employer gets nothing.

## Rules the code depends on

Extracted from SYSTEM.md §7 (now `docs/agent-surfaces.md`, which still owns the panel's shape); these are the
mechanics a reader of `sw.js`, `content/agent.js` and the fill engine has to
know, and each one was learned from a live failure.

- **Sender model.** A panel has no `sender.tab` (that is the discriminator) and
  NAMES its bound tab, so sw.js's `sender.id !== chrome.runtime.id` is the WHOLE
  of provenance for a tab-less sender; `detect_page` joins `extract_job_posting`
  as a frame-0 read because the panel runs in no page, and both are also
  broadcastable, asked of every frame only when frame 0 has no answer. A frame
  that does not answer one of these two reads is logged at debug level, not
  warned: they run on most pages, and a warning lands in chrome://extensions →
  Errors. Content scripts are the fill engine and the field work and NOTHING
  else: `fanoutTab` refuses any sender that carries a tab, so no content script
  can route a message to a tab (its one message, `fields_touched`, has no SW
  handler; the panel hears it directly).
- **The COMMIT GESTURE.** `visitControl`/`leaveControl` (plus the
  `guided`-prefixed and twin copies) wrap everything that is not a text
  commit, because a `<select>` set through the native setter and a radio driven
  by `click()` fire no focus events, so Workday's required-field validation
  never ran.
- **ONE definition of "a box a résumé could go into".** `agent.js`'s
  `attachableFileInputs` is read by `attachResumePdf` AND by `detect_page`'s
  `fileInputs` count, which is what lets the panel offer an attach it can honour.
- **What a box is FOR is a narrow rule on its own words**, `agent.js`'s
  `uploadBoxOf`, not the fill's AI mapping: the inventory skips file inputs and
  a file slot is not a profile fact. `kind` is `resume`, `other`, `parser` or
  `unknown`. **The nearest NAME decides.** Levels, nearest first: the box's own
  label (field reader question, the NAME OUTSIDE ITS WIDGET (below), aria labels
  on it and its uploader, name, id, automation id), then the uploader's text,
  then its section heading; a word for another document (cover letter,
  transcript, "additional"...) beats "resume"/"CV" at the same level, and words
  end at letters and digits, not `\b` (which ends at an accent: "Résumé"). The
  section heading is the uploader's own, h2-h6 inside its form, never the page's
  h1 ("Computer Vision (CV) Engineer" names no box), found by a CLIMB of up to 10
  levels (`SECTION_CLIMB`: Workday seats it seven wrappers above the box), where
  past the 6th (`NEAR_CLIMB`) the climb also stops at an ancestor holding another
  field or file input, whose heading is no longer this box's alone.
  **A PARSER box is never written, by any press.** It is the site's own "fill
  this form from my resume": its words are an action on the file ("Import
  Resume", "Autofill from resume", "Apply with resume", `PARSER_WORDS`), the
  resume noun its object ("Import from Dropbox" is a file source). The nearest
  name decides here too: a section heading that plainly names a resume upload
  outranks its button's "Import Resume" (the button beside the input is the
  UPLOADER's word, not the box's), and a parser-worded section never overrides a
  box that names a plain resume. A **combined** box ("Resume (we'll use it to
  fill your profile)", `COMBINED_WORDS`) is the resume box when it is the page's
  only one, and a parser only beside a separate resume box (`readBoxes`).
  **The vendor's own markers beat the words** (`BOX_MARKS`, found through shadow roots): a box inside an easy-apply container (`oc-easy-apply`,
  `[data-test="easy-apply-container"]`, the vendor's "fill this from your resume" import) is a `parser` and never written; one inside `oc-resume-upload` /
  `[data-test="resume-upload-container"]` is the `resume` box. Upload reading (`attachableFileInputs`, the widget climb, section heading, label ids, `occupied`)
  uses `ns.deep` too, with the section heading found in composed document order and a file row drawn inside a shadow root proving a file through composed text
  (`rowsNaming`, `hasFile`: a row is in no `textContent`).
  **The outside name:** a react-dropzone's hidden input reads nothing but the
  uploader's "Click to upload", while its name ("Resume *") is a sibling of the
  WIDGET; `outsideName` reads the text before the widget (a stray file name is
  never a label), its star as `required`. A required box that is the page's only
  upload and whose words name no document is the resume's.
  **Demotion among several boxes** (`readBoxes`): of several resume-looking
  boxes, only those whose section names a resume upload stay `resume` and the
  rest become `unknown` ("Candidate Info" beside "Resume Upload"); with no such
  section all stay and the callers' "exactly one" rule refuses.
  `occupied` is files in the input, a file row in the uploader (a filename,
  brackets and all: "Resume (1).pdf", or `file-upload-item`), or a remove,
  delete or replace control in it; help text listing types ("(.pdf, .docx)")
  is not a file. `detect_page` returns one `{kind, occupied}` per counted box
  (`uploads`): a word and a boolean; `page_uploads` adds `required` and the
  page's own label, and reports `required` for a parser too, so a required
  parser box parks the run naming it.
- **Posting identity is one table in two languages.** `shared/decisions.js`
  `postingId` mirrors the backend's `job_url_match.posting_id` (query keys
  `currentJobId`, `jk`, `vjk`, `gh_jid`; LinkedIn's `/jobs/view/<id>` path). The
  tenant scope, the backend match and `agent.js`'s stale-JSON-LD guard all read
  it; `backend/tests/test_extension_posting_identity.py` pins the two copies.
- **A failed round trip never prints the server's own text.**
  `actions/during.js`' `failureNote` writes the call site's "Couldn't <what>." and then a next step
  chosen by `err.status` and the key: no status means no answer came back, so
  check that Maestro CS is running; a missing key ("Add an API key in Maestro CS
  under Settings › Basics.") and a refused one or any 502 ("Check your API
  key …") are told apart by `MISSING_KEY`/`REFUSED_KEY`, the web app's own
  patterns (`frontend/lib/error-text.ts`, pinned equal); any other status gets
  the call site's own sentence, else "Try again."
  The raw message goes to the console unless the call site's `answered`
  function recognised the refusal (Chrome lists an extension page's warnings
  under chrome://extensions → Errors, where an expected refusal reads as a
  fault); the automatic on-open score logs nothing. A run with no saved answers leads its
  note with "No saved answers yet …", and `sw.js`' `attach_pdf` puts the status
  on its error the way `api()` does, so a failed PDF fetch reads as the backend
  answering rather than as an app that is not running. The runner's own sentences are marked
  `guidedRun.shown`, so a thrown sentence reaches the note as written.

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
  "turned off in Profile › Diversity questions" (the fold that holds the switch),
  so the silence does not read as a fill that missed a whole section. While it is on,
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
  is matched to the profile job, school, language or website it holds (on the
  employer, and the title when two jobs share an employer, the school, the
  language, or the URL, ignoring case and punctuation, for an employer its
  company suffix such as Inc, LLC, Ltd, Corp, Co and GmbH, and for a URL its
  scheme, `www.`, trailing slash and #fragment); a Websites entry's profile
  entries are your website, then your GitHub, whichever you have (an entry
  holding your own LinkedIn, as a parsed resume often leaves one, is yours
  and is left as it is, placed at nothing and not foreign; a LinkedIn the
  model names for a Websites entry is never written there); empty entries,
  then added ones, take the profile entries no entry holds, in order. /map
  is told each field's place (`profile_entry`) and writes that profile
  entry's facts there, whatever order the page's entries are in — so
  an empty entry above a pre-filled job #1 gets job #2, never job #1 again,
  a job the resume parser dropped is added in its own place, and Websites 2
  gets your GitHub even when the model reads both entries' "URL" as your
  website (live Workday left that entry empty and required, 2026-09-30).
  Websites placement needs a backend from this release: an older one sends
  no `order` for a Websites section, so the Companion leaves it to you. An entry
  holding something the profile does not have may be a profile job spelled
  another way, so its whole section is left to you: nothing placed, nothing
  added, and the report says so. Two entries holding the same one add
  nothing. When two sections read as one job, school, language or website list (a
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
  waiver boxes (`CONSENT_FORMS`, which also reads "I ... authorize" and "background check
  authorization": a box that itself authorizes a check) — are also refused without that permission.
  **With it** (an explicit `consentForms: true`) `isPolicyBlocked` refuses NO
  label: every field above, agreement boxes and salary history become fillable
  (owner's decision, 2026-09-26: it is your application and your recorded,
  revocable consent). Submit is never clicked, at any setting; Next / Save and Continue is
  pressed only by `page_advance` in a run the user started with Apply (Queued run). It is a switch you give in Profile beside the EEO opt-in: two
  switches, because opting into EEO fill must not also opt you into agreeing to
  terms. Lifting the policy only lets a box reach /map; what answers it is a
  derived fact the backend holds only while the permission is served on
  (`derived.agrees_to_terms`, Yes, exact: the application's own terms and
  conditions, privacy notice, certification, acknowledgement and
  background-check authorization statements; never an optional opt-in to
  texts, marketing, job alerts or a talent community, which stay the
  low-stakes setting's, never a willingness question, and never criminal
  history, convictions or charges or anything a background check might
  find), so such a box is
  ticked, and with the permission off, lapsed, unreadable or never given no
  fact exists and the box is left (live Workday left one with the permission
  on, 2026-09-30). A background-check box /map still calls a protected
  question no fact answers stays yours, never a low-stakes guess. Signature and typed-name boxes take
  the full legal name (`derived.full_name`). A box is looked at before it is clicked, never re-ticked, and a
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
- **The veteran answer says it answers a military self-identification.**
  Described only as "is a protected veteran", Workday's "Military Status:"
  dropdown found no fact (2026-09-30); it is offered as also answering a
  military self-identification question whose options are protected-veteran
  classifications, and never whether you ever served or serve now, a branch,
  a discharge or a relative's service (a non-protected veteran's No to "Have
  you served?" would be false). Still a proposition with a direction. Nothing
  is flipped for such a label, so the dropdown is picked for the whole answer
  ("No, I am not a protected veteran") among its statements, exact or nothing.
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
     start before 6 s. A slow fast model gets a floor over that cap
     (below). On the fast engine, or when the Jev call fails,
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
- **Which engine decides.** On the Jev engine (Settings › Companion ›
  Form-filling engine), /map, /pick and /step ask Jev first. The fast model
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
  `Budget`, and never longer than 4 s (`SECOND_OPINION_MAX_S`).
  **A floor for a slow fast model** (live check 9, where a Claude fast model timed out three times in a day
  and the safe answers were lost): the second opinions of /map, /pick and /step and the fast polarity call
  (both of its attempts) get at least `FAST_PROVIDER_FLOORS` seconds, by the provider the fast model resolves
  to (`second_opinion_floor`): 3 s for `anthropic`, 1 s (`MIN_CALL_S`, the old limits) for every other
  provider, a custom server and an OpenRouter id included. `Budget.left(floor=, keep=, late_ok=)` lifts a call
  over its cap and its reserve but never past what is left of the 9 s less `keep`, the time a main call that
  follows still needs: Jev's pick and its fast fallback (`jev.TIMEOUT_S` + `MIN_CALL_S`) for polarity, 1 s for
  /map's second opinion, and for /pick's only when its reasoning call follows. `late_ok` lets the passes after
  a floor-lifted call start although it ran past the 6 s window (until under `MIN_CALL_S` of the request is
  left). The low-stakes Jev judge takes up to its whole 2 s and is skipped when less of the request is left;
  the queued years check keeps the keen pick and its fallback their time (`reason_years(keep=)`), and with no
  room left its fields are the user's. Each fast call on a budget logs the timeout it was given, and a failed
  second opinion says so with it. The fast
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
  1. **Low-stakes** — on at the web app's Screening answers **Balanced** (the
     default) and **Confident**, in Settings › Companion
     (`/api/settings/autofill-options`), re-read server-side by /map, /pick and
     /step, never trusted from the Companion. Answered the way an applicant keen on this job would: how you
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
     any option ("Former Associate of The Globex Depot") — is refused before
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
- **A dropdown that shows "— Make a Selection —" is empty.** iCIMS draws a
  select2-style box over a native `<select>` it hides; live on 2026-10-01, Fill
  read the box's "— Make a Selection —" and "Please select a country" as
  answers and skipped Degree, School, Country and four more. A select is a
  box's backing only when the page ties it to the box — the select right
  before the box's own container (select2's layout: a wrapper holding no
  label, no heading and no control but the box, so never the next
  question's), or one the box's aria-labelledby / aria-controls names,
  itself or by its label — and hides ITSELF inside a shown parent (not
  displayed, or select2's 1px clip; aria-hidden alone hides nothing on
  screen, so such a select is still a field); a hidden select that is merely nearby (a follow-up question's) is
  not, and a box with a backing input (Workday) never looks for one. Over
  its backing select a box is answered only while the select holds a value
  that is not empty, a disabled option or a placeholder row (whatever that
  row's value: "-1", "0"), whatever the box's words; that select is the
  pick's proof, and it is never a field of its own (two fields would be two
  writes). The placeholder test (`ns.isPlaceholderText`) also knows
  "make a selection" and "select / choose / pick a, an or your" and one or
  two words, wrapped in dashes or dots, by shape only: "Select Medical" or
  "Choose Health" is an answer. Such a row is never offered as an option.
- **A part of a date gets only its part, and a current job never gets an
  end.** iCIMS writes a date as a Month list, a Day list and a Year box, each
  labelled only "Month", "Day" or "Year", under "Start Date (Month / Day /
  Year)"; live, both Year boxes were read as "Year", the start got "2026-06"
  and the current job's End Date Year got the earlier job's end (the model,
  offered no end for that job, took another's). A label that is only a part
  word ("Month", "Day", "Year", "Type", "Number") now carries its group's
  question ("Start Date (Month / Day / Year): Year", "Enter in your mobile
  number: Type"): the group's legend or name, its first child when that is
  a heading, or the text before it, its "(1)" dropped. Shape, not meaning: /map still decides. When
  /map's slot is a date (`format: "date"`, by the slot) and the control holds
  one part (its label; or an id ending `_month`, `_day`, `_year` on a list,
  a box of at most 4 characters, or beside a control whose id shares the
  stem with another part — never a whole-date box named `birth_year`), only
  that part is written: a Year box "2026", a Month box "06", a Month or Year list
  the option spelling it (6, 06, Jun or June), chosen without a model. A part
  the profile does not have (a day) is left, "Your profile has no day for
  this date." A job's end date goes into an entry not placed by /sections
  only when that entry's other job picks in the same /map request (start,
  employer, title…) all name the same job; an end with nothing to anchor it,
  or beside another job's picks, is left, and the report says so ("Left for
  you: it isn't clear which of your jobs this entry is."; /map's `why`
  `unclear_job`, never "no fact" when the profile has the date). A page entry is its section and
  page position, which need not be the profile's order (an oldest-first
  page), so the picks decide. Known limit: an entry split across two /map
  requests (40 fields each) has no anchor in the second, and its end is
  left. A placed entry needs no check: its entry number is code's, and a
  current job has no end fact to place.
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
- **Nothing is ever submitted automatically.** Always review before submitting. The Companion presses Next only in a run you started with Apply.

## The answer receipt — what the panel records of a form

`shared/receipt.js` builds, and `panel/actions/fill.js` posts, ONE row per
capture to `POST /api/jobs/{id}/filled-answers` (matched job only; the body
names the base resume the fill used, which is how the server links it to an
application). It is a record of VALUES, so it is not telemetry: the generic
`api` door, never `telemetry`/`fill_trace`, whatever `telemetryEnabled` says,
and its values reach no value-free builder (SYSTEM.md
`{#inv-filled-answers-local}`).

- **The page's inventory is the source of a row.** After a run the panel reads
  the page with a `fill_inventory` carrying `readOnly: true` (no run starts;
  the engine's standing `consentForms` is not replaced) and the run's own
  `consentForms` (the loop report's, the rule pass's context), so the policy
  that judged the run judges the read. Only a frame that earns the data answers
  (`{#inv-frame-earns-data}`). A field the policy never fills (`policyBlocked`)
  is never recorded, on any path. The inventory's flag is not the whole of that:
  standing consent makes the fill's `isPolicyBlocked` answer "not blocked" for
  every label, so the receipt also drops the labels of the consent-independent
  `ns.isNeverFilled` (`shared/policy.js`: signatures, passwords, government IDs;
  salary questions are not on it). It is applied in the receipt's one entry
  builder, so every path obeys it.
- **The rule pass names its field.** Each `filled`/`corrected` item carries the
  rule id and the `fid` of the control written (`ns.fillInventory.fidFor(el)`,
  which names a control no pass has listed yet at the cost of a re-list per DOM
  change, capped per run). The panel reads that field's question, section,
  committed value and options from the inventory by fid; the rule's label is
  never used (for a radio or checkbox it is the option's text). A write with no
  field behind it is not recorded. A checkbox group is ONE row with a list
  answer and `options_count`. The pass's own radio/checkbox clicks run under
  `ns.fillBusyEl` (`clickControl`), so the trusted `change` they fire does not
  mark the field `touched`.
- **What it records, and under which source.** Every field the run wrote, with the page's committed value (a
  multi-select as its list, `options_count` from the inventory), its source from the slot (`sourceOfSlot`:
  the profile's sections and `derived.full_name` → `profile`, `experience.*` and `skills` → `resume`,
  `custom.*` → `custom`, any other `derived.*` → `inferred`; the loop's free-text route → `written`) or from
  the rule id (`sourceOfRule`); every field you typed or changed that no report names (`touched`) as `you`;
  Autofill's own resume attach as an `upload` (`slot: "resume"`, the file name); a pause-row answer that
  sticks as its own one-field `you` row (`typedAnswer`, no inventory read). A field left open, left alone
  or found already filled is not recorded; an EEO write carries `eeo` and its `eeo.*` slot.
- **Host and step.** `pageOf` sends the tab's hostname and its URL path (no query or hash) as the `step`,
  so a wizard that keeps one path across its pages reads as ONE step, and a label repeated on two such pages
  is one answer there (latest wins). It is the receipt's only notion of a page.
- **Rows are in page order, every occurrence kept** (the server counts a
  repeated label by its place in the row), cut to the server's bounds (question
  500, answer 20000, 100 list items, `options_count` 1000); a field with no
  question is skipped, never sent.
- **Capture points:** after a loop run, after a rule-pass run, after a pause
  answer, **while bound** (a debounced capture, below), at **Mark applied**
  (`setStatus`, before the PATCH), and as the panel **lets go of a page**
  (`bindPage`, before `resetPageFacts`, when the tab or url changes; a Refresh
  is not leaving). The last three post what you typed or changed since the last
  post (`fromEdits`): a field a run wrote keeps its source and is marked
  `edited_by_you`, one it did not is `you`. `receiptSeen` (page-shaped, carried
  by Refresh, cleared only with the page) is the memory of what was posted, by
  fid; nothing is posted when nothing changed, and none of these reads a page
  no run has posted for. The leaving capture is fire-and-forget, built from the
  facts as they stood, and writes nothing back to the store.
- **Every post restates.** The server keeps the newest answer per (step,
  section, question, occurrence IN THE ROW), so a row with only the third
  "Company" would land on the first one's place. Each run and each edit capture
  therefore also restates every already-posted field still on the page
  (`restated`/`fromEdits`), in page order, under the source it was posted with.
- **The hint while bound.** `content/touch-notice.js` sends the panel
  `{type: "fields_touched", fids}` (opaque fids, no value), at most once per two
  seconds, for fields the USER changed (`inventory.js`'s trusted-event listener;
  the engine's writes run under `fillBusyEl` and are exempt), and only from a
  frame that passes `ns.frameMayReceiveUserData` (agent.js's gate, asked at send
  time). The panel (`onFieldsTouched`) accepts it only from this extension, from
  the bound tab, for a matched job with a receipt posted; after `EDIT_CAPTURE_MS`
  (3 s) of quiet it runs the same gated edit capture. The message is a hint: all
  values still come from the gated `fill_inventory` read.
- **What the Fill body shows of it.** The post answers with the flagged fields
  (server-computed, fixed reason strings); `receiptFlags` is rendered by
  `stages/fill.js` `flagNodes` as the "Check before you submit" group, first among
  the loop report's groups and beside the rule pass's rows. Warn-only: a flag
  never stops a run and never gates a Submit (the Companion clicks none). A row with a field id jumps to it. The debounced capture
  and Mark applied refresh the list from their own post's answer (a capture that
  posts nothing leaves it; leaving a page cannot, the page is gone). The matched
  job's knock-out scan (`knockout` on `/api/jobs/match`) heads the body (the
  no-form body too) as one plain-text line, the scan's own message and nothing
  added, only for a `conflict` or `profile_missing` check.
- **A rule that wrote over your edit** is the rule's value, not yours: a
  rule-pass run first reads which fids were already changed (`touchedBefore`) and
  does not mark those `edited_by_you`; the loop never writes a field you changed.

## Queued run (one job, Phase 2)

What the Companion does beyond filling a page: with full automation On, the Job step's **Apply** takes ONE job through its
application in the CURRENT tab, clicking Next on every page, and stops on the review page. **Submit is never clicked, at any
setting.** Built so far: the driver, the page operations, the one-job panel states, the Screening answers dial and the fill-agent
fixes below. **Phase 3, not built:** the Queue view, the run list and run log, parallel tabs and pacing, the `next()` scheduler,
Prepare queued jobs, `GET /api/autofill/queue-run`, and the **Queue** button (`QUEUE_BUTTON = false` in `panel.js`; Apply fills the
footer alone).

- **Pieces.** `shared/queue-run.js` is the driver: pure, with every browser effect an injected dep (`openTab`, `classify`, `advance`,
  `fill`, `signIn`, `waitForChange`, `tabUrl`, …), so node drives the whole state machine and a later move of the host is a change of
  host. `panel/actions/run.js` is the host (a tab, a clock and the page fan-out arrive through the `run` door of the action handle, so
  `actions/*.js` stay chrome-free); `panel/runs.js` draws the record into the Fill row's Next card. The record is plain data, one per
  tab, saved to `chrome.storage.session` (`queueRun`) at every change, so reopening the panel shows where a run got to; a record that
  was mid-air when the panel closed is not running any more. A run is not the active page: a tab switch cancels nothing (the user's
  own Autofill keeps its tab-switch cancel); what ends a run is Stop (which also sends `fill_cancel` to the run's own tab), a wall, or
  a finished application.
- **Page operations** are content-script messages through the existing fan-out and frame gate (`inv-frame-earns-data`):
  `page_classify` and `page_advance` (`content/page-reader.js`; broadcastable and gated like the `fill_*` ops; a broadcast may name the
  one frame to ask), `page_errors`, `page_uploads`, `page_required` and `page_field_count` (broadcastable like the others, so listed in `sw.js` `BROADCASTABLE`; below), `page_sign_in` and `page_create_account` (top frame only, in
  `panel_frame0`'s allow list and NOT broadcastable), `fill_watch` and `fill_watch_report` (below). `summary()` is counts, button texts and booleans, never a value or a password;
  its `errors` is a COUNT of what the page complains about, `errorKeys` are hashes of those errors (which ones, never what they say), and a
  button that is only a line of the error summary carries `inErrors` (and `errorLine` when its own text reads as "Error - <field>"). It also names
  `fieldControl` and `navigation` on a button, `chooserId` (the start chooser's one link) and, on the Workday host only, `headerSignIn` (below).
- **Page kinds** (`shared/page-kind.js`, pure): the posting, start chooser, sign-in, create-account, email-code, CAPTCHA, board-native, form step,
  review, confirmation and closed pages. A button sorts as Submit when ANY Submit stem appears in its text (submit, apply, send, finish,
  finalize, complete, confirm: substrings, because a wrong match only stops), as Next only when the whole label is a Next word
  (next, continue, save and continue, review), and otherwise as unclear. A review carries `by`, WHY it reads as one, because only one reason is the
  end of an application: `submit_button` (a real Submit control that is not site chrome, and no real Next still on the page). Every other reason
  means "stop, not sure": `several_next` (a Submit beside a real Next, or several Nexts with nothing to fill), `submit_seen` (a Submit the button
  list could not see), `submit_context` (a dialog or heading that asks about submitting) and `fields_no_next` (fields and no Next). A board's
  own pages (LinkedIn, Indeed) are `board_native` before any other check. Unclear buttons stop the run (no model picks one; `/api/autofill/page`
  is not built). **A Next is the step's when** it is visible, enabled, not an error line (`inErrors`) and not site chrome (`chrome`: header, nav,
  footer, search, contentinfo; a footer inside the application's own content is not chrome): inside a form first; when no Next is in a form (a
  wizard whose fields sit in several `<form>`s keeps its footer Next in a bar outside all of them), the ONE pressable Next anywhere in the
  application, leaving out a dialog's or a cookie notice's (`overlay`); such a Next outside every form is no "real Next" either, so a cookie banner's Continue beside a real Submit never turns the end of an application into `several_next`. `isPlainNext` tells "Next", "Next step" and "Save and continue/next" from a
  bare "Continue" or "Proceed". **Closed** is the notice wordings only (this job, position, posting or requisition has been or is now closed, has
  been filled, no longer accepting applications, available or open; "has been filled" after until, once, when, after, before, if or unless is
  prose) and counts only on a page with nothing fillable and no Apply control, so a job description's own prose never ends a run.
- **Open shadow roots: a page of web components reads like any other** (`ns.deep`, `content/detect.js`). A hosted one-click application draws its inputs, file
  inputs and buttons inside OPEN shadow roots, which `querySelectorAll`, `closest` and `contains` do not cross, so the page read as "nothing to fill" while
  `content/inventory.js` (its own walk) listed nine fields. `ns.deep` is the composed-tree version of those: `all(sel, root)` (document order, a host's shadow content right
  after the host), `any` (the light DOM first, then only the shadow roots under `root`), `closest`, `contains`, `up` (parent, else the host), `text` (textContent or innerText plus the
  shadow roots' text), `kids`, `roots`, `scope`, and the shared `searchBox` / `picker` rule. It lives in `detect.js` because every injection re-runs that file: a re-run file may
  call it without a fallback, where a newer export of a load-once file is what `tests/test_extension_manifest.py` forbids. Cost: each call answers from the elements holding a shadow
  root, found by ONE pass over the page (one per call outside a scope); `scope(fn)` keeps that list until it ends (the page reader wraps `summary`, `pageErrors` and `pageRequired` in one), and a page with no
  host answers the plain light query. **Only OPEN roots are read**; a closed root is invisible to every read here (Known limits). The page reader's three uses: a shadow
  button's label is its own text plus its slots' assigned text (a component's slotted "Submit"), and `ownHosts` adds the host's `aria-label`/`title` (and a Submit mark, a
  required mark) **only when the host speaks for that control**: its shadow root holds exactly that one button and no field (or exactly one field), as a design system's
  button or input does. A container component (a card holding a field, Back and Next) is not that: its title or id is never the label or mark of the buttons inside it, or every
  one would sort as Submit and a middle step end as Ready. `aria-labelledby` and `aria-describedby` resolve inside the control's own shadow root first. A dismiss press on a
  shadow submit inside a light form is refused. `detectPage` asks the light DOM first and, on a miss, each open shadow root (`roots()`, found once by that first miss, one `*`
  pass), so the panel's manual Autofill is not withheld on such a page; its page text stays the light DOM's.
- **The owner's rule: an unknown first page that has fields is filled** (`shared/queue-run.js`, owner, live check 8: "when I am there the autofill should work"). A page the reader
  calls `unknown`, at step 0, that the run has not filled (`record.filled`, `pageFilled`), is asked `fieldCount` once before the run parks `unknown_page`: `page_field_count`
  returns the fill inventory's fields minus search boxes and rich text (`ns.deep.searchBox`, the same rule `fillableControls` leaves them out by), so a careers landing page with
  a keyword box and a Location in a search landmark is not an application. With a count above zero the summary is read as having that many `fillable` and classified again: it is
  filled, then judged as any page with fields (a Next, a Submit, or `fields_no_next`, which parks `unsure_page` after the hold, never Ready); a real Submit beside the fields makes it a
  one-page form as anywhere. With none it is the old `unknown_page`. A later step, a page already filled, a host without the dep and a page still blank during the wait to draw are not
  asked. `fillableControls` counts a read-only combobox that opens a list (`picker`: `readOnly`, `role=combobox`, `aria-haspopup=listbox`, as Ant Design draws its select) and
  excludes `type=search` and search-named boxes, so the common case needs no second opinion; the pair is pinned equal on the shadow fixture in `tests/browser/test_shadow_dom.py`.
- **A field's own control is never an action** (`fieldControl` on the summary's button, `content/page-reader.js`). A Workday question popup carries its
  question in its aria-label ("... willing to submit to a background check? Select One Required"), which sorted by words is a Submit. So a popup button
  (`aria-haspopup` listbox or true), a member of a pill group (the shape reader's `pills`, or a real group of `aria-pressed` toggles; a lone toggle, one worded
  as a Next and one that is a whole Submit or Send phrase are not) and a button inside a field holder (`fieldset`, `[role=group]`, `formField*` automation
  ids, when it holds another field or is a vendor wrapper) are left out of the Submit/Next sort, of `submitSeen` and of `page_advance`. Exceptions stay
  actions: a form's own submit (a button with no type inside a form, `type=submit`, a submit mark), a button whose SHOWN text says Submit or Send when it is
  an `aria-haspopup="true"` button or sits in a holder, and a holder button worded as a Next. A listbox popup and a pill show the answer picked ("Yes, I am
  willing to submit..."), which stays the field's.
- **The footer decides the step** (`navigation`). The vendor's footer button (`shared/ats-buttons.js`, Workday `pageFooterNextButton`, verdict `text`) that
  is visible, enabled and worded as a Next makes the page a `form_step` with that button as the Next: it settles several Nexts and outweighs a Submit the
  button list could not see (`submitSeen`). It never overrides a real Submit button or a dialog that asks about submitting, and a footer worded Submit is a Submit.
- **The start chooser** (Workday's "Start Your Application": Autofill with Resume, Apply Manually, Use My Last Application, three same-tab links). The page
  reads `chooser` (`chooserId` set and nothing fillable) before the posting and Submit checks, because "Apply Manually" is a Submit word. `shared/ats-buttons.js`
  `CHOOSERS` allows exactly one link by host, automation id, exact text and path end, citing `fixtures/browser/workday_chooser.html`; the other two
  links (the resume parser, the last application's answers) are never named, so never followed. The reader names it only when no control on the page is
  fillable; the press (`advance(.., {chooser: true})` -> `pressChooser`) re-checks everything and NAVIGATES to the checked address (`location.assign`),
  never a click. The driver allows it only at step 0, with nothing filled, no sign-in or account made, not on a Resume or a run in place, on the host the
  run reached, and on the first page read after it opened the tab or the one read right after its own posting Apply moved the page. Anything else parks
  `chooser` ("Choose how to apply": press Apply Manually in the tab, then Resume; the host the user lands on joins the run's).
- **`page_advance` is the only navigation click in the extension.** It re-sorts the button's CURRENT labels (text, value, aria-label,
  aria-labelledby, title) at click time and refuses any Submit-worded one, a disabled or hidden one, and a forged id; ids are minted
  per read and tagged per frame, and the press goes to the one frame that named the button. `shared/ats-buttons.js` adds only
  recorded markers: today Workday's footer button (`data-automation-id="pageFooterNextButton"`, verdict `text`: it is navigation, and
  its own label still decides Next or Submit). A marker never beats a Submit word, and no row says "next".
- **A posting's Apply** is followed only as a same-tab http(s) link (`location.assign`, no click handlers), and only on the FIRST read
  of a tab the run opened itself, at step 0, with nothing filled, on the host the apply link led to, and when the page has no fillable
  control and one control worded exactly Apply / Apply now / Apply for this job that is not a form's submit. Never after a sign-in
  or a Resume: a site that restores a saved draft lands on its review page, whose "Apply" is a Submit.
  **A career site's Apply** (the employer's own posting page, which the run reached by the saved posting link or a redirect) is pressed too,
  when it goes to the record's queued link (same origin, same posting: `leadsOn`) or to a known ATS host (`shared/ats-hosts.js`), whoever the tenant.
  Such a link often asks for a NEW TAB (`target=_blank`); the press navigates THIS tab, so the reader (`applyPressable(el, {blank: true})`, this call
  alone) allows `_blank` for a link to the page's own site or a known ATS host, and any other target is still refused. The summary names the link
  (`applyHref`: origin and path, no query) and the record keeps it (`record.applyHref`, the address a tab the user opens is told by, below). The
  press carries that address and the page refuses it if the link was rewritten since the read (`would_submit`). **The landing is judged before
  it is trusted** (`landing`): the first read after the press must be on the link's host, the queued link's host or a known ATS host, else the
  run parks `moved_away` before any fill, and that host never joins `record.hosts` (the fill, the sign-in and the frame vouch all follow `hosts`).
  A site that bounces the application through a single-sign-on host the list does not hold therefore parks there; the user signs in in the tab and
  presses Resume.
- **Walls park, they do not retry.** CAPTCHA (a visible challenge frame of reCAPTCHA, hCaptcha, Cloudflare or DataDome's `captcha-delivery.com` reads as one, so the run parks without asking a model), email code, account creation on a host that is not a known ATS or that the page refuses, a sign-up page seen again after the press (`create_account_failed`), board-native apply, a failed sign-in, a start chooser it may not follow (`chooser`), a page it does not
  recognise and that lists no field to fill (`unknown_page`) or whose every frame threw (`page_stale`: the extension was updated under the open tab, see Install internals), a "thank you" page before the run reached
  review, the tab on a host the run never navigated to (`moved_away`, and the same park for a posting Apply that landed on a host nothing named; not after a park that told the user to go somewhere, `sign_in_yourself`,
  `verify`, `posting`, `chooser` or `unknown_page`: where they land on Resume is theirs, and that host joins the run's), the same page again, more than 15 steps, a Next that changes nothing
  (after one refill), a Next the page refuses and names (`page_errors`), a required upload it could not fill (`upload`), a review page that is not
  plainly the end (`unsure_page`, after it held; below) and a field-less page with only a bare Continue or Proceed (`confirm_page`; a step whose only content is an upload box the fill wrote or listed is a step, not this: `hadUpload`) each park with a fixed `why` word;
  `panel/runs.js` holds the words and which of Resume or Skip this job each offers. An `unsure_page` card is worded per reason (`run.lastBy`), never
  "the last page" while a real Next is visible: `several_next` "More than one Next", `submit_seen` and `submit_context` "May send the application", `fields_no_next`
  "No Next button found", else "Not sure about this page". A **closed** page ends the run as stopped (`closed`) and offers
  Resume ("Open the application in the tab, then press Resume").
- **Sign-in.** `pageOps().signIn` fetches the login (`POST /api/companion/job-site-login`) and types it in one call, the password a
  local that goes out of scope with it. It types only on a known ATS host (`shared/ats-hosts.js`, anchored at a dot, never a
  substring); on any other sign-in page the run parks `sign_in_yourself` without fetching the login. The email box is found by type
  or autocomplete, the button by plain sign-in wording and re-judged right before the click; the page refuses a locked, captcha-guarded
  or sign-up form. A password-only second screen parks (`no_email`).
- **Account creation** (`pageOps().createAccount`, owner decision 2026-10-14, reversing "account creation always parks"). The driver runs it only
  when the page classifies as `create_account`, the host the run reached (`record.hosts.at(-1)`) is a known ATS (`shared/ats-hosts.js`) and the record
  has not already tried (`accountTried`, set BEFORE the press so a Stop that lands during it still leaves the attempt made and a Resume never creates a second account; a refusal that pressed nothing unmarks it); a sign-up on any other host stays the `create_account` wall. It fetches the login
  as sign-in does and `page_create_account` (content/page-reader.js `createAccount`; TOP frame only, `panel_frame0`, NOT broadcastable) types it in
  one call, the password a local that goes out of scope with it and every outcome a fixed word. The page must hold exactly one email box and
  exactly two new-password boxes and no code box or CAPTCHA, or it refuses. It never types into a honeypot (robot-trap wording, `name="website"`,
  a beecatcher or honeypot id), types the same password in both boxes, ticks only a REQUIRED checkbox whose own words agree to create the account or
  to the privacy notice ("terms" counts only in a sentence that names the account; only the `createAccountCheckbox` automation id marks a box
  required for it) and refuses any whose words mention an application, a certification, a background check, FCRA, third parties, sharing, selling,
  alerts or marketing. A REQUIRED box it will not tick, and the user has not, refuses the page (`agreement`: nothing typed or pressed, the `create_account` wall,
  the attempt not used). It presses only the one visible control whose WHOLE label is "Create Account" (never one in site chrome, one with a Submit word
  in any label, or one the page marks as a submit). The status shows "Creating account". After the
  press the run SETTLES (`accountTaken`): it reads the page every `POLL_MS` for up to `ACCOUNT_SETTLE_MS` (20 s), because the site keeps showing the sign-up form
  for a while before the next page, with the pre-press error keys as the baseline (errorish text already there is not new). **Taken**: a verify, CAPTCHA or
  sign-in page (the main loop then parks or signs in as for any page); on the Workday host a read whose header Sign In button (`headerSignIn`) is gone with fewer than
  two password boxes, no code box and a Next in the step (`pageKind.signedUpRead`); or any other page that is no longer the sign-up form and has left it (another
  address or step heading; a failed sign-up redrawn without its password boxes is the same page). **Failed** (`create_account_failed`, the "Account not created" card,
  never retried): the sign-up form with an error that was not there before the press, held for `REJECT_HOLD_MS` (3 s), or the sign-up form still showing at the
  timeout. **Blank**: a page that stayed blank to the timeout is not called a refusal; the main loop judges it (the unknown-page park). An account that
  already exists is one of the failures: the user signs in or fixes the page and presses Resume.
- **Ready is a real review page.** `finish("ready")` needs, in order: the page is a review with `by` = `submit_button` (the record keeps `lastBy`;
  any other `by` parks `unsure_page` after the unsure hold, below, worded per reason), evidence the
  page was the application (a step behind it, or a field this page's fill wrote or confirmed), no page errors (`summary.errors`: one repair of the
  fields they name as after a rejected Next, then `page_errors`), and no required box left empty (`summary.requiredEmpty`, below). A required empty
  gets ONE scoped fix (`requiredTried`, `deps.fix` over exactly those items, the way a rejected Next is repaired) and must then be filled, else
  `open_questions` names them; an upload item follows the box-kind rules of the next bullet. `readyBy` is `submit_button`, or `user` when the Ready
  came from a **Resume on an `unsure_page`** whose `lastBy` was `submit_seen`, `submit_context` or `fields_no_next` (`VOUCHABLE`): the user's word that it
  is the last page (`vouched`, `record.parkedPage` kept for the park). The page is FILLED first like any Resume's (the fill answers nothing that already
  holds an answer); errors and required empties are still checked, and an attach an earlier run wrote, even unconfirmed, is not asked of the page again.
  The vouch is void once the page reads as a `form_step` (a real Next: that Next is pressed) and never covers `several_next`. A review page with no
  heading is matched to its park by its address alone (an empty step key proves nothing, but the address does).
  **The unsure hold.** A review whose `by` is not `submit_button` and is not vouched must read the same, unchanged, for `LONE_STABLE` (4) reads in a row
  (about 2 s; capped at `LIMITS.changeMs`, 15 s) before the run parks, because a step half drawn reads as fields and no Next for a moment. Page errors
  and required empties are dealt with BEFORE the verdict, so a page with boxes empty gets its fix (or names them) first. The
  confirmation watch and the auto-mark work the same for either `readyBy`. A ready tab the user took back to a form step (a real Next) shows "You
  moved on" with a Resume.
- **The page reader's required items and overlays** (`content/page-reader.js`). `summary()` carries `requiredEmpty` (a count) and `requiredKeys`
  (value-free hashes); `page_required` returns `{count, items: [{label, target, kind}]}` for the ones to fix, one per field (a radio group or a split
  date is one, a pill group is one through the shape reader: required from its `describe()`, never a lone toggle). A field counts as required by
  `required` or `aria-required`, a label's star or trailing "Required", a legend's star, a popup's aria name ending "Required", or the field
  reader's verdict (only the read that names items asks it, never the count). **Popups count as fields** when the button has `aria-haspopup`
  `listbox`, or a bare `true` inside a field holder (`fieldset`, `[role=group]`, `formField*` automation ids; never a bare `<form>`, which an ASP.NET
  page wraps around everything) or showing a placeholder ("Select One"), never in the site's own header, nav or footer and never a Search button
  (`content/detect.js` `fillableControls`, shared with the fill). A menu button inside an upload box is no required empty. A parser upload box is
  never owed a file. A button is `chrome`, `overlay`-flagged and `inErrors`-flagged on the summary; **`overlayOf`**: a cookie or OneTrust notice is always an overlay,
  and a dialog, `aria-modal` or consent container only while it holds no visible field, so a dialog wizard step, or a consent step of checkboxes, keeps
  its Next. **A stepper** (a container named `stepper`, `-steps` or `steps-item` that holds no form field, or a progressbar) lists step names, the
  last often "Submit": those are labels, not Submit controls, and only a real button inside one still counts.
- **The one refill.** A page that draws its fields after its footer (Workday question steps: popups mounting ~2.5 s later) showed none when it was
  filled: when the fill LISTED no field (`listed === 0`) while the re-read reports fillable controls (`summary.fillable > 0`; the guard no longer asks
  what the pre-fill read counted, since a page that showed one other control at the fill still listed none of its popups), the page is filled once more
  (`refilled`) before Next or Ready, and it is filled BEFORE it is judged. A Next that changes nothing is refilled once more too (`tried`). The trigger is the
  control count; a changed set of field fingerprints is not a trigger. Per-page flags (`pageFilled`, `tried`, `fixRounds`, `requiredTried`, `vouched`, `unsureRun`, `listed`,
  `refilled`, `attempted`, `wroteResume`, `record.attach`, `record.memory`) reset in `moved()`; `record.flags` (Check before you submit) is the LAST
  page's alone, so a page whose receipt is null shows none. `record.assumedRows` is the run's, NOT reset per page: every answer the run made for you on any
  page (a drafted answer, a date set to the 1st) as `{fid, question, step, note}`, one per question and step, never a value; Ready merges it into
  the same list (a receipt flag for the same question gains the note; a row from another page is a name, not a jump).
- **Park less.** A required field the fill reports `unconfirmed` does not park: Next and the page's own validation decide, and a page
  that does not move is refilled once. A run parks only on required fields it could not answer or operate (`open_questions`, the page's
  own invalid flag counts), once per page, naming them.
- **A value the engine landed is checked, not parked on** (`landedToCheck`, `shared/queue-run.js`). A required field the fill left `needs_answer` with a value ON it (its last
  outcome `group_committed`, `search_committed` or `committed_while_*`: a search picked its one hit, a click committed an option) is not an open question: the engine's own check
  could not call the value right and the page's validation can. `openQuestions` leaves it out and `keepAssumed` lists it in `record.assumedRows`, so Ready shows it under
  **Check before you submit** with one of two fixed lines ("Searching picked a value. Check it.", "Companion clicked an option. Check it."; never the text the page took:
  `fillLoop.landedNote`, `KNOWN_NOTES`). A field the engine gave up on (nothing landed) still parks, and a landed field beside one that needs an answer parks naming only the second.
  **Never one the protected list covers** (`PROTECTED_SLOT`: `work_auth.*`, `eligibility.*`, `eeo.*`, `derived.sponsorship`, `derived.previously_employed_here`, `derived.us_citizen`,
  `derived.agrees_to_terms`, `preferences.desired_salary`): a value a click happened to land on is not the applicant's answer to those, so they park and are never listed as checked.
- **An optional field left unanswered is listed, not parked on** (`leftForYou`, `shared/queue-run.js`; `keepAssumed`, `panel/actions/run.js`). An optional field the profile had a
  saved answer for (the map filed a fact under it; its last outcome is not `no_value`) that the fill still left `needs_answer`, and that no search or click landed a value on
  (that is the "Check" row's), gets a row in `record.assumedRows` with `left: true`, shown under **Check before you submit** as "Left for you" (`runs.js` `checkRows`; never the
  value). It never parks the run and never blocks the Next. A later fill of the same page that answers the field (any status in `ANSWERED`) removes the row at that step; a row
  is one per question and step, like the others.
- **An optional field left blank is listed too** (`keepAssumed`, `panel/actions/run.js`; `checkRows`, `panel/runs.js`). A not-required field the fill left `left_blank` (no fact, no skill to add)
  gets a row with `blank: true`, shown under **Check before you submit** as "Left blank — optional" (never a value), so nothing the run did not answer is silent. Like "Left for you" it never
  parks and never blocks Next, is one per question and step, and goes when a later fill of the same page answers the field, or when the reasoning step then writes it (that row's flags
  `left` and `blank` are removed and it reads as the answer the step wrote).
- **A skills box that is not required is left empty in a run** (`skipOptionalSkills`, passed by `fillPage` for a full fill, not for a scoped repair; `shared/fill-loop.js`
  `optionalSkills`). A box the map put the resume's skills in (slot `skills`), or a multi-select or search box whose question names skills, that is neither required nor flagged
  invalid, finishes `left_blank` with `lastOutcome: optional_skills` and no explore, pick or step call: a list of tags is a set of searches, one step each, and nothing
  waits on it. A required one is filled as before, and so is one a page error names (the repair is scoped, so the skip does not apply). A prose box about skills is the model's.
- **A Next the page rejects is not a move** (`rejected`). A Workday "Errors Found" banner adds buttons, which used to change the page
  fingerprint, so the press read as a move and the card said "Page 3" over the same page. Now the buttons the error summary owns (`inErrors`,
  `errorLine`) are out of the fingerprint, the Submit sort and the page classifier, and `press` returns `rejected` instead of `moved` when the
  address and the step heading are those of the press and the page names an error that was not there before it (or nothing else changed). A
  page with no heading is an unknown step, never "the same". **The step's heading is its own** (`stepHeading`): the first visible h1/h2 inside the
  form or main region that is not the job's title, else the progress list's `aria-current="step"` entry, else any visible h1/h2 inside the region (even one the tab's title
  echoes: a title that follows the step names the step), else the first one that is not the job's, else the first anywhere; a heading that is the JOB's title (the tab's
  title contains it, or it or a holder around it is named for a job posting / title / header; the holder walk stops at the first region or field-holding ancestor, so a
  page-wide `jobPostingPage` holder names no job) reads the same on every step and is skipped, and so is an error summary's
  ("Errors Found", "Please correct": the field reader shares the pattern, so it is no field's section either). A standing "Fields marked * are
  required" line on a page that moved is a move. `waitForChange` ends the wait at once on a fresh error; one that is not new must stay for `REJECT_HOLD_MS` (3 s), or
  `REJECT_HOLD_STANDING_MS` (8 s) when the page already showed errors before the press (`baseline`, the press's `errorKeys`), since a slow save
  leaves the old banner up. `step` and `seen` do not change, and `moved()` clears the page's `fixRounds`, `attempted` set, resume-written flag, attach note and `record.memory`.
  The driver reads `page_errors` from the frame that was pressed, hands the items to `deps.fix` (the host's `fixPage`) and presses once more.
  `fixPage` works ONLY the named fields: a fill field through `runFill(..., {only: fids, memory})` (a scoped call posts no receipt, no gap rows and
  no resume attach, so the page's receipt reflects the page's first full fill only, and its progress count stays as that fill left it), an upload box through the targeted attach. It works every
  error it can map and returns `{fixed, remaining}`: an error that names nothing the run can work (an unmapped label, an `unknown` kind), two upload errors at once, a box left
  unattached and a field the fill did not repair stay the user's, and the park names ONLY those (`errorsOpen(remaining)`; the same for a required-empty fix on a review page, which
  parks `open_questions`). A repair that wrote nothing (a banner left up over boxes already holding their file) is not a fix; the driver reads the page again and judges it by the
  rule below. An error is repaired once (`attempted`, by label), at most `MAX_FIX_ROUNDS` (3) rounds a page; the same error back, or a blocker, parks `page_errors` with `open` set to the
  errors' labels. The card says "The page asks for more" and lists them; a field the page named only by its words (an upload box) has nothing to
  jump to.
- **A page the run did not fill is never pressed** (`filledPage`: `{where, key, shape, here}` of the page the run last filled, set at every fill, cleared by `moved()`).
  A refused press or a repair can end with the site on its NEXT page, whose Next the run would otherwise press unfilled. Before any press the current read is compared
  with `filledPage` by `samePage`: the same PATH and step key (the query is left out: a session or tracking parameter that appears after a fill is the same page, and
  `filledPage.where` follows it) and, once the page's post-fill read is known, the same SHAPE (`shapeOf`: its step buttons and its count of controls; the error summary's buttons and a field's own control are out of it and out of `fingerprint`, since a
  tenant's dropdown is a button whose text is its VALUE and a value never tells pages apart). A tenant that keeps one
  address and one heading for every step is told apart by the shape. A change of shape alone, under the same path and key, counts as a step once per path and key in a
  drive (`leftFilled`; a conditional field an answer revealed); a further shape change only refills the page (`pageFilled` off, no step added, the repair counts kept), so a page is
  never pressed unfilled and a page that keeps changing is still bounded. `fingerprint` also carries the count of required boxes still empty, so a Next that only swaps
  dropdowns (its fresh step shows them empty) still reads as a change. A different page counts as one step (`step + 1`, the old page's `here` goes into `seen`),
  `moved()` runs and the page is filled first. The count is bounded like any step: `step_limit` at the step cap and `loop` for a page already in `seen`, so a site that
  rewrites its address on every fill cannot walk the run through forty fills. A page that is `samePage` as the one filled is pressed again without a second fill. The reasoning
  step's `press_next` uses the same comparison. **A refused press is re-read before the run parks** (`movedOn`, ahead of a `page_errors` park): a press that read as refused only
  because the new step drew its own error line or upload box leaves the site on a page that is not the one filled; that counts as a step and the loop fills it (a page already in
  `seen` is not a step: the errors' park, not `loop`). `fixPage` treats an upload error whose box the page no longer has as stale, like a box the user filled by hand
  (nothing is attached; the driver reads the page again), unless the page shows a required box still empty: that is the box redrawn under another tag, and the run parks.
- **`page_errors` reads what the page itself complains about**, in its own words and never a value: `{count, items: [{label, target, kind}]}`, `kind`
  `field` | `upload` | `unknown`. Sources: a visible alert or `aria-live` region that reads like an error (not `aria-live="off"`; a region that holds a
  field is the step around it), a block headed "Errors Found" / "Please correct" and the like, and each control marked invalid (the field reader's
  `invalid`, extended to upload boxes: the box's own `aria-invalid`, an error node in its widget, an error referenced by `aria-describedby`; never a
  fieldset around a neighbour). One item per field (the summary's line and the field's own mark are one error). **One error line is read as one line** (`lineParts`): Workday sets the "Error - X" button and "The field X is required and must have a value." in one list
  item with no space between, so the name comes from the line's own "Error - X" button or link when it holds one (its linked control is the field), else from the
  first non-empty line of its text, never from the item's text run together; the X of a "The field X is required" sentence is kept as a second name. A summary item maps to its field by its link
  (`href="#id"`, `aria-controls`, the `for` of its label), else by `aria-describedby`, else by an exact normalised label (the name, then the sentence's X),
  both compared after the same 160-character clip, so a long question still matches; popup buttons count among the controls a name can map to. "Error - X" and
  "The field X is required" reduce to `X`. A mapped error is worded by the field's own question; an unmapped one by its line's field name; a name that could carry
  something of the user's (a file name, an address, a quoted string, a value the page holds, `heldValues`) becomes "Something the page names". A
  block that merely sits under "please correct any errors" is not a summary when it holds a button that is no error line, and a Submit-sorted
  button always counts as a Submit, wherever it sits.
- **The resume is written once per page, before Next.** The fill's attach (`panel/stages/fill.js`, via `fillPage`) counts a REQUIRED upload box as the
  resume box when it is the page's only upload box and its own words (not its section's) name no other document (cover letter, transcript,
  portfolio, writing sample, other), or a lone box under a resume heading whether or not it is required; it never writes over a file already there
  and re-checks `resumeOnly` at write time. It NEVER writes a `parser` box and never one of kind `other`. `page_uploads` lists the
  boxes (`{label, target, kind, required, occupied}`, `target` an opaque `data-maestro-up` tag, `kind` resume/other/parser/unknown) and `attach_resume_pdf` takes that `target`: the box a
  page error, or the fill's report of a required empty box, named. A targeted attach skips the "exactly one resume box" rule but still refuses an
  occupied box, a parser, or one labelled for another document; with several boxes on the frame the named one must read as a resume box and no other box may
  hold a file (the user attached by hand). **The gate** (`queue-run.js`, after the fill and before `advance`): the report's `attach.required` (a
  required box still empty that the fill's own write did not cover) gets ONE targeted attach if it is a lone box of kind `resume` or `unknown` (never
  `other` or `parser`) and the resume has not been written on this page (`wroteResume`); else the run parks `upload` naming the boxes. An outcome of
  `attached` or `unconfirmed` (a write the page may have taken but did not show) means the resume was written: `wroteResume` is set and it is never
  written again on that page, by the gate or a repair (a repair attaches to at most one named box), and a Resume on an `unsure_page` park keeps it when
  the parked record's attach outcome says a file was written. **On a review page** (below) a required empty upload item carries its box kind: one of kind
  `resume` excused by `wroteResume` is not owed (ONE box only: a second required upload parks `upload`), a `parser` or `other` box, or a choice between several, parks `upload` and is never given the resume
  through the required-empty fix. The page line reads "Resume attached", "A file was already attached" or "Couldn't attach the resume: ...", and the
  counter "N of M answered" counts only fields that ended filled, verified or kept, an upload box as one field. The Ready card shows the attach line
  whenever the outcome was not a plain attach.
- **Resume** turns the record to `filling` BEFORE its first await (Resume and Skip leave the card and Stop shows, so a second Resume cannot
  post the receipt twice or replace Undo's memory, and a Skip pressed meanwhile is honoured; Skip also sets `stopRequested`), then re-reads
  the parked page, learns every answer the user typed (`learnAnswer`, with Undo; never a multiline box, so a long written answer is not
  saved as a standing one; after an `open_questions`, `page_errors` or `upload` park, `LEARNS`: a field the page named as wrong, or one typed in the page over an upload park,
  is an answer like any other, while a wall or a navigation park asked for none), posts a "you" receipt row, and continues; a record ended under the read is not driven. Resume also makes the
  record belong to the panel that pressed it (its lease), so the mark after the user's Submit has exactly one owner even when another window's
  panel left the record. A `page_errors`, `upload` or `unsure_page` park remembers its page (`record.parkedPage`: address, step key and shape, plus the labels of the errors a `page_errors` park named; cleared on the first
  read after the Resume; an `unsure_page` page is matched by address alone when it has no heading). A Resume after `page_errors` or `upload` skips the fill only when that first read is that page: the same address and key and the same
  shape (`samePage`), or, after `page_errors`, the named error still on it (an empty step key proves nothing, so that page is filled
  as usual; a page that merely shares the address and heading with the parked one, a Workday step after the one parked, is filled); then after a `page_errors` park the errors are read and any that remain get a repair round, and after an `upload` park the upload
  boxes are only LOOKED at (`deps.uploads`, never an attach): a required box still empty parks `upload` again, naming only it, except the box
  an `unconfirmed` write went into (excused by its tag, or, if the page redrew it, when it is the only one left), and Next is pressed only when
  none is. After an `unsure_page` park the Resume FILLS the page (a fill never overwrites an answered field) and the user's word (`vouched`) feeds only the Ready
  judgement, for the parks that were about a Submit or a missing Next (above); errors and required empties are still checked, and a clean page goes Ready
  with `readyBy` "user". On any other page a Resume fills as usual, so it never presses Next over an unfilled page.
- **A saved answer that names this job stays with this job.** The panel (`panel/actions/pause.js` `scopeOf`) saves a row with `only_for`
  and `only_for_kind` (`company` or `city`) when the QUESTION names the job's company (the legal-suffix-free name first) or its city. The
  company match is case-sensitive on the job's own spelling (a company called Lapse is not "any lapse in employment"); a city is taken only from
  a "City, ST" or "City, Country" location, not a mode of work or a country (a short denylist). The backend (`autofill_catalog._for_this_job`)
  matches whole words, case-insensitively, in that field only ("Crate" is not in Datacrate, "Rome" not in Jerome, a company scope is not met by
  a job's location); a row with no kind, written by hand or earlier, is met by either. A scoped row reaches `/api/autofill/context` and
  `/choose` only through `autofill_job.profile_for_job` (with no application it holds nowhere), so a model never sees another job's answer.
  Answering the same question at a job the scoped row does not hold for ADDS a row instead of overwriting; updating an old general row whose
  question names this job scopes it; Undo removes only the row it added or restores only the one it changed. Settings shows the scope and
  **Use for every job** drops it. A profile read from `/context` is never PUT back (it lacks other jobs' rows).
- **Learning from a hand fix.** While a run is parked on a popup or search field, `fill_watch` has the page record what the user does
  to it: event types and a fixed few key names (ArrowDown, ArrowUp, Enter, Space, Tab, Escape), trusted input only, never `value`. One field
  is active at a time (the one the user's hands are on), and a pick in an option, listbox, menu or tree popup is credited to that field only;
  a trusted key, input or focus outside every watched field ends its turn, except inside an open popup, where arrowing through the list is
  still the field's. On Resume `fill_watch_report` turns that into the engine's own moves (`open:press`, `open:keys`, `search:enter`,
  `search:debounce`). The generic move (the first of each axis, a plain press) is never taught: the book drops it before its lifecycle sees
  it, so a hand fix cannot demote a recipe whose move was not tried, and nothing worth teaching writes nothing. A known other move enters the
  recipe book at probation for that site (one demonstration never makes it trusted), and a gesture that matches nothing joins the known-gaps list as `missing_technique`, as do leftovers the fill could not operate (`cannot_operate`,
  `unconfirmed`) and fields the user fixed (`user_fixed`). The recipe book is local and is taught whatever the fill log says; the gaps
  post only while `telemetryEnabled === true`. A gap is posted once per field and outcome and never retried (each post adds one).
- **A parked run follows the user into the tab they open** (`panel/actions/run.js` `followTo`, `onTabCreated`, `followOpened`, `moveRun`; `panel.js` listens to
  `chrome.tabs.onCreated` and the panel preview's stub knows it). The parks that send the user elsewhere (`USER_NAVIGATES`: `posting`, `chooser`, `unknown_page`,
  `sign_in_yourself`, `verify`) leave the run waiting in a tab the user may abandon: a career site's Apply opens the form in a NEW tab, a start chooser is pressed by
  hand. A record is `movable` only when it is `parked` on one of those, not stopping, not being driven and owned by this panel (`ownedHere`, the lease). **Follow
  rule.** A tab whose `openerTabId` is the record's tab is followed at once when its address is the application itself: under the queued link (`openUrl`) or under
  the Apply link the posting showed (`record.applyHref`), one path the prefix of the other with two segments at least on the same origin (`underPath`; a leading locale
  segment such as /en-US/ ignored), so another job of the same tenant or a policy page is not. A tab with no address yet (`pendingUrl`) is followed when it arrives (`followOpened`).
  Any other page, however it was opened, is followed only when the backend says it is this job (`GET /api/jobs/match`, one lookup per tab and address, the last fifty
  remembered) and only on the apply link's host or a known ATS host. The follow rebinds `tabId`/`startTabId`, sets `moved`, adds the new tab's host, unvouches the old
  tab and keeps the park; it **never drives**. The card then says "The run moved to this tab. Press Continue here when this is the page to fill." and its Resume is
  labelled **Continue here** (`runs.js`); pressing it is the ordinary Resume. A driving run, a wall or a question never moves; a tab the user already has a live run in is
  never taken over; a tab in another window is left alone (`ownsTab`: a side panel is one per window and every panel hears every tab) and so is a run another panel holds.
  The other way round, when the user is on a tab of this job and its run waits elsewhere, the Job step's footer is one primary, **Move the run to this tab**
  (`moveRun`, published by `actions.js`; `movableFor` finds the record), which makes the same rebind and nothing else. A moved record is saved at its new tab for a reopened panel.
- **Recording the user's Submit.** A ready tab believes a confirmation page only when it is on a host the run reached, at the employer of the
  page that reached Ready, and every read since Ready was a review or form step of that application (a page not drawn yet says nothing). The
  record keeps that employer as `tenant` (the panel's `sessionTenant`: origin plus first path segment), because a shared ATS host serves every
  employer and the host alone proves nothing. Any other page the tab shows (another employer on the same host, a posting, which after Ready is
  another job being looked at, a portal) sets `noAutoMark` and leaves the manual Mark applied. A believed confirmation shows "Marking applied in 8 s · Undo"; after 8 s the
  host posts `companion-submitted` (host, path and the matched words; no page text beyond them). The host and path are kept from the read that
  saw the page, so a tab closed during the countdown marks at once and a tab that moved on cannot change the address sent. A mark that fails
  after the tab closed (also one already in flight when it closed) ends the record as `stopped` / `tab_closed`, where its note shows on the
  stopped card, not as a ready card nobody would see. Undo posts nothing and offers Mark applied. A 409 shows the server's own sentence and falls back to the status PATCH. The
  user's time ends when the confirmation is detected. The Ready card's **Done** ends the record as stopped with no server write and frees the
  tab for a new Apply; the job stays the tab's (per-tab memory, under "What the panel does"). A read that fails on a ready tab leaves it ready (the driver does not stop a run mid-Submit). Each record carries the
  lease of the panel that owns it, and only that panel arms its auto-mark (every window's panel hears every tab; a reopened panel takes over the
  records on tabs of its own window). A run tab that navigates to a host the run never reached loses its frame vouch until a Resume reads it.
- **Apply on the Job step** (`panel/actions/job.js`, `shared/decisions.js` `applyPress`/`preselect`): re-reads the job and its tailoring
  sessions; an applied job stops; a job held by the always-on copy is refused with nothing written; it saves and scores the job's bases first
  (**Save job** also routes on the backend's match, not on a remembered job, so Apply after a restored pick uses that job and never saves the page
  as a second one), picks the resume per the switches below, queues as the user's yes (consent channel `companion`, only from
  `pending_review`), claims the job for this copy when sync marked it offered, settles the resume (a PDF: go; a draft without a PDF:
  render it, never quick-tailor over it; nothing and no open session: quick tailor with the user's pick; an open custom session:
  "Finish tailoring first", with Apply using the base resume and the session untouched), then opens `apply_url` (else `source_url`,
  else the tab's address; http(s) only, re-checked here because a value that arrived by sync skipped the server) in the current tab.
  The seed also carries the job's saved posting (`sourceUrl`): `openTab` keeps the tab only when it is not the job's posting, or the job has
  no separate application link. A run started on the posting itself (the page the job was found on, a career site's description) therefore
  NAVIGATES to the saved application link instead of staying there; a tab already on the application (the link, or a page under it) stays, and
  so does one on a job whose only link is its posting (`onPostingOnly`: the posting is where the user found the job, the link is where the form is).
  On a tab that already has a live run it only says "A run is already going in this tab." and writes nothing.
  When another tab's run for this job is parked on a step the user does by hand (below), the press says "Move the run to this tab" (`MOVE_RUN`) instead of
  "Running in another tab", writes nothing and moves nothing; a run that is driving still says "Running in another tab".
  It shows for a job with no application or the user's own draft, and stays hidden once the application is applied. **A job picked by
  hand** (the user's pick on a page the backend's match did not name, `claimFrom: "pick"`; a binding taken from a run record is not one, because
  the tab may have gone elsewhere) shows it too and runs `inPlace`: the pick says this page IS that job's application, so the record's
  `openUrl` is this page, the tab is never navigated or opened, and a posting's Apply is not pressed (the run did not open the tab; it parks
  as "Apply yourself"). The application is the DRAFT THEY NAMED, read at the press (it must still be this job's open draft, else "Pick it
  again"), not the job's newest. If the first read finds the tab on another site than the press saw, the run parks as `moved_away`. If the job
  has no `apply_url`, this page is saved as it with `PATCH /api/jobs/{id}`, but only when it names a posting (`decisions.applyLink`: an id
  segment or a posting-id query key, never a job board), and without its fragment or any query but that key; a job that has a link keeps it,
  and a refused save does not stop the run. The next visit then matches: `/api/jobs/match` reads `apply_url` as well as `source_url`
  (`is_same_posting`), trusting an apply link only when it names a posting (`job_url_match.names_posting`). With full automation
  Off the footer is Save job plus "Turn on full automation in Settings to apply from here." On a page whose job is not saved yet, with Apply
  as the button, **Add job** (`decisions.offersAddJob`, secondary, beside Apply) runs the Save job press (`applyJob` with `saveOnly`, busy kind
  `add`): save, score, stop on the ranked list, with no tailoring, queue or run; once the job is saved only Apply shows. With **Stop after each
  step** on, or **Choose the base resume for me** off, the one button already reads Save job and Add job is not drawn.
- **The Apply checklist and Stop** (`panel/actions/job.js` `applyChecklist`, store key `applySteps`, drawn by `panel/stages/job.js`). While a press
  prepares, the Job card lists each step it takes, in order: Saving the job, Scoring your resumes, Using <base> (<score>) with the base's colour
  square, Queueing the job, Tailoring the resume (or Using your tailored resume), Making the PDF, Linking the resume to the job, Opening the
  application. A step shows a spinner while it runs, a tick when done, a cross with a FIXED reason when it fails ("Couldn't save", ...; never
  server text, the note under the list carries whatever the panel may say) or a plain marker for the line the user is to answer ("Pick a resume to
  apply with"); a step that was not needed is never listed, and each state is also written for a screen reader. The footer's live note announces
  each step (the rail is rebuilt on every paint, so a live region inside it would be a new node each time). **Stop** (a labelled button with a stable
  id) is read at the boundaries between steps, never inside a call: a request sent is not cancelled halfway, and what was done stays done (a saved
  job, a tailored draft); the list then says "Stopped after <step>". A Stop between save and score ends before the score is asked, a press from a tab
  the panel left counts as stopped, and Stop survives a rebind and keeps focus. The base list is locked while Apply works (disabled radios,
  `aria-disabled`). Apply is refused while a checklist is live or while another tab's run holds the job's proposal (`ANOTHER_TAB`; the panel reads
  `run.js` `TERMINAL` to tell). Once the run starts, the run card takes over. Held, no-link and finish-first stops cross a line of their own. **Limit:** "Apply with the base
  resume" (the finish-first path) and quick tailor's nothing-to-tailor path use the base text as it is, with no voice repair, so a base summary
  written in the third person reaches the PDF; the health check flags it (`voice.third_person`), so fix it at the source, in the base resume.
- **The switches** (Settings › Companion › How the Companion applies, `companion_apply`: `GET`/`PUT /api/settings/companion-apply`, `{auto_pick: true,
  stop_each_step: false}`, file-mirrored and carried in the synced profile bundle). `loadAutomation` fetches both switches with the auto-apply
  setting in one breath and obeys them only with full automation On; a switch it cannot read is the default. **Choose the base resume for me**
  (`decisions.preselect`): the top match score must reach Auto-apply's `auto_pick_floor` and lead the next scored base by `auto_pick_margin` (a lone
  scored base has no rival); a close call, a low top or a re-score that made the race close clears an earlier preselection (`null`), and Apply stops
  after scoring at "Pick a resume to apply with" with the list unlocked. The mode line then says why (`decisions.pickHeldBack`: "The top two
  scores are too close for Apply to choose." or "The top score is too low for Apply to choose.", then "Pick one and Apply runs every step.")
  instead of "Apply picks the resume", and two rows that show the same rounded score are a tie with no green chip (`decisions.bestIndex`). With the switch Off nothing is preselected, an unsaved posting's footer is
  **Save job** (a pick comes after the save) and a saved job with nothing picked waits (`needsPick`). **Stop after each step** (`decisions.applyPress`):
  the footer names the NEXT press, **Save job** (save, score, pick), **Tailor resume** (or **Make PDF** when a draft has no PDF), **Start filling**
  (queue as the user's yes, claim, link, run), and each press re-reads what the server holds so it is idempotent; no `/api/proposals` call happens
  before Start filling. With it Off one press runs every stage and queueing stays at the start of Apply. The Job step says the active mode in one
  line with a link to the Settings card (`modeLine`). The pick limits are Auto-apply's; their label now says they apply to connected agents and
  the Companion. **Track this** counts as a pick (`claimFrom: "pick"`), so a just-tracked binding offers Apply at once.
- **Relinking the proposal.** Apply links the draft it made to the open proposal; a draft the user tailors afterwards used to meet "proposal already
  linked" on every later press. `POST /api/proposals` now moves an `accepted` proposal to a newer draft of the same job, only for the Companion's
  exact origin, only when the proposal was queued on the `companion` channel with no final review taken, and while the old draft is gone or still a
  draft (the draft it leaves goes back to the user lane); an application of another job is refused on every linking route. Everything else is a 409. A job
  the user marked applied (its proposal closed as "applied manually") and set back to Draft queues again; while an application still says applied, the 409 says
  "You marked this job applied. Set its application back to Draft", not "You skipped this job before".
- **Per-run fill limits.** `runFill` copies its limits per run; a driven tab passes `RUN_LIMITS` (60 s a field, 12 adaptive steps,
  10 minutes a page), the user's Autofill keeps 25 s, 8 and 3 minutes, and the module defaults are never written.

- **The reasoning step** (`shared/reason-loop.js`; host ops `panel/actions/reason.js`, wired by `think` in `panel/actions/run.js`; backend
  `POST /api/autofill/reason`, `app/services/autofill_reason.py`). Where the run would otherwise park, a model looks at the page once, acts a little
  through code the run already has, looks again, and either carries on or parks with a plain note. The model decides; every wall stays in code.
  - **When.** The driver's `parkOr` calls `deps.reason` before the parks in `THINKS` (`page_errors`, `open_questions`, `unknown_page`, `no_change`, `loop`,
    `moved_away`), at most once per page per drive (`thought`, `thoughtOn`), and AGAIN when it moved the run on. Never on a wall (CAPTCHA, email code, an account on
    an unknown host, a Submit page or any page that asks about submitting, a review page with no fields), never on open questions that are all protected, never within one step of
    `stepMax` (the park keeps its own reason). **A one-page form** (owner decision 2026-10-15) is the exception to "a review page": a page the driver judged `review`
    at step 0 that HAS fields (`summary.fillable > 0`), with no `submitContext` and no dialog (`pageKind.dialogUp`; a cookie notice is none), is thought about for
    `open_questions` and `page_errors` only, as `onePage`: the model works its fields (fill, answer from, write, choose, retry, redo) and nothing on the page is pressed.
    The request carries `one_page: true` and no button or tab (`buttonRows` returns none), the backend allows no press for it (`PRESSES`: `press_next`, `close_dialog`,
    `follow_tab`) and offers none in the prompt, `perform` rejects one here whatever the reply names, and the driver's own `press` refuses whatever the step asks. A wizard's
    final review page (step above 0) is never thought about. The review branch's park for required boxes still empty (`requiredEmpty`) goes through `parkOr` too
    (`open_questions`), so the same rule decides whether the step is asked; the other reasons on a one-page form (`no_change`, `loop`, `unknown_page`) are the user's.
    The host passes `reason` only with full automation On, **Think when stuck** On (Settings › Companion › How the Companion applies,
    `companion_apply.think_when_stuck`, default On, read like **Stop after each step**) and **Stop after each step** Off; the route reads all three itself
    (full automation, Think when stuck, Stop after each step: `switched_off`, ask the user, no model is paid, so a stale panel is not obeyed).
  - **Snapshot** (`snapshotOf`, exactly a `ReasonRequest`, never a value): the stuck reason, each field's `fid`, question, shape, required / filled / invalid /
    multi / multiline / by_run / touched, the fact NAME `/map` filed it under and up to 20 options; the page's Next and dialog buttons (`b<i>`, role `next` /
    `dialog`: only the Next the classifier names, a dialog button only while nothing asks about submitting), error lines (with the field's id when they name one),
    tabs (`t<i>`, host only), the last 8 moves and the signatures excluded. The job selectors (`application_id` or `base`, `page_url`, `today`) ride along; a
    `moved_away` snapshot carries no field, button or error of the foreign site. Page text is cut to 300 characters and stripped of invisible Unicode (Cf, Co, Cn).
    The page can say a typed value back, so every question, option text and error line passes the run trace's own screens first (`fillLoop.valueScreens`, over the
    inventory's `committed` values, same rule and thresholds as "Run trace"): a question loses its own keys and the siblings', an option against the typed
    siblings' keys (4+ characters), an error line against the siblings' keys. A question or error line keeps its words and reads `[your answer]` for the value (the words are how a protected question is told; the floors are the sibling ones,
    so a step number is not a value), an option text that holds one is `""`; with no fill loop there is no snapshot.
  - **Limits and guards** (`LIMITS`, mirrored by `schemas/autofill_reason.py`): 3 rounds, 3 actions a round, a minute a page, and no call is started with under 25 s of
    that minute left (the backend gives the model 25 s). An action's signature (`type:target`) that failed twice goes back as `excluded`; a field an action left
    unchanged twice leaves the snapshot; a round after which the page key (fingerprint, error count, filled fields) is unchanged ends the loop, as do `ask_user`, a
    missing or late reply, Stop and the page clock. The reply is checked again here: ids in THIS snapshot, a button's role, the actions the stuck reason allows
    (`unknown_page` only `close_dialog`, `follow_tab`, `ask_user`; `moved_away` only `follow_tab`, `ask_user`; `open_questions` no `press_next`, which the driver never
    presses there; a one-page form no press of any kind, and only `open_questions` or `page_errors`).
  - **Actions**, each through code that already exists: `fill` is `runFill({only})`; `answer_from` a `slotHints` entry for `/map`; `write` the `free_text` route with
    `reasoner` `short` (`essay` on a required multiline box) for `/choose`; `choose` the `reasoned` (basis history) or `low_stakes` (basis default) route for `/pick`;
    `retry` a move-order variant (`open_with_keys`, `search_with_enter`, `search_and_wait`), for `clear_and_set` a redo, or for `step_by_step` the field sent straight to the adaptive
    step agent (`options.stepByStep`; the backend judges it like the other techniques); `redo` refills over a field the run
    filled (never the user's `touched` one, never a multi-value field; no clear op exists, a text write replaces and a single choice re-picks); `close_dialog` is `page_advance` with `dismiss`, which the page refuses for any button that asks about
    submitting; `press_next` is the DRIVER's `press` (it re-sorts the label at click time, and only a page this run filled is pressed), the last action only;
    `follow_tab` is `rebind`, the Phase 2e move. The model names targets and never supplies a value: what is written comes from the profile, history and resume under
    the answer rules, so work authorization, sponsorship, salary, EEO, background history, signatures, licences and any fact the profile lacks are `ask_user`.
  - **The route** is the Companion's exact origin only (`companion_origin.is_companion`; 403 otherwise), because it spends the strong model. The panel asks through its
    ONE api door (`store.api`; the service worker stays the only fetch site) on its own clock, `REASON_MS` 30 s, polled every 250 ms for Stop. The server wraps and datamarks
    page text, lists the answer types the profile holds by name, calls the Reasoning model (a JSON Schema for Claude, JSON mode for the rest) and checks every action
    (`check`): allowed list, ids in the snapshot, the protected list, failed signatures, the Careful level (`write` and `choose` off). One failure turns the whole
    reply into `ask_user`, with the codes in `rejected`. The note is cleaned (invisible characters, links, emails, phone numbers, 200 characters). Any failure,
    late reply or fault in the loop is the normal park.
  - **The card.** While it works the card shows a live line (`run.thinking`; also the footer note for the run in view); when it moved the run on, one sentence
    (`run.sorted`, "Sorted it out: answered 2 questions and moved on."); when it parks, the code's own words (`run.thought`): what it asks of the user, else one line per attempt, "It tried How Did You Hear About Us? a
    second way; it didn't take." (`triedOf`: the doing as a phrase, then "it took" for progress or a move, "it didn't take" for no effect, "it was refused"; a rejected action is
    not listed; a question is cut to 55 characters so the outcome survives the card's own 100-character cut, and a field with no question is "a field"). The model's note is never on the card: it is on the live Thinking line and in the fill log, and the checker's refusal asks with the code's line, not the
    model's plan. The prompt has the note written to the applicant, in the present tense, about what is wrong on the page ("The state is still empty."), never a plan.
    What it wrote, chose or redid is listed under **Check before you submit** as answered for you ("Written for you: read it", "Chosen for you: check it", "Filled
    again: check it"), by field and step, never the value.
  - **The fill log.** A step posts a run of its own (`traceOf`; `fields: []`, up to 3 `reasoning` rounds): the model, time, the model's note, each action with its outcome
    (a written answer as its LENGTH) and the capped value-free snapshot the model saw (30 fields, 8 options each). `scripts/eval_reason.py` replays those snapshots
    against other models. See "Run trace".

### Known limits (Queued run)

- **The board a job came from is one guess.** `board_visits` keeps only the last board page the Companion looked up, for 20 minutes, in memory, and is not tied to the tab: a job saved from
  any non-board address inside the window carries that board, and a restart forgets it. The answer is `assumed` and listed for the user to check.
- **A step with the same heading, buttons and count of controls as the page before it reads as that page** (`samePage`). A tenant whose steps share all three is filled once and pressed, as before.
- **A Next drawn as a div is not seen.** The button list is `button`, `input[type=submit|button]` and `a[role=button]`; a page whose only Next is a div (even
  with `role=button`) reads as fields and no Next (`fields_no_next`), and the run parks after the unsure hold. The user presses that Next and Resume.
- **The chooser needs a page with nothing fillable.** Any fillable control on the start chooser's page (a cookie notice's checkbox, a search box) means no
  `chooserId`: the page reads as something else and the user presses Apply Manually once in the tab, then Resume. Only the one Workday row exists.
- **Darwinbox is not a known ATS host** (`shared/ats-hosts.js`). Its postings are read (Save job), but its Apply leads to a sign-in with a CAPTCHA, so the run
  never types a login or creates an account there and parks for the user.
- **A page with no heading can never read as a rejected Next** (the fingerprint has no step key, so "same step" is unknown, never true); such a
  page that refuses a Next shows as "no change" and parks after one refill. A headingless REVIEW page, though, is matched to its park by its address
  when the user presses Resume on an `unsure_page`.
- **`heldValues` misses a select's visible text and a custom combobox's value** (it reads typed inputs and a multi-select's pills), so an error line
  that echoes one of those is shown as the page wrote it instead of "Something the page names".
- **A file the user attached by hand is seen in the run's own frame only.** A targeted attach refuses when another box in the frame holds a file; one
  held in a different frame of the page is not seen.
- **Step mode, Save job:** on a wizard page whose restored job has no posting text, **Save job** dead-ends ("Nothing to save yet"); and a save from
  a page that escapes the backend's dedupe can create a second job (an older gap).
- **Closed shadow roots are invisible.** `ns.deep` and every read built on it enter OPEN roots only; a form whose components attach `mode: "closed"` roots reads as no fields, no buttons
  and no boxes, as before, and the run parks `unknown_page`.
- **An icon-only Submit whose name is elsewhere reads as unclear and is never pressed.** A shadow button with no text, slotted text, own `aria-label`/`title` or speaking host has no
  label to sort, so it is `unclear`: never pressed, and an unclear button stops the run like any other (no model picks one). The user presses it.
- **Several required upload boxes** park `upload`, naming them: the run never guesses which one is the resume's.
- **Modal wizards are handled.** A step drawn inside a dialog or `aria-modal` container that holds a visible field keeps its Next (`overlayOf`
  judges a dialog by what it holds); only a notice with no field, and a cookie or OneTrust box, is an overlay.
- **The refill trigger is the control count, not a changed set of field fingerprints** (the plan allowed either; fingerprints were skipped). A page
  that swaps one set of fields for another with the same count, after the first fill, is not refilled by that rule.
- **The chevron markup is assumed.** A category row is told by a trailing icon whose class, automation id, `data-icon`, aria label, id or `use` href
  says chevron, caret, angle-right or arrow-right; a site that draws it another way reads as an option, and the click's outcome (children shown,
  `group_committed`) is the fallback.
- **SmartRecruiters and iCIMS are unverified.** They are on the known-host list (sign-in and account creation are typed there), but no recorded page
  of either has been run through the account or review rules; only the sites of the 2026-10-14 live checks (Workday and three tenants called ATS-D, ATS-G and ATS-O in the diagnoses) were driven live.
- **A follow needs the application's address or the backend's word.** A page the user opens that is neither under the queued link or the posting's Apply link
  nor a job the backend matches (an applicant system whose first page carries nothing the job's records name) is not followed: the card waits where it was and the
  footer's **Move the run to this tab** is the way. The user's tab must also be in the panel's own window.
- **A single-sign-on redirect after a career site's Apply parks.** The landing check allows the link's host, the queued link's host and a known ATS host only; an
  identity provider in between is none of them, so the run parks `moved_away` and the user signs in in the tab, then presses Resume.
- **Query-only wizards read as one page.** The filled-page guard compares path and step heading with the query left out. A wizard whose steps differ only in a query
  parameter AND share a heading (or have none) AND the same buttons and count of controls reads as the page already filled, so after a refused press or a repair that ended on its next step, that step
  is pressed without being filled first. A press that moved still resets the guard (`moved()`), so the ordinary path is not affected.
- **Account creation has no password-rule retry**: a site whose rule the saved password fails parks `create_account_failed` and waits for the user.
- **The reasoning step cannot see a dialog in another frame.** It reads the frame that holds the form; a popup drawn in an iframe of its own is out of reach, so
  `close_dialog` is never offered for it and the run parks as it always did.
- **A status toast's Continue is the classifier's Next.** A page whose only button reading Next-like is a toast's "Continue" is what the page classifier names, so
  `press_next` presses it (through the driver's `press`, which still refuses a button that turned into a Submit).
- **A draft with a Socket.io-style word is dropped.** The link, email and phone check (`services/contact_scan.py`, on every drafted answer and every reasoning note)
  reads a bare dotted word on a country-code or common TLD (`socket.io`) as a link the owner did not give, and drops the draft; the question is then the user's.
- **The snapshot's value screen covers what the page can read back, not everything the user ever typed.** It uses the inventory's `committed` values on THIS page:
  a value typed on an earlier page (and held in neither the profile nor a base resume), or one the page cleared, is not known to it; a partial quote of a drafted answer
  inside an error line is not caught; and the card's "answered for you" rows show the field's unscreened question (panel only, never sent or stored). The stored
  copy's backstop (`redact_trace`) adds the profile's and every active base resume's values, no more. A screened question or error line keeps its words and reads
  `[your answer]` for the value, so a protected question stays recognisable; a field the backend receives with no question text is treated as protected.
- **A follow never drives.** `follow_tab` rebinds the run to the application's tab and parks with **Continue here**; the model cannot press anything there.
- **A one-page form is only worked on its fields.** The reasoning step on a one-page form presses nothing: a Next-looking button, a dialog's button and a tab are never offered, so
  a page whose only way on is a press (a validation dialog, a button that reveals more fields) parks as before. A form that shows a dialog or asks about submitting is not
  thought about at all, and a one-page form is only what the driver judges a review page at step 0 with fields.
- **The update guard covers re-run files, not a stale load-once file.** A load-once file that an update changed keeps its OLD code in an open tab until the page is reloaded; the
  scan only keeps the re-run files from reading what the old copy lacks. A run that finds the page unreadable parks `page_stale` ("Reload the page") after three reads.
- **A list that no word and no whole-list read shows still goes to the step agent.** The word fallback is skipped for a list that never settled (`unsettled`), which is the
  adaptive step's as before. "City, State" is typed only when the profile's state fact was filed under a field on the page this fill; a city box on a page with no state field is
  searched by the city alone.

### The fill agent's rules (all Autofill, run or not)

- **Robot traps are never filled, listed or asked.** `fillBase.robotTrap` judges a control by the field reader's label, aria-label and
  placeholder (honeypot / "for bots only" / "do not fill this" / "leave this blank" wording, on any control) and, for text boxes only,
  by page geometry wholly outside the page. A required field is never a trap. The inventory's `eligible()`, the saved-answers fill and
  open-question collection all use it. KNOWN LIMIT: a trap option inside a real checkbox/radio group (a shared name) is not filtered.
- **Fill memory and `only`.** `runFill(..., {only, memory})` serves a repair after a rejected Next. `only` (fids): the call works those fields and
  no others; every other field is closed before any map or explore, so it is never read into a row, mapped, explored, written or reported, and no
  section is grown (its entry-adding pass is skipped, and `fill_sweep` carries `only`). Its values still feed the trace's redaction keys (a
  field the call leaves alone holds a value the trace must not carry). `memory` (`fillLoop.newMemory()`, one per run record; `record.memory`): what a
  field's adaptive step learnt, keyed by the field's fingerprint (the question and kind, never a value) as `failedMoves`, `moveRuns` and
  `termsTried`, so a second call on the same page keeps the twice-per-search cap and the tried search terms. The record clears it when the step
  changes, and it saves as nothing (`toJSON` returns undefined: the terms may carry a value; a record read back from storage starts empty).
- **A list item that is already a pill is covered.** In `commitSet`, an item equal (case and spacing aside) to a pill the box already shows is marked
  `matched` with no explore and no set, and a list the first item's look left open is closed; twelve skills with ten already present cost two
  explores. `setAll`'s `holds` check stays as the backstop.
- **A field that already holds an answer is `already`**, even when no fact maps to it (a phone code showing "United States (+1)").
- **Optional fields with no fact are `left_blank`**: not asked, not counted as missing, named in a collapsed "left blank" list under the
  Fill report (it does not hold Ready). Required markers are read from stars, a trailing "Required" word and `aria-required`;
  question-led labels ("Is travel required") are never read as marked. An optional lone checkbox reads No and a native select without
  a placeholder shows its first option, so neither is ever `left_blank` (it is still asked). Neither is a box with no label of its own that
  is prose (a textarea) or required: with no question to read, "optional" is only a guess, so it is asked (`needs_answer`), not left blank.
- **A list field is worked an item at a time**, up to 20 items: each is searched, picked, committed and confirmed (its pill read)
  before the next; a missing pill is clicked once more, then reported (`missing`), and a partial list says "N of M added". A list item
  never takes a closest pick (a `/pick` closest for an item is treated as no pick).
- **No going round in circles.** A move that left the options and state looking the same as before is `no_change` and counts as failed,
  whatever the page said; the same search for the same value is never sent three times (a scroll is exempt from the twice cap).
- **The agent's own search term.** `search:term` types a short term the step model writes (a shorter word, a synonym, the category;
  `^[\w .&+/#-]{1,40}$`, never logged or traced, at most 6 tried per value). Typing is never an answer: a pick is still a click that
  clears the slot's floor. After a settled term search that shows the whole list (50 options or fewer, nothing to scroll), one
  flag-policy field may take the closest option, reported `closest_filled`. `/step` carries `kind` and `worked_here` (up to 4 moves
  that worked on this site, from the recipe book's axes).
- **A tree or slow list goes to the step agent, not to a second try.** A single-value choose that runs out of time (a slow search list, a long tree) hands the
  field to the adaptive step with `choose -> timeout` in its history, as the multi-value path already did; running the same choose again only burns the field's clock.
  A "how did you hear" field (`preferences.how_heard`) on a popup or search goes to the step agent first, since a source list can be a category and then a long list under
  it, and the reasoning step's `step_by_step` retry asks for the same on any popup or search. A search-shape choose has its settle on top of its budget
  (`budgets.searchSettle`, 4 s, added to `apply`): it types its term again and waits for the list as the explore before it did.
- **Technique cards.** `services/autofill_techniques.py` holds one card (at most 700 characters) per widget kind (search, multi, popup,
  group, select, date), appended to the adaptive step's instructions with the kind: what to try after which failure. Cards are widget
  craft, never per-site procedures. KNOWN LIMIT: the adaptive step runs for popup and search widgets only, so the group, select and date
  cards are not reached.
- **Calm before typing.** `fillBase.quiet` waits for the page to stop changing (text and attribute changes included) before a write that
  follows a choice (600 ms) or a recent change (300 ms), under a 2.5 s cap, watching the field's own section (closest form, fieldset,
  group or Workday section) except for the first write after a choice, which watches the whole page. A wait that hits the cap marks the
  page noisy for the rest of the run (a carousel never settles) and its writes then wait only out the post-choice window. A write
  that finds its element gone is re-found by fingerprint and written once more in the same apply.

- **Pill groups are fields** (`shapes.js` `pills`, reported to the loop and the backend as a radio set, `reports: "group"`). A Yes/No or Degree
  question drawn as buttons with `aria-pressed` (or ARIA radios with `aria-checked`, or a `ul[role=list][aria-label]` whose every `li` holds one plain
  button and nothing else, two or more, none a menu, pager or tab: the list shape needs no `aria-pressed`, and shows its state, when it does, as a
  selected class) is grouped by the nearest container within six levels holding two or more of them and no other control, never inside a toolbar. The
  question comes from the container's label; the options are the button texts; the answer is the pressed one. Choosing LOOKS first and never clicks a
  pressed button, since a second click un-selects it. A group is multi-select by `aria-multiselectable`, or by a `multiselect` class or tag name on the
  container or up to three ancestors, and is then added to, never un-pressed, and never finished while items may be missing. A lone toggle and a
  toolbar's toggles are not fields. A group holding a button that sorts as a Submit or a Next, is submit-marked or is `type=submit` (`ns.pageKind.movesOn`) is a row of
  actions, not a field (a `Form actions` list of Back and Submit), and `choose` and `set` refuse to press such a pill (`submit_like`) as a second line of defence.
  The page reader counts a pill group in `requiredEmpty` once, required from its `describe()`, and `fillableControls` counts one control per group.
- **A category row is a group to open, never an answer.** A list row (Workday's source tree) with no selection control (no radio, checkbox or
  `aria-checked`) whose LAST content is a chevron icon (`trailingChevron`) is described to the adaptive step as a group. A row whose click showed
  children is remembered per field as a group even when nothing marks it, unless it is selectable (a selectable row whose click redrew the list is an
  option, never a learned category). A `choose` whose click on a category committed a value reports `group_committed` (an `unexpected` outcome the loop
  treats as landed, never as verified), and a category is never committed as the answer.
- **A debounced list is waited for.** A search box that says `aria-autocomplete` list or both lists as you type, possibly long after typing (a
  JET-style combobox on ATS-O showed its rows after 500-800 ms, and an Enter before they exist CANCELS the search, which killed the search and
  re-picked up to three times: the visible flicker). Such a box gets the whole `OPEN_MS` (2.5 s) with NO Enter; only a box that showed nothing in that
  time gets the Enter as a last resort, and then waits `LATE_ENTER_MS` (1.5 s) for its answer. A Workday box is ALWAYS sent the Enter (its widget marker
  searches on Enter whatever it says), a street-address box is NEVER sent one (and gets `ADDRESS_MS`, 4 s), and a learned `search:debounce` recipe
  selects the patient wait. The rule keys on the live input's own attributes.
- **A pick that is only the box's own text is not proof.** A select-style box with a hidden backing input reads that input's value (empty: nothing is
  committed) and falls back to its resting text (`restingText`: the input's text only while its list is closed and it is not focused) when no backing
  input exists; the JET host losing `oj-has-no-value` stays real proof ahead of both. A read that rests on the resting text alone is a **weak read**
  (`weakRead`): when the only evidence is that text and the query the engine typed reads the same as the picked option, the pick is reported `unconfirmed`, not verified, since
  a strict widget that rejects the click and keeps the query looks the same. To make a real commit visible, a **weak box** (`weakBox`: select-style, with no
  selection node, no chip and no backing input to read a pick from) is typed a PREFIX of the option's text, its last character dropped, when the term would be the
  whole text and has at least 3 characters: after the click a real commit shows a change (`Canad` to `Canada`), while a widget that rejected the click keeps the prefix.
- **A pick the box shows differently from its option is proven by its list** (`fill-core.js` `listHolds`; live check 9). A phone-country select lists "Acmeland +1" and shows a flag and
  "+1", so no text on the box equals the option and the text check calls a taken pick unread. After the box CHANGED and the text check failed, in a list pick (`choose`), a searched pick's commit and its
  whole-list re-read, the list is reopened and its marked option read (`option--is-selected`, or `aria-selected="true"`): if that is one of the wanted texts (the option chosen, the value)
  the pick is `verified` with the option's text. Read only when the box displays something, changed since before, and is not a multi-answer field, a set's item, a kept list, a Workday box
  (there `aria-selected` is a keyboard highlight) or an undo; and only if reopening and closing the list left the box showing what it showed (a page may take a highlighted row as a pick when
  the box is left), exactly one option is marked, and the reopen committed nothing. A dialing code is ignored only when the wanted text carries none, so "+1809" and "+1829" stay two
  countries. Text equality with the saved value stays the first check.
- **A follow-up's question is the one it follows** (`field-reader.js` `withFollowed`). A label that opens like a follow-up ("If applicable, …", "Please specify …") on a non-choice field is
  joined to the question before it ("Were you referred by an employee? — If applicable, name the referring employee"): the nearest earlier visible control's question, UNLESS that control
  is no choice (select, radio, checkbox, combobox or popup) and names none of the follow-up's nouns, when the nearest of the last 8 earlier choice controls of the SAME section that does
  name one wins. Nouns are words of five letters or more cut to six ("referring", "referred"), less the follow-up's own words and the stems every application shares (employ, company,
  position, experience, current, application, information), which join nothing.
- **A read-only select drawn with an invisible input is a field** (the antd opacity rule, `inventory.js` `invisibleButDrawn`). An Ant Design
  read-only select puts its combobox `input` at `opacity: 0` over the words it shows. Only opacity is forgiven: the input must be read-only, popup-shaped,
  still have client rects, not be `visibility: hidden`, and sit in a visible widget box; `display: none`, `visibility: hidden` and an empty box stay hidden.
- **A street address is picked by code** (`fill-loop.js` `fillAddress`, for `personal.address` on a search box). The fact's full line 1 is typed with no
  Enter and the loop waits up to 4 s for suggestions. Each row is scored: the house number as a whole token and the street core (words up to the LAST
  road-suffix word, with a direction right after it kept: Pl equals Place, St equals Street, and NW is not SW; whatever follows is a unit) must both
  appear, with a bonus for the profile's city or ZIP. Only the single best qualifying row is picked, with no model and no word or term search; two equal
  rows with different texts are no answer. A list without the number is searched once more as number plus street name. If no row qualifies, the typed
  line is left where the box keeps free text (`format: "address"`) and the field is `unconfirmed` with a fixed sentence; elsewhere it is the user's. A
  City, State or ZIP the page filled that matches the profile stands.
- **A URL is written whole** (`format: "url"`). A fact of a website, LinkedIn, GitHub or portfolio slot, or any value carrying a scheme, is a URL:
  `https://` is added only to what is a host (with or without a path; a GitHub handle or an email in a URL slot is written as it is, and a dotted number
  such as 1.2.3 is no host, since a host's last label is two or more letters). The page compares by the site named, dropping scheme, `www.`, case, a
  default port (80, 443), a trailing slash and a fragment, keeping path and query. A box shorter than the URL is refused (`too_long`), never truncated; a
  URL is never offered as search words or searched by a word. A box already holding a DIFFERENT site is flagged as holding something else and is never
  counted answered or overwritten; the same site in another spelling is already there.
- **A search that finds nothing is tried by words, then the whole list is read** (`content/fill-core.js` `fallbackWords`, `shared/fill-loop.js`; live check 7). When a typed
  term shows no options (and the list settled), explore types, in order, the term's first word of 3+ characters that is not the term, then that word with its apostrophes
  and a trailing plural s removed (`Masters` finds `Master's Degree`, `Bachelors` finds `Bachelor's`); a word loses the punctuation it carried from the term (`Springfield,` is
  `Springfield`); never for a URL; it stops at the first word that shows options, and `viaWord` tells the choose to type that word too. If the term and its words all leave the
  box empty (a fixed list the page filters by substring, the saved wording matching no text), the loop reads the list once more with NO term; a list that shows goes to `/pick`
  whole (`complete` says whether it is the full list), and only a box still empty after that goes to `/step` (`noOptions`). **A city box is searched as "City, State"**
  when some field on the page was mapped to `personal.state` (`placeOf`); nothing found that way, the city alone is searched next. A Places-style list is then decided by
  code (`autofill_place.city_option`, `/pick` `city_picks`, `/step`): see `docs/entities/others.md`.
- **Dates take the 1st when the box wants more than the fact has** (owner decision: low stakes are decisive). A native date, month, pattern or section
  date widget given a month-only value gets day 01, and a year-only value gets January 1st, written and reported `assumed` with a fixed note ("Day set to
  the 1st", "Month set to January", "Set to the 1st of January"). A box that already shows every part the fact has is left as it is (2021-05-17 for the
  fact 2021-05): an assumed day never overwrites a real one. A native box's `min` and `max` are respected: a date outside them is refused
  (`outside_date_range`, nothing typed) unless only the part the engine assumed put it there, in which case that part moves inside the range, within the
  fact's own month or year, and the row is reported with its own note ("Date set to the nearest the box allows"). Separate Month, Day and Year controls
  follow the same rule. The fact itself is never changed or invented.
- **`outside_date_range` and `too_long` are the user's.** They finish `needs_answer` with a fixed sentence ("This date is outside the range the box allows.
  Left for you.", "This box is too short for the whole link, so nothing was typed. Left for you.") instead of retrying: asking again cannot help.
- **A flicker is named, not hidden.** An explore that committed a value (a search whose one hit picked itself) and had it taken back is recorded as a
  `took_back` step (`fill-ops.js`, `got.tookBack`); each field reports `changes`, how many times its value changed under the engine this run (a commit,
  its being taken back, a reversion). A count above 1 is a flicker, carries no value and is clamped to 99 in the trace. The service worker's
  whitelist and the trace schema take the effect word and the count.
- **A row's fixed note, from an allowlist.** A report row may carry a `note`, drawn under the field's name in the answered list and in **Check before you
  submit** (`ns.fillLoop.knownNote`). Only a sentence in `KNOWN_NOTES` is kept: the date notes above and the backend's draft note, "Drafted from your
  history: read it" (`qa.DRAFT_NOTE`); anything else `/choose` sends is dropped, so server text and values never reach the panel.
- **A drafted answer is a prose write marked assumed.** `answerProse` sends each prose field's `required` and its `draft` mark (from `/map`) to
  `/choose`; a draft comes back as `reason: assumed` with the note, is typed by `writeProse`, and is reported `assumed` (the user reads it), never as a
  verified answer and never saved as a standing one. See Screening answers below.

### Screening answers

`autofill.answer_level` (Settings › Companion › Screening answers, in What the Companion may fill; `facts` | `history` | `queued`, default `history`) is read by `/map`, `/pick` and
`/step` (the same level in each prompt), by the Companion and by agents through the Job Search Brief's `applying.answer_level`. The
protected list (work authorization and sponsorship, salary, EEO, criminal or background history, termination or discipline, agreements, debarment, security
clearance and agency employment, signatures, attestations and authorization boxes, licences and certifications, unsupported education or experience claims)
sits outside every level. `queued` applies only
to the job's own posting: `/map`, `/pick` and `/step` carry the page's address (`page_url`, http(s), no fragment; never in a trace) and
the server needs an accepted or approved proposal and `job_url_match.is_same_posting` against the job's `apply_url` or `source_url`.
At the top level a years question is Yes only when the history is silent or shows enough years (fewer: asked, in `/step` too); at the
middle level it is Yes when the history shows the skill and does not contradict the years. Clearance and agency questions are never
a keen guess. An answer the level gives is an `inferred` receipt row, so the `guessed_screening` flag lists it under "Check before you submit".

**The safe default** (owner decision, 2026-10-14; a "no fact" answer at any probability reaches the judge unless a second opinion named a fact or the runner-up was protected or EEO at 0.2 or more:
`others.md`, "Slow fast models, the low-stakes reach…"; `autofill_map._LOW_STAKES_TEMPLATE`, `_KEEN_NO`, `_KEEN_YES`, read by `/map` and `keen()` for `/pick` and
`/step`; from `history` up, never at `facts`). When the profile has no fact: a yes/no about a status, affiliation or circumstance that would only add
something, from a CLOSED list (tribal, union or association membership, an employee referral, a relative or household member at the company), is No (Not
applicable when offered); a yes/no about willingness, readiness or consent to a standard pre-employment step (background check, drug test, reference check,
I-9/E-Verify, providing documents) or about basic means (reliable transportation, internet) is Yes, both directions stated outright to the model. Never
defaulted (the never-list): work authorization, sponsorship, age or eligibility facts, EEO and voluntary self-identification (the safe answer there is
"decline", never No), background or criminal HISTORY (a record, a conviction, a pending charge; the protected sentinel names only that, so willingness to a
check is no longer protected; Jev still files some under it, and code lets a QUESTION of willingness (willing, agree, consent, able to undergo or submit to) to a background check, drug test, reference check,
I-9 or E-Verify reach the judge, never a first-person consent box, a pass, clear, eligibility or proof, or a history word), termination or discipline, non-competes and other agreements, debarment, clearance, salary, signatures and attestations, a box
that itself authorizes a check or a consumer report, licences and certifications, factual education or experience. A skills section that is not required stays
empty. Such a box is the user's alone: `CONSENT_FORMS` refuses it without the Agreements permission, and with that standing consent (owner model, 2026-09-26) the consent-forms rule ticks it, never a model.

### Answers the backend derives or drafts (live check 2)

- **Worked here (J4).** The reroute is an ALLOWLIST of question shapes about the applicant's own employment (`autofill_catalog._WORKED_SHAPES`: have/has
  you ever worked, been employed or been an employee, intern or contractor for/at/by/with; were/was you employed or an employee by/at/of/with; did you
  work for/at; are you an employee, contractor or intern of; are you currently employed by; a former or current employee), with the job's company
  DIRECTLY after the phrase ("worked with Acme products" and "employed by a competitor of Acme" never reroute) and an adverb allowed before the verb
  (been directly employed with). A backstop exclusion list still refuses a question that names kin, referrals, applications, interviews, convictions,
  authorization, sponsorship, clearance, background checks, terminations, non-competes, eligibility, willingness, a competitor, customer, vendor or
  partner, a government, agency, military or other public body beside the company, or a time window. `/map` reroutes a choice the model filed as history
  or no-fact (never a refusal or an unreadable map answer), and the trace names it as code's call. A derived Yes also asks the user when the question lists
  only a parent or subsidiary of an employer. **Another company's name** (the page's word for the job's own company, which the record spells as its legal
  entity, or a stranger) is rerouted too while the derived answer is No (`asks_worked_here_of_other`): employment verbs only (`_OTHER_SHAPES`; "worked with" is
  use or collaboration, never employment), the exclusion list, ONE capitalised proper name that is no group of companies ("FAANG", "Fortune 500", "Big Four"),
  no company the history or a parent or subsidiary of it holds, and no history entry that is no employer ("Confidential", "Freelance": the resume cannot say
  where it was). It is its own slot, `derived.previously_employed_here#other`, in `ASSUMED_SLOTS`, so the answer is reported `assumed` and listed under "Check
  before you submit".
- **Phone type and country (J5).** `derived.phone_type` is "Mobile", reported `assumed`; `derived.phone_country` is the profile country's calling code and name
  ("+1 United States", from a fixed table). Neither receives the number, and `content/autofill.js` skips a phone-type box ("Phone number type", "Mobile number type")
  before its phone rule; the rule reads "type" as a noun, so "Please type your mobile number" is still the phone box.
- **How did you hear (J6).** A saved source that reads as a board (or names one) is answered by code before any model (`autofill_step._board_move`, traced as
  code's call). The board is the job hint's `source`, else a board named in the saved value, matched as whole tokens against the known board names
  (`board_of`: "rec_linkedin" names LinkedIn, "prejudice" does not name Dice; `linkedin.com` is LinkedIn). **Board search first**: a plain click candidate whose
  first quoted text equals the board is clicked unless it was already tried and missed; else, when the page offers a search and that board was not searched
  yet, the board's name is searched (a tree is searched whole, where a model walking categories cannot back out of a wrong one: on one tenant LinkedIn sits
  under Social Media, on another under Job Board); else the MODEL decides, with a goal that says to search the board's name first, then open the category most
  likely to hold it (names like Job Board, Online, Internet, Website, Social Media or Other) and try the next if it is not there. The goal never names one
  category. A website or careers-page answer picks the careers-site leaf and names no board; any other saved word ("Referral", "Internet search") is walked to
  its own leaf by the ordinary goal. A leaf that is not the saved word itself is reported `assumed`. **A generic board answer** ("Job board", "job site", "employment portal": a
  kind, not a name) with no board known for this job takes LinkedIn (`GENERIC_BOARD`) when the list offers it, as a leaf or by search, else the first other specific job
  board the list offers: always `assumed`, listed under "Check before you submit" (owner decision 2026-10-15). A referral is never a board answer, even one that names the board
  the person works through, and "Board member" is none (the word must follow job or career, or be a known board name). **The board a job came from**: the job hint's `source`
  also reads `jobs.referrer_board`, the board page the user opened just before saving the job from the employer's own page (`services/board_visits`: the last known board page
  the Companion's `/api/jobs/match` was asked about, kept 20 minutes in memory, name only, never an address; `POST /api/jobs` stamps it when the saved address is not a board's).
- **Degree levels (J7).** `answer_flags.differs_from_profile` compares a degree by level when the page's value names only a level ("Master's/Advanced Degree"
  matches a Master of Science), reads M.B.A. as a master's in business administration only, treats a bare MS, MA, BS or BA as a degree in its own field, and
  compares a named field by its words.
- **Education level (threshold lists).** `derived.education_level` is the highest level a FINISHED degree in the profile names (`autofill_education.highest_completed`:
  high school, associate, bachelor, master, doctorate; a degree still in progress, a candidate, a denial, an end date ahead or "present" does not count; policy `exact`). A list of thresholds ("Bachelor's
  degree or higher", "Combination of relevant education, experience, and training", "None of the above") is answered in code by `/pick` and `/step`, never by a model: the highest threshold the level
  meets, an option naming two levels taken at the lowest, never "None of the above". It abstains (the user answers) when none is met, when the winning level has several options or one tied to a field or
  a degree type, and a list that names no level is left to the ordinary path.
- **Type of sponsorship.** A question that asks what TYPE of sponsorship is needed (the question has a need / require verb and no "any type of") under a saved sponsorship slot, with every saved sponsorship answer No
  (a question about now only needs the now fact), is answered by the option that means none or not applicable (`autofill_sponsorship`, in `/pick` and `/step`; a closed list is opened first); with no such
  option it abstains. A Yes/No list and a saved Yes never take this rule. The saved No is used even when the question counts OPT or STEM OPT as sponsorship (owner decision 2026-10-15).
- **Middle name.** `/map` files a middle-name or middle-initial question as none unless the fact is `personal.middle_name` (the profile has none), and
  `content/autofill.js` has a middle-name guard rule ahead of the first-name rule. The name is used as stored, never split.
- **Drafted written answers.** Only a REQUIRED text or textarea field `/map` filed under `free_text` or `years_unanswered` (`Mapped.draft`) and `/choose` could not
  answer is drafted (`autofill_choose._with_drafts`, at most six a call, one smart-model call in `qa.draft_answers`). Never at **Careful**, never without an
  application to ground it, and never when the never-drafted backstop matches the label (protected, EEO, work-authorization, money, background, signature,
  logistics, public-sector and worked-here wording). It is bounded by what is left of 7.5 s since `/choose` began (reading the context counts; under 2 s left,
  nothing is drafted), and a failure leaves the field open. The draft is plain text in the owner's voice (`resume_voice.repair` in code), about 120 words unless the
  label states a word count or a character limit (honoured), or `""` when the history cannot answer. It is saved nowhere: the user edits it in the page
  and Resume teaches the edited version (`learnAnswer` never learns a long written answer as a standing one).


## Telemetry — what leaves the page

Off by default: the user's **fill log** (`telemetryEnabled` in
`chrome.storage.sync`, defaulted to `false` in `sw.js` `DEFAULTS` and gated in its
`telemetry` and `fill_trace` handlers, which post only when the key is exactly
`true`). The switch is **Keep a fill log** on the options page (`options.js`
writes that one key on change, with no Save press); the panel has none. A choice
never made is not consent, which is also what the Chrome Web Store's user-data
policy asks for, so removing the key turns it off. It is fire-and-forget: it can
never surface an error to you or delay a fill.

**The off answer.** When the switch is not `true`, the worker's `fill_trace` handler answers `{posted: 0, why: "off", lastAt}` instead of a bare
`{posted: 0}`; `lastAt` is the time of the last trace this device posted (an ISO time kept in `chrome.storage.local` as `lastTraceAt`, and nothing
else about the run), `null` when none. A queued run records it (`record.logOff`, `record.logLast`) and the run card, when it ends or parks, adds
"Fill log is off. Turn it on in Options to let Maestro CS see what each field tried." and, with a time, "Last trace: Oct 13, 6:27 AM.", so a gap in
the observations has a date. Posting is never awaited.

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
| `outcome` | what happened: `filled`, `corrected`, `filled_normalized`, `filled_unverified`, `not_stuck`, `combobox_snap_failed`, `no_rule`, `missing_source`, `skip_rule`, `skipped_checkbox`, `hidden`, `policy_blocked`, `eeo_disabled`, `retry_filled`, `match_recovered`, `ai_abstained`; on a `loop_fill` row the loop's report status: `verified`, `closest_filled`, `assumed_filled`, `partial`, `unconfirmed` (a value the page shows but never confirmed, or that reverted after its one re-commit), `needs_answer`, `left_blank` (an optional field nothing answered, left empty on purpose: the loop did not ask), `cannot_operate`, `unsupported` (the control ignored every synthetic input), `prefilled`, `blocked`, `user_edited`, or `filled_unverified` for a value that landed without being chosen as the answer — a group click that committed one, a search that picked while exploring (`buildLoopObservations` in `shared/fill-loop.js`). (The backend also accepts `ai_answered`, `ai_no_stick`, `ai_unanswered` and `ai_unaligned` — stored rows carry them — but nothing emits one since the floating card was retired: its AI write-back path was their only source.) |
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
   **Settings → Advanced → Autofill coverage → Clear data**. It reports how many rows went
   and it does *not* turn capture off — clearing history and opting out are two
   different decisions, and the button only makes the one you asked for.

### Known gaps — what the fill could not learn

A durable, value-free table (`autofill_widget_gap`) that survives the 50-run trace limit. A row is a widget family hash (the recipe
book's, without its `f:` prefix), the host, the field's shape and an outcome (`cannot_operate`, `unconfirmed`, `user_fixed`,
`missing_technique`) with a count and a last-seen time; the schema is `extra="forbid"` over closed enums. `sw.js` `fill_gaps` posts it
to `POST /api/autofill/gaps` (at most 40 a post, keys whitelisted to the schema's four) only while `telemetryEnabled === true`, so with
the fill log off nothing is posted. It holds hosts, so `DELETE /api/autofill/telemetry` clears it with the rows and runs. It is ranked
in `scripts/fill_trace.py report` (without hosts) and summarised in one line in Settings › Companion › How the Companion applies (`GET /api/autofill/gaps/summary`).
It is local to this copy (sync does not carry it).

### Run trace — how the fill loop decided

Separately from the rows above, a "Saved answers + AI" run builds one `report.trace` in
`shared/fill-loop.js`, and the panel (`panel/actions/fill.js`) sends it once as `fill_trace`. It
records, per field, how the engines decided: the label source, the map / polarity / pick / step decisions
(route, slot, engine, confidence, second opinion, chosen option index), each step as an op with `ms`
and its effect, and the final status. Failed model calls are noted as `{op, ms}`. Each field also reports `changes`, how many times its value changed under the engine (a count, clamped to 99; above 1 is a flicker), and an explore whose committed value the page took back is a `took_back` step (`effectOf`, whitelisted in `sw.js`). An adaptive step's move ids include `search:term`; the term itself is never in the trace or the report. A /map step also names the sentinel the
model chose when it filed the field under one of the six fixed words (`free_text`, `none`, `protected_unanswered`, `history_unanswered`,
`years_unanswered`, `blocked_eeo`; `Sentinel` in `schemas/autofill_fill.py`, `TRACE_SENTINELS` declared in `shared/fill-loop.js` and again in
`sw.js`, each side filtering to the list): a fixed word, never a value, kept by the reasoned and low-stakes routes too, and printed by
`scripts/fill_trace.py`. A /map field routed `none` because the model's top fact fell under that fact's floor also carries that fact's NAME (`top_fact`: a slot name such as
`personal.email`, never a value; the schema's `SLOT_NAME` pattern, up to 120 characters, checked again by `shared/fill-loop.js` `DECISION_CHECKS` and `sw.js` `TRACE_STEP`, an invalid one left out). A field notes its
polarity once (the first answer: later /pick and /step calls on a Yes/No field answer with the same way, recalled
from memory; a recalled way carries `remembered` and the counters skip it). A field keeps at
most 40 steps (the first 20 and the last 20), and any text is cut to 200 characters without
splitting a surrogate pair.

It holds no value. A label or section is blanked, run-wide, when it contains a value the run wrote,
was answered, left over or found committed (`rowKeys` / `siblingKeys` in `shared/fill-loop.js`). Two
things never count: a field's own option texts (a country select answered "United States" would
otherwise blank every label saying so) and a lone checkbox's yes/no. A field's own value blanks its
own label at any length; another field's value blanks a label at 2+ characters when that other
field is typed (text, date, search, popup) and at 4+ otherwise; a word every form uses as an OPTION (Yes, No, True, False, Mobile, Home, Work, Other, None, Cell,
Office, Personal, Business; `COMMON_OPTION_WORDS`) never blanks ANOTHER row's label or option list, so an answer "Mobile" leaves a question that names a company
called Acme-Mobile readable, while the row that holds it still blanks its own label. The page's own option texts and the
chosen option's index are kept on every field, EEO included (owner decision), so a wrong pick can be
read back. A search box has no passive list, so the options its explore showed are kept as `offered` (`fill-loop.js`): a **typed** explore (a city, an employer, a
word of the term: its rows echo what was typed) keeps only their COUNT (`option_count`, no texts); an explore with no term (a popup's click-open, the whole-list re-read) keeps
the texts, screened by the same rule as any option text. The index of a pick is never kept for an explored row. The index counts the field's own `options` list (the inventory's passive list, `o{i+1}`, as stored
in `options`), not the options /pick was offered (those drop placeholder and never-fill rows); it is left out
when the field has no passive list, when the pick was an explored row (explore oids restart at o1, so a row
counts only when its oid and text are the passive option's), or at 250 and over (the schema's bound). An
option text that contains another TYPED field's value (text, date or search, 4+ characters) is blanked,
since a dependent select can list what was typed earlier: only typed siblings screen it (a country chosen
in one select, or a popup's chosen option, must not blank another's list; a typed "Yes" is too short), and a row's own keys never do, so the index still lines up.
No typed or profile string ever sits in a free-text slot. `sw.js` `scrubTrace` then
rebuilds the trace from a whitelist mirroring `app/schemas/autofill_trace.py` (numbers only, anything
the schema would reject dropped), and posts it to `POST /api/autofill/runs` only while
`telemetryEnabled` is `true` — the same switch as above. The backend keeps the newest 50 runs
and folds each into counters with no host and no label; **Clear data** deletes the runs and keeps
the counters. Read them with `backend/scripts/fill_trace.py last|report`, which opens a copy of the
database and refuses the live file.

**The reasoning step's rounds.** A thought posts a second kind of run: `fields` is `[]` and `reasoning` holds up to 3 rounds
(`TraceReasonRound`; `reasonLoop.traceOf` builds it, `sw.js` `TRACE_REASON_ROUND` and the backend schema bound it alike). A round has the model id, `ms`, the
model's note (the same cleaned sentence the card shows, 200 characters), each action as `{type, target, outcome}` (the target a field id or an opaque
`b<i>` / `t<i>` ref; `slot` for `answer_from`, the fact NAME; `technique` for a `retry`, `basis` for a `choose`, each from a closed list; `written` for a write, the answer's LENGTH), the checker's rejection codes, how the
round ended (`stopped`: a reply the checker or the clock ended, or `no_read` / `wall` for an exit before any model call, which still posts a row with no model) and `snapshot`: what the model was shown, without the job's selectors, capped to 30 fields and 8 options each (a snapshot over 120 000
characters is dropped and the round kept). The snapshot is screened in the panel before it is sent or stored (above); the table's backstop (`autofill_reason.redact_trace`, on
`POST /runs`) takes every saved answer and every active base resume's employer, title, school and skill out of its questions, option texts, error lines and the round's note,
each cut to the schema's cap (an option keeps the facts a page lists as its own choices: country, state, EEO, work authorization and preferences). A stored
snapshot can therefore read `[saved answer]` where a page named one of your own values. A reasoning step is a run row of its own, so its rounds count against the
newest-50 `RUNS_KEPT` with the fill runs. The model, the note and the page's own words are the only free text.
`fill_trace.py last` prints the rounds after the fields. `backend/scripts/eval_reason.py` replays the snapshots against other models
(`--models claude-sonnet-5-5,claude-haiku-5-5,gpt-6-luna`, from a database copy or a JSON file), runs the server's own checker and prints the valid
and ask_user rates, the actions chosen, latency, tokens and a cost estimate; it spends your keys' money and is maintainer-run, never in CI.

## Install internals

- **Settings have one home.** `DEFAULTS` in `sw.js` (`backendUrl`, `appUrl`,
  `telemetryEnabled`, `fillMode`) is the one place a default lives; stored values
  in `chrome.storage.sync` override it. The panel and options page load
  `read_settings` rather than copying defaults. The panel writes `fillMode`;
  options writes `backendUrl`/`appUrl`, requiring an http(s) host and optional
  port, with no path, query, fragment or credentials. Writes need no defaults.
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
- **An update under an open tab: a re-run file never depends on a newer export of a load-once file.** Re-injecting runs the guarded files' OLD copy and every unguarded file's
  new one in the tab's same world, so a re-run file that reads at load an `ns.X` only a load-once file publishes (page-reader's `ns.ERROR_HEADING`, live 2026-10-15) gets
  `undefined` after an update and every page read throws ("Page not recognised" over a plain form). The rule: such a read keeps its own copy (`page-reader.js` has its own
  `ERROR_HEADING`; `tests/test_extension_manifest.py` pins both equal) or a fallback (`ns.X ?? …`) or a `typeof ns.X` guard anywhere in the file. A static scan over the
  manifest's content scripts fails on a plain or destructured read of a name past `SHIPPED_ONCE_EXPORTS` (the names the last release already published; a new name is
  never added there to quiet the test). The runtime backstop: when no frame gave a summary and a frame answered with an error that is not "no script listening"
  (`scriptThrew`, `NOT_LISTENING`), the read repeats up to 3 times (`BROKEN_READS`), then the run parks `page_stale`, not `unknown_page`; the card reads "Reload the page: The
  Companion couldn't read this page (usually after an update). Reload the page, then press Resume." (`panel/runs.js`).

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
`MAESTRO_CS_EXTENSION_IDS` only to admit a *different* build, such as a fork
you re-keyed. The variable **replaces** the default, so list every id you want,
comma-separated.

The default also holds the Chrome Web Store build's id,
**`bppkeipififkepldkogmfpkkhoakgndl`**, which Google assigned at the first
upload (admitted from 0.11.1). Store uploads are packed without the pinned
`key` (`scripts/pack_extension.py --first-upload`), and the manifest keeps the
unpacked key rather than the store's, so the two builds keep different ids and
the backend admits both (docs/RELEASING.md, "Chrome Web Store"). A store
install updates itself; only an unpacked one needs Reload.

- The pinned key is a **public** key and identifies the extension; it is not a
  secret and is meant to be committed. The matching private key is not in this
  repo and is not needed to load, run or develop the extension.
- Because the id does not depend on the directory path, **moving your clone
  does not change it**, so the allowlist cannot silently break that way.

## Maintainer notes

- **Panel and content API calls go through the service worker**, because a content script's
  fetch presents the *page's* origin, which the backend's CORS list does not
  admit — and widening it to admit arbitrary ATS hosts is the trade this avoids.
  The panel is an extension page and *could* fetch directly; it routes through
  the same door anyway. Options makes only its own `/health` connection check,
  from the extension origin behind the same backend CORS gate; it sends no
  career data. Only the backend's AI calls leave the machine.
- The panel runs in no page at all; the fill engine runs in **every** frame. One
  dead frame (an ad iframe, a frame that navigated away) does not fail the run,
  and the reason it failed is kept in the console.
- `host_permissions` is broad (`http(s)://*/*`) so the modules are present and
  the panel can reach whatever tab you point it at, without per-site prompts.
  What keeps that cheap is that they do nothing until asked, and that the first
  thing they are asked — the detection read — is synchronous and
  side-effect-free. This is a personal, locally loaded extension — narrow it if
  that bothers you.
- **`tabs` stays.** Without it Chrome omits `tab.url` (and `changeInfo.url`) for
  any tab outside `host_permissions` — `chrome://newtab`, settings, `file://` and other
  non-http(s) pages (an http(s) PDF keeps its url: it is the PDF's own, covered by
  `host_permissions`). `panel.js` rebinds only on a truthy `changeInfo.url`. A bound tab that navigates from a posting to one of those then fires
  `tabs.onUpdated` with a status and no url, `onTab` never runs, and the panel
  keeps the posting it left (`healPosting` sees a loaded preview and does
  nothing). Measured in Chromium, same tab, `http` page to `chrome://version`:
  with `tabs`, `{status: "loading", url: "chrome://version/"}`; without, only
  `{status: "loading"}` and `{status: "complete"}`. A tab SWITCH still unbinds
  (`tabs.get` gives no url, read as `""`), and posting to posting keeps its url
  either way. Dropping the permission needs a deliberate unbind on url-less
  loads first.
- **The per-application Q&A transcript is not in the panel** — a chat log is
  list-shaped, versioned and re-readable, and a 400px rail is the wrong place
  for it. The composer for the question in front of you stays; the header's
  "Open application" is the route to the rest.
- **Two identifiers keep historical names on purpose.** The command key is still
  `toggle-widget`, because Chrome keys a user's rebinding by the command NAME and
  renaming it silently discards every custom binding anyone has made; what a user
  sees is its description, "Open the Maestro CS panel on this page". The
  `widget.session` storage key was the same trade until the pick became a per-tab
  map (`widget.sessions`, above): renaming it would have dropped every live entry,
  stranding a user mid-wizard, so it was read once by the build that renamed it
  (`adoptLegacySession`; the string lives on as `KEY.legacySession` until that
  migration is deleted). `restoreSession`'s
  `if (entry.applicationId)` guard is the condition of writing an
  application-less entry at all. The keys the
  floating card and an earlier panel build left behind (`widget.dock`, `widget.hiddenOrigins`,
  `widget.hiddenGlobally`, `panel.pick`) are unread and unswept.
- The hotkey cannot close the panel: `chrome.sidePanel` has an `open` and no
  counterpart, so the close affordance is the browser's own.
