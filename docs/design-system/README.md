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
- **Labels** are as short as they can be, with no trailing colon. **Hints** are one short sentence and carry what the label cannot (a consequence, a default, a constraint); delete a hint that restates the label.
- **No placeholder in a blank field.** No example value, no instruction. The only exception is a short prompt in a search box: "Search company or role…".
- **No em dash as a clause joiner.** Use two sentences or a colon. The dash stays for an empty cell and inside composed labels.
- **Address the person as "you"; the app is not "we".** Say what happened and what to do: "Enter a number, such as 2."
- **Be honest about state.** Never say saved while a save is pending; a failed load is its own state, not an empty one; a cut-off list says so at its end.
- Page subtitles are one clause: "Jobs you saved and every application."
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

- A status as plain text, an icon or a dot on a surface uses the role itself: `success`, `warning`, `attention`, `tertiary`, `destructive`.
- Every pair above, and every text role on every surface, holds at least 4.5:1 in light and dark; the repo's tests compute it from the tokens.
- Status never rides on color alone: the chip's word, an icon or a Check says it too.
- A link's color is `primary`. `bg-primary/N` with `text-primary` is not a component fill.
- Hover on a container is its pre-mixed 8% state layer (`primary-container-hover`, `secondary-container-hover`); a call site never picks an opacity.
- `chart-1` to `chart-6` are for chart series only, in their fixed order. `brand-blue` and `brand-yellow` are for the mark only.

## Surfaces and elevation

- Separate surfaces by tone first. In light: `card` is the lightest, the page (`background`) sits just under it, then `surface-container-low`, `surface-container`, `surface-container-high`, `surface-container-highest`. Dark runs the same names from darkest up.
- Use `surface-container-low` for stat tiles, hovered rows and quiet panels; `surface-container` for a neutral chip or a progress track. Never write `bg-muted` with an opacity.
- `canvas` is only the ground behind a rendered resume page.
- Shadows are for what floats: `shadow-level1` a hovered FAB or chip, a focused skip link, a modal sheet; `shadow-level2` menus, popovers, rich (chart) tooltips, sticky bars, the PDF page pill and a dragged row; `shadow-level3` dialogs and toasts. Cards, tiles, tables, plain tooltips and controls at rest have none.

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

One corner per kind of thing: `radius-corner-xs` (4px) menus, tooltips, the checkbox; `radius-corner-sm` (8px) buttons, inputs, selects; `radius-corner-md` (12px) cards, tiles, tables, callouts; `radius-corner-lg` (16px) the FAB and a sheet's open edge; `radius-corner-xl` (28px) dialogs; `radius-full` chips, badges, segmented toggles (the outline and its segments), the search field, every sidebar row (hover and current share the shape).

## Selection and state

- **Selected in a set** (a toggle, a filter chip, a segment): `secondary-container`, a leading Check and `aria-pressed`. The tonal fill alone is too faint to say "on".
- **Current in a list or nav** (a sidebar row, the open chat): `secondary-container`, weight 600 and `aria-current`, with no Check.
- **One filled button per view.** Everything else is tonal, outline, ghost or text-style. A dialog's confirm is filled because the dialog is its own view.
- **Focus is the solid `ring`**, never a translucent one: a solid 1px `ring` border with a 3px halo on controls, or a 2px `ring` outline. A ring offset names its surface.
- **A button whose request is running** takes `pending`: a spinner replaces its icon, `aria-busy` is set, presses are ignored and focus stays on it (a natively disabled button would drop focus to the page). Some of these swap the label too ("Saving…", "Updating scores…", "Approving…", "Adapting…", "Answering…", "Writing…"); the rest keep it and show the spinner only.
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
- **Confirm in place** with `animate-confirm`: one soft `ring` pulse (400ms) on the thing that changed, such as a status chip after its value changed. It is a registered `@utility`, so it takes variants (`data-confirm:animate-confirm`); a plain class under a variant compiles to nothing.
- **A row that leaves its list** wraps in `.collapse-exit` with one child and sets `data-leaving`: it fades and its height closes (200ms, `ease-emphasized-accelerate`), so the rows below slide up.
- **A number that changes** counts to its new value with `useCountUp` (400ms; no counting when reduced motion is on).
- **Budget:** nothing runs longer than 400ms except the 1.2s hold of a confirmation ("Copied", "Saved") before it settles. No bounce, no overshoot. The three timings live in `lib/motion.ts` (`CONFIRM_HOLD_MS`, `CONFIRM_MS`, `ROW_EXIT_MS`); import them, never re-declare.
- Transition lists name the CSS `translate`, `scale` and `rotate` properties (`transition-[opacity,translate]`), never `transform`: Tailwind v4's `translate-*` and `scale-*` set those properties, so a `transform` list jumps.
- With reduced motion requested, transforms and animations stop and opacity changes stay; the global rule in `globals.css` is the one switch.

