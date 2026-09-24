> **Appendix C (Settings and Profile) to the 2026-09-23 UX IA and copy plan.** This is a research brief. It
> was written read-only against `8cac7cf9` (branch `claude/ux-ia-copy-plan`, which equals local main). Each
> task in the plan names the section it uses. Where this appendix offers options, the plan's "Owner
> decisions" section is binding. Line numbers drift, so re-locate each one before editing.

# Phase C: Settings and Profile get tabs, a header status, a split Models card and one rhythm

Worktree: `.claude/worktrees/ux-next-plan-continue-03c4a1`. All paths are relative to its root, and all
line numbers are at `8cac7cf9`. Sources:
- the owner decisions quoted in the plan (tabs, status in the header, the Models split, the spacing pass);
- `docs/frontend-conventions.md`;
- SYSTEM.md §11 item 31;
- the code.

**Goal Card line this serves:** Settings and Profile read as a small set of places, not one long scroll.
- Every old link still lands on its card.
- Unsaved text survives a tab switch, and the leave guard still covers it.
- A card's save state sits next to its title.
- WCAG 2.2 AA holds, focus never drops to `<body>`, and no new dependencies are added.

## 0. Read this first

**Nine findings change or sharpen the owner's directions:**

1. **The leave guard's Back/Forward machine treats a `?tab=` change as leaving the page. This has to be
   fixed before any tab writes the URL.** `lib/leave-guard.ts` compares pages by full URL (pathname plus
   search):
   - `stampAfterWrite` at :145 keeps the sentinel flag only while `before.url === written.url`;
   - `arrive` at :312 and `judge` at :331 test `e.url === t.page`, and `judge` at :358 tests `above.url === e.url`.

   So a dirty Persona, followed by a tab switch that rewrites the URL, loses the sentinel. After a save,
   Back becomes a dead press. While the page is still dirty, Back asks about "leaving" a page it does not
   leave, and **Leave** targets the editor itself.

   I verified this on a scratchpad copy. Two new history tests fail against the current machine and pass
   once page identity is the PATHNAME (C4); all 38 existing history tests still pass.

   Pathname identity is the true semantic. Next keys a page's React state without its search params:
   `layout-router.js:549`, `createRouterCacheKey(activeSegment, true) // no search params`. A search or
   hash change therefore keeps the page, and every unsaved edit on it, mounted.
2. **`keepMounted` is required. Today's "visited panels stay mounted" is a Base UI quirk, not a
   contract.** `TabsPanel.js` (`@base-ui/react` 1.4.1) does two things:
   - It returns `null` for a panel that was never opened (`shouldRender = keepMounted || mounted`).
   - It keeps a visited panel only because `useOpenChangeComplete` never fires with no transition. The
     `[&[inert]]:hidden` comment in `tabs.tsx:101-114` records this.

   With `keepMounted` on every settings panel:
   - the page mounts exactly what it mounts today, so there are no extra requests;
   - deep-link anchors exist from the first client render;
   - no editor ever unmounts.

   `useLeaveGuard` (`hooks/use-leave-guard.ts:13-23`) registers in an effect keyed on `when`. An inert,
   `display:none` component still runs its effects, so a dirty Persona on a hidden tab stays registered.
   GuardedLink asks, and `beforeunload` warns.
3. **Write the tab with native `history.replaceState`, not `router.replace`.** Next 16.3 patches
   `history.replaceState` (`app-router.js:271-283`). A call without `__NA` gets Next's internal state
   copied in, and it dispatches `ACTION_RESTORE`. `useSearchParams`/`usePathname` follow, and there is no
   RSC fetch and no new history entry.

   `/analytics` uses `router.replace` (`app/analytics/page.tsx:63-69`). That is a server round trip per
   tab click, and the tab only flips once the navigation commits. The job page writes nothing back
   (`app/jobs/[id]/page.tsx:117-121` only seeds `useState` from `?tab=`).
4. **The hash cannot be read during SSR, so internal links must carry `?tab=`.** Otherwise the server
   renders the default tab and the client flips it after hydration. A hash-only link (old bookmarks,
   docs, `/profile#autofill`) still works: the tab hook reads the hash through `useSyncExternalStore`,
   whose server snapshot is `""`. That is the same hydration primitive `appearance-section.tsx:38-42`
   uses.

   `useFocusSection` must also wait until its target is *shown*, not just *present*. With `keepMounted`,
   the card exists inside a `display:none` panel. `scrollIntoView` on it is a no-op, and today's poll
   would ring an invisible card and stop.
5. **The header status can be a portal with no lifted state.** `SettingCard` renders shadcn's `CardAction`
   (`components/ui/card.tsx:61-72`; `chart-kit.tsx:99` is a precedent) with `ref={setSlot}`, and
   provides the node through context. The body renders `<SettingCardAction>` into it with `createPortal`.
   - The editor's state stays in the body.
   - In the DOM, the status sits in the header, after the title and description, which is the right
     reading order.

   I probed it with `npx eslint --stdin` (nothing written): 0 errors under the React Compiler rules. A
   CSS-grid move of a body element is worse. Visually it is in the header, but a screen reader reads it
   after the fields.
6. **One `TabsList` fix covers three §11 item 31 symptoms.** The row gets `max-w-full`,
   `overflow-x-auto` and `justify-center-safe` in the primitive. That fixes:
   - the job page's Q&A tab running off-screen at 375;
   - the New base résumé dialog's tab row not shrinking;
   - the new five-tab Settings row, which needs about 480px against 295px available at 375 and 400px at
     768.

   Base UI already scrolls the active tab into view on arrow keys (`internals/composite/root/
   useCompositeRoot.js:45`, `scrollIntoViewIfNeeded`).
7. **I found defects inside this scope. Fix each in the section that already touches its file:**
   - **Prompts.** The Advanced disclosure unmounts its prompt editors on collapse
     (`prompts-section.tsx:89`, `{advancedOpen && …}`). That drops their typed text and their leave-guard
     registration. Neither prompt toggle carries `aria-expanded` (:77-88, :157-175).
   - **Buttons that disable themselves while their own request runs drop focus to `<body>`.** These lack
     `focusableWhenDisabled`:
     - Persona's "Draft from my career" (`persona-section.tsx:124-134`);
     - every model's Test (`llm-endpoint.tsx:200-211`, whose label is replaced by a bare spinner, so the
       button has no accessible name at all while it probes);
     - both Sync buttons (`model-catalog-panel.tsx:107-132`);
     - every catalog Remove (:208-217).
   - **Model catalog.** A removed row takes its focused Remove button with it. `AutosaveStatus` does not
     reserve width, although its docstring says it does (:21-22). Beside a title, that re-wraps the
     description on every save.
   - **A fieldset cannot be a grid container here.** The rendered `<legend>` is not a grid item, so
     `gap` never separates it from the first field. Autofill's fieldsets must stay block flow
     (`space-y-*`).
8. **Two backend messages send the user to the wrong page.**
   - `services/knockout.py:63,81,125` says to set work authorization "in Settings".
   - `services/job_search_brief.py:80` says to correct "the autofill profile in Settings".

   Both live on Profile, in the Autofill tab. Three more messages name "Settings → Models" for the API
   key (`llm.py:93,96,456`, `main.py:87`). After this phase that becomes Settings → AI & models.
9. **Page subtitle: keep ONE per page, not one per tab.** A per-tab subtitle rewrites the header on every
   tab click, which is a layout shift above the tab row. The tab labels already say what each panel
   holds, and every card keeps its description. Settings' subtitle becomes "Models, tailoring, connected
   agents and appearance." Profile keeps its subtitle.

**Order and lanes:**
- **Lane A** is C1 to C5: the tab table, pages, deep links, leave guard and tab row. It owns
  `app/settings`, `app/profile`, `lib/`, `components/ui/tabs.tsx`, `components/setup/` and the new
  `components/settings/settings-tabs.tsx`.
- **Lane B** is C6 to C8: the header slot, the Models split and the rhythm. It owns
  `components/settings/*` except `settings-tabs.tsx`.

The two lanes touch disjoint files, except for `backend/tests/test_frontend_settings_pages.py`. Give each
lane its own section of that file, or two files. **C9** (copy and docs) goes last.

## Global constraints (read before any step)

- **Lint (`npm run lint`) runs the React Compiler rules at error level**: `react-hooks/refs`,
  `set-state-in-effect` and `set-state-in-render`. I piped each new hook shape in this appendix through
  `npx eslint --stdin --stdin-filename components/settings/__probe.tsx` (nothing written), and all three
  report 0 errors:
  - `useSettingsTab`, which uses `useSyncExternalStore` plus the "adjust state while rendering on change"
    pattern and a layout effect;
  - the `SettingCard` portal slot, where a callback ref sets state;
  - the catalog's remove-then-refocus effect.
- **`lib/*.ts` has no `@/` imports.** The two new lib files import nothing, so `node --test` loads them.
  Node tests are **not in CI**. Every `lib/*.ts` behaviour here also gets a pytest source pin. I ran all
  node tests quoted below against scratchpad copies with Node 26.9:
  - `settings-tabs` 4/4;
  - `model-catalog` 3/3;
  - `leave-guard-history` 43/43 with the change, 41/43 without it;
  - `focus` 20/20.

  `tsc --strict` is clean on the two new lib files.
