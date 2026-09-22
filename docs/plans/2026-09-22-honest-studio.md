# Honest studio + app-wide UI fixes — implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or
> superpowers:subagent-driven-development) to implement this plan task-by-task.

## Goal Card

**Goal.** The product is called Maestro Career *Studio*, and the owner wants the
résumé editors to feel like a studio: the page is honest about whether it
reflects your edits, you can always see whether your work is saved, frequent
moves have keys, and the page is framed as the centerpiece. In the same pass,
fix the app-wide defects the UX research verified against primary sources:
light-mode blue text fails WCAG AA on tints, the sidebar barely shows or
announces the current page, "New application" is repeated on one screen, and a
new user dead-ends on the Score tab. Minimal and intuitive stays the bar.

**Principles**
- **Keep explicit Save.** "Two save models, and only two"
  (`docs/frontend-conventions.md`). A résumé save writes a version, renders and
  re-scores, so the studio feel comes from status and honesty, never autosave.
- **Accessibility is not negotiable.** Keyboard reachable, WCAG 2.2 AA contrast
  and target size, programmatic state (`aria-current`, `role="status"`).
- **No new dependencies.** Tailwind v4 tokens and the existing components only.
- **Conventions win unless this plan changes them on purpose.** Every
  deliberate change updates `docs/frontend-conventions.md` in Task 13.

**Non-goals**
- Phase 2 and 3 of the research conclusion: the draft preview, the three-zone
  inspector at ≥1200px, the job-fit chip in the tailored studio, and
  document-level undo/redo. Separate plans.
- The earlier review items not listed here (KB "Profile" tab rename,
  `category_label`, analytics role labels, copy nits, Referrals, template
  Sample label, and whether example-value placeholders stay allowed). A
  follow-up plan. Task 5 still removes `/new`'s instruction placeholder: that
  one breaks the convention as it stands today.

**Autonomy: peer (adapt-and-advise).** You may adapt *how* when a step
conflicts with repo reality — log every deviation below with one line of
reason. Anything touching scope, another task's interface, or the Goal Card
goes back to the planner as a deviation note. Never expand scope.

**Source of truth for the decisions:**
`docs/ux/research-studio-and-ui-direction.md` (Conclusion section; Part A
§4–5 for the studio, Part B C1, C2, C5 and R1–R2, R10 for colours and the
sidebar). The owner decided on 2026-09-22: Refresh-first preview (Phase 2), three zones at ≥1200px (Phase 2), a
focus toggle only (no auto-hide), and a grey canvas behind the page.

**Architecture.** Colour roles become real M3 tokens in `globals.css`
(light primary moves to M3 tone 40; primary and secondary container pairs;
a canvas neutral), pinned by a pytest that computes WCAG contrast from the CSS.
The studios gain pure helpers in `lib/studio.ts` and `lib/shortcuts.ts`
(unit-tested with `node --test`), one `SaveStatusText` component, and two
hooks (`useSaveShortcut`, `useModKey`); `EditorShell` owns the stale strip,
the canvas and the keyboard divider, and `PdfPagesPreview` owns zoom.
Structure is pinned by pytest source tests in `backend/tests/`, because CI has
no React test runner.

**Tech stack.** Next 16 App Router, React 19, Tailwind v4, Base UI-flavoured
shadcn, TanStack Query v5; pytest (source pins) and `node --test` (pure TS).

---

## Before you start

- Work only in the worktree
  `/Users/ajeyds/Projects/maestro-career-studio/.claude/worktrees/seinun-resume-update-45a8c0`
  on branch `claude/review-ui-ux-improvements-70a620`. Never `cd` to the main
  checkout (its `data/` is the real database). Subagents: use absolute
  worktree paths and confirm with `git -C <worktree> status` (SYSTEM.md §12).
- Read `SYSTEM.md` and `docs/frontend-conventions.md` first. Every rule there
  was paid for by a defect.
- **Install frontend deps once:** `cd frontend && npm ci` (the worktree has no
  `node_modules`). Then read `frontend/AGENTS.md`: this Next version has
  breaking changes; check `node_modules/next/dist/docs/` before touching any
  Next API. This plan touches none beyond components.
- **Python:** `/opt/anaconda3/bin/python3` holds the editable backend install.
  Run pytest from the worktree's `backend/` so `app` resolves to the worktree.
  Tests need no service (conftest makes a throwaway SQLite file).
- **Frontend unit tests:** `cd frontend && node --test lib/<name>.test.ts`.
  Test files import siblings with the `.ts` extension
  (`from "./studio.ts"`) and must not import `@/…` paths; `tsconfig.json`
  excludes `*.test.ts` from `tsc`. CI does not run these, so the pytest pins
  are the CI-enforced half.
- **Baseline before Task 1** (record results in *Gate results* below):
  `cd frontend && npx tsc --noEmit && npm run lint`;
  `cd backend && python3 -m pytest tests/ mcp_server/tests/ -q`.
- Every commit message ends with
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Keep the *Deviation log* and *Gate results* tables at the end current.
- Contrast numbers in this plan are computed from tokens, not measured. Task 14
  confirms the key ones in the browser.

---

### Task 1: Colour roles (M3 tone-40 primary, containers, canvas)

