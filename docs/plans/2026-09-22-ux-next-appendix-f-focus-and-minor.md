> **Appendix F (focus and minor honesty gaps) to the 2026-09-22 UX next plan.** Research brief written read-only
> against `2cce6139` (local main; branch `claude/ux-next-plan`). Each task in the plan names the section it uses.
> Where this appendix offers options, the plan's "Owner decisions" section is binding. Line numbers drift: re-locate
> before editing.

# Phase F — focus never falls to `<body>`, and four small gaps: implementation brief

Worktree `.claude/worktrees/seinun-resume-update-45a8c0`, branch `claude/ux-next-plan` at `2cce6139`. All paths
are relative to that root, and all line numbers are at `2cce6139`. Sources: `docs/plans/2026-09-22-ux-followups.md`
*Next plan* items 7 (first clause) and 11; `docs/frontend-conventions.md`; SYSTEM.md §11 items 29, 31 and 32.

**Goal Card (this phase):** keyboard focus is never dropped to `<body>`, and small honesty gaps close.
Principles: accessibility is not negotiable (WCAG 2.2 AA; focus never dropped to `<body>`; programmatic state);
honesty about unsaved work; no new dependencies; conventions change with the code.

## 0. Read this first

**Eight findings change the directions in the ask:**

1. **Every F1 drop is one of two shapes, and the repo already has both fixes, hand-rolled once each.**
   - *A control that unmounts itself*: a pencil that swaps for its editor, Done, a collapse toggle. The fix is
     to arm a target in the handler and focus it after the commit. The Formatting panel's retry does this with a
     ref plus an effect (`formatting-panel.tsx:95-102`), and Referrals does it after the first create
     (`app/referrals/page.tsx:86, 116-120`).
   - *A subtree that vanishes while it holds focus*: an error that recovers, or an editor that remounts. The fix
     is to hand focus to a surviving `tabIndex={-1}` ancestor. The ATS score panel does this with `finalFocus` as
     a function (`ats-score-panel.tsx:218-223, 453-459`).

   This recurs about 15 times across F1 and F2, so it earns one module, `hooks/use-focus-return.ts`, with three
   primitives: `useFocusOnNextCommit`, `useFocusHandoff` and `focusReturnPoint` (design in F1 §"Shared
   helper"). Three bespoke copies (formatting panel, the F2 callers, the confirm) collapse into it.
2. **Base UI's default return target for a dialog with no `Trigger` is not "the opener".** For a controlled
   dialog, `FloatingFocusManager` returns focus to `domReference || getPreviouslyFocusedElement()`. That is a
   module-global list of every element any focus manager saw focused, filtered to the ones still connected
   (`@base-ui/react@1.4.1 esm/floating-ui-react/components/FloatingFocusManager.js:54-72, 416-432`). It is
   resolved in the close cleanup, **before** the popup leaves the DOM, so its top entry can be an element inside
   the closing dialog. The Role dialog's `RolePicker` combobox records its own input when its popup opens, so
   Escape "returns" focus to an input that is removed a moment later. That explains the verified "Role: … (after
   Escape)" drop. The same resolution returns `null` once the opener is gone, which explains Load latest. An
   **explicit** `finalFocus` (a `RefObject`, or a function that returns an element) bypasses both the list and the
   "focus moved elsewhere" heuristic (`hasExplicitReturnFocus`, :446-449).
3. **F2 cannot be fixed inside `LoadErrorState` alone.** The branch that unmounts it belongs to the caller, so
   every caller needs a one-token change (`q.isError` becomes `isLoadFailure(q)`). Three of those callers need
   more than the token:
   - **Four callers test the loading gate before the error** (Referrals, Applications, Agent proposals, the ATS
     score panel). A retry resets a data-less query to `isLoading`, so these fall into the skeleton even with
     the new predicate. The failure branch has to move first.
   - **Referrals would crash.** `app/referrals/page.tsx:140` reads `(referrals.error as Error).message` with no
     `?.`. A retry sets `error: null` (`@tanstack/query-core@5.99.2 build/modern/query.js:400-410`), so once the
     error block stays mounted during a retry, this line throws.
   - **Two callers treat a 404 as a state**: the health report's "No health report yet" and the application
     page's "This application no longer exists". During any refetch (window focus included) they lose the 404
     and would flash "Couldn't load… Retrying…". They need the last error remembered (`useLastSeen`).
4. **The referral double-create is TanStack's scheduler, not React.** `notifyManager` tells observers on
   `setTimeout(0)` (`notifyManager.js:3, 13-27`). The mutation's state changes synchronously inside `mutate()`,
   but the component re-renders with `isPending: true` only in a later task. A second click that is already
   queued runs first and sees `false`. So **every** create and generate button has the race, including the
   studio's Save. There is a precedent for the fix: `sendingRef` in `components/chat/chat-page.tsx:126, 296-302,
   402` ("the send button's `disabled` reads the same stale state").
5. **F3 does not need a buffer.** `flushSync(() => field.blur())` commits the blur-committed draft synchronously,
   and re-focusing before the keydown handler returns means every key queued behind the chord lands in the
   field. React 19.2 also flushes the passive effects of a sync-lane commit before `flushSync` returns
   (`react-dom-client.development.js:18323`, `pendingEffectsLanes & 3`). A field that unmounts on blur can
   therefore move focus with its own `useFocusOnNextCommit` inside that same call.
6. **F5's cause is the history rail, and a viewport breakpoint can't see it.** At 768px the pinned sidebar
   leaves 512px. `p-4` plus the 256px rail plus `gap-4` leave `<main>` 208px, while the composer's action row
   has a min-content width of about 340px. The rail gate has to be a **container** query. That fixes 768 only.
   At 375 the rail is already hidden and the composer overflows on its own (§11 item 31), which needs the row
   to wrap (owner option F5-b).
7. **`lib/*.ts` cannot value-import another `lib/*.ts`.** `node --test` needs `./x.ts` with the extension, and
   `tsc` rejects that extension (no `allowImportingTsExtensions`). Today only type imports cross lib files
   (`lib/health-report.ts:9`). So `lib/formatting.ts`'s `unloadedLayer` keeps its own copy of the retry
   predicate, and a node parity test pins it to the new `lib/query-state.ts`.
8. **Reading found about a dozen more drops of the same class** that the browser sweep didn't list (table in
   F1 §"Also found by reading"). With the helper, each costs one to three lines. Whether they are in scope is
   OWNER decision 1.

**"Edit raw JSON" is the one drop whose cause I could not establish from source.** The menu has a trigger, so
Base UI's default returns focus to it. Monaco 0.55.1 calls `focus()` only on IME changes
(`nativeEditContext.js:172-183`), and nothing remounts the trigger. So the first step of that fix is a
diagnosis (F1 §C). The explicit `finalFocus` is needed anyway for the overlays opened from ⋯.

**Order:** do the helpers first (the task split is at the end). F2 and F1 both use `useFocusHandoff`. F3 uses
`focusReturnPoint`. F4 and F5 are independent.

## Global constraints (read before writing any step)

- **Lint (`npm run lint`) has the React Compiler rules at error level**: `react-hooks/refs` (no `ref.current` in
  render), `react-hooks/set-state-in-effect` and `react-hooks/set-state-in-render`. A1 probed them. Every new
  piece of code below stays inside patterns that already pass in this repo:
  - refs read only in effects, layout cleanups and event handlers (`formatting-panel.tsx:97-102`);
  - a closure returned from a custom hook that reads a ref when called (`useRawJsonDraft().commitThen`,
    `raw-json-toggle.tsx:30-44`);
  - a function that reads refs passed as `finalFocus` (`ats-score-panel.tsx:220-223`);
  - the "adjust state while rendering" pattern (`if (v !== last) setLast(v)`, `raw-json-toggle.tsx:67-71`)
    for `useLastSeen`;
  - `setState` from a subscription callback, not from an effect body (`chat-page.tsx:146-154`) for F5's
    `ResizeObserver`.

  No effect added here calls `setState`. Run lint after every step.
- **Frontend duplication ratchet: 505 duplicated lines in 42 clones measured at Task 19, and it must not
  rise.** The committed `frontend/.slop-baseline.json` still says 518/43, so measure first:
  `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend`, run from the repo root. In a
  claim, name every surface you touched. `editor-body.tsx` already holds 9 clones. `SummaryBlock` and
  `CertificationsBlock` (:627-731) are near-twins, and adding the same focus wiring to both can grow their clone.
  If the check flags it, fold them into one local `ReadEditBlock` (F1 §A). Everything shared lives in
  `hooks/`, so the studios gain one or two lines each.
- **`lib/*.ts` imports only relative type imports or bare packages** (finding 7). `lib/query-state.ts` is pure
  and imports nothing. The hooks live in `hooks/`, which may import `@/lib/*` and is not node-tested.
- **Node unit tests are not in CI.** Run `cd frontend && node --test lib/*.test.ts` (85 at Task 19). New:
  `lib/query-state.test.ts`.
- **Source pins** are pytest files in `backend/tests/test_frontend_*.py`. Run
  `cd backend && python -m pytest tests/test_frontend_*.py -q` (284 at Task 18). **Mutation-check every new pin**:
  revert the fix line and watch the pin fail. The lane reviews found weak pins that stayed green with the fix
  reverted (the delegation skill's Grok 4.7 note).
- **Browser checks use real key events.** Playwright's `page.keyboard.press(...)` with headed Chrome, and read
  `document.activeElement` through `page.evaluate`. Synthetic `dispatchEvent` was not enough before.
  `document.hasFocus()` is false in the Claude browser pane, which suppresses Base UI's initial focus
  (conventions, "Initial focus in a dialog"), so do the dialog checks in Playwright. Use a throwaway stack per
  the worktree verification recipe, never the compose images (SYSTEM.md §9).
- **Library facts relied on** (all verified in `frontend/node_modules`):
  - **React 19.2.4**: a function component's layout-effect cleanup runs *before* React detaches its host
    children (`commitDeletionEffectsOnFiber`, `react-dom-client.development.js:14363-14380` against
    :14289-14330), so a layout cleanup still sees the focused element inside its subtree. Sync-lane commits
    flush passive effects synchronously (:18323).
  - **`@tanstack/query-core` 5.99.2**:
    - `fetchState` resets a data-less query to `status: "pending", error: null` on every fetch (query.js:400-410);
    - `errorUpdateCount` survives the refetch (queryObserver.js:326);
    - observers are notified on `setTimeout(0)` (notifyManager.js:3).
  - **`@base-ui/react` 1.4.1**:
    - `finalFocus` on `Menu.Popup` and `Dialog.Popup` takes `boolean | RefObject | (closeType) => HTMLElement |
      boolean | null | void` (`MenuPopup.d.ts:19-28`, `DialogPopup.d.ts:24-32`);
    - an element or ref is "explicit" and always wins;
    - a menu with a trigger defaults `returnFocus` to true (`MenuPopup.js:107-115`).
- **Docs contract**: conventions bullets change in the same commit as their code. SYSTEM.md is at **999/1000**
  lines, so nothing below adds a §12 entry. The two new gotchas (a data-less refetch resets to pending; `isPending`
  can't guard a double click) live in the conventions doc beside the rules they explain. The §11 edits here only
  narrow items, which frees lines. Run `python3 scripts/check_system_md.py`.

---

## Shared helper — `hooks/use-focus-return.ts` (used by F1, F2, F3)

### Why one module
The same four steps occur in every F1 and F2 fix:
- decide where focus should land if the focused thing disappears;
- remember it while the thing is still attached (a detached subtree has no path back to the document);
- move focus there after the commit;
- move it **only if focus fell to `<body>`**, never away from where the user put it.

`sidebar-reveal-trigger.tsx:37-47`, `formatting-panel.tsx:97-102` and `ats-score-panel.tsx:220-223` each
hand-write a version of this. Three primitives cover every site below.

### Code
```ts
"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

/** SidebarGutter's id: the skip link's target, the one `tabIndex={-1}` element every route shares. */
const MAIN_CONTENT_ID = "main-content";
const FIELD = 'input:not([type="hidden"]):not(:disabled), textarea:not(:disabled), select:not(:disabled)';
const TABBABLE = `${FIELD}, button:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])`;

