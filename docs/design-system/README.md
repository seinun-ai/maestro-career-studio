> **What this folder is.** The Maestro Career Studio design system, as files: this brand book,
> `tokens.json` (every token with its usage note), `migration.md` (old class → token), and one folder
> per component under `components/` with its guidelines (`README.md`) and a static preview
> (`preview.html`, open it in a browser). Read this file first, then the component you are building with.
> The values live in `frontend/app/globals.css`; when the two disagree, the stylesheet is right and this
> folder needs updating. A browsable copy with light and dark previews is the Maestro Career Studio
> design system on claude.ai: https://claude.ai/artifact/VxnjspbkP71d8Z183QqrB7 (private to its owner
> unless shared). The logo files are in `docs/assets/brand/`.

Maestro Career Studio is a desktop web app for a job search: it tracks jobs, tailors resumes to job descriptions, scores them and keeps a career history. The interface is dense, calm and plain-spoken, built on Material 3's roles and scales with Maestro's own blue, the Geist typeface and Lucide icons. Build for 1024px and wider; check at 1280 and 1024.

## Content fundamentals

- **Plain words.** No abbreviations and no internals. Say "job description", never "JD"; "Career history", never "KB". A term that must stay (ATS) is explained once where it first appears.
- **One word per thing, on every surface.** Jobs (the page), Add job, Save job, Agent inbox, Career history, item, bullet, Base resumes, Quick tailor, Create PDF, Update score, Hide / Show, Archive / Restore. Do not introduce a synonym.
- **Sentence case everywhere**, including buttons, titles and group headings: "Import resumes and documents". No all-caps headings.
- **Labels** are as short as they can be, with no trailing colon. **Hints** are one short sentence and carry what the label cannot (a consequence, a default, a constraint); delete a hint that restates the label. A section's explanation that need not be seen before acting sits in a `HintTip` (an Info button beside the title, the sentence in its tooltip); a consequence stays a visible line.
- **No placeholder in a blank field.** No example value, no instruction. The only exception is a short prompt in a search box: "Search company or role…".
- **No em dash as a clause joiner.** Use two sentences or a colon. The dash stays for an empty cell and inside composed labels.
- **Address the person as "you"; the app is not "we".** Say what happened and what to do: "Enter a number, such as 2."
- **Be honest about state.** Never say saved while a save is pending; a failed load is its own state, not an empty one; a cut-off list says so at its end.
- Page subtitles are one clause: "Jobs you saved and every application." A page built on the tiers (see Shape) has none: its Lead says what matters.
- No emoji.

## Color

Use roles, never a palette shade or a hex. Every fill has a named text partner; use the pair.

| Fill | Text on it | Use for |
| --- | --- | --- |
| `background` | `foreground`, `muted-foreground` | The page |
| `card`, `popover` | `card-foreground`, `popover-foreground` | Cards; menus and dialogs |
| `primary` | `primary-foreground` | The one filled action in a view; links and selected controls as text |
| `primary-container` | `on-primary-container` | The Add job FAB; information status (Applied, Proposed) |
| `secondary-container` | `on-secondary-container` | Tonal buttons and badges, the current sidebar row, a selected toggle or chip |
| `success-container` | `on-success-container` | Accepted, passed, added |
| `warning-container` | `on-warning-container` | Interviewing, a caution |
| `attention-container` | `on-attention-container` | Needs you |
| `tertiary-container` | `on-tertiary-container` | An offer, an Ask |
| `error-container` | `on-error-container` | Rejected, removed, must fix |
| `resume-container` | `on-resume-container` | The footer of a card that stands for one base resume (see below) |

- A status as plain text, an icon or a dot on a surface uses the role itself: `success`, `warning`, `attention`, `tertiary`, `destructive`.
- Every pair above, and every text role on every surface, holds at least 4.5:1 in light and dark; the repo's tests compute it from the tokens.
- Status never rides on color alone: the chip's word, an icon or a Check says it too.
- A link's color is `primary`. `bg-primary/N` with `text-primary` is not a component fill, and neither is `bg-background/N`: take the container pair, or the next surface step up. The exceptions, each named in the allow-list in `test_frontend_color_roles.py`: a bar that floats over scrolling content, a pill over an image, the hover tint on a solid primary fill (Button, Badge), and the editor's resize handle on a transparent fill.
- Hover on a container is its pre-mixed 8% state layer (`primary-container-hover`, `secondary-container-hover`); a call site never picks an opacity.
- `chart-1` to `chart-6` are for chart series only, in their fixed order: blue, orange, teal, violet, ochre, slate. They are OKLCH near one lightness per theme, with no red or green series, so a chart never reads as good or bad, and each holds 3:1 on `card` in light and dark. One series is `chart-1`; the six are only for comparing. `brand-blue` and `brand-yellow` are for the mark only.
- **Company monograms are neutral**: every company's initial sits on `surface-container-highest` with `foreground`, so the base resume square is the only hue in a row and a status chip the only state colour.
- **Base resume color is identity, never state.** Each base resume has one hue, picked at random from the free presets when it is made and changeable in its Target. Draw it as a square (`ResumeSwatch`) beside the resume's name, never alone and never as a round pill or dot (round is status). The tones come from the hue (`resume`, `resume-container`, `on-resume-container`), so any hue holds contrast.
- **Only a card that stands for one base resume** (its gallery card, its score card) carries the color as a 6px top band; the gallery card also tints its footer with `resume-container`, and the score card keeps its body as it is. Rows, pages and the sidebar never take it. PDFs never carry it.
- **Charts split by base resume** color each series by its resume. Every other chart keeps `chart-1` to `chart-6`.