Light `--primary` is `oklch(0.55 0.17 259)`, lighter than M3's light primary
(tone 40 ≈ `oklch(0.48 …)`), so `text-primary` fails 4.5:1 on its own tints
(3.8–4.3:1 on the `tonal` button, across 25+ controls). Moving primary to tone
40 fixes every hand-rolled `bg-primary/10|15 text-primary` pairing at once
(worst case becomes 4.52:1). Tonal buttons move to M3's secondary container,
and a `fab` variant takes primary container (M3's FAB default).

**Files**
- Create: `backend/tests/test_frontend_color_roles.py`
- Modify: `frontend/app/globals.css`
- Modify: `frontend/components/ui/button.tsx` (tonal comment + variant; add `fab`)
- Modify: `frontend/components/ui/badge.tsx` (tonal variant)
- Modify: `frontend/components/setup/setup-status-strip.tsx:21`

**Step 1: Write the failing test** — `backend/tests/test_frontend_color_roles.py`:

```python
"""Pins the M3 colour roles in frontend/app/globals.css.

Contrast is COMPUTED from the tokens: OKLCH -> OKLab -> linear sRGB -> WCAG
relative luminance, with alpha composited in gamma-encoded sRGB, which is how
a browser blends `bg-primary/10` over a surface. Not a browser measurement,
but the same arithmetic, and it fails CI the moment a token slips below WCAG
1.4.3's 4.5:1 for normal-size text.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_CSS = (_FRONTEND / "app/globals.css").read_text()
_BUTTON = (_FRONTEND / "components/ui/button.tsx").read_text()
_BADGE = (_FRONTEND / "components/ui/badge.tsx").read_text()

_OKLCH = re.compile(r"--([\w-]+):\s*oklch\(([\d.]+)\s+([\d.]+)\s+([\d.]+)\)")


def _tokens(selector: str) -> dict[str, tuple[float, float, float]]:
    start = _CSS.index(f"{selector} {{")  # first block: the palette
    block = _CSS[start : _CSS.index("}", start)]
    return {
        m.group(1): (float(m.group(2)), float(m.group(3)), float(m.group(4)))
        for m in _OKLCH.finditer(block)
    }


LIGHT = _tokens(":root")
DARK = {**LIGHT, **_tokens(".dark")}
_MODES = {"light": LIGHT, "dark": DARK}


def _oklab(lch):
    lightness, chroma, hue = lch
    return (
        lightness,
        chroma * math.cos(math.radians(hue)),
        chroma * math.sin(math.radians(hue)),
    )


def _srgb(lab):
    lightness, a, b = lab
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    linear = (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )

    def encode(x: float) -> float:
        x = max(0.0, x)
        return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055

    return tuple(min(1.0, encode(v)) for v in linear)


def _luminance(rgb) -> float:
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _rgb(tokens, name):
    return _srgb(_oklab(tokens[name]))


def _over(fg, bg, alpha):
    return tuple(alpha * f + (1 - alpha) * b for f, b in zip(fg, bg))


def _hover(tokens, container, on):
    # Mirrors `color-mix(in oklab, container, on 8%)` in globals.css.
    c, o = _oklab(tokens[container]), _oklab(tokens[on])
    return _srgb(tuple(0.92 * x + 0.08 * y for x, y in zip(c, o)))


_PAIRS = [
    ("primary-container", "on-primary-container"),
    ("secondary-container", "on-secondary-container"),
]


@pytest.mark.parametrize("mode", list(_MODES))
@pytest.mark.parametrize("container,on", _PAIRS)
def test_container_text_meets_aa_at_rest_and_on_hover(mode, container, on):
    t = _MODES[mode]
    assert _contrast(_rgb(t, on), _rgb(t, container)) >= 4.5
    assert _contrast(_rgb(t, on), _hover(t, container, on)) >= 4.5


# Blue text sits on blue tints at ~20 hand-rolled sites. Light mode is safe up
# to /15 at tone 40; /20 is dark-mode only (see the scan below).
_TINT_CEILING = {"light": 0.15, "dark": 0.20}


@pytest.mark.parametrize("mode", list(_MODES))
def test_primary_text_on_primary_tints_meets_aa(mode):
    t = _MODES[mode]
    primary = _rgb(t, "primary")
    for surface in ("card", "background", "sidebar", "muted"):
        bg = _rgb(t, surface)
        for pct in (5, 10, 15, 20):
            if pct / 100 > _TINT_CEILING[mode]:
                continue
            ratio = _contrast(primary, _over(primary, bg, pct / 100))
            assert ratio >= 4.5, (
                f"{mode}: text-primary on bg-primary/{pct} over --{surface} "
                f"is {ratio:.2f}:1"
            )


def test_light_primary_is_m3_tone_40():
    lightness, _, _ = LIGHT["primary"]
    assert lightness <= 0.49, (
        "light --primary is M3 tone 40 (about oklch 0.48); any lighter and blue "
        "text fails AA on its own tints again"
    )


def test_no_light_mode_primary_20_tint_under_primary_text():
    offenders = []
    for root in ("app", "components"):
        for path in (_FRONTEND / root).rglob("*.tsx"):
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if not re.search(r"text-primary(?![-\w])", line):
                    continue
                for tok in re.findall(r"[\w:\[\]&-]*bg-primary/20\b", line):
                    if "dark:" not in tok:
                        offenders.append(f"{path.relative_to(_FRONTEND)}:{n}: {tok}")
    assert offenders == [], offenders


def test_tonal_variants_use_secondary_container():
    for source in (_BUTTON, _BADGE):
        tonal = re.search(r'tonal:\s*"([^"]+)"', source).group(1)
        assert "bg-secondary-container" in tonal
        assert "text-on-secondary-container" in tonal
        assert "bg-primary/" not in tonal


def test_fab_variant_uses_primary_container():
    fab = re.search(r'fab:\s*"([^"]+)"', _BUTTON).group(1)
    assert "bg-primary-container" in fab
    assert "text-on-primary-container" in fab


def test_theme_exposes_role_utilities():
    for role in (
        "primary-container",
        "on-primary-container",
        "primary-container-hover",
        "secondary-container",
        "on-secondary-container",
        "secondary-container-hover",
        "canvas",
    ):
        assert f"--color-{role}: var(--{role});" in _CSS
```

Note: `re.search(r'tonal:\s*"…"')` expects the variant string on the line after
`tonal:` or the same line; `\s*` spans the newline. Keep each variant a single
string literal.

**Step 2: Run it and watch it fail**

Run: `cd backend && python3 -m pytest tests/test_frontend_color_roles.py -q`
Expected: FAIL — `KeyError: 'primary-container'` and the tone-40 assertion.

**Step 3: Implement**

`frontend/app/globals.css` — in `@theme inline { … }` add, beside the other
`--color-*` lines:

```css
  --color-primary-container: var(--primary-container);
  --color-on-primary-container: var(--on-primary-container);
  --color-primary-container-hover: var(--primary-container-hover);
  --color-secondary-container: var(--secondary-container);
  --color-on-secondary-container: var(--on-secondary-container);
  --color-secondary-container-hover: var(--secondary-container-hover);
  --color-canvas: var(--canvas);
```

In the first `:root { … }` block, replace the primary line and its comment:

```css
  /* Google-blue primary at M3 tone 40, the light-theme primary Material
     derives from a blue source. It was oklch(0.55), a tone lighter, and blue
     text failed WCAG AA (3.8-4.3:1) on its own tints across 25+ controls.
     Pinned by backend/tests/test_frontend_color_roles.py. */
  --primary: oklch(0.48 0.17 259);
```

and add, after `--primary-foreground`:

```css
  /* M3 colour roles from the same hue (a static scheme: no wallpaper source
     on a desktop app). FAB = primary container; tonal buttons and the nav
     active indicator = secondary container. Hover is M3's 8% state layer of
     the on-colour, mixed once here so call sites never pick an opacity.
     Declared once: custom properties resolve per element, so .dark's
     container values flow through these color-mix()es. */
  --primary-container: oklch(0.91 0.045 259);
  --on-primary-container: oklch(0.33 0.12 259);
  --primary-container-hover: color-mix(in oklab, var(--primary-container), var(--on-primary-container) 8%);
  --secondary-container: oklch(0.925 0.022 259);
  --on-secondary-container: oklch(0.33 0.05 259);
  --secondary-container-hover: color-mix(in oklab, var(--secondary-container), var(--on-secondary-container) 8%);
  /* Neutral canvas behind the rendered page in studio previews. */
  --canvas: oklch(0.915 0 0);
```

In `.dark { … }`, after `--primary-foreground`, add:

```css
  --primary-container: oklch(0.37 0.09 259);
  --on-primary-container: oklch(0.92 0.04 259);
  --secondary-container: oklch(0.33 0.03 259);
  --on-secondary-container: oklch(0.91 0.02 259);
  --canvas: oklch(0.115 0 0);
```

`frontend/components/ui/button.tsx` — replace the tonal comment and variant
(lines ~17–24) with:

```tsx
        // M3's filled-tonal: SECONDARY container, M3's role for "recessive
        // components like tonal buttons". It was `bg-primary/10 text-primary`,
        // which failed AA (3.8-4.3:1) in light mode; the role pair is pinned
        // at >= 4.5:1 by backend/tests/test_frontend_color_roles.py.
        tonal:
          "bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover",
        // M3 extended FAB: the ONE create action on a screen (the sidebar's
        // New application). Primary container is M3's default FAB colour.
        fab: "bg-primary-container text-on-primary-container shadow-sm hover:bg-primary-container-hover hover:shadow-md",
```

`frontend/components/ui/badge.tsx` — the `tonal` variant becomes:

```tsx
        tonal:
          "bg-secondary-container text-on-secondary-container [a]:hover:bg-secondary-container-hover",
```

(Keep its comment; change "the same fill ladder" to "the same role pair".)

`frontend/components/setup/setup-status-strip.tsx:21` — `hover:bg-primary/20`
→ `hover:bg-primary/15` (light /20 under blue text is below AA over muted).

**Step 4: Run the test and the type check**

Run: `cd backend && python3 -m pytest tests/test_frontend_color_roles.py -q` → PASS
Run: `cd frontend && npx tsc --noEmit && npm run lint` → clean.

**Step 5: Commit**

```bash
git add backend/tests/test_frontend_color_roles.py frontend/app/globals.css \
  frontend/components/ui/button.tsx frontend/components/ui/badge.tsx \
  frontend/components/setup/setup-status-strip.tsx
git commit -m "fix(ui): M3 colour roles; tone-40 primary passes AA on tints"
```

---

### Task 2: Sidebar shows and announces the current page; the FAB

Active row today: neutral `oklch(0.97)` on a `0.985` sidebar (≈1.045:1),
identical to hover, and no `aria-current` anywhere (WCAG technique ARIA26 for
1.3.1). The New application CTA becomes the `fab` variant with M3's 16px
corners. The sidebar toggle names its shortcut. Cross-reload persistence of the
sidebar state is **out of scope**: reading the cookie in the root layout makes
every route dynamic, which conflicts with the desktop plan's static UI served by
the Python sidecar. In-app navigation already keeps the state.

**Files**
- Create: `frontend/lib/nav.ts`, `frontend/lib/nav.test.ts`
- Create: `frontend/lib/shortcuts.ts`, `frontend/lib/shortcuts.test.ts`
- Create: `frontend/hooks/use-mod-key.ts`
- Create: `backend/tests/test_frontend_sidebar_nav.py`
- Modify: `frontend/components/app-sidebar.tsx`
- Modify: `frontend/components/ui/sidebar.tsx` (`sidebarMenuButtonVariants`)
- Modify: `frontend/components/sidebar-reveal-trigger.tsx`

**Step 1: Failing unit tests**

`frontend/lib/nav.test.ts`:

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { navCurrent } from "./nav.ts";

test("the exact route is the current page", () => {
  assert.equal(navCurrent("/applications", "/applications"), "page");
});

test("a child route marks its section current, not as the page", () => {
  assert.equal(navCurrent("/base-resumes/data_scientist", "/base-resumes"), "true");
});

test("a sibling sharing a prefix is not current", () => {
  assert.equal(navCurrent("/applications-archive", "/applications"), undefined);
});

test("an unrelated route is not current", () => {
  assert.equal(navCurrent("/settings", "/profile"), undefined);
});
```

`frontend/lib/shortcuts.test.ts`:

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { modKeyFor, shortcutLabel } from "./shortcuts.ts";

test("Apple platforms get Command, everything else Control", () => {
  assert.equal(modKeyFor("MacIntel"), "⌘");
  assert.equal(modKeyFor("iPhone"), "⌘");
  assert.equal(modKeyFor("Win32"), "Ctrl");
  assert.equal(modKeyFor("Linux x86_64"), "Ctrl");
});

test("labels use each platform's own spelling", () => {
  assert.equal(shortcutLabel("⌘", "s"), "⌘S");
  assert.equal(shortcutLabel("Ctrl", "b"), "Ctrl+B");
});
```

**Step 2: Failing pins** — `backend/tests/test_frontend_sidebar_nav.py`:

```python
"""Pins: the sidebar SHOWS and ANNOUNCES the current page, and its create
action is the M3 FAB. See docs/ux/research-studio-and-ui-direction.md Part B
C1, C2 and C5."""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_SIDEBAR = (_FRONTEND / "components/app-sidebar.tsx").read_text()
_UI = (_FRONTEND / "components/ui/sidebar.tsx").read_text()
_REVEAL = (_FRONTEND / "components/sidebar-reveal-trigger.tsx").read_text()


def test_nav_links_carry_aria_current():
    assert "navCurrent(" in _SIDEBAR
    assert "aria-current={current}" in _SIDEBAR


def _menu_button_base() -> str:
    # The cva BASE string only: `SidebarMenuSubButton` further down still
    # carries shadcn's neutral active style, and the app never renders it.
    start = _UI.index("const sidebarMenuButtonVariants = cva(")
    open_quote = _UI.index('"', start)
    return _UI[open_quote + 1 : _UI.index('"', open_quote + 1)]


def test_active_row_is_a_tinted_indicator_distinct_from_hover():
    base = _menu_button_base()
    assert "data-active:bg-secondary-container" in base
    assert "data-active:font-semibold" in base
    assert "data-active:bg-sidebar-accent" not in base
    assert "hover:bg-sidebar-accent" in base  # hover stays neutral


def test_create_action_is_the_fab_variant():
    assert 'variant: "fab"' in _SIDEBAR
    assert "bg-primary/15" not in _SIDEBAR


def test_sidebar_toggles_name_their_shortcut():
    assert 'shortcutLabel(mod, "B")' in _SIDEBAR
    assert 'shortcutLabel(mod, "B")' in _REVEAL
```

**Step 3: Run both and watch them fail**

Run: `cd frontend && node --test lib/nav.test.ts lib/shortcuts.test.ts` → FAIL (modules missing)
Run: `cd backend && python3 -m pytest tests/test_frontend_sidebar_nav.py -q` → FAIL

**Step 4: Implement**

`frontend/lib/nav.ts`:

```ts
/**
 * `aria-current` for a sidebar destination (WCAG technique ARIA26).
 *
 * "page" when the route IS the destination; "true" when it is inside it (a
 * base-resume studio under Base Resumes), so exactly one item in the set is
 * current either way. `undefined` omits the attribute.
 */
export function navCurrent(
  pathname: string,
  href: string,
): "page" | "true" | undefined {
  if (pathname === href) return "page";
  if (pathname.startsWith(`${href}/`)) return "true";
  return undefined;
}
```

`frontend/lib/shortcuts.ts`:

```ts
/** Keyboard-shortcut helpers. Pure (no DOM, no React) so `node --test` runs them. */

export type ModKey = "⌘" | "Ctrl";

/** Apple platforms use Command; everything else Control. */
export function modKeyFor(platform: string): ModKey {
  return /Mac|iPhone|iPad|iPod/i.test(platform) ? "⌘" : "Ctrl";
}

/** "⌘S" on Apple platforms, "Ctrl+S" elsewhere: each platform's own spelling. */
export function shortcutLabel(mod: ModKey, key: string): string {
  const k = key.toUpperCase();
  return mod === "⌘" ? `⌘${k}` : `Ctrl+${k}`;
}
```

`frontend/hooks/use-mod-key.ts`:

```ts
"use client";

import { useEffect, useState } from "react";

import { modKeyFor, type ModKey } from "@/lib/shortcuts";

/**
 * The platform's modifier, for shortcut hints. "Ctrl" on the server AND on the
 * first client render so hydration matches; corrected after mount.
 */
export function useModKey(): ModKey {
  const [mod, setMod] = useState<ModKey>("Ctrl");
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the platform is only knowable after mount
    setMod(modKeyFor(navigator.platform || navigator.userAgent));
  }, []);
  return mod;
}
```

`frontend/components/ui/sidebar.tsx` — in the `sidebarMenuButtonVariants`
base string, replace
`data-active:bg-sidebar-accent data-active:font-medium data-active:text-sidebar-accent-foreground`
with
`data-active:bg-secondary-container data-active:font-semibold data-active:text-on-secondary-container data-active:hover:bg-secondary-container-hover data-active:[&_svg]:text-primary`.
Leave `hover:bg-sidebar-accent` (neutral hover, now distinct from active).
Pair `data-active:` with `hover:` explicitly. shadcn's `data-active` variant
compiles to `:where([data-active])`, which adds NO specificity, so a bare
`data-active:bg-*` (0,1,0) loses to `hover:bg-sidebar-accent` (0,2,0). The
paired `data-active:hover:` ties it and wins on output order (custom variants
are emitted after built-in `hover:`); verified in compiled CSS during Task 1's
review.

`frontend/components/app-sidebar.tsx`:
- Imports: add `navCurrent` from `@/lib/nav`, `shortcutLabel` from
  `@/lib/shortcuts`, `useModKey` from `@/hooks/use-mod-key`.
- In `AppSidebar`: replace the `isActive` lambda with
  `const mod = useModKey();` (no `isActive` needed any more).
- Header trigger: `<SidebarTrigger className="shrink-0" title={`Toggle sidebar (${shortcutLabel(mod, "B")})`} />`.
- The CTA `<Link>` becomes:

```tsx
          <Link
            href="/new"
            aria-current={navCurrent(pathname, "/new")}
            className={cn(
              // M3 extended FAB at the top of the rail: primary container,
              // 16px corners (M3's 16dp; this theme's rounded-2xl is 18px), the
              // one create action on a screen.
              buttonVariants({ variant: "fab", size: "lg" }),
              "h-10 gap-2.5 rounded-[16px] px-4",
              navCurrent(pathname, "/new") && "shadow-md",
            )}
          >
```

- `NavMenu` takes `pathname` instead of `isActive`:

```tsx
function NavMenu({ items, pathname }: { items: NavItem[]; pathname: string }) {
  return (
    <SidebarMenu>
      {items.map((item) => {
        const Icon = item.icon;
        const current = navCurrent(pathname, item.href);
        return (
          <SidebarMenuItem key={item.href}>
            <SidebarMenuButton
              isActive={current !== undefined}
              render={
                <Link href={item.href} aria-current={current}>
                  <Icon />
                  <span>{item.label}</span>
                </Link>
              }
            />
          </SidebarMenuItem>
        );
      })}
    </SidebarMenu>
  );
}
```

and both call sites pass `pathname={pathname}`.

`frontend/components/sidebar-reveal-trigger.tsx` — import `useModKey` and
`shortcutLabel`; in `SidebarRevealTrigger` add `const mod = useModKey();` and
pass `title={`Toggle sidebar (${shortcutLabel(mod, "B")})`}` to its
`SidebarTrigger`. (Call `useModKey()` before the `if (!hidden) return null`
early return: hooks run unconditionally.)

**Step 5: Run the tests**

`cd frontend && node --test lib/nav.test.ts lib/shortcuts.test.ts` → PASS
`cd backend && python3 -m pytest tests/test_frontend_sidebar_nav.py -q` → PASS
`cd frontend && npx tsc --noEmit && npm run lint` → clean

**Step 6: Commit**

```bash
git add frontend/lib/nav.ts frontend/lib/nav.test.ts frontend/lib/shortcuts.ts \
  frontend/lib/shortcuts.test.ts frontend/hooks/use-mod-key.ts \
  frontend/components/app-sidebar.tsx frontend/components/ui/sidebar.tsx \
  frontend/components/sidebar-reveal-trigger.tsx backend/tests/test_frontend_sidebar_nav.py
git commit -m "fix(ui): sidebar shows and announces the current page; New application is the FAB"
```

---

### Task 3: Empty tracker leads with the task; one New application

**Files**
- Create: `backend/tests/test_frontend_first_run.py`
- Modify: `frontend/app/applications/page.tsx`
- Modify: `frontend/components/setup/setup-steps.ts`
- Modify: `frontend/components/setup/getting-started-card.tsx`

**Step 1: Failing pins** — `backend/tests/test_frontend_first_run.py`:

```python
"""Pins for the first-run path: the task before the checklist, one create
action per screen, the two required setup steps marked, and no dead ends
(Score tab with no base resumes; Extract with no API key)."""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def test_empty_tracker_leads_with_the_task_not_the_checklist():
    page = _read("app/applications/page.tsx")
    empty = page[page.index("filtered.length === 0 ?") :]
    assert empty.index("<EmptyState") < empty.index("<GettingStartedCard")


def test_header_new_application_only_while_the_sidebar_fab_is_hidden():
    page = _read("app/applications/page.tsx")
    assert "useSidebarHidden()" in page
    assert "sidebarHidden ? (" in page


def test_required_setup_steps_are_marked():
    assert _read("components/setup/setup-steps.ts").count("required: true") == 2
    card = _read("components/setup/getting-started-card.tsx")
    assert "row.required && !row.done" in card
```

**Step 2: Run** `cd backend && python3 -m pytest tests/test_frontend_first_run.py -q` → FAIL.

**Step 3: Implement**

`frontend/app/applications/page.tsx`:
- Import `useSidebarHidden` from `@/components/sidebar-reveal-trigger`.
- In the component, beside the other hooks: `const sidebarHidden = useSidebarHidden();`
- `PageHeader`'s `actions` becomes:

```tsx
        actions={
          // The sidebar's FAB is THE New application while it is showing (M3:
          // a FAB's action is not repeated on its screen). The sidebar slides
          // off-canvas when collapsed and below 768px; then this is the only
          // way to start one, so it renders exactly when the FAB cannot be seen.
          sidebarHidden ? (
            <Button
              nativeButton={false}
              render={
                <Link href="/new">
                  <FilePlus2 className="size-4" />
                  New application
                </Link>
              }
            />
          ) : null
        }
```

- In the `filtered.length === 0` branch, render `<EmptyState …/>` FIRST and
  `{allRows.length === 0 ? <GettingStartedCard /> : null}` AFTER it, and make
  the empty-state action `variant="ghost"` (M3 text button: lowest emphasis;
  NN/g still wants the pathway to be a control, so it stays).

`frontend/components/setup/setup-steps.ts`:
- Add to `SetupStepView`:

```ts
  /** Blocks the core loop: extract needs a key, scoring needs a base resume. */
  required?: boolean;
```

- Add `required: true,` to the `model_key` and `import` step objects only.

`frontend/components/setup/getting-started-card.tsx`:
- Import `Badge` from `@/components/ui/badge`.
- Subtitle copy: `Required steps first. The rest can wait until you need them.`
- Title line becomes:

```tsx
                    <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      {row.title}
                      {row.required && !row.done ? (
                        <Badge variant="outline" className="font-normal">
                          Required
                        </Badge>
                      ) : null}
                    </p>
```

**Step 4: Run** the pins → PASS; also
`python3 -m pytest tests/test_frontend_query_error_states.py -q` → PASS (its
`<GettingStartedCard` marker must still follow the error branch);
`npx tsc --noEmit && npm run lint` → clean.

**Step 5: Commit**

```bash
git add backend/tests/test_frontend_first_run.py frontend/app/applications/page.tsx \
  frontend/components/setup/setup-steps.ts frontend/components/setup/getting-started-card.tsx
git commit -m "fix(ui): empty tracker leads with the task; one New application per screen"
```

---

### Task 4: Score tab with no base résumés offers the import

`score_all_bases` returns `[]` (200) when there are no selectable bases, so
today "Run ATS scoring" re-runs to the same empty screen forever.
`GET /api/base-resumes` returns exactly the selectable set the engine scores.

**Files**
- Modify: `backend/tests/test_frontend_first_run.py` (append)
- Modify: `frontend/components/ats-score-panel.tsx`

**Step 1: Append the failing pin**

```python
def test_score_tab_offers_import_when_there_is_nothing_to_score():
    panel = _read("components/ats-score-panel.tsx")
    assert "No base resumes to score against." in panel
    assert "<UploadDialog" in panel
    # A failed list fetch must never read as "you have none" (conventions).
    assert "bases.isSuccess && bases.data.length === 0" in panel
    assert panel.index("scores.isError") < panel.index(
        "No base resumes to score against."
    )
```

**Step 2: Run** → FAIL.

**Step 3: Implement** in `frontend/components/ats-score-panel.tsx`:
- Imports: add `useState` to the React import; `UploadDialog` from
  `@/components/setup/upload-dialog`; `type BaseResumeSummary` to the
  `@/lib/types` import.
- After the `scores` query:

```tsx
  // The engine scores every SELECTABLE base resume, the same set
  // GET /api/base-resumes returns. With none, "Run ATS scoring" can only
  // return an empty list again, so the empty state offers the import instead.
  const bases = useQuery({
    queryKey: ["base-resumes"],
    queryFn: () => apiFetch<BaseResumeSummary[]>("/api/base-resumes"),
  });
  const noBases = bases.isSuccess && bases.data.length === 0;
  const baseCount = bases.data?.length ?? 0;
  const [importOpen, setImportOpen] = useState(false);
```

- After the existing auto-run `useEffect` (it defines `autoRan`/`runMutate`):

```tsx
  // A resume imported from the prompt below lands in ["base-resumes"] (the
  // import dialog invalidates it). Score against it straight away, but only on
  // a CONFIRMED none -> some transition, never on the first load.
  const sawNoBases = useRef(false);
  useEffect(() => {
    if (noBases) {
      sawNoBases.current = true;
    } else if (sawNoBases.current && baseCount > 0) {
      sawNoBases.current = false;
      runMutate();
    }
  }, [noBases, baseCount, runMutate]);
```

- Inside `if (baseRows.length === 0) {`, before the `unscorable` constant:

```tsx
    if (noBases) {
      return (
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <p className="text-sm font-medium">No base resumes to score against.</p>
          <p className="text-muted-foreground max-w-[50ch] text-sm">
            Import the resumes you already have. Each becomes a base resume, and
            this job is scored against all of them.
          </p>
          <Button size="sm" onClick={() => setImportOpen(true)}>
            Import resumes
          </Button>
          <UploadDialog open={importOpen} onOpenChange={setImportOpen} />
        </div>
      );
    }
```

**Step 4: Run** the first-run pins and
`tests/test_frontend_query_error_states.py` → PASS; tsc + lint clean.

**Step 5: Commit**
`git commit -m "fix(ui): Score tab offers the import when no base resume exists"`
(add both files).

---

### Task 5: New application names the key before the paste

**Files**
- Modify: `backend/tests/test_frontend_first_run.py` (append)
- Modify: `frontend/app/new/page.tsx`

**Step 1: Append the failing pin**

```python
def test_new_application_names_the_key_before_the_paste():
    page = _read("app/new/page.tsx")
    assert "setup.data?.model_key.done === false" in page
    assert "disabled={disabled || busy || needsKey}" in page
    # Placeholders are example values only (conventions: microcopy rules).
    assert "Paste the full job description here" not in page
    assert '<Label htmlFor="source_url" optional>' in page
    assert "The job is listed under Saved. Scoring comes next." in page
```

**Step 2: Run** → FAIL.

**Step 3: Implement** in `frontend/app/new/page.tsx`:
- Imports: `Link` from `next/link`; `useQuery` beside `useMutation`;
  `apiFetch` from `@/lib/api`; `type SetupStatus` beside `type Job`.
- In the component:

```tsx
  // Extract is an LLM call: with no provider key it can only fail, so say so
  // before the paste, not after it. A failed status fetch blocks nothing:
  // `needsKey` is true only on a confirmed "not done". Same query key as the
  // setup checklist, so a key saved in Settings clears this too.
  const setup = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => apiFetch<SetupStatus>("/api/setup/status"),
  });
  const needsKey = setup.data?.model_key.done === false;
```

- Directly after `</PageHeader>`-equivalent (the `PageHeader` element):

```tsx
      {needsKey ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-amber-500/40 bg-amber-500/[0.08] px-3 py-2 text-sm dark:border-amber-400/40 dark:bg-amber-400/[0.08]">
          <span className="text-amber-800 dark:text-amber-200">
            Extract reads the posting with a model, so it needs a provider API key.
          </span>
          <Button
            size="sm"
            variant="outline"
            nativeButton={false}
            render={<Link href="/settings#api-keys" />}
          >
            Add API key
          </Button>
        </div>
      ) : null}
```

- Remove the textarea's `placeholder` prop (it was an instruction).
- Source URL label becomes `<Label htmlFor="source_url" optional>Source URL</Label>`
  (the shared optional suffix; drop the hand-rolled span).
- The button row becomes:

```tsx
      <div className="flex flex-wrap items-center gap-3">
        <Button
          onClick={() => extractJob.mutate()}
          disabled={disabled || busy || needsKey}
        >
          {extractJob.isPending ? "Extracting…" : "Extract job"}
        </Button>
        <p className="text-muted-foreground text-sm">
          The job is listed under Saved. Scoring comes next.
        </p>
      </div>
```

Keep both `setSavedJob(null)` call sites (pinned by
`test_new_application_clears_cached_job_when_source_url_changes`).

**Step 4: Run** the first-run pins and
`tests/test_frontend_query_error_states.py` → PASS; tsc + lint clean.

**Step 5: Commit**
`git commit -m "fix(ui): New application names the API key before the paste"`.

---

### Task 6: Pure studio helpers

**Files**
- Create: `frontend/lib/studio.ts`, `frontend/lib/studio.test.ts`
- Modify: `frontend/lib/shortcuts.ts`, `frontend/lib/shortcuts.test.ts`

**Step 1: Failing tests**

`frontend/lib/studio.test.ts`:

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  actualSizeWidthPx,
  nextPreviewPct,
  parseZoom,
  PREVIEW_PCT,
  saveStatus,
} from "./studio.ts";