/** Focus `target` only when focus has fallen to <body>: never take it from where the user put it. */
export function focusIfDropped(target: HTMLElement | null | undefined): void {
  const active = document.activeElement;
  if (active && active !== document.body) return;
  target?.focus({ preventScroll: true });
}

/**
 * Where focus goes back to if `el` disappears. The ancestors are read NOW, while `el` is attached: a removed
 * subtree has no path back to the document. The answer is `el` while it is still connected, else the nearest
 * `tabIndex={-1}` ancestor still connected (a panel that opted in), else the main area.
 */
export function focusReturnPoint(el: Element | null): () => HTMLElement | null {
  if (!(el instanceof HTMLElement) || el === document.body) return () => null;
  const chain: HTMLElement[] = [];
  for (
    let a = el.parentElement?.closest<HTMLElement>('[tabindex="-1"]');
    a;
    a = a.parentElement?.closest<HTMLElement>('[tabindex="-1"]')
  )
    chain.push(a);
  return () =>
    el.isConnected ? el : (chain.find((a) => a.isConnected) ?? document.getElementById(MAIN_CONTENT_ID));
}

/** The element when it takes focus itself, else its first text field, else its first tabbable. */
function focusTarget(el: HTMLElement): HTMLElement {
  if (el.matches(TABBABLE)) return el;
  return el.querySelector<HTMLElement>(FIELD) ?? el.querySelector<HTMLElement>(TABBABLE) ?? el;
}

/**
 * For a control that unmounts itself (a pencil that becomes its editor, Done, a collapse toggle). Call the
 * returned function in the handler with a ref to what replaces the control. After this component's next
 * commit, focus that fell to <body> moves there; a container ref focuses its first field.
 */
export function useFocusOnNextCommit() {
  const pending = useRef<RefObject<HTMLElement | null> | null>(null);
  // No deps: it runs after every commit of this component and does nothing unless a handler armed it.
  useEffect(() => {
    const target = pending.current;
    if (!target) return;
    pending.current = null;
    if (target.current) focusIfDropped(focusTarget(target.current));
  });
  return useCallback((target: RefObject<HTMLElement | null>) => {
    pending.current = target;
  }, []);
}

/**
 * For a subtree that can vanish while it holds focus (an error state that recovers, an editor a remount
 * replaces): focus moves to `focusReturnPoint(root)`.
 */
export function useFocusHandoff(ref: RefObject<HTMLElement | null>) {
  // A LAYOUT cleanup: React runs it before it detaches the subtree, so the focused element is still
  // inside `root` here and its ancestors can still be walked.
  useLayoutEffect(() => {
    const root = ref.current;
    return () => {
      if (!root || !root.contains(document.activeElement)) return;
      const back = focusReturnPoint(root);
      queueMicrotask(() => focusIfDropped(back())); // after the commit: the replacement is in the document
    };
  }, [ref]);
}

/**
 * A read view that swaps for an edit view and back. Each swap unmounts the button that was pressed:
 * opening moves focus to the edit view's first field, and Done moves it back to the pencil.
 */
export function useEditToggle(initial = false) {
  const [editing, setEditing] = useState(initial);
  const editRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLButtonElement>(null);
  const focusNext = useFocusOnNextCommit();
  return {
    editing,
    editRef,
    openerRef,
    open: () => { setEditing(true); focusNext(editRef); },
    close: () => { setEditing(false); focusNext(openerRef); },
  };
}
```
**`hooks/use-last-seen.ts`** (F2):
```ts
import { useState } from "react";
/** `value`, or the last non-nullish value it had. A refetch clears a query's `error` while it runs; a surface
 *  still showing that failure (retrying) must keep its words, and a 404-as-state must stay that state. */
export function useLastSeen<T>(value: T | null | undefined): T | null | undefined {
  const [last, setLast] = useState(value);
  if (value != null && value !== last) setLast(value);
  return value ?? last;
}
```

### Why "only if focus fell to `<body>`"
- It makes arming safe in a handler that fires on blur. The chip input's inline edit commits on blur: if the
  user clicked another field, that field has focus and nothing is stolen.
- It lets `useFocusOnNextCommit` arming coexist with Base UI's own return focus: whichever runs first wins,
  and the other is a no-op.

### Tests / pins (new `backend/tests/test_frontend_focus.py`)
```python
_HOOK = _read("hooks/use-focus-return.ts")

def test_focus_helpers_move_only_a_dropped_focus():
    body = _HOOK[_HOOK.index("export function focusIfDropped("):]
    assert "active !== document.body" in body[: body.index("\n}\n")]

def test_handoff_reads_focus_before_react_detaches_the_subtree():
    body = _HOOK[_HOOK.index("export function useFocusHandoff("):]
    body = body[: body.index("\n}\n")]
    assert "useLayoutEffect(" in body and "useEffect(" not in body
    assert "root.contains(document.activeElement)" in body

def test_return_point_is_remembered_while_attached_and_ends_at_the_main_area():
    body = _HOOK[_HOOK.index("export function focusReturnPoint("):]
    assert 'closest<HTMLElement>(\'[tabindex="-1"]\')' in body
    assert '"main-content"' in _HOOK
    # the skip-link target it relies on still exists and is focusable
    gutter = _read("components/sidebar-reveal-trigger.tsx")
    assert 'id="main-content"' in gutter and "tabIndex={-1}" in gutter