## Surfaces and elevation

- Separate surfaces by tone first. In light: `card` is the lightest, the page (`background`) sits just under it, then `surface-container-low`, `surface-container`, `surface-container-high`, `surface-container-highest`. Dark runs the same names from darkest up.
- Use `surface-container-low` for stat tiles, hovered rows and quiet panels; `surface-container` for a neutral chip or a progress track. Never write `bg-muted` with an opacity.
- `canvas` is only the ground behind a rendered resume page.
- Shadows are for what floats: `shadow-level1` a hovered FAB or chip, a focused skip link, a modal sheet; `shadow-level2` menus, popovers, rich (chart) tooltips, sticky bars, the PDF page pill and a dragged row; `shadow-level3` dialogs and toasts. Cards, tiles, tables, plain tooltips and controls at rest have none; the one exception is the Lead card, which floats a little on `shadow-level1`.

## Typography

- One family, Geist; Geist Mono for code and the template editor.
- Use the scale as one utility; never pair a size with a weight by hand.

| Style | Use |
| --- | --- |
| `title-large` at weight 500 | The page title |
| `title-medium` | A card or dialog title |
| `title-small` | A table header, a group heading, a row's primary name |
| `body-medium` | Running text, field values, descriptions |
| `body-small` | Hints, metadata, table secondary lines |
| `label-large` | Buttons and field labels |
| `label-medium` | Chips, badges, small buttons, sidebar group labels |
| `label-small` | A count or a grade chip |
| `headline-small` | A grade or a large stat |

- Wrap reading text at 65 characters (`max-w-[65ch]`).
- Numbers that line up use tabular numerals.
- Judged resume text is upright `body-medium` in `foreground`: never italic, grey or cut to one line.

## Shape

One corner per kind of thing: `radius-corner-2xs` (2px) the resume square; `radius-corner-xs` (4px) menus, tooltips, the checkbox; `radius-corner-sm` (8px) buttons, inputs, selects; `radius-corner-md` (12px) cards, tiles, tables, callouts; `radius-corner-lg` (16px) the FAB, a sheet's open edge and the Lead card; `radius-corner-xl` (28px) dialogs; `radius-full` chips, badges, segmented toggles (the outline and its segments), the search field, every sidebar row (hover and current share the shape).

**A page has three tiers: Lead, Also, Folded.** Each page has one thing that matters most, a few secondary things, and the advanced rest folded away.

- **Lead**: the one thing that matters most, in a `LeadCard` at the top (`radius-corner-lg`, `card`, `p-7`, `shadow-level1`). An eyebrow in `primary` names it, and its one action is the view's one filled button. One per page.
- **Also**: a few secondary things under a small heading, as plain cards or rows that rest flat, with tonal, outline or text actions. A row's next move is a `NextStep`.
- **Folded**: advanced or rare things last, each a `Fold` row (a chevron, a title and a short summary on the right) that opens in place.

## Selection and state

- **Selected in a set** (a toggle, a filter chip, a segment, an option card): `secondary-container` (its hover is `secondary-container-hover`), a leading Check and `aria-pressed`. The tonal fill alone is too faint to say "on". An option card may keep its `primary` border.
- **A color swatch** (the base resume color picker) has no tonal fill to give, so its selected state is a Check and the solid 2px `ring` outline, with its focus drawn as a separate outer ring.
- **Current in a list or nav** (a sidebar row, the open chat): `secondary-container`, weight 600 and `aria-current`, with no Check.
- **One filled button per view.** Everything else is tonal, outline, ghost or text-style. A dialog's confirm is filled because the dialog is its own view.
- **Focus is the solid `ring`**, never a translucent one: a solid 1px `ring` border with a 3px halo on controls, or a 2px `ring` outline. A ring offset names its surface.
- **A button whose request is running** takes `pending`: a spinner replaces its icon, `aria-busy` is set, presses are ignored and focus stays on it (a natively disabled button would drop focus to the page). Some of these swap the label too (Save job "Saving…", the job header's Queue "Queueing…", "Updating scores…", "Approving…", "Adapting…", "Answering…", "Writing…", "Applying…"); the rest keep it and show the spinner only (the studios' Save, the bulk Queue, the Skip confirm).
- **A field warning** is the amber sibling of an error: an icon and words under the control (`TriangleAlert` in `warning` for a warning, `CircleX` in `destructive` for an error), and `data-warning` turns the border and halo amber. It never blocks a save and shows on blur. See TextField.
- Pending work dims its section (`data-pending`); a pressed button scales to 0.97.
- Disabled is 50% opacity and no pointer events.