const idle = { dirty: false, saving: false, rendering: false, rescoring: false };

test("a clean studio says everything is saved", () => {
  assert.deepEqual(saveStatus(idle), { label: "All changes saved", tone: "clean" });
});

test("unsaved edits are flagged", () => {
  assert.deepEqual(saveStatus({ ...idle, dirty: true }), {
    label: "Unsaved changes",
    tone: "dirty",
  });
});

test("a save in flight outranks the dirty flag it is clearing", () => {
  assert.deepEqual(saveStatus({ ...idle, dirty: true, saving: true }), {
    label: "Saving…",
    tone: "busy",
  });
});

test("render then re-score report in chain order", () => {
  assert.equal(saveStatus({ ...idle, rendering: true, rescoring: true }).label, "Rendering PDF…");
  assert.equal(saveStatus({ ...idle, rescoring: true }).label, "Re-scoring…");
});

test("ArrowLeft widens the preview, ArrowRight narrows it, within limits", () => {
  assert.equal(nextPreviewPct(45, "ArrowLeft"), 50);
  assert.equal(nextPreviewPct(45, "ArrowRight"), 40);
  assert.equal(nextPreviewPct(PREVIEW_PCT.max, "ArrowLeft"), PREVIEW_PCT.max);
  assert.equal(nextPreviewPct(PREVIEW_PCT.min, "ArrowRight"), PREVIEW_PCT.min);
});