```
Mutation check:
- swap `useLayoutEffect` for `useEffect` → the second pin fails;
- drop the body guard → the first pin fails.

---

## F1 — Focus drops to `<body>` in the studios (browser-verified)

### Locations (at `2cce6139`)
| Drop | File:line | Control that held focus |
|---|---|---|
| Edit summary | `components/resume-editor/editor-body.tsx:627-679` (pencil :668-676, Done :646-648) | the pencil, unmounted by `setEditing(true)` |
| Edit contact | `components/resume-editor/contact-form.tsx:38, 44-69` (Done :64), :95-103 (pencil) | same |
| Hide / Show PDF preview | `components/resume-editor/editor-shell.tsx:96-115` (Show :103-111), :198-205 (Hide) | the toggle; the two live in different branches |
| ⋯ Edit raw JSON | `studio-overflow.tsx:40-75`; `editor-body.tsx:419-423`; `tailored-resume-studio.tsx:850-854` | the menu item (cause unconfirmed, §C) |
| ⋯ Role: … (after Escape) | `editor-body.tsx:409`, `:599-605`; `components/role-category-picker.tsx:195-232` | the dialog's own `RolePicker` input (finding 2) |
| Confirm Load latest | `tailored-resume-studio.tsx:733-756` → `onLoadLatest` :371 → `replaceEditor` :271-277 | the banner button, removed by the remount (`key={editorGen}` :356) |
| Confirm Rebuild from base | `tailored-resume-studio.tsx:879-897` → `materialize` :282-305 → remount | the ⋯ item, then whatever was focused when the remount landed |
| (all confirms) | `components/confirm-dialog.tsx:42-112` | the provider passes no `finalFocus` |

### A. Edit summary / Edit contact (and Certifications, which is the same code)
**Current code** (`SummaryBlock`; `ContactForm` and `CertificationsBlock` have the same shape):
```tsx
const [editing, setEditing] = useState(false);
if (editing) return (<div className="grid gap-2"> <Label/> <Textarea …/> <Button onClick={() => setEditing(false)}>Done</Button> </div>);
return (<div …> … <Button aria-label="Edit summary" onClick={() => setEditing(true)}>…</Button> </div>);
```
**Cause:** the pencil and Done each unmount themselves. React does not move focus to the new view, and nothing
in the edit view takes focus. `autoFocus` would handle opening, but not Done, and it doesn't fit
`ChipListInput` (no prop).

**Where focus goes:**
- opening → the edit view's first field (Summary textarea; Contact "Name"; Certifications' add-row input,
  since `focusTarget` prefers a text field over the chips' "Edit X" buttons);
- Done → the pencil. It is `opacity-0` until hover or focus, and its `focus-within:opacity-100` shows it.

**Fix:**
```tsx
function SummaryBlock({ value, onChange }: …) {
  const toggle = useEditToggle();
  if (toggle.editing) {
    return (
      <div ref={toggle.editRef} className="grid gap-2">
        … <Button size="sm" onClick={toggle.close}>Done</Button>
      </div>
    );
  }
  return ( … <Button ref={toggle.openerRef} … aria-label="Edit summary" onClick={toggle.open}> … );
}
```
Apply the same three edits in `CertificationsBlock` and `ContactForm`. If the ratchet flags
Summary/Certifications, fold them into one `ReadEditBlock({ label, editLabel, read, edit })` inside
`editor-body.tsx`. The two differ only in the label, the read body and the control.

### B. Hide / Show PDF preview (mouse and keyboard)
**Cause:** `collapsed` picks one of two trees (:96 and :117). Both roots are `div.flex.min-h-0.w-full.flex-1`,
so React keeps the root and the editor pane. The second child differs (the rail `div` against `<Splitter>`), so
the pressed toggle unmounts. Enter or Space goes through the same `onClick`.

**Where focus goes:** the counterpart toggle ("Hide" → "Show PDF preview" on the rail, and back).

**Fix (`editor-shell.tsx`):**
```tsx
const hideRef = useRef<HTMLButtonElement>(null);
const showRef = useRef<HTMLButtonElement>(null);
const focusNext = useFocusOnNextCommit();
// collapsed branch
<button ref={showRef} … onClick={() => { setCollapsed(false); focusNext(hideRef); }}>
// open branch
<Button ref={hideRef} … aria-label="Hide PDF preview" onClick={() => { setCollapsed(true); focusNext(showRef); }}>
```
`collapsed` also changes from another tab (`useLocalStorageState` syncs), but nothing arms then, so a remote
toggle never moves focus.

**Also in this file (same class, by reading):** Widen and Narrow preview (:174-197) are natively `disabled` at
the 75% and 25% limits. Pressing Widen until it disables drops focus. Add `focusableWhenDisabled` with
`className="data-disabled:pointer-events-none data-disabled:opacity-50"`, the `StudioSaveButton` pattern
(`studio-save-button.tsx:41-46`).

### C. ⋯ menu: "Edit raw JSON", and every overlay an item opens
**Diagnose "Edit raw JSON" first** (its cause is not visible in source):
1. In Playwright, add `document.addEventListener('focusin', e => console.log('in', e.target.outerHTML.slice(0,80)), true)`
   and the same for `focusout`.
2. Tab to ⋯, press Enter, then ArrowDown to "Edit raw JSON", then Enter.
3. If the trigger never receives `focusin`, the explicit `finalFocus` below fixes it. If the trigger receives
   focus and then loses it, find what takes it before shipping, and record the answer in the deviation log.

**Where focus goes:** the ⋯ trigger, for the menu itself and for every overlay an item opens. APG's menu-button
pattern returns focus to the button, and the item is gone by the time the overlay closes. Landing a keyboard
user inside Monaco unasked is a trap, because Tab indents there (OWNER decision 3).

**Fix:**
- **`studio-overflow.tsx`**: a required `triggerRef` prop.
  ```tsx
  triggerRef: RefObject<HTMLButtonElement | null>;  // doc: focus returns here from the menu and from every overlay an item opens
  <DropdownMenuTrigger render={<Button ref={triggerRef} … aria-label="More resume actions" …/>} />
  <DropdownMenuContent finalFocus={triggerRef} align="end" …>
  ```
- **`role-category-picker.tsx` `RoleCategoryDialog`**: add `finalFocus?: RefObject<HTMLElement | null>` and
  pass it to `<DialogContent finalFocus={finalFocus}>`. This fixes the verified Escape drop (finding 2).
- **The same prop on `VersionHistorySheet` (`resume-versions/version-history-sheet.tsx:184`), `InstructSheet`
  (`instruct-sheet.tsx:105`) and `KbImportDrawer` (`kb-import-drawer.tsx:166`)**, passed to `<SheetContent>`.
  They are opened from the same menu and have the same default-return exposure (verify each in the browser).
- **Both studios**: `const overflowRef = useRef<HTMLButtonElement>(null);`.
  - Pass it to `StudioOverflowMenu`.
  - Base studio: pass `finalFocus={overflowRef}` to RoleCategoryDialog, VersionHistorySheet, InstructSheet
    and KbImportDrawer.
  - Tailored studio: pass it to VersionHistorySheet.
- **The raw pane's own exits** (by reading, same class): Apply JSON and Cancel (`raw-json-toggle.tsx:94-100,
  122-134`) call `onClose`, which unmounts the pane with focus on the pressed button. Each studio changes to
  `onClose={() => { setRawMode(false); focusNext(overflowRef); }}` (`const focusNext =
  useFocusOnNextCommit()`). "Form view" in the menu already returns to ⋯ through the menu's `finalFocus`.

### D. Confirm Load latest / Rebuild from base (the remount)
**Cause, traced:**
- **Load latest.** `finish(true)` resolves the promise, and the `await` continuation calls
  `replaceEditor(customizedKey)`, which bumps `editorGen`: StudioEditor, header included, remounts. The dialog's
  popup stays mounted through its ~100ms exit animation. When it unmounts, Base UI resolves the return target
  to the Load latest button, which was already removed, so it gets `null` (`el.isConnected ? el : null`, :428),
  focuses nothing, and focus falls to `<body>`.
- **Rebuild.** The confirm returns focus from a menu item (a portal element that is also gone), and seconds
  later the remount removes whatever was focused inside the editor.
- **A foreign edit adopted while the editor is clean** (chat or MCP) remounts the same way. It isn't in the
  verified list, but it is the same drop.

**Where focus goes:**
- For a confirm whose opener still exists: the opener (Base UI's default).
- When the confirmed action removed the opener: the nearest stable container outside the remounted subtree.
  Give `FullscreenEditorPage`'s `<main>` `tabIndex={-1}` so that container is the studio's own landmark rather
  than `#main-content` (OWNER decision 2).
- Rebuild's Cancel: back to ⋯.

**Fix, three small parts:**
1. **`confirm-dialog.tsx`**: the provider remembers the opener when `confirm()` is called and passes an explicit
   `finalFocus`. This is generic, so it also covers any other confirm that removes its own opener.
   ```tsx
   export interface ConfirmOptions { …; /** Where focus goes on close, when not the element that opened it
    *  (a menu item is gone by then). */ returnFocus?: () => HTMLElement | null; }
   // Taken when the confirm opens: a confirmed action can remove its own opener (Load latest remounts the
   // editor), and Base UI's default then finds nothing to return to.
   const returnPoint = useRef<() => HTMLElement | null>(() => null);
   const confirm = useCallback<ConfirmFn>((options) => {
     returnPoint.current = focusReturnPoint(document.activeElement);
     setOpts(options); setOpen(true); …
   }, []);
   <DialogContent … finalFocus={() => opts?.returnFocus?.() ?? returnPoint.current() ?? true}>
   ```
   `true` keeps Base UI's default when there is nothing to name, for example when a confirm is opened with focus
   on `<body>`.
2. **Rebuild** passes `returnFocus: () => overflowRef.current` (:883-889), so Cancel and the in-flight
   "Rebuilding…" state keep focus on ⋯.
3. **`EditorShell`** gets `useFocusHandoff(rootRef)`, with the ref on the root `div` of both branches (the same
   DOM node). When a remount removes the shell with focus inside (⋯ during Rebuild, a field during a foreign
   adoption), focus goes to `FullscreenEditorPage`'s `<main>`. This one line covers both studios and the
   template editor.

   `FullscreenEditorPage` (`fullscreen-editor-page.tsx:12`) becomes
   `<main tabIndex={-1} className="flex h-dvh flex-col overflow-hidden outline-none">`. `outline-none` matches
   `#main-content` and the Formatting panel's wrapper: the target is a container, not a control.

### Also found by reading (same class; OWNER decision 1 on scope)
| Where | What drops | Fix with the helper |
|---|---|---|
| `editable-card.tsx:77-83, 136-138` (every Experience/Education/Project/extra entry) | Edit and Done unmount themselves | `useFocusOnNextCommit` inside its `setEditing` wrapper; `ref`s on the pencil and the edit `div` |
| `ui/chip-input.tsx:135-145` | inline chip edit: Enter / Escape (and a blur-commit via Cmd+S) unmount the edit input | `commitEdit`/`cancelEdit` arm `focusNext(addRowRef)`; the body guard makes the blur path safe |
| `extra-sections-editor.tsx:146-155, 174-182` | section rename: Enter / Escape / Done unmount the input | arm `focusNext(renameButtonRef)` in `commitRename` and the Escape branch |
| `editable-title.tsx:65-71, 82-90` (base studio name) | Enter / Escape unmount the input | arm `focusNext(pencilRef)` in `commit` and on Escape |
| `chat/chat-page.tsx:563-596` | Hide chat history / Show chat history | as B (counterpart toggle) |
| `app/referrals/page.tsx:333-341, 409-414, 509-523` | row Edit → edit row; Save (natively disabled while pending) / Cancel → view row | `useEditToggle`-style arming in `ReferralRow`; Save `focusableWhenDisabled` |
| `app/referrals/page.tsx:309-331` | deleting the LAST referral (§11 item 29, second clause) | `useFocusHandoff` on `ReferralsTable`'s root; add `tabIndex={-1}` to the empty-state card if the owner wants focus there rather than `#main-content` |

