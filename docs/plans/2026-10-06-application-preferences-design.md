# Application preferences: answers an agent shouldn't have to ask for

Approved by the owner on 2026-10-06 (brainstorming session). Builds on phase 4 (full automation
mode, `docs/plans/2026-10-05-full-automation-design.md`).

## Why

In the first attended pilot apply, the agent stopped mid-form to ask three things: whether to
consent to text messages, whether to add a cover letter, and whether to submit. The third is by
design (an attended apply asks one yes before submit). The first two are Maestro's gaps: the
Companion already answers text-message consent from the "Answer low-stakes questions for me"
switch, but agents can't see that switch, and nothing says whether to include a cover letter.

## Decisions and rejected options

- **A small set of typed preferences, read by agents from the brief.** Chosen.
- Rejected: writing rules as "Your own questions" entries (fuzzy matching, an agent could misread
  a free-text rule, and still no way to produce a letter PDF); per-job choices on each queued job
  (adds a decision to every job, the friction this removes; a per-job override can come later).
- **One low-stakes switch for the Companion and agents,** same list, same "in the job's favor"
  rule. Not a separate agent switch.
- **A cover letter Maestro wrote does not stop automatic submission** in full automation mode; it
  is written from the same resume and career history as the tailored resume, which full
  automation already submits unread.

## Part 1: What the user sets (Settings → Form filling)

- A new **Cover letters** card:
  - **When to include one:** "Skip unless required" (default), "Always write one", or "Never, and
    park the job if it's required".
  - **Tone:** Balanced (default), Enthusiastic, Formal or Concise — the four tones the Q&A tab
    already offers.
- **"Answer low-stakes questions for me"** stays where it is; its copy says it applies to the
  Companion and the user's agents. The list and the rule are unchanged; text-message and
  marketing consent are already on it.
- One stored setting with its own endpoint, like the other settings. Existing installs get the
  defaults, so nothing changes until the user picks something.

## Part 2: What agents see and do

- The **brief** gains an `applying` block: the cover-letter choice, the tone, whether low-stakes
  answering is on, and the low-stakes topics, taken from the same source the Companion's fill
  uses (`autofill_map.low_stakes_scope`) so the two can't drift.
- A new MCP tool **`prepare_cover_letter_upload(application_id)`**: writes the letter in the
  user's tone when the application has none (an existing or user-edited letter is kept), renders
  its PDF and stages it for upload exactly like the resume (`prepare_application_pdf_upload`).
- The shared apply instructions (`agent-apply-execution`) get explicit rules:
  - a cover-letter field follows the setting; the upload is recorded as slot `cover_letter`;
  - with the low-stakes switch on, the listed topics are answered in the job's favor; with it
    off, optional ones stay blank and required ones go to the user (attended) or park the job
    (full automation);
  - never ask the user for anything these settings answer;
  - an attended apply still asks one yes before submit.

## Part 3: Full automation, final review, failures

- `get_final_review` gains which cover letter went: written by Maestro, the user's own edit, or
  none.
- Plain low-stakes answers (text and marketing consent, how the user heard, how to contact them)
  never park a job. Low-stakes topics that are also knock-out questions under phase 4's rule
  (relocation, on-site work, start date) still raise `guessed_screening` when inferred and park
  the job: knock-outs auto-submit only from a saved answer. Saving "Willing to relocate" and a
  start date in Autofill removes those parks. This rule is kept, not loosened.
- "Never" and a required letter: the job goes to Needs you with the reason "needs a cover
  letter".
- The letter can't be written (no AI key, model error): a required letter sends the job to Needs
  you; an optional one under "Always" is left out and the run notes say so.

## Testing and docs

Setting defaults, round trip and rejected values; the brief's `applying` block; the agents'
topics equal the Companion's by test; the tool writes once, keeps an edit, uses the tone, renders
and stages; the skill rules pinned word for word; a browser check of the card. Docs: the settings
doc, the MCP tool list, one SYSTEM.md line (trimmed to fit the cap).

## Roles

Sol implements task by task; Opus reviews each task, as in phases 3 and 4.