- **No new dependency.** `justify-center-safe` and `@container` queries are Tailwind 4.2.4 core
  (`node_modules/tailwindcss/package.json`). There is no `no-scrollbar` utility in `globals.css`
  (`sidebar.tsx:388`'s class is inert), so the hidden scrollbar is written with arbitrary properties.
- **Links:** `GuardedLink` stays the only importer of `next/link` (`test_frontend_leave_guard.py`). The tab
  switch and in-page jumps are not links (C3, C4).
- **Focus:** nothing drops to `<body>`. Every button that disables itself while its own request runs is
  `focusableWhenDisabled` and dimmed with `data-disabled:pointer-events-none data-disabled:opacity-50`.
  This is the `test_a_button_that_disables_itself_while_it_works_keeps_focus` shape.
- **`SettingCard` stays the one card shell.** Appearance stays the one exemption, because it fetches
  nothing.
- **SYSTEM.md is at the cap (1000 lines).** This phase is net-negative there: C5 deletes two clauses of §11
  item 31. Rules go into `docs/frontend-conventions.md`. Run `python3 scripts/check_system_md.py`.
- **Ratchets:**
  - Run `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend` and `check
    backend`, and name each surface in the claim.
  - Measure frontend duplication before the phase and quote both numbers. The shared `SettingsTabs`,
    `SwitchRow` and `RemoveButton` exist so the new code adds no clones.
- **Tests:**
  - Pins: `cd backend && python3 -m pytest tests/test_frontend_*.py -q`, then the full suite, `pytest
    tests/ mcp_server/tests/ -q`.
  - Node: `cd frontend && node --test lib/*.test.ts`.

---

## C1: the tab table (`lib/settings-tabs.ts`, new)

### Why a table

Deep-link anchors are card ids (`SettingCard id=`) and ids inside a card (the `autofill-<group>`
fieldsets at `autofill-section.tsx:724`). The tab that holds an anchor has to be known in three places:
- during render (the hash landing, C2);
- when building a link (C3);
- in a pin (so a card moved between panels cannot silently break a link).

A DOM lookup (`closest('[role=tabpanel]')`) cannot answer the first of those. The ids inside a card body
only mount after the card's queries resolve (`setting-card.tsx:104-108`), and nothing can read the DOM
during render. So the answer is a pure table, plus a prefix rule for ids inside a card.

### New file: `frontend/lib/settings-tabs.ts`

```ts
/**
 * The tabs on /settings and /profile, and which tab holds each deep-link anchor
 * (docs/frontend-conventions.md, "Settings vs Profile"). No imports: `node --test`
 * loads this file as it is (settings-tabs.test.ts).
 *
 * The FIRST tab of each page is its default, and its URL carries no `?tab=`.
 * `anchors` lists every card id a panel renders (a pin checks the pages against
 * it); ids INSIDE a card resolve by prefix (`autofill-work_auth`, the fieldsets
 * setup-steps.ts and the job knock-out card aim at).
 */
export type SettingsPage = "settings" | "profile";

export type SettingsTab = {
  value: string;
  label: string;
  anchors: readonly string[];
};

export const SETTINGS_TABS = [
  {
    value: "models",
    label: "AI & models",
    anchors: ["api-keys", "models", "model-catalog", "custom-endpoint", "prompts"],
  },
  { value: "tailoring", label: "Tailoring", anchors: ["quick-tailor"] },
  // "mcp" is reserved for the MCP explainer card (a sibling appendix designs it).
  { value: "agents", label: "Connected agents", anchors: ["mcp", "agent-hints", "auto-apply"] },
  { value: "appearance", label: "Appearance", anchors: ["appearance"] },
  { value: "about", label: "About", anchors: ["about"] },
] as const satisfies readonly SettingsTab[];

export const PROFILE_TABS = [
  { value: "you", label: "About you", anchors: ["persona", "market", "job-preferences"] },
  { value: "autofill", label: "Autofill", anchors: ["autofill"] },
] as const satisfies readonly SettingsTab[];

const TABS: Record<SettingsPage, readonly SettingsTab[]> = {
  settings: SETTINGS_TABS,
  profile: PROFILE_TABS,
};

/** [id prefix, tab]: ids inside a card that no table row names. */
const PREFIXES: Record<SettingsPage, readonly (readonly [string, string])[]> = {
  settings: [],
  profile: [["autofill-", "autofill"]],
};

export function tabsFor(page: SettingsPage): readonly SettingsTab[] {
  return TABS[page];
}

export function defaultTab(page: SettingsPage): string {
  return TABS[page][0].value;
}

/** `?tab=` as the page reads it: absent, repeated or unknown is the default tab. */
export function parseTab(
  page: SettingsPage,
  raw: string | readonly string[] | null | undefined,
): string {
  const value = typeof raw === "string" ? raw : raw?.[0];
  return TABS[page].some((tab) => tab.value === value) ? (value as string) : defaultTab(page);
}

/** The tab that renders `anchor`, or null when no tab does (`#main-content`, the skip link). */
export function tabForAnchor(page: SettingsPage, anchor: string): string | null {
  if (!anchor) return null;
  const exact = TABS[page].find((tab) => tab.anchors.includes(anchor));
  if (exact) return exact.value;
  const prefixed = PREFIXES[page].find(([prefix]) => anchor.startsWith(prefix));
  return prefixed ? prefixed[1] : null;
}

/** `/profile?tab=autofill#autofill-eeo`; the default tab writes no `?tab=`. */
export function tabHref(page: SettingsPage, tab: string, anchor?: string): string {
  const query = tab === defaultTab(page) ? "" : `?tab=${tab}`;
  return `/${page}${query}${anchor ? `#${anchor}` : ""}`;
}

/** A deep link to `anchor` on `home`: settings and profile name the tab, other routes are `home#anchor`. */
export function anchorHref(home: string, anchor: string): string {
  const page: SettingsPage | null =
    home === "/settings" ? "settings" : home === "/profile" ? "profile" : null;
  if (page === null) return `${home}#${anchor}`;
  return tabHref(page, tabForAnchor(page, anchor) ?? defaultTab(page), anchor);
}
```

The slugs are short and stable, and are never shown to the user: `models`, `tailoring`, `agents`,
`appearance`, `about` for Settings, and `you`, `autofill` for Profile. The default tabs are `models` and
`you`, because those are what a new install needs first. That ordering carries over from the page's own
docstring (`app/settings/page.tsx:19-27`).

### New file: `frontend/lib/settings-tabs.test.ts` (verified 4/4)

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  PROFILE_TABS,
  SETTINGS_TABS,
  anchorHref,
  parseTab,
  tabForAnchor,
  tabHref,
} from "./settings-tabs.ts";

test("an absent, repeated or unknown ?tab= reads as the page's first tab", () => {
  assert.equal(parseTab("settings", undefined), "models");
  assert.equal(parseTab("settings", "nope"), "models");
  assert.equal(parseTab("settings", "agents"), "agents");
  assert.equal(parseTab("profile", ["autofill", "you"]), "autofill");
  assert.equal(parseTab("profile", null), "you");
});

test("every anchor belongs to exactly one tab", () => {
  for (const tabs of [SETTINGS_TABS, PROFILE_TABS]) {
    const all = tabs.flatMap((tab) => [...tab.anchors]);
    assert.equal(new Set(all).size, all.length);
  }
});

test("a card id resolves to its tab, an id inside the autofill card by prefix", () => {
  assert.equal(tabForAnchor("settings", "api-keys"), "models");
  assert.equal(tabForAnchor("settings", "agent-hints"), "agents");
  assert.equal(tabForAnchor("profile", "autofill"), "autofill");
  assert.equal(tabForAnchor("profile", "autofill-work_auth"), "autofill");
  assert.equal(tabForAnchor("profile", "persona"), "you");
  assert.equal(tabForAnchor("profile", "main-content"), null);
  assert.equal(tabForAnchor("settings", ""), null);
});

test("hrefs name the tab only when it is not the default", () => {
  assert.equal(tabHref("settings", "models"), "/settings");
  assert.equal(tabHref("settings", "about"), "/settings?tab=about");
  assert.equal(tabHref("profile", "autofill", "autofill-eeo"), "/profile?tab=autofill#autofill-eeo");
  assert.equal(anchorHref("/settings", "api-keys"), "/settings#api-keys");
  assert.equal(anchorHref("/settings", "agent-hints"), "/settings?tab=agents#agent-hints");
  assert.equal(anchorHref("/profile", "job-preferences"), "/profile#job-preferences");
  assert.equal(anchorHref("/profile", "autofill-work_auth"), "/profile?tab=autofill#autofill-work_auth");
  assert.equal(anchorHref("/career", "kb-entities"), "/career#kb-entities");
});
```

### Pins (new file `backend/tests/test_frontend_settings_pages.py`, section "Tabs")

```python
"""Pins for the Settings and Profile tabs, header status, Models split and rhythm
(2026-09-23 UX IA plan, Appendix C). Source pins: CI does not run the node tests in
frontend/lib/settings-tabs.test.ts or model-catalog.test.ts."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


_TABS_LIB = _read("lib/settings-tabs.ts")
_TAB_ROW = re.compile(r'\{\s*value: "(\w+)",\s*label: "[^"]*",\s*anchors: \[([^\]]*)\]')


def _tab_table(name: str) -> dict[str, set[str]]:
    start = _TABS_LIB.index(f"export const {name} = [")
    block = _TABS_LIB[start : _TABS_LIB.index("] as const", start)]
    return {v: set(re.findall(r'"([\w-]+)"', a)) for v, a in _TAB_ROW.findall(block)}


def test_the_tab_table_is_node_loadable_and_resolves_card_bodies_by_prefix():
    assert "import " not in _TABS_LIB  # node --test loads it bare
    assert '["autofill-", "autofill"]' in _TABS_LIB
    # The default tab's URL carries no ?tab= (the analytics precedent).
    assert 'tab === defaultTab(page) ? ""' in _TABS_LIB
    assert list(_tab_table("SETTINGS_TABS")) == ["models", "tailoring", "agents", "appearance", "about"]
    assert list(_tab_table("PROFILE_TABS")) == ["you", "autofill"]
```

The pin that checks the tab table against the pages is in C2. It needs the page code.

### Risks
- Adding a card without adding its id to the table breaks nothing at runtime, because the tab still
  renders it. But a deep link to it would open the default tab. The C2 pin makes that a test failure.
- `"mcp"` is reserved before its card exists. The C2 pin is a subset check (`ids <= anchors`), so an
  unused reservation passes.

---

## C2: the tab state and the two pages

### Current code

- `app/settings/page.tsx:28-64` renders eight cards in one `PageShell` column and calls
  `useFocusSection()`. The subtitle is "API keys, models, agent behaviour, and appearance." (:35).
- `app/profile/page.tsx:17-58` renders `SetupStatusStrip` (or its `LoadErrorState`, :32-45), then
  Persona, Market, Job preferences and Autofill.
- The job workspace, the pattern the owner named, is `app/jobs/[id]/page.tsx`:
  - `JOB_TABS` at :58-59;
  - `JobTabsList` at :61-87;
  - `?tab=` read through the page's `searchParams` prop and `use()` at :104-121;
  - a controlled `<Tabs value={tab} onValueChange=…>` at :455-458;
  - `TabsContent` with `className="mt-0 space-y-4"` at :482-517.

  It never writes the URL back. Its keyboard model is Base UI's: manual activation (`activateOnFocus =
  false`, `tabs/list/TabsList.js:25`), looping arrows (`loopFocus = true`), Home/End, and the open panel as
  a tab stop.

### New file: `frontend/components/settings/settings-tabs.tsx`

```tsx
"use client";

import {
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { focusIfStranded } from "@/lib/focus";
import {
  parseTab,
  tabForAnchor,
  tabHref,
  tabsFor,
  type SettingsPage,
} from "@/lib/settings-tabs";

function subscribeToLocation(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  window.addEventListener("popstate", onChange);
  return () => {
    window.removeEventListener("hashchange", onChange);
    window.removeEventListener("popstate", onChange);
  };
}
const readAnchor = () => window.location.hash.slice(1);
// The server cannot see a hash: hydrate with none, then React re-renders with the real one.
const noAnchor = () => "";

/**
 * Which tab is open. Three inputs, newest wins:
 * - `?tab=` from the page's `searchParams` (server-rendered, so an internal link that carries it never
 *   flashes the default tab);
 * - the hash, once hydrated: `/profile#autofill` opens the tab that renders `#autofill` (old links,
 *   docs, and `useFocusSection`'s in-page jumps, which announce the anchor with a `hashchange`);
 * - a click on the tab row.
 *
 * A click writes the URL with the NATIVE `history.replaceState`: Next copies its own state in and
 * updates `useSearchParams` with no server round trip and no new history entry
 * (`next/dist/client/components/app-router.js`, Next 16.3). `router.replace` would fetch the page's
 * RSC payload on every click and flip the tab only when that lands. The written URL drops the hash, so a
 * reload opens what is on screen.
 */
export function useSettingsTab(
  page: SettingsPage,
  param: string | readonly string[] | undefined,
) {
  const urlTab = parseTab(page, param);
  const anchor = useSyncExternalStore(subscribeToLocation, readAnchor, noAnchor);
  const [tab, setTab] = useState(urlTab);
  const [seen, setSeen] = useState({ urlTab, anchor: "" });
  if (seen.urlTab !== urlTab || seen.anchor !== anchor) {
    setSeen({ urlTab, anchor });
    const anchored = anchor !== seen.anchor ? tabForAnchor(page, anchor) : null;
    if (anchored) setTab(anchored);
    else if (urlTab !== seen.urlTab) setTab(urlTab);
  }

  // A tab opened by anything but the tab row (a hash link, an in-page jump from inside another
  // panel) can hide the panel that holds focus. Inert blurs only at the browser's next focus fixup,
  // so this runs as a layout effect and also accepts focus still sitting inside `[inert]`.
  const shown = useRef(tab);
  useLayoutEffect(() => {
    if (shown.current === tab) return;
    shown.current = tab;
    focusIfStranded(document.querySelector<HTMLElement>(`[data-settings-tab="${tab}"]`));
  }, [tab]);

  const select = (next: string) => {
    const value = parseTab(page, next);
    setTab(value);
    window.history.replaceState(null, "", tabHref(page, value));
  };
  return [tab, select] as const;
}

const LIST_LABEL: Record<SettingsPage, string> = {
  settings: "Settings sections",
  profile: "Profile sections",
};

/**
 * The tab row and one kept-mounted panel per tab. `keepMounted`, not Base UI's default: a never-opened
 * panel would not exist (so a deep link has no target), and a visited one survives only because these
 * panels have no closing transition (the `[&[inert]]:hidden` note in ui/tabs.tsx). Kept mounted, no
 * editor ever unmounts on a tab switch: Persona, Prompts and Autofill keep their typed text, and their
 * `useLeaveGuard` registrations (effects of a mounted, inert component) keep asking.
 */
export function SettingsTabs({
  page,
  param,
  panels,
}: {
  page: SettingsPage;
  param: string | readonly string[] | undefined;
  panels: Record<string, ReactNode>;
}) {
  const [tab, select] = useSettingsTab(page, param);
  return (
    <Tabs value={tab} onValueChange={(value) => select(String(value))} className="gap-4">
      <TabsList aria-label={LIST_LABEL[page]}>
        {tabsFor(page).map((t) => (
          <TabsTrigger key={t.value} value={t.value}>
            {t.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {tabsFor(page).map((t) => (
        <TabsContent
          key={t.value}
          value={t.value}
          keepMounted
          data-settings-tab={t.value}
          className="grid gap-6"
        >
          {panels[t.value]}
        </TabsContent>
      ))}
    </Tabs>
  );
}
```

Notes on the choices above:
- `data-settings-tab`, not `id`. Base UI's panel sets its own `id` and registers it for the tab's
  `aria-controls` (`TabsPanel.js:74-79, 97-107`). An `id` prop would override it and break that wiring.
- `gap-4` between the row and the panel matches the job page. `grid gap-6` between cards matches the
  `PageShell` gap the cards use today (`page-shell.tsx:31`).
- The panel's focus ring is the existing `after:` overlay (`tabs.tsx:95-96`). It needs 4px of room on
  every side, and `PageShell`'s `p-6` gives it. The panel tag passes no `outline-*`, `after:hidden` or
  `overflow-*`, which `test_no_tab_panel_call_site_undoes_the_ring` requires.

### `app/settings/page.tsx` (replace :1-64)

```tsx
"use client";

import { use } from "react";
import { BookOpen } from "lucide-react";

import { AboutSection } from "@/components/settings/about-section";
import { AppearanceSection } from "@/components/settings/appearance-section";
import { AutoApplySection } from "@/components/settings/auto-apply-section";
import { CustomEndpointSection } from "@/components/settings/llm-endpoint";
import { McpWorkflowSection } from "@/components/settings/mcp-workflow-section";
import { ModelCatalogSection } from "@/components/settings/model-catalog-panel";
import { ApiKeysSection, ModelsSection } from "@/components/settings/models-section";
import { PromptsSection } from "@/components/settings/prompts-section";
import { QuickTailorSection } from "@/components/settings/quick-tailor-section";
import { SettingsTabs } from "@/components/settings/settings-tabs";
import { Button } from "@/components/ui/button";
import { PageHeader, PageShell } from "@/components/page-shell";
import { useFocusSection } from "@/lib/use-focus-section";

/**
 * System behaviour, in five tabs. Candidate facts live on `/profile`: see the page rule in
 * `docs/frontend-conventions.md`. The first tab is what a new install needs first (nothing works
 * without a key); the tab table, and which card each anchor opens, is `lib/settings-tabs.ts`.
 */
export default function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string | string[] }>;
}) {
  const { tab } = use(searchParams);
  useFocusSection();

  return (
    <PageShell>
      <PageHeader
        title="Settings"
        subtitle="Models, tailoring, connected agents and appearance."
        actions={guideButton}
      />
      <SettingsTabs
        page="settings"
        param={tab}
        panels={{
          models: (
            <>
              <ApiKeysSection />
              <ModelsSection />
              <ModelCatalogSection />
              <CustomEndpointSection />
              <PromptsSection />
            </>
          ),
          tailoring: <QuickTailorSection />,
          agents: (
            <>
              {/* The MCP explainer card (sibling appendix) renders FIRST here, id="mcp". */}
              <McpWorkflowSection />
              <AutoApplySection />
            </>
          ),
          appearance: <AppearanceSection />,
          about: <AboutSection />,
        }}
      />
    </PageShell>
  );
}
```

### `app/profile/page.tsx` (replace :17-58; imports gain `use` and `SettingsTabs`)

```tsx
export default function ProfilePage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string | string[] }>;
}) {
  const { tab } = use(searchParams);
  useFocusSection();

  const setupStatus = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => apiFetch<SetupStatus>("/api/setup/status"),
    refetchOnMount: "always",
  });

  return (
    <PageShell>
      <PageHeader
        title="Profile"
        subtitle="Who you are as a candidate, and the answers autofill uses."
      />
      {/* Setup progress spans both tabs (and Settings), so it stays above the tab row. */}
      {isLoadFailure(setupStatus) ? (
        <LoadErrorState
          className="py-8"
          title="Couldn't load setup progress."
          detail={(setupStatus.error as Error)?.message}
          retrying={setupStatus.isFetching}
          onRetry={() => void setupStatus.refetch()}
        />
      ) : (
        <SetupStatusStrip status={setupStatus.data} loading={setupStatus.isLoading} />
      )}
      <SettingsTabs
        page="profile"
        param={tab}
        panels={{
          you: (
            <>
              <PersonaSection
                draftDisabledReason={
                  setupStatus.data?.import_resumes.done === true
                    ? undefined
                    : "Import a resume first."
                }
              />
              <MarketSection />
              <JobPreferencesSection />
            </>
          ),
          autofill: <AutofillSection />,
        }}
      />
    </PageShell>
  );
}
```

`guideButton` is the "Getting started guide" `<Button …>` element from `:37-51`, hoisted into a
module-level constant unchanged.

`searchParams` as a prop plus `use()` is the job page's pattern, so neither page needs a `<Suspense>`
boundary. `useSearchParams` under the root layout needs one, or `next build` fails (see the
frontend-conventions sidebar bullet). The prop opts both routes into dynamic rendering. For a local
single-user app that costs nothing, and the job page is dynamic already.

### Pins (section "Tabs", continued)

```python
_IMPORT = re.compile(r'import\s*\{([^}]*)\}\s*from\s*"@/components/settings/([\w-]+)"')
_CARD_ID = re.compile(r'<(?:SettingCard|Card)\b[^>]*?\bid="([\w-]+)"', re.S)


def _panels(src: str, values: list[str]) -> dict[str, str]:
    start = src.index("panels={{")
    block = src[start : src.index("}}\n", start)]
    marks = sorted((re.search(rf"\b{v}: ", block).start(), v) for v in values)
    bounds = [at for at, _ in marks] + [len(block)]
    return {v: block[bounds[i] : bounds[i + 1]] for i, (_, v) in enumerate(marks)}


