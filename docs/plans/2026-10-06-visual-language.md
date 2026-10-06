# Visual language Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (or superpowers:executing-plans)
> to implement this plan task by task. Sonnet 5.5 implements, Opus 5.5 reviews each task (owner's routing).

**Goal:** Make Maestro readable at a glance. Icons, colour roles and small meters replace repeated or
numeric words. Size and position show what matters most. Every action answers, and small motion confirms
it.

**Architecture:** One concept-to-icon register (`lib/concept-icons.ts`) and eight small visual primitives
(`components/visual/`) with pure, node-tested helpers (`lib/visual.ts`). Two state primitives: Button
`pending` and Field `error`/`warning`. A few motion utilities in `app/globals.css`. These are then applied
surface by surface. The Companion side panel gets the same vocabulary in plain JS. There is one backend
change: a tracker score field.

**Tech stack:**
- Next.js 16, React 19 and Tailwind v4 tokens (`app/globals.css`), with Base UI and shadcn
- lucide-react 1.48 and Sonner 2
- pytest source pins in `backend/tests/test_frontend_*.py`, and `node --test` for `lib/*.test.ts`, run from
  pytest through `tests/node_ts.py`
- MV3 extension (`extension/panel/`)

**Branch:** `claude/ui-ux-icons-visual-research-6195e9` (from main `f46cd5c9`).
- Commit once per task, locally.
- **Do not push** and open no PR until the owner says so (design-system batching rule).

**Verified against the code** in two read-only passes. Every finding was folded into the task text: one
blocker (the panel test harness cannot build an svg; Task 28) and about two dozen existing pins and facts.
- **The pin line numbers** (`file:NNN`) are from the plan's base commit. Re-locate each by its quoted text.
- **"Existing pins to rewrite"** lists in each task are known, not exhaustive. Run each surface's pin files
  before committing.

**Background (local only, not in git):** `docs/ux/2026-10-05-visual-language-research.md` and the artifact
https://claude.ai/artifact/HPybSXXgERmPV61ApAvyuL. This plan is self-contained; the research is the "why".

---

## Goal Card

Goal: The owner wants the app to read faster. Some text gets replaced by icons and colourful
differentiation, so state is understood visually with fewer words. The owner then added three checks:

- hierarchy (size, position and contrast show what matters most)
- states and feedback (every action responds; buttons and inputs have all their states)
- micro-interactions (small animations that confirm an action, like a "Copied" chip)

Principles:
- **An icon never stands alone** (a word beside it, or its accessible name), and **colour never stands
  alone**. Words get shorter by deleting repeats and moving teaching sentences into a tooltip or
  `aria-describedby`, never by removing a label a task needs.
- **One meaning per icon and per colour role** across the app, held in one register and pinned by tests.
- **Volume follows the need to act.** Good news is quiet, a conflict is loud, and attention means Needs you
  only.
- **Design-system tokens only.** No new dependency (no motion library) and no palette shades. Every graphic
  has an accessible name.

Non-goals:
- Copy rewrites beyond what a visual replaces.
- Phone widths (the app is 1024px and up).
- New features.
- State-machine or API changes, except the one tracker score field (Task 25).
- Sweeping every site of an old pattern when only the named ones are in scope. Examples: all 63 alpha fills,
  all 98 hand-written disabled classes. Ratchet those instead.

Autonomy: **peer** (Opus 5.5 plans; Sonnet 5.5 executes):

- **May adapt HOW** when the repo differs from this plan: a line moved, a name differs, a test helper
  already exists. Log every adaptation in the task's commit body as `Deviation: <what> — <why>`.
- **Escalate with a deviation note before acting** if a change touches scope, an interface another task
  uses, or a Goal Card line. The note says what was planned, what was found, the proposed change, and the
  Goal Card line behind it.
- **Never widen scope on your own.** Suggestions to improve the plan are welcome in the task report.

## Owner decisions (2026-10-06: "go with your recommendations")

| # | Question | Decision |
|---|---|---|
| D1 | Glyph for connected agents | `Bot` + the agent's name, from `lib/agent-name.ts`, everywhere. Never a client's logo. |
| D2 | Approve-type actions | Off `Check`. **Queue** = `SendHorizontal` (already "Queue in Agent inbox"). **Keep it** and **Approve** = `ThumbsUp`. `Check` = selected only. `CircleCheck` = done (a state). |
| D3 | Requirement level | Required = filled primary (`default`), Preferred = `tonal`, Mentioned = `outline`, everywhere. No red. |
| D4 | Weak subscores | A "Weakest" word on the lowest subscore only. No thresholds and no warning colour on scores. |
| D5 | Status chip in single-status lanes | Hidden in To review, Queued and Applying (the lane heading says it). Kept in History and Needs you. |
| D6 | Tracker ATS column | Yes. One backend field each on `ApplicationSummary` and `JobSummary` (Task 25). |
| D7 | Company logos | No. Monograms stay the only company image (privacy). Not built. |
| D8 | Undo instead of confirm | **Undo where the server can already reverse the change:** Approve bullet (PATCH `state: "draft"`) and Archive base resume (`/unarchive`). **Skip keeps its reason dialog** and gains a success toast: `rejected` is terminal and writes a `ConsentEvent` (`services/proposals.py` `ALLOWED`), so an Undo would change the proposal state machine (non-goal). Queue gets a toast and no Undo, for the same reason (`accepted` has no edge back to `pending_review`). |
| D9 | Motion budget | No bounce. Nothing longer than 400ms except the 1.2s "Copied" hold. The existing global reduced-motion rule (`globals.css:455`) stays the switch. |

Further decisions carried from the research (no question was needed):

- **Analyze gaps:** `ScanSearch`. Tailor resume keeps `Wand2`.
- **Drafts to review:** `FilePen`.
- **Add to career history:** `BookPlus`.
- **Uploaded document and attachment:** `Paperclip`.
- **Create PDF:** `FileOutput` everywhere.
- **More actions:** `Ellipsis`.
- **Work authorization and OPT stat labels:** `IdCard` and `School`.
- **Job-facts chip row:** `Layers`.
- **Skills heading:** `Tags`.

---

## How to verify (every task)

- **Setup (once).** Run `cd frontend && npm ci`; a worktree has no `node_modules`. Then confirm every icon
  name used below exists:

  ```bash
  ls frontend/node_modules/lucide-react/dist/esm/icons/ | grep -E '^(ellipsis|thumbs-up|scan-search|file-pen|book-plus|id-card|school|layers|tags|send-horizontal|circle-dashed|chevrons-up|trending-up|trending-down|calendar-clock|hand|text-quote|folder-git-2|skip-forward|file-input|merge)\.js$' | wc -l
  ```

  Expect 21. A missing name is a deviation note, not a silent swap.
- **Backend pins** (from `backend/`):

  ```bash
  /opt/anaconda3/bin/python3 -m pytest tests/<file>.py -q
  ```

  The full suite always runs with xdist:

  ```bash
  /opt/anaconda3/bin/python3 -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile
  ```
- **Node tests** (from `frontend/`): `node --test lib/<name>.test.ts`. Local node is 26. CI runs them through
  `backend/tests` with `run_node_test`.
- **Frontend gates** (from `frontend/`): `npx tsc --noEmit` and `npm run lint` on every task; `npm run build`
  at the end of each wave.
- **Slop ratchet** (from the repo root), at wave ends:

  ```bash
  python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend
  ```

  Also `check backend` for Task 25 and `check extension` for Tasks 28–29. Name every surface in the claim.
  Re-baseline `complexity_hotspots` with a reason; never re-baseline duplication.
- **Browser check** at the end of each wave:
  - At 1280 and 1024, light and dark, on a **fresh stack** with a snapshot of the live database. Use the
    recipe in memory "worktree-verification-recipe": uvicorn on :8765, `next dev` on :3100, the DB copied
    with `sqlite3 … ".backup"`.
  - **Never** verify against the Docker compose stack.
  - **Never** open the live DB file from the host while the container runs.
  - **Ask before using the owner's API key.**
- **Existing pins may break on purpose.** Several pin today's strings or classes, for example "Nothing rules
  you out" and the `REQUIREMENT_VARIANTS` map. When a task changes one, update the pin in the same commit
  and say so in the commit body. Never delete a pin to get green; rewrite it to the new truth.
- **Docs move with the code.** `docs/frontend-conventions.md`, `docs/design-system/README.md` and component
  READMEs change in the same commit as the behaviour, in present tense, with no dates (SYSTEM.md header
  contract).

## Waves and dependencies

Each wave ends with the build, the slop check, a browser pass and an Opus review of the wave.

| Wave | Tasks | Depends on |
|---|---|---|
| 1 Foundations and hygiene | 1, 2, 3, 4 | — |
| 2 States, feedback, motion | 15 first, then 5, 6, 7, 8, 9, 10, 11, 12, 13 | 1 |
| 3 Visual primitives | 14 | 1, 15 |
| 4 Surfaces A | 16, 17, 18, 19, 20 | 14 |
| 5 Surfaces B | 21, 22, 23, 24, 25, 26, then 27 (it reuses 21's run-outcome map) | 14 (25 also backend) |
| 6 Companion, docs, close | 28, 29, 30 | 1 |

Inside a wave, tasks that touch different files can run as parallel subagents in this worktree.
- **Same file, same agent:** tasks that share a file run in sequence. Tasks 7 and 25 both edit
  `app/applications/page.tsx`; Tasks 8 and 21 both edit `proposals-section.tsx`.
- **Hand subagents absolute worktree paths.** Afterwards, check with
  `git -C /Users/ajeyds/Projects/maestro-career-studio/.claude/worktrees/ui-ux-icons-visual-research-6195e9 status`
  that nothing landed in the main checkout (SYSTEM.md §12).

---

# Wave 1: Foundations and hygiene

### Task 1: The concept-icon register and its bans

**Files:**
- Create: `frontend/lib/concept-icons.ts`
- Create: `backend/tests/test_frontend_concept_icons.py`
- Modify: `frontend/components/app-sidebar.tsx` (draw section icons from the register)

**Step 1: Write the failing test** (`backend/tests/test_frontend_concept_icons.py`):

```python
"""One concept, one glyph (visual-language plan, Task 1).

An icon can only take over from a word if it means one thing. `lib/concept-icons.ts` is the ONE map from
a concept to its Lucide icon, the way `status-chip.tsx` is the one status vocabulary. These pins keep the
map one-to-one, keep the deprecated aliases and the drifted glyphs out, and keep text glyphs from standing
in for icons.
"""

from __future__ import annotations

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_REGISTER = _FRONTEND / "lib" / "concept-icons.ts"
_SOURCES = sorted(
    p
    for folder in ("app", "components", "hooks", "lib")
    for pattern in ("*.tsx", "*.ts")
    for p in (_FRONTEND / folder).rglob(pattern)
    if "node_modules" not in p.parts and not p.name.endswith(".test.ts")
)

# name -> what to use instead. Aliases first, then the glyphs whose one meaning went to another icon.
_BANNED = {
    "AlertTriangle": "TriangleAlert (same glyph, canonical name)",
    "CheckCircle2": "CircleCheck (same glyph, canonical name)",
    "MoreHorizontal": "Ellipsis (same glyph, canonical name)",
    "EllipsisVertical": "Ellipsis: More actions is drawn one way",
    "Library": "BriefcaseBusiness: the sidebar's Career history icon",
    "Briefcase": "Bot for the Agent inbox, Layers for the job-facts row",
}

_TEXT_GLYPHS = "⚠▲▼✓✅🟡⏸📎▾▸↗"


def _lucide_names(text: str) -> list[str]:
    names: list[str] = []
    for match in re.finditer(r'import\s*\{([^}]*)\}\s*from\s*"lucide-react"', text, re.S):
        for part in match.group(1).split(","):
            part = part.strip()
            if part and not part.startswith("type "):
                names.append(part.split(" as ")[0].strip())
    return names


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(^|[^:])//[^\n]*", r"\1", text)


def _register_entries() -> dict[str, str]:
    text = _REGISTER.read_text()
    body = text.split("export const CONCEPT_ICONS", 1)[1]
    return dict(re.findall(r"^\s{2}(\w+):\s*(\w+),", body, re.M))


def test_no_banned_or_alias_icon_is_imported():
    hits = [
        f"{p.relative_to(_FRONTEND)}: {name} -> {_BANNED[name]}"
        for p in _SOURCES
        for name in _lucide_names(p.read_text())
        if name in _BANNED
    ]
    assert hits == [], "\n".join(hits)


def test_the_register_maps_each_concept_to_its_own_icon():
    entries = _register_entries()
    assert len(entries) >= 25, entries
    by_icon: dict[str, list[str]] = {}
    for concept, icon in entries.items():
        by_icon.setdefault(icon, []).append(concept)
    shared = {icon: concepts for icon, concepts in by_icon.items() if len(concepts) > 1}
    assert shared == {}, f"one icon, two concepts: {shared}"


def test_the_sidebar_draws_its_sections_from_the_register():
    sidebar = (_FRONTEND / "components" / "app-sidebar.tsx").read_text()
    for concept in ("jobs", "agentInbox", "careerHistory", "baseResume", "assistant"):
        assert f"CONCEPT_ICONS.{concept}" in sidebar, concept


# Stored data, not display: the importer prefixes a career-history notes line with "⚠ stale?" and
# notes-editor.tsx parses that marker out (it never renders it).
_GLYPH_DATA_MARKERS = {"components/career/notes-editor.tsx"}


def test_no_text_glyph_stands_in_for_an_icon():
    hits = []
    for p in _SOURCES:
        if str(p.relative_to(_FRONTEND)) in _GLYPH_DATA_MARKERS:
            continue
        code = _strip_comments(p.read_text())
        for ch in _TEXT_GLYPHS:
            if ch in code:
                hits.append(f"{p.relative_to(_FRONTEND)}: {ch!r}")
    assert hits == [], "\n".join(hits)
```

**Step 2: Run it.** Command: `/opt/anaconda3/bin/python3 -m pytest tests/test_frontend_concept_icons.py -q`
(from `backend/`). Expected: FAIL. The register is missing, the aliases are imported (`AlertTriangle` in
several files) and ⚠ ▲ ▼ are present. The ban and glyph tests stay red until Tasks 2–3. That is expected:
commit this task with the register and sidebar tests green and the other two marked
`@pytest.mark.xfail(strict=True, reason="Tasks 2-3")`. Task 3 removes the markers.

**Step 3: Write the register** (`frontend/lib/concept-icons.ts`):

```ts
// The ONE map from a concept to its Lucide icon (visual-language plan, Task 1). An icon only replaces a
// word if it means one thing, so a concept here owns its glyph app-wide and no two concepts share one
// (backend/tests/test_frontend_concept_icons.py). An icon is never the only carrier of meaning: a word sits
// beside it or in its accessible name (docs/design-system/README.md, Iconography).
import {
  BarChart3, BookOpen, BookPlus, Bot, BriefcaseBusiness, CalendarClock, CircleCheck, CircleDashed,
  CircleHelp, CircleX, Ellipsis, FileInput, FileOutput, FilePen, FileText, FolderGit2, Handshake,
  HeartPulse, IdCard, Inbox, LayoutTemplate, Layers, Lock, Merge, MessageSquare, Minus, Paperclip,
  RefreshCw, RotateCcw, ScanSearch, School, SendHorizontal, Settings, Sparkles, Tags, TextQuote,
  ThumbsUp, TriangleAlert, UserRound, Wand2, Workflow,
  type LucideIcon,
} from "lucide-react";

export const CONCEPT_ICONS = {
  // Sections (the sidebar's icons win: they were learned first).
  jobs: Inbox,
  agentInbox: Bot,
  automations: Workflow,
  referrals: Handshake,
  careerHistory: BriefcaseBusiness,
  baseResume: FileText,
  templates: LayoutTemplate,
  assistant: MessageSquare,
  analytics: BarChart3,
  settings: Settings,
  // Things and actors.
  attachment: Paperclip,
  drafts: FilePen,
  you: UserRound,
  ai: Sparkles,
  jobWords: TextQuote,
  fromResume: FileInput,
  merged: Merge,
  project: FolderGit2,
  health: HeartPulse,
  skills: Tags,
  jobFacts: Layers,
  workAuthorization: IdCard,
  studentPermit: School,
  docs: BookOpen,
  // States.
  done: CircleCheck,
  notRun: CircleDashed,
  warning: TriangleAlert,
  fails: CircleX,
  unknown: CircleHelp,
  notListed: Minus,
  locked: Lock,
  scheduled: CalendarClock,
  // Actions.
  createPdf: FileOutput,
  addToCareerHistory: BookPlus,
  refresh: RefreshCw,
  restore: RotateCcw,
  queue: SendHorizontal,
  approve: ThumbsUp,
  analyzeGaps: ScanSearch,
  tailor: Wand2,
  more: Ellipsis,
} as const satisfies Record<string, LucideIcon>;

export type Concept = keyof typeof CONCEPT_ICONS;
```

Then in `components/app-sidebar.tsx`, replace the per-item Lucide imports for the eleven nav items (around
lines 45–77) with `CONCEPT_ICONS.<concept>`. Profile uses `CONCEPT_ICONS.you`: it is already `UserRound`,
and your profile is "you", so this is one concept, not two. Keep any icon that is not a section (for example
`Plus`/`FilePlus2` for Add job) as it is. Check the exact icons the sidebar uses before mapping. If a section
icon differs from the register, the **sidebar's** icon wins: update the register and log a deviation.

**Step 4: Run it.** The register and sidebar tests PASS; the two xfail tests XFAIL. Then run
`npx tsc --noEmit && npm run lint`.

**Step 5: Commit.**

```bash
git add frontend/lib/concept-icons.ts frontend/components/app-sidebar.tsx backend/tests/test_frontend_concept_icons.py
git commit -m "feat(web): one concept-icon register; the sidebar draws from it"
```

### Task 2: Move the drifted icons onto the register

**Files** (each line: file, then the change; locate by the quoted text, since line numbers drift):

| File | Change |
|---|---|
| `app/jobs/[id]/tailor/[sessionId]/page.tsx` | `Library` (auto-resolved banner) → `CONCEPT_ICONS.careerHistory` |
| `components/gap-analysis/gap-card.tsx` | `Library` (auto card) → `careerHistory` |
| `components/gap-analysis/resolution-controls.tsx` | `Library` ("Found in…") → `careerHistory` |
| `components/proposals/proposal-agent-panel.tsx` | `Briefcase` on "Open Agent inbox" → `agentInbox` |
| `components/job-extracted-fields.tsx` | `Briefcase` (role chips row) → `jobFacts`; `Sparkles` ("Skills (n)") → `skills`; `ShieldCheck` (Work authorization) → `workAuthorization`; `CheckCircle2` (OPT) → `studentPermit` |
| `components/qa-tab.tsx` | `FileText` on the cover letter's `label="Create PDF"` (~:400) → `createPdf`. "Write a new version" keeps `RefreshCw`: it is a re-run, the register's `refresh`. |
| `components/career/inbox-panel.tsx` | `Inbox` ("Drafts to review") → `drafts` |
| `components/chat/kb-capture-card.tsx` | `Inbox` ("Review drafts") → `drafts` |
| `components/career/entity-card.tsx` | `BookOpen` (draft count) → `drafts` |
| `components/kb-sync-pill.tsx` | `RefreshCw` on "Add N things to career history" (the trigger, around :168) → `addToCareerHistory`. The retry `RefreshCw` (:111) stays. |
| `app/applications/page.tsx` | `EllipsisVertical` (row ⋯) → `more` |
| `components/ats-score-panel.tsx` | `MoreHorizontal` → `more`; `Wand2` on Analyze gaps → `analyzeGaps` |
| every other `MoreHorizontal`, `AlertTriangle`, `CheckCircle2` import | → `Ellipsis`, `TriangleAlert`, `CircleCheck` (plain renames) |
| `app/jobs/[id]/page.tsx` | Queue (proposal pill, around :469) `Check` → `queue`; Keep it (:490) `Check` → `approve` |
| `components/proposals/proposals-section.tsx` | row IconButton "Queue" `<Check />` → `queue`; "Keep it" `<Check />` → `approve` |
| `components/career/points-list.tsx` and `components/career/inbox-panel.tsx` | Approve / Approve all `Check` → `approve` |

Usage pattern, for an icon in JSX:

```tsx
import { CONCEPT_ICONS } from "@/lib/concept-icons";
const CareerHistoryIcon = CONCEPT_ICONS.careerHistory;
// …
<CareerHistoryIcon className="size-4" aria-hidden="true" />
```

**Step 1: Add the failing pins** to `test_frontend_concept_icons.py`:

```python
_MUST_NOT_IMPORT = [
    ("components/career/inbox-panel.tsx", "Inbox"),
    ("components/chat/kb-capture-card.tsx", "Inbox"),
    ("components/career/entity-card.tsx", "BookOpen"),
    ("components/job-extracted-fields.tsx", "ShieldCheck"),
    ("components/job-extracted-fields.tsx", "Sparkles"),
]


def test_drifted_glyphs_are_gone_from_their_old_homes():
    hits = [f"{f}: {n}" for f, n in _MUST_NOT_IMPORT if n in _lucide_names((_FRONTEND / f).read_text())]
    assert hits == [], hits


def test_queue_and_approve_are_not_drawn_as_a_check():
    page = (_FRONTEND / "app/jobs/[id]/page.tsx").read_text()
    row = (_FRONTEND / "components/proposals/proposals-section.tsx").read_text()
    for text in (page, row):
        assert "CONCEPT_ICONS.queue" in text and "CONCEPT_ICONS.approve" in text
    assert 'label="Queue"\n                  icon={<Check />}' not in row


def test_the_career_history_add_pill_does_not_say_refresh():
    pill = (_FRONTEND / "components/kb-sync-pill.tsx").read_text()
    assert "CONCEPT_ICONS.addToCareerHistory" in pill
```

**Step 2: Run them.** They FAIL.

**Step 3: Make the edits** in the table. After the renames, remove the `xfail` marker from
`test_no_banned_or_alias_icon_is_imported`.

**Step 4: Run them.** `test_frontend_concept_icons.py` passes except the glyph test (still xfail). Run
`tsc` and lint. Then run the frontend pin suites that read these files: `-k "frontend or kb_sync"` over
`tests/`. Fix any pin that names an old icon (say so in the commit body).

**Step 5: Commit.** `refactor(web): move drifted icons onto the concept register`

### Task 3: Colour-only, icon-only and text-glyph fixes

**Files:**
- `frontend/components/job-extraction-summary.tsx`: the skill list tells Required, Preferred and Mentioned
  apart by badge variant only (WCAG 1.4.1). Group the badges under the same three labels
  `job-extracted-fields.tsx` uses ("Required (n)", "Preferred (n)", "Mentioned (n)"). Keep the cap of 24
  with "+N more" counted across groups, and the D3 variants (`default` / `tonal` / `outline`).
- `frontend/components/setup/getting-started-card.tsx` (around :105–124): the done state is an
  `aria-hidden` icon only.
  - Add a visible word after the row title: `<span className="text-success text-label-medium">Done</span>`
    when `row.done`. Nothing extra when not done; the "Required" badge already says it.
  - Swap `text-primary` on the done icon for `text-success`.
- `frontend/components/templates/template-gallery.tsx` (:81): `<span aria-hidden="true">⚠</span>` →
  `<TriangleAlert className="size-3.5 shrink-0" aria-hidden="true" />` inside an
  `inline-flex items-start gap-1.5` wrapper.
- `frontend/app/applications/page.tsx` (:484): `{sortDir === "asc" ? "▲" : "▼"}` →
  `{sortDir === "asc" ? <ArrowUp className="size-3" aria-hidden="true" /> : <ArrowDown className="size-3" aria-hidden="true" />}`.
  `aria-sort` on the header stays the accessible signal.

**Step 1: Failing pins.** Remove the `xfail` from `test_no_text_glyph_stands_in_for_an_icon`. Then add this to
`backend/tests/test_frontend_color_roles.py`, or create `test_frontend_visual_rules.py` if that file has no
natural home:

```python
def test_the_add_job_summary_names_each_requirement_group():
    src = (_FRONTEND / "components/job-extraction-summary.tsx").read_text()
    for word in ("Required", "Preferred", "Mentioned"):
        assert word in src


def test_a_done_setup_step_says_done_in_words():
    src = (_FRONTEND / "components/setup/getting-started-card.tsx").read_text()
    assert ">Done<" in src
```

**Step 2: Run them.** They FAIL.
**Step 3: Make the edits.**
**Step 4: Run them.** All of `test_frontend_concept_icons.py` and the new pins PASS. Run `tsc` and lint.
**Step 5: Commit.** `fix(web): no meaning in colour, icon or text glyph alone`

### Task 4: Borrowed colour roles, selection without a Check, and named alpha fills

**Files and changes:**

1. **`components/resume-versions/version-history-sheet.tsx`** (`SOURCE_BADGE`, around :39–42):
   `restore: "bg-warning-container …"` → `restore: "bg-surface-container text-foreground"`.
2. **`components/resume-editor/diff-review.tsx`** (`ProvenanceChip`, around :27–37): the "You" chip's
   `success-container` → `bg-surface-container text-foreground`. Provenance is not "good". Task 19 adds icons
   to these chips later.
3. **`components/gap-analysis/gap-card.tsx`** `REQUIREMENT_VARIANTS` →
   `{ required: "default", preferred: "tonal", mentioned: "outline" }` (D3). Widen the type to
   `"default" | "tonal" | "outline"`.
4. **`components/gap-analysis/resolution-controls.tsx`:**
   - **`ActionSegment` selected:** `bg-background text-foreground` →
     `bg-secondary-container text-on-secondary-container`, plus a leading
     `<Check className="size-3" aria-hidden="true" />` when selected.
   - **`Chip` selected:** `border-primary bg-primary text-primary-foreground` →
     `border-transparent bg-secondary-container text-on-secondary-container`, plus a leading `Check`. The
     `date` span's selected colour becomes `text-on-secondary-container`.
   - **The highlighted (not selected) ring:** `border-primary/40 … ring-primary/30` →
     `border-primary text-foreground`, with no ring.
   - **The unverified warning** (`bg-destructive/10`, around :423) →
     `bg-error-container text-on-error-container`.
5. **`components/ui/badge.tsx` `destructive` variant:** →
   `bg-error-container text-on-error-container focus-visible:ring-destructive/20 [a]:hover:bg-error-container/80`.
   Drop the `dark:` overrides; the role carries both themes.
6. **The research's named fills:**
   - `components/job-knockout-card.tsx` conflict tone → `bg-error-container text-on-error-container`.
     Task 16 rewrites this card; do the one-line swap now anyway.
   - `app/jobs/[id]/tailor/[sessionId]/page.tsx`:
     - Strong match (`border-primary/30 bg-primary/5`) → `bg-success-container text-on-success-container`
       with a `CircleCheck`.
     - The auto banner (`border-primary/25 bg-primary/[0.04]`) → `bg-surface-container-low`.
   - `components/gap-analysis/gap-card.tsx` auto card (`bg-primary/[0.04]`) → `bg-surface-container-low`.
   - `components/setup/getting-started-card.tsx` (`bg-primary/[0.03]`) → `bg-surface-container-low`.
   - `components/ats-score-panel.tsx` top card: `border-primary/50 ring-primary/20 ring-1` →
     `border-primary`.
   - `bg-destructive/10 text-destructive` → `bg-error-container text-on-error-container` at:
     - `components/resume-health/finding-cards.tsx:1246` (Must fix) **only**. Line :1235
       (`"border-destructive/50 bg-destructive/5"`) is the `_FATAL_GATE` literal pinned by
       `test_fatal_gate_containers_use_the_destructive_token`; it stays.
     - `components/resume-health/health-badges.tsx:154`
     - `components/career/documents-panel.tsx:237`
     - `components/resume-versions/version-diff-view.tsx:13`
     - `app/templates/[id]/page.tsx:380`

**Step 1: Failing pins.** Add to `test_frontend_color_roles.py` (it already measures chips; follow its
helpers):

```python
import re

_ALPHA_FILL = re.compile(r"(?<![:\w-])(bg|border|ring)-(primary|destructive)/[\d\[]")
# A ratchet, not a sweep (plan non-goal): the count can only go down. Set it to the count left after Task 4.
_ALPHA_FILL_CEILING = 0  # replace with the measured count in Step 4


def test_alpha_fills_of_primary_and_destructive_only_shrink():
    sites = []
    for p in (_FRONTEND / "app").rglob("*.tsx"):
        sites += [f"{p.name}" for _ in _ALPHA_FILL.finditer(p.read_text())]
    for p in (_FRONTEND / "components").rglob("*.tsx"):
        if p.name == "button.tsx":  # the destructive Button variant: out of scope
            continue
        sites += [f"{p.name}" for _ in _ALPHA_FILL.finditer(p.read_text())]
    assert len(sites) <= _ALPHA_FILL_CEILING, sorted(sites)


def test_restored_and_you_are_neutral_not_status():
    sheet = (_FRONTEND / "components/resume-versions/version-history-sheet.tsx").read_text()
    assert "restore: \"bg-warning-container" not in sheet
    diff = (_FRONTEND / "components/resume-editor/diff-review.tsx").read_text()
    assert "success-container" not in diff


def test_required_is_not_an_error():
    card = (_FRONTEND / "components/gap-analysis/gap-card.tsx").read_text()
    assert 'required: "default"' in card


def test_selected_gap_controls_show_a_check():
    rc = (_FRONTEND / "components/gap-analysis/resolution-controls.tsx").read_text()
    segment = rc.split("export function ActionSegment", 1)[1].split("export function Chip", 1)[0]
    chip = rc.split("export function Chip", 1)[1]
    for body in (segment, chip):
        assert "<Check" in body and "bg-secondary-container" in body
```

**Existing pins to update in this commit:**
- **`test_gap_target_chip_text_meets_aa`** (`test_frontend_color_roles.py:228-236`). It reads the `selected ? "…" : "…"`
  pairs in `resolution-controls.tsx` and computes contrast through `_TOKEN_UTIL`, which only knows
  `primary-foreground|primary|muted-foreground|muted|background`. The new selected pair would raise
  `KeyError`. Widen `_TOKEN_UTIL` to the container pairs (`secondary-container` / `on-secondary-container`,
  and the others this task introduces), so the test keeps measuring the new pair.
- **`_ROLE_SITES`** (`test_frontend_color_roles.py:722`). It pins
  `restore: "bg-warning-container text-on-warning-container"`. Rewrite it to the neutral pair.

**Step 2: Run them.** They FAIL. The ceiling of 0 fails by design; the test prints the sites.
**Step 3: Make the edits.**
**Step 4: Set the ceiling.** Rerun the test, set `_ALPHA_FILL_CEILING` to the printed count (expect about
45–50), and add a comment naming this plan. Run the colour-role suite (it computes contrast for the new pairs),
then `tsc` and lint.
**Step 5: Commit.** `fix(web): status roles mean status; selected gap controls show a Check`

**Wave 1 close:** run `npm run build`, the full backend suite with xdist and the slop check on `frontend`.
Browser pass: the gap page (selected segments and chips), the job Overview (skills, stat icons), the Jobs
sort header, Add job's summary, the getting-started card (an empty DB snapshot or a fresh scratch DB) and
version history. Opus review of the wave against the Goal Card.

---

# Wave 2: States, feedback and motion

### Task 5: Button `pending` and built-in disabled styling

**Files:**
- Modify: `frontend/components/ui/button.tsx`
- Test: `backend/tests/test_frontend_states.py` (create)

**Step 1: Failing test** (`backend/tests/test_frontend_states.py`):

```python
"""Every action answers (visual-language plan, Wave 2).

The Button primitive owns its loading state: `pending` shows a spinner, keeps the button focusable and
busy, and ignores presses. Base UI marks a disabled button `data-disabled`, which the primitive styles
itself, so call sites stop repeating the class by hand.
"""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def test_the_button_has_a_pending_state():
    src = _read("components/ui/button.tsx")
    assert "pending?: boolean" in src
    assert "aria-busy={pending || undefined}" in src
    assert "focusableWhenDisabled" in src and "Loader2" in src


def test_the_button_styles_data_disabled_itself():
    src = _read("components/ui/button.tsx")
    assert "data-disabled:pointer-events-none" in src and "data-disabled:opacity-50" in src
```

**Step 2: Run it.** FAIL.

**Step 3: Implement** in `components/ui/button.tsx`:
- Add `data-disabled:pointer-events-none data-disabled:opacity-50` to the base class string, next to
  `disabled:`.
- Hide a caller's own icon while pending: `aria-busy:[&_svg:not([data-spinner])]:hidden`.

Replace the component with:

```tsx
import { Loader2 } from "lucide-react"
// …buttonVariants unchanged except the two additions above…

function Button({
  className,
  variant = "default",
  size = "default",
  pending = false,
  disabled,
  focusableWhenDisabled,
  children,
  ...props
}: ButtonPrimitive.Props &
  VariantProps<typeof buttonVariants> & {
    /** A request this button started is running: spinner, busy, presses ignored, focus kept. */
    pending?: boolean
  }) {
  return (
    <ButtonPrimitive
      data-slot="button"
      aria-busy={pending || undefined}
      disabled={disabled || pending}
      // Focus stays on a busy button: a natively disabled one drops it to <body>.
      focusableWhenDisabled={pending || focusableWhenDisabled}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    >
      {pending ? <Loader2 data-spinner className="animate-spin" aria-hidden="true" /> : null}
      {children}
    </ButtonPrimitive>
  )
}
```

A Button rendered through `render={<a …>}` is never `pending`, so the spinner never lands inside a link. Do
**not** sweep the 98 existing `data-disabled:` call-site classes (non-goal). Remove them only in files a later
task touches anyway.

**Step 4: Run it.** PASS. Run `tsc` and lint. Click a pending button in a scratch page or Storybook-free check
(Task 6 exercises it for real).
**Step 5: Commit.** `feat(web): Button pending state; the primitive styles data-disabled`

### Task 6: Slow AI actions show the pending state

**Files** (each uses `pending={<mutation>.isPending}`, keeps or sets its busy label, and drops any hand-made
spinner):

| File | Button |
|---|---|
| `app/new/page.tsx` (~:143) | Save job |
| `components/qa-tab.tsx` (~:214, ~:245) | Answer questions, Write cover letter |
| `components/resume-health/finding-cards.tsx` (~:532, ~:956) | Apply suggestion, Write new wording |
| `components/resume-health/demonstrate-skill-dialog.tsx` (~:266) | Write new wording |
| `components/resume-health/question-pass.tsx` (~:367) | Write N new wordings |
| `components/career/send-to-resume-dialog.tsx` (~:527) | Adapt and preview |
| `app/jobs/[id]/page.tsx` (~:537) | Queue in Agent inbox |
| `components/proposals/triage-actions.tsx` | DeclineDialog Skip, BulkBar Queue and Skip |
| `components/career/inbox-panel.tsx` (~:479) | Approve: its busy label "Saving…" becomes "Approving…", matching Approve all |

**Step 1: Failing pin** in `test_frontend_states.py`:

```python
_PENDING_SITES = [
    ("app/new/page.tsx", "Save job"),
    ("components/qa-tab.tsx", "Answer questions"),
    ("components/qa-tab.tsx", "Write cover letter"),
    ("components/resume-health/finding-cards.tsx", "Apply suggestion"),
    ("components/career/send-to-resume-dialog.tsx", "Adapt and preview"),
    ("components/proposals/triage-actions.tsx", "Skip"),
]


def test_slow_actions_show_pending():
    for rel, label in _PENDING_SITES:
        src = _read(rel)
        assert "pending={" in src, f"{rel}: {label} has no pending state"


def test_approve_does_not_say_saving():
    row = _read("components/career/inbox-panel.tsx").split("function DraftRow(", 1)[1]
    assert "Approving…" in row and '"Saving…"' not in row
```

If `DraftRow` also holds a real save action (an edit's Save) whose label is "Saving…", narrow the slice to
the Approve button and log it.

**Step 2:** FAIL. **Step 3:** edit. **Step 4:** PASS, then `tsc` and lint. **Step 5: Commit.**
`feat(web): slow actions show a spinner while they run`

### Task 7: A status change answers at once and cannot race

**Files:**
- Modify: `frontend/app/applications/page.tsx` (`patchStatus`, ~:254–275)
- Modify: `frontend/components/application-panel.tsx` (the job header's status PATCH, ~:77–88)
- Modify: `frontend/components/status-chip.tsx` (`StatusChip`, `chipClasses`)
- Test: `backend/tests/test_frontend_states.py`

**What happens today** (from reading the code; not reproduced, because it would change live data):
- `onSuccess` calls `qc.invalidateQueries(…)` without returning it, so `isPending` ends before the refetch
  lands, and the chip can show the old label for a moment.
- There is no optimistic update.
- A second pick while the first runs fires a parallel PATCH.

**Step 1: Failing pins:**

```python
def test_status_change_is_optimistic_and_awaits_the_refetch():
    page = _read("app/applications/page.tsx")
    # Up to the next mutation, as test_frontend_focus.py slices it: the body itself contains "});".
    block = page.split("const patchStatus = useMutation", 1)[1].split("const deleteApp = useMutation(", 1)[0]
    assert "onMutate" in block and "setQueriesData" in block
    assert "onSettled" in block and "return qc.invalidateQueries" in block


def test_a_pending_status_chip_cannot_be_changed_again():
    chip = _read("components/status-chip.tsx")
    body = chip.split("export function StatusChip", 1)[1]
    assert "disabled={pending}" in body


def test_the_status_chip_cross_fades_and_confirms():
    chip = _read("components/status-chip.tsx")
    assert "transition-[background-color,color" in chip
    assert "data-confirm" in chip and "animate-confirm" in chip
```

**Step 2:** FAIL.

**Step 3: Implement.**
- **`patchStatus`** in `app/applications/page.tsx`. Keep its existing `leaving`/focus logic intact; add
  around it:

  ```tsx
  onMutate: async ({ id, status }) => {
    await qc.cancelQueries({ queryKey: ["applications"] });
    const previous = qc.getQueriesData<ApplicationSummary[]>({ queryKey: ["applications"] });
    qc.setQueriesData<ApplicationSummary[]>({ queryKey: ["applications"] }, (rows) =>
      rows?.map((row) => (row.id === id ? { ...row, status } : row)),
    );
    return { previous };
  },
  onError: (err: Error, _vars, context) => {
    context?.previous.forEach(([key, rows]) => qc.setQueryData(key, rows));
    // …existing onError body (leaving.current = null; toast) stays…
  },
  onSettled: (_data, _err, { id }) => {
    const jobId = apps.data?.find((a) => a.id === id)?.job_id;
    if (jobId) void qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
    return qc.invalidateQueries({ queryKey: ["applications"] });
  },
  ```

  Move the invalidations out of `onSuccess` into `onSettled`. Check that `["applications"]` really holds
  `ApplicationSummary[]` in every query under that prefix; if one holds another shape, narrow the key and log
  a deviation.
- **The job header's PATCH** (`application-panel.tsx`): the same pattern on its `["job-detail", jobId]`
  data, setting `application.status`.
- **`StatusChip`:**
  - Pass `disabled={pending}` to the trigger `<button>`.
  - Add `transition-[background-color,color,transform,box-shadow] duration-(--duration-short3) ease-(--ease-standard)`
    to `chipClasses`, replacing its current `transition-[transform,box-shadow] duration-150 ease-out`.
  - Confirm a change with one soft ring pulse:

    ```tsx
    const shown = useRef(current);
    const [confirm, setConfirm] = useState(false);
    useEffect(() => {
      if (shown.current === current) return;
      shown.current = current;
      setConfirm(true);
      const t = window.setTimeout(() => setConfirm(false), 400);
      return () => window.clearTimeout(t);
    }, [current]);
    // on the trigger: data-confirm={confirm || undefined} className={cn(…, "data-confirm:animate-confirm")}
    ```

  `animate-confirm` is defined in Task 15. **Run Task 15 before Task 7** (see Waves).

**Existing pins to rewrite in this commit:**
- `backend/tests/test_frontend_focus.py:636` pins `patchStatus`'s squashed `onError` literal
  (`onError: (err: Error) => { leaving.current = null; toast.error(couldnt("change the status", err)); },`).
  Rewrite it to the new `onError` (rollback, then the same `leaving.current = null` and toast).
- `test_frontend_focus.py:647` pins `'<button type="button" data-status-chip'`. Put `disabled={pending}`
  **after** `data-status-chip` so the literal still holds.

**Step 4:** PASS. Run `tsc` and lint. Browser (fresh stack): change a status in the tracker. The chip turns
at once, pulses once, and a second change is blocked while the first runs. With the backend stopped, the
chip snaps back and the error toast shows.
**Step 5: Commit.** `fix(web): a status change is optimistic, single and confirmed`

### Task 8: Agent inbox actions answer on every page

**Files:**
- Modify: `frontend/components/proposals/triage-actions.tsx` (`useProposalActions`, `BulkBar`)
- Modify: `frontend/app/jobs/[id]/page.tsx` (drop its own success toasts for these actions, ~:177–180)
- Modify: `frontend/components/proposals/proposals-section.tsx` (row exit and per-row spinner)
- Test: `backend/tests/test_frontend_states.py`, plus the existing `test_frontend_agent_inbox.py` pins

**Behaviour:**
- **One owner for toasts.** Success toasts live in the hook, so the inbox and the job page say the same
  thing. A success toast names its object (`docs/frontend-conventions.md` ~:1343: "Template deleted", never
  "Deleted"), so the job page's existing sentences move into the hook unchanged:

  | Action | Toast |
  |---|---|
  | `accepted` | "Queued. A connected agent can apply to it now." (today's job-page string) |
  | `rejected` | "Proposal skipped" |
  | `pending_review` | "Kept. It's back in To review." (today's job-page string) |
  | bulk, all succeeded | "Queued {n} proposals" / "Skipped {n} proposals" (singular for 1) |
  | bulk, partial failure | unchanged |

  **Pins to rewrite:** `test_frontend_agent_inbox.py:434` (the Queued sentence) and `:773` (the
  `became === "pending_review"` Kept toast in the job page). Both now point at `triage-actions.tsx`.

- **Spinner on the acting row only.** Buttons stay globally disabled, as today: the single-flight guard
  drops a second press, so enabled-looking buttons would be a silent no-op. The hook returns `actingIds`,
  the ids in flight:

  ```ts
  const actingIds = new Set<string>(
    transition.isPending && transition.variables ? [transition.variables.id]
    : bulk.isPending && bulk.variables ? bulk.variables.ids
    : [],
  );
  ```

  In `proposals-section.tsx`, a row whose id is in `actingIds` shows `<Loader2 className="size-4 animate-spin" aria-hidden="true" />`
  in place of its action buttons and sets `data-pending="true"` on its card.
- **Row exit.** After a successful Queue or Skip, the row leaves before the refetch removes it. Keep a
  `leavingIds` state in the section, filled from `onDone`. Wrap each row:

  ```tsx
  <div
    data-leaving={leavingIds.has(proposal.id) || undefined}
    className="grid grid-rows-[1fr] transition-[grid-template-rows,opacity] duration-(--duration-short4) ease-(--ease-emphasized-accelerate) data-leaving:grid-rows-[0fr] data-leaving:opacity-0"
  >
    <div className="min-h-0 overflow-hidden">{/* the Card */}</div>
  </div>
  ```

  Clear an id once the refetched list no longer holds it.
- **Focus hand-off.** Keep the existing hand-off (`onDone` already moves focus to the next row). Check it
  still lands while the row animates out.
- **`BulkBar`:**
  - Queue and Skip take `pending`.
  - The bar slides up on mount: `animate-in slide-in-from-bottom-2 fade-in-0 duration-(--duration-short4) ease-(--ease-emphasized-decelerate)`
    (tw-animate-css, already imported).

**Step 1: Failing pins:**

```python
def test_inbox_actions_toast_from_the_hook():
    hook = _read("components/proposals/triage-actions.tsx")
    assert 'toast.success("Queued. A connected agent can apply to it now.")' in hook
    assert 'toast.success("Proposal skipped")' in hook
    assert "Kept. It's back in To review." in hook
    page = _read("app/jobs/[id]/page.tsx")
    assert "Queued. A connected agent" not in page and "Kept. It's back" not in page


def test_inbox_rows_leave_with_an_exit_transition():
    section = _read("components/proposals/proposals-section.tsx")
    assert "data-leaving" in section and "grid-rows-[0fr]" in section
    assert "actingIds" in section
```

Its point: one toast per action, owned by the hook.

**Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS. Run `test_frontend_agent_inbox.py` and
`test_frontend_single_flight.py`, then `tsc` and lint. Browser: Queue a row on `/proposals`. The spinner
shows on that row, the row slides out, the Queued toast appears and focus lands on the next row. A bulk
Skip toasts "Skipped 3 proposals".
**Step 5: Commit.** `feat(web): inbox actions answer with a toast, a row spinner and an exit`

### Task 9: Undo where the server can reverse it (D8)

**Files:**
- Modify: `frontend/components/career/inbox-panel.tsx` (single Approve)
- Modify: `frontend/components/career/points-list.tsx` (Approve on a draft point, if it approves there too)
- Modify: `frontend/app/base-resumes/page.tsx` (`archive` mutation)
- Test: `backend/tests/test_frontend_states.py`

**Behaviour:**
- **Approve a draft bullet.** The toast reads "Bullet approved" (a toast names its object), with an
  `action: { label: "Undo", onClick }`. The Undo calls the existing client `patchKbPoint(pointId, { state: "draft" })`
  (`lib/api.ts:457`; `KBPointPatch.state` allows it) and invalidates the same queries. No new client
  function is needed.
- **Archive a base resume.** The toast reads "Resume archived", with Undo calling the existing mutation with
  `{ slug, archived: true }` (the unarchive branch).
- **Skip and Queue get no Undo** (D8).

**Step 1: Failing pin:**

```python
def test_reversible_actions_offer_undo():
    for rel in ("components/career/inbox-panel.tsx", "app/base-resumes/page.tsx"):
        src = _read(rel)
        assert 'label: "Undo"' in src, rel
```

**Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS, then `tsc` and lint. Browser: approve a draft,
press Undo, and the bullet is back in Drafts to review. Archive a resume, press Undo, and it is back.
**Step 5: Commit.** `feat(web): Undo on approve bullet and archive resume`

### Task 10: One copy confirmation everywhere

**Files:**
- Create: `frontend/hooks/use-copy.ts`
- Create: `frontend/components/copy-button.tsx`
- Modify: `frontend/components/qa-tab.tsx` (the Copy IconButton, ~:389–396)
- Modify: `frontend/components/automations/automation-card.tsx` (Copy prompt, ~:53–68)
- Modify: `frontend/components/resume-editor/editor-body.tsx` ("Copy ID for connected agents", ~:473–482)
- Test: `backend/tests/test_frontend_states.py`

**Step 1: Failing pins:**

```python
def test_copy_uses_one_hook_with_an_error_path():
    hook = _read("hooks/use-copy.ts")
    assert "navigator.clipboard.writeText" in hook and "catch" in hook and "couldnt(" in hook
    for rel in ("components/qa-tab.tsx", "components/automations/automation-card.tsx",
                "components/resume-editor/editor-body.tsx"):
        src = _read(rel)
        assert "useCopy" in src or "CopyButton" in src, rel
        assert "navigator.clipboard" not in src, rel


def test_the_copy_button_confirms_in_place_and_aloud():
    btn = _read("components/copy-button.tsx")
    assert "Copied" in btn and 'aria-live="polite"' in btn and "data-show" in btn
```

**Step 2:** FAIL.

**Step 3: Implement.** First `hooks/use-copy.ts`:

```ts
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { couldnt } from "@/lib/error-text";

/** Copy text, then hold `copied` for a moment so the control can say so. A refused copy says why. */
export function useCopy(holdMs = 1200) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const copy = useCallback(
    async (text: string): Promise<boolean> => {
      try {
        await navigator.clipboard.writeText(text);
      } catch (err) {
        toast.error(couldnt("copy that", err));
        return false;
      }
      setCopied(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), holdMs);
      return true;
    },
    [holdMs],
  );
  return { copied, copy };
}
```

Then `components/copy-button.tsx`:

```tsx
"use client";

import { Check, Copy } from "lucide-react";

import { IconButton, type IconButtonProps } from "@/components/icon-button";
import { useCopy } from "@/hooks/use-copy";

/** Copy with the confirmation in place: the icon turns to a Check and a "Copied" chip rises from the
 *  button for a moment, and a screen reader hears "Copied" (visual-language plan, Task 10). */
export function CopyButton({
  text,
  label = "Copy",
  ...rest
}: { text: string; label?: string } & Omit<IconButtonProps, "label" | "icon" | "onClick">) {
  const { copied, copy } = useCopy();
  return (
    <span className="relative inline-flex">
      <IconButton
        {...rest}
        label={copied ? "Copied" : label}
        icon={copied ? <Check /> : <Copy />}
        onClick={() => void copy(text)}
      />
      <span
        aria-hidden="true"
        data-show={copied || undefined}
        className="bg-foreground text-background pointer-events-none absolute -top-6 left-1/2 inline-flex h-5 -translate-x-1/2 translate-y-1 items-center gap-1 rounded-full px-2 text-label-small whitespace-nowrap opacity-0 transition-[opacity,transform] duration-(--duration-short3) ease-(--ease-spring) data-show:translate-y-0 data-show:opacity-100"
      >
        <Check className="size-3" />
        Copied
      </span>
      <span className="sr-only" aria-live="polite">
        {copied ? "Copied" : ""}
      </span>
    </span>
  );
}
```

Apply it:
- **Q&A:** `<CopyButton text={entry.answer ?? ""} />` replaces the IconButton and its success toast.
- **Copy prompt:** it is a labelled Button, so keep the Button and use `useCopy`. The label swaps
  `Copy prompt` → `Copied` with a `Check` icon while `copied`. Keep its toast ("Prompt copied. Paste it into
  {app}."), because it carries an instruction. Keep its failure fallback (open and focus the prompt): call it
  when `copy()` resolves false.
- **Copy ID:** a menu item, so use `useCopy` and its success toast stays. The menu closes on select, so there
  is no in-place chip.

**Step 4:** PASS, then `tsc` and lint. Browser: copy a Q&A answer. The icon turns to a Check, the chip rises
and fades in about 1.4s, and VoiceOver hears "Copied".
**Step 5: Commit.** `feat(web): one copy confirmation: Check, a Copied chip, a spoken status`

### Task 11: Saves say "Saved"; background work dims what it changes

**Files:**
- `frontend/components/settings/autosave-status.tsx`: after `pending` goes false with no failure, show
  `<Check /> Saved` in `text-success` for 1500ms, then the idle "Saves automatically". Track the previous
  `pending` with a ref. The status keeps its live region, if it has one; if not, give the wrapper
  `aria-live="polite"`.
- `frontend/components/settings/form-filling-section.tsx` (~:58–150): its `save` mutation (:58; it saves the
  Jev key, provider and engine) is silent today. Mount `AutosaveStatus` in the card header, like the sibling
  cards, fed by `save.isPending`/`save.isError`. The `probe` mutation (:75) is a test, not a save, and keeps
  its own result line.
- **Order in `AutosaveStatus`:** `test_frontend_settings_autosave.py:72` requires `!failed` to come before the
  literal "Saves automatically" after `return (`. Add the transient "Saved" branch without reordering those
  two.
- **Mutation names:** the tailored studio's render mutation is `render` (:207); `renderPdf` is
  `application-panel.tsx:273`. Use each file's own name in the `data-pending` wiring.
- `frontend/components/settings/market-section.tsx:89`: `data-pending={save.isPending ? "" : undefined}` →
  `data-pending={save.isPending ? "true" : undefined}`. The `""` never matched `[data-pending="true"]`.
- `frontend/components/resume-editor/tailored-resume-studio.tsx` and `components/application-panel.tsx`:
  the PDF preview region gets `data-pending="true"` while the render runs.
- **One rule for Update scores: a manual update confirms with a toast; an automatic re-score does not.**
  - The tailored studio (`test_frontend_studio.py:162-163`, conventions ~:299-301) and the compare panel
    (`ats-compare-panel.tsx:117` and `:126`) already follow it. Leave them.
  - The one surface that breaks it is Score and tailor's manual **Update scores** (`ats-score-panel.tsx`),
    which is silent. Add `toast.success("ATS scores updated")` on its success.
  - The count-up from Task 18 shows the number moving as well.
- `frontend/app/jobs/[id]/tailor/[sessionId]/page.tsx` (~:101–110): the gap page's "Saved" gets the same
  `Check` + 1500ms treatment, if it shows "Saved" permanently today.

**Step 1: Failing pins:**

```python
def test_autosave_says_saved_for_a_moment():
    src = _read("components/settings/autosave-status.tsx")
    assert ">Saved<" in src or '"Saved"' in src
    assert "1500" in src


def test_market_select_dims_while_saving():
    src = _read("components/settings/market-section.tsx")
    assert 'data-pending={save.isPending ? "true" : undefined}' in src


def test_form_filling_saves_are_visible():
    assert "AutosaveStatus" in _read("components/settings/form-filling-section.tsx")


def test_a_rendering_pdf_preview_dims():
    assert 'data-pending={renderPdf.isPending ? "true" : undefined}' in _read("components/application-panel.tsx")
```

Adapt the variable names to the real ones.

**Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS. Run `test_frontend_settings_autosave.py`, then
`tsc` and lint.
**Step 5: Commit.** `feat(web): saves say Saved; background renders dim their preview`

### Task 12: Field error and warning states, and checks on the autofill contact fields

**Files:**
- Create: `frontend/lib/field-checks.ts` and `frontend/lib/field-checks.test.ts`
- Create: `backend/tests/test_frontend_field_checks.py` (runs the node test, like
  `test_frontend_agent_dashboard.py:115`)
- Modify: `frontend/components/ui/input.tsx`, `frontend/components/ui/textarea.tsx` (the `data-warning`
  style)
- Modify: `frontend/components/resume-editor/field.tsx` (`error?: string`, `warning?: string`)
- Modify: `frontend/components/settings/autofill-section.tsx` (~:84–98: `type`, `autoComplete`, warnings)
- Modify: `frontend/components/resume-editor/contact-form.tsx` (Email warning; Name and Email are marked
  required)
- Modify: `frontend/components/qa-tab.tsx` (Answer questions disabled while the box is empty, with a hint, in
  place of an error toast)

**Step 1: Failing node test** (`frontend/lib/field-checks.test.ts`):

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { emailWarning, phoneWarning, linkWarning } from "./field-checks.ts";

test("an email warns only when its shape is off", () => {
  assert.equal(emailWarning(""), null);
  assert.equal(emailWarning("sam@example.com"), null);
  assert.match(emailWarning("sam.example.com") ?? "", /email address/);
  assert.match(emailWarning("sam@example") ?? "", /email address/);
});

test("a phone warns under seven digits", () => {
  assert.equal(phoneWarning(""), null);
  assert.equal(phoneWarning("+1 (972) 555-0100"), null);
  assert.match(phoneWarning("555-01") ?? "", /digits/);
});

test("a link warns when it is not a web address", () => {
  assert.equal(linkWarning(""), null);
  assert.equal(linkWarning("linkedin.com/in/sam"), null);
  assert.equal(linkWarning("https://github.com/sam"), null);
  assert.match(linkWarning("sam rivera") ?? "", /web address/);
});
```

And `backend/tests/test_frontend_field_checks.py`:

```python
"""Field warnings never block a save; they flag a value that looks off (visual-language plan, Task 12)."""

from tests.node_ts import run_node_test


def test_field_checks_node_suite():
    result = run_node_test("lib/field-checks.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr
```

**Step 2:** Run it from `frontend/` with `node --test lib/field-checks.test.ts`. FAIL (no module).

**Step 3: Implement** `frontend/lib/field-checks.ts`. It is pure; `node --test` loads it directly.

```ts
// Warnings for values the Companion types into real application forms (visual-language plan, Task 12).
// A warning never blocks a save: it says what looks off. Empty is not a warning; required-ness is the
// form's own business.

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function emailWarning(value: string): string | null {
  const v = value.trim();
  if (!v || EMAIL.test(v)) return null;
  return "This doesn't look like an email address. Check it before a form uses it.";
}

export function phoneWarning(value: string): string | null {
  const digits = value.replace(/\D/g, "");
  if (!value.trim() || digits.length >= 7) return null;
  return "A phone number usually has at least 7 digits.";
}

export function linkWarning(value: string): string | null {
  const v = value.trim();
  if (!v) return null;
  if (/\s/.test(v) || !/\.[a-z]{2,}/i.test(v)) return "This doesn't look like a web address.";
  return null;
}
```

Primitives:
- **Input and Textarea:** add
  `data-[warning=true]:border-warning data-[warning=true]:ring-3 data-[warning=true]:ring-warning/20` to the
  class string. `aria-invalid` remains the error state.
- **`Field`:** takes `error` and `warning`. It renders the hint line under the control with an icon:
  - error: `CircleX` in `text-destructive`; sets `aria-invalid` and `aria-describedby`.
  - warning: `TriangleAlert` in `text-warning`; sets `data-warning="true"` and `aria-describedby`.

  Error wins when both are set.

Call sites:
- **Autofill email, phone and links:** `type="email"`/`"tel"`/`"url"`, `autoComplete`
  (`email`/`tel`/`url`) and a warning from the checks, computed on blur, not on every keystroke.
- **Contact form Email:** same.
- **Q&A Answer questions:** `disabled` while every line is blank, plus a hint "Type at least one question."
  tied by `aria-describedby`. Remove the empty-input error toast at ~:79.

**Step 4:** The node test passes, the pytest passes, then `tsc` and lint. Browser: type `sam.example.com` in
Profile › Autofill email, blur, and the amber border and hint show. Save still works.
**Step 5: Commit.** `feat(web): field warning state; checks on the contact fields forms will use`

### Task 13: Never show "empty" before the data is known

**Files:**
- `frontend/components/qa-tab.tsx` (~:262): render a `Skeleton` (two rows) while the history query is
  pending; "No answers yet." only once it has loaded.
- `frontend/components/chat/chat-page.tsx` (~:767, :828–840): while an existing chat's `detail.isPending`,
  render a thread skeleton, not the "What are we working on?" greeting.

**Step 1: Failing pins** (`test_frontend_states.py`):

```python
def test_qa_history_waits_before_saying_empty():
    src = _read("components/qa-tab.tsx")
    assert "Skeleton" in src


def test_an_existing_chat_does_not_greet_while_loading():
    src = _read("components/chat/chat-page.tsx")
    assert "detail.isPending" in src and "Skeleton" in src
```

**Steps 2–5:** FAIL, implement, PASS, then `tsc` and lint. Commit `fix(web): no empty state before data
loads`.

### Task 15: Motion utilities and a count-up

(Numbered 15 to match the research ordering. It runs **first** in Wave 2, because Tasks 7, 8 and 14 use
it.)

**Files:**
- Modify: `frontend/app/globals.css` (utilities layer)
- Create: `frontend/lib/count-up.ts`, `frontend/lib/count-up.test.ts`
- Create: `frontend/hooks/use-count-up.ts`
- Create: `backend/tests/test_frontend_motion.py`

**Step 1: Failing tests.** `frontend/lib/count-up.test.ts`:

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { easeOutCubic, valueAt } from "./count-up.ts";

test("the ease starts at 0, ends at 1 and never overshoots", () => {
  assert.equal(easeOutCubic(0), 0);
  assert.equal(easeOutCubic(1), 1);
  for (let t = 0; t <= 1; t += 0.05) assert.ok(easeOutCubic(t) <= 1);
});

test("valueAt interpolates and clamps time", () => {
  assert.equal(valueAt(10, 20, 0), 10);
  assert.equal(valueAt(10, 20, 1), 20);
  assert.equal(valueAt(10, 20, 2), 20);
  assert.ok(valueAt(10, 20, 0.5) > 15);
});
```

`backend/tests/test_frontend_motion.py`:

```python
"""Small motion that confirms (visual-language plan, Task 15; owner's motion budget D9)."""

import re
from pathlib import Path

from tests.node_ts import run_node_test

_CSS = (Path(__file__).resolve().parents[2] / "frontend/app/globals.css").read_text()


def test_count_up_node_suite():
    result = run_node_test("lib/count-up.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_motion_utilities_exist_and_stay_within_budget():
    for name in ("animate-confirm", "animate-row-exit"):
        assert f".{name}" in _CSS
    for ms in re.findall(r"(\d+)ms", _CSS.split("@layer utilities", 1)[1].split("@media (prefers-reduced-motion", 1)[0]):
        assert int(ms) <= 400 or int(ms) == 1400, ms  # 1400 is the existing shimmer


def test_no_bounce_curve_is_introduced():
    assert "cubic-bezier(0.34, 1.56" not in _CSS and "bounce" not in _CSS.lower()
```

**Step 2:** FAIL.

**Step 3: Implement.** Add to `globals.css` `@layer utilities`:

```css
  /* Confirm a change in place: one soft ring that fades out (a status chip after its value changed). */
  @keyframes confirm-ring {
    from {
      box-shadow: 0 0 0 0 color-mix(in oklab, var(--ring) 45%, transparent);
    }
    to {
      box-shadow: 0 0 0 6px transparent;
    }
  }
  .animate-confirm {
    animation: confirm-ring var(--duration-medium4) var(--ease-standard);
  }

  /* A row leaving a list it no longer belongs to (a skipped proposal). */
  @keyframes row-exit {
    to {
      opacity: 0;
      transform: translateX(16px);
    }
  }
  .animate-row-exit {
    animation: row-exit var(--duration-short4) var(--ease-emphasized-accelerate) forwards;
  }
```

`lib/count-up.ts`:

```ts
// A number moving to its new value (visual-language plan, Task 15). Pure, so node tests it.
export function easeOutCubic(t: number): number {
  const c = Math.min(1, Math.max(0, t));
  return 1 - (1 - c) ** 3;
}

export function valueAt(from: number, to: number, t: number): number {
  return from + (to - from) * easeOutCubic(t);
}
```

`hooks/use-count-up.ts`:

```ts
"use client";

import { useEffect, useRef, useState } from "react";

import { valueAt } from "@/lib/count-up";

/** The displayed value of `target`, counting to each new value over `ms` (no motion when reduced). */
export function useCountUp(target: number, ms = 400): number {
  const [shown, setShown] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    const start = from.current;
    from.current = target;
    if (start === target) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(target);
      return;
    }
    let frame = 0;
    const t0 = performance.now();
    const step = (now: number) => {
      const t = (now - t0) / ms;
      setShown(valueAt(start, target, t));
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, ms]);
  return shown;
}
```

**Step 4:** PASS (node test and pytest), then `tsc` and lint. **Step 5: Commit.**
`feat(web): confirm and row-exit motion utilities; a count-up hook`

**Wave 2 close:** run the build, the full backend suite, the slop check on `frontend` and a browser pass of
every behaviour above at 1280 and 1024. With macOS Reduce motion on, check that the motion stops and the
state still changes. Opus wave review.

---

# Wave 3: Visual primitives

### Task 14: Eight primitives, built once

**Files:**
- Create: `frontend/lib/visual.ts`, `frontend/lib/visual.test.ts`
- Create: `frontend/components/visual/dot-meter.tsx`, `score-bar.tsx`, `segmented-bar.tsx`,
  `progress-count.tsx`, `delta-chip.tsx`, `actor-chip.tsx`, `sparkline.tsx`, and `index.ts` (re-exports)
- Modify: `frontend/components/status-chip.tsx` (export `StatusDot`)
- Create: `backend/tests/test_frontend_visual_primitives.py`
- Create: `docs/design-system/components/<Name>/README.md` for each of the eight, in the existing READMEs'
  shape: prose, then "**You provide:**" with bullets, then "Source:". They have no headings. No `preview.html`; the README's "Not synced" list gains them.

**Step 1: Failing node test** (`frontend/lib/visual.test.ts`):

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { clampPct, formatDelta, meterLabel, segmentShares, sparkPath } from "./visual.ts";

test("clampPct keeps a share between 0 and 100", () => {
  assert.equal(clampPct(50), 50);
  assert.equal(clampPct(150), 100);
  assert.equal(clampPct(-3), 0);
  assert.equal(clampPct(3, 12), 25);
  assert.equal(clampPct(Number.NaN), 0);
  assert.equal(clampPct(1, 0), 0);
});

test("formatDelta signs a change and calls zero flat", () => {
  assert.deepEqual(formatDelta(6.24), { text: "+6.2", sign: "up" });
  assert.deepEqual(formatDelta(-1.36), { text: "−1.4", sign: "down" });
  assert.deepEqual(formatDelta(0.04), { text: "0.0", sign: "flat" });
});

test("meterLabel reads as a sentence", () => {
  assert.equal(meterLabel("Evidence", 3, 5, "Specific, no result"), "Evidence 3 of 5: Specific, no result");
});

test("segmentShares splits a whole and survives an empty one", () => {
  assert.deepEqual(segmentShares([{ key: "a", count: 3 }, { key: "b", count: 1 }]).map((s) => s.share), [75, 25]);
  assert.deepEqual(segmentShares([{ key: "a", count: 0 }]).map((s) => s.share), [0]);
});

test("sparkPath spans the box and handles flat and short series", () => {
  assert.equal(sparkPath([], 100, 20), "");
  assert.match(sparkPath([1, 1, 1], 100, 20), /^M0 10/);
  const d = sparkPath([0, 5, 10], 100, 20);
  assert.ok(d.startsWith("M0 20") && d.endsWith("100 0"));
});
```

`backend/tests/test_frontend_visual_primitives.py` runs it and pins the components:

```python
"""Eight visual primitives with one accessible-text contract each (visual-language plan, Task 14)."""

from pathlib import Path

from tests.node_ts import run_node_test

_VISUAL = Path(__file__).resolve().parents[2] / "frontend/components/visual"
_PRIMITIVES = {
    "dot-meter.tsx": 'role="img"',
    "score-bar.tsx": 'role="meter"',
    "segmented-bar.tsx": "legend",
    "progress-count.tsx": 'role="progressbar"',
    "delta-chip.tsx": "aria-label",
    "actor-chip.tsx": "CONCEPT_ICONS",
    "sparkline.tsx": 'role="img"',
}


def test_visual_helpers_node_suite():
    result = run_node_test("lib/visual.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_each_primitive_carries_its_accessible_text():
    for name, marker in _PRIMITIVES.items():
        assert marker in (_VISUAL / name).read_text(), name


def test_status_dot_takes_its_colour_from_the_status_vocabulary():
    chip = (_VISUAL.parent / "status-chip.tsx").read_text()
    assert "export function StatusDot" in chip and "STATUS_STYLES" in chip.split("export function StatusDot", 1)[1]


def test_primitives_use_roles_not_shades():
    for path in _VISUAL.glob("*.tsx"):
        text = path.read_text()
        assert "bg-muted/" not in text and "#" not in text.replace("#!", ""), path.name
```

**Step 2:** FAIL.

**Step 3: Implement.** First `lib/visual.ts`:

```ts
// Pure helpers behind components/visual (visual-language plan, Task 14). Node tests load this directly.

export function clampPct(value: number, max = 100): number {
  if (!Number.isFinite(value) || !(max > 0)) return 0;
  return Math.min(100, Math.max(0, (value / max) * 100));
}

export type DeltaSign = "up" | "down" | "flat";

/** "+6.2" / "−1.4" (a true minus sign) / "0.0", and which way it went. */
export function formatDelta(value: number, digits = 1): { text: string; sign: DeltaSign } {
  const rounded = Number(value.toFixed(digits));
  if (rounded === 0) return { text: (0).toFixed(digits), sign: "flat" };
  const text = `${rounded > 0 ? "+" : "−"}${Math.abs(rounded).toFixed(digits)}`;
  return { text, sign: rounded > 0 ? "up" : "down" };
}

export function meterLabel(name: string, filled: number, total: number, word: string): string {
  return `${name} ${filled} of ${total}: ${word}`;
}

export function segmentShares<K extends string>(parts: { key: K; count: number }[]): { key: K; share: number }[] {
  const total = parts.reduce((sum, p) => sum + Math.max(0, p.count), 0);
  return parts.map((p) => ({ key: p.key, share: total === 0 ? 0 : (Math.max(0, p.count) / total) * 100 }));
}

/** An SVG path through `values`, x spread across `width`, y scaled into `height` (top = max). */
export function sparkPath(values: number[], width: number, height: number): string {
  if (values.length === 0) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const stepX = values.length === 1 ? 0 : width / (values.length - 1);
  const y = (v: number) => (span === 0 ? height / 2 : height - ((v - min) / span) * height);
  return values
    .map((v, i) => `${i === 0 ? "M" : "L"}${+(i * stepX).toFixed(2)} ${+y(v).toFixed(2)}`)
    .join(" ");
}
```

Components (all `"use client"` only where they need it; most are pure render):

```tsx
// components/visual/dot-meter.tsx
import { meterLabel } from "@/lib/visual";
import { cn } from "@/lib/utils";

/** An ordinal step on a short scale (the health evidence ladder, inbox readiness). The word stays. */
export function DotMeter({ name, filled, total, word, className }: {
  name: string; filled: number; total: number; word: string; className?: string;
}) {
  return (
    <span role="img" aria-label={meterLabel(name, filled, total, word)}
      className={cn("inline-flex items-center gap-1.5 text-body-small", className)}>
      <span className="inline-flex items-center gap-0.5" aria-hidden="true">
        {Array.from({ length: total }, (_, i) => (
          <span key={i} className={cn("size-1.5 rounded-full", i < filled ? "bg-foreground" : "bg-surface-container-highest")} />
        ))}
      </span>
      <span aria-hidden="true">{word}</span>
    </span>
  );
}
```

```tsx
// components/visual/score-bar.tsx
import { clampPct } from "@/lib/visual";
import { cn } from "@/lib/utils";

/** A value on a fixed scale, with the number beside it (an ATS score, skills covered). */
export function ScoreBar({ value, max = 100, label, valueText, digits = 0, width = "w-12", className }: {
  value: number; max?: number; label: string; valueText?: string; digits?: number; width?: string; className?: string;
}) {
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-2", className)}>
      <span role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={value}
        aria-valuetext={valueText}
        className={cn("h-1.5 shrink-0 overflow-hidden rounded-full bg-surface-container", width)}>
        <span className="block h-full rounded-full bg-primary transition-[width] duration-(--duration-medium2) ease-(--ease-standard)"
          style={{ width: `${clampPct(value, max)}%` }} />
      </span>
      <span className="text-label-medium tabular-nums" aria-hidden="true">{valueText ?? value.toFixed(digits)}</span>
    </span>
  );
}
```

- **`segmented-bar.tsx`:** props
  `parts: { key: string; label: string; count: number; tone: "primary" | "muted" | "success" | "warning" | "attention" | "tertiary" | "error" | "empty" }[]`
  and `name: string`.
  - Draws a `flex h-2 gap-0.5 overflow-hidden rounded-full bg-surface-container` row of segments sized by
    `segmentShares`, `aria-hidden`.
  - Under it, a visible `<ul aria-label={name} className="legend …">`: a role-coloured 8px swatch, then
    `{count} {label}`, per part.
  - Tone → class: primary `bg-primary`, muted `bg-muted-foreground`, success `bg-success`, warning
    `bg-warning`, attention `bg-attention`, tertiary `bg-tertiary`, error `bg-destructive`, empty
    `bg-transparent`.
- **`progress-count.tsx`:** props `done`, `total`, `noun` (for example "answered"). Visible text
  `{done} of {total} {noun}`, followed by a `role="progressbar"` bar with `aria-valuenow`, `aria-valuemax`
  and `aria-label`.
- **`delta-chip.tsx`:** props `value`, `prefix?` (for example "up to") and `unit?` (default "points").
  - Uses `formatDelta`. Icon `TrendingUp` `text-success` / `TrendingDown` `text-destructive` / `Minus`.
  - Chip `inline-flex h-5 items-center gap-1 rounded-full bg-surface-container px-2 text-label-medium tabular-nums`.
  - `aria-label={`${prefix ? prefix + " " : ""}${text} ${unit}`}`. Visible text is prefix + text, with the
    icon `aria-hidden`.
- **`actor-chip.tsx`:**
  - Props: `kind: "you" | "assistant" | "agent" | "careerHistory" | "resume" | "document" | "jobWords" | "merged" | "fromResume"`
    and `name?: string`.
  - Icon from `CONCEPT_ICONS` (`you`, `assistant`, `agentInbox`, `careerHistory`, `baseResume`,
    `attachment`, `jobWords`, `merged`, `fromResume`).
  - Default words: You, Assistant, Connected agent, Career history, Your resume, Document, Job's words,
    Merged, From a resume. `name` overrides the word; for agents, pass `agentDisplayName(...)`.
  - Neutral `bg-surface-container text-foreground` chip, h-5 or h-6.
- **`sparkline.tsx`:** props `values: number[]`, `label: string`, `width = 120`, `height = 32`.
  - An `<svg role="img" aria-label={label} viewBox=… preserveAspectRatio="none">`.
  - The area under the line filled `var(--primary-container)`, the line `var(--primary)` at 1.5 stroke,
    and the last point a 2.5r dot.
- **`StatusDot`** in `status-chip.tsx`:

  ```tsx
  /** A status's own dot, for places that list statuses without the chip (filters, analytics). */
  export function StatusDot({ status, className }: { status: ApplicationStatus; className?: string }) {
    return <span aria-hidden="true" className={cn("size-1.5 shrink-0 rounded-full", STATUS_STYLES[status].dot, className)} />;
  }
  ```

**Step 4:** PASS (node test and pins), then `tsc` and lint. Run `test_frontend_design_tokens.py` and
`test_frontend_color_roles.py` (no palette shades, radius tokens only).
**Step 5: Commit.** `feat(web): eight visual primitives with an accessible-text contract`

**Wave 3 close:** run the build and the slop check. Opus review of the primitives' API before surfaces adopt
it; this is the cheapest moment to change a prop name.

---

# Wave 4: Surfaces A

Each surface task: pins first (structure only; never pin a whole sentence a later copy pass might change),
then edits. Then `tsc`, lint and the surface's existing pin files. Browser check at 1280 and 1024, light and
dark. Commit.

### Task 16: The knock-out check strip and the volume swap (Overview)

**Files:**
- `frontend/components/job-knockout-card.tsx` (rewrite the render)
- `frontend/components/job-extracted-fields.tsx` (the stat icons are already swapped in Task 2)
- Test: `backend/tests/test_frontend_visual_surfaces.py` (create; later surface tasks add to it)

**Behaviour:**
- **`clear` and `unstated` become one quiet line, no filled band.**
  - The line: `CircleCheck` (`text-success`) + "No knock-outs" for `clear`, or `CircleHelp` + "No
    requirements listed" for `unstated`.
  - It is followed by the strip.
  - Wrapper: `rounded-corner-md border border-border px-3 py-2`.
- **`conflict` becomes a filled `bg-error-container text-on-error-container` banner.** Today it is
  `border-destructive/40 bg-destructive/5 text-destructive` (:19). It shows `CircleX` + "You may not
  qualify: {first conflicting check's word}".
- **`incomplete_profile`** stays `bg-warning-container`, with its link.
- **The strip.** One compact chip per check present in `scan.checks`, plus one per `uncheckedItems` entry.
  - Label words, keyed by kind: work_authorization "Work auth", opt "OPT", salary "Pay", experience
    "Experience", on_site "On-site".
  - Results, in a `SUMMARY_BY_RESULT` map:

    | Result | Icon | Word | Chip |
    |---|---|---|---|
    | pass | `CircleCheck` `text-success` | OK | `bg-surface-container` |
    | conflict | `CircleX` | Conflict | `bg-error-container text-on-error-container` |
    | warning | `TriangleAlert` | Warning | `bg-warning-container text-on-warning-container` |
    | profile_missing | `CircleHelp` | Add answer | links to the profile, via the existing hrefs |
    | job_unstated | `Minus` | Not listed | `bg-surface-container text-muted-foreground` |
    | an unchecked item | `CircleDashed` | Not run | link to its field |

  - Each chip's accessible text is `"{label}: {word}"`.
- **Messages.** Server messages for conflict, warning and profile_missing render under the strip as before,
  each prefixed by its label word, with the icon of its result instead of the shared `AlertTriangle`.
- **The detail line goes** for `clear` (it repeated the headline). The `uncheckedSentence` paragraph goes:
  the strip's "Not run" chips and their links say it.

**Pins:**

```python
def test_knockout_pass_is_quiet_and_conflict_is_loud():
    src = _read("components/job-knockout-card.tsx")
    assert "bg-success-container" not in src          # a pass is not a filled band any more
    assert "bg-error-container" in src                # a conflict is
    for word in ("OK", "Conflict", "Warning", "Add answer", "Not listed", "Not run"):
        assert f'"{word}"' in src, word


def test_knockout_rows_use_their_result_icon():
    assert "AlertTriangle" not in _read("components/job-knockout-card.tsx")
```

**Existing pins to rewrite in this commit:**
- `test_frontend_jobs_honest_words.py:39-40` (the `clear` label "Nothing rules you out" and its detail; the
  label becomes "No knock-outs" and the detail goes)
- `:50` (the `uncheckedSentence` template, deleted)
- `:66` (the `uncheckedLabel` "check: not run yet", replaced by the "Not run" chips)
- `:345` (the sentence-case list entry for "That doesn't mean you qualify."). Keep that safety meaning: the
  `unstated` line's accessible text says it.
- `CHECK_GROUP` and `anchorHref("/profile", group ?` stay as they are, so
  `test_frontend_job_submitted_tab.py:160` and `test_frontend_settings_pages.py:214,318` hold.

**Browser.** Check three jobs: one that passes, one with a conflict and one missing pay. The passing job's
Overview top is now a quiet line; the conflict is the loudest thing on the page.
**Commit:** `feat(web): knock-out check strip; a pass is quiet, a conflict is loud`

### Task 17: Job header: the best score, and locked tabs

**Files:**
- `frontend/app/jobs/[id]/page.tsx`:
  - The identity header gains a best-score pill beside the status chip.
  - The locked Resume and Q&A tab triggers gain `CONCEPT_ICONS.locked`.
  - The always-visible `LOCKED_REASON` paragraph under the tabs (:620-621) becomes `sr-only`; it is not
    deleted. It is the triggers' `aria-describedby` target, pinned by `test_frontend_jobs_honest_words.py:271`
    together with `"{LOCKED_REASON}"`. The triggers already carry `title: LOCKED_REASON` (:96), so sighted
    users keep it on hover.
- **Data.** `GET /jobs/{id}/detail` (`JobDetail`, `types.ts:153-159`) carries no scores. Read the Score tab's
  own query, key `["ats-scores", jobId]` via `listAtsScores(jobId)` (`ats-score-panel.tsx:330`,
  `lib/api.ts:184`). It only lists and never scores, so it is safe on the header. Take the best `phase === "base"`
  row, as the panel's sort does (:478-480).
  With no score yet, render nothing; never "0". Pill: "Best" (muted), then `ScoreBar` with `valueText` =
  composite to 1 decimal, then the base name in `text-muted-foreground`, inside a
  `rounded-full bg-surface-container-low px-2.5 h-7` wrapper.

**Pins:**

```python
def test_job_header_shows_the_best_score_and_locks_tabs_with_an_icon():
    src = _read("app/jobs/[id]/page.tsx")
    assert "ScoreBar" in src and "CONCEPT_ICONS.locked" in src
```

**Commit:** `feat(web): the job header carries its best score; locked tabs show a lock`

### Task 18: Score and tailor cards

**Files:** `frontend/components/ats-score-panel.tsx`

**Behaviour:**
- **One banner for a shared warning.** A gate warning present on **every** base row becomes one banner above
  the grid (the same `bg-warning-container` box `LOW_COVERAGE_ON_EVERY_RESUME` uses), with a `TriangleAlert`.
  Cards stop repeating it: pass a `sharedWarnings: Set<string>` and filter it out of each card's
  `gateWarnings`. Warnings unique to a card stay on the card.
- **"Weakest" (D4).** In `SubscoreBar`, the lowest subscore of a card (ties: the first) gets
  `<span className="inline-flex h-4 items-center rounded-full bg-surface-container px-1.5 text-label-small">Weakest</span>`
  after its label. It is a word only: `ArrowDown` means "Lost" in Task 22. No colour change on the bar.
- **Drop " of 100".** The visible " of 100" goes from each subscore row. The bar gains
  `role="meter" aria-valuenow aria-valuemax=100 aria-label={label}` (use `ScoreBar` with `width="w-full"`, or
  give the existing bar those attributes). Keep the card's headline "/ 100".
- **Coverage.** When `jd_skills_extracted_count > 0`, render
  `ScoreBar value={matched} max={extracted} label="Skills covered" valueText={`${matched} of ${extracted}`} width="flex-1"`
  with the muted label "Skills covered". The coverage sentence stays only when `showCoverage` and the ratio
  is under the warning line. That rule exists today; keep it.
- **Gap progress.** "Continue gap analysis · 3 answered" becomes "Continue gap analysis" on the button, with
  `ProgressCount done={answered} total={totalGaps} noun="answered"` above it. `gapCounts` gives both; read
  its return shape.
- **The best match leads.** At `@3xl`, the top card spans two columns (`@3xl:col-span-2`) and lays its
  subscores in two columns (`grid @3xl:grid-cols-2 gap-x-6`). The others keep one column. No other layout
  change.
- **The headline number counts.** It uses `useCountUp(score.composite)` (Task 15) so an Update scores visibly
  moves it.

**Pins:**

```python
def test_score_cards_hoist_shared_warnings_and_mark_the_weakest():
    src = _read("components/ats-score-panel.tsx")
    assert "sharedWarnings" in src and "Weakest" in src
    assert "ProgressCount" in src and "useCountUp" in src
    assert '"> of 100"' not in src and "> of 100<" not in src
```

**Existing pins to rewrite in this commit:**
- `test_frontend_jobs_honest_words.py:425` (`<span className="text-body-small text-muted-foreground"> of 100</span>`)
- `:99` (the `` ` · ${answered} answered` `` button suffix)

**Browser.** Check a job where all five bases share the years warning: one banner shows and the cards are
quieter. Press Update scores: the numbers count.
**Commit:** `feat(web): score cards hoist shared warnings, mark the weakest, meter coverage`

### Task 19: Gap analysis

**Files:**
- `frontend/components/gap-analysis/resolution-controls.tsx`
- `frontend/components/gap-analysis/gap-card.tsx`
- `frontend/app/jobs/[id]/tailor/[sessionId]/page.tsx`
- `frontend/components/resume-editor/diff-review.tsx` (`ProvenanceChip` gains icons via `ActorChip`)

**Behaviour:**
- **Action icons** (the word stays). `ACTION_ICONS: Record<GapAction, LucideIcon>`:

  | Action | Icon |
  |---|---|
  | add_keyword | `Tag` |
  | user_input | `MessageSquareText` |
  | attach_project | `CONCEPT_ICONS.project` |
  | skip | `SkipForward` |
  | enable_entry | `Eye` |
  | port_kb_point | `CONCEPT_ICONS.careerHistory` |
  | cannot_confirm | `Ban` |

  `ActionSegment` draws each icon at `size-3` before its label. The resolved-row summary leads with the icon
  of the action taken, replacing the generic `Check`. `Check` appears at both `gap-card.tsx:619` and `:637`;
  replace both.
- **Explain once.**
  - The page-level paragraph that explains every action (~:779–788) goes.
  - Each action's explanation moves into an `ACTION_HINTS` map. Use the paragraph's own clauses: Add keyword
    "Puts the skill in your Skills section.", and so on. Keep `CANNOT_CONFIRM_EXPLANATION` for cannot_confirm.
  - Each hint is shown as the segment button's tooltip and set as its `aria-describedby`. One visually hidden
    `<span id>` per action, rendered once per page, keeps ids unique.
  - The per-card visible `CANNOT_CONFIRM_EXPLANATION` (`gap-card.tsx` ~:697–699) goes; the resolved row keeps
    it (~:543).
  - "Only what you write here is used." **stays visible**. It is already the Textarea's `aria-describedby`
    `<p id>` (`resolution-controls.tsx:488-494`), with a comment saying it must stay on screen, and is pinned
    by `test_frontend_placeholders.py:552`.
  - Only "Pick one to use it…" (:604-607) moves into an `aria-describedby` hint plus a tooltip on an `Info`
    icon (size 3.5, IconButton labelled "About this field"). Not `CircleHelp`: in the register that means
    unknown.
- **Progress footer.** "3 answered · 1 skipped · 4 open" becomes
  `SegmentedBar name="Gap progress" parts=[answered primary, skipped muted, open empty]`, which keeps the
  legend words.
- **Categories.** Each category header's "N open" / "Nothing open" badge becomes "{resolved}/{total}"
  (`text-label-medium tabular-nums`), with a `CircleCheck` `text-success` when nothing is open. The
  accessible name is "{resolved} of {total} handled".
- **Points.** `formatPotentialPoints` users render `DeltaChip value={points} prefix="up to"`.
- **Provenance.** Gap-card provenance lines ("Filled in from your career history" etc., ~:209–223) become
  `ActorChip kind="careerHistory" | "resume" | "jobWords"` with the existing sentence as its `title`.
  `diff-review.tsx` `ProvenanceChip` renders `ActorChip`:

  | Provenance | ActorChip |
  |---|---|
  | kb_auto | careerHistory, name "From your career history" |
  | user | you |
  | llm | `kind` "assistant", name "AI" |

  `diff-review.tsx:395` returns `null` for **every** `llm` hunk (pinned by `test_frontend_resume_review.py:367`).
  That stays: the llm row of the map exists only for the legend (:712-714).
- **Resolving collapses.** When a card resolves, it collapses with the grid-rows transition from Task 8
  (`duration-short4`).

**Pins:**

```python
def test_gap_actions_carry_icons_and_explain_once():
    rc = _read("components/gap-analysis/resolution-controls.tsx")
    assert "ACTION_ICONS" in rc and "ACTION_HINTS" in rc
    card = _read("components/gap-analysis/gap-card.tsx")
    assert card.count("{CANNOT_CONFIRM_EXPLANATION}") == 1   # the resolved row only
    page = _read("app/jobs/[id]/tailor/[sessionId]/page.tsx")
    assert "SegmentedBar" in page


def test_gap_provenance_and_points_are_chips():
    card = _read("components/gap-analysis/gap-card.tsx")
    assert "ActorChip" in card and "DeltaChip" in card
    assert "ActorChip" in _read("components/resume-editor/diff-review.tsx")
```

**Existing pins to rewrite in this commit:**
- `test_frontend_jobs_honest_words.py:95-96` (the footer's `"</span> answered\n"` and the `Nothing open`
  badge template)
- `test_frontend_plain_words.py:337` (the same footer string)
- `test_frontend_jobs_honest_words.py:112` (`page.index("These gaps need your input.")`, which raises once
  the paragraph goes; re-point it at `ACTION_HINTS`)

**Browser.** On a session with mixed gaps, tab through the segments: each hint is announced. Resolve a gap:
it collapses, and its row shows the chosen action's icon.
**Commit:** `feat(web): gap actions with icons, hints said once, a progress bar, provenance chips`

### Task 20: Health report rows and question pass

**Files:**
- `frontend/components/resume-health/finding-cards.tsx` (`LevelChip`, `CollapsedRow`, the gain line at
  ~:623)
- `frontend/components/resume-health/health-badges.tsx` (`HealthListChip`)
- `frontend/components/resume-health/question-pass.tsx` (row states, the sticky progress)
- `frontend/components/gallery/preview-thumbnail.tsx` (the loading state)

**Behaviour:**
- **`LevelChip` becomes a `DotMeter`:** `name="Evidence"`, `total={5}` and `filled` from the level's place on
  the ladder. Order (filled count): unaddressed 1, implied 2, adjacent 3, analogue 4, direct 5. Derive it
  from `EVIDENCE_LEVELS` order (reversed index + 1), not a second table. `word` is `EVIDENCE_LABELS[name]`.
- **The collapsed row's meta line:** `{finding.label}`, then the DotMeter, then, for `zone === "hot"`, a chip
  `<span className="inline-flex h-5 items-center gap-1 rounded-full bg-secondary-container px-2 text-label-medium text-on-secondary-container"><ChevronsUp className="size-3" aria-hidden="true" />{ATTENTION_BADGE_LABEL}</span>`.
  Not attention colours (attention means Needs you).
- **"Up to +{points} points"** becomes `DeltaChip value={points} prefix="up to"`.
- **`HealthListChip`** gains `CONCEPT_ICONS.health` before the grade letter. The chip's accessible name stays
  as today ("Grade A, score 90. Open report.").
- **Question-pass row states** become glyph + word. The states are `PassStatus` in
  `lib/health-report.ts:937-948`, and a separate `skipped` boolean. Words are at
  `question-pass.tsx:475, 552-555, 602`:

  | State | Glyph |
  |---|---|
  | `queued` ("Waiting to write…") | `Clock` |
  | `drafting` ("Writing…") | `Loader2` spinning |
  | `failed` (couldn't write) | `CircleX` `text-destructive` |
  | the `skipped` row ("Skipped for now.") | `SkipForward` |
  | `drafted` | `CircleCheck` `text-success` |
  | "No change to save" | `Minus` |

  Keep the existing words.
- **The sticky footer** keeps `passProgress` and `{progress.words}` (pinned by
  `test_frontend_question_pass.py:57-63`). It adds the bar part of `ProgressCount` from
  `progress.answered`/`progress.total`, or a bar beside the words; don't drop the pinned words.
- **Base resume cards.** The placeholder lives in the shared `components/gallery/preview-thumbnail.tsx`
  (:51-75; it is used by Templates too). It has a `FileText size-6 opacity-40` + "No PDF yet" placeholder,
  but the live tour saw blank white cards: the `<img>` shows while it loads. Show a `Skeleton` until the
  image's `onLoad`, and the existing placeholder on `onError`. "No PDF yet" stays (allow-listed in
  `test_frontend_placeholders.py:73`).

**Pins:**

```python
def test_health_rows_draw_the_evidence_ladder_and_priority_chip():
    src = _read("components/resume-health/finding-cards.tsx")
    assert "DotMeter" in src and "ChevronsUp" in src and "DeltaChip" in src
    assert "CONCEPT_ICONS.health" in _read("components/resume-health/health-badges.tsx")
    assert "ProgressCount" in _read("components/resume-health/question-pass.tsx")
```

Run `test_frontend_health_report.py` and `test_frontend_question_pass.py`, and update their string pins in
the same commit.
**Commit:** `feat(web): health rows show the evidence ladder; question pass shows progress`

**Wave 4 close:** the standard close, plus an Opus goal critique of the surfaces against the Goal Card.

---

# Wave 5: Surfaces B

### Task 21: Agent inbox rows and page top

**Files:**
- `frontend/components/proposals/proposals-section.tsx`
- `frontend/components/proposals/arrivals-strip.tsx`
- `frontend/components/proposals/recent-runs.tsx`
- `frontend/components/proposals/cap-today.tsx`
- `frontend/components/proposals/readiness-marks.tsx`. Readiness renders here; the row's
  `<ReadinessMarks readiness={proposal.readiness} />` call (:856) is pinned by `test_frontend_agent_inbox.py:789`
  and stays.
- `frontend/components/ui/stat-tile.tsx` or wherever `StatTile` lives (an optional `icon` slot)
- `frontend/lib/inbox-readiness.ts`, `frontend/lib/inbox-readiness.test.ts` (it exists; add to it)

**Behaviour:**
- **Meta line.** "Proposed by X · 7 days ago" becomes `ActorChip kind="agent" name={agentDisplayName(...)}`
  (or `kind="you"` for a `you` filer) plus the relative time. Inside a lane, drop the verb. The full sentence
  stays as the line's `title`.
- **Base chip.** "Data Engineer · ATS score 62.4" becomes the base name (muted) plus
  `ScoreBar value={score} label="ATS score" valueText={score.toFixed(1)}`.
- **Status badge (D5).** Hidden when the row is in a lane whose rows all share one status: To review,
  Queued, Applying. Shown in History and Needs you. The `lane` prop is
  `"needs_you" | "triage" | "queued" | "in_flight" | "history"` (:759), so the rule is
  `lane !== "history" && lane !== "needs_you"` → hide.
- **Readiness.** Add `readinessSteps(r)` to `lib/inbox-readiness.ts`:

  ```ts
  /** The three readiness steps as a meter: tailored, no knock-out, answers checked. Null without readiness. */
  export function readinessSteps(r: Readiness | null | undefined): { done: number; total: 3 } | null {
    if (!r) return null;
    const done = [r.tailored === true, r.knockout == null, r.to_check === 0].filter(Boolean).length;
    return { done, total: 3 };
  }
  ```

  `ReadinessMarks` renders a `DotMeter name="Ready" filled={done} total={3} word={`${done} of 3 ready`}` when
  not ready, and a chip `CircleCheck` "Ready" (`bg-success-container text-on-success-container`) when
  `isReady`. The knock-out mark stays as a warning chip.
- **OPT warning merge.** "May not accept OPT" and a knock-out chip are not both shown. The existing condition
  already hides OPT when readiness says opt. Fold "Possible duplicate" into the same chip style
  (`bg-warning-container`, `TriangleAlert`, size 3).
- **Arrivals strip.** The tiles are `StatTile`s (`arrivals-strip.tsx:42`; keys `new`, `ready`, `needs_you`,
  `applied_this_week`). `StatTile` gains an optional `icon` slot. When every tile is 0, render one muted line: "Nothing new since your last visit". The
  tiles keep their current layout otherwise. Only the two tiles whose glyph already means their thing gain one:
  - Ready: `CircleCheck` `text-success`.
  - Needs you: the attention dot, from the `NEEDS_YOU` role in `status-chip.tsx`.
  - New and Applied stay words only. `SendHorizontal` means Queue in the register, and the primary dot means
    New on rows; reusing either for a second tile would give a glyph two meanings.

- **Recent runs.**
  - Empty: one line, `Bot` icon + "No runs yet." + the Automations link.
  - The run outcome becomes glyph + word: `CircleCheck` Done, `CircleAlert` Partly done, `CircleX` Failed,
    on a surface chip. Read `lib/agent-runs.ts` for the outcome values.
  - The counts line stays text.
- **Cap.** It stays a 24-hour window, never "today" (`cap-today.tsx:17,31`). It becomes
  `ProgressCount done={cap.reserved_last_24h} total={cap.max_per_day} noun="used in the last 24 hours"`,
  with the sentence "Applications per day: …" kept as visible lead text or `title`.
  - **Pins:** `test_frontend_agent_inbox.py:89` and `test_frontend_jobs_honest_analytics.py:35` hold the
    sentence verbatim. Keep it rendered so both stay true, or rewrite both in this commit.

**Node test** (`frontend/lib/inbox-readiness.test.ts`, add if the file exists):

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { readinessSteps } from "./inbox-readiness.ts";

test("readiness steps count what is done", () => {
  assert.equal(readinessSteps(null), null);
  assert.deepEqual(readinessSteps({ tailored: true, knockout: null, to_check: 0 }), { done: 3, total: 3 });
  assert.deepEqual(readinessSteps({ tailored: false, knockout: "opt", to_check: 2 }), { done: 0, total: 3 });
  assert.deepEqual(readinessSteps({ tailored: null, knockout: null, to_check: 1 }), { done: 1, total: 3 });
});
```

Run it from `test_frontend_agent_inbox.py` via `run_node_test` (add a test function).

**Pins:**

```python
def test_inbox_rows_use_actor_score_and_readiness_visuals():
    src = _read("components/proposals/proposals-section.tsx")
    assert "ActorChip" in src and "ScoreBar" in src and "DotMeter" in src
    assert "ATS score ${score}" not in src and "· ATS score" not in src


def test_empty_inbox_top_collapses():
    assert "Nothing new since your last visit" in _read("components/proposals/arrivals-strip.tsx")
```

**Existing pins to rewrite in this commit:**
- **`test_frontend_agent_inbox.py`:**
  - :294-300 (`byLine`/`meta` lines verbatim, `title={meta}`). Keep `meta` as the `title`.
  - :324-327 (the `agent-name.ts` templates, unchanged)
  - :789 (unchanged, by design)
- **`test_frontend_agent_dashboard.py`:**
  - :38, :42 (the tile labels and `disabled={!count}`). Keep the labels.
  - :49 ("No runs yet. Set one up on Automations."). Keep it.
  - :52 (`outcomeWord(`). Keep it.

`test_frontend_proposed_by.py` has no "Proposed by" assertion.
**Commit:** `feat(web): inbox rows show who, score and readiness at a glance; an empty top collapses`

### Task 22: Resume tab steps and the before/after change column

**Files:** `frontend/components/application-panel.tsx` (OutputTab), `frontend/components/ats-compare-panel.tsx`

**Behaviour:**
- **OutputTab.**
  - The `status` sentence and the Badge go. The header shows a two-step line: Draft, `ChevronRight`, PDF.
    Each step is `CONCEPT_ICONS.done` `text-success` when done and `CONCEPT_ICONS.notRun`
    `text-muted-foreground` when not, with its word.
  - The wrapper's `aria-label` reads "Draft done. PDF not created yet", or "…PDF ready".
  - The placeholder keeps one line: "No PDF yet." with a draft, and "No tailored resume yet. Start on the
    Score and tailor tab." without one. That second sentence is the guidance that used to live in `status`.
- **Compare panel.**
  - **Skill table.** Columns Skill, Change, Now. Change is `ArrowUp` + "Gained" (`text-success`) when
    before missing → after matched, `ArrowDown` + "Lost" (`text-destructive`) for the reverse, and `Minus` +
    "Same" (muted) otherwise. Now shows the after state's note (placement or fix hint), as
    `SkillStateCell`'s note does. Sort Gained first, then Lost, then Same.
  - **`DeltaBar`.** Zero renders neutral (`formatDelta` → `flat`: `text-muted-foreground`, no bar, a
    `Minus`). The bar diverges from the centre: a `relative` track with a 1px centre line, the fill from 50%
    to the right (gain) or left (loss), width `|pts|/2 %` of the track, capped at 50%.
  - **Headline.** It keeps its numbers and its `MoveRight` icon between them (there is no literal "→"), and
    renders the delta through `DeltaChip`.

**Pins:**

```python
def test_resume_tab_says_its_state_once():
    src = _read("components/application-panel.tsx")
    assert "Your PDF is ready." not in src and '"Not yet a PDF"' not in src


def test_compare_shows_what_changed():
    src = _read("components/ats-compare-panel.tsx")
    for word in ("Gained", "Lost", "Same"):
        assert f'"{word}"' in src or f">{word}<" in src
    assert "formatDelta" in src or "DeltaChip" in src
```

**Existing pins to rewrite in this commit:**
- `test_frontend_first_read_words.py:33` (the Badge ternary `{pdfReady ? "PDF ready" : hasDraft ? "Not yet a PDF" : "Not started"}`)
- `test_frontend_color_roles.py:714-715` (the `DeltaBar` colours and the Matched class), if the change column
  replaces them

**Commit:** `feat(web): Resume tab shows Draft → PDF; compare shows what changed`

### Task 23: Assistant tool chips and cards

**Files:**
- `frontend/components/chat/chat-page.tsx` (`TOOL_PHRASES`, ~:97–123; the chip render, ~:787–793)
- `frontend/components/chat/proposal-card.tsx`, `edit-proposal-card.tsx`, `change-card.tsx`,
  `kb-capture-card.tsx`

**Behaviour:**
- **Tool chips.** `TOOL_PHRASES` entries gain a concept, `{ phrase, concept }`. The chip renders that
  concept's icon (`baseResume`, `careerHistory`, `analytics`, `templates`, `attachment`; default
  `assistant`) and a short word. Keep the phrase as the chip's `title` and sr text.
  - While the tool runs: `Loader2` spinning in place of the icon.
  - **The stream sends only `tool_start`** (`lib/types.ts:1729`; `chat-page.tsx:455-458`) and nothing marks a
    finished tool. A chip counts as finished when a later `tool_start`, a text delta or a card event arrives,
    or when the stream ends. It then shows `CircleCheck` for 1.2s, then the domain icon. No stream change
    (non-goal).
  - `Wrench` is no longer used.
- **Card kind badges:**

  | Card | Badge |
  |---|---|
  | "Suggested project", "Suggested edits" | `Sparkles` + word |
  | "Edited" | `FileDiff` + word |
  | KB capture | `CONCEPT_ICONS.careerHistory` + "Career history" |

- **Resolutions.** Resolved states read `CircleCheck` "Applied" / "Added" (done, per D2) or `X`
  "Discarded", and the resolved card takes `opacity-80`.

**Pins:**

```python
def test_assistant_tool_chips_show_their_domain():
    src = _read("components/chat/chat-page.tsx")
    assert "Wrench" not in src and "concept:" in src and "CONCEPT_ICONS" in src
```

**Existing pins to rewrite in this commit** (they are in `test_frontend_settings_assistant_words.py`, not
the layout file):
- `:127` (`toolPhrases(streaming.tools).map((phrase) =>`): keep the call, or rewrite.
- `:132`, the regex `\["(\w+)", "[^"]+…"\]` over `const TOOL_PHRASES`. With `{ phrase, concept }` entries it
  matches nothing, and the "every chat tool has a phrase" check fails. Rewrite it to
  `\["(\w+)", \{ phrase: "[^"]+…"`, so it still proves every tool is phrased.

**Commit:** `feat(web): Assistant tool chips show their domain and finish with a check`

### Task 24: Career history bullets

**Files:**
- `frontend/components/career/points-list.tsx` (~:61–85 origin and provenance maps; chips ~:343–389)
- `frontend/components/career/inbox-panel.tsx` (draft rows)

**Behaviour:**
- **One `ActorChip` for origin.** The origin and provenance chips merge.
  - Origin → kind:

    | Origin | ActorChip |
    |---|---|
    | You | you |
    | Document | document |
    | Assistant | assistant |
    | Connected agent / From {agent} | agent with the name |
    | Merged | merged |
    | Your answer | you, name "Your answer" |
    | From a resume | fromResume |

  - Provenance appears only when trust is in doubt: "AI inferred" as a trailing `Sparkles` + "AI inferred"
    inside the same chip, and "You couldn't confirm this" as `CircleHelp` + "Unconfirmed". Keep the full
    provenance words as the chip's `title`.
  - "From your own material", "You said it" and "Unknown source" add nothing visible beyond the origin chip.
    They stay in `title`.
- **Usage.** "On 2 resumes" becomes `CONCEPT_ICONS.baseResume` + "2". Its `aria-label` keeps the retired
  distinction: ``${point.state === "retired" ? "Still on" : "On"} ${n} ${n === 1 ? "resume" : "resumes"}``
  (pinned by `test_frontend_resume_review.py:164`).
- **Drift.** "Wording differs" already has `TriangleAlert` (:367). Only its colour becomes `text-warning`, on
  a neutral chip.
- **State chip.** Draft / Approved / Not used is unchanged.
- **Drafts.** Draft rows in Drafts to review render the same origin `ActorChip`.

**Pins:**

```python
def test_career_bullets_merge_origin_and_trust():
    src = _read("components/career/points-list.tsx")
    assert "ActorChip" in src
    assert "ActorChip" in _read("components/career/inbox-panel.tsx")
```

**Existing pins:** the word pins are in `test_frontend_resume_review.py:164, 270-276` and
`test_frontend_agent_words.py:33-36`. `ORIGIN_LABELS`/`PROVENANCE_LABELS` and the `From ${agent}` template
stay as data; the chip reads from them. Keep the manual/user_stated hide rule. Draft rows in `inbox-panel.tsx`
render no origin today, so adding it is new.
**Commit:** `feat(web): career history bullets show who and how sure in one chip`

### Task 25: Jobs tracker: score column, filter dots, a "what needs me" strip

**Backend (TDD).** The only API change in this plan (D6).
- Modify: `backend/app/schemas/application.py` (`ApplicationSummary.ats_score: float | None = None`)
- Modify: `backend/app/schemas/job.py` (`JobSummary.best_ats_score: float | None = None`; find the list
  response model of `GET /api/jobs`)
- Modify: `backend/app/services/ats_score.py` (two read helpers)
- Modify: `backend/app/routers/applications.py` (`list_applications`) and `backend/app/routers/jobs.py` (the
  list, stamping a transient attribute like `_stamp_newest_proposal`)
- Test: `backend/tests/test_tracker_scores.py` (create)
- Docs: `docs/entities/application.md` and `docs/entities/job.md` (list projection fields), and
  `frontend/lib/types.ts`

**Rules:**
- **An application's score** is its newest `phase="tailored"` row for that application if one exists.
  Otherwise it is the `phase="base"` row for `(job_id, target_type="base_resume", target_id=application.base_resume)`.
  Otherwise null.
- **A saved job's best score** is the max `composite` over its `phase="base"` rows. Null when none.
- **No scoring on read.** Never call `score_*`/`compare`/`best_base` here; they can backfill and commit.
- **One query per kind** for the whole page, with no N+1.

**Step 1: Failing test** (`backend/tests/test_tracker_scores.py`). There is no shared `client`, `make_job` or
`make_application` fixture. Build the test from what exists:

- **`db_session`** is the shared fixture (`conftest.py:175`).
- **A client:** router tests use `app.dependency_overrides[get_db] = _override_db(db_session)` +
  `TestClient(app)`. Copy the local helper and fixture from `tests/test_applications_router.py` /
  `tests/test_jobs_router.py`.
- **Jobs:** seeded with a file-local `_job(db_session, …)` (`test_applications_router.py:87`); copy it.
  Applications: copy that file's way of creating one.
- **Score rows:** copy the factory `_row` from `tests/ats/test_ats_score_service.py:32-40`.
- **The base-row unique index** is `uq_ats_scores_base_target(job_id, target_type, target_id) where phase='base'`.
  The two base rows below use different `target_id`s, so they do not collide.

Shape (the names `client`, `make_job`, `make_application` and `_score` stand for those copied helpers):

```python
def test_application_summary_carries_tailored_else_base_score(client, db_session, make_job, make_application):
    job = make_job()
    app = make_application(job=job, base_resume="data_scientist")
    _score(db_session, job, target_type="base_resume", target_id="data_scientist", phase="base", composite=61.0)
    rows = client.get("/api/applications").json()
    assert next(r for r in rows if r["id"] == str(app.id))["ats_score"] == 61.0
    _score(db_session, job, target_type="application", target_id=str(app.id), application_id=app.id,
           phase="tailored", composite=67.2)
    rows = client.get("/api/applications").json()
    assert next(r for r in rows if r["id"] == str(app.id))["ats_score"] == 67.2


def test_saved_job_carries_its_best_base_score(client, db_session, make_job):
    job = make_job()
    _score(db_session, job, target_type="base_resume", target_id="a", phase="base", composite=55.0)
    _score(db_session, job, target_type="base_resume", target_id="b", phase="base", composite=62.5)
    rows = client.get("/api/jobs?without_application=true").json()
    assert next(r for r in rows if r["id"] == str(job.id))["best_ats_score"] == 62.5


def test_no_score_reads_null_not_zero(client, make_job):
    job = make_job()
    rows = client.get("/api/jobs?without_application=true").json()
    assert next(r for r in rows if r["id"] == str(job.id))["best_ats_score"] is None
```

The fixture names (`make_job`, `make_application`, `_score`) are placeholders. Use the repo's real
factories, and write `_score` as a small local helper that inserts an `AtsScore` with the required non-null
columns: `subscores_json={}`, `skill_table_json=[]`, `config_version`/`engine_version` strings.

**Step 2:** `python -m pytest tests/test_tracker_scores.py -q` fails.

**Step 3: Implement** the helpers in `services/ats_score.py`. Its import line (:4) has only `not_, select`;
add `func`:

```python
def tracker_scores(session: Session, applications: list[Application]) -> dict[UUID, float]:
    """The score each tracker row shows: the newest tailored row, else the base row for its resume.
    Read-only: never scores or backfills (the list must not write)."""
    if not applications:
        return {}
    ids = [a.id for a in applications]
    out: dict[UUID, float] = {}
    for app_id, composite in session.execute(
        select(AtsScore.application_id, AtsScore.composite)
        .where(AtsScore.phase == "tailored", AtsScore.application_id.in_(ids))
        .order_by(AtsScore.created_at.desc())
    ):
        out.setdefault(app_id, float(composite))
    missing = [a for a in applications if a.id not in out]
    if missing:
        base = {
            (job_id, target_id): float(composite)
            for job_id, target_id, composite in session.execute(
                select(AtsScore.job_id, AtsScore.target_id, AtsScore.composite).where(
                    AtsScore.phase == "base",
                    AtsScore.target_type == "base_resume",
                    AtsScore.job_id.in_({a.job_id for a in missing}),
                )
            )
        }
        for a in missing:
            score = base.get((a.job_id, a.base_resume))
            if score is not None:
                out[a.id] = score
    return out


def best_base_scores(session: Session, job_ids: list[UUID]) -> dict[UUID, float]:
    """Each job's best base-resume score, read-only."""
    if not job_ids:
        return {}
    return {
        job_id: float(best)
        for job_id, best in session.execute(
            select(AtsScore.job_id, func.max(AtsScore.composite))
            .where(AtsScore.phase == "base", AtsScore.job_id.in_(job_ids))
            .group_by(AtsScore.job_id)
        )
    }
```

Then wire them up:
- **`list_applications`:** collect the page's applications, call `tracker_scores`, set `summary.ats_score`.
- **The jobs list:** call `best_base_scores` and stamp `job.best_ats_score` as a transient attribute; add the
  field to the list schema.
- **MCP.** `list_applications` passes the field through unchanged (`mcp_server/client.py:1073`, a thin
  wrapper). Update the `list_jobs` docstring (`mcp_server/client.py:309-311`) to name `best_ats_score`, and
  check the docstring-budget ratchet in `mcp_server/tests/test_server.py` still passes.

**Step 4:** The new tests pass. Run the full backend suite with xdist.

**Frontend:**
- `lib/types.ts`: add `ats_score?: number | null` to `ApplicationSummary` and `best_ats_score?: number | null`
  to `Job` (or the list type the tracker uses).
- `app/applications/page.tsx`:
  - **ATS column** between Resume and Status: `ScoreBar value={score} label="ATS score" valueText={score.toFixed(1)}`.
    Empty is `—` with an sr "No score yet". Sortable like the others, if the sort model takes a new key
    cheaply. If not, not sortable, with a deviation note.
  - **Status filter.** Options and the trigger show `StatusDot` before each application status label. Agent
    lane options show their lane chip's dot colour (`PROPOSAL_STATUS_CHIP` classes); reuse, don't copy.
  - **A strip above the table**, shown only when any count is above 0: three tonal buttons, "Needs you ·
    {n}", "Interviewing · {n}", "Drafts not applied · {n}". Each sets the existing Status filter to
    `needs_you`, `interviewing` or `draft` (verify the filter values) and gets `aria-pressed` + a leading
    `Check` when that filter is active, per the selected-in-set rule. Counts come from data the page already
    has.

**Pins:**

```python
def test_tracker_shows_scores_dots_and_a_needs_strip():
    src = _read("app/applications/page.tsx")
    assert "ScoreBar" in src and "StatusDot" in src and "Drafts not applied" in src
```

Run `test_frontend_jobs_page_words.py`, `test_frontend_sticky_lists.py` and the `jobs_honest_*` pins.

**Commit:** two commits. `feat(api): tracker rows carry their ATS score (read-only)`, then
`feat(web): Jobs shows the score, status dots and a needs-you strip`.

### Task 26: Analytics

**Files:**
- `frontend/components/analytics/analytics-overview.tsx` (status count pills ~:139–151; the Applied tile
  ~:99–132; the gap rows ~:176–185)
- `frontend/components/analytics/agent-pipeline-card.tsx`

**Behaviour:**
- **Status count pills** become one `SegmentedBar name="Applications by status"`, with one part per status
  in `APPLICATION_STATUSES` order. The tone mapping mirrors `STATUS_STYLES`: draft muted, applied primary,
  interviewing warning, offered tertiary, accepted success, rejected error, withdrawn muted. The legend
  carries the words and counts.
- **The "Applied · last 7 days" tile** gains a `Sparkline` of the last 28 days from the activity series the
  page already fetches. `label` = "Applied per day, last 28 days".
- **"Most common gaps" and "Quick wins" rows** gain an inline `ScoreBar` (max = the list's top count,
  `valueText` = "{n} jobs").
- **Agent pipeline bars:** `bg-primary/10` on a muted track becomes `bg-primary` on `bg-surface-container`.
  This closes SYSTEM.md §11 item 28's first clause; delete that clause in Task 30.

**Pins:**

```python
def test_analytics_draws_status_mix_and_trend():
    src = _read("components/analytics/analytics-overview.tsx")
    assert "SegmentedBar" in src and "Sparkline" in src
    assert "bg-primary/10" not in _read("components/analytics/agent-pipeline-card.tsx")
```

Run `test_frontend_analytics.py` and `test_frontend_jobs_honest_analytics.py`.
**Commit:** `feat(web): analytics shows the status mix, a trend line and inline bars`

### Task 27: Automations, Settings, Q&A and version history

**Files and changes:**
- **`components/automations/automation-card.tsx`:**
  - Kind badge: `CONCEPT_ICONS.scheduled` "Scheduled", `Hand` "Attended", `Wrench` "Custom". `Wrench` keeps
    one meaning here, since Task 23 freed it.
  - "Needs" badges: `AtSign` Email, `Globe` Web; the Maestro badge stays text. `Mail` means a cover letter in
    Q&A, so Email gets its own glyph.
  - "Not run yet" gets `CONCEPT_ICONS.notRun`. "Last ran …" gets the run-outcome glyph from Task 21's map:
    share it from `lib/agent-runs.ts`, don't copy.
  - **The outcome is not available to the card today.** `latestByAutomation` (`lib/agent-runs.ts:27-31`)
    returns `Map<automation, finished_at>`. Change it to `{ finished_at, outcome }` and give the card an
    `outcome` prop. Keep the `lastRanLine(lastRun, formatTimeAgo)` call verbatim, passing `finished_at`,
    since `test_frontend_automations.py:80` pins it. Update `lib/agent-runs.test.ts` for the new map shape.
  - The `card.never` sentence starts with `Ban` (size 3.5, muted) and drops to `text-body-small`.
- **`app/automations/page.tsx`:** "Your agent needs to be connected to Maestro first." becomes a callout
  (`bg-secondary-container text-on-secondary-container rounded-corner-md`, `Bot` icon, the How-to link as
  its action) **while no automation card has ever run** (no Last ran on any card). Once one has, it is the
  plain line or nothing. The page already has that data.
- **`components/settings/connected-agents-card.tsx`:** keep the `<h3 id={canId} …>They can</h3>` markup that
  `test_frontend_agent_words.py:197-199` pins. "They can" items gain `CircleCheck` `text-success`;
  "They can't" items gain `Ban` `text-muted-foreground`. Headings stay.
- **`components/qa-tab.tsx`:**
  - Each history card gains a kind glyph before its title: `MessageSquareText` for a question, `Mail` for a
    cover letter.
  - A cover letter with a `pdf_path` shows a chip `CircleCheck` "PDF ready".
- **`components/resume-versions/version-history-sheet.tsx`:**
  - Source badges gain icons: `UserRound` Your edit, `Sparkles` Suggested edit, `MessageSquare` Assistant,
    `FileInput` Imported, `CONCEPT_ICONS.restore` Restored (the same glyph as the Restore button),
    `FilePlus2` Created, `CONCEPT_ICONS.tailor` Tailored.
    Restored was made neutral in Task 4.
  - "Current" becomes a `bg-primary` dot + "Current".

**Pins:**

```python
def test_small_surfaces_gain_their_glyphs():
    card = _read("components/automations/automation-card.tsx")
    assert "CONCEPT_ICONS.scheduled" in card and "CONCEPT_ICONS.notRun" in card
    assert "Ban" in _read("components/settings/connected-agents-card.tsx")
    assert "MessageSquareText" in _read("components/qa-tab.tsx")
```

Run `test_frontend_automations.py`, `test_frontend_settings_cards.py` and `test_frontend_qa_tab.py`.
**Commit:** `feat(web): glyphs for automations, connected agents, Q&A and versions`

**Wave 5 close:** the standard close, plus the full backend suite (Task 25 touched the API) and the slop
check on `backend` and `frontend`.

---

# Wave 6: The Companion, docs and close

### Task 28: The Companion's icons

**Files:**
- Create: `extension/panel/icons.js` (inline Lucide SVG builders; plain script on the panel's
  namespace, like the other panel scripts)
- Modify: `extension/panel/panel.html` (add `<script src="icons.js"></script>` before the stage scripts;
  `decisions.js` stays first and `panel.js` last, pinned at `test_extension_panel.py:689-758`), and the boot
  roster that throws on a missing script (read how `panel.js` checks its roster). The new file must attach
  to `window.careerStudioCompanion`, like its siblings (`test_extension_panel.py:754`).
- **Modify: `backend/tests/extension_panel_harness.py`** (this is the blocker the review found). The fake
  `document` (:426-544) has only `getElementById`, `createElement` and `activeElement`, and no
  `createElementNS` or `innerHTML`, so an svg builder throws in every panel test.
  - Add `createElementNS(ns, tag)`, returning a `FakeNode` that records `tagName`, attributes
    (`setAttribute`/`getAttribute`) and children (`appendChild`), like the HTML nodes.
  - Make `_text()` return `""` for an svg node, as a browser's `textContent` would.
  - Build icons with `createElementNS` + `setAttribute`, never `innerHTML`; that keeps the panel CSP-clean
    and testable.
- Modify:
  - `extension/panel/stages/fill.js` (:98–100, `DONE`/`OPEN`/`SKIPPED`)
  - `extension/panel/stages/track.js` (:99, 📎)
  - `extension/panel/actions/resume.js` (:96, ⚠ in a live region)
  - `extension/panel/panel.js` (✓ rail tick, ▾/▸ carets, ↗ link labels, and the → between the ATS rings at
    ~:1761)
  - `extension/panel/stages/resume.js` (↗ only)
- Test: `backend/tests/test_extension_panel_icons.py` (create), plus the existing panel tests

**`icons.js`.** It holds the path data for check, circle-check, circle-minus, circle-alert, triangle-alert,
chevron-down, chevron-right, external-link, arrow-right, paperclip, lock and minus. Copy each from
`frontend/node_modules/lucide-react/dist/esm/icons/<name>.js` (ISC licence; keep a one-line notice in the
file header). It exposes:

```js
// ns.icon("circle-check", { size: 14, label: null }) -> an <svg> element, aria-hidden unless a label is given.
```

**Replacements:**
- **Fill rows:** `DONE` → `circle-check` + visible word "Done"; `OPEN` → an attention dot + "Needs you";
  `SKIPPED` → `circle-minus` + "Skipped". The `.st` span now holds icon + word, and its `aria-label` goes,
  since the word is visible.
- **Track:** 📎 → `paperclip`.
- **The resume live region:** ⚠ is dropped from the text. The visible note gains a `triangle-alert` svg; the
  live text is words only.
- **Rail:** ✓ → `check`. ▾/▸ → `chevron-down`/`chevron-right`. ↗ → `external-link` (aria-hidden), with "(opens
  in a new tab)" in the link's accessible name, like the web app's `NewTabLink`. → → `arrow-right`.

**Test:**

```python
"""The Companion draws Lucide icons, never emoji or text glyphs (visual-language plan, Task 28)."""

from pathlib import Path

_PANEL = Path(__file__).resolve().parents[2] / "extension/panel"
_GLYPHS = "⚠▲▼✓✅🟡⏸📎▾▸↗→"


def test_no_emoji_or_text_glyph_in_panel_code():
    hits = []
    for path in list(_PANEL.rglob("*.js")) + [_PANEL / "panel.html"]:
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("//", 1)[0]
            hits += [f"{path.name}:{lineno} {ch!r}" for ch in _GLYPHS if ch in code]
    assert hits == [], "\n".join(hits)


def test_icons_module_is_on_the_roster():
    assert "icons.js" in (_PANEL / "panel.html").read_text()
```

Run `test_extension_panel*.py`; the harness reads `panel.html`'s roster (:82), so the new script loads in
tests too.

**Pins that read the old glyphs.** There are many, well beyond fill and track. `_text()` reads
`textContent`, so an svg reads as "". Rewrite each to assert the icon (by its `data-icon` attribute, which
`ns.icon` sets) plus the visible word:

| File | Lines | What it pins |
|---|---|---|
| `test_extension_panel.py` | :873, :1675, :2413, :2459-2467, :3090 | ✓ tick, ↗ suffix |
| `test_extension_panel_resume.py` | :204 to :1000 | "Tailor in Maestro CS ↗" ×9, `("done","✓")` |
| `test_extension_panel_track.py` | :393, :423, :440, :738 | |
| `test_extension_panel_score.py` | :305 | |
| `test_extension_panel_fill.py` | :1131-1134 | the 🟡/⏸ marks and their lowercase `aria-label`s |

Count them before starting. If the rewrite touches more than about 40 assertions, split the task into
28a (icons.js + harness + fill/track) and 28b (rail and links), and log it.

**Commit:** `feat(extension): Lucide icons in the side panel; no emoji or text glyphs`

### Task 29: The Companion's status vocabulary, states and report headings

**Files:**
- Create: `extension/shared/status-roles.js`, the application status table:
  `{ draft: { label: "Draft", role: "muted" }, applied: { label: "Applied", role: "primary" }, interviewing: …warning, offered: { label: "Offer", role: "tertiary" }, accepted: { label: "Offer accepted", role: "success" }, rejected: …error, withdrawn: …muted }`
- Modify: `extension/panel/panel.html`, and the roster if `shared/` scripts are listed there
- Modify: `extension/panel/panel.css`:
  - Add M3-named tokens for the missing roles: `--cs-error-container`/`--cs-on-error-container`,
    `--cs-warning-container`/`--cs-on-warning-container`, `--cs-attention-container`/`--cs-on-attention-container`,
    `--cs-tertiary-container`/`--cs-on-tertiary-container`, `--cs-success-container`/`--cs-on-success-container`,
    `--cs-primary-container`/`--cs-on-primary-container` and `--cs-surface-container`. Copy the light and dark
    values from `frontend/app/globals.css`.
  - Add `.chip.role-<name>` classes.
  - Add hover, pressed and focus-visible states on `.cta`, `.stop` and the secondary buttons:
    `transition: background-color 150ms, transform 140ms`, `:active { transform: scale(.97) }`, a hover mix,
    a solid focus ring. Keep the existing reduced-motion rule.
- Modify: `extension/panel/panel.js`:
  - Replace `STATUS_LABELS` (~:1398) with the shared table.
  - `matchChip` (~:1704–1713): `chip role-<role>` from the table.
  - The Track `statusSegment` (~:2545–2570): the selected segment uses the secondary container + a leading
    `check` icon, the selected-in-set rule, instead of `draft-on` amber and `on` green.
  - "Not saved yet" is a neutral outline chip, not `warn`.
  - The rail: a locked row shows `lock` + "Not yet"; a not-needed row shows `minus` + "Not needed". These
    words are visible; they are in `aria-label` only today (`STATE_LABELS` ~:331–339).
- Modify: `extension/panel/stages/fill.js`:
  - Report group headings: icon + short heading + count chip. Closest matches → `search` (add it to
    `icons.js`), "Answered for you" → a sparkles icon (add it) with the word "AI answered", "Filled but not
    confirmed" → `circle-help`.
  - Delete the repeated ": check each one" and add one shared line, "Check each one before you submit.",
    under the headings.
  - Drop the per-row "· closest match:" prefix under the Closest matches heading.
- Test: `backend/tests/test_extension_status_roles.py` (create), plus panel tests

**Test** (parity with the web app's one status vocabulary):

```python
"""The Companion names and colours an application status exactly as StatusChip does (Task 29)."""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_CHIP = (_ROOT / "frontend/components/status-chip.tsx").read_text()
_ROLES = (_ROOT / "extension/shared/status-roles.js").read_text()

_ROLE_OF_CHIP = {
    "bg-muted": "muted", "bg-primary-container": "primary", "bg-warning-container": "warning",
    "bg-tertiary-container": "tertiary", "bg-success-container": "success", "bg-error-container": "error",
}


def _web_table() -> dict[str, tuple[str, str]]:
    block = _CHIP.split("const STATUS_STYLES", 1)[1].split("};", 1)[0]
    out = {}
    for key, label, chip in re.findall(r'(\w+): \{\s*label: "([^"]+)",\s*chip: "([^"]+)"', block):
        role = next(r for cls, r in _ROLE_OF_CHIP.items() if chip.startswith(cls))
        out[key] = (label, role)
    return out


def _panel_table() -> dict[str, tuple[str, str]]:
    return {k: (label, role) for k, label, role in
            re.findall(r'(\w+): \{ label: "([^"]+)", role: "(\w+)" \}', _ROLES)}


def test_panel_status_table_matches_status_chip():
    assert _panel_table() == _web_table()


def test_panel_no_longer_colours_every_status_good():
    css = (_ROOT / "extension/panel/panel.css").read_text()
    assert ".chip.app {" not in css and ".draft-on" not in css
```

**Pins to rewrite in this task:**
- `STATE_LABELS` at `test_extension_panel.py:1318-1319` and `:2460` (the rail words are now visible text).
- The report headings at `test_extension_panel_fill.py:3811-3850`.

Run all `test_extension_panel*.py`, then the slop check on `extension`. Load the unpacked extension in Chrome
and check the panel on a job page: the statuses' colours, Track, the rail and a fill report.
**Commit:** `feat(extension): one status vocabulary with the web app; button states; quieter report headings`

### Task 30: Docs, ledgers and the close

**Files:**
- **`docs/design-system/README.md`:**
  - Iconography: link `lib/concept-icons.ts` as the register, and say "one concept, one glyph".
  - Selection and state: add Button `pending` and the field warning state.
  - Motion: `animate-confirm`, the row exit, the count-up, the 400ms budget, no bounce.
  - Components list: the eight primitives.
  - "Not synced": the new component pages have no preview yet.
- **`docs/design-system/components/<Name>/README.md`:** written in Task 14; re-read them against the final
  API.
- **`docs/frontend-conventions.md`:**
  - A "Visual encodings" section: which primitive for which data, and the accessible-text contract.
  - "States and feedback": one feedback rule per action class (navigate / in place / background), Undo only
    where the server can reverse, never empty before loaded.
  - Update the copy rules if a pin moved a canonical string.
- **`SYSTEM.md`:**
  - §5 step 2: the tracker reads `ats_score` / `best_ats_score` (read-only).
  - §11 item 28: delete its first clause (the pipeline bar is solid now; its text also still names an old
    `bg-muted/50` track, now `bg-surface-container-low`) and keep the FAB-ring clause.
  - §12: add a gotcha only if one bit during execution.
  - Run `python3 scripts/check_system_md.py`.
- **`docs/entities/application.md` and `job.md`:** the list fields, if Task 25 did not already add them.
- **`extension/INTERNALS.md`:** `icons.js` and `shared/status-roles.js` in the script family.
- **The design-system artifact.** The main session republishes the Maestro design system artifact
  (https://claude.ai/artifact/VxnjspbkP71d8Z183QqrB7) with the new components, as in memory
  "design-system-rollout". Not a subagent job.

**Final gates:**
- the full backend suite with xdist
- `npx tsc --noEmit`, `npm run lint`, `npm run build`
- the slop check on `frontend`, `backend` and `extension`, each named
- `check_system_md.py`
- a full browser pass at 1280 and 1024, light and dark, on a fresh stack with the DB snapshot: Jobs, a job's
  four tabs, the gap page, the health report and question pass, the Agent inbox, Career history, Analytics,
  Automations, Settings and the Assistant
- the Companion loaded unpacked

**Goal critique.** Opus critiques the finished branch against the **Goal Card**, not this plan. Default to
approve. Each finding names a Goal Card line and the screen that breaks it. Then the owner chooses merge, PR
or keep (superpowers:finishing-a-development-branch). Nothing is pushed before that.

**Commit:** `docs: visual language in the design system, conventions and SYSTEM.md`

---

## Not in this plan (recorded so nobody re-files them)

- Company logos (D7).
- Undo for Skip or Queue (D8: it would change the proposal state machine).
- Sweeping all palette-alpha fills or all hand-written `data-disabled` classes: ratcheted (Task 4) or left
  for a later pass.
- Job header meta-line icon chips. Low value next to the score pill; revisit after Wave 4's browser pass.
- Health report tab icons. The tab words are abstract and the research advises against icon-only tabs; the
  words stay as they are.