test("Home and End jump to the limits; other keys do nothing", () => {
  assert.equal(nextPreviewPct(45, "Home"), PREVIEW_PCT.max);
  assert.equal(nextPreviewPct(45, "End"), PREVIEW_PCT.min);
  assert.equal(nextPreviewPct(45, "Enter"), null);
});

test("an unknown or missing zoom falls back to fit width", () => {
  assert.equal(parseZoom(null), "width");
  assert.equal(parseZoom("bogus"), "width");
  assert.equal(parseZoom("page"), "page");
  assert.equal(parseZoom("actual"), "actual");
});

test("a 150-DPI Letter page is 816 CSS px at actual size", () => {
  assert.equal(actualSizeWidthPx(1275), 816);
});
```

Append to `frontend/lib/shortcuts.test.ts` (and add `isSaveShortcut` to its import):

```ts
test("Cmd+S and Ctrl+S save; with Shift or Alt they do not", () => {
  const key = (over: Partial<{ key: string; metaKey: boolean; ctrlKey: boolean; altKey: boolean; shiftKey: boolean }>) => ({
    key: "s",
    metaKey: false,
    ctrlKey: false,
    altKey: false,
    shiftKey: false,
    ...over,
  });
  assert.equal(isSaveShortcut(key({ metaKey: true })), true);
  assert.equal(isSaveShortcut(key({ ctrlKey: true, key: "S" })), true);
  assert.equal(isSaveShortcut(key({ metaKey: true, shiftKey: true })), false);
  assert.equal(isSaveShortcut(key({ ctrlKey: true, altKey: true })), false);
  assert.equal(isSaveShortcut(key({})), false);
});
```

**Step 2: Run** `cd frontend && node --test lib/studio.test.ts lib/shortcuts.test.ts` → FAIL.

**Step 3: Implement**

`frontend/lib/studio.ts`:

```ts
/**
 * Pure helpers for the resume studios. No DOM, no React: `node --test` runs
 * them directly (lib/studio.test.ts).
 */

export type SaveStatusInput = {
  dirty: boolean;
  saving: boolean;
  rendering: boolean;
  rescoring: boolean;
};

export type SaveStatus = { label: string; tone: "busy" | "dirty" | "clean" };

/**
 * The studio's one save-status line. Work in flight outranks everything (a
 * Save is still "dirty" until the server copy is adopted), then unsaved
 * edits, then clean. It sits beside the title, where Google Docs and
 * Reactive Resume both put it.
 */
export function saveStatus(s: SaveStatusInput): SaveStatus {
  if (s.saving) return { label: "Saving…", tone: "busy" };
  if (s.rendering) return { label: "Rendering PDF…", tone: "busy" };
  if (s.rescoring) return { label: "Re-scoring…", tone: "busy" };
  if (s.dirty) return { label: "Unsaved changes", tone: "dirty" };
  return { label: "All changes saved", tone: "clean" };
}

/** Width of the preview pane, as a percent of the studio. */
export const PREVIEW_PCT = { default: 45, min: 25, max: 70, step: 5 } as const;

/**
 * Keyboard move for the editor/preview divider (APG window-splitter
 * pattern). The divider's value is the EDITOR's share, so Left moves it left:
 * a smaller editor, a wider preview. Home/End jump to the limits; any other
 * key returns null so the caller leaves the event alone.
 */