@pytest.mark.parametrize(
    ("page", "table"),
    [("app/settings/page.tsx", "SETTINGS_TABS"), ("app/profile/page.tsx", "PROFILE_TABS")],
)
def test_every_card_id_resolves_to_the_tab_that_renders_it(page, table):
    """A deep link opens the tab `tabForAnchor` names. A card moved to another panel without
    its id moving in lib/settings-tabs.ts would land on the wrong tab, ringing nothing."""
    tabs = _tab_table(table)
    src = _read(page)
    files = {
        name.strip(): f"components/settings/{mod}.tsx"
        for names, mod in _IMPORT.findall(src)
        for name in names.split(",")
        if name.strip()
    }
    for value, body in _panels(src, list(tabs)).items():
        rendered = {n for n in re.findall(r"<(\w+)\b", body) if n in files}
        assert rendered, f"{page}: panel {value} renders no settings card"
        ids = {i for n in rendered for i in _CARD_ID.findall(_read(files[n]))}
        assert ids and ids <= tabs[value], (page, value, sorted(ids - tabs[value]))


def test_tab_panels_stay_mounted_and_the_url_is_written_natively():
    src = _read("components/settings/settings-tabs.tsx")
    panel = src[src.index("<TabsContent") : src.index("</TabsContent>")]
    assert "keepMounted" in panel
    assert "data-settings-tab={t.value}" in panel
    assert "id=" not in panel  # Base UI's panel id is the tab's aria-controls target
    select = src[src.index("const select = (") :]
    assert 'window.history.replaceState(null, "", tabHref(page, value));' in select
    assert "router." not in src  # a router.replace fetches the page on every click
    assert "useSyncExternalStore(subscribeToLocation, readAnchor, noAnchor)" in src
```

### Browser checks (fresh uvicorn and `next dev` per SYSTEM.md §9; never the compose images)

1. **Mouse.** Click every tab on `/settings` and `/profile`.
   - The address bar shows `?tab=<slug>`, and shows nothing on the default tab.
   - The Network panel shows no RSC or document request per click, and no skeleton flashes.
   - History length is unchanged: `history.length` in `javascript_tool` before and after five clicks.
2. **Keyboard.** Tab to the row. Arrow Right and Left move focus and loop at the ends; Home and End jump.
   Enter or Space opens the focused tab (manual activation). Tab moves into the panel: the panel shows
   the 2px ring overlay, and the next Tab reaches the first control in it.
3. **Accessibility tree** (`read_page`): the tablist is named "Settings sections"; each tab has
   `aria-selected` and `aria-controls` pointing at a `tabpanel` labelled by it; hidden panels are absent.
4. **Reload `/settings?tab=about`.** The About tab is open in the server HTML (`get_page_text` right after
   `navigate`), with no flash of AI & models.
5. **Unsaved text survives.** Type in Persona. Switch to Autofill and back, and the text is still there.
   Do the same on Settings with an open Prompt and a typed endpoint draft.
6. **Unknown values.** `/settings?tab=zzz` opens AI & models. `/profile?tab=autofill&tab=you` opens
   Autofill.

### Risks
- **`searchParams` after a native replaceState.** `ACTION_RESTORE` reuses the history entry's tree, so the
  page's `searchParams` promise may keep the arrival value. The hook does not depend on it changing: the
  "adjust on change" block only reacts when it *does* change. If a Next upgrade turns that promise into a
  new, unresolved one on restore, `use()` would suspend. Browser check 1 ("no skeleton flashes") guards
  this. The fallback is `useSearchParams` plus a `<Suspense>` whose fallback renders the default tab.
- **A hash-only landing** renders the default tab on the server, then the anchored tab after hydration.
  That is one frame of the wrong panel. C3 removes every internal source of hash-only links.

---

## C3: deep links (inventory, `anchorHref`, `useFocusSection`)

### Inventory: every link into `/settings` and `/profile`, and where it lands

| Source (file:line at `8cac7cf9`) | Link today | Tab · card | Change |
|---|---|---|---|
| `frontend/app/new/page.tsx:102` | `/settings#api-keys` | AI & models · API keys | `anchorHref("/settings", "api-keys")`; same string, since the default tab adds no `?tab=` |
| `frontend/components/job-knockout-card.tsx:66` | `/profile#autofill-${group}` (`work_auth`, `preferences`) or `/profile#autofill` | Autofill · the group's fieldset, or the card | `anchorHref("/profile", group ? \`autofill-${group}\` : "autofill")` → `/profile?tab=autofill#autofill-work_auth` |
| `frontend/components/setup/setup-steps.ts:106-107, 181` (`model_key`) | `/settings#api-keys` | AI & models · API keys | `href: anchorHref(step.home, step.anchor)` at :181 |
| `setup-steps.ts:129-132` (`autofill`) | `/profile#autofill-<group>` or `#autofill` | Autofill · fieldset or card | same |
| `setup-steps.ts:139-140` (`job_preferences`) | `/profile#job-preferences` | About you · Job preferences | same (no `?tab=`) |
| `setup-steps.ts:147-148` (`persona`) | `/profile#persona` | About you · Persona | same |
| `frontend/components/setup/getting-started-card.tsx:153` | `` `${row.home}#${row.anchor}` `` (all four rows above) | as above | `anchorHref(row.home, row.anchor)` |
| `frontend/components/setup/setup-status-strip.tsx:81` (on `/profile`) | in-page `focus(step.anchor)` for autofill, job preferences and persona; the API key step navigates | as above | `focus` now reveals the tab (below) |
| `frontend/components/app-sidebar.tsx:71-72` | `/profile`, `/settings` | default tabs | none |
| `frontend/lib/use-focus-section.ts:48-94` | the landing effect for any hash | as the hash | waits for *shown* (below) |
| `docs/entities/others.md:149-150` | `/settings#api-keys`, "→ `/profile`" | AI & models · API keys | still valid; no edit |
| `docs/frontend-conventions.md:894` | `/profile#autofill` (example) | Autofill · card | still valid; reword per C9 |
| `backend/app/services/llm.py:93,96,456`, `backend/app/main.py:87` | prose: "Settings → Models" | AI & models · API keys / Custom endpoint | C9 |
| `backend/app/services/llm_capabilities.py:241` | prose: "in Settings" | AI & models · Models | C9 |
| `backend/app/services/knockout.py:63,81,125` | prose: "in Settings" (**wrong page**) | Profile · Autofill | C9 |
| `backend/app/services/job_search_brief.py:80` | prose: "autofill profile in Settings" (**wrong page**) | Profile · Autofill | C9 |
| `extension/panel/actions/fill.js:91` | prose: "under Profile" | Profile · Autofill | C9: "under Profile → Autofill" |
| `extension/INTERNALS.md:311` | prose: "Profile → Eligibility" | Profile · Autofill · Eligibility fieldset | C9 |
| `extension/README.md:53,56`, `INTERNALS.md:274,300`, `docs/skills/agent-apply-execution/SKILL.md:74-80`, `docs/playbooks/agent-apply.md:221-231` | prose: "in Profile" | Profile · Autofill (the EEO consent switches) | C9: "Profile → Autofill" |
| `README.md:152,166,221,363,382,715`, `docs/GETTING_STARTED.md:25,79,87,100,134,155`, `KNOWN_ISSUES.md:77` | prose: "Settings → Models", "Settings → Quick tailor", "the Test button in Settings" | AI & models, Tailoring | C9 |
| MCP docstrings (`mcp_server/server.py:127,544,674-679,1362`), `services/mcp_workflow.py:8` | prose: "Settings switch", "Profile" | still true | none |

No extension code links into `/settings` or `/profile`. The panel's only web-app links go to
`/jobs/<id>` (`panel/panel.js:992-1003`) and `/jobs/<id>?tab=fit` (`panel/stages/resume.js:66`). The
backend emits no URL into either page.

### Code changes

- `components/setup/setup-steps.ts:181`:
  ```ts
  : { kind: "navigate", href: anchorHref(step.home, step.anchor) },
  ```
  with `import { anchorHref } from "@/lib/settings-tabs";`.
- `components/setup/getting-started-card.tsx:153`: `render={<Link href={anchorHref(row.home, row.anchor)} />}`.
- `components/job-knockout-card.tsx:63-67`:
  ```ts
  function autofillHref(scan: KnockoutScan): string {
    const missing = scan.checks.find((c) => c.result === "profile_missing");
    const group = missing ? CHECK_GROUP[missing.kind] : undefined;
    return anchorHref("/profile", group ? `autofill-${group}` : "autofill");
  }
  ```
- `app/new/page.tsx:102`: `render={<Link href={anchorHref("/settings", "api-keys")} />}`.

### `lib/use-focus-section.ts`: wait for *shown*, and reveal a hidden target

The target is `display:none` inside a kept-mounted panel, so `getElementById` finds it but
`scrollIntoView` does nothing. Replace `focus` (:18-29) and the poll inside the landing effect (:70-84):

```ts
/** Shown, not merely mounted: a card in a hidden tab panel is in the DOM with no box. */
function shown(anchor: string): HTMLElement | null {
  const el = document.getElementById(anchor);
  return el && el.getClientRects().length > 0 ? el : null;
}

/**
 * Put `anchor` in the address bar with no history entry and no scroll, and tell the page. A tabbed
 * page (Settings, Profile) opens the tab that renders it (`useSettingsTab` listens for hashchange);
 * Next listens for no hashchange, so the synthetic event reaches only that hook.
 */
function announce(anchor: string) {
  const { pathname, search } = window.location;
  window.history.replaceState(null, "", `${pathname}${search}#${anchor}`);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

/** Poll (every 50ms, up to WAIT_MS) until `anchor` is shown, then hand it over. Returns a cancel. */
function whenShown(anchor: string, then: (el: HTMLElement) => void): () => void {
  const started = performance.now();
  const poll = window.setInterval(() => {
    const el = shown(anchor);
    if (el) {
      window.clearInterval(poll);
      then(el);
      return;
    }
    if (performance.now() - started > WAIT_MS) window.clearInterval(poll);
  }, 50);
  return () => window.clearInterval(poll);
}

/** Scroll a section into view and ring it briefly, opening its tab first if it is hidden. */
export function useFocusSection() {
  const focus = useCallback((anchor: string) => {
    if (!document.getElementById(anchor)) return;
    if (!shown(anchor)) announce(anchor);
    whenShown(anchor, (el) => {
      const behavior: ScrollBehavior =
        document.visibilityState === "visible" ? "smooth" : "auto";
      el.scrollIntoView({ behavior, block: "center" });
      ring(el);
    });
  }, []);
  // The landing effect keeps its shape: `const cancel = whenShown(hash, (el) => { scroll; ring; hold })`,
  // and its cleanup calls `cancel()` beside `observer?.disconnect()`. Only the found-test changes.
  …
}
```

On `/career`, the other caller (`app/career/page.tsx:54`), every target is visible, so behaviour there
is unchanged. The profile strip keeps calling `focus(step.anchor)`. It is outside the tab row, so its
button keeps focus while the tab opens.

### Pins (section "Deep links")

```python
_SOURCES = [
    p for d in ("app", "components", "lib", "hooks") for p in (_FRONTEND / d).rglob("*.ts*")
    if ".test." not in p.name
]


def test_links_into_settings_and_profile_name_their_tab():
    """A hash-only link renders the default tab on the server and flips after hydration; every
    in-app link goes through anchorHref so the server renders the right tab."""
    offenders = [
        str(p.relative_to(_FRONTEND))
        for p in _SOURCES
        if re.search(r"""["'`]/(?:settings|profile)#""", p.read_text())
    ]
    assert offenders == [], offenders
    assert "anchorHref(step.home, step.anchor)" in _read("components/setup/setup-steps.ts")
    assert "anchorHref(row.home, row.anchor)" in _read("components/setup/getting-started-card.tsx")
    assert 'anchorHref("/profile", group ?' in _read("components/job-knockout-card.tsx")
    assert 'anchorHref("/settings", "api-keys")' in _read("app/new/page.tsx")


def test_a_section_lands_only_once_it_is_shown():
    src = _read("lib/use-focus-section.ts")
    assert "el.getClientRects().length > 0" in src
    assert 'window.dispatchEvent(new HashChangeEvent("hashchange"))' in src
    assert "window.history.replaceState(null, \"\", `${pathname}${search}#${anchor}`);" in src
    # A bare getElementById poll rang a card hidden in another tab and stopped.
    assert "const el = document.getElementById(hash);\n      if (el) {" not in src