## Layout and spacing

- Tailwind's 4px scale. `space-2` (8px) between sibling controls, `space-4` (16px) inside and between cards, `space-6` (24px) for page padding and between page sections.
- Every page is one `PageShell` with one `PageHeader`; the page owns `<main>`.
- Controls are compact: 32px by default, 28px small, 24px extra small; chips 24px; table header 40px.
- The sidebar is 256px; its top-left corner belongs to the reveal pill.
- Long lists keep their toolbar and column names in view; a list that drags also has a click-only move.

## Motion

- `ease-standard` with `duration-short3` (150ms) for hover and selection, `duration-short4` (200ms) for a control changing shape.
- Things entering use `ease-emphasized-decelerate`; leaving, `ease-emphasized-accelerate`.
- Lists rise in with `animate-fade-rise`; skeletons use `animate-shimmer`.
- **A status that changes** cross-fades: the old label fades out and the new one in, with a 2px blur between (`animate-status-out` and `animate-status-in`, 200ms, strong ease-out), and the chip holds the wider label's width while they cross.
- **Confirm in place** with `animate-confirm`: one soft `ring` pulse (400ms) on the thing that changed, such as a status chip once its new value has settled, never before its cross-fade ends. It is a registered `@utility`, so it takes variants (`data-confirm:animate-confirm`); a plain class under a variant compiles to nothing.
- **A row that leaves its list** wraps in `.collapse-exit` with one child and sets `data-leaving`: it fades and its height closes (200ms, `ease-emphasized-accelerate`), so the rows below slide up.
- **A number that changes** counts to its new value with `useCountUp` (400ms; no counting when reduced motion is on), or rolls with `NumberRoll`: each digit is a 0–9 column that slides on `translate` over `ROLL_MS` (400ms, strong ease-out), so only the digits that changed move. With reduced motion it is the plain number. Neither announces; the parent holds a live region if the change should be spoken.
- **The AI is working** shows `WorkingDots` beside the words for what it does ("Writing your cover letter"): three `primary` dots that rise in turn on a 900ms loop, with a `role="status"` that is in the page before its words arrive, so they are spoken. It replaces a spinner where the work is shown; with reduced motion the dots hold still.
- **Saved, then settles**: `CheckDraw` draws the done mark's tick once (`animate-check-draw`, 300ms, strong ease-out), then the caller holds it 1.2s and settles. It is a registered `@utility`, so it takes variants. With reduced motion the tick is drawn at once.
- **A row that opens into its page** morphs: a Jobs row's monogram and title travel to the job page's header (a View Transition, 250ms, strong ease-out), and back. Only that pair is named (`JobMorph`, `default="none"`), so nothing else moves and nothing slides; a row opened from the keyboard opens without it. With reduced motion the pair fades in place.
- **Budget:** nothing runs longer than 400ms except the 1.2s hold of a confirmation ("Copied", "Saved") before it settles, and the two loops that say "still going" (the skeleton shimmer, 1.4s, and the working dots, 0.9s). No bounce, no overshoot. The timings live in `lib/motion.ts` (`CONFIRM_HOLD_MS`, `CONFIRM_MS`, `ROW_EXIT_MS`, `ROLL_MS`, `FADE_MS`); import them, never re-declare. Frequent and keyboard actions do not animate.
- Transition lists name the CSS `translate`, `scale` and `rotate` properties (`transition-[opacity,translate]`), never `transform`: Tailwind v4's `translate-*` and `scale-*` set those properties, so a `transform` list jumps.
- With reduced motion requested, the global rule in `globals.css` stops CSS transforms and animations and opacity changes stay; `useCountUp` and `NumberRoll` check `prefers-reduced-motion` themselves in JS and show the value.

## Iconography