export function nextPreviewPct(pct: number, key: string): number | null {
  const { min, max, step } = PREVIEW_PCT;
  switch (key) {
    case "ArrowLeft":
      return Math.min(max, pct + step);
    case "ArrowRight":
      return Math.max(min, pct - step);
    case "Home":
      return max;
    case "End":
      return min;
    default:
      return null;
  }
}

export type PreviewZoom = "width" | "page" | "actual";

export const PREVIEW_ZOOMS: { value: PreviewZoom; label: string }[] = [
  { value: "width", label: "Fit width" },
  { value: "page", label: "Fit page" },
  { value: "actual", label: "100%" },
];

export function parseZoom(value: string | null): PreviewZoom {
  return value === "page" || value === "actual" ? value : "width";
}

/**
 * The DPI the backend rasterizes preview pages at (`app/services/pdf_preview.DPI`).
 * Pinned equal by backend/tests/test_frontend_studio.py: a cross-boundary
 * constant needs a contract test, not a comment.
 */
export const PREVIEW_DPI = 150;

/** CSS width for true print size (a CSS inch is 96px). */
export function actualSizeWidthPx(naturalWidthPx: number): number {
  return Math.round((naturalWidthPx * 96) / PREVIEW_DPI);
}
```

Append to `frontend/lib/shortcuts.ts`:

```ts
type KeyLike = {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
};