```

### Existing pins affected
- `test_frontend_first_run.py:34` (`count("required: true") == 2`): unchanged.
- `test_frontend_query_error_states.py:85, 233`: the profile page keeps `<SetupStatusStrip` and
  `{isLoadFailure(setupStatus) ? (`, so they are unchanged.

### Browser checks
1. From `/new` with no key: **Add API key** lands on `/settings`. AI & models is open, and API keys is
   centred and ringed.
2. On a job whose knock-out scan says `incomplete_profile` (work auth unset): the card's link lands on
   `/profile?tab=autofill#autofill-work_auth`. Autofill is open, and the Work authorization fieldset is
   ringed after the autofill query loads (up to 3s).
3. **Legacy hash-only links**, typed in the address bar in a fresh tab. Each opens the right tab and rings
   the card:
   - `/profile#autofill`, `/profile#autofill-eeo`, `/profile#persona`;
   - `/settings#agent-hints`, `/settings#about`, `/settings#prompts`, `/settings#model-catalog`.
4. On `/profile`, with the Autofill tab open, click the strip's **Persona** pill. About you opens,
   Persona is ringed, and focus stays on the pill (`document.activeElement`).
5. On `/applications` with setup incomplete, the Getting started card's buttons open the right tab for
   each row.
6. **Skip link** on `/profile?tab=autofill`: Tab once, then Enter. Focus moves to the main area, and the
   tab does not change (`#main-content` maps to no tab).

### Risks
- `announce` rewrites the URL to `?tab=you#autofill` when the strip jumps from About you. The hash wins on
  reload (`useSettingsTab` reads it first), so the page reopens where it was. A later tab click rewrites
  the URL without the hash.
- `/profile` still calls `useFocusSection()` twice: the page at :18 and the strip at
  `setup-status-strip.tsx:44`. So a hash landing polls twice and rings twice. That is harmless and
  pre-existing. Removing the strip's call would need the page to pass `focus` down (open question 9).

---

## C4: the leave guard and focus across hidden panels

### What already holds (verified by reading)
- **Registration survives a hidden tab.** `useLeaveGuard` registers in `useEffect(() => { setLeaveGuard
  (owner, scope); return () => setLeaveGuard(owner, null) }, [owner, scope])`
  (`hooks/use-leave-guard.ts:19-22`). The effect is torn down only on unmount or a scope change.
  `keepMounted` means no unmount, and `inert` plus `display:none` do not stop effects. The registered
  owners today:
  - Persona `useLeaveGuard(dirty)` (`persona-section.tsx:119`);
  - Autofill (`autofill-section.tsx:689`);
  - every PromptCard (`prompts-section.tsx:153`);
  - Quick tailor and Job preferences `useLeaveGuard(failed)` (:85, :125).

  Market and Agent hints register nothing on purpose (`test_server_value_cards_report_failure_without_retry`).
- **In-app links and unload.** `GuardedLink` reads `leaveBlocked("in-app")` at click time
  (`guarded-link.tsx`), and the one `beforeunload` listener reads the registry at unload time
  (`leave-guard-listeners.tsx:245-256`). Neither knows or cares which tab is showing.

### What breaks without a change: Back/Forward (finding 1)

`listeners` reads every entry as `pathname + search` (`leave-guard-listeners.tsx:55`). The tab switch is a
replace on the current entry. While the page is dirty, the current entry is the sentinel.
`stampAfterWrite` (:145) then drops the sentinel flag, because the URL changed. From there:
- After a save, Back is a dead press: it lands on the real entry of the same page.
- While dirty, Back is judged "another page" (:331 is false). The ask's `leaveTo` is the editor's own
  entry.

### Change `frontend/lib/leave-guard.ts` (verified: 43/43 history tests; the new ones fail 2/5 before)

Add, above `stampAfterWrite` (:135):

```ts
/**
 * The page an entry shows is its PATHNAME. Next keys a page's React state without its search
 * params (`layout-router.js`, `createRouterCacheKey(activeSegment, true)`), so a search or hash
 * change (a settings tab) keeps the page, and its unsaved work, mounted: it is not leaving.
 */
export function samePage(a: string, b: string): boolean {
  return pagePath(a) === pagePath(b);
}

function pagePath(url: string): string {
  const cut = url.search(/[?#]/);
  return cut === -1 ? url : url.slice(0, cut);
}
```

and make four one-token edits:
- :145 `sentinel: written.sentinel || (before.sentinel && samePage(before.url, written.url)),`
- :312 (`arrive`) `if (samePage(e.url, t.page)) {`
- :331 (`judge`) `if (samePage(e.url, t.page)) {`
- :358 `if (dir > 0 && e.at !== null && above?.sentinel && samePage(above.url, e.url)) {`

Then `components/leave-guard-listeners.tsx:69` becomes `next.here.kind === "next" && samePage(next.here.url,
next.page)`. That way `restorePage` snapshots the newest tab of the page, not only its arrival URL.

**`lib/leave-guard-history.test.ts`: add to `class Tab`** (after `write`, before `link`):

```ts
  /** A same-page tab switch: the tab hook's native replaceState. Next copies its own state in,
   *  without our fields, so the stamp decides whether the entry is still the duplicate. */
  switchTab(url: string) {
    this.write("replace", url, false);
    this.shown = url;
  }
```

and append:

```ts
test("a tab switch keeps the duplicate: Back asks, Stay returns to the tab, Leave leaves the page", () => {
  const tab = dirtyStudio();
  tab.switchTab("/studio?tab=b");
  assert.equal(tab.slots[tab.index].sentinel, true, "still the duplicate");
  tab.back();
  assert.equal(tab.asking, true, "a Back off a switched tab still asks");
  assert.equal(tab.shown, "/studio?tab=b", "Next did not render the older tab");
  tab.answer(false);
  tab.agrees();
  assert.equal(tab.url, "/studio?tab=b");
  tab.back();
  tab.answer(true);
  tab.agrees();
  assert.equal(tab.shown, "/list");
});

test("a tab switch, then a save: Back leaves in one press", () => {
  const tab = dirtyStudio();
  tab.switchTab("/studio?tab=b");
  tab.saved();
  tab.back();
  assert.equal(tab.asking, false);
  tab.agrees();
  assert.equal(tab.shown, "/list");
});

test("a clean tab switch writes no entry, and Back leaves the page", () => {
  const tab = new Tab("/list");
  tab.link("/studio");
  const length = tab.slots.length;
  tab.switchTab("/studio?tab=b");
  assert.equal(tab.slots.length, length);
  tab.back();
  tab.agrees();
  assert.equal(tab.shown, "/list");
});

test("a tab switch, then an edit: the duplicate carries the tab", () => {
  const tab = new Tab("/list");
  tab.link("/studio");
  tab.switchTab("/studio?tab=b");
  tab.edit();
  assert.equal(tab.slots[tab.index].sentinel, true);
  assert.equal(tab.url, "/studio?tab=b");
  tab.back();
  assert.equal(tab.asking, true);
  tab.answer(false);
  tab.agrees();
});

test("a pathname change still drops the duplicate flag", () => {
  const tab = dirtyStudio();
  tab.saved();
  tab.link("/other");
  assert.equal(tab.slots[tab.index].sentinel, false);
});
```

On the unchanged machine, the first test fails at "still the duplicate", and the second fails with
`actual '/studio'`. That second failure is the dead Back press.

### Recommended: `GuardedLink` does not ask for a link to the same page

`components/guarded-link.tsx`, inside `onNavigate`, changes to `if (!leaveBlocked("in-app") ||
samePage(href, window.location.pathname)) return;`, and imports `samePage` from `@/lib/leave-guard`.

A link from inside a settings panel to another tab of the same page unmounts nothing. For example, the
MCP explainer might say "add a key" and link to `/settings#api-keys`. Asking "Leave without saving?"
there is a false alarm. When the sentinel is current, GuardedLink already `replace`s rather than pushes
(:57), and `stampAfterWrite` now keeps the flag. This is optional: open question 1. In-page cross-tab
jumps should in any case be buttons that call `useFocusSection()`'s `focus(anchor)`, not links, so that
they push no history entry.

### New helper `focusIfStranded` in `frontend/lib/focus.ts` (verified: 20/20 focus tests)

Insert after `focusIfDropped` (:13-17):

```ts
/**
 * Focus `target` when focus has nowhere useful to be: on <body>, or inside an `inert` subtree (a tab
 * panel another control just hid, which the browser blurs only at its next focus fixup).
 */
export function focusIfStranded(target: HTMLElement | null | undefined): void {
  const active = document.activeElement;
  if (active && active !== document.body && !active.closest("[inert]")) return;
  target?.focus({ preventScroll: true });
}
```

In `lib/focus.test.ts`, add `focusIfStranded` to the import list. Add one line to the stand-in's
`matches`: `if (selector === "[inert]") return "inert" in this.attrs;`. Then append:

```ts
test("focusIfStranded takes focus from <body> or an inert panel, never from a live control", () => {
  const hidden = h("div", { role: "tabpanel", inert: "" }, h("button", { id: "old" }));
  const shownPanel = h("div", { role: "tabpanel", tabindex: "0", id: "new" });
  const live = h("button", { id: "live" });
  doc.body.append(hidden, shownPanel, live);
  (doc.getElementById("old") as El).focus();
  focusIfStranded(asEl(shownPanel));
  assert.equal(doc.activeElement, shownPanel);
  live.focus();
  focusIfStranded(asEl(shownPanel));
  assert.equal(doc.activeElement, live);
  doc.activeElement = doc.body;
  focusIfStranded(asEl(shownPanel));
  assert.equal(doc.activeElement, shownPanel);
});
```

### Pins (append to `backend/tests/test_frontend_leave_guard.py`)

```python
def test_a_search_or_hash_change_is_the_same_page():
    """A settings tab rewrites ?tab= on the sentinel. Compared by full URL, the duplicate was
    lost (a dead Back after a save) and a dirty Back asked about leaving a page it stays on."""
    src = _read("lib/leave-guard.ts")
    assert "export function samePage(" in src
    assert "before.sentinel && samePage(before.url, written.url)" in src
    assert src.count("if (samePage(e.url, t.page)) {") == 2  # arrive and judge
    assert "above?.sentinel && samePage(above.url, e.url)" in src
    assert "before.url === written.url" not in src
    assert "e.url === t.page" not in src
    assert "samePage(next.here.url, next.page)" in _read("components/leave-guard-listeners.tsx")


def test_a_panel_hidden_under_focus_hands_focus_to_the_open_panel():
    focus = _read("lib/focus.ts")
    assert '!active.closest("[inert]")' in focus
    tabs = _read("components/settings/settings-tabs.tsx")
    assert "useLayoutEffect(" in tabs
    assert "focusIfStranded(document.querySelector<HTMLElement>(`[data-settings-tab=\"${tab}\"]`));" in tabs
```

If the GuardedLink recommendation is taken, also edit the existing
`test_guarded_link_cancels_before_it_asks` (`test_frontend_leave_guard.py:44`). Its early-return string
becomes `'if (!leaveBlocked("in-app") || samePage(href, window.location.pathname)) return;'`. As written,
the old assert fails on the new line.

### Browser checks
1. **Leave guard from a hidden tab.** On `/profile`, type in Persona without saving, then open Autofill.
   Click the sidebar's **Applications**. "Leave without saving?" appears. **Stay** keeps you on Autofill
   with the Persona text intact (switch back to check it). **Leave** navigates. Repeat on `/settings`
   with an open, edited Prompt, then switch to About.
2. **Reload warns** from the hidden tab: the browser's own dialog appears.
3. **Back** (Next 16.3, per the conventions' leave-guard bullet). Arrive at `/profile` from
   `/applications`. Type in Persona, switch to Autofill (the URL is `?tab=autofill`), and press Back.
   - It asks. The page still shows Autofill.
   - **Stay** restores the URL to `?tab=autofill`.
   - Back again, then **Leave**, lands on `/applications`.
   - Then: Forward returns to `/profile`, and one Back leaves again, with no dead press.
4. **Save first, then Back.** Type in Persona, switch tab, Save Persona, then Back. You land on
   `/applications` in one press.
5. **Clean switching adds no history.** On a clean page, switch tabs five times and press Back once: you
   are on the previous page.

### Risks
- **The machine change is global.** Every guarded page now treats a search or hash change as the same
  page. Today no guarded page keys content on its search params. The gap page's `?review=1` and the job
  page's `?tab=` both keep the page mounted, so the change is correct for them too. A future page that
  remounts on a search change (`key={searchParams…}`) would need its own guard. Record that in the
  conventions (C9).
- **`focusIfStranded` assumes Chrome and WebKit blur an inert element at the next focus fixup, after
  React's layout effects.** If a browser blurs synchronously, `activeElement` is `<body>` and the helper
  still moves focus, because it takes both branches. The browser check "a cross-tab jump from inside a
  panel" needs the MCP explainer's link, so run it when that card lands.

---

## C5: the shared tab row scrolls inside itself (`components/ui/tabs.tsx`)

### Current code

`tabsListVariants` base, `tabs.tsx:34`:

```ts
"group/tabs-list inline-flex w-fit items-center justify-center rounded-lg p-[3px] text-muted-foreground group-data-horizontal/tabs:min-h-8 group-data-vertical/tabs:h-fit group-data-vertical/tabs:flex-col data-[variant=line]:rounded-none",
```

`w-fit` with no cap, plus `whitespace-nowrap` triggers (:68), means the list is as wide as its labels. At
375 the job page's four tabs push Q&A off-screen, and the New base résumé dialog's row does not shrink
(both in SYSTEM.md §11 item 31). The new Settings row needs about 480px.

### New base string

```ts
// max-w-full + overflow-x-auto: a row wider than its container scrolls INSIDE itself instead of
// widening the page (the job page's Q&A tab ran off-screen at 375, SYSTEM.md §11 item 31). A scroll
// container's min-width:auto is 0, so it also shrinks as a flex item. justify-center-safe, not
// justify-center: centred content that overflows clips its START, which no scroll can reach. Base UI
// scrolls the focused tab into view on arrow keys (composite scrollIntoViewIfNeeded). The scrollbar
// is hidden: the cut-off last label is the cue, and keys and swipes reach it.
"group/tabs-list inline-flex w-fit max-w-full items-center justify-center-safe rounded-lg p-[3px] text-muted-foreground group-data-horizontal/tabs:min-h-8 group-data-horizontal/tabs:overflow-x-auto group-data-horizontal/tabs:overscroll-x-contain group-data-horizontal/tabs:[scrollbar-width:none] group-data-horizontal/tabs:[&::-webkit-scrollbar]:hidden group-data-vertical/tabs:h-fit group-data-vertical/tabs:flex-col data-[variant=line]:rounded-none",
```

Why this is safe for every call site (the list is at `grep -rn "<TabsList" app components`):
- **Single-row lists** fit or scroll: the job page, the template editor (`app/templates/[id]/page.tsx:270`),
  the upload dialog, New base résumé, and Settings and Profile.
- **Wrapping lists** (`h-auto flex-wrap`) never overflow sideways, so the class is inert there: Career,
  Analytics, both studios' section tabs, and the KB import drawer.
- **Focus rings are not clipped.** A trigger's `ring-[3px]` halo sits inside the list's 3px padding, and
  the pills' `p-1` is 4px. The 1px `border-ring` is inside the trigger.
- **The `line` variant's indicator** (`after:bottom-[-5px]`, :71) would be clipped by 2px. No call site
  uses `variant="line"`. Say so in a comment beside the variant.

### Pins (section "Tab row")

```python
def test_a_tab_row_scrolls_inside_itself_instead_of_widening_the_page():
    tabs = _read("components/ui/tabs.tsx")
    base = tabs[tabs.index("const tabsListVariants") : tabs.index("function TabsList")]
    for cls in (
        "max-w-full",
        "justify-center-safe",
        "group-data-horizontal/tabs:overflow-x-auto",
        "group-data-horizontal/tabs:[scrollbar-width:none]",
    ):
        assert cls in base, cls
    # Centred overflow clips the first tab out of reach.
    assert re.search(r"\bjustify-center\b(?!-)", base) is None
```

`test_frontend_color_roles.py:412-433` slices `TabsContent` only, so it is unaffected.

### SYSTEM.md

§11 item 31 (:835-838): delete "the New base résumé dialog's tab row does not shrink;" and "the job page's
tab row pushes Q&A off-screen;". Do this only after browser checks 1 and 2 pass.

### Browser checks (375, 768, 1280; light and dark)
1. **Job page, 375.** All four tabs are reachable by swipe and by arrow keys; each focused tab scrolls
   into view. There is no page horizontal scrollbar
   (`document.documentElement.scrollWidth === innerWidth`).
2. **New base résumé dialog, 375.** The tab row scrolls inside the dialog.
3. **`/settings` at 375 and 768.** The row scrolls, and the active tab's pill and focus ring are complete
   at both ends. `/profile` fits without scrolling.
4. **No regression** on `/analytics`, `/career` and both studios' section tabs (wrapping pills) at 1280
   and 375.

### Risks
- With the scrollbar hidden, a desktop mouse user at a narrow window width without a trackpad has no
  pointer path to the last tab except shift+wheel. Keys and click-then-arrow still work. Open question 7
  covers a visible thin scrollbar instead.

---

## C6: autosave status in the card header (`SettingCard`)

### Current code
- `setting-card.tsx:88-111`: the header is title and description only. The body is error, skeleton or
  `children(value)`.
- `setting-card.tsx:114-127` (`AutosaveRow`) records the decision this reverses: "`SettingCard` gives the
  header no slot so the question cannot be reopened". Its row is `mb-4 flex justify-end`.
- `autosave-status.tsx:51`, outer span: `inline-flex items-center gap-2 text-xs`. It reserves no width.

**Inventory of header-ish controls, and where each goes:**

| Control | Today | Moves to |
|---|---|---|
| Quick tailor `AutosaveStatus` + Try again | `quick-tailor-section.tsx:89-91`, in `AutosaveRow` | header (`SettingCardAction`) |
| Job preferences `AutosaveStatus` + Try again | `job-preferences-section.tsx:143-145` | header |
| Market `AutosaveStatus` | `market-section.tsx:70-72`; inside `grid gap-4` plus `mb-4`, a 32px row holding only the status | header; the empty row goes |
| Agent hints `AutosaveStatus` | `mcp-workflow-section.tsx:62-64` | header |
| Persona "Draft from my career" | `persona-section.tsx:123-135`, `mb-3 flex justify-end` | header (a card-level action) |
| Catalog "Sync OpenAI" / "Sync Gemini" | `model-catalog-panel.tsx:98-134`, a sub-header inside the body | the new Model catalog card's header (C7) |
| Autofill "Fill from resume", "Decline all" | inside group legends, `autofill-section.tsx:725-743` | stay: they act on one group, not the card |
| Save / Discard (API keys, Auto-apply, Persona, Autofill, each Prompt, endpoint Save) | body | stay in the body, as its last row (C8) |

### New `components/settings/setting-card.tsx`

Render (replaces :60-112; the `SettingQuery` type and `firstMessage` stay):

```tsx
"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { LoadErrorState } from "@/components/load-error-state";
import { isLoadFailure } from "@/lib/query-state";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/** The header's action node, filled once the card has committed. */
const HeaderSlot = createContext<HTMLElement | null>(null);

// Beside the title while the header has room; below the description when it is narrower
// than 28rem (every card at 375, and a header crowded by the catalog's two Sync buttons at 768).
const ACTION =
  "flex items-center gap-2 empty:hidden @max-md/card-header:col-start-1 @max-md/card-header:row-span-1 @max-md/card-header:row-start-auto @max-md/card-header:justify-self-start";

export function SettingCard<T>({ id, title, description, errorTitle, skeleton = "h-40 w-full", query, also, children }: /* props unchanged */) {
  const queries: SettingQuery<unknown>[] = [query, ...(also ?? [])];
  const ready = queries.every((q) => q.data !== undefined);
  const loadFailed = queries.some((q) => isLoadFailure(q));
  // A callback ref, not an effect: React sets it in the commit, and the body's portal renders
  // into it on the next render.
  const [slot, setSlot] = useState<HTMLElement | null>(null);

  return (
    <Card id={id}>
      <CardHeader>
        <CardTitle role="heading" aria-level={2}>
          {title}
        </CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
        <CardAction ref={setSlot} className={ACTION} />
      </CardHeader>
      <CardContent className="@container/setting">
        <HeaderSlot value={slot}>
          {loadFailed && !ready ? (
            <LoadErrorState /* unchanged from :95-103 */ />
          ) : !ready ? (
            <Skeleton className={skeleton} />
          ) : (
            children(query.data as T)
          )}
        </HeaderSlot>
      </CardContent>
    </Card>
  );
}

/**
 * Renders its children into the card header, right of the title: the autosave status, Persona's
 * "Draft from my career", the catalog's Sync pair.
 *
 * A PORTAL, not a prop. Each of those is driven by state that belongs to the editor inside the body
 * (the autosave queue, the draft request, the sync mutation); a header prop would mean lifting that
 * state out through an effect for a placement. The portal leaves the state where it is and puts the
 * DOM in the header, so a screen reader meets the status after the title and description and before
 * the fields it describes. (It replaces the old status row at the top of the body, which left an empty
 * row on a one-field card such as Market.) Nothing renders on the card's first frame; the slot fills
 * on the next.
 */
export function SettingCardAction({ children }: { children: ReactNode }) {
  const slot = useContext(HeaderSlot);
  return slot ? createPortal(children, slot) : null;
}
```

Extra docstring changes:
- **Delete** `AutosaveRow` (:114-127).
- **Add** one paragraph to the `SettingCard` docstring:

  > 3. **The header has one action slot, filled from the body.** See `SettingCardAction`. The title is a
  > level-2 heading (`CardTitle` is a `div`), so each tab panel reads as a list of named cards.

- **Appearance** (`appearance-section.tsx:50`) gets the same `role="heading" aria-level={2}` on its
  `CardTitle`.

`empty:hidden` keeps a card with no action exactly as it is today. `CardHeader`'s
`has-data-[slot=card-action]:grid-cols-[1fr_auto]` (`card.tsx:30`) still opens an empty auto column,
which costs one `gap-1` (4px) of the title's width.

### `AutosaveStatus` reserves its width (`autosave-status.tsx:51`)

```tsx
<span className={`inline-flex min-w-36 items-center justify-end gap-2 text-xs ${className ?? ""}`}>
```

The three states measure about 60px ("Saving…"), about 123px ("Saves automatically") and about 126px
("Not saved Try again") at `text-xs`. The width of a `1fr_auto` header's auto column changes with its
content, so the description re-wrapped on every save. Correct the docstring (:21-22) to say where the
width comes from.

### Each card (the body keeps the state)

```tsx
// quick-tailor-section.tsx, replacing :89-91 (the rest of the body per C8)
<SettingCardAction>
  <AutosaveStatus pending={pending} failed={failed} onRetry={retry} />
</SettingCardAction>
```

- Job preferences: the same replacement at :143-145.
- Market: :70-72 becomes `<SettingCardAction><AutosaveStatus pending={save.isPending}
  failed={save.isError} /></SettingCardAction>`.
- Agent hints: :62-64 becomes the same as Market.
- Persona (:123-135), with the missing focus fix:

```tsx
<SettingCardAction>
  <Button
    type="button"
    variant="outline"
    size="sm"
    focusableWhenDisabled
    disabled={draft.isPending || Boolean(draftDisabledReason)}
    aria-describedby={draftDisabledReason ? reasonId : undefined}
    className="data-disabled:pointer-events-none data-disabled:opacity-50"
    onClick={() => draft.mutate(editRevision.current)}
  >
    {draft.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}
    Draft from my career
  </Button>
</SettingCardAction>
```

Put `<p id={reasonId} className="text-muted-foreground text-xs">{draftDisabledReason}</p>`, rendered only
while there is a reason, as the first row of the body. A native `disabled` button shows no `title` to a
keyboard or screen-reader user, and dropped focus when a draft started. Remove the `title` prop.
`reasonId` comes from `useId()`.

### Pins

In `test_frontend_settings_autosave.py`, keep every existing string. The `<AutosaveStatus …/>` literals at
:93 and :102 are unchanged. Add:

```python
_CARD = _read("components/settings/setting-card.tsx")


def test_the_header_has_one_action_slot_the_body_renders_into():
    header = _CARD[_CARD.index("<CardHeader>") : _CARD.index("</CardHeader>")]
    assert "<CardAction ref={setSlot}" in header
    assert '<CardTitle role="heading" aria-level={2}>' in header
    assert "createPortal(children, slot)" in _CARD
    assert "<HeaderSlot value={slot}>" in _CARD
    assert "AutosaveRow" not in _CARD
    assert "useEffect" not in _CARD  # the slot is a callback ref, never an effect


@pytest.mark.parametrize("rel", _AUTOSAVE_CARDS + _SERVER_VALUE_CARDS)
def test_every_autosave_status_renders_in_the_card_header(rel):
    src = _read(rel)
    at = src.index("<AutosaveStatus")
    assert src.rfind("<SettingCardAction>", 0, at) > src.rfind("</SettingCardAction>", 0, at), rel
    assert "AutosaveRow" not in src


def test_the_status_reserves_its_width():
    # Beside a title the auto column's width follows the status, so the description re-wrapped.
    assert "inline-flex min-w-36 items-center justify-end gap-2 text-xs" in _STATUS
```

Add `import pytest` to that file. In `test_frontend_focus.py`, add a row to the parametrize at :396-410.
The ids list gains `"persona-draft"`:

```python
(_read("components/settings/persona-section.tsx"), "Draft from my career"),
```

### Existing pins affected
- `test_frontend_query_error_states.py:152`, `"<CardHeader" not in source`: section files still never
  build a header. `CardHeader` stays inside `setting-card.tsx`, which that list does not include.

### Browser checks (fresh stack; 1280, 768 and 375, light and dark)
1. On every card that autosaves (Quick tailor, Job preferences, Market, Agent hints), "Saves
   automatically" sits right of the title at 1280 and 768, and below the description at 375. Market shows
   no empty row. The description does not re-wrap while the status goes Saving… to Saves automatically.
2. **Force a failed save.** With `javascript_tool`:
   ```js
   window.__realFetch ??= window.fetch;
   window.fetch = (input, init) =>
     String(input).includes("/api/settings/job-preferences") && init?.method === "PUT"
       ? Promise.resolve(new Response(JSON.stringify({ detail: "forced failure" }),
           { status: 500, headers: { "Content-Type": "application/json" } }))
       : window.__realFetch(input, init);
   ```
   Type in Locations, and the header reads "Not saved" (destructive colour) with **Try again**. Restore
   with `window.fetch = window.__realFetch`, click Try again, and it reads "Saves automatically". Focus is
   on the status, not `<body>` (`document.activeElement`). Repeat on Market (URL `/api/settings/market`):
   "Not saved" appears with no Try again.
3. **Screen-reader order** (`read_page`, one card): heading "Job preferences", then the description, then
   the status, then the first field.
4. **Persona.** With no imported resume, "Draft from my career" is dimmed but focusable, and its reason
   is read (`aria-describedby`). With a resume, click it: focus stays on the button through the request.
   At 375 the button sits under the description.

### Risks
- **Every autosave card's status paints one frame late** (the slot fills after the first commit). A
  skeleton covers it on first load, so only a card that mounts with data in the cache shows it. That is
  one frame.
- **Two slots per card are not supported.** A second `SettingCardAction` in the same card renders beside
  the first, and nothing separates them. The Model catalog has one action group, so this is fine today.

---

## C7: the Models card splits into Models, Model catalog and Custom endpoint

### Current code
- `models-section.tsx:73-162`, `ModelsSection`: one card holding:
  - `ModelProfileNote`;
  - the three `ModelField`s (:121-146), whose Chat label packs its hint into the label: "Chat model ·
    needs streaming tool calls, so test it";
  - `EndpointControls`, `CapabilityMatrix` and `ModelCatalogPanel`, each behind its own `border-t pt-3`.
- `llm-endpoint.tsx:148-218`, `CapabilityMatrix`: lists the de-duplicated role models by **id**, with
  Text/JSON/Tools and a Test button whose label becomes a bare spinner (:206-210).
- `model-catalog-panel.tsx:184-221`, `CatalogRow`:
  - name and mono id side by side (:199-202);
  - `capitalize` on the raw provider, plus `" · seed"`/`" · in use"` (:203-206), which renders "Openai ·
    Seed";
  - `text-destructive` ghost trash (:208-217).

  The select items repeat the name/id pair (`models-section.tsx:454-458`).
- **The discovery box** (:147-179) is a bordered box inside a card (`rounded-lg border p-3`). That breaks
  `CardSection`'s one-drawn-level rule (`card.tsx:97-109`). Its copy joins clauses with an em dash
  ("… discovery — + adds …"), which the microcopy rule forbids.

### New pure helpers: `frontend/lib/model-catalog.ts` (verified 3/3 with its test)

```ts
/**
 * How a model catalog row reads (components/settings/model-catalog-panel.tsx). No imports:
 * `node --test` loads it (model-catalog.test.ts). The API sends keys (`openai`, `seed`); the
 * screen shows words.
 */
const PROVIDER_LABELS: Record<string, string> = { openai: "OpenAI", gemini: "Gemini" };

export function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider;
}

/** `source` is absent on older payloads, which means a seed. */
export function sourceLabel(source: "seed" | "extra" | "configured" | undefined): string {
  if (source === "extra") return "Added";
  if (source === "configured") return "In use";
  return "Built-in";
}

/** The id is worth showing only when the name is not already it (a Sync-added OpenAI model is named by its id). */
export function showsModelId(option: { id: string; label: string }): boolean {
  return option.label.trim() !== option.id;
}

/** A model's name for a sentence or an accessible name; the id when the catalog lacks it. */
export function modelName(options: readonly { id: string; label: string }[], id: string): string {
  return options.find((option) => option.id === id)?.label ?? id;
}
```

`frontend/lib/model-catalog.test.ts`:

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { modelName, providerLabel, showsModelId, sourceLabel } from "./model-catalog.ts";

test("provider and source read as words, never keys", () => {
  assert.equal(providerLabel("openai"), "OpenAI");
  assert.equal(providerLabel("gemini"), "Gemini");
  assert.equal(sourceLabel(undefined), "Built-in");
  assert.equal(sourceLabel("seed"), "Built-in");
  assert.equal(sourceLabel("configured"), "In use");
  assert.equal(sourceLabel("extra"), "Added");
});

test("the id shows only when it differs from the name", () => {
  assert.equal(showsModelId({ id: "gpt-5.6-luna", label: "OpenAI GPT-5.6 Luna" }), true);
  assert.equal(showsModelId({ id: "gpt-6-luna", label: "gpt-6-luna" }), false);
  assert.equal(showsModelId({ id: "gpt-6-luna", label: " gpt-6-luna " }), false);
});

test("a model is named by its label, else its id", () => {
  const options = [{ id: "gemini-3.7-flash", label: "Gemini 3.7 Flash" }];
  assert.equal(modelName(options, "gemini-3.7-flash"), "Gemini 3.7 Flash");
  assert.equal(modelName(options, "llama3.2:3b"), "llama3.2:3b");
});
```

The labels come from the backend:
- Seeds carry curated labels (`services/model_settings.py:27-39`).
- A Sync-added OpenAI model's label **is** its id (`services/llm.py:446`).
- Gemini discovery carries display names (:481).
- A configured-only id's label is its id (`model_settings.py:256`).

So `showsModelId` is true for the three seeds and for Gemini extras only.

### File layout (paths are kept, so no pin changes path)

- `models-section.tsx`: `ApiKeysSection`, `ModelsSection` (pickers plus the per-role capability line),
  `useOpenAIInfo`, `useSaveModelSettings`, `ModelField`/`FreeTextModel`/`ModelSelect`, and the moved
  `CAPABILITY_LABELS`.
- `model-catalog-panel.tsx`: `ModelCatalogSection` (a `SettingCard`) around the existing panel.
- `llm-endpoint.tsx`: `CustomEndpointSection` (a `SettingCard`) plus `EndpointControls` and
  `isRemoteEndpoint`. `CapabilityMatrix` is deleted.

### Models card (`models-section.tsx`, replacing `ModelsSection`'s render at :109-161)

```tsx
const ROLES = [
  { key: "fast_model", label: "Fast model", hint: "Reads postings and runs bulk work.", patch: (v: string) => ({ fast_model: v }) },
  { key: "smart_model", label: "Smart model", hint: "Tailors resumes and finds gaps.", patch: (v: string) => ({ smart_model: v }) },
  { key: "chat_model", label: "Chat model", hint: "Runs the in-app assistant, which needs tool calls.", patch: (v: string) => ({ chat_model: v }) },
] as const;

// CAPABILITY_LABELS moves here unchanged from llm-endpoint.tsx:18-23 (with its docstring).

// in ModelsSection:
<SettingCard
  id="models"
  title="Models"
  description="Which model does each job. Test a model to see what it can do."
  errorTitle="Couldn't load your model settings."
  skeleton="h-48 w-full"
  query={info}
>
  {(data) => (
    <div className="grid gap-6">
      <ModelProfileNote />
      <div className="grid gap-4 @2xl/setting:grid-cols-3">
        {ROLES.map((role) => (
          <RoleModel
            key={role.key}
            role={role}
            info={data}
            disabled={save.isPending}
            probing={probing}
            onChange={(value) => value && save.mutate(role.patch(value))}
            onProbe={(model) => probe.mutate(model)}
          />
        ))}
      </div>
      <p className="text-muted-foreground text-xs">
        Measured, not assumed. A model that cannot call tools still works everywhere except chat.
      </p>
    </div>
  )}
</SettingCard>

function RoleModel({ role, info, disabled, probing, onChange, onProbe }: {
  role: (typeof ROLES)[number];
  info: OpenAIInfo;
  disabled: boolean;
  probing: string | null;
  onChange: (value: string | null) => void;
  onProbe: (model: string) => void;
}) {
  const hintId = useId();
  const model = info[role.key];
  return (
    <div className="grid content-start gap-1.5">
      <ModelField
        label={role.label}
        hint={role.hint}
        hintId={hintId}
        value={model}
        options={info.model_options}
        custom={info.custom_endpoint}
        disabled={disabled}
        onChange={onChange}
      />
      <ModelCapability
        report={info.capabilities[model]}
        name={modelName(info.model_options, model)}
        probing={probing === model}
        busy={probing !== null}
        onProbe={() => onProbe(model)}
      />
    </div>
  );
}

/** The chosen model's measured Text/JSON/Tools, under its picker. A model two roles share shows in both. */
function ModelCapability({ report, name, probing, busy, onProbe }: {
  report: CapabilityReport | undefined;
  name: string;
  probing: boolean;
  busy: boolean;
  onProbe: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      {report ? (
        // The map body is the <span key={key} title=…> from llm-endpoint.tsx:176-195, unchanged.
        CAPABILITY_LABELS.map(({ key, label, gates }) => <CapabilityMark key={key} ok={report[key] === true} label={label} gates={gates} error={report.errors[key]} />)
      ) : (
        <span className="text-muted-foreground">Not tested</span>
      )}
      <Button
        type="button"
        size="xs"
        variant="ghost"
        focusableWhenDisabled
        disabled={busy}
        aria-label={`Test ${name}`}
        className="data-disabled:pointer-events-none data-disabled:opacity-50"
        onClick={onProbe}
      >
        {probing ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}
        Test
      </Button>
    </div>
  );
}
```

`CapabilityMark` is the `<span>` at `llm-endpoint.tsx:179-195`, extracted with no change to its classes,
its `title` or its Check/X icons.

`ModelField`, `FreeTextModel` and `ModelSelect` take `hint` and `hintId`. They render
`<p id={hintId} className="text-muted-foreground text-xs">{hint}</p>` between the `Label` and the
control, and pass `aria-describedby={hintId}` to `SelectTrigger`/`Input`. That follows the rule that hint
text sits between the label and the control. Drop the Label overrides `text-muted-foreground text-xs
font-normal` (:387, :437), per C8's label rule. The `SelectItem` body at :454-458 becomes:

```tsx
<SelectItem key={option.id} value={option.id}>
  <span className="grid">
    <span>{option.label}</span>
    {showsModelId(option) ? (
      <span className="text-muted-foreground font-mono text-xs">{option.id}</span>
    ) : null}
  </span>
</SelectItem>
```

The name/id pair is never side by side. The id is secondary text under the name, and only when it says
something the name does not. `SelectValue` already renders `selected?.label` (:442).

### Model catalog card (`model-catalog-panel.tsx`)

```tsx
export function ModelCatalogSection() {
  const info = useOpenAIInfo();
  return (
    <SettingCard
      id="model-catalog"
      title="Model catalog"
      description="The models the pickers offer: built-in ones, plus any you add with Sync."
      errorTitle="Couldn't load the model catalog."
      skeleton="h-32 w-full"
      query={info}
    >
      {(data) => <ModelCatalogPanel info={data} />}
    </SettingCard>
  );
}
```

Changes inside `ModelCatalogPanel`:
- **The Sync pair moves into the header.** Replace :98-134 with the block below. `syncing` and `sync`
  stay in the body.

```tsx
<SettingCardAction>
  {(["openai", "gemini"] as const).map((provider) => (
    <Button
      key={provider}
      size="sm"
      variant="outline"
      focusableWhenDisabled
      disabled={syncing !== null}
      className="data-disabled:pointer-events-none data-disabled:opacity-50"
      onClick={() => sync.mutate(provider)}
    >
      {syncing === provider ? (
        <Loader2 className="size-3 animate-spin" aria-hidden="true" />
      ) : (
        <RefreshCw className="size-3" aria-hidden="true" />
      )}
      Sync {providerLabel(provider)}
    </Button>
  ))}
</SettingCardAction>
```

- **The list** (:136-145) becomes `<ul ref={listRef} tabIndex={-1} aria-label="Available models"
  className="divide-y outline-none">`. There is no `max-h`/`overflow-y-auto` any more: the catalog is its
  own card now, and a nested scroller inside a scrolling page was the old compromise.
- **A row** (`CatalogRow`, :197-220):

```tsx
<li className="flex min-h-10 items-center gap-3 py-1.5">
  <div className="min-w-0 flex-1">
    <p className="truncate text-sm font-medium">{option.label}</p>
    {showsModelId(option) ? (
      <p className="text-muted-foreground truncate font-mono text-xs">{option.id}</p>
    ) : null}
  </div>
  <span className="text-muted-foreground shrink-0 text-xs">
    {providerLabel(option.provider)} · {sourceLabel(option.source)}
  </span>
  {option.source === "extra" ? (
    <RemoveButton
      label={`Remove ${option.id}`}
      disabled={busy}
      onClick={(event) => onRemove(event.currentTarget.closest("li"))}
    />
  ) : null}
</li>
```

  `RemoveButton` is defined in C8's `setting-layout.tsx`. It is a ghost `IconButton` (`icon-sm`, 28px, and
  44px on a coarse pointer) that turns destructive only on hover or focus. It is `focusableWhenDisabled`,
  because all Remove buttons disable while one removal runs.
- **Focus after a removal.** The row, and the focused button with it, unmounts once `setQueryData` lands
  (:79-80). Arm a successor in the click and focus it after the list re-renders:

```tsx
const listRef = useRef<HTMLUListElement>(null);
const leaving = useRef<(() => HTMLElement | null) | null>(null);
// in remove: onError: (err) => { leaving.current = null; toast.error(err.message); }
useEffect(() => {
  const next = leaving.current;
  if (!next) return;
  leaving.current = null;
  focusIfDropped(next());
}, [info.model_options]);

const removeRow = (li: HTMLElement | null, id: string) => {
  // The next row's Remove, else the previous row's, else the list itself (seed rows have no button).
  const pick = (el: Element | null | undefined) => el?.querySelector<HTMLElement>("button") ?? null;
  const neighbour = pick(li?.nextElementSibling) ?? pick(li?.previousElementSibling);
  leaving.current = () => (neighbour?.isConnected ? neighbour : listRef.current);
  remove.mutate(id);
};
```

  (`focusSuccessor` in `lib/focus.ts` falls back to a sibling's `focusTarget`. For a seed row with no
  button, that returns the non-focusable `<li>`, so this list names its own fallback.)
- **Discovery** (:147-179) becomes a `CardSection className="grid gap-3"`, so it is tonal with no
  border:
  - Copy: `<p className="text-muted-foreground text-xs">Models {providerLabel(discovery.provider)}
    offers. Add one to the catalog, then choose it under Fast, Smart or Chat.</p>`.
  - The list keeps `max-h-72 overflow-y-auto` (a Sync can return 100+ ids) and becomes `divide-y`.
  - The `+` stays **the same element** when it flips to added, so focus is kept:

```tsx
<Button
  size="icon-sm"
  variant="ghost"
  focusableWhenDisabled
  disabled={model.in_catalog || add.isPending}
  aria-label={model.in_catalog ? `${model.id} added` : `Add ${model.id}`}
  className="data-disabled:pointer-events-none data-disabled:opacity-50"
  onClick={() => add.mutate(model)}
>
  {model.in_catalog ? <Check aria-hidden="true" /> : <Plus aria-hidden="true" />}
</Button>
```

### Custom endpoint card (`llm-endpoint.tsx`)

```tsx
export function CustomEndpointSection() {
  const info = useOpenAIInfo();
  const save = useSaveModelSettings(() => toast.success("Endpoint settings saved"));
  return (
    <SettingCard
      id="custom-endpoint"
      title="Custom endpoint"
      description="Run models on your own server, such as Ollama or LM Studio."
      errorTitle="Couldn't load your endpoint settings."
      skeleton="h-10 w-full"
      query={info}
    >
      {(data) => (
        <EndpointDisclosure info={data} disabled={save.isPending} onSave={(patch) => save.mutate(patch)} />
      )}
    </SettingCard>
  );
}

/** Most installs never touch this, so it starts collapsed unless something is set. `hidden`, not
 *  unmounted: a typed endpoint draft survives a collapse. */
function EndpointDisclosure({ info, disabled, onSave }: {
  info: OpenAIInfo;
  disabled: boolean;
  onSave: (patch: { base_url?: string | null; json_mode?: string }) => void;
}) {
  const [open, setOpen] = useState(Boolean(info.base_url) || info.json_mode !== "auto");
  const panelId = useId();
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted-foreground min-w-0 text-sm wrap-anywhere">
          {info.base_url ? (
            <>
              Using <code className="font-mono text-xs">{info.base_url}</code>
            </>
          ) : (
            "Not set. Models run on the OpenAI and Gemini APIs."
          )}
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((o) => !o)}
        >
          <ChevronRight className={cn("transition-transform", open && "rotate-90")} aria-hidden="true" />
          Advanced
        </Button>
      </div>
      <div id={panelId} hidden={!open}>
        <EndpointControls info={info} disabled={disabled} onSave={onSave} />
      </div>
    </div>
  );
}
```

In `EndpointControls` (:65-145):
- The root `space-y-3 border-t pt-3` becomes `grid gap-4 @xl/setting:grid-cols-[2fr_1fr]`, and the inner
  :67 grid goes.
- Both hint `<span … block>` elements become `<p>`.
- The Label overrides are dropped (C8).

### Pins (section "Models")

```python
_MODELS = _read("components/settings/models-section.tsx")
_CATALOG = _read("components/settings/model-catalog-panel.tsx")
_ENDPOINT = _read("components/settings/llm-endpoint.tsx")
_MODEL_LIB = _read("lib/model-catalog.ts")


def test_models_catalog_and_endpoint_are_three_cards():
    assert 'id="models"' in _MODELS and 'id="api-keys"' in _MODELS
    assert "<SettingCard" in _CATALOG and 'id="model-catalog"' in _CATALOG
    assert "<SettingCard" in _ENDPOINT and 'id="custom-endpoint"' in _ENDPOINT
    assert "<ModelCatalogPanel" not in _MODELS and "<EndpointControls" not in _MODELS
    assert "CapabilityMatrix" not in _ENDPOINT + _MODELS
    assert "border-t" not in _MODELS + _CATALOG + _ENDPOINT


def test_each_chosen_model_shows_its_capabilities_and_a_named_test():
    assert "<ModelCapability" in _MODELS
    test = _MODELS[_MODELS.index("function ModelCapability") :]
    assert "aria-label={`Test ${name}`}" in test
    assert "focusableWhenDisabled" in test and "data-disabled:opacity-50" in test
    # The label stays: a bare spinner left the button with no name while it probed.
    assert "Test\n" in test[test.index("aria-label={`Test ${name}`}") :]


def test_the_catalog_reads_words_not_keys():
    assert "capitalize" not in _CATALOG
    assert '" · seed"' not in _CATALOG and '" · in use"' not in _CATALOG
    assert "providerLabel(option.provider)} · {sourceLabel(option.source)}" in _CATALOG
    assert "showsModelId(option) ?" in _CATALOG and "showsModelId(option) ?" in _MODELS
    assert "rounded-lg border p-3" not in _CATALOG  # second containment level is tonal
    assert "discovery —" not in _CATALOG
    assert "import " not in _MODEL_LIB
    assert '{ openai: "OpenAI", gemini: "Gemini" }' in _MODEL_LIB
    assert 'return "Built-in";' in _MODEL_LIB


def test_sync_lives_in_the_card_header():
    header = _CATALOG[_CATALOG.index("<SettingCardAction>") : _CATALOG.index("</SettingCardAction>")]
    assert "sync.mutate(provider)" in header and "focusableWhenDisabled" in header


def test_a_removed_model_hands_focus_to_a_neighbour_or_the_list():
    assert "<RemoveButton" in _CATALOG and "label={`Remove ${option.id}`}" in _CATALOG
    assert "text-destructive size-7" not in _CATALOG
    assert "leaving.current = () => (neighbour?.isConnected ? neighbour : listRef.current);" in _CATALOG
    assert "focusIfDropped(next());" in _CATALOG
    assert '<ul ref={listRef} tabIndex={-1} aria-label="Available models"' in _CATALOG


def test_the_endpoint_starts_collapsed_and_keeps_its_draft():
    assert "useState(Boolean(info.base_url) || info.json_mode !== \"auto\")" in _ENDPOINT
    assert "aria-expanded={open}" in _ENDPOINT and "aria-controls={panelId}" in _ENDPOINT
    assert "hidden={!open}" in _ENDPOINT
```

Add `"llm-endpoint.tsx"` and `"model-catalog-panel.tsx"` to `_SETTINGS_CARDS` in
`test_frontend_query_error_states.py:122-134`. Both now render through `SettingCard`, so they must never
hand-roll a header.

### Existing pins affected
- `test_frontend_placeholders.py:682-685`: `placeholder="e.g. http://host.docker.internal:11434/v1"` stays
  in `llm-endpoint.tsx`, and `placeholder="e.g. llama3.2:3b"` stays in `models-section.tsx`
  (`FreeTextModel`). No change.
- `test_frontend_placeholders.py:508-520` (`test_saved_key_is_a_hint_not_a_placeholder`): the regex
  `r'className="grid items-end gap-3 sm:grid-cols-2">\s*<KeyField'` becomes
  `r'className="grid items-end gap-4 @lg/setting:grid-cols-2">\s*<KeyField'` (C8's API keys row).
- `test_frontend_color_roles.py:833`: the literal `"font-medium text-emerald-700 dark:text-emerald-400"`
  must stay byte-identical in `models-section.tsx` (`KeyField`'s status). C8 leaves that span's classes
  alone.
- `test_frontend_first_run.py:147-154`: `useSaveModelSettings` still invalidates `["setup-status"]`, so
  it is unchanged.
- `test_frontend_focus.py:396-410`: add rows `(_read("components/settings/model-catalog-panel.tsx"),
  "sync.mutate(provider)")` and `(_read("components/settings/models-section.tsx"),
  "aria-label={`Test ${name}`}")`, with ids `"sync"` and `"model-test"`. `_button_with` (:379-382) finds
  the enclosing `<Button`. It cannot see `RemoveButton`, which is an `<IconButton`, so C8's layout pin
  asserts that one directly.

### Browser checks (1280, 768 and 375, light and dark)
1. **AI & models shows five cards in order:** API keys, Models, Model catalog, Custom endpoint, Prompts.
2. **Models**:
   - At 1280 there are three columns. Each has a label, a one-line hint, a picker, and under it the
     chosen model's Text/JSON/Tools plus Test.
   - At 768 and 375 the columns stack.
   - A model shared by two roles shows its result in both.
   - Test on a model: its button keeps the name "Test <name>" and focus while it runs, and the others
     dim.
   - "Which models did you measure?" still opens its note.
3. **Catalog**:
   - Rows read "OpenAI · Built-in" and "Gemini · Built-in". There is no "Openai · Seed".
   - A seed shows its name, with the id beneath in mono. A Sync-added OpenAI id shows once.
   - The Remove icon is muted at rest and destructive on hover and focus.
   - The accessibility tree names it "Remove gpt-…".
   - Remove the middle extra of three with the keyboard: focus lands on the next row's Remove. Remove the
     last extra: focus lands on the previous extra's Remove, or on the list if no extra is left.
   - Sync OpenAI: the header buttons dim, focus stays on the one pressed, and the discovery section
     appears in a tonal box. Press + on one discovered model with the keyboard: the same button turns to
     a check, reads "<id> added", and keeps focus.
4. **Custom endpoint**:
   - Collapsed on a fresh install. **Advanced** has `aria-expanded` false then true.
   - Type a URL, collapse, then expand: the draft is still there.
   - Set an endpoint and reload: the card starts expanded and reads "Using …".
   - A remote URL still shows the amber warning.
   - With a custom endpoint set, the three pickers become free-text inputs.
5. **Dropdowns** list names, with an id beneath only for seeds and Gemini extras.

### Risks
- **Three cards read `["settings", "openai"]`.** A failed load shows three "Couldn't load…" states, each
  with its own retry. Any retry refetches the one shared query, so all three recover together.
- **Endpoint and model saves no longer share one `isPending`.** Two PUTs can overlap. The backend applies
  omitted fields as "leave alone" (`models-section.tsx:45-52` docstring), so they cannot overwrite each
  other's fields.

---

## C8: one vertical rhythm across every settings and profile card

### The rhythm (document it as a new conventions bullet, C9)

| # | Element | Classes | Replaces |
|---|---|---|---|
| R1 | Card shell | `Card`'s own `gap-4 py-4` (header to body 16px); `CardHeader`'s `gap-1` | unchanged |
| R2 | Body stack: the blocks of one card | `grid gap-6` | `space-y-3/4/5`, `mb-*`, `mt-*`, a `<>` with no gap |
| R3 | Fields in a block | `grid gap-4`; two columns only at `@lg/setting:grid-cols-2` (body ≥ 32rem), three at `@2xl/setting:grid-cols-3` (≥ 42rem) or `@3xl` (Autofill) | `gap-3`; viewport `sm:`/`lg:` columns |
| R4 | One field | `grid gap-1.5`: `Label`, then hint `p.text-muted-foreground.text-xs` with `aria-describedby`, then the control | unchanged (conventions: "A field row is `grid gap-1.5`") |
| R5 | Field labels | the `Label` default (`text-sm font-medium`), no size or colour override | `text-xs`; `text-muted-foreground text-xs font-normal` (open question 3) |
| R6 | Switch list | `divide-y` of `SwitchRow` (`flex min-h-11 items-center justify-between gap-4 py-1.5`) | rows with `px-3 py-2.5` inside `space-y-3` |
| R7 | Titled groups | only a long form earns them: `fieldset` (block flow, `space-y-4`) + `legend` in `GROUP_HEADING`, groups `gap-8`, **no rules** | `border-t pt-3` rules, `[&>fieldset~fieldset>legend]:border-t` |
| R8 | Actions row (Save/Discard) | last child of the stack: `flex flex-wrap items-center justify-end gap-2`, secondary before primary | `justify-between`, left-aligned `gap-3`, `mt-3` |
| R9 | A second containment level | `CardSection` (tonal, no border) | `rounded-lg border p-3`, `border-t` inside a `CardSection` |

The two column widths are measured, not guessed. `SettingCard`'s `CardContent` gets `@container/setting`
(C6):
- At 1280, with the sidebar pinned (256px), the body is about 944px.
- At 768 it is about 432px. The conventions call this band "the layout's worst case": 512 minus p-6 minus
  the card's `px-4`.
- At 375 it is about 295px.

Two columns start at 512px, so every card is one column at 768 and at 375. Viewport `sm:grid-cols-2`
gave API keys two 208px columns at 768. In each, "OpenAI API key" and "Configured · in-app" had to share
208px.

**The fieldset rule (R7) is a finding.** A `<fieldset>` is kept in block flow because its rendered
`<legend>` is laid out outside the anonymous content box. It is not a grid or flex item, so `gap` on a
grid fieldset never separates the legend from the first field. Tailwind 4's `space-y-4` sets
`margin-block-end` on every child but the last, which includes the legend. That is why Autofill's
`space-y-3` fieldsets work today.

### New file: `frontend/components/settings/setting-layout.tsx`

```tsx
"use client";

import type { MouseEventHandler, ReactNode } from "react";
import { Trash2 } from "lucide-react";

import { IconButton } from "@/components/icon-button";
import { Label } from "@/components/ui/label";

/** Group headings: the Career KB read view's uppercase tracked style (frontend-conventions,
 *  "A long form is divided by group headings"). Autofill's legends use it. */
export const GROUP_HEADING =
  "text-muted-foreground text-xs font-semibold tracking-[0.12em] uppercase";

/** The last row of a card body: Save and its siblings, right-aligned, secondary first. */
export const ACTION_ROW = "flex flex-wrap items-center justify-end gap-2";

/** A labelled switch. 44px tall, so the label (which toggles it) is a full-size target. */
export function SwitchRow({ htmlFor, label, children }: { htmlFor: string; label: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-11 items-center justify-between gap-4 py-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}

/**
 * Remove one entry. Muted at rest and destructive only on hover or focus: a column of solid red icons
 * shouted "danger" at every row. Stays focusable while a removal runs (every Remove disables together).
 */
export function RemoveButton({ label, disabled, onClick }: {
  label: string;
  disabled?: boolean;
  onClick: MouseEventHandler<HTMLButtonElement>;
}) {
  return (
    <IconButton
      label={label}
      icon={<Trash2 />}
      focusableWhenDisabled
      disabled={disabled}
      className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive focus-visible:text-destructive data-disabled:pointer-events-none data-disabled:opacity-50 dark:hover:bg-destructive/20 shrink-0"
      onClick={onClick}
    />
  );
}
```

`text-destructive` over `bg-destructive/10` and `/20` is inside the tints
`test_frontend_color_roles.py` already measures (`_DESTRUCTIVE_WORST`, :452-456). The hover fill is not a
new pair.

### Per card: current spacing and target (all at `8cac7cf9`)

| Card (file) | Current (file:line → classes) | Target |
|---|---|---|
| **API keys** (`models-section.tsx`) | :224 `space-y-3`; :227 `grid items-end gap-3 sm:grid-cols-2`; :247 footer `flex items-center justify-between` holding "Leave blank to use defaults from .env.", which repeats the card description; :296 `flex items-center justify-between text-xs`; :297 Label `text-muted-foreground text-xs font-normal` | :224 `grid gap-6`; :227 `grid items-end gap-4 @lg/setting:grid-cols-2`; :247 `ACTION_ROW` with only Save (delete the duplicate sentence); :296 `flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5 text-xs`; :297 plain `<Label id={labelId}>`. Keep the status span's classes byte-identical (pinned). |
| **Models** (`models-section.tsx`) | :119 `space-y-4 text-sm`; :121 `grid gap-3 sm:grid-cols-3`; :185 note `mt-2 max-w-prose`; :386, :436 fields `grid gap-1.5` with Labels `text-muted-foreground text-xs font-normal` | C7's code: `grid gap-6`, `grid gap-4 @2xl/setting:grid-cols-3`, role column `grid content-start gap-1.5`. The note's disclosure is a `grid gap-2`, with no `mt-2`. |
| **Model catalog** (`model-catalog-panel.tsx`) | :97 `space-y-3 border-t pt-3`; :98 sub-header; :136 `max-h-48 space-y-1 overflow-y-auto text-xs`; :148 `space-y-2 rounded-lg border p-3`; :154 `max-h-56 space-y-1 overflow-y-auto`; :198 row `flex items-center gap-2` | body `grid gap-4`; header action (C6); list `divide-y`, rows `flex min-h-10 items-center gap-3 py-1.5`; discovery `CardSection className="grid gap-3"`, list `max-h-72 divide-y overflow-y-auto` |
| **Custom endpoint** (`llm-endpoint.tsx`) | :66 `space-y-3 border-t pt-3`; :67 `grid gap-3 sm:grid-cols-[2fr_1fr]`; :76, :114 `span … block`; :80 `flex gap-2` | `grid gap-4` (disclosure row, then panel); controls `grid gap-4 @xl/setting:grid-cols-[2fr_1fr]`; hints `<p>`; `flex gap-2` kept |
| **Prompts** (`prompts-section.tsx`) | :67 `space-y-3`; :76 `pt-1`; :79 toggle, no `aria-expanded`; :89 `{advancedOpen && …}` **unmounts drafts**; :90 `mt-3 space-y-3`; :159 PromptCard toggle `p-3`, no `aria-expanded`; :177 `space-y-2 border-t p-3`; :188 `flex gap-2` | root `grid gap-3` (a list of collapsible items); Advanced `grid gap-3`, its toggle `aria-expanded`/`aria-controls`, and the list `<div id=… hidden={!advancedOpen} className="grid gap-3">` (always mounted); PromptCard toggle `aria-expanded={open}` + `aria-controls`; open body `grid gap-3 px-3 pb-3` (no `border-t`); buttons `ACTION_ROW` ("Reset to default" then "Save") |
| **Quick tailor** (`quick-tailor-section.tsx`) | :88 `space-y-5`; :89 `AutosaveRow`; :93 `space-y-3`; :97-111 rows `px-3 py-2.5`; :116 `grid gap-1.5`; :117 Label `text-xs` | status → header (C6); root `grid gap-6`; switches `<div className="divide-y">{SWITCH_ROWS.map(… <SwitchRow htmlFor={id} label={row.label}><Switch …/></SwitchRow>)}</div>`; instruction field `grid gap-1.5` with plain `Label optional` |
| **Auto-apply** (`auto-apply-section.tsx`) | :128 `space-y-4`; :129 `grid gap-4 sm:grid-cols-2`; :156 `max-w-[10rem]`; :168 chips `flex flex-wrap gap-1.5`; :178 chip × `rounded-full px-1` (a ~16px target); :193 `flex max-w-sm gap-2`; :212 `flex items-center gap-3` with Save then **Cancel** | root `grid gap-6`; :129 `grid gap-4 @lg/setting:grid-cols-2`; `max-w-[10rem]` kept; chip × → `IconButton size="icon-xs" label={\`Remove ${name} from blocklist\`} icon={<X />}` (24px, 44px coarse, meeting WCAG 2.5.8); :212 `ACTION_ROW` with **Discard** (renamed; nothing is cancelled) then Save |
| **Agent hints** (`mcp-workflow-section.tsx`) | :61 fragment; :62 `AutosaveRow`; :66 row `px-3 py-2.5` | status → header; body is one `<SwitchRow htmlFor={id} label="Suggest the next step in MCP tool results">` |
| **Appearance** (`appearance-section.tsx`) | :57 row `flex items-center justify-between gap-4 px-3 py-2.5` | `<SwitchRow htmlFor={id} label="Dark mode">`; `CardTitle role="heading" aria-level={2}` |
| **About** (`about-section.tsx`) | :59 `divide-y`; :34, :64, :68 rows `flex items-baseline justify-between gap-4 px-3 py-2.5` | `<dl className="divide-y">`; rows `<div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5"><dt className="text-muted-foreground text-sm">…</dt><dd className="min-w-0 text-sm wrap-anywhere">…</dd></div>`, so a 40-character Git SHA wraps at 375 instead of overflowing |
| **Persona** (`persona-section.tsx`) | :123 `mb-3 flex justify-end` (Draft); :147 `mt-3 flex items-center justify-end gap-2` | Draft → header (C6); root `grid gap-4`: optional reason `<p>`, Textarea, and while dirty `ACTION_ROW` (Discard, Save) |
| **Market** (`market-section.tsx`) | :69 `grid gap-4` + :70 `AutosaveRow` (`mb-4`), a 32px row with only the status; :73 `grid max-w-sm gap-1.5`; :104 note `border-muted border-l-2 pl-3 text-xs` | status → header; root `grid gap-4`; field unchanged; note `text-muted-foreground max-w-prose text-xs` with no border rule |
| **Job preferences** (`job-preferences-section.tsx`) | :142 `space-y-5`; :143 `AutosaveRow`; :147, :161, :189, :222, :249, :267 Labels `text-xs`; :159 `grid gap-4 sm:grid-cols-2` | status → header; root `grid gap-6`; :159 `grid items-start gap-4 @lg/setting:grid-cols-2`; Labels plain `Label optional`; employment group unchanged (`test_employment_types_carry_their_state`) |
| **Autofill** (`autofill-section.tsx`, 971 lines) | :58-59 `LEGEND`; :703 root `space-y-6 [&>fieldset~fieldset>legend]:border-t [&>fieldset~fieldset>legend]:pt-6`; :724, :851, :899 fieldsets `space-y-3`; :748 permissions `CardSection … space-y-2 border-l-2 px-3 py-2.5`; :753, :775 `space-y-0.5`; :800 `grid gap-3 sm:grid-cols-2 lg:grid-cols-3`; :807, :863 Labels `text-xs`; :857 education `CardSection flex items-start gap-2` with inner :858 `grid flex-1 gap-3 sm:grid-cols-3`; :906-907 custom `flex items-start gap-2` / `grid flex-1 gap-1.5`, the question with **no visible label** and the answer's Label `mt-1.5 text-xs`; :883-890 and :939-946 ghost Trash `icon-sm` with repeated names ("Remove education entry" on every row); :959 `flex justify-end` | `LEGEND = cn(GROUP_HEADING, "flex w-full items-center justify-between gap-2")`; root `grid gap-8` (**no rules**); fieldsets `space-y-4` (block flow, R7); permissions `CardSection className="border-primary/40 grid gap-3 border-l-2 px-3 py-2.5"` (the accent is deliberate, :742-747) with rows' text blocks `grid gap-1`; fields `grid gap-4 @lg/setting:grid-cols-2 @3xl/setting:grid-cols-3`; Labels plain; education `CardSection className="flex items-start gap-2"` with inner `grid flex-1 gap-4 @xl/setting:grid-cols-3`; custom: pair `grid flex-1 gap-3` of two `grid gap-1.5` rows, adding `<Label htmlFor={\`af-custom-${i}-question\`}>Question</Label>` + `id` on the Input (keep its `aria-label`, which contains "question"), and "Answer" Label without `mt-1.5`; removes → `RemoveButton label={\`Remove education entry ${i + 1}\`}` / `\`Remove custom question ${i + 1}\``; after a remove, `armFocus(addEducationRef)` / `armFocus(addQuestionRef)` through `useFocusOnNextCommit` (the row, and its focused button, unmount); save row `ACTION_ROW` |

Also rewrite Autofill's root comment (:692-702). It describes the old `space-y-6` gap and the
legend `border-top` rule. Left as it is, it trips the rhythm pin: its "space-y-6" sits outside a
fieldset, and "border-top" contains "border-t". The new text states R7 in one sentence. Everything the
Autofill parity pin reads (`test_autofill_groups_parity.py:45-60`, the `GROUPS` block) is untouched. `Input className="h-8 text-sm"` and `SelectTrigger size="sm"` stay: Autofill's density is a
deliberate choice across 30+ fields, not rhythm.

### Pins (section "Rhythm")

```python
_SETTINGS = sorted((_FRONTEND / "components/settings").glob("*.tsx"))


def test_settings_cards_share_one_rhythm():
    """R2 to R9. Spacing is gap on a grid, never margins; columns follow the card's width, not
    the viewport's; groups are headed, never ruled; a label takes no size override."""
    for path in _SETTINGS:
        src = path.read_text()
        name = path.name
        assert "AutosaveRow" not in src, name
        assert re.search(r'className="[^"]*\bm[tby]-\d', src) is None, name
        assert re.search(r"\b(?:sm|md|lg):grid-cols-", src) is None, name
        assert "border-t" not in src, name
        assert re.search(r"<Label\b[^>]*className=\"[^\"]*text-xs", src) is None, name
        for match in re.finditer(r"space-y-\d", src):
            tag = src[src.rfind("<", 0, match.start()) : match.start()]
            assert tag.startswith("<fieldset"), f"{name}: space-y outside a fieldset"
    card = _read("components/settings/setting-card.tsx")
    assert '<CardContent className="@container/setting">' in card


def test_autofill_groups_are_headed_not_ruled():
    src = _read("components/settings/autofill-section.tsx")
    assert "fieldset~fieldset>legend]:border-t" not in src
    assert 'const LEGEND = cn(GROUP_HEADING, "flex w-full items-center justify-between gap-2");' in src
    # A fieldset stays block flow: a legend is not a grid item, so gap never reaches it.
    assert re.search(r"<fieldset[^>]*className=\"[^\"]*\bgrid\b", src) is None
    assert "Remove education entry ${i + 1}" in src and "Remove custom question ${i + 1}" in src


def test_prompt_editors_stay_mounted_and_say_whether_they_are_open():
    src = _read("components/settings/prompts-section.tsx")
    assert "{advancedOpen && (" not in src  # collapsing dropped drafts and their leave guard
    assert "hidden={!advancedOpen}" in src
    assert src.count("aria-expanded=") == 2


def test_switch_rows_and_about_rows_share_their_geometry():
    layout = _read("components/settings/setting-layout.tsx")
    assert 'className="flex min-h-11 items-center justify-between gap-4 py-1.5"' in layout
    for rel in ("quick-tailor-section.tsx", "mcp-workflow-section.tsx", "appearance-section.tsx"):
        assert "<SwitchRow" in _read(f"components/settings/{rel}"), rel
    about = _read("components/settings/about-section.tsx")
    assert '<dl className="divide-y">' in about and "wrap-anywhere" in about
    remove = layout[layout.index("export function RemoveButton") :]
    # Muted at rest, destructive on hover/focus; focusable while every Remove is disabled.
    for cls in ("text-muted-foreground", "hover:text-destructive", "focus-visible:text-destructive"):
        assert cls in remove, cls
    assert "focusableWhenDisabled" in remove and "data-disabled:opacity-50" in remove
```

### Existing pins affected
- `test_frontend_placeholders.py:508-520`: the regex change is in C7.
- `test_frontend_placeholders.py:571-582` (`test_custom_answer_has_a_visible_label_not_a_placeholder`) orders
  the Answer `htmlFor`, then "Answer", then `<Textarea`, then `id=…`, then `aria-label=…`. The new
  Question label sits **before** that sequence, and the Answer row keeps its order. No change.
- `test_frontend_placeholders.py:471-481` (the locations hint order): Job preferences keeps the label, hint,
  `aria-describedby` and `id` order. No change.
- `test_frontend_color_roles.py:215-220` (employment types): unchanged.
- `test_frontend_unsaved_surfaces.py:27-33`: `useLeaveGuard(value !== prompt.value)` stays in PromptCard.
  It now stays registered while Advanced is collapsed, which is the point.

### Browser checks (1280, 768 and 375, light and dark; screenshot each tab at each width)
1. **At 1280**:
   - API keys shows two columns, with each key's status on the label's line.
   - Job preferences shows two columns.
   - Autofill shows three columns.
   - Models shows three columns.
2. **At 768**, every card is one column, and no label/status pair wraps into its input.
3. **At 375**:
   - There is no page horizontal scroll on either page, in any tab
     (`document.documentElement.scrollWidth === innerWidth`).
   - The About Git SHA wraps.
   - Catalog names truncate with "OpenAI · Built-in" and Remove held at the right.
4. **Rhythm.** Measure the header-to-body gap (16px), the gap between blocks (24px), and the gap between
   fields (16px) with `javascript_tool` (`getBoundingClientRect`) on API keys, Job preferences and
   Autofill. Autofill groups sit 32px apart with no rule lines. Each legend reads in the uppercase
   tracked style.
5. **Switch rows.** Click a Quick tailor label: the switch toggles. Each row is at least 44px tall. The
   left edges line up with the Standing instruction label.
6. **Prompts.** Expand Advanced, edit a prompt, collapse Advanced, then click the sidebar's Applications:
   the leave guard asks. Expand again: the text is there. Each toggle's accessibility-tree node shows
   expanded or collapsed.
7. **Autofill removes.** Add two education entries and remove the first with the keyboard: focus lands on
   **Add education**. Screen-reader names read "Remove education entry 1" and "…2".
8. **Auto-apply.** The blocklist × is 24px (44px under touch emulation at 375). Edit a cap, and **Discard**
   appears, not Cancel.

### Risks
- **R5 (labels) changes type**, not only spacing: Job preferences, Autofill and Quick tailor labels grow
  from 12 to 14px. Autofill gets taller. If the owner wants 12px labels kept there, R5 becomes "one size
  per page". That is open question 3.
- **The `divide-y` switch lists drop `px-3`**, so the switches' left edges now align with the field
  labels. This is a visible change from today's indented rows.

---

## C9: words, docs and conventions follow-through

**Backend messages.** No test pins these strings except `tests/test_llm.py:210` (`"Settings" in message`),
which still holds.
- `services/llm.py:93` and `:456`: "Add one under Settings → AI & models → API keys".
- `services/llm.py:96`: "…endpoint under Settings → AI & models → Custom endpoint."
- `app/main.py:87`: the same wording as `llm.py:93`.
- `services/llm_capabilities.py:241`: "Choose a {capability}-capable model in Settings → AI & models".
- `services/knockout.py`, **wrong page today**:
  - :63: "…set your work authorization in Profile → Autofill."
  - :81: "…answer the sponsorship questions in Profile → Autofill."
  - :125: "…set your work authorization in Profile → Autofill."
- `services/job_search_brief.py:80`, **wrong page today**: "…correct the autofill profile in Profile →
  Autofill before relying on them."

**Extension:**
- `panel/actions/fill.js:91`: "No autofill profile yet. Fill it in under Profile → Autofill in Maestro
  CS."
- `extension/INTERNALS.md:311`: "(Profile → Autofill → Eligibility)".
- `extension/INTERNALS.md:274,300` and `extension/README.md:53,56`: "in Profile → Autofill".

**User docs:**
- `README.md`: "Settings → Models" becomes "Settings → AI & models" at :152, :166, :221, :363, :382 and
  :715. At :363 keep "has three slots" (the Models card). At :715, "press **Test**" still matches the
  per-model Test.
- `docs/GETTING_STARTED.md:25,79,87,100,134`: the same change. At :155, "Settings → Quick tailor"
  becomes "Settings → Tailoring".
- `KNOWN_ISSUES.md:77`: "the per-model **Test** button in Settings → AI & models".
- The Claude/Codex "Settings → Extensions/Plugins/Connectors" lines are the client apps' own settings.
  Leave them.

**`docs/frontend-conventions.md`.** These bullets record the old decision. Rewrite them in the same
commit:
- **:621-635, TabsContent bullet.** Add: "Settings and Profile pass `keepMounted` (through
  `SettingsTabs`), so every panel mounts at load and none unmounts on a switch. Unsaved text and
  leave-guard registrations survive a hidden tab. `TabsList` scrolls sideways inside itself (`max-w-full
  overflow-x-auto justify-center-safe`, scrollbar hidden) instead of widening the page."
- **:298-357, leave-guard bullet.** Add: "Page identity is the PATHNAME (`samePage`). Next keeps a page
  mounted across a search or hash change, so a settings tab rewriting `?tab=` is not leaving, and the
  sentinel survives it. A page that remounts on a search change must not rely on this."
- **:839-843, "A long form is divided by rules on the `<legend>`".** Replace with: "**A long form is
  divided by group headings, not rules.** A group is a `<fieldset>` whose `<legend>` uses `GROUP_HEADING`
  (`components/settings/setting-layout.tsx`, the Career KB read view's uppercase tracked style). Groups
  sit `gap-8` apart. The fieldset stays in block flow (`space-y-4`): a rendered legend is not a grid or
  flex item, so `gap` never separates it from the first field. If a rule is ever needed, it goes on the
  legend, because the browser clips a fieldset's block-start border behind a full-width legend."
- **:887-895, Settings vs Profile.** Append: "Each page is tabbed (`lib/settings-tabs.ts`: Settings is AI &
  models, Tailoring, Connected agents, Appearance, About; Profile is About you, Autofill). `?tab=` names
  the tab and the default tab has none. A deep link is `anchorHref(home, cardId)`, which adds the tab, so
  the server renders the right panel; a hash-only link still opens its tab after hydration. A new card
  adds its id to its tab's `anchors` (pinned). An in-page jump to another tab is a button calling
  `useFocusSection()`'s `focus`, never a link."
- **:896-902, SettingCard.** Append: "Its header has one action slot. The body renders into it with
  `SettingCardAction`, a portal, so the controlling state stays in the editor, and a screen reader reads
  the action after the title. The title is a level-2 heading, and `CardContent` is `@container/setting`,
  which every card's column breakpoints read."
- **:903-927, Two save models.** Replace "reports with `AutosaveStatus` inside `AutosaveRow` at the top of
  the card body (never the header — the mutation lives in the editor)" with "reports with
  `AutosaveStatus` in the card header, right of the title, through `SettingCardAction`. The mutation stays
  in the editor, and the status reserves its width (`min-w-36`) so the description never re-wraps."
- **:932-936, Derived setup guidance.** Change "Profile starts with `SetupStatusStrip`, then Persona…,
  Market, Job preferences, and Autofill" to "Profile starts with `SetupStatusStrip` above its tab row;
  About you holds Persona…, Market and Job preferences; Autofill holds the autofill profile."
- **New bullet after :832-835, "Settings rhythm".** Copy the table's R1 to R9 rows in prose, with the
  measured body widths (944, 432 and 295px), and why two columns start at `@lg/setting`.

**SYSTEM.md:** only the §11 item 31 deletion from C5. §7 "Persona draft … Profile puts it into the persona
editor" is still true.

---

## File ownership

**New files:**
- `frontend/lib/settings-tabs.ts` and `settings-tabs.test.ts` (C1): Lane A.
- `frontend/components/settings/settings-tabs.tsx` (C2): Lane A.
- `frontend/lib/model-catalog.ts` and `model-catalog.test.ts` (C7): Lane B.
- `frontend/components/settings/setting-layout.tsx` (C8): Lane B.
- `backend/tests/test_frontend_settings_pages.py`: Lane A writes "Tabs", "Deep links" and "Tab row";
  Lane B writes "Models" and "Rhythm". Or split it into two files.

**Modified by Lane A** (C1 to C5):
- `frontend/app/settings/page.tsx`, `frontend/app/profile/page.tsx`.
- `frontend/components/ui/tabs.tsx`.
- `frontend/lib/use-focus-section.ts`.
- `frontend/lib/leave-guard.ts`, `frontend/lib/leave-guard-history.test.ts`,
  `frontend/components/leave-guard-listeners.tsx`, and optionally `frontend/components/guarded-link.tsx`.
- `frontend/lib/focus.ts`, `frontend/lib/focus.test.ts`.
- `frontend/components/setup/setup-steps.ts`, `frontend/components/setup/getting-started-card.tsx`.
- `frontend/components/job-knockout-card.tsx`, `frontend/app/new/page.tsx`.
- `backend/tests/test_frontend_leave_guard.py`.

**Modified by Lane B** (C6 to C8):
- `frontend/components/settings/`: `setting-card.tsx`, `autosave-status.tsx`, `models-section.tsx`,
  `model-catalog-panel.tsx`, `llm-endpoint.tsx`, `quick-tailor-section.tsx`, `auto-apply-section.tsx`,
  `mcp-workflow-section.tsx`, `prompts-section.tsx`, `appearance-section.tsx`, `about-section.tsx`,
  `persona-section.tsx`, `market-section.tsx`, `job-preferences-section.tsx`, `autofill-section.tsx`.
- `backend/tests/`: `test_frontend_settings_autosave.py`, `test_frontend_query_error_states.py`,
  `test_frontend_placeholders.py`, `test_frontend_focus.py`.

**Shared seam:**
- The pages import `ModelCatalogSection` and `CustomEndpointSection` (Lane B) and render them inside
  `SettingsTabs` (Lane A). Land Lane B's exports first, or have Lane A stub them.
- `settings-tabs.tsx` imports `focusIfStranded` from `lib/focus.ts` (Lane A).

**Modified in C9, after both lanes:**
- Backend: `backend/app/services/llm.py`, `backend/app/main.py`, `backend/app/services/llm_capabilities.py`,
  `backend/app/services/knockout.py`, `backend/app/services/job_search_brief.py`.
- Extension: `extension/panel/actions/fill.js`, `extension/INTERNALS.md`, `extension/README.md`.
- User docs: `README.md`, `docs/GETTING_STARTED.md`, `KNOWN_ISSUES.md`.
- Reference: `docs/frontend-conventions.md`, and SYSTEM.md §11 item 31.

## Open questions for the planner

1. **The machine change (C4) is a precondition for writing `?tab=` into the URL.** The fallback, if the
   owner will not touch `lib/leave-guard.ts`, is job-page parity: read `?tab=` on arrival and never write
   it. That keeps Back/Forward exactly as it is, but a reload loses the tab. Also: take the optional
   GuardedLink same-page change? Without it, a link to another tab of the same page asks "Leave without
   saving?" while nothing is leaving.
2. **Connected agents order:** MCP explainer, then Agent workflow hints, then Auto-apply (proposed: the
   explainer says what an agent is, the hints are its switch, and auto-apply bounds its lane)? Or
   Auto-apply first, as the page orders it today (:57-58)?
3. **R5 (labels).** Normalize every settings label to the `Label` default (14px), or keep 12px on
   Autofill, Job preferences and Quick tailor? The type-scale bullet says "meta/labels `text-xs`", but
   the primitive's default is `text-sm`, and today the cards split between the two.
4. **Catalog ids.** The id as a second mono line (proposed, readable by keyboard and screen reader), or
   only a `title` tooltip on the name (owner's alternative, invisible without a pointer)?
5. **Show unsaved work on a hidden tab.** A hidden tab with unsaved work gives the user no sign. The
   leave question fires, but the user cannot see which tab holds the edit. A dot on the tab needs the
   registry to know panels, which is new state. Worth a follow-up, or not?
6. **Custom endpoint default.** Start expanded whenever `base_url` is set or JSON mode is not Auto
   (proposed), or always collapsed?
7. **Tab-row scrollbar.** Hidden (proposed; the cut-off label is the cue), or a thin visible scrollbar
   for pointer users without a trackpad?
8. **Two explicit-Save surfaces register no leave guard today.** Should this phase add
   `useLeaveGuard(draft !== null)` to Auto-apply (`auto-apply-section.tsx:93`) and `useLeaveGuard(openaiKey
   !== null || geminiKey !== null)` to API keys (`models-section.tsx:205-206`)? Both drafts survive tab
   switches now, but a navigation drops them silently.
9. **`/profile` calls `useFocusSection()` twice** (page :18 and strip :44), so a hash landing polls and
   rings twice. Should the strip take `focus` as a prop from the page (a one-line change in each)?
10. **Should the job page get `keepMounted` and native URL writes too?** Its Q&A cover-letter editor
    survives a tab switch today only through the Base UI no-transition quirk (finding 2). `keepMounted`
    would also mount the Resume tab's PDF preview on arrival. Proposed: not in this phase. Record the
    quirk dependency instead.
