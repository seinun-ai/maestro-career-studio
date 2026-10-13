# Resume colour, the Jobs Where column and the card clean-up Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Give every base resume its own colour (random on create, changeable, shown as a square wherever the resume is named), give Jobs rows one height with a Where column, clean up Career history cards, and bring the Companion onto the same colours.

**Architecture:** The backend stores one integer hue per base resume (`base_resumes.color_hue`) and picks a free preset hue on every create path. The frontend turns a hue into three colours with a CSS recipe: tones live in `globals.css` per theme, the hue and chroma ride on the element as `--resume-h` / `--resume-c`, and three `@theme inline` colours (`resume`, `resume-container`, `on-resume-container`) compute from them, so every hue clears contrast by construction. The Companion copies the recipe and the presets, pinned equal by tests.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (SQLite), pytest (xdist), Next.js 16 + React 19 + Tailwind v4, the Companion's plain JS panel tested through pytest + Node.

**Branch:** `claude/ui-ux-audit-design-system-fff8a1` (from `main` at `6695ee40`). Commit per task, locally. **Never push or open a PR** until the owner says so (owner rule: design-system work is batched locally).

**Approved design:** the Design canvas https://claude.ai/artifact/4GvcVd1pUw493gxwkQiRX4 (boards 2 to 6). Owner approved on 2026-10-12: per-resume colour (not per role), random on create, ten presets plus a Custom hue, Jobs option B with Where after Status, full-size thumbnails with a top band and tinted footer, the Companion changes. Not approved: flags (stay text), renaming "Ai Ml Engineer" (owner's data).

**Read first:** `SYSTEM.md` (§6, §8, §9, §12), `docs/frontend-conventions.md` "Visual encodings" (~line 1630) and chart rules (~1548), `docs/design-system/README.md`, `docs/entities/others.md` (BaseResume, ~line 93).

**How to run things** (from the worktree root):
- Backend venv (once): `~/.langflow/uv/uv venv -p 3.12 backend/.venv && cd backend && VIRTUAL_ENV=.venv ~/.langflow/uv/uv pip install -r requirements.lock && VIRTUAL_ENV=.venv ~/.langflow/uv/uv pip install -e ".[dev,mcp]"`. `backend/.venv` is git-ignored; check with `git check-ignore backend/.venv`.
- One backend test file: `cd backend && .venv/bin/python -m pytest tests/<file>.py -q`
- Whole backend suite (always with xdist): `cd backend && .venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`
- Frontend (once: `cd frontend && npm ci`): `npx tsc --noEmit`, `npm run lint`, `npm run build`. There is no frontend unit runner; backend tests pin frontend and extension source by reading files.

**Words on screen:** "Color" (`test_frontend_vocabulary.py` bans the British spelling on screen), sentence case, no placeholder in a blank field, hints only when they add something. One word per thing: "base resume", "Where", "Laptop", "Bot", "Moving".

---

## The colour recipe (shared by every task)

Ten presets. Hue in degrees, chroma for the swatch tone. A custom hue uses chroma `0.10`.

| Name | Hue | Chroma |
|---|---|---|
| Rose | 5 | 0.11 |
| Copper | 40 | 0.11 |
| Ochre | 80 | 0.11 |
| Olive | 125 | 0.11 |
| Pine | 160 | 0.09 |
| Teal | 195 | 0.09 |
| Sky | 230 | 0.09 |
| Slate | 265 | 0.06 |
| Iris | 300 | 0.11 |
| Plum | 335 | 0.11 |