`contact-form.tsx:50, 55` builds ids from the key (`contact_${key}`), against "Form-control ids come from
`useId()`". It renders once per studio, so it is not a live collision. Leave it, or add it to §11 item 32's id list.

### Tests / pins (`test_frontend_focus.py`, continued)
```python
def test_read_edit_blocks_focus_their_field_and_return_to_the_pencil():
    for rel in ("components/resume-editor/contact-form.tsx", "components/resume-editor/editor-body.tsx"):
        src = _read(rel)
        assert "useEditToggle(" in src
        assert "ref={toggle.editRef}" in src and "ref={toggle.openerRef}" in src
        assert "onClick={toggle.close}" in src
        assert "onClick={() => setEditing(" not in src   # no bare toggle left

def _element(src: str, label: str, tag: str) -> str:
    at = src.index(f'aria-label="{label}"')
    start = src.rfind(f"<{tag}", 0, at)
    return src[start : src.index(f"</{tag}>", at)]

def test_preview_toggles_hand_focus_to_each_other():
    assert "focusNext(hideRef)" in _element(_SHELL, "Show PDF preview", "button")
    assert "focusNext(showRef)" in _element(_SHELL, "Hide PDF preview", "Button")
    for label in ("Widen preview", "Narrow preview"):
        assert "focusableWhenDisabled" in _element(_SHELL, label, "Button")

def test_overflow_menu_and_its_overlays_return_to_the_trigger():
    menu = _read("components/resume-editor/studio-overflow.tsx")
    assert "finalFocus={triggerRef}" in menu and "ref={triggerRef}" in menu
    assert re.search(r"<DialogContent[^>]*finalFocus=\{finalFocus\}", _read("components/role-category-picker.tsx"))
    base = _read("components/resume-editor/editor-body.tsx")
    assert base.count("finalFocus={overflowRef}") == 4   # role, history, instruct, import

def test_confirm_returns_to_its_opener_or_what_survived_it():
    src = _read("components/confirm-dialog.tsx")
    assert "focusReturnPoint(document.activeElement)" in src
    assert re.search(r"finalFocus=\{\(\) =>[^}]*returnPoint\.current\(\)", src)
    tailored = _read("components/resume-editor/tailored-resume-studio.tsx")
    rebuild = tailored[tailored.index('title: "Rebuild from base resume?"'):]
    assert "returnFocus: () => overflowRef.current" in rebuild[:600]

def test_a_studio_remount_hands_focus_to_the_page_landmark():
    assert "useFocusHandoff(rootRef)" in _SHELL
    page = _read("components/resume-editor/fullscreen-editor-page.tsx")
    assert re.search(r"<main\s+tabIndex=\{-1\}", page)
```
Existing pin `test_divider_tracks_the_pointer_on_the_shell` (`test_frontend_studio.py:37-44`) slices the Show
button. Adding a `ref` keeps it green. Re-check it anyway.

### Browser checks (Playwright, real keys, both studios, light and dark)
For each check, assert `await page.evaluate(() => document.activeElement !== document.body)` plus the named
target:
- **Edit summary**: Tab to it, Enter → `activeElement.tagName === "TEXTAREA"`. Tab to Done, Enter → the
  pencil. Repeat for Edit contact (→ Name) and Edit certifications (→ add-row input).
- **Hide PDF preview**: Enter → `aria-label === "Show PDF preview"`, then Enter → "Hide PDF preview". Do it by
  mouse too: the target is the same, and no ring shows (`:focus-visible` follows a pointer).
- **Widen preview**: press Enter repeatedly until it disables → still focused, with `aria-disabled="true"`.
- **Edit raw JSON**: open the menu from the keyboard, choose the item → focus is on ⋯. Choose "Form view" → ⋯.
  Apply JSON and Cancel → ⋯.
- **Role…**: open the dialog, type in the picker so its popup opens, Escape twice → focus is on ⋯. Close with
  Done → ⋯.
- **Load latest**: make the editor dirty, then PATCH `customized_json` through the API (or chat) so the banner
  shows. Tab to Load latest, Enter, Tab to "Load latest" in the confirm, Enter → `activeElement.tagName ===
  "MAIN"`. Cancel instead → the banner button.
- **Rebuild from base**: from ⋯, confirm → focus is on ⋯ while "Rebuilding…". After the toast →
  `activeElement.tagName === "MAIN"`. Cancel → ⋯.
- **Foreign adoption while clean**: focus a field, apply a chat edit → `MAIN`.

### Edge cases
- **`focusIfDropped` never steals.** If Base UI's own return focus wins a race, the armed target is a no-op, and
  the reverse holds too.
- **StrictMode (dev)** runs mount, cleanup, mount. The handoff's first cleanup sees no focus inside, so it does
  nothing. `useFocusOnNextCommit`'s effect is idempotent, because it clears `pending` before focusing.
- **Route navigation** out of a studio: the handoff fires if focus was inside, and focuses `#main-content`, the
  layout's stable wrapper, once the new route has mounted. That is the right place after a client navigation.
- **`focus-visible`**: programmatic focus after a keyboard gesture shows the ring on buttons, as it should.
  After a mouse click Chrome suppresses it. Containers are `outline-none` by precedent.
- **The known defect** (conventions, "Initial focus in a dialog": a confirm opened from a menu gets its
  *initial* focus raced by the menu) is not touched here. Only the *final* focus changes.

### Docs
Add one conventions bullet near "Initial focus in a dialog", with a bolded lead:

> **Focus never falls to `<body>`.**
> - A control that unmounts itself arms `useFocusOnNextCommit` with what replaces it: the counterpart toggle,
>   the first field of the editor it opened, or the pencil on Done. `useEditToggle` wraps the read/edit case.
> - A subtree that can vanish while holding focus calls `useFocusHandoff`: `LoadErrorState`, `EditorShell`.
> - Every overlay opened from a ⋯ menu takes the trigger as `finalFocus`, because the item is gone by the
>   time it closes.
> - `ConfirmDialogProvider` returns to its opener, or, when the confirmed action removed it, to the nearest
>   `tabIndex={-1}` ancestor that survived.
> - The fallback chain ends at `#main-content`. Focus moves only when it fell to `<body>`.
> - Why the rule exists: Base UI's default return target for a trigger-less dialog is the last connected
>   element it saw focused, which can be inside the closing dialog.

Also:
- in *Divider*, add "the two preview toggles hand focus to each other";
- in *Raw JSON*, add "leaving the pane returns focus to ⋯".

---

## F2 — `LoadErrorState` "Try again" drops focus on most screens

### Locations and inventory (every caller, at `2cce6139`)
| # | Caller | Branch | Loading gate first? | Special |
|---|---|---|---|---|
| 1 | `app/referrals/page.tsx:135-143` | `referrals.isError ?` | **yes** (:135 skeleton) | **`(referrals.error as Error).message` without `?.` (:140)** |
| 2 | `app/base-resumes/page.tsx:139-145` | `resumes.isError ?` | no | |
| 3 | `app/profile/page.tsx:31-37` | `setupStatus.isError ?` | no | |
| 4 | `app/applications/page.tsx:327-331, 474-492` | `loadFailed` = `apps.isError \|\| savedJobs.isError` | **yes** (`loading ?` :474) | two queries |
| 5 | `app/applications/[id]/page.tsx:23, 34-66` | `if (isError)` | no | **404 → "no longer exists"** |
| 6 | `app/templates/page.tsx:188-194` | `templates.isError ?` | no | |
| 7 | `app/jobs/[id]/page.tsx:127, 215-231` | `if (isError)` | no | destructured |
| 8 | `components/qa-tab.tsx:50, 206-212` | `isError ?` | no | destructured |
| 9 | `components/ats-score-panel.tsx:353-377` | `if (scores.isError)` | **yes** (`scores.isLoading \|\|` :353) | inside the `rootRef tabIndex={-1}` wrapper (:453) |
| 10 | `components/settings/setting-card.tsx:83-97` | `loadFailed && !ready` | no | `SettingQuery` type (:40-46), many queries |
| 11 | `components/career/first-run-import-card.tsx:43-50` | `entities.isError` | no | |
| 12 | `components/resume-health/health-report-page.tsx:222-229` | `baseQuery.isError` | no | |
| 13 | same, `:181-183, 324-330` | `reportFailed = report.isError && !noReportYet` | no | **404 → "No health report yet"** |
| 14 | `components/chat/chat-page.tsx:612-619` | `sessionId !== null && detail.isError` | no, but falls to the empty greeting during a retry | |
| 15 | `components/setup/getting-started-card.tsx:53-60` | `setupStatus.isError` | no | |
| 16 | `components/proposals/proposals-section.tsx:188, 361-382` | `if (isError)` | **yes** (`if (isLoading)` :361) | destructured |
| 17 | `components/proposals/proposal-agent-panel.tsx:36-47` | `if (isError)` | no | destructured |
| 18 | `components/resume-editor/formatting-panel.tsx:331-341` | via `unloadedLayer` (`lib/formatting.ts:247-262`) | n/a | already correct; bespoke refocus :92-102 |

`LoadErrorState` itself: `components/load-error-state.tsx:31-75` (`focusableWhenDisabled` since `29ccb04d`).

### Cause
`refetch()` on a query with no data runs `fetchState`, which sets `status: "pending", error: null`. So
`isError` goes false the instant Try again is pressed. The caller's branch falls to the skeleton or the empty
state, and the focused button unmounts. Two consequences follow:
- `retrying={q.isFetching}` never shows "Retrying…" on these screens, because the block is gone before
  `isFetching` renders true.