/** Cmd/Ctrl+S exactly. Shift is "Save As" elsewhere; Alt is someone else's. */
export function isSaveShortcut(e: KeyLike): boolean {
  return (
    (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "s"
  );
}
```

**Step 4: Run** → PASS. `npx tsc --noEmit && npm run lint` → clean.

**Step 5: Commit**
`git commit -m "feat(studio): pure helpers for save status, divider keys and zoom"`.

---

### Task 7: `SaveStatusText` and the two studio hooks

**Files**
- Create: `frontend/components/resume-editor/save-status.tsx`
- Create: `frontend/hooks/use-save-shortcut.ts`

These are exercised by Tasks 9–10's pins and Task 14's browser check.

`frontend/components/resume-editor/save-status.tsx`:

```tsx
import { Loader2 } from "lucide-react";

import type { SaveStatus } from "@/lib/studio";
import { cn } from "@/lib/utils";

/**
 * The studio's save-status line. `role="status"` makes it a polite live
 * region, so each change is announced once without stealing focus.
 *
 * It replaces the success toasts a Save used to fire (three per tailored
 * Save): a toast announces a moment and vanishes, while "is my work saved?"
 * is a question about NOW. Errors still toast, because they must interrupt.
 */
export function SaveStatusText({ status }: { status: SaveStatus }) {
  return (
    <span
      role="status"
      className={cn(
        "inline-flex items-center gap-1.5",
        status.tone === "dirty" && "text-amber-700 dark:text-amber-300",
      )}
    >
      {status.tone === "busy" ? (
        <Loader2 aria-hidden="true" className="size-3 animate-spin" />
      ) : (
        <span
          aria-hidden="true"
          className={cn(
            "size-1.5 rounded-full",
            status.tone === "dirty" ? "bg-amber-500" : "bg-emerald-500",
          )}
        />
      )}
      {status.label}
    </span>
  );
}
```

`frontend/hooks/use-save-shortcut.ts`:

```ts
"use client";

import { useEffect, useRef } from "react";

import { isSaveShortcut } from "@/lib/shortcuts";

/**
 * Cmd/Ctrl+S saves the studio. The browser's own "Save page" dialog is
 * suppressed while a studio is mounted: it saves the app's HTML, never what
 * someone editing a resume meant. `canSave` mirrors the Save button's
 * disabled state, so the key and the button always agree.
 */
export function useSaveShortcut(onSave: () => void, canSave: boolean) {
  const latest = useRef({ onSave, canSave });
  useEffect(() => {
    latest.current = { onSave, canSave };
  });
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!isSaveShortcut(event)) return;
      event.preventDefault();
      if (latest.current.canSave) latest.current.onSave();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
```

(The ref is updated in an effect, not during render: React 19's lint rules
forbid writing `ref.current` while rendering.)

**Run** `npx tsc --noEmit && npm run lint` → clean.
**Commit** `git commit -m "feat(studio): save-status line and Cmd/Ctrl+S hook"`.

---

### Task 8: `EditorShell` — stale strip, canvas, keyboard divider

**Files**
- Create: `backend/tests/test_frontend_studio.py`
- Modify: `frontend/components/resume-editor/editor-shell.tsx`

**Step 1: Failing pins** — `backend/tests/test_frontend_studio.py`:

```python
"""Pins for the honest studio (docs/ux/research-studio-and-ui-direction.md,
Phase 1): the preview says when it is stale, the divider works from the
keyboard, save status lives in the header, Cmd/Ctrl+S saves, and the page
sits on a canvas with zoom presets."""

from __future__ import annotations

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_BACKEND = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


_SHELL = _read("components/resume-editor/editor-shell.tsx")


def test_divider_is_keyboard_operable():
    sep = _SHELL[_SHELL.index('role="separator"') :]
    sep = sep[: sep.index("/>")]
    for attr in (
        "tabIndex={0}",
        'aria-label="Resize preview"',
        "aria-valuenow={Math.round(editorPct)}",
        "aria-valuetext=",
        "aria-controls=",
        "aria-valuemin=",
        "aria-valuemax=",
        "onKeyDown=",
    ):
        assert attr in sep, attr
    assert "nextPreviewPct(" in _SHELL


def test_preview_says_when_it_is_stale():
    assert "previewStale" in _SHELL
    assert "Preview doesn't include your unsaved edits. Save to update it." in _SHELL


def test_preview_pane_is_a_canvas():
    assert "bg-canvas" in _SHELL
    assert "bg-muted/30" not in _SHELL
```

**Step 2: Run** `python3 -m pytest tests/test_frontend_studio.py -q` → FAIL.

**Step 3: Implement** in `editor-shell.tsx`:
- Imports: add `History` to the lucide import; `cn` from `@/lib/utils`;
  `PREVIEW_PCT`, `nextPreviewPct` from `@/lib/studio`. Delete the local
  `DEFAULT_PREVIEW_PCT` / `MIN_PREVIEW_PCT` / `MAX_PREVIEW_PCT` constants and
  use `PREVIEW_PCT.default|min|max` everywhere they were read.
- New prop, documented in the props type:

```tsx
  /**
   * The form has unsaved edits, so the pages below are the LAST SAVE. The
   * shell marks the preview stale rather than letting an old page pass for
   * the current one (Overleaf's "uncompiled" state).
   */
  previewStale?: boolean;
```

- Preview pane wrapper: `bg-muted/30` → `bg-canvas`.
- Replace `<div className="min-h-0 flex-1 overflow-hidden">{preview}</div>` with:

```tsx
        {previewStale ? (
          // Not a live region: the header's save-status line already
          // announces "Unsaved changes". This is the visual half.
          <div className="flex items-center gap-2 border-b bg-amber-500/10 px-3 py-1.5 text-xs text-amber-800 dark:text-amber-200">
            <History aria-hidden="true" className="size-3.5 shrink-0" />
            {"Preview doesn't include your unsaved edits. Save to update it."}
          </div>
        ) : null}
        <div
          className={cn(
            "min-h-0 flex-1 overflow-hidden transition-opacity duration-200",
            previewStale && "opacity-60",
          )}
        >
          {preview}
        </div>
```

- `const editorPaneId = useId();` (add `useId` to the React import) and put
  `id={editorPaneId}` on the open-state left pane `<div className={leftOpenClass} …>`.
- Persist the width rounded: the width effect writes
  `String(Math.round(previewPct))` (dragging leaves fractions; the keyboard
  helper snaps to the 5% grid since Tasks 6–7's review).
- `Splitter` gains keyboard support. Call site:

```tsx
      <Splitter
        editorPct={100 - previewPct}
        controls={editorPaneId}
        onDrag={(deltaPct) =>
          setPreviewPct((p) =>
            Math.min(PREVIEW_PCT.max, Math.max(PREVIEW_PCT.min, p - deltaPct)),
          )
        }
        onKey={(key) => {
          const next = nextPreviewPct(previewPct, key);
          if (next === null) return false;
          setPreviewPct(next);
          return true;
        }}
      />
```

  and the component:

```tsx
function Splitter({
  editorPct,
  controls,
  onDrag,
  onKey,
}: {
  /** The editor's share. Fractional while dragging; announced rounded. */
  editorPct: number;
  /** id of the editor pane this divider resizes (APG window splitter). */
  controls: string;
  onDrag: (deltaPct: number) => void;
  /** Returns true when it handled the key. */
  onKey: (key: string) => boolean;
}) {
  const start = /* unchanged pointer handler */;
  return (
    // APG window splitter: focusable, and its value is the primary (editor)
    // pane's share. Pointer-only resizing was the gap Apple's split-view
    // guidance and WCAG 2.1.1 both name.
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize preview"
      aria-controls={controls}
      aria-valuenow={Math.round(editorPct)}
      // The value is the EDITOR's share; say both so "Resize preview" is not
      // read as the preview's width.
      aria-valuetext={`Editor ${Math.round(editorPct)}%, preview ${100 - Math.round(editorPct)}%`}
      aria-valuemin={100 - PREVIEW_PCT.max}
      aria-valuemax={100 - PREVIEW_PCT.min}
      tabIndex={0}
      onPointerDown={start}
      onKeyDown={(e) => {
        if (onKey(e.key)) e.preventDefault();
      }}
      className="hover:bg-primary/20 focus-visible:bg-primary/40 focus-visible:ring-ring w-1 shrink-0 cursor-col-resize bg-transparent transition-colors outline-none focus-visible:ring-2"
    />
  );
}
```

**Step 4: Run** the studio pins → PASS; tsc + lint clean.
**Step 5: Commit** `git commit -m "feat(studio): stale preview strip, canvas and a keyboard divider"`.

---

### Task 9: Base studio — status line, Cmd/Ctrl+S, dirty-gated Save, Regenerate

Save stays enabled with nothing to save today, and it doubles as the only way
to re-render after a failed render. Gating it (as the tailored studio already
does) needs a replacement retry: the base render endpoint already exists
(`POST /api/base-resumes/{slug}/render`, `backend/app/routers/base_resumes.py`).

**Files**
- Modify: `backend/tests/test_frontend_studio.py` (append)
- Modify: `frontend/components/resume-editor/editor-body.tsx`

**Step 1: Append the failing pins**

```python
_BASE = _read("components/resume-editor/editor-body.tsx")


def test_base_studio_save_is_dirty_gated_and_keyed():
    assert "disabled={!canSave}" in _BASE
    assert "useSaveShortcut(" in _BASE
    assert 'aria-keyshortcuts="Meta+S Control+S"' in _BASE


def test_base_studio_can_rerender_with_nothing_to_save():
    assert "/render`" in _BASE
    assert '"Regenerate PDF"' in _BASE


def test_base_studio_reports_save_in_the_header_not_a_toast():
    assert "<SaveStatusText" in _BASE
    assert "Saved. PDF re-rendered." not in _BASE
    assert "previewStale={hasUnsavedChanges}" in _BASE
```

**Step 2: Run** → FAIL.

**Step 3: Implement** in `editor-body.tsx`:
- Imports: `RefreshCw` (lucide); `useModKey` from `@/hooks/use-mod-key`;
  `useSaveShortcut` from `@/hooks/use-save-shortcut`; `SaveStatusText` from
  `@/components/resume-editor/save-status`; `saveStatus` from `@/lib/studio`;
  `shortcutLabel` from `@/lib/shortcuts`.
- In `save.onSuccess`, delete the `toast.success("Saved. PDF re-rendered.", …)`
  call. Keep `notifyRenderNote(result)`.
- Add after `save`:

```tsx
  // Recovery for a render that FAILED. Save is dirty-gated, so with nothing to
  // save it can no longer double as "render again". Mirrors the tailored
  // studio's ⋯ Regenerate PDF, against the base's own render endpoint (the
  // render IS the request, so a failure is a 400, never a persisted note).
  const regenerate = useMutation({
    mutationFn: () =>
      apiFetch<BaseResumeDetail>(`/api/base-resumes/${slug}/render`, {
        method: "POST",
      }),
    onSuccess: (result) => {
      qc.setQueryData(["base-resumes", slug], result);
      qc.invalidateQueries({ queryKey: ["pdf-preview"] });
      notifyRenderNote(result);
    },
    onError: (err: Error) => toast.error(err.message),
  });
```

- After `useUnsavedChangesWarning(hasUnsavedChanges);`:

```tsx
  const status = saveStatus({
    dirty: hasUnsavedChanges,
    saving: save.isPending,
    rendering: regenerate.isPending,
    rescoring: false,
  });
  const canSave = hasUnsavedChanges && !save.isPending && !regenerate.isPending;
  useSaveShortcut(() => save.mutate(), canSave);
  const mod = useModKey();
```

- `PageHeader`: add `subtitle={<SaveStatusText status={status} />}` and rewrite
  the "No subtitle." comment to say the subtitle is the save-status line, not an
  identity line, so the three-identity-lines rule still holds.
- The primary button:

```tsx
                    <Button
                      onClick={() => save.mutate()}
                      disabled={!canSave}
                      title={`Save (${shortcutLabel(mod, "S")})`}
                      aria-keyshortcuts="Meta+S Control+S"
                    >
                      {save.isPending ? "Saving…" : "Save"}
                    </Button>
```

- First child of `StudioOverflowMenu` (before "Ask for changes…"):

```tsx
                      <DropdownMenuItem
                        disabled={hasUnsavedChanges || regenerate.isPending || save.isPending}
                        onClick={() => regenerate.mutate()}
                      >
                        <RefreshCw />
                        {regenerate.isPending
                          ? "Generating…"
                          : live.pdf_path
                            ? "Regenerate PDF"
                            : "Generate PDF"}
                      </DropdownMenuItem>
```

- `EditorShell`: add `previewStale={hasUnsavedChanges}`.

**Step 4: Run** the studio pins and `tests/test_kb_sync_frontend.py` → PASS;
tsc + lint clean.
**Step 5: Commit**
`git commit -m "feat(studio): base studio status line, Cmd/Ctrl+S and Regenerate PDF"`.

---

### Task 10: Tailored studio — status line, Cmd/Ctrl+S, no success toasts

**Files**
- Modify: `backend/tests/test_frontend_studio.py` (append)
- Modify: `frontend/components/resume-editor/tailored-resume-studio.tsx`

**Step 1: Append the failing pins**

```python
_TAILORED = _read("components/resume-editor/tailored-resume-studio.tsx")


def test_tailored_save_chain_fires_no_success_toasts():
    assert '"Saved. Rendering PDF…"' not in _TAILORED
    assert 'toast.success("PDF rendered")' not in _TAILORED
    # The chained re-score is silent; a manual Re-score still confirms, since
    # the score itself is not shown in the studio yet (Phase 2 chip).
    assert "if (opts?.announce)" in _TAILORED
    assert "rescore.mutate({ announce: true })" in _TAILORED


def test_tailored_studio_status_shortcut_and_stale_preview():
    assert "<SaveStatusText" in _TAILORED
    assert "useSaveShortcut(" in _TAILORED
    assert 'aria-keyshortcuts="Meta+S Control+S"' in _TAILORED
    assert "previewStale={unsaved}" in _TAILORED


def test_tailored_status_ignores_the_post_save_refetch_gap():
    # `dirty` still feeds the parent's adoption guard; the USER-facing signals
    # read `unsaved`, which forgets the gap before the remount.
    assert "savedSnapshot" in _TAILORED
    assert "dirty: unsaved" in _TAILORED
    assert "const canSave = unsaved && !busy;" in _TAILORED
    assert "onDirtyChange(dirty)" in _TAILORED
```

**Step 2: Run** → FAIL.

**Step 3: Implement**
- Same new imports as Task 9 (minus `RefreshCw`, already imported).
- `rescore`:

```tsx
  const rescore = useMutation({
    mutationFn: (_opts?: { announce?: boolean }) =>
      runAtsScoreTarget(jobId, "application", applicationId, "tailored"),
    onSuccess: (_data, opts) => {
      qc.invalidateQueries({ queryKey: ["ats-compare", applicationId] });
      qc.invalidateQueries({ queryKey: ["ats-scores", jobId] });
      // Only the manual Re-score confirms. The Save chain reports through the
      // header's status line, not a third toast.
      if (opts?.announce) toast.success("Tailored resume re-scored");
    },
    onError: (err: Error) => toast.error(err.message),
  });
```

- `render.onSuccess`: delete `toast.success("PDF rendered");`.
- `StudioEditor` props: `rescore: { mutate: (opts?: { announce?: boolean }) => void; isPending: boolean };`
- `save.onSuccess`: delete `toast.success("Saved. Rendering PDF…");`.
- The manual Re-score button: `onClick={() => rescore.mutate({ announce: true })}`.
- **The post-save gap.** `saveStatus` ranks dirty above rendering (Tasks 6–7
  review), and after our own Save lands `dirty` stays true until the
  `["application"]` refetch remounts this editor, because it still compares
  against the PRE-save server values. Without this, the header would flash and
  announce "Unsaved changes" while the PDF renders. Keep `dirty` exactly as it
  is for `onDirtyChange` (the parent's adoption guard depends on it) and for
  `useUnsavedChangesWarning`; derive `unsaved` for everything the user sees:

```tsx
  // What our own last Save sent, as adopted from its response. Between that
  // Save landing and the refetch that remounts this editor, `dirty` still
  // compares against the PRE-save server values; this keeps the status line,
  // Save and the stale strip from reporting the save we just made as unsaved.
  // An edit made after the Save differs from it and reads as unsaved at once.
  const sentData = useRef<ResumeData | null>(null);
  const [savedSnapshot, setSavedSnapshot] = useState<string | null>(null);
  const snapshotOf = (
    d: ResumeData,
    f: Partial<ResumeFormatting> | null,
    t: string | null,
  ) => JSON.stringify({ d, f: f ?? null, t });
  const unsaved =
    dirty &&
    snapshotOf(data, formatting, templateIdToApi(templateId)) !== savedSnapshot;
```

  In `save.mutationFn`, after validation: `sentData.current = data;`. In
  `save.onSuccess`, after adopting formatting and template:
  `setSavedSnapshot(snapshotOf(sentData.current ?? data, (result.formatting as Partial<ResumeFormatting> | null) ?? null, result.template_id ?? null));`
  (use the same null/default normalisation `templateIdToApi` produces, so an
  untouched template compares equal). Verify in Task 14 that a formatting-only
  save (which does not remount) settles to "All changes saved".

- After `const busy = …`:

```tsx
  const status = saveStatus({
    dirty: unsaved,
    saving: save.isPending,
    rendering: render.isPending,
    rescoring: rescore.isPending,
  });
  const canSave = unsaved && !busy;
  useSaveShortcut(() => save.mutate(), canSave);
  const mod = useModKey();
```

- `PageHeader` subtitle:

```tsx
              subtitle={
                <span className="inline-flex flex-wrap items-center gap-x-2">
                  <span>{jobLabel}</span>
                  <span aria-hidden="true">·</span>
                  <SaveStatusText status={status} />
                </span>
              }
```

- Save button: `disabled={!canSave}`, `title={`Save (${shortcutLabel(mod, "S")})`}`,
  `aria-keyshortcuts="Meta+S Control+S"`.
- `EditorShell`: add `previewStale={unsaved}`.

**Step 4: Run** the studio pins → PASS; tsc + lint clean.
**Step 5: Commit**
`git commit -m "feat(studio): tailored studio status line; Save fires no success toasts"`.

---

### Task 11: `PdfPagesPreview` — canvas and zoom presets

Used by both studios, the job page's Resume tab (`application-panel.tsx`) and
the template editor (`app/templates/[id]/page.tsx`); all of them gain it.

**Files**
- Modify: `backend/tests/test_frontend_studio.py` (append)
- Modify: `frontend/components/resume-editor/pdf-pages-preview.tsx`

**Step 1: Append the failing pins**

```python
_PREVIEW = _read("components/resume-editor/pdf-pages-preview.tsx")


def test_preview_offers_zoom_presets_as_a_labelled_group():
    assert 'role="group"' in _PREVIEW and 'aria-label="Zoom"' in _PREVIEW
    assert "PREVIEW_ZOOMS" in _PREVIEW and "aria-pressed" in _PREVIEW
    assert "bg-canvas" in _PREVIEW


# (Add `import re` to this file's imports here: Task 8 dropped it as unused.)
def test_preview_dpi_matches_the_backend_rasterizer():
    py = (_BACKEND / "app/services/pdf_preview.py").read_text()
    ts = _read("lib/studio.ts")
    backend_dpi = int(re.search(r"^DPI = (\d+)", py, re.M).group(1))
    frontend_dpi = int(re.search(r"export const PREVIEW_DPI = (\d+);", ts).group(1))
    assert backend_dpi == frontend_dpi
```

**Step 2: Run** → FAIL.

**Step 3: Implement**
- Imports: `useEffect`, `useState` from react; `cn`; from `@/lib/studio`:
  `actualSizeWidthPx`, `parseZoom`, `PREVIEW_ZOOMS`, `type PreviewZoom`.
- Module constants:

```tsx
const ZOOM_KEY = "pdfPreview.zoom";

const PAGE_CLASS: Record<PreviewZoom, string> = {
  // The long-standing default: the page fills the pane's width, capped.
  width: "w-full max-w-3xl",
  // Whole page in view. The studio is h-dvh; the preview header and padding
  // take about 6rem.
  page: "max-h-[calc(100dvh-6rem)] w-auto max-w-full",
  // Print size: width set inline from the PNG's natural width.
  actual: "max-w-none",
};
```

- In the component, before the query:

```tsx
  const [zoom, setZoom] = useState<PreviewZoom>("width");
  const [naturalWidth, setNaturalWidth] = useState<number | null>(null);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrating from localStorage after mount
    setZoom(parseZoom(window.localStorage.getItem(ZOOM_KEY)));
  }, []);
  const chooseZoom = (value: PreviewZoom) => {
    setZoom(value);
    window.localStorage.setItem(ZOOM_KEY, value);
  };