## Iconography

- Lucide icons (`lucide-react`), outline style, 2px stroke, drawn in `currentColor`.
- 16px beside text, 14px in small buttons, 12px in chips and extra-small buttons, 32px in an empty state.
- An icon-only button has an `aria-label`; an icon beside its label is `aria-hidden`.
- An icon never carries meaning alone; a word sits beside it or in its accessible name. Colour never carries it alone either.
- **One concept, one glyph.** `frontend/lib/concept-icons.ts` (`CONCEPT_ICONS`) is the register: each concept owns one icon app-wide, no two concepts share one, and `test_frontend_concept_icons.py` pins it. Reach for the register before importing a Lucide icon at a call site; a new meaning is a new key.
- Meanings that are easy to confuse: `none` (`Minus`) is "nothing here / no change" (not listed, not stated, same, flat); `cannot` (`Ban`) is "can't confirm / they can't"; `unknown` (`CircleHelp`) is only unknown; `increase` / `decrease` (`TrendingUp` / `TrendingDown`) are "went up / went down", while sort direction is `ArrowUp` / `ArrowDown` and not a concept; `email` (`Mail`) is an address and `coverLetter` (`ScrollText`) a cover letter; `FileText` means a resume only and a document or attachment is `Paperclip`; `queue` is `SendHorizontal`, `approve` (Keep it, Approve) `ThumbsUp`, `skip` `SkipForward`.
- `agentInbox` (`Bot`) is the Agent inbox and also connected agents, always with the agent's name and never a logo. `ai` (`Sparkles`) is AI-made, `you` the person, `assistant` the Assistant.
- **Done is `CircleCheck` in `text-success`.** `Check` means selected, and only that. A few older done sites still draw `CircleCheck` in `text-primary` (the setup checklist's row icon, the Career history timeline, the gap page's closed-session state) and some non-selected `Check` uses remain; they are a ratchet, converted when their file is touched, not swept.

## Logo

The mark is an M of two folded blades in `brand-blue` and `brand-yellow`; the lockup adds the "maestro" wordmark. Files and rules are under Assets, Logos. In the app use `MaestroMark` and `MaestroLogo` from `components/brand-logo.tsx`.

## Components

Each component page has a live preview in light and dark, what you provide, and its source file.

- Actions: Button
- Status: Badge, StatusChip
- Selection: SegmentedToggle, FilterChips
- Inputs: TextField, SelectionControls
- Containment: Card, StatTile
- Navigation: Sidebar, PageHeader, Tabs
- Data: JobsTable, HealthSummary
- Visual primitives (eight, from `components/visual/` plus `StatusDot` and `LaneDot` in `status-chip.tsx`): DotMeter, ScoreBar, SegmentedBar, ProgressCount, DeltaChip, ActorChip, Sparkline, StatusDot
- Communication: Callout, EmptyState, JudgedText, Dialog

## Not synced

Matches the app after all eight token steps and the six approved interface changes in `docs/plans/2026-10-02-design-system-tokens.md` (branch `claude/ds-steps`, on `main` at `5baf568c`); the repo's tests pin each rule. Skipped variables: `primary-container-hover` and `secondary-container-hover` (they are `color-mix()` values). Fonts: Geist and Geist Mono load from Google Fonts; no font files are stored. Components: previews are static HTML that uses the repo's own Tailwind classes, compiled with its `globals.css`; the React components were not built into a bundle, so menus, popovers and dialogs do not open. Not previewed: the eight visual primitives (DotMeter, ScoreBar, SegmentedBar, ProgressCount, DeltaChip, ActorChip, Sparkline, StatusDot) have a README and no `preview.html`, and the Button `pending` state and the field warning appear in their READMEs only; the new component pages and the motion utilities are not in the browsable artifact until it is republished. Not yet covered: dropdown menu, popover, sheet, tooltip, slider, sortable list, chip input, the resume studio, gap-analysis cards, the Assistant, charts and the settings cards.