- Nothing takes focus when the data arrives.

`29ccb04d` fixed this for the Formatting panel alone, in three parts: the predicate in `unloadedLayer`,
`focusableWhenDisabled`, and a bespoke refocus effect.

### Options
| Option | Per-caller code | Covers 404-as-state | Focus after recovery |
|---|---|---|---|
| A. `useLoadFailure(query)` hook returning props | branch + spread props | yes (it holds the last error) | inside the hook |
| **B. Pure `isLoadFailure(q)` + `LoadErrorState` owns memory and focus (recommended)** | one token; failure first where the loading gate was first | with `useLastSeen` in 2 callers | inside `LoadErrorState` (handoff) |
| C. A global react-query option | none | — | — |

**C does not exist:** `fetchState` is internal, and no client option keeps a data-less error through a refetch.
**A** needs a hook per query, which `SettingCard` can't call (its queries are an array, and hooks in `.map`
break `rules-of-hooks`). It also churns 17 call sites. **B**'s predicate is node-testable, leaves callers
nearly unchanged, and puts focus and memory in the one component every caller already renders.

### Fix design (B)
**`lib/query-state.ts`** (new, pure, no imports):
```ts
/** The slice of a react-query result a load-failure check reads. */
export type LoadQuery = {
  data: unknown;
  isError: boolean;
  isFetching: boolean;
  /** How many times the query has failed; a refetch does not reset it. */
  errorUpdateCount: number;
};

/**
 * Whether a surface shows its failed-load state (`LoadErrorState`). Not `isError` alone: react-query refetches
 * a query that holds no data from "pending" (error null), so the moment Try again was pressed the error branch
 * fell through to the skeleton or the empty state and unmounted the focused button. A query that has failed
 * before and is fetching again with still no data is a failure being retried, not a first load.
 */
export function isLoadFailure(query: LoadQuery): boolean {
  return query.isError || (query.data === undefined && query.isFetching && query.errorUpdateCount > 0);
}
```
`lib/formatting.ts:251` keeps its own expression, because a value import across lib files breaks `node --test`
(finding 7). Add the comment "the same rule as `isLoadFailure` (lib/query-state.ts); a lib file cannot
value-import another, so the parity test pins them together".

**`components/load-error-state.tsx`**:
```tsx
export function LoadErrorState({ … }) {
  const rootRef = useRef<HTMLDivElement>(null);
  // Recovery unmounts this block, focused Try again included. Focus moves to the nearest tabIndex={-1}
  // ancestor (a panel that opted in: the Formatting panel's body, the ATS score panel) or the main area.
  useFocusHandoff(rootRef);
  // A retry clears the query's error while it runs; keep the words until it answers.
  const shownDetail = useLastSeen(detail);
  return (
    <div ref={rootRef} role="alert" …>
      … {shownDetail ?? "The request failed. It may just be the backend restarting."} …
```
Rewrite the docstring's last paragraph to say the retry keeps this block mounted (with `isLoadFailure`) and
that focus is handed off on recovery.

**Callers.** Mechanical: `X.isError` becomes `isLoadFailure(X)` in the branch. Destructured callers (5, 7, 8, 16,
17) either keep the query object (`const job = useQuery(...)`) or also destructure `errorUpdateCount`. Keeping
the object reads better. The special cases:
- **#1 Referrals**: put the failure branch first, and make the detail optional.
  ```tsx
  {isLoadFailure(referrals) ? (
    <LoadErrorState title="Couldn't load referrals." detail={(referrals.error as Error | null)?.message} … />
  ) : referrals.isLoading ? ( <Skeleton className="h-40 w-full" /> ) : populated ? …
  ```
  `populated` (:88-89) is unchanged. It is false during the retry because `isLoading` is true.
- **#4 Applications**: `const loadFailed = isLoadFailure(apps) || isLoadFailure(savedJobs);` and the
  `loadFailed ?` branch moves above `loading ?`. An error in either query wins over loading, the same rule as
  `overlayBaseline`.
- **#9 ATS score panel**: move `if (isLoadFailure(scores))` above the skeleton gate. The gate's comment
  (:347-351) about `isSuccess` still holds.
- **#16 Proposals**: `if (isLoadFailure(…))` above `if (isLoading)`.
- **#10 `SettingCard`**: add `errorUpdateCount: number` to `SettingQuery`. Every caller passes a whole
  `UseQueryResult`, so it type-checks. The branch becomes `const loadFailed = queries.some(isLoadFailure);`.
- **#5 Application page**:
  ```tsx
  const lastError = useLastSeen(query.error);     // before any early return
  if (isLoadFailure(query)) {
    const missing = lastError instanceof ApiError && lastError.status === 404;
  ```
  Today a window-focus refetch of a missing application shows the skeleton for about 7 s: three default
  retries (§11 item 32 names the same wait on `/health`), then "no longer exists" again. With this change it
  stays "no longer exists" throughout.
- **#13 Health report**: the same pattern.
  ```tsx
  const reportError = useLastSeen(report.error);
  const noReportYet = isLoadFailure(report) && reportError instanceof ApiError && reportError.status === 404;
  const reportFailed = isLoadFailure(report) && !noReportYet;
  ```
- **#14 Chat**: `sessionId !== null && isLoadFailure(detail)`. That also stops the "What are we working on?"
  greeting flashing during a retry.
- **#18 Formatting panel**: delete the bespoke refocus (:92-102, and `refocusWhenReady.current = true;` in
  `onRetry`, which goes back to `onRetry={baseline.retry}`). Keep `tabIndex={-1}` on the body wrapper, since it is
  now the handoff's target. `bodyRef` can go. The behaviour is identical: after recovery, focus that fell to
  `<body>` lands on the panel body.

**Optional closer targets:** these callers land on `#main-content` (the top of the main area) unless a wrapper
opts in with `tabIndex={-1}`:
- the Q&A History section (`qa-tab.tsx:204`);
- the chat conversation column;
- the proposal agent card.

Each is one attribute plus `outline-none`. Recommended for the chat column and Q&A, where the recovered content
sits far from the top.

**Found by inventory, outside `LoadErrorState`:** four route-level error branches offer no retry at all, against
"A failed fetch is a THIRD state … always offers the retry":
- `app/base-resumes/[slug]/page.tsx:25-36`;
- `app/applications/[id]/resume/page.tsx:32-43`;
- `app/templates/[id]/page.tsx:~180-190`;
- `app/jobs/[id]/tailor/[sessionId]/page.tsx:~490-500`.

Folding them into F2 is four small `LoadErrorState` swaps (OWNER decision 4). Otherwise add them to §11 item 32.

### Tests / pins
- **`frontend/lib/query-state.test.ts`** (node):
  - a first load (`isFetching`, count 0) → false;
  - a failed load → true;
  - **a retry of a failed load (`isError: false, isFetching: true, errorUpdateCount: 1, data: undefined`) →
    true**, the regression test;
  - data held and refetching after an earlier failure → false;
  - data held and a failed background refetch (`isError: true`) → true (unchanged);
  - **a parity case that imports both `./query-state.ts` and `./formatting.ts`**: for each of those five states,
    `unloadedLayer(q, "x").status === "error"` equals `isLoadFailure({ ...q, data: undefined })`.
- **`backend/tests/test_frontend_query_error_states.py`**:
  - add `r"|isLoadFailure\("` to `_ERROR_BRANCH` (:34-46), or the table fails the moment a caller migrates.
  - Add:
    ```python
    _LOAD_ERROR_CALLERS = sorted(
        str(p.relative_to(_FRONTEND)) for d in ("app", "components") for p in (_FRONTEND / d).rglob("*.tsx")
        if "<LoadErrorState" in p.read_text() and p.name != "load-error-state.tsx")

    @pytest.mark.parametrize("relpath", _LOAD_ERROR_CALLERS)
    def test_a_retry_keeps_the_error_mounted(relpath):
        src = (_FRONTEND / relpath).read_text()
        if relpath.endswith("formatting-panel.tsx"):
            assert "baseline.retrying" in src; return          # unloadedLayer, parity-tested in node
        assert "isLoadFailure(" in src
        assert not re.search(r"\.error as Error\)\.message", src), "a retry clears `error`: use ?."

    # (file, loading-gate marker) — the failure branch must come first, or a retry lands in the skeleton.
    _LOADING_GATES = [
        ("app/referrals/page.tsx", '<Skeleton className="h-40 w-full" />'),
        ("app/applications/page.tsx", "animate-shimmer h-12"),
        ("components/proposals/proposals-section.tsx", "if (isLoading) {"),
        ("components/ats-score-panel.tsx", "scores.isLoading ||"),
    ]
    ```
    and assert `src.index("isLoadFailure(") < src.index(marker)`.
  - Add `test_load_error_state_hands_off_focus_and_keeps_its_words`: `useFocusHandoff(rootRef)`,
    `ref={rootRef}` and `useLastSeen(detail)` are all in `load-error-state.tsx`.
  - The existing `focusableWhenDisabled` pin stays.
- **`test_frontend_studio.py::test_formatting_retry_never_drops_focus_to_body`** (:292-306): replace the
  `refocusWhenReady` asserts with these, and keep the `focusableWhenDisabled` asserts:
  - `"refocusWhenReady" not in _PANEL`;
  - `re.search(r"tabIndex=\{-1\}", _PANEL[wrapper_slice])` on the div that holds the `LoadErrorState`;
  - `"onRetry={baseline.retry}"` in the error slice;
  - the old `test_formatting_panel_reports_a_failed_baseline_with_a_retry` asserts `"baseline.retry();"` (:287).
    Change it back to `onRetry={baseline.retry}`.