Tones (OKLCH lightness, and chroma as a multiple of the hue's chroma):

| Colour | Light L | Light C× | Dark L | Dark C× | Use |
|---|---|---|---|---|---|
| `resume` | 0.52 | 1.00 | 0.76 | 0.90 | the square, the card's top band |
| `resume-container` | 0.93 | 0.36 | 0.33 | 0.45 | the tinted footer behind a name |
| `on-resume-container` | 0.38 | 0.82 | 0.90 | 0.40 | text on the container |

A resume with no hue (`null`) draws neutral grey: chroma 0.

---

# Step 1: design system and tokens

### Task 1: The preset table and the picker service (backend)

**Files:**
- Create: `backend/app/services/resume_colors.py`
- Test: `backend/tests/test_resume_colors.py`

**Step 1: Write the failing test**

```python
"""Base resume colours: the preset table and how a new resume gets one."""

import random

from app.services.resume_colors import PRESET_HUES, pick_hue


def test_presets_are_ten_distinct_hues_in_range():
    assert len(PRESET_HUES) == 10
    assert len(set(PRESET_HUES)) == 10
    assert all(0 <= h < 360 for h in PRESET_HUES)


def test_pick_avoids_hues_in_use():
    used = PRESET_HUES[:9]
    assert pick_hue(used, rng=random.Random(1)) == PRESET_HUES[9]


def test_pick_is_random_among_free_presets():
    seen = {pick_hue([], rng=random.Random(seed)) for seed in range(50)}
    assert len(seen) > 3
    assert seen <= set(PRESET_HUES)


def test_when_all_are_taken_pick_the_least_used():
    used = list(PRESET_HUES) + list(PRESET_HUES[1:])  # every preset twice except the first
    assert pick_hue(used, rng=random.Random(3)) == PRESET_HUES[0]


def test_custom_hues_in_use_do_not_block_presets():
    assert pick_hue([7, 41, 200], rng=random.Random(2)) in PRESET_HUES
```

**Step 2:** Run `cd backend && .venv/bin/python -m pytest tests/test_resume_colors.py -q`. Expected: FAIL (module missing).

**Step 3: Implement**

```python
"""Base resume colours.

A base resume's colour is identity, never state: one hue per resume, shown as a
square beside its name. The app derives every tone from the hue (see
frontend/lib/resume-color.ts and globals.css), so only the hue is stored.

PRESET_HUES is mirrored in frontend/lib/resume-color.ts and
extension/shared/resume-color.js; test_resume_color_parity.py pins all three.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable

PRESET_HUES: tuple[int, ...] = (5, 40, 80, 125, 160, 195, 230, 265, 300, 335)


def valid_hue(value: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 360


def pick_hue(used: Iterable[int | None], *, rng: random.Random | None = None) -> int:
    """A random preset no resume in `used` has; else one of the least-used presets."""
    rng = rng or random.Random()
    counts = Counter(h for h in used if h in PRESET_HUES)
    fewest = min(counts.get(h, 0) for h in PRESET_HUES)
    return rng.choice([h for h in PRESET_HUES if counts.get(h, 0) == fewest])
```

**Step 4:** Run the test again. Expected: PASS.

**Step 5:** `git add backend/app/services/resume_colors.py backend/tests/test_resume_colors.py && git commit -m "feat(base-resumes): preset hues and the free-colour picker"`

---

### Task 2: Store the hue, pick it on every create path, change it through identity

**Files:**
- Modify: `backend/app/models/base_resume.py` (add a column beside `focus`, ~line 41)
- Create: `backend/migrations/versions/<id>_base_resume_color_hue.py`. Generate `<id>` with `python -c "import uuid; print(uuid.uuid4().hex[:12])"` (§12: hand-written ids collide). Its `down_revision` is the current head `cf0804d00ae2`; confirm with `cd backend && .venv/bin/alembic heads`.
- Modify: `backend/app/schemas/base_resume.py`, adding `color_hue` to `_BaseResumeIdentityRead` (:9), `BaseResumeCreate` (:61) and `BaseResumeIdentity` (:140)
- Modify: `backend/app/routers/base_resumes.py`, at `_detail` (:199), `create_base_resume` (ctor :287), `duplicate_base_resume` (ctor :804) and `update_base_resume_identity` (:614)
- Modify: `backend/app/services/kb_import.py` `_mint_base` (ctor :165)
- Modify: `backend/app/services/seeding.py` `seed_base_resumes` (ctor :70)
- Modify: `backend/mcp_server/server.py` `set_base_resume_identity` (:880) and `backend/mcp_server/client.py` (:736)
- Test: `backend/tests/test_base_resume_color.py` (copy the fixture pattern from `backend/tests/test_base_resume_anchors.py`: `client` fixture, `_add`, `teardown_function`)

**Step 1: Write the failing tests**

Cover each of these, one test each:
- `POST /api/base-resumes` with no `color_hue` → the response and the list carry a hue from `PRESET_HUES` that no other active resume has (seed two resumes with known hues first).
- `POST` with `color_hue: 200` keeps 200. With `color_hue: 360` or `-1` → 422 and nothing saved.
- `POST /{slug}/duplicate` → the copy gets a different hue from the source.
- `PATCH /{slug}/identity` with `{"color_hue": 230}` → 230 stored, no ResumeVersion written, no render (assert like the anchors tests do). `{"color_hue": 400}` → 422, and the other fields in the same request are not saved.
- Archived and deleted resumes do not count as "in use" (archive one holding the only free preset; a new resume may take it).
- The KB import path `kb_import._mint_base` gives the minted base a preset hue (follow an existing test that drives `POST /api/kb/import`, or call `_mint_base` directly with `db_session`).
- MCP: `backend/mcp_server/tests/`: `set_base_resume_identity(slug, color_hue=230)` sends `color_hue` in the PATCH body (copy a respx test of the same tool).

**Step 2:** Run the new file. Expected: FAIL.

**Step 3: Implement**
- Model: `color_hue: Mapped[int | None] = mapped_column(Integer, nullable=True)`, with a comment: identity colour hue, picked on create (`services/resume_colors.py`), never state.
- Migration: add the column with `batch_alter_table` like `559244b575bc_base_resume_anchors.py`, then backfill existing live rows so today's resumes get distinct colours. Hard-code the hues in the migration (a migration never imports app code):

```python
_PRESETS = (5, 40, 80, 125, 160, 195, 230, 265, 300, 335)

def upgrade() -> None:
    with op.batch_alter_table("base_resumes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("color_hue", sa.Integer(), nullable=True))
    conn = op.get_bind()
    slugs = [r[0] for r in conn.execute(sa.text(
        "SELECT slug FROM base_resumes WHERE deleted_at IS NULL ORDER BY created_at, slug"))]
    for i, slug in enumerate(slugs):
        conn.execute(sa.text("UPDATE base_resumes SET color_hue = :h WHERE slug = :s"),
                     {"h": _PRESETS[i % len(_PRESETS)], "s": slug})

def downgrade() -> None:
    with op.batch_alter_table("base_resumes", schema=None) as batch_op:
        batch_op.drop_column("color_hue")
```

- A helper in `resume_colors.py`, taking a session: `hues_in_use(db) -> list[int|None]` = `color_hue` of rows matching `base_resume_data.selectable_filter()` (:29, not deleted and not archived). Do not use `active_filter()`, which excludes deleted rows only.
- Schemas: read side `color_hue: int | None = None`. `BaseResumeCreate`, `BaseResumeFromKB` (:86), `BaseResumeDuplicate` (:81) and `BaseResumeIdentity` gain `color_hue: int | None = None`, with a shared `field_validator` that raises on a value outside `0..359` (Pydantic → 422).
- `create_base_resume`: `color_hue=payload.color_hue if payload.color_hue is not None else pick_hue(hues_in_use(db))`.
- `create_from_kb` builds its own `BaseResumeCreate` (:481-489): pass `color_hue` through. `/import` takes `Form()` fields (:536-539) and builds its own `BaseResumeCreate` (:566-574): add `color_hue: Annotated[int | None, Form()] = None` and pass it through. Add one test each, with a hue and without one.
- `duplicate_base_resume`: `payload.color_hue` if given, else `pick_hue(...)`. `_mint_base` and `seed_base_resumes` always `pick_hue(...)`. Seeding inserts several rows in one go, so add each picked hue to the in-use list before picking the next.
- Identity PATCH: treat `color_hue` like an anchor. Validate before any write (one 422 saves nothing), then `setattr`. `_detail` gains `color_hue=row.color_hue`.
- MCP `set_base_resume_identity`: add `color_hue: int | None = None`, pass it through, and add one docstring sentence: "`color_hue` (0-359) sets the colour the app shows beside the resume's name; it never changes the PDF."

**Step 4:** Run the new test file, then `tests/test_migration_model_parity.py`, `tests/test_base_resume_anchors.py`, `tests/test_base_resumes_router.py` and `mcp_server/tests/`. Expected: all PASS.

**Step 5:** Update `docs/entities/others.md` (BaseResume, ~:93-101, and :15/:95 "only anchor writer"): `color_hue` is identity metadata set at create (random free preset), changed only through PATCH `/identity`, and syncs with the profile row like the anchors (no payload change: export walks the columns). Commit: `feat(base-resumes): every base resume has a colour hue`.

---

### Task 3: The recipe in globals.css and the frontend preset table

**Files:**
- Modify: `frontend/app/globals.css` (`@theme inline` block, `:root`, `.dark`)
- Create: `frontend/lib/resume-color.ts`
- Modify: `frontend/lib/types.ts` (`BaseResumeSummary` :556, adding `color_hue: number | null`)
- Test: `backend/tests/test_frontend_resume_colors.py` (contrast) and `backend/tests/test_resume_color_parity.py` (backend ↔ frontend presets; the extension joins in Task 14)

**Step 1: Write the failing tests**

`test_frontend_resume_colors.py`: import `_CSS, _MODES, _contrast, _oklab, _read, _rgb` the way `test_frontend_design_tokens.py:17` does. Parse the six tone numbers per mode from `:root` / `.dark`:

`--resume-swatch-l`, `--resume-swatch-c`, `--resume-container-l`, `--resume-container-c`, `--on-resume-container-l`, `--on-resume-container-c`

Then, for every preset (hue, chroma) **and** for hues 0..355 in steps of 5 at chroma 0.10, in both modes:
- `on-resume-container` on `resume-container` ≥ 4.5:1
- `resume` (the square) on `card` and on `background` ≥ 3:1 (a graphic beside its name, WCAG 1.4.11)
- every derived colour is inside sRGB (reuse `_linear_srgb` from the design-tokens test, with a small tolerance as that test does)

Also assert that the three `@theme inline` lines exist exactly as written below, so nobody "fixes" them onto `:root`. Put that reason in the test: `_tokens` in `test_frontend_color_roles.py:31-55` parses `:root`/`.dark` with `oklch\(([^)]*)\)` and asserts on what it cannot read, so these lines on `:root` would also break that parser. `_linear_srgb` lives at `test_frontend_design_tokens.py:89`.

`test_resume_color_parity.py`: parse `PRESET_HUES` from `backend/app/services/resume_colors.py` (import it) and the `RESUME_PRESETS` array from `frontend/lib/resume-color.ts` (regex `hue:\s*(\d+)` and `chroma:\s*([\d.]+)`). The hues must be equal and in the same order, and the chromas must equal the table above.

**Step 2:** Run both. Expected: FAIL.

**Step 3: Implement**

`globals.css`, inside `@theme inline`:

```css
  /* Base resume colour: identity, never state. The hue and chroma ride on the
     element (`--resume-h`, `--resume-c`, set by resumeColorStyle in
     lib/resume-color.ts); the tones below are per theme. These MUST stay
     `inline`: a custom property declared on :root resolves its var()s there,
     where no resume's hue exists, and children would inherit grey. No hue set
     means chroma 0: neutral. Pinned by test_frontend_resume_colors.py. */
  --color-resume: oklch(var(--resume-swatch-l) calc(var(--resume-c, 0) * var(--resume-swatch-c)) var(--resume-h, 0));
  --color-resume-container: oklch(var(--resume-container-l) calc(var(--resume-c, 0) * var(--resume-container-c)) var(--resume-h, 0));
  --color-on-resume-container: oklch(var(--on-resume-container-l) calc(var(--resume-c, 0) * var(--on-resume-container-c)) var(--resume-h, 0));
```

`:root`: `--resume-swatch-l: 0.52; --resume-swatch-c: 1; --resume-container-l: 0.93; --resume-container-c: 0.36; --on-resume-container-l: 0.38; --on-resume-container-c: 0.82;`
`.dark`: `0.76 / 0.9`, `0.33 / 0.45`, `0.90 / 0.40`.

If `test_frontend_design_tokens.py` or `test_frontend_color_roles.py` enumerates `--color-*` lines and expects `var(--x)` only, extend that test's allow-list with these three names and say why in a comment. Do not weaken any other check.

`lib/resume-color.ts`:

```ts
import type { CSSProperties } from "react";

/** A base resume's colour is identity, never state: a square beside its name.
 *  Only the hue is stored; globals.css derives the tones. Mirrors
 *  backend/app/services/resume_colors.py (pinned by test_resume_color_parity.py). */
export const RESUME_PRESETS = [
  { name: "Rose", hue: 5, chroma: 0.11 },
  { name: "Copper", hue: 40, chroma: 0.11 },
  { name: "Ochre", hue: 80, chroma: 0.11 },
  { name: "Olive", hue: 125, chroma: 0.11 },
  { name: "Pine", hue: 160, chroma: 0.09 },
  { name: "Teal", hue: 195, chroma: 0.09 },
  { name: "Sky", hue: 230, chroma: 0.09 },
  { name: "Slate", hue: 265, chroma: 0.06 },
  { name: "Iris", hue: 300, chroma: 0.11 },
  { name: "Plum", hue: 335, chroma: 0.11 },
] as const;

export const CUSTOM_CHROMA = 0.1;

export function resumeChroma(hue: number): number {
  return RESUME_PRESETS.find((p) => p.hue === hue)?.chroma ?? CUSTOM_CHROMA;
}

/** The CSS variables that colour `bg-resume`, `bg-resume-container` and
 *  `text-on-resume-container` on this element and its children. */
export function resumeColorStyle(hue: number | null | undefined): CSSProperties {
  if (hue === null || hue === undefined) return {};
  return { "--resume-h": hue, "--resume-c": resumeChroma(hue) } as CSSProperties;
}

/** A random preset no hue in `used` has; else one of the least-used. Same rule as the server. */
export function pickFreeHue(used: (number | null)[], random = Math.random): number {
  const counts = new Map<number, number>();
  for (const h of used) if (h !== null && RESUME_PRESETS.some((p) => p.hue === h)) counts.set(h, (counts.get(h) ?? 0) + 1);
  const fewest = Math.min(...RESUME_PRESETS.map((p) => counts.get(p.hue) ?? 0));
  const free = RESUME_PRESETS.filter((p) => (counts.get(p.hue) ?? 0) === fewest);
  return free[Math.floor(random() * free.length)].hue;
}

export function presetName(hue: number | null | undefined): string | null {
  return RESUME_PRESETS.find((p) => p.hue === hue)?.name ?? null;
}
```

**Step 4:** Run both tests and `tests/test_frontend_design_tokens.py tests/test_frontend_color_roles.py`, then `cd frontend && npx tsc --noEmit`. Expected: PASS.

**Step 5:** Commit: `feat(design-system): the base resume colour recipe`.

---

### Task 4: ResumeSwatch, ResumeTag, ResumeColorPicker and the hook

**Files:**
- Create: `frontend/components/visual/resume-swatch.tsx` (exports `ResumeSwatch`, `ResumeTag`)
- Create: `frontend/components/base-resumes/resume-color-picker.tsx`
- Modify: `frontend/hooks/use-base-resume-label.ts`, adding `useBaseResumeColor(slug)`
- Test: `backend/tests/test_frontend_resume_swatch.py` (source pins, in the style of `test_frontend_visual_primitives.py`)

**Behaviour:**
- `ResumeSwatch({ hue, className })`: a `span`, `size-2.5 shrink-0 rounded-corner-2xs bg-resume`, with `style={resumeColorStyle(hue)}` and `aria-hidden="true"`. Its name always sits beside it. Export it from `components/visual/index.ts`.
- **The new corner `corner-2xs` (2px) needs all four edits** (two tests pin the scale):
  1. `frontend/app/globals.css` `@theme inline`: add `--radius-corner-2xs: 0.125rem;` after `--radius-corner-xs` (~:98).
  2. `frontend/lib/utils.ts:30`: add `"corner-2xs"` to the tailwind-merge `radius` list (`test_scale_names_are_registered_with_tailwind_merge`, :168-173).
  3. `backend/tests/test_frontend_design_tokens.py:458`: add `"2xs"` to the tuple in `test_every_corner_name_is_on_the_scale`.
  4. `docs/design-system/README.md` Shape (:77): "`radius-corner-2xs` (2px) the resume square".

  Never use a stock `rounded-*`, an arbitrary `rounded-[2px]` (`_RADIUS_BY_HAND` bans it), or `rounded-full` (round means status).
- `ResumeTag({ hue, children })`: `inline-flex items-center gap-1.5` with the swatch, then the name.
- `useBaseResumeColor(slug)`: the hue from the archived-inclusive list `useBaseResumes(true)`, `null` while loading or unknown.
- `ResumeColorPicker({ value, onChange, used, label = "Colour" })`:
  - A `role="radiogroup"` of ten 32px swatch buttons. Each is a `button` with `role="radio"`, `aria-checked`, `aria-label` set to the preset name plus ", used by <name>" when taken, `rounded-corner-sm` (a control), and `bg-resume` with its `resumeColorStyle`.
  - A checked swatch shows a 16px `Check` in `text-primary-foreground` plus the solid 2px `ring` outline with an offset (the DS's selected rule).
  - Taken presets are not disabled. Mark them with a small `surface` dot in the corner, not opacity (50% opacity means disabled in this DS).
  - A "Custom" outline button reveals a hue slider (`input type="range"` 0-359, labelled "Hue", with a gradient track drawn from the recipe), sitting under the swatches.
  - Hint under the group, only when the value was picked at random: "Picked at random from colours no other resume uses."
  - Arrow keys move between swatches (radiogroup pattern).
- Source-pin tests: no `rounded-full` and no `opacity-` in `resume-swatch.tsx`; the picker has `role="radiogroup"` and `aria-checked`; `ResumeSwatch` sets `aria-hidden`.

**Verify:** the pins, `npx tsc --noEmit`, `npm run lint`. Commit: `feat(design-system): ResumeSwatch, ResumeTag and the colour picker`.

---

### Task 5: Write the rule down (repo docs and SYSTEM.md)

**Files:** `docs/design-system/README.md` (Color :25, Shape :77, Components :127), `docs/design-system/components/ResumeSwatch/README.md`, `docs/design-system/components/ResumeColorPicker/README.md` (format: a one-line definition, "**You provide:**", rules, "Source:"), `docs/design-system/tokens.json` (three colour entries; their light/dark `value` is the recipe text, with `usage` set), `docs/frontend-conventions.md` "Visual encodings" (~1656), `SYSTEM.md` §8 index line if it lists primitives.

The Color section gains:
- **Base resume colour is identity, never state.** Each base resume has one hue, picked at random from the free presets when it is made and changeable in its Target. Draw it as a square (`ResumeSwatch`) beside the resume's name, never alone and never as a round pill or dot (round is status). The tones come from the hue (`resume`, `resume-container`, `on-resume-container`), so any hue holds contrast.
- **Only a card that stands for one base resume** (its gallery card, its score card) carries the colour as a 6px top band and a `resume-container` footer. Rows, pages and the sidebar never take it. PDFs never carry it.
- **Charts split by base resume** colour each series by its resume. Every other chart keeps `chart-1` to `chart-6`.

Commit: `docs(design-system): the base resume colour rule`.

**Step 1 ends here.** The main session then updates the owner's Design System artifact (https://claude.ai/code/artifact/ea89fa46-aeeb-433e-97b3-bda98567d71e): it reads `project/README.md` and `project/tokens.json` first, then publishes the same rule text and the three tokens. It must not run before Tasks 1-5 are reviewed.

---

# Step 2: the app screens

### Task 6: Colour in the New base resume dialog and in Target

**Files:** `frontend/components/base-resumes/new-base-resume-dialog.tsx` (shared block :490, after :544; payloads :352, :371 FormData, :389, :420), `frontend/components/role-category-picker.tsx` `TargetDialog` (:287-375; save via `useAnchorSave`), and the backend for the FormData import path if `color_hue` is not read there (`/import` :533).

- The dialog opens with `pickFreeHue(hues of useBaseResumes(false))`, held in state with `pickedAtRandom = true` until the user chooses. It always sends `color_hue` on every tab's payload: the JSON bodies at :352/:389/:420 and the FormData at :371 (`fd.append("color_hue", String(hue))`). Task 2 made all four endpoints accept it.
- `TargetDialog` gains a Colour row (the picker, `pickedAtRandom` false). A change saves right away through `PATCH /identity` like the other anchors, invalidating the base resume queries (both list keys and the detail key).
- Test: extend `backend/tests/test_frontend_base_resume_anchors.py` (or a sibling) to pin that both dialogs mount `ResumeColorPicker` and that the create payloads include `color_hue`.

Commit: `feat(base-resumes): pick and change a resume's colour`.

### Task 7: The base resume gallery

**Files:** `frontend/components/base-resumes/base-resume-gallery.tsx`, `frontend/components/base-resumes/anchor-pills.tsx`, `frontend/app/base-resumes/page.tsx` (:180-310), `frontend/components/gallery/gallery-card.tsx` (only if a slot is needed).

- **The card:** a 6px `bg-resume` band above the thumbnail (outside it). The thumbnail keeps its size and full bleed. The header area gets `bg-resume-container text-on-resume-container`. The title gets the square, and secondary text in the footer uses `text-on-resume-container`, not `text-muted-foreground`. Set `resumeColorStyle(resume.color_hue)` on the card root.
- **Chips:** the health chip and the country pills keep their own fills. A secondary Badge on the tint must keep 4.5:1, so check it in the browser and switch the pill to a `card` fill if needed.
- **`AnchorPills`:** gains `showRole?: boolean` (default `true`). The gallery passes `false`. The role is now the group heading.
- **Grouping by role:** a plain heading (`text-title-small`, the role label, a `label-small` count) per role, in the order roles first appear in the page's current list order. "Role not set" goes last and keeps its existing "Role not set" badge on each card. Archived cards (Show archived) stay in their group, at the existing `opacity-60`.
- **Pins:** `backend/tests/test_frontend_base_resume_anchors.py:179` asserts the literal `"<AnchorPills resume={resume} />"` in the gallery. Change it to the new literal with `showRole={false}` and keep its intent. Lines :170 (the role line inside `anchor-pills.tsx`) and :183-184 (the score card keeps its role pill) must stay green.

Commit: `feat(base-resumes): colour band, tinted footer, grouped by role`.

### Task 8: The square wherever a base resume is named

Use `ResumeTag`/`ResumeSwatch`, with the hue from the summary where the site has one and from `useBaseResumeColor(slug)` where it has only a slug. Sites:

| Where | File:line |
|---|---|
| Jobs Resume cell (name in `text-foreground`, not muted) | `app/applications/page.tsx:815-817` |
| Score and tailor cards: square beside the title, plus a 6px top band (the card stands for one resume) | `components/ats-score-panel.tsx:207-248` |
| Gap analysis header | `app/jobs/[id]/tailor/[sessionId]/page.tsx:768` |
| Resume studio title | `components/resume-editor/editor-body.tsx:367` / `editable-title.tsx:112` |
| Agent inbox rows | `components/proposals/proposals-section.tsx:931-935` |
| Chat cards | `components/chat/proposal-card.tsx:66`, `edit-proposal-card.tsx:108`, `change-card.tsx:48,87` |
| Application panel | `components/application-panel.tsx:155-156` |
| Job header "Best" pill | `app/jobs/[id]/page.tsx:562-571` |
| Pickers | `chat/chat-page.tsx:636,714-716`, `new-base-resume-dialog.tsx:675,683`, `resume-editor/project-port-dialog.tsx:111,119`, `career/send-to-resume-dialog.tsx:306,315`, `career/resume-import-dialog.tsx:240` |
| Analytics summary cards | `components/analytics/base-summary-cards.tsx:70` |

Skip `career/points-list.tsx` and `use-resume-key-label.ts`: their keys can be application ids.

Pin test: a test that lists these files and asserts each imports `ResumeSwatch` or `ResumeTag`.

Commit: `feat(ui): a base resume's square beside its name everywhere`.

### Task 9: The chart split by base resume

`components/charts/fit-distribution-chart.tsx:30-32,85`: each series' `fill` is `resumeFill(hue)` from `lib/resume-color.ts`, a CSS string `oklch(var(--resume-swatch-l) calc(<chroma> * var(--resume-swatch-c)) <hue>)` (chroma 0 when the hue is null, so grey). The tones stay in globals.css only, and the theme follows with no JS, as chart-kit's `CHART_COLORS` already passes `var()` fills (built this way after review: a JS copy of the recipe plus a theme hook was dropped). The legend gets the squares. Update the comment at :30-32 and `docs/frontend-conventions.md` (~1548) to match the rule from Task 5. Every other chart is untouched.

Commit: `feat(analytics): fit distribution uses resume colours`.

### Task 10: Jobs, one height per row and a Where column

**Files:** `frontend/app/applications/page.tsx` (columns :734-742, Role cell :787-814, menu :899-933), `frontend/components/job-ownership.tsx`, `frontend/lib/job-ownership.ts`, `frontend/components/status-chip.tsx`.

- **Role cell:** remove `JobOwnershipMark` and `JobOwnershipNotice` (:810-811). The row is two lines.
- **The Where column:**
  - A plain `TableHead` "Where" placed after Status and before Applied. Shown only when some visible row has `jobOwnershipView(owner).mark`; with sync off the table stays as it is today.
  - Cell: the concept icon (`CONCEPT_ICONS.laptop`, or `agentInbox` for the bot) in `text-muted-foreground`, plus a word: "Laptop", "Bot", or "Moving" when the handover is `offered` or `returning`.
  - The cell's `title` is the long sentence (`ownershipReason`, or "On your laptop"), exported from `lib/job-ownership.ts`.
  - The cell reads only row data (`r.job.ownership` / `r.app.ownership`). `tests/sync/test_frontend_ownership.py::test_sync_off_pages_make_no_ownership_requests` (:52-58) forbids importing `use-job-ownership` in this page.
  - Today's widths sum to 96% (34+14+12+14+11+11, :736-741). New: Role 30, Resume 15, Match score 11, Status 13, Where 9, Applied 9, Added 9 (= 96, with `w-10` for actions). When the Where column is hidden, give its 9 to Role.
  - Export `ownershipReason` from `lib/job-ownership.ts` (private at :28).
- **Status chip lock:** `StatusChip` gains `lockedReason?: string`. When it is set, the chevron becomes `CONCEPT_ICONS.locked` with that `title`, and the chip stays disabled as today. Read `status-chip.tsx` first and keep its focus and `pending` behaviour. Pass it when `!ownership.canRequest`.
- **Row menu:** export `useOwnershipAction` from `job-ownership.tsx`. When `view.action` is set, add "Work on it here" or "Keep it here" (the laptop icon), plus a `DropdownMenuSeparator`, before Delete. It is pending-aware, and the toast is the existing `syncActionMessage`.
- **Other screens:** the job header, gap page and proposals keep `JobOwnershipMark`/`Notice` unchanged.
- **Pins:** no backend test pins the mark inside the Jobs row today. Add new pins: the Role cell has no `JobOwnershipMark`; the Where head renders only when a row has a mark; the menu offers the ownership action. `useOwnershipAction` is private at `job-ownership.tsx:13`: export it and keep the Node test `frontend/components/job-ownership.test.mjs` green (run it with `node --test` as its header says, or through its pytest wrapper if one exists).
- **Docs:** add the Where column to `docs/design-system/components/JobsTable/README.md`.

Commit: `feat(jobs): one row height, a Where column, ownership in the row menu`.

### Task 11: Career history cards and opacity fills

**`components/career/entity-card.tsx`:**
- Remove the kicker (:61-65). Every list is single-kind, and "Other sections" already has an h3 per section title.
- Drop the `completed` chip: return null for completed, and keep Ongoing and Archived.
- Hide a `Metric` whose value is 0.
- Change `bg-background/70` (:153) to `bg-surface-container`.

**Opacity fills used as component fills:**
- `bg-primary/10` + `text-primary` becomes `bg-primary-container text-on-primary-container` (an icon bubble may keep `text-primary` if contrast holds). Sites: `send-to-resume-dialog.tsx:54-56`, `profile-panel.tsx:89`, `timeline-panel.tsx:44`, `capture-box.tsx:143`, `points-list.tsx:424`, `question-pass.tsx:411`, `setup/dropzone.tsx:178`, `analytics/gap-tiers-panel.tsx:41`.
- `bg-background/70|80|90` used as a fill becomes the surface step it sits on plus one (`surface-container-low` on a card, `surface-container` on the page). Sites: `documents-panel.tsx:148`, `entity-detail.tsx:359`, `inbox-panel.tsx:231,419,486`, `merge-entity-dialog.tsx:219` (hover: `hover:bg-surface-container-high`), `capture-box.tsx:156`.
- Leave the overlay sites alone: the sticky and fixed bars and the pills over images.
- Add a pin: no `bg-primary/` or `bg-background/` outside an allow-list. The allow-list is the overlay files (the tailor sticky footer, `health-report-page.tsx`, `question-pass.tsx` sticky bar, `triage-actions.tsx`, `sidebar-reveal-trigger.tsx`, `gallery/preview-thumbnail.tsx`) plus `components/ui/button.tsx` (a comment only). The numeric tint tests in `test_frontend_color_roles.py:156-192` are not site pins, so removing sites is safe.

Commit: `fix(ui): quieter career cards, no opacity fills`.

### Task 12: "In N resumes" on Career history cards

**Backend:** `KBEntitySummary` (`backend/app/schemas/career_kb.py:308`) gains `used_in_bases: list[str] = []` (active base slugs; the default keeps `KBEntityDetail` (:328) and every other builder working). `entity_summary(session, entity)` (`services/career_kb.py:495`) serves both list and detail: give it an optional `used_in: dict[str, list[str]] | None` argument and precompute the map once in the list route (`routers/career_kb.py:166-179`) with one query: `SELECT DISTINCT entity_id, resume_key FROM kb_port_log WHERE resume_kind='base'`, filtered to active base slugs (`deleted_at IS NULL`). Test it in the KB entity list tests: port a point to a base, and the entity lists that slug; delete the base, and the slug is gone.

Known gap: `create_from_kb` writes no port-log rows, so bases composed from Career history are not counted. Record it in SYSTEM.md §11; do not fix it here.

**Frontend:** the card's last row, shown only when the list is non-empty: "In N resumes" (`body-small`, muted) followed by up to 8 `ResumeSwatch` squares, the rest as "+N". The squares' names go in the row's `title` and in an `sr-only` list.

Commit: `feat(career): show which base resumes use an item`.

### Task 13: Verify step 2

- Run the full backend suite with xdist, then `npx tsc --noEmit`, `npm run lint` and `npm run build`.
- Run the slop ratchet on `frontend` and `backend` (`python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check <surface>`).
- Browser check on a snapshot of the live data, following the stack recipe in the worktree-verification memory: a scratch home, `sqlite3 .backup`, `base_resumes/` copied in, uvicorn on a spare port, `next dev` on another. Check at 1280 and 1024, in light and dark: Base resumes, a job's Score and tailor, Jobs (sync on and off), Career history, Agent inbox, Analytics, and the New base resume dialog including Custom.
- Never touch the live install or its data.

---

# Step 3: the Companion

### Task 14: Align the panel's own colours with the app

**Files:** `extension/panel/panel.css` (:19-90), `backend/tests/test_extension_status_roles.py` (`_COPIED` :52-59).

Change light and dark to the app values:

| Token | Light | Dark |
|---|---|---|
| `--cs-primary` | `--primary` | 0.76 0.11 259 |
| `--cs-on-primary` | (no change) | restate it as 0.205 0.05 259, or the dark CTAs break |
| `--cs-primary-tonal` | `--primary-container` | `--primary-container` |
| `--cs-good` | `--success` | 0.83 0.11 163 |
| `--cs-good-tonal` | `--success-container` | `--success-container` |
| `--cs-warn-tonal` | `--warning-container` | `--warning-container` |
| `--cs-warn-text` | `--on-warning-container` (it sits on the warn tint at `.sub.ko`) | `--on-warning-container` |
| `--cs-danger-text` | `--destructive` | `--destructive` |
| `--cs-muted` | `--muted-foreground` | `--muted-foreground` |

Then:
- Check every text use (`.chip.lib`, `.ats .delta`, `.baserow .score.good`, `.identity .refresh:hover`) against its background.
- Extend `_COPIED` with explicit entries: today's f-string covers only `--cs-<role>-container`. Add `--cs-primary→--primary`, `--cs-on-primary→--primary-foreground`, `--cs-primary-tonal→--primary-container`, `--cs-good→--success`, `--cs-good-tonal→--success-container`, `--cs-warn-tonal→--warning-container`, `--cs-warn-text→--on-warning-container`, `--cs-danger-text→--destructive`, `--cs-muted→--muted-foreground`.
- The test asserts every pinned token is restated in the panel's dark block. `--cs-good` and `--cs-on-primary` are not restated there today (panel.css:62-75), so restate them.
- Add a contrast test over the panel's text-on-fill pairs, reusing `_contrast`.
- The extension tests must stay green: `tests/test_extension_*.py`.

Commit: `fix(extension): the panel's colours are the app's`.

### Task 15: The square in the Companion

**Files:**
- Create: `extension/shared/resume-color.js`, with the same presets as the frontend (an IIFE on the `ns` namespace like the other shared files). Load it with a `<script>` tag in `panel/panel.html` before `icons.js`. The test harness reads the script list from panel.html (`extension_panel_harness.py:68-84`), so nothing else needs listing.
- Modify: `extension/panel/panel.css`, adding the six tone variables per theme with the `--cs-` prefix (`--cs-resume-swatch-l`, `--cs-resume-swatch-c`, `--cs-resume-container-l`, …), declared in both the light `:root` and the dark block. `_COPIED` maps `--cs-X → --X` and the dark parser captures only `--cs-*`. Then add `.swatch { width:10px; height:10px; border-radius:2px; flex:none; background: oklch(var(--cs-resume-swatch-l) calc(var(--resume-c,0) * var(--cs-resume-swatch-c)) var(--resume-h,0)); }`.
- Modify: `panel.js`, adding a `swatch(build, hue)` helper that returns `null` when `hue` is null (`attach` skips nulls) and otherwise a `span.swatch` with `aria-hidden` and `style.setProperty("--resume-h"/"--resume-c")`.
- Modify: `stages/job.js` `rowText` :283-288 (the square before the name).
- Modify: `tailoredFrom` :302-310 / :340. Keep the words as the `div.sub`'s OWN text node first, then attach the square as a child. `test_extension_panel_score.py:428` asserts `_by_class(body,"sub")[0]["text"] == "Resume from Data Scientist · 64"`, and `["text"]` is the node's own text. Do not change that assertion.
- Leave `panel.js` `stageSummaries` :1081-1093 as text: those are strings, and a one-line summary gets no square.
- Modify: `stages/resume.js` :94-97/:189 "Using … as is", if it builds a node. If it builds a string, leave it.
- Modify: `test_resume_color_parity.py`, which now also parses `extension/shared/resume-color.js`; `test_extension_status_roles.py`, adding the six `--cs-resume-*` tone variables to `_COPIED`.
- Modify: `test_extension_panel_job.py`, asserting that the base rows carry a `.swatch` with `--resume-h` set from `color_hue` and none when `color_hue` is null.

Commit: `feat(extension): the base resume square in the Companion`.

### Task 16: Close out

- Run the full backend suite with xdist, the frontend gates and the slop ratchet.
- SYSTEM.md: integrate, don't append. In §6, add an invariant if one fits ("Base resume colour is identity, never state", enforced by `test_frontend_resume_colors.py` + `test_resume_color_parity.py`, with a stable id and a pin in `.system_md_enforcement.json`). §11 gets the `create_from_kb` port-log gap. Run `python3 scripts/check_system_md.py`.
- `docs/design-system/README.md` "Not synced" names what the artifact copy lacks.
- **Do not push.** Report to the owner, who decides when to push and release.