- Lucide icons (`lucide-react`), outline style, 2px stroke, drawn in `currentColor`.
- 16px beside text, 14px in small buttons, 12px in chips and extra-small buttons, 32px in an empty state.
- An icon-only button has an `aria-label`; an icon beside its label is `aria-hidden`.
- An icon never carries meaning alone; a word sits beside it or in its accessible name. Colour never carries it alone either.
- **One concept, one glyph.** `frontend/lib/concept-icons.ts` (`CONCEPT_ICONS`) is the register: each concept owns one icon app-wide, no two concepts share one, and `test_frontend_concept_icons.py` pins it. Reach for the register before importing a Lucide icon at a call site; a new meaning is a new key.
- Meanings that are easy to confuse: `none` (`Minus`) is "nothing here / no change" (not listed, not stated, same, flat); `cannot` (`Ban`) is "can't confirm / they can't"; `unknown` (`CircleHelp`) is only unknown; `increase` / `decrease` (`TrendingUp` / `TrendingDown`) are "went up / went down", while sort direction is `ArrowUp` / `ArrowDown` and not a concept; `email` (`Mail`) is an address and `coverLetter` (`ScrollText`) a cover letter; `FileText` means a resume only and a document or attachment is `Paperclip`; `queue` is `SendHorizontal`, `approve` (Keep it, Approve) `ThumbsUp`, `skip` `SkipForward`.
- `agentInbox` (`Bot`) is the Agent inbox and also connected agents, always with the agent's name and never a logo. A sync mark draws the bot's copy with it too ("With your bot") and your laptop's copy with `laptop` (`Laptop`); a locked-by-sync notice leads with `locked`. `ai` (`Sparkles`) is AI-made, `you` the person, `assistant` the Assistant.
- **Done is `CircleCheck` in `text-success`.** `Check` means selected, and only that. A few older done sites still draw `CircleCheck` in `text-primary` (the setup checklist's row icon, the Career history timeline, the gap page's closed-session state) and some non-selected `Check` uses remain; they are a ratchet, converted when their file is touched, not swept.

## Logo

The mark is an M of two folded blades in `brand-blue` and `brand-yellow`; the lockup adds the "maestro" wordmark. Files and rules are under Assets, Logos. In the app use `MaestroMark` and `MaestroLogo` from `components/brand-logo.tsx`.

## Components

Each component page has a live preview in light and dark, what you provide, and its source file.

- Actions: Button
- Status: Badge, StatusChip
- Selection: SegmentedToggle, FilterChips
- Inputs: TextField, SelectionControls
- Tiers: LeadCard (Lead) and Fold (Folded) from `components/ui/`
- Containment: Card, StatTile
- Navigation: Sidebar, PageHeader, Tabs
- Data: JobsTable, HealthSummary, NextStep (a row's next move)
- Visual primitives (nine): DotMeter, ScoreBar, SegmentedBar, ProgressCount, DeltaChip, ActorChip, Sparkline and DayStrip from `components/visual/`, and StatusDot from `status-chip.tsx`, which also exports `LaneDot` for proposal statuses
- Motion: NumberRoll, WorkingDots and CheckDraw from `components/visual/`
- Communication: Callout, EmptyState, JudgedText, Dialog
- Base resume color: ResumeSwatch and ResumeTag from `components/visual/`, and ResumeColorPicker from `components/base-resumes/`

## Not synced

Matches the app after all eight token steps and the six approved interface changes in `docs/plans/2026-10-02-design-system-tokens.md` (branch `claude/ds-steps`, on `main` at `5baf568c`); the repo's tests pin each rule. Skipped variables: `primary-container-hover` and `secondary-container-hover` (they are `color-mix()` values). Fonts: Geist and Geist Mono load from Google Fonts; no font files are stored. Components: previews are static HTML that uses the repo's own Tailwind classes, compiled with its `globals.css`; the React components were not built into a bundle, so menus, popovers and dialogs do not open. Not previewed: the nine visual primitives (DotMeter, ScoreBar, SegmentedBar, ProgressCount, DeltaChip, ActorChip, Sparkline, DayStrip, StatusDot), ResumeSwatch, ResumeColorPicker, the tiers (LeadCard, Fold), NextStep and the motion primitives (NumberRoll, WorkingDots, CheckDraw) have a README and no `preview.html`, and the Button `pending` state and the field warning appear in their READMEs only; the motion utilities are described, not demonstrated. The claude.ai artifact copy was synced with the base resume color work on 2026-10-13 (README, tokens.json and the component READMEs) and does not have the design refresh's tiers, motion primitives, OKLCH chart series or neutral monograms yet; its `bundle.css` was not regenerated, so no preview draws the `resume` tones, the `radius-corner-2xs` square or the sticky dialog footer, its chart tokens are the old hexes, and the JobsTable preview's neutral monogram reads `--surface-container-highest` through an inline style until the bundle has the class. Not yet covered: dropdown menu, popover, sheet, tooltip, slider, sortable list, chip input, the resume studio, gap-analysis cards, the Assistant, charts and the settings cards.