- **`test_frontend_referrals.py::test_a_failed_fetch_is_the_shared_error_state`** (:42-45) slices from
  `referrals.isError ?`. Re-anchor it to `isLoadFailure(referrals) ?` … `) : referrals.isLoading ?`.
- **Mutation check**: revert any one caller to `.isError`, and the parametrized pin fails for that file.
  Remove `useFocusHandoff` from `LoadErrorState`, and its pin fails.

### Browser checks (Playwright; block the endpoint with `page.route(url, r => r.abort())`, then `unroute`)
For Referrals, Applications, Base resumes, a settings card, the ATS score panel (job page Score tab), the chat
conversation and the Formatting panel:
1. load with the route blocked;
2. Tab to Try again;
3. `unroute`;
4. press Enter.

Assert that:
- **while fetching**: the label reads "Retrying…", `activeElement` is the button with `aria-disabled="true"`,
  and the detail text is unchanged;
- **after**: the content renders and `activeElement` is not BODY (it is the panel wrapper where one opted in,
  else `#main-content` or the studio `<main>`).

Also run it with the route still blocked. The error stays, focus stays on Try again for the whole ~7 s of
default retries, and afterwards the button re-enables with focus on it. For the 404 cases, open
`/applications/<unknown-id>`, blur and refocus the window, and "no longer exists" must never change to the
generic error.

### Edge cases
- **A failed background refetch over existing data** still reads `isError: true` and behaves exactly as today:
  the error replaces the loaded list where a caller already did that. Changing that is out of scope. The
  predicate only adds the data-less retry case.
- **The error changing between failures** (a different message on the second failure): `useLastSeen` takes the
  new one.
- **`role="alert"` staying mounted through the retry** is not re-announced. Only the button label changes, and
  the button has focus, so its new name is read.
- **Navigation from the error's `action` link** ("Back to Applications") also unmounts with focus inside, and
  the handoff lands on `#main-content` after the route renders. That is the right target.

### Docs
- Rewrite conventions **"A failed fetch is a THIRD state"** (:302-309). Add: branch on `isLoadFailure(query)`
  (`lib/query-state.ts`), never on `query.isError`; a refetch resets a data-less query to pending with a null
  error, which unmounted the error state and its focused Try again; the failure branch precedes the loading
  gate; `LoadErrorState` keeps its last detail while retrying and hands focus to the nearest `tabIndex={-1}`
  ancestor on recovery; a caller that treats a status as a state reads the error through `useLastSeen`.
- Trim *Formatting controls* (:233-239) to one sentence: "a retry stays that error (`unloadedLayer`, the same
  rule as `isLoadFailure`), and recovery hands focus to the panel body's `tabIndex={-1}` wrapper through
  `LoadErrorState`".
- **`SettingCard`** bullet (:592-598): add "readiness is `data !== undefined`; failure is `isLoadFailure`".

---

## F3 — Keystrokes typed in the same instant as Cmd/Ctrl+S are lost

### Locations
- `frontend/hooks/use-save-shortcut.ts:34-70` (blur :55, refocus on the next task :58-62, gap guard :44-46)
- The blur-committed fields it exists for:
  - `components/ui/chip-input.tsx:196-201`: the add row's pending text commits on blur (the real case);
  - `chip-input.tsx:145`: the inline chip edit commits on blur, then unmounts;
  - `extra-sections-editor.tsx:146-155, 182`: section rename. The title is already live in `data` on every
    keystroke. Blur only normalizes an empty or colliding title, then unmounts the input;
  - `editable-title.tsx:65-71, 81`: the base studio name. Blur commits through its own `PATCH /identity`, not
    Save, then unmounts.
- Conventions *Cmd/Ctrl+S* (`docs/frontend-conventions.md:151-165`).

### Current code
```ts
field.blur();
timer = setTimeout(() => { timer = undefined; if (field.isConnected) field.focus({ preventScroll: true }); save(); }, 0);
```

### Cause
Between `blur()` and the refocus there is a whole task. Keydown events already queued behind the chord (fast
typing, or a key held with the modifier released) are dispatched while focus is on `<body>`, and are lost. The
existing `timer` guard only stops a second chord from saving twice inside that gap.

### Options
| Option | Gap | Keeps "never saves less than the button" | Cost |
|---|---|---|---|
| Blur only fields marked `data-commit-on-blur` | remains for marked fields (the chip add row) | yes, if every such field is marked; a future unmarked one silently saves less | 4 attributes and a convention |
| Buffer keys typed in the gap and replay them | none in theory | yes | IME, dead keys, selection, `beforeinput`: a small text-input engine |
| **`flushSync` the blur, refocus synchronously (recommended)** | **none** | **yes, for every field that blurs today** | 3 lines, no new API |

**Recommend `flushSync`.** `field.blur()` fires `focusout` synchronously, and React's `onBlur` handler runs
inside it. Its `setState` calls sit in the sync lane, `flushSync` commits them before it returns, and
`useEffectEvent`'s `save` is updated in that commit, so it reads the committed draft. Focus goes back before the
keydown handler returns, so every queued key lands in the field. There is no gap, which means the `timer` guard
goes too: one chord is one save because `canSave` gates it, and F4's guard covers a second chord.

### Fix design
```ts
import { flushSync } from "react-dom";
import { focusIfDropped, focusReturnPoint } from "@/hooks/use-focus-return";
…
const onKeyDown = (event: KeyboardEvent) => {
  if (!isSaveShortcut(event)) return;
  const claimed = event.defaultPrevented;
  event.preventDefault();
  if (claimed || event.repeat || event.isComposing) return;
  if (event.target instanceof Element && event.target.closest(DIALOG)) return;
  const field = document.activeElement;
  if (!holdsDraft(field)) { save(); return; }
  // Some fields commit only on blur (a chip input's pending text), and a click on Save blurs first.
  // Blur, make React commit the draft NOW, and put focus back before this handler returns: keys typed
  // right after the chord are queued behind it and land in the field. A field that unmounts on blur
  // (an inline chip edit, a rename) moves focus itself; otherwise the nearest surviving container.
  const back = focusReturnPoint(field);
  flushSync(() => field.blur());
  focusIfDropped(back());
  save();
};
```
Delete `timer`, its `clearTimeout` in the cleanup, and the gap comment. Rewrite the docstring's last paragraph.

**Fields that unmount on blur** (F1 "Also found by reading": chip inline edit, section rename, EditableTitle):
- **If those rows are in scope**, their commit handlers arm `useFocusOnNextCommit`. The passive effect of a
  sync-lane commit runs before `flushSync` returns, so focus is already on the add row or the pencil, and
  `focusIfDropped` does nothing.
- **If they are not**, `back()` resolves to the nearest `tabIndex={-1}` ancestor, which is still better than
  `<body>`.

### Tests / pins (`test_frontend_studio.py`)
```python
def test_save_shortcut_commits_a_draft_with_no_gap():
    hook = _read("hooks/use-save-shortcut.ts")
    assert "flushSync(() => field.blur())" in hook
    assert "setTimeout" not in hook, "a refocus on the next task drops the keys typed in between"
    after = hook[hook.index("flushSync(") :]
    assert after.index("focusIfDropped(back())") < after.index("save();")
    assert "const back = focusReturnPoint(field);" in hook[: hook.index("flushSync(")]
```
`test_one_save_button_owns_the_click_and_the_shortcut` (:102-106) is unaffected.

### Browser checks (Playwright; real `keyboard.down("Meta")`, `press("s")`, `up("Meta")`)
- **Summary textarea** (tailored) or a contact field: type `abc`, then Cmd+S and immediately
  `keyboard.type("xyz", { delay: 0 })` → the value ends `abcxyz`, the status reads "Unsaved changes" once the
  save lands, and the caret is still where it was. Blur, then focus, keeps the selection in Chrome; check a
  mid-text caret too.
- **Chip add row** (Skills): type `Kafka`, Cmd+S → a "Kafka" chip is in the saved copy (reload and check), and
  focus is in the add row. Type `Flink` immediately → it lands in the add row.
- **Inline chip edit**: click a chip, change it, Cmd+S → saved. Focus is on the add row (if in scope) or not on
  BODY.
- **Ctrl+S** on Linux/Windows key mapping: `isSaveShortcut` is unchanged.
- **Two chords** 50 ms apart → one PATCH (Network panel) once F4's guard is on Save. Without it, check that
  `canSave` false after the first render stops the second.

### Edge cases
- **IME**: `isComposing` returns before any blur (unchanged).
- **Monaco** edits through `div.native-edit-context`, which is not `isContentEditable`, so it saves directly
  (unchanged, deviation log Task 3).
- **A field inside a dialog**: returns early (unchanged).
- **EditableTitle**: blur fires its identity PATCH as before. Save then saves the rest.
- **`flushSync` inside a native `window` listener** is supported. It must never run during render, which it can't.
- **A checkbox or range input** is `HTMLInputElement`, so it blurs and refocuses too. That is harmless.

### Docs
Rewrite the conventions *Cmd/Ctrl+S* sentence (:157-160) as:

> "It blurs a focused field inside `flushSync`, so a blur-committed draft (chip input, section rename) is
> committed before it saves, as a click would, and puts focus back before the handler returns, so keys typed
> right after the chord land in the field."

Delete "a chord inside that gap is swallowed".

---

## F4 — An instant double-click on the referral submit creates two rows

### Locations
- `app/referrals/page.tsx:94-114` (`create`), :151 and :166 (`onAdd={create.mutate}` twice), :226-238
  (`canSubmit` reads `!adding`, `submit` checks `canSubmit`)
- Pins: `backend/tests/test_frontend_referrals.py:138-160`