```

- The empty/error branch's wrapper gains `bg-canvas`.
- The scroller becomes `className="bg-canvas relative h-full overflow-auto p-4"`
  (`overflow-auto` so 100% can scroll sideways). Its first child:

```tsx
      <div className="sticky top-0 z-10 mb-2 flex justify-end">
        <div
          role="group"
          aria-label="Zoom"
          className="bg-background/90 inline-flex gap-0.5 rounded-md border p-0.5 shadow-sm backdrop-blur"
        >
          {PREVIEW_ZOOMS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={zoom === option.value}
              onClick={() => chooseZoom(option.value)}
              className={cn(
                "h-6 rounded px-2 text-xs transition-colors",
                zoom === option.value
                  ? "bg-secondary-container text-on-secondary-container font-medium"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
```

- Each page `<img>`: keep `key`, `src`, `alt`, the eslint comment; add

```tsx
          onLoad={
            i === 0
              ? (e) => setNaturalWidth(e.currentTarget.naturalWidth)
              : undefined
          }
          style={
            zoom === "actual" && naturalWidth
              ? { width: actualSizeWidthPx(naturalWidth) }
              : undefined
          }
          className={cn(
            "mx-auto mb-4 block rounded-[2px] bg-white shadow-lg ring-1 ring-black/5",
            PAGE_CLASS[zoom],
          )}
```

Leave the page-count pill as is. Update the render-error banner's copy: it
says "...and save again", but both studios' Save is dirty-gated now, so it
reads "Fix the content or template, then save or regenerate the PDF." 

**Step 4: Run** the studio pins → PASS; tsc + lint clean.
**Step 5: Commit**
`git commit -m "feat(studio): page canvas and zoom presets in the PDF preview"`.

---

### Task 12: Section order is buttons only (drag removed)

`formatting-panel.tsx` added HTML5 drag to the section-order list while its own
comment and the conventions say up/down buttons, not drag-and-drop. The
convention wins (WCAG 2.5.7 is met by the buttons; drag added a second,
pointer-only path and a `cursor-grab` promise on every row).

**Files**
- Modify: `backend/tests/test_frontend_studio.py` (append)
- Modify: `frontend/components/resume-editor/formatting-panel.tsx`

**Step 1: Append** `def test_section_order_has_no_drag_path(): assert "draggable" not in _read("components/resume-editor/formatting-panel.tsx")` → run → FAIL.

**Step 3: Implement:** on the `<li>` delete `draggable`, `onDragStart`,
`onDragOver`, `onDrop`, and the `!disabled && "cursor-grab active:cursor-grabbing"`
class; delete `const sectionDragFrom = useRef<number | null>(null);` (line ~82);
drop `useRef` from the React import if nothing else uses it (`grep -n useRef`).

**Step 4: Run** → PASS; tsc + lint clean.
**Step 5: Commit** `git commit -m "fix(studio): section order reorders by buttons only, per convention"`.

---

### Task 13: Docs

**Files**
- Modify: `docs/frontend-conventions.md`
- Check: `SYSTEM.md` (expected: no change; §5 step 7's "Save chains render →
  re-score" still holds)

Edits to `docs/frontend-conventions.md`, present tense, no dates (the gate
fails a `(YYYY-MM-DD` in reference-tier files):
1. First bullet: primary is `oklch(0.48 0.17 259)` light (M3 tone 40).
2. New bullet after it: **Colour roles are M3's, pinned for contrast.** FAB →
   primary container (`fab` variant); tonal buttons, tonal badges and the nav
   active indicator → secondary container; hover is the 8% state-layer token;
   `--canvas` sits behind rendered pages. `test_frontend_color_roles.py`
   computes every pair ≥ 4.5:1; light `bg-primary/20` under blue text is
   refused (dark only).
3. Sidebar bullet: the create action is the M3 extended FAB (`fab`, 16px
   corners), the one New application per screen; the Applications header shows
   its own button only while the sidebar is hidden (`useSidebarHidden`); nav
   links carry `aria-current` via `lib/nav.ts`; active is secondary container +
   semibold + primary icon, hover stays neutral.
4. "Derived setup guidance": the empty tracker places its empty-state action
   ABOVE `GettingStartedCard`; the API-key and import steps carry a Required
   badge; `/new` names a missing key before the paste; the Score tab offers
   the import when no base resume exists.
5. New bullet, **The studio is honest about its page**: `SaveStatusText` in the
   header subtitle (`role="status"`) is how a studio Save reports success, not
   a toast; `EditorShell previewStale` marks the preview as the last save;
   Cmd/Ctrl+S via `useSaveShortcut` (same gate as the button); the divider is an
   APG window splitter; `PdfPagesPreview` has Fit width / Fit page / 100% on the
   canvas; base Save is dirty-gated with ⋯ Regenerate PDF as the retry.
6. "Two save models": add that explicit studio Saves report through the status
   line; errors still toast.
7. Reordering bullet: the formatting panel's section order is buttons only.
8. Facts that changed during Tasks 1–5 (from the reviews):
   - The FAB rests flat (M3 rail FAB elevation 0) and hover raises it one
     level; both sidebar toggles carry `aria-keyshortcuts="Meta+B Control+B"`.
   - `["setup-status"]` has THREE readers (Profile strip, Getting started,
     `/new`); Profile saves AND Settings model/key saves invalidate it.
   - Selected tonal toggles show a leading Check (health filters also carry
     `aria-pressed`): the secondary-container fill alone is too faint a signal.
   - The empty tracker keeps a ghost New application in its empty state on
     purpose (NN/g: the pathway is a control), beside the FAB or header button.
   - SYSTEM.md §5 step 4 (Score): with no base resume the tab offers the import.
   - One saved zoom (`pdfPreview.zoom`) applies to all four PdfPagesPreview
     surfaces; Fit page measures the PREVIEW (container units), not the
     viewport; the zoom row sits above the scroller so it never scrolls away.
   - Studio ⋯ menu: `w-auto min-w-56 max-w-(--available-width) wrap-anywhere`.
   - Tailored studio: user-facing signals read `unsaved`; `dirty` stays the
     adoption guard's input. Base studio: rename re-syncs the saved baseline.

Run: `python3 scripts/check_system_md.py` → PASS.
Commit: `git commit -m "docs(conventions): colour roles, sidebar FAB and the honest studio"`.

---

### Task 14: Verification

1. **Gates**
   - `cd frontend && npx tsc --noEmit && npm run lint && npm run build`
   - `cd frontend && node --test lib/*.test.ts`
   - `cd backend && python3 -m pytest tests/ mcp_server/tests/ -q`
   - `cd backend && python3 -m ruff check .` (CI runs it; Task 8's review caught
     an unused import and an E741 in the new pins)
   - `python3 scripts/check_system_md.py`
   - Slop ratchet, naming BOTH surfaces:
     `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend`
     and `… check backend` (the new pins live in `backend/tests/`). Re-baseline
     only with a reason string.
2. **Fresh stack** (SYSTEM.md §9: never the compose images). Backend: uvicorn
   on a free port with `DATABASE_URL=sqlite:///<scratchpad>/verify.sqlite3`
   and every `*_DIR` under the scratchpad (startup runs alembic);
   `ALLOWED_WEB_ORIGINS` naming the frontend port. Frontend: a gitignored
   `.claude/launch.json` entry running
   `API_PROXY_BACKEND=http://127.0.0.1:<port> npx next dev -p 3100`, started
   with `preview_start`. A fresh stack has no API key and no base resume, which
   is exactly the first-run state to check. Create a base resume without an
   LLM through the Base Resumes gallery's Create (see
   `new-base-resume-dialog.tsx`).
3. **Browser checklist** (light AND dark; 1280px AND 768px):
   - Sidebar: the active item is visibly tinted and its link has
     `aria-current="page"` (`read_page`); hover looks different from active;
     New application reads as the FAB.
   - Applications, empty: the empty state comes before Getting started; API key
     and Import show Required; no header button while the sidebar shows;
     collapse the sidebar (⌘/Ctrl+B) and the header button appears.
   - `/new` with no key: the notice shows and Extract is disabled.
   - A job with no base resumes: the Score tab offers Import resumes.
   - Base studio: edit a field → header "Unsaved changes", amber strip, dimmed
     page; ⌘/Ctrl+S → "Saving…" → "All changes saved", the page updates, no
     success toast; Save disabled when clean; ⋯ Regenerate PDF works; Tab to
     the divider, arrows resize it, Home/End jump; zoom Fit page / 100%
     persists across reload; the formatting panel's section order cannot be
     dragged. Press ⌘/Ctrl+S inside raw-JSON mode too: no browser save dialog.
   - Tailored studio: one Save → no success toasts; the status line walks
     Saving → Rendering PDF → Re-scoring → All changes saved; the manual
     Re-score still toasts.
   - devtools: confirm tonal-button text ≥ 4.5:1 and the primary button colour
     `#1358bb` (light).
   - The flat FAB (no resting shadow since Task 2's review) does not blend into
     the light sidebar: fill is only ~1.25:1 there, so it relies on its label.
   - Selected health-report filters and the pressed Review toggle show a check.
   - Score tab import: after importing, focus should not drop to `<body>` and
     no frame of "No ATS scores yet" should flash (review minors #3 and #5).
   - Cmd/Ctrl+S inside a section-rename field or a skill chip input saves the
     typed draft; if the field unmounts on blur, focus lands somewhere sensible.
   - Template editor at 1280x800: since Task 11 the preview scrolls in its own
     pane; re-measure whether the page still scrolls (~962px before) and
     whether the collapsed "Show PDF preview" edge button clears the scrollbar.
   - Empty tracker: the FAB (or header button) plus the ghost empty-state
     button is deliberate (NN/g: the empty state's pathway is a control).
4. Stop every server you started. Record results below.

Then run the goal critique: read the Goal Card, and check the landed branch
against it (not against this plan). Default to approve; a finding names the
Goal Card line it violates.

---

## Out of scope — next plans

- **Phase 2:** draft-preview endpoint + Refresh (Cmd/Ctrl+Enter), then opt-in
  auto-refresh after timing a multi-page résumé in Docker; Formatting as a
  right-hand inspector at ≥1200px; the job-fit chip in the tailored studio.
- **Phase 3:** document-level undo/redo.
- **Earlier review items:** KB "Profile" tab → "Basics"; server-side
  `category_label` for MCP and chat; analytics role labels and series cap;
  copy nits; Referrals form on demand; template Sample label; the placeholder
  convention (GOV.UK forbids example placeholders; the conventions doc cites
  GOV.UK for allowing them).
- **HIGH PRIORITY, found in Tasks 9–10 review (pre-existing):** the tailored
  studio's external-edit guard (SYSTEM.md §12). After a Save that leaves
  `customized_json` unchanged (formatting/template only) `adoptNextServerKey`
  is never consumed, so a later foreign edit is adopted banner-free even over
  unsaved edits; an edit typed in the post-save gap is lost on the remount;
  focus drops to `<body>` on remount (and the status live region remounts).
  Fix direction: `onSaved(savedKey)` and adopt banner-free only when
  `customizedKey === savedKey`.
- **Found by reviews, pre-existing, not this plan's to fix:** the light
  `--ring` is ~2.5:1 on `--canvas` (WCAG 1.4.11 borderline); `text-destructive`
  on `bg-destructive/10` is ~3.1–3.6:1 (render-error banner, template compile
  error); the divider has no single-pointer alternative to dragging beyond
  hide/show (WCAG 2.5.7); the drag scales by `window.innerWidth` rather than the
  shell's width, has no `pointercancel`, and writes localStorage on every move;
  moving a section down and back up leaves "Unsaved changes" (the first move
  stores an explicit `section_order` where `null` meant the template's order);
  the preview paints one frame at Fit width before a stored zoom applies (the
  same read-after-mount pattern as EditorShell; `useSyncExternalStore` would fix
  both);
  the setup pill and top-skills chip have no dark-mode hover.
- **Sidebar state across reloads:** needs a server read (a cookie in the root
  layout) that conflicts with the desktop shell's static UI, or a pre-paint
  script. Decide with the desktop shell.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|
| 1 (review) | Task 1 only | Hardened colour pins (fail loudly on unparsed tokens, every tint above ceiling, hover read from CSS); chroma nudged into sRGB; selected tonal toggles (health filters, Review changes) show a Check + `aria-pressed`; conventions primary value | Task 1 made those toggles' "on" state fainter than "off": fixing a regression it introduced (Principles: accessibility) |
| 2 | Plan code only | Comment above `sidebarMenuButtonVariants` on why the `data-active:hover:` pairing must stay | Unpinned-by-intent class a cleanup would delete |
| 2 (review) | `data-active:hover:bg-…` only; substring pins; `useModKey` via effect; FAB `shadow-sm` at rest + `shadow-md` on /new | Adds `data-active:hover:text-on-secondary-container`; exact-token pins; `useModKey` via `useSyncExternalStore` (the `use-mobile.ts` pattern); `aria-keyshortcuts` on both sidebar toggles; "Toggle sidebar" sentence case; FAB rests flat, hover +1 (M3 rail FAB elevation 0) | Review findings; accessibility and conventions |
| 4 | Rescore as soon as ["base-resumes"] goes none → some | Rescore waits until the import dialog CLOSES; the prompt stays mounted while it is open | The plan's version swapped the prompt for a skeleton and unmounted the dialog mid-report, where the user confirms each new resume's role (Principles: accessibility; don't break a flow) |
| 5 | `/new` reuses ["setup-status"] and "a key saved in Settings clears this" | `refetchOnMount: "always"`, like the two other readers | Settings does not invalidate ["setup-status"]; Extract would stay disabled up to 30 s after adding a key (Goal: no first-run dead end) |
| 8 | Divider class as written; `useState(PREVIEW_PCT.default)` | Adds `relative z-10` (with a comment); `useState<number>(…)` | The opaque, relative preview pane painted over half the focus ring (seen in the browser); `as const` inferred the literal 45 |
| 11 | Zoom group sticky inside the scroller | A normal row above the scroller; `backdrop-blur` dropped | At 100% scrolled right only 56px of a sticky group stayed visible; clipped at 375px (browser-checked) |
| 11 | Fit page = `max-h-[calc(100dvh-6rem)]` | `max-h-[100cqh]` (the preview's own height, container units) + a pin that fails on the plan's value | The dvh value overflowed the job page's 638px box and the studio pane with Formatting open |
| 11 | ⋯ menu `max-w-(--available-width)` | Also `wrap-anywhere` | Slugs are `[a-z0-9_]`, unbreakable; capped width alone cut the slug off at 375px |
| 12 (review) | Section-order buttons as they were (18×18) | Shared ghost `icon-xs` (24px, 44px coarse) | WCAG 2.5.8; since Task 12 they are the only pointer reorder path (Principles: accessibility) |
| 11 (review) | Drop the zoom group's background | Keeps a solid `bg-background` (shadow and translucency dropped) | Unselected muted labels are 4.56:1 on the bare canvas vs 5.48:1 on background |
| 9 | Plan pins only | `test_kb_sync_frontend.py` now slices from `<StudioToolbar` | Its first-`status={` anchor matched the new `<SaveStatusText status={status} />` in the header; same assertion, sturdier anchor |
| 10 | `mutationFn: (_opts?) => …`, chained `rescore.mutate()` | `mutationFn` takes no argument; the variables type lives on `onSuccess`; the chain passes `{ announce: false }` | The plan's form failed tsc and added a lint warning (`_` args are not ignored here) |
| 6–7 (fix) | `isSaveShortcut` accepts `code === "KeyS"` | Physical-key fallback only when `key` is not a single Latin letter | Colemak/Dvorak put other letters on KeyS: the planner's version made Cmd+R / Cmd+O save (proven by a failing test) |
| 6–7 (review) | Status order saving > rendering > rescoring > dirty; arrow keys step from any value; chord handled everywhere | Order saving > dirty > rendering > rescoring; keys snap to the 5% grid; `code === "KeyS"` fallback; the shortcut ignores dialogs, repeats and IME composition, and blurs the focused field first so blur-committed drafts save like a click; dirty text amber-800 + nowrap | Goal: "always see whether your work is saved"; Principles: accessibility. Planner amended Task 8 (rounded aria value, `aria-valuetext`, `aria-controls`) and Task 10 (`unsaved` vs `dirty`, the post-save gap) to match |
| 1 | globals.css comment: hover tokens work because "custom properties resolve per element" | Comment says they work because `.dark` sits on `<html>`, the same element `:root` matches; a `.dark` on a subtree would keep the light hover | Accuracy of a comment the next agent will trust (Principles: conventions win); code unchanged |

## Gate results

| When | Gate | Result |
|---|---|---|
| Baseline | `npx tsc --noEmit` / `npm run lint` | clean / 0 errors, 5 pre-existing warnings |
| Baseline | `pytest tests/ mcp_server/tests/ -q` (before Task 1) | 4378 passed, 2 skipped (232 s) |
| Task 1 | `test_frontend_color_roles.py` | 10 failed → 11 passed; tsc clean; lint unchanged |
| Task 1 fix | colour-role pins | 12 passed (fail-first shown for parse, tint scan, hover mix, toggle check) |
| Task 2 | sidebar pins + nav/shortcuts unit tests | exact-token pins pass; node 6/6; full backend 4394 passed |
| Tasks 3–5 | first-run + query-error pins | 47 passed after review fixes; full backend 4399 passed |
| Tasks 6–7 | `node --test lib/*.test.ts` | 39/39 after review fixes |
| Task 8 | studio pins | 3 pass; ruff clean on new pins after review; divider browser-checked on a throwaway stack |
| Tasks 9–10 | studio + kb-sync + colour pins | 36 → 42 passed after review; full backend 4411 passed / 2 skipped; both studios browser-checked |
| Tasks 11–12 | frontend pin set | 157 passed after review; ruff/tsc/lint clean; browser-checked 1280/768/375, light+dark |