### Cause
`create.mutate()` changes the mutation to pending synchronously, but `useMutation`'s observer notifies React
on `setTimeout(0)` (`notifyManager.js:3`). Until that task runs, the component's `create.isPending` (so
`adding`, `canSubmit` and the button's `disabled`) is still false. A second click already queued (Playwright
`dblclick`, a fast double-click, or a double Enter) passes every guard and POSTs again. The backend has no
dedup for referrals (`routers/referrals.py:49`).

### The same race elsewhere (inventory)
| Surface | File:line | Guard today | What a double fire costs |
|---|---|---|---|
| Referral create | `app/referrals/page.tsx:151, 166` | `!adding` | **two rows** (verified) |
| New career item | `components/career/new-entity-dialog.tsx:91, 139-141, 394` | `disabled={… create.isPending}` | two entities |
| Capture to inbox | `components/career/capture-box.tsx:31, 71-75, 178` | `disabled` | two LLM extractions, two sets of draft points |
| Read document | `capture-box.tsx:44, 77-84` | `if (ingest.isPending)` toast | two LLM ingests |
| New base résumé | `components/base-resumes/new-base-resume-dialog.tsx:375, 394, 711` | `disabled={!canCreate \|\| busy}` | a success, then a 409 toast ("already exists", `routers/base_resumes.py:228-231`) |
| New template | `app/templates/page.tsx:60, 301-302` | `disabled` | a success, then a 409 toast |
| New application: Extract job | `app/new/page.tsx:61, 130-131` | `disabled={… busy}` | two paid LLM extractions; `_persist_job` returns the twin (`routers/jobs.py:292-303`) |
| Answer questions / Cover letter | `components/qa-tab.tsx:65, 88, 167, 196` | `disabled` | two LLM generations, two entries |
| **Studio Save (click or chord)** | `editor-body.tsx:286-289`, `tailored-resume-studio.tsx:683-686` | `canSave` includes `!busy` | two PATCHes, two version rows, two renders |

"From base" application creation (`ats-score-panel.tsx:269`, the gap page :366) is reuse-or-insert on the
server, so it needs no guard. Chat send already has one (`sendingRef`).

### Options
| Option | Notes |
|---|---|
| **A ref flipped in the handler, cleared on settle, in one hook (recommended)** | the `sendingRef` precedent; works for any `mutate` |
| `qc.isMutating({ mutationKey })` in the handler | exact (it reads the cache synchronously), but every mutation needs a key and every handler needs `qc` |
| `mutateAsync` + local `useState` | state is also stale until a render: the same race |

### Fix design
**`hooks/use-single-flight.ts`**:
```ts
"use client";
import { useRef } from "react";

/**
 * A mutation's `mutate` that starts one request per gesture. `isPending` cannot guard a double click:
 * react-query notifies its observers on a zero-delay timeout, so a second click already queued runs
 * before the re-render that disables the button, reads `isPending === false`, and POSTs again (two
 * referral rows). The ref flips inside the first handler and clears when the request settles.
 */
export function useSingleFlight<TVars>(
  mutate: (vars: TVars, options?: { onSettled?: () => void }) => void,
): (vars: TVars) => void {
  const inFlight = useRef(false);
  return (vars) => {
    if (inFlight.current) return;
    inFlight.current = true;
    mutate(vars, { onSettled: () => { inFlight.current = false; } });
  };
}
```
TanStack's `mutate(vars, { onSettled })` is assignable to that parameter. A per-call `onSettled` does not fire
if the owner unmounts first. The ref dies with it, and every owner above is page- or dialog-owner-level, so it
outlives its form.

**Call sites** (one or two lines each):
- Referrals: `const add = useSingleFlight(create.mutate);` → `onAdd={add}` in both places.
  `canSubmit`/`adding` stay for the label and the disabled state.
- New entity: `const createOnce = useSingleFlight(create.mutate);` and `if (isValid) createOnce();`.
- Capture box: `captureOnce` and `ingestOnce`. Keep the "Still reading…" toast: it still shows once the render
  lands.
- New base résumé: `const submit = useSingleFlight(create.mutate);` and `onClick={() => submit()}`.
- Templates: the Create button.
- `/new`: `const extract = useSingleFlight(extractJob.mutate);`.
- Q&A: `askOnce`, `coverOnce`.
- Studios: `const saveOnce = useSingleFlight(save.mutate);` inside `onSave`'s `commitThen` callback (OWNER
  decision 5).

### Tests / pins
- **`test_frontend_referrals.py::test_one_create_and_the_page_owns_it`** (:138-149): replace the count of
  `adding={create.isPending} onAdd={create.mutate}` with `adding={create.isPending} onAdd={add}` (2) and
  `"const add = useSingleFlight(create.mutate);" in _ROOT`, and assert `onAdd={create.mutate}` is not in `_PAGE`.
- **New `backend/tests/test_frontend_single_flight.py`**:
  ```python
  _SITES = [("app/referrals/page.tsx", "create"), ("components/career/new-entity-dialog.tsx", "create"),
            ("components/career/capture-box.tsx", "capture"), ("components/career/capture-box.tsx", "ingest"),
            ("components/base-resumes/new-base-resume-dialog.tsx", "create"), ("app/templates/page.tsx", "create"),
            ("app/new/page.tsx", "extractJob"), ("components/qa-tab.tsx", "askQuestions"),
            ("components/qa-tab.tsx", "coverLetter")]   # + both studios' "save" if decision 5 = yes
  @pytest.mark.parametrize("rel,name", _SITES)
  def test_a_create_starts_one_request_per_gesture(rel, name):
      src = _read(rel)
      assert f"useSingleFlight({name}.mutate)" in src
      assert f"{name}.mutate(" not in src.replace(f"useSingleFlight({name}.mutate)", ""), \
          "a direct call skips the guard"
  def test_the_guard_flips_before_the_request_and_clears_on_settle():
      hook = _read("hooks/use-single-flight.ts")
      body = hook[hook.index("return (vars) =>"):]
      assert body.index("if (inFlight.current) return;") < body.index("inFlight.current = true;") < body.index("mutate(vars")
      assert "onSettled: () => { inFlight.current = false; }" in re.sub(r"\s+", " ", body)
  ```
  The `.mutate(` exclusion needs care for `capture.mutate` against `capture.mutateAsync`, which doesn't occur
  today. Mutation-check both pins.

### Browser checks
- **Deterministic** (same task, no render between):
  `await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find(x => x.textContent === 'Add referral' && x.type === 'submit'); b.click(); b.click(); })`,
  then `GET /api/referrals` holds exactly one new row. Before the fix this creates two.
- **Real**: `page.dblclick(submit)` and `keyboard.press("Enter")` twice → one row, one toast.
- Repeat the deterministic check for New career item, New template and Extract job (count `POST /api/jobs`
  requests in Network: one).
- A failed create re-enables: block the route, click (error toast), unblock, click → one row. That proves
  `onSettled` clears the guard on error.

### Edge cases
- **A retry after an error** works, because `onSettled` runs on error too.
- **The same form twice on one page** (Referrals: dialog and inline): both share the page's one guard, which is
  correct.
- **`mutateAsync` callers**: none of the listed sites use it. If one does, the hook needs an async twin, so
  don't pass `mutateAsync` to it.

### Docs
In conventions *"A dialog holding a create form keeps its draft…"* (:413-423), after "Every form the page shows
reads the shared pending flag", add:

> "…and submits through `useSingleFlight`: react-query re-renders `isPending` on a zero-delay timeout, so a
> double click read `false` twice and created two rows. Every create and generate button uses it (the chat
> composer's `sendingRef` is the same guard, inline)."

---

## F5 — The chat composer overflows at 768 with the history rail open

### Locations
- `components/chat/chat-page.tsx`:
  - :541 the root `div.relative.flex.h-[calc(100svh-1rem)].gap-4.p-4`;
  - :556-583 the rail `aside.hidden.w-64.shrink-0…md:flex`;
  - :584-594 the "Show chat history" edge button `…hidden…md:flex`;
  - :599 `<main className="flex min-w-0 flex-1 flex-col">`;
  - :602-611 the mobile History button row `md:hidden`;
  - :435-531 the composer (action row :476-529: Attach 32px, the pinned-résumé `SelectTrigger` `w-auto`,
    Context, a `flex-1` spacer, Send);
  - :111-121, :145-154 the matchMedia listener that closes the Sheet at ≥768.
- SYSTEM.md §11 item 31 (the 375 list names "the chat composer's Send").

### Cause (measured by arithmetic, matching the verified 128px)
At 768 the sidebar is still pinned (`MOBILE_BREAKPOINT = 768`): 768 − 256 = 512 for the page. The chat root takes
`p-4` (32), the rail 256 and `gap-4` (16), which leaves `<main>` 208px. The composer's action row doesn't wrap,
and its min-content is about 340px (Attach 32 + Select ≈150 + Context ≈80 + Send 36 + gaps), so it overflows
`<main>` (which is `min-w-0`, `overflow: visible`), and the document scrolls sideways. The rail is gated on the
**viewport** (`md:`), but the space it takes depends on the **sidebar's** state, which the viewport can't see.

### Options
| Option | Fixes 768 | Fixes 375 | Thread width at 768 (pinned) |
|---|---|---|---|
| **(a) Gate the rail on the chat column's own width (container query)** | yes | **no** (the rail is already hidden there) | 480px |
| (b) Let the composer's action row wrap | yes (no sideways scroll) | **yes** | 208px (the rail stays; a 208px thread is barely usable) |
| (c) Hide the rail below `lg` (a viewport breakpoint) | yes | no | 480px pinned, but hides it needlessly at 768–1023 with the sidebar collapsed (712px) |

**Recommend (a)** for this item: the rail is the cause, and the conventions already name the 768–1023 band as the
worst case. **(b)** is the only thing that fixes 375, and it costs two classes, so OWNER decision 6 is whether to
fold it in and delete the chat clause of §11 item 31.

### Fix design (a)
```tsx
// :541 — the chat column measures itself
<div ref={rootRef} className="@container/chat relative flex h-[calc(100svh-1rem)] gap-4 p-4">
// :557 — the rail needs 256 + 16 gap + a ~360px thread, so it shows from a 42rem (672px) content box
<aside className="hidden w-64 shrink-0 flex-col gap-3 @2xl/chat:flex">
// :589 — the collapsed rail's edge button, same gate
className="… hidden h-20 w-7 … @2xl/chat:flex"
// :602 — the Sheet trigger shows exactly when the rail cannot
<div className="flex items-center pb-2 @2xl/chat:hidden">
```
Container queries measure the container's content box, so 768 with the sidebar pinned gives a 480px content box
and the rail hides. The layouts that result:
- **768, sidebar collapsed**: the root is 768 − 56 (the reveal-pill gutter) = 712, and its content box is 680, so
  the rail shows and `<main>` is 408px.
- **1024, sidebar pinned**: content box 736, the rail shows, `<main>` is 464px.
- **375**: content box 287. The rail hides, as today.

`@container` means inline-size containment, which is safe here: the root's width comes from its parent (a
flex-column child).

**Replace the matchMedia listener (:145-154) with a `ResizeObserver` on the root.** It is the same size of code.
The Sheet is a portal that no container query reaches, and the rail now appears at a container width, not at
768:
```tsx
// The Sheet is a portal, so no container query reaches it. Close it when the chat column grows wide enough
// to show the rail (the `@2xl/chat` breakpoint, 42rem), or it would sit over the rail with no trigger left.
useEffect(() => {
  const root = rootRef.current;
  if (!root) return;
  const observer = new ResizeObserver(([entry]) => {
    const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
    if (entry.contentRect.width >= 42 * rem) setHistorySheetOpen(false);
  });
  observer.observe(root);
  return () => observer.disconnect();
}, []);
```
Rewrite the three comments that say "md+" (:116-120, :139-145, :546-555) to name the container query.

**(b), if the owner takes it:**
- the action row (:476) gets `flex flex-wrap items-center gap-1 px-1 pb-0.5`;
- the `SelectTrigger` gets `min-w-0 max-w-full`, and its `SelectValue` child is wrapped in `<span className="truncate">`;
- the `<div className="flex-1" />` spacer goes, and Send gets `ml-auto`.

At 375 (263px inside the pill) the row wraps to Attach and Select, then Context and Send.

### Tests / pins (new `backend/tests/test_frontend_chat_layout.py`, or in `test_frontend_sidebar_nav.py`)
```python
_CHAT = _read("components/chat/chat-page.tsx")
def test_history_rail_is_gated_on_the_chat_column_not_the_viewport():
    assert "@container/chat" in _CHAT
    assert re.search(r'<aside className="hidden w-64 shrink-0 flex-col gap-3 @2xl/chat:flex"', _CHAT)
    assert "@2xl/chat:hidden" in _CHAT            # the Sheet trigger shows exactly when the rail cannot
    assert "md:flex" not in _CHAT and "md:hidden" not in _CHAT
def test_history_sheet_closes_when_the_rail_can_show():
    assert "new ResizeObserver(" in _CHAT and "42 * rem" in _CHAT
    assert 'matchMedia("(max-width: 767px)")' not in _CHAT
# (b) only:
def test_composer_actions_wrap():
    row = _CHAT[_CHAT.index('aria-label="Attach file"') - 400 : _CHAT.index('aria-label="Attach file"')]
    assert "flex-wrap" in row
```

### Browser checks (light and dark)
At each width, check `document.documentElement.scrollWidth <= innerWidth`, that Send's `getBoundingClientRect().right
<= innerWidth`, and whether the rail is visible:
- 768×900, sidebar pinned, rail stored open → no sideways scroll; Send and Context on screen; rail hidden; the
  History button opens the Sheet.
- Press Cmd+B to collapse the sidebar at 768 → the rail appears (container 712), and an open Sheet closes.
- 1280 → the rail is shown, and Hide/Show chat history work (and, if F1-extra is taken, focus moves between them).
- 375 → report the result. With (a) alone Send still overflows (§11 item 31 unchanged). With (b) it doesn't.

### Edge cases
- **Hydration**: the gate is CSS, so there is no client/server mismatch, the same property the `md:` classes
  relied on.
- **`historyCollapsed`** (the stored preference) still decides the rail above the breakpoint. Below it, the rail
  is hidden regardless, and the preference is kept for later.
- **Browser zoom or a larger root font**: 42rem scales, and the observer reads the live root font size.

### Docs
In the conventions "Chat page is Gemini-styled" bullet (:580-582), add:

> "The sessions rail shows only when the chat column's content box is at least 42rem (`@container/chat`, not a
> viewport breakpoint: at 768 the pinned sidebar leaves the column 480px); below that, History opens the same
> list in a Sheet, which a `ResizeObserver` closes when the rail returns."

With (b), also narrow SYSTEM.md §11 item 31 by deleting "the chat composer's Send and".

---

## SYSTEM.md and plan bookkeeping

- **§11 item 29**: if "Also found by reading" (last-referral delete) ships, narrow it to "Escape on the <768px
  sidebar sheet (which also stays open after a nav link is tapped)". Otherwise leave it.
- **§11 item 31**: narrow it only with F5-b.
- **§11 item 32**: add the four no-retry route error branches only if OWNER decision 4 defers them. Find the
  line from 29/31's narrowing to stay under 1000.
- **No new §12 entry**: the two gotchas live in the conventions bullets above, per the two-tier contract.
- `docs/plans/2026-09-22-ux-followups.md` *Next plan*: items 7 (first clause) and 11 are this appendix. The new
  plan's wrap-up replaces them with a pointer.

## Suggested task split for the plan

1. **Helpers and node tests (fail-first)**:
   - `lib/query-state.ts` and `lib/query-state.test.ts`, with the parity case against `unloadedLayer`;
   - `hooks/use-focus-return.ts`, `hooks/use-last-seen.ts`, `hooks/use-single-flight.ts`;
   - `test_frontend_focus.py`'s helper pins.

   Gate: node, tsc, lint.
2. **F2**: `LoadErrorState` (handoff, `useLastSeen`); the 17 callers (4 reordered, Referrals' `?.`, 2 with
   404-as-state); the Formatting panel simplification; the pins in `test_frontend_query_error_states.py`,
   `test_frontend_studio.py` and `test_frontend_referrals.py`; the conventions. It touches the most files, so it
   is best done alone.
3. **F1, studios**:
   - `editor-shell.tsx` (toggles, Widen/Narrow, handoff), `fullscreen-editor-page.tsx`;
   - contact, summary and certifications;
   - `studio-overflow.tsx` and its four overlays, `confirm-dialog.tsx`, Rebuild's `returnFocus`, the raw pane's
     exits;
   - the diagnosis of "Edit raw JSON" first;
   - pins and conventions.

   Plus, per OWNER decision 1: EditableCard, the chat rail toggles, the referral rows and the last-referral delete.
4. **F3 and the blur-unmounting fields**: `use-save-shortcut.ts`; chip-input, section rename and EditableTitle
   commit focus (if decision 1 includes them). This is kept apart from task 3 because the files overlap only
   through the helper.
5. **F4**: `useSingleFlight` at the listed sites, plus Save per decision 5; the pins; the conventions.
6. **F5**: the chat layout, the pins, the conventions, and item 31 per decision 6.
7. **Gate and browser pass**:
   - `pytest tests/ mcp_server/tests/ -q`, `ruff check .`;
   - `node --test lib/*.test.ts`;
   - `npx tsc --noEmit`, `npm run lint`, `npm run build`;
   - the frontend slop ratchet (named, and at or under the start measurement), `check_system_md.py`;
   - Playwright over every browser check above at 1280/768/375, light and dark.

Tasks 2, 3+4, 5 and 6 can run as parallel lanes after task 1. Tasks 3 and 4 share no file if chip-input,
extra-sections and editable-title stay in 4. Task 2 and task 3 both touch `formatting-panel.tsx` only if task 3
edits it, and it doesn't.

## Owner decisions (recommendations in bold)

1. **F1 scope.** Fix only the eight verified drops, or also the read-found drops of the same class (EditableCard
   Edit/Done, the chip inline edit, section rename, EditableTitle, the raw pane's Apply/Cancel, Widen/Narrow at
   their limits, the chat rail toggles, the referral row Edit/Save/Cancel, the last-referral delete in §11 item
   29)? **Recommend all of them.** The Goal says "never", and each costs one to three lines once the helper exists.
2. **Where focus lands after a studio remount** (Load latest, Rebuild, a foreign adoption):
   - **`FullscreenEditorPage`'s `<main tabIndex={-1}>`** (recommended: the studio's own landmark, stable outside
     the remount, one attribute);
   - `#main-content` (no change, but it includes the version banner);
   - the new editor's `<h1>` (it announces "Tailored resume", but it lives inside the remounted subtree, so it
     needs a post-remount effect and a `PageHeader` prop).
3. **After ⋯ → "Edit raw JSON"**: **focus returns to ⋯** (APG menu button; recommended), or it moves into Monaco,
   where Tab indents, so a keyboard user entering unasked is trapped until Ctrl+M.
4. **The four route-level error branches with no retry** (base and tailored studio routes, template editor, tailor
   session): **fold them into F2** (four small `LoadErrorState` swaps; recommended), or file them under §11 item 32.
5. **Studio Save gets `useSingleFlight` too** (a double click or two fast chords makes two PATCHes, two version
   rows and two renders): **yes** (two lines, the same race as the referral).
6. **F5 at 375**: the container-gated rail fixes 768 only. **Also make the composer's action row wrap** (two
   classes, and it deletes the chat clause of §11 item 31)? Recommended: **yes**. The ask said to fix 768 only,
   so this is the owner's call.
