> **Appendix U (unsaved work) to the 2026-09-22 UX next plan.** Research brief written read-only
> against `2cce6139` (branch `claude/ux-next-plan` = local main). Each task in the plan names the
> section it uses. Where this appendix offers options, the plan's "Owner decisions" section is
> binding. Line numbers drift: re-locate before editing.

# Phase U — unsaved work: implementation brief

Worktree `.claude/worktrees/seinun-resume-update-45a8c0`. All paths below are relative to that
root, and line numbers are at `2cce6139`. Source: the *Next plan* list at the end of
`docs/plans/2026-09-22-ux-followups.md`, items 1–4.

**Goal Card line this serves:** honesty about unsaved work outranks convenience. If a gesture
could lose typed text, it asks or keeps the text, and the status line never says "saved" while
something is pending. No new dependencies. Conventions change in the same commit as the code.
Focus never drops to `<body>`.

## 0. Read this first

**Six findings change the directions in the ask:**

1. **`onNavigate` is synchronous, so the guard cannot `await` inside it.** In
   `frontend/node_modules/next/dist/client/app-dir/link.js:71-81`, Link calls `onNavigate({
   preventDefault })` and reads the flag as soon as the call returns. An `await confirm()` before
   `preventDefault()` is too late: the navigation has already been dispatched. So the guard
   **always cancels first when something is unsaved, asks second, and replays the navigation
   through `router.push`/`router.replace` on "Leave"**. The Next docs' own example
   (`link.md` "Blocking navigation") uses `window.confirm`, which is synchronous. We use the
   repo's async `useConfirm`, so the replay is required.
2. **Guarding the named links is not enough: guard every `next/link` in the app.** 31 files
   import `next/link`. A studio holds links beyond its back arrow: `HealthBadges` has three,
   `KbSyncPill` has two, and the error branches have more. Any link added later inside an editor
   would silently lose edits. The fail-closed design is **one `GuardedLink` that wraps `next/link`
   and a pin that no other file imports `next/link`**. It is a drop-in: every `href` in the repo
   is a string (checked), and nothing uses `onNavigate` today. With nothing registered, the wrapper
   is a no-op.
3. **The App Router cannot block Back or Forward.** `popstate` cannot be cancelled. Next's handler
   (`next/dist/client/components/app-router.js:284-301`) is a plain window listener that
   dispatches a traverse. `cacheComponents` is off (`frontend/next.config.ts`), so pages unmount
   on navigation, and a Back press from a dirty studio drops everything. The two workable
   in-app techniques are in U1 §Back/Forward: a sentinel history entry plus a capture-phase
   `popstate` listener, or stash-and-restore. Both have costs, so this is **owner decision 1**.
4. **The gap page cannot use `lib/use-autosave.ts`.** That hook has no debounce, no awaitable flush
   (the Tailor buttons `await saveNow()` and bail on `false`), no stale/409 bail-out, and no
   prompt-only partial PATCH. The debounce also matters beyond performance: a `cannot_confirm`
   resolution writes a **durable** KB record at SAVE time (SYSTEM.md §5 step 5,
   inv-provenance-no-decay), so saving every keystroke would persist a mis-click that the 800 ms
   window currently absorbs. Fix the page's own saver (U2). The two surfaces share only the status
   vocabulary.
5. **Most dialog fixes are deletions, and no shared draft hook is needed.** Four of the five
   dialogs already hold their state *above* `DialogContent`/`SheetContent`. They lose it because
   they call `reset()` on close, or because their caller mounts them conditionally
   (`{open ? <Dialog/> : null}`) or re-keys them. The fifth (`NewBaseResumeDialog`) keeps twelve
   fields and two requests *inside* the popup. Base UI's `Dialog.Portal keepMounted`
   (`@base-ui/react` 1.4.1, `dialog/portal/DialogPortal.js:29`) keeps it alive with one prop.
   Tailwind's preflight `[hidden] { display: none !important }` hides it, because the popup gets
   `hidden` when closed. A generic `useDialogDraft` would only wrap `useState` and would not reduce
   clones.
6. **Several "keep" fixes need a staleness guard, and one needs none.**
   - **Ask for changes** returns index-based ops against the saved résumé with no content hash
     (`BaseResumeProposal`, `lib/types.ts:510-515`). A kept proposal applied after the résumé
     changed would edit the wrong bullets. It needs a client-side basis stamp (U3.2).
   - **Demonstrate skill** carries `content_hash`, and the server rejects a stale apply.
   - **Send to résumé** carries `replaces_text`, which the server checks
     (`backend/app/services/kb_adapt.py:335`).

   Keeping the last two is safe as they are.

**Order:** U1's core (registry, `GuardedLink`, one `beforeunload`) goes first, because U2 and U4
register with it. U3 is independent and can run in parallel. U1's Back/Forward part is a
separate task behind owner decision 1.

## Global constraints (read before writing any step)

- **Lint (`npm run lint`) has the React Compiler rules at error level**: `react-hooks/refs` (no
  `ref.current` read during render), `react-hooks/set-state-in-effect`,
  `react-hooks/set-state-in-render`. I probed every new shape in this appendix with
  `npx eslint --stdin --stdin-filename components/__probe.tsx` (nothing written). All reported
  **0 errors**:
  - the registry hook (`useId` + an effect calling a module function);
  - `GuardedLink` (a registry read inside `onNavigate`);
  - the listeners component (window listeners in a mount effect; refs and closure variables read
    only inside handlers);
  - a "latest callback" ref assigned in a dependency-less effect;
  - `flushSync(() => setX(false)); ref.current?.focus()` inside an async click handler.

  The registry is read **only in event handlers**, never during render. That is why it can be
  module state with no `useSyncExternalStore`. The "adjust state while rendering on prop change"
  pattern (`if (prop !== prev) { setPrev(prop); … }`) passes too (A1 appendix, re-used in
  U3.5). Run lint after every step.
- **Frontend duplication ratchet: 505 duplicated lines / 42 clones must not rise** (Task 19
  gate). The committed `frontend/.slop-baseline.json` still says 518/43, so the tool would let
  13 lines through. The plan's ceiling is the measured 505/42, and a task's claim must quote the
  number. jscpd `min_tokens` is 50. Mitigations used below:
  - one `useConfirmLeave` and one `useConfirmDiscard` hold each confirm's copy;
  - `GuardedLink` replaces imports rather than adding wrapper JSX at call sites;
  - the dialog fixes mostly delete code.

  Run `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend` and name
  the surface in the claim.
- **`lib/*.ts` imports only relative paths or bare packages** (no `@/`), so the node tests can
  load them. The new `lib/leave-guard.ts` has **no imports at all**. React hooks go in
  `hooks/` or `components/`.
- **Node tests (`frontend/lib/*.test.ts`) are NOT in CI.** Any behaviour that lives in `lib/*.ts`
  also needs a pytest source pin in `backend/tests/test_frontend_*.py`, which runs in CI.
  Run the node tests with `cd frontend && node --test lib/*.test.ts` (85 at the previous gate).
  Tests import with the `.ts` extension (`lib/nav.test.ts` precedent).
- **Next 16.3.0** (`node_modules/next/package.json`). Facts used below, read from
  `node_modules/next/dist`:
  - `onNavigate` does not fire for modifier-clicks, `download` links or external URLs
    (`link.md:499-503`, `link.js:56-69`);
  - Next patches `history.pushState`/`replaceState`, and passes a state that carries `__NA`
    straight through with no router action (`app-router.js:249-277`);
  - Next's `HistoryUpdater` rewrites the current entry's state on every router-state change
    (`app-router.js:38-67`).
- **SYSTEM.md is at 999/1000 lines.** This phase should be net-negative there. It deletes one
  clause of §11 item 32 and adds nothing unless a §12 gotcha bites during the work. New rules go
  in `docs/frontend-conventions.md` (the reference tier). Run `python3 scripts/check_system_md.py`.
- **Pins**: `cd backend && pytest tests/test_frontend_*.py -q` (284 at the previous gate), then
  the full suite `pytest tests/ mcp_server/tests/ -q`.

---

## U1 — Leaving an editor through an in-app link loses unsaved edits

### Locations
- `frontend/hooks/use-unsaved-changes-warning.ts:25-35`: the only guard, `beforeunload` only.
  Its doc comment (:14-19) says "the App Router gives no navigation-blocking hook". That is
  false for links since Next added `onNavigate`, and still true for Back/Forward.
- Callers:
  - `components/resume-editor/editor-body.tsx:277` `useUnsavedChangesWarning(hasUnsavedChanges)`;
  - `components/resume-editor/tailored-resume-studio.tsx:592` `useUnsavedChangesWarning(dirty)`.
- `app/templates/[id]/page.tsx`: **no guard at all**. `dirty` state at :37, set on every source
  keystroke (:326-329), cleared by Save and Recompile (:74, :105).
- Studio back arrows:
  - `editor-body.tsx:342-345` `<Link href="/base-resumes" …/>`;
  - `tailored-resume-studio.tsx:319` (the no-draft branch) and :769 `<Link href={backHref} …/>`;
  - `app/templates/[id]/page.tsx:241` (and the error branch :188).
- Links inside the studios:
  - `components/resume-health/health-badges.tsx:85,102,147` (the health report);
  - `components/kb-sync-pill.tsx:126,246` (`/career`).
- Sidebar: `components/app-sidebar.tsx:125-138` (the FAB `/new`), :171 (every nav row, both
  `<nav>`s).
- `useConfirm`: `components/confirm-dialog.tsx:34-112`. A destructive confirm lands initial
  focus on Cancel (:84). It is mounted in `app/providers.tsx` around `{children}`, and the
  sidebar sits inside it (`app/layout.tsx`).
- All `next/link` importers (31): `grep -rln 'from "next/link"' frontend/app frontend/components`.

### Current code
```ts
// hooks/use-unsaved-changes-warning.ts
export function useUnsavedChangesWarning(when: boolean) {
  useEffect(() => {
    if (!when) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [when]);
}
```
```tsx
// editor-body.tsx:335-347 (the tailored and template back arrows have the same shape)
<IconButton label="Back to base resumes" icon={<ArrowLeft className="size-4" />} size="icon-sm"
  className="mt-1.5 shrink-0" nativeButton={false}
  render={<Link href="/base-resumes" className="text-muted-foreground" />} />
```

### Cause
- A `<Link>` click is a client-side navigation, so `beforeunload` never fires. The editor
  unmounts, and its `useState` working copy goes with it.
- Browser Back/Forward is the same: a `popstate` handled by Next, which unmounts the page.
- The template editor tracks `dirty` but registers nothing, so even a reload loses the source.

### Options and trade-offs (link clicks)
| Option | Coverage | Cost / risk |
|---|---|---|
| A. Add `onNavigate` at each named site (back arrows, sidebar) | Only the sites edited. Health badges, KB pill and future links leak | Many call-site edits, and every new link needs remembering. Pins would list sites, not a rule |
| **B. `GuardedLink` wraps `next/link`; it is the app's only `next/link` importer (recommended)** | Every in-app link, now and later, fail-closed by one pin | 31 one-line import swaps. Uses the API the Next docs endorse, and keeps Link's prefetch/`replace`/`scroll` behaviour |
| C. Document-level capture `click` listener on `<a>` | Every anchor, zero call-site edits | Bypasses Link. `replace`/`scroll` props become invisible, so the listener must re-derive modifier/target/download/origin rules. `stopPropagation` at the document also kills the click for every React ancestor |

**Recommend B.** A `router.push` fired after an action is a separate path (no `onNavigate`).
The audit found **no `router.push`/`replace` that can fire while a guard is registered on the
same page**:
- the studios and the template editor have no router calls;
- the gap page's pushes come after `saveNow()` succeeds (Tailor) or make the edits moot (Use base
  as-is, Start over);
- entity delete (`entity-detail.tsx:97`) is not an editor exit.

So nothing wraps `router.push` today. `useConfirmLeave()` exists for the next one, and the
conventions bullet says so.

### Fix design

**`frontend/lib/leave-guard.ts`** (new, pure, no imports, node-testable):
```ts
/**
 * Who holds unsaved work, so every exit can ask first (docs/frontend-conventions.md,
 * "Leaving with unsaved work"). Module state, not React state: the readers are event
 * handlers (a link's onNavigate, beforeunload, popstate) that need the value at the
 * moment of the gesture, and nothing renders from it.
 *
 * Two scopes. "all": an in-app exit asks and reload/close warns. "unload": only
 * reload/close warns, for work an in-app exit still saves (a debounced autosave flushes
 * on unmount, and a page unload runs no cleanup).
 */
export type LeaveScope = "all" | "unload";

const owners = new Map<string, LeaveScope>();
const listeners = new Set<(blocked: boolean) => void>();
let unloadBypass = false;

export function leaveBlocked(exit: "in-app" | "unload"): boolean {
  if (exit === "unload") return owners.size > 0;
  for (const scope of owners.values()) if (scope === "all") return true;
  return false;
}

/** `null` removes the owner. Listeners hear only in-app transitions (U1 Back/Forward). */
export function setLeaveGuard(owner: string, scope: LeaveScope | null): void {
  const before = leaveBlocked("in-app");
  if (scope === null) owners.delete(owner);
  else owners.set(owner, scope);
  const after = leaveBlocked("in-app");
  if (before !== after) for (const fn of listeners) fn(after);
}

export function onInAppBlockedChange(fn: (blocked: boolean) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** The user already chose "Leave": a hard navigation that follows must not ask again. */
export function allowLeave(): void {
  unloadBypass = true;
}
export function consumeLeaveBypass(): boolean {
  const bypass = unloadBypass;
  unloadBypass = false;
  return bypass;
}
export function clearLeaveBypass(): void {
  unloadBypass = false;
}
```
Module state is safe under SSR: only effects write it, and effects never run on the server.

**`frontend/hooks/use-leave-guard.ts`** (replaces `use-unsaved-changes-warning.ts`, which is deleted):
```ts
"use client";

import { useEffect, useId } from "react";

import { setLeaveGuard } from "@/lib/leave-guard";

/**
 * Register unsaved work while `when` holds. In-app links (GuardedLink) then ask
 * "Leave without saving?", and reload/close shows the browser's own warning.
 * `reloadOnly`: work an in-app exit still saves (it flushes on unmount), so only a
 * page unload, which runs no cleanup, needs the warning.
 */
export function useLeaveGuard(when: boolean, { reloadOnly = false }: { reloadOnly?: boolean } = {}) {
  const owner = useId();
  const scope = when ? (reloadOnly ? "unload" : "all") : null;
  useEffect(() => {
    setLeaveGuard(owner, scope);
    return () => setLeaveGuard(owner, null);
  }, [owner, scope]);
}
```

**`frontend/components/guarded-link.tsx`** (new):
```tsx
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ComponentProps, useCallback } from "react";

import { useConfirm } from "@/components/confirm-dialog";
import { allowLeave, leaveBlocked } from "@/lib/leave-guard";

/** True at once when nothing is unsaved, else asks. The one copy of the question. */
export function useConfirmLeave() {
  const confirm = useConfirm();
  return useCallback(
    async () =>
      !leaveBlocked("in-app") ||
      confirm({
        title: "Leave without saving?",
        description: "Changes you haven't saved on this page will be lost.",
        confirmLabel: "Leave",
        cancelLabel: "Stay",
        destructive: true,
      }),
    [confirm],
  );
}

type GuardedLinkProps = Omit<ComponentProps<typeof Link>, "href" | "onNavigate"> & {
  href: string;
};

/**
 * The app's only `next/link` (pinned by test_frontend_leave_guard.py). With nothing
 * unsaved it IS Link. With unsaved work it cancels first and asks second: Link reads
 * `preventDefault` the moment `onNavigate` returns (next/dist/client/app-dir/link.js),
 * so an awaited confirm would be too late. On "Leave" it replays the navigation through
 * the router. Modifier-clicks, downloads and external URLs never reach `onNavigate`, and
 * none of them unmounts this page.
 */
export function GuardedLink({ href, replace, scroll, ...props }: GuardedLinkProps) {
  const router = useRouter();
  const confirmLeave = useConfirmLeave();
  return (
    <Link
      {...props}
      href={href}
      replace={replace}
      scroll={scroll}
      onNavigate={(event) => {
        if (!leaveBlocked("in-app")) return;
        event.preventDefault();
        void confirmLeave().then((leave) => {
          if (!leave) return;
          allowLeave();
          if (replace) router.replace(href, { scroll });
          else router.push(href, { scroll });
        });
      }}
    />
  );
}
```
- `ref`, `className`, `aria-current` and Base UI's merged `onClick`/`ref` from
  `render={<GuardedLink …/>}` all pass through `...props`. React 19 treats `ref` as a prop.
  Link calls `onClick` before `linkClicked`, and `onNavigate` after it (`link.js:317-339`).
- **Import swap in all 31 files**: `import Link from "next/link"` becomes
  `import { GuardedLink as Link } from "@/components/guarded-link"`. The alias keeps every JSX
  line unchanged, so the diff adds no clones. The one exception is `components/guarded-link.tsx`
  itself. `app/not-found.tsx` is a server component, and rendering a client `GuardedLink` from
  it is fine (string props only).
- **`GuardedLink` needs `ConfirmDialogProvider` above it**, because `useConfirm` throws otherwise.
  `app/global-error.tsx` replaces the root layout and has no provider. It imports no Link
  today, and the pin keeps it that way (it must use a plain `<a>`).

**`frontend/components/leave-guard-listeners.tsx`** (new; rendered once in `app/providers.tsx`
inside `<ConfirmDialogProvider>`, beside the `Toaster`):
```tsx
"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

import { clearLeaveBypass, consumeLeaveBypass, leaveBlocked } from "@/lib/leave-guard";

/**
 * The app's ONE beforeunload listener (it used to be one per editor, which also meant
 * one per mounted editor). It reads the registry at the moment of the unload, so it
 * warns only while something is registered. It stays quiet for a hard navigation the
 * user already confirmed in GuardedLink, which would otherwise ask twice.
 */
export function LeaveGuardListeners() {
  const pathname = usePathname();
  // A confirmed "Leave" that became a client navigation leaves no unload to bypass.
  useEffect(() => {
    clearLeaveBypass();
  }, [pathname]);
  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!leaveBlocked("unload") || consumeLeaveBypass()) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, []);
  return null;
}
```
`usePathname` needs no `<Suspense>`; only `useSearchParams` does (conventions, sidebar bullet).

**Adopters in this plan:**

| Surface | Call | Why this flag |
|---|---|---|
| Base studio `editor-body.tsx:277` | `useLeaveGuard(hasUnsavedChanges)` | Unchanged input. It already includes `raw.pending` and clears on the Save response (`markSynced`) |
| Tailored studio `tailored-resume-studio.tsx:592` | `useLeaveGuard(unsaved)`: move the call below `unsaved` (:610) | See below |
| Template editor `app/templates/[id]/page.tsx` | `useLeaveGuard(dirty)` after the `dirty` state | Source edits are explicit-save. Knob edits autosave and flush on unmount (:147-159) |
| Gap page | U2 | Autosave: `reloadOnly` while pending, full while failed |
| Settings autosave cards | U4.3 | Only after a failed write |

**Tailored studio: `unsaved`, not `dirty`.** `dirty` stays true in the post-save refetch gap
(it compares against the pre-save server copy until the `["application"]` refetch). With an
in-app guard, pressing Back right after Save would ask "Leave without saving?" about a save
that already landed. `unsaved` differs from `dirty` only in that gap, and in that gap the
content is on the server, so a reload loses nothing either. `dirty` keeps feeding
`onDirtyChange` (the adoption guard). The existing pin `onDirtyChange(dirty)` is unaffected.

**Candidates beyond this plan** (each one is a single `useLeaveGuard(...)` line now that every
link is guarded). This is **owner decision 2**:
- Persona (`persona-section.tsx:117`, `dirty`) and Autofill (`autofill-section.tsx:471`),
  dirty-gated Save cards;
- Prompts (`prompts-section.tsx:113-114`);
- `/new` (a pasted JD, `rawText` at `app/new/page.tsx:22`);
- the Q&A cover-letter editor (U4.1);
- the chat composer (`chat-page.tsx:100` `input`). The session rail's `router.replace`
  (`chat-page.tsx:97-98`) keeps the composer mounted and loses nothing; leaving `/chat` does
  lose it.

### Back / Forward (owner decision 1)
What the App Router allows: nothing that blocks. `popstate` fires after the URL has already
moved. Next's listener is on `window` and is not a capture listener
(`app-router.js:301`). A listener added with `{ capture: true }` runs first at the target, and
`stopImmediatePropagation()` keeps Next from rendering the destination. The URL has still moved,
though, and plain `popstate` gives no direction to undo it.

| Option | Behaviour | Cost / risk |
|---|---|---|
| **A. Sentinel + ask (recommended)** | While in-app work is unsaved, a duplicate history entry of the current URL sits on top. Back lands on the real entry (same URL, page still mounted), the capture listener stops Next and asks. Leave goes `history.back()` again; Stay re-parks the sentinel | ~50 lines in `LeaveGuardListeners`, and the table's edge rows below. It relies on Next passing `__NA` state through its patched `pushState` (internal, verified at 16.3.0), so a Next upgrade must re-run browser check U1-7 |
| B. Stash and restore ("keeps the text") | Each editor stashes its working copy (module memory, keyed by route and server `serverKey`) on unmount, and offers "Restore your unsaved edits?" on remount if the baseline is unchanged | Per-editor work across three different state shapes, plus a new banner. No history tricks. A reload still loses the stash unless it goes in sessionStorage (résumé PII in storage) |
| C. Accept, and file §11 | Links, reload and close are guarded; Back/Forward silently drops edits | Contradicts the Goal Card for a common gesture: mouse back buttons, Cmd+[ and trackpad swipe in browsers. The divider already passes Alt/Ctrl/Meta+Arrow through as Back/Forward |

Design A (added to `LeaveGuardListeners`; it needs `useConfirmLeave`):
```tsx
const SENTINEL = "__leaveGuard";
const onSentinel = () =>
  Boolean((window.history.state as Record<string, unknown> | null)?.[SENTINEL]);
// Carries Next's `__NA` and tree, so Next's patched pushState passes it straight
// through (no router action), and a later traverse to it still renders this route.
const pushSentinel = () =>
  window.history.pushState({ ...window.history.state, [SENTINEL]: true }, "", window.location.href);

const confirmLeave = useConfirmLeave();
useEffect(() => {
  let armed = false; // our sentinel is (or was) above the real entry
  let swallow = 0;   // popstates we caused ourselves
  const stop = onInAppBlockedChange((blocked) => {
    if (blocked && !armed) {
      pushSentinel();
      armed = true;
    } else if (!blocked && armed) {
      armed = false;
      // Saved while parked on the sentinel: step off it, or the next Back is a dead press.
      if (onSentinel()) {
        swallow += 1;
        window.history.back();
      }
    }
  });
  const onPopState = (event: PopStateEvent) => {
    if (swallow > 0) {
      swallow -= 1;
      event.stopImmediatePropagation();
      return;
    }
    if (!armed || onSentinel()) return;
    armed = false; // Back off the sentinel: same URL, and the editor is still mounted
    if (!leaveBlocked("in-app")) return;
    event.stopImmediatePropagation();
    void confirmLeave().then((leave) => {
      if (leave) {
        allowLeave();
        window.history.back();
      } else {
        pushSentinel();
        armed = true;
      }
    });
  };
  window.addEventListener("popstate", onPopState, { capture: true });
  return () => {
    stop();
    window.removeEventListener("popstate", onPopState, { capture: true });
  };
}, [confirmLeave]);
```
`GuardedLink` then uses `router.replace` instead of `push` when `onSentinel()` holds. Otherwise
a later Back from the new page would land on the sentinel and then on a dead same-URL step.
Export `onSentinel` from the listeners module, or keep the flag in `lib/leave-guard.ts`.

| Edge (option A) | Outcome |
|---|---|
| First edit on a page reached by Back | The forward entries are dropped (a `pushState` truncates). This is the same as any navigation, and should be stated in the conventions |
| Reload while parked | The sentinel survives the reload. After it, the first Back is a same-URL no-op |
| Next rewrites the current entry's state (`HistoryUpdater` on a router change such as `router.refresh`/`replace`) | The marker is lost, and Back leaves unguarded. No registered page does either today. Pin that the three editor surfaces import no `useRouter`, and re-check when an adopter does (the chat composer would) |
| A second Back while the dialog is open | The browser moves again, and Next renders that entry under the dialog. The swallow counter does not cover it. It is rare. Make the dialog modal-first: mark it `asking`, and while asking `stopImmediatePropagation()` every `popstate`, then `history.go(n)` back after the answer. Verify by hand (U1-8) |
| WebKit desktop shell | `beforeunload` dialogs depend on the host's UI delegate, and may not show in a WKWebView. The in-app guard (A) works there, which argues for A |

### Tests / pins
New `backend/tests/test_frontend_leave_guard.py`:
- `test_next_link_is_imported_only_by_guarded_link`: walk `frontend/app`, `components`,
  `hooks` and `lib` (`*.ts`, `*.tsx`). The files containing `from "next/link"` must be exactly
  `{components/guarded-link.tsx}`. Match the import, not the word: `app/applications/page.tsx:566`
  has a comment mentioning `<Link>`.
- `test_guarded_link_cancels_before_it_asks`: in `guarded-link.tsx`, `onNavigate=` is present,
  and `leaveBlocked("in-app")` < `event.preventDefault()` < `confirmLeave()` by index.
  `allowLeave()` must come before both `router.push(` and `router.replace(`, and no `await`
  appears before `event.preventDefault()`.
- `test_leave_confirm_copy`: `title: "Leave without saving?"`, `confirmLabel: "Leave"`,
  `cancelLabel: "Stay"` and `destructive: true` in `useConfirmLeave`, and
  `"Leave without saving?"` appears exactly once across the frontend.
- `test_one_beforeunload_listener`: `"beforeunload"` appears in exactly one file under `app/`,
  `components/` and `hooks/` (`leave-guard-listeners.tsx`). That file reads
  `leaveBlocked("unload")` and `consumeLeaveBypass()`.
- `test_listeners_sit_inside_the_confirm_provider`: in `app/providers.tsx`,
  `<ConfirmDialogProvider>` < `<LeaveGuardListeners />` < `</ConfirmDialogProvider>`.
- `test_editors_register`:
  - `useLeaveGuard(hasUnsavedChanges)` in `editor-body.tsx`;
  - `useLeaveGuard(unsaved)` in `tailored-resume-studio.tsx`, and `useLeaveGuard(dirty)` not in
    it;
  - `useLeaveGuard(dirty)` in `app/templates/[id]/page.tsx`;
  - `hooks/use-unsaved-changes-warning.ts` does not exist, and `useUnsavedChangesWarning` appears
    nowhere.
- `test_leave_store_is_pure`: `lib/leave-guard.ts` has no `import` line. It defines
  `leaveBlocked(exit: "in-app" | "unload")`, `setLeaveGuard(`, `allowLeave(` and
  `consumeLeaveBypass(`. The in-app branch tests `scope === "all"` (mutation check: flipping it
  to `owners.size > 0` must fail a pin, so pin that exact expression).
- `test_registered_editors_have_no_router`: `useRouter` appears in none of `editor-body.tsx`,
  `tailored-resume-studio.tsx` or `app/templates/[id]/page.tsx`. This guards option A's marker
  (drop it if A is not chosen).
- If A is chosen: `{ capture: true }` and `stopImmediatePropagation()` are in the listeners
  file, and `GuardedLink` calls `router.replace` when `onSentinel()` holds.

New `frontend/lib/leave-guard.test.ts` (node, not CI):
- empty → both exits false;
- `"unload"` owner → unload true, in-app false;
- `"all"` → both true;
- removing the last `"all"` owner fires the listener with `false` exactly once;
- re-setting the same scope fires nothing;
- `consumeLeaveBypass()` is true once, then false.

### Browser checks (throwaway stack; memory: worktree verification recipe)
1. Base studio: edit the summary, click the sidebar's Applications. "Leave without saving?"
   appears with initial focus on **Stay**. Stay keeps the edit, and focus returns to the sidebar
   link. Repeat, and Leave navigates with no browser dialog after it.
2. Same through the back arrow, the health badge link and the KB pill's `/career` link.
3. Tailored studio: Save, then immediately click Back. There is **no** prompt (`unsaved` is false
   once the Save response lands).
4. Template editor: type in Code and click Back to templates: prompt. Reload: the browser's
   warning. Save, then click Back: no prompt.
5. A clean studio: every link navigates with no prompt, and Cmd/Ctrl+click opens a new tab with
   no prompt.
6. At 375px the sidebar is a sheet: with an edit pending, tap a nav row. The confirm must take
   focus above the sheet (two Base UI modal roots), and Stay returns focus into the sheet. A
   focus fight here blocks the task.
7. (Option A) An edited studio: browser Back → prompt. Stay: the URL and page are unchanged, and
   the edit is there. Back again → prompt. Leave → the previous page. Save, then Back → the
   previous page in one press (the sentinel popped).
8. (Option A) Press Back twice fast with an edit pending (see the edge table).
9. Light and dark, 1280 and 375.

### Edge cases / risks
- **Concurrent confirms.** `ConfirmDialogProvider` holds one resolver (`resolverRef`,
  `confirm-dialog.tsx:45-55`). A second request overwrites the first, whose promise never
  settles. A second link click during the prompt is harmless: the first promise hangs, and the
  second click's answer acts. Do not "fix" this by queueing.
- **Focus after "Leave":** Next's layout router calls `domNode.focus()` on the new segment
  (`layout-router.js:236`), a no-op on a non-focusable div. This matches every link click today
  and is out of scope.
- **Template editor knob debounce** (400 ms, `:160-167`): a reload inside the window loses one
  knob change (the unmount flush does not run on unload). This is minor. Registering it would
  mean reading a ref in render, so leave it.
- **Leaving mid-save.** The studios stay registered while a Save is in flight, so leaving then
  asks, even though the PUT/PATCH completes server-side. Only edits typed after the send are
  really at risk. The prompt is over-cautious here, which is acceptable.

### Docs
- `docs/frontend-conventions.md`, new bullet after the studio block, **"Leaving with unsaved work
  asks."** It covers:
  - `useLeaveGuard(when, { reloadOnly })` and the two scopes;
  - `GuardedLink` as the only `next/link` importer, and why (fail-closed);
  - "cancel first, ask second, replay";
  - the one `beforeunload` listener and the bypass;
  - a `router.push` from a registered page goes through `useConfirmLeave()` first;
  - Back/Forward per owner decision 1.
- Rewrite *Tailored studio* (:204-209), "`dirty` stays the input to the external-edit adoption
  guard (SYSTEM.md §12) and the leave-page warning", to "…adoption guard; the leave guard reads
  `unsaved`".
- The hook's doc comment moves into `use-leave-guard.ts` (the old claim about links is dropped).
- SYSTEM.md: no change. The "App Router has no navigation-blocking hook" fact lives in the
  conventions bullet. Add a §12 gotcha only if one bites in the browser pass (for example the
  `onNavigate` sync trap), and pay for it by grooming.

---

## U2 — Gap-answer page autosave: "Saved" while an edit waits; leaving within 800 ms drops keystrokes

### Locations (`frontend/app/jobs/[id]/tailor/[sessionId]/page.tsx`)
- :53 `type SaveState = "idle" | "saving" | "saved" | "error"`;
- :55-69 `SaveIndicator`, which returns `null` when idle, so its `aria-live` region mounts
  together with its first message;
- :186-195 the timer, and an unmount effect that only clears it;
- :197-248 `saveNow`;
- :328-348 `handleChange`;
- :350-359 `handlePromptChange`;
- :587 the back link;
- :689 `<SaveIndicator state={saveState} />`.
- Every keystroke in a gap card commits through `onChange` (`components/gap-analysis/gap-card.tsx`:
  `onTextChange` :704-711, `onWordingChange` :671-683), so `handleChange` runs per keystroke.

### Current code
```tsx
useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);  // :190-195
…
const handleChange = (gapId, resolution) => {
  …
  latestRef.current = next;
  setEdited(next);
  if (timerRef.current) clearTimeout(timerRef.current);
  if (!tailor.isPending && !staleReason) {
    timerRef.current = setTimeout(() => { void saveNow(); }, 800);   // no setSaveState
  }
};
// saveNow: setSaveState("saving") … await run; setSaveState("saved")   (:206, :226)
```

### Cause
1. **Stale "Saved".** The edit handlers never touch `saveState`, so after one save lands the
   line reads "Saved" through the whole 800 ms debounce of the next edit.
2. **"Saved" while newer edits wait, even after the debounce.** `saveNow` sets "saved" when *its*
   request resolves. If the user typed during that request, a newer save is already scheduled or
   chained, and the older resolution still paints "Saved".
3. **Unmount drops the tail.** The cleanup cancels the pending timer instead of firing it. The
   back link, the sidebar or any Link within 800 ms of the last keystroke discards it.
   `notes-editor.tsx:68-77` and the template editor's knob flush (`:147-159`) show the repo's
   fix: flush on unmount.

### Why not `useAutosave`
See §0 finding 4. It lacks a debounce, which the durable `cannot_confirm` write needs, and an
awaitable `flush(): Promise<boolean>` for Tailor and Quick tailor. It also lacks the 409/stale
bail-out and the prompt-only PATCH (`promptRef` null = omit). Retro-fitting all of that into a
hook four settings cards share is a bigger blast radius than the page's own saver. Revisit only
if a third debounced autosave appears.

### Fix design
States stay `idle | saving | saved | error`. **"Saving…" now covers the debounce too**: from
the first keystroke until the newest edit is on the server. For an autosave, an edit waiting its
turn *is being saved*; "Unsaved changes" would imply an action the user must take.
```tsx
// Bumped by every edit. A save reports "Saved"/"Save failed" only if no edit came
// after it began; otherwise a newer save is queued behind it and will report.
const editGen = useRef(0);

const saveNow = async (): Promise<boolean> => {
  if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
  if (staleReason) return true;
  if (latestRef.current === null && promptRef.current === null) return true;
  const gen = editGen.current;
  setSaveState("saving");
  … // attempt / chain unchanged
  try {
    await run;
    if (editGen.current === gen) setSaveState("saved");
    return true;
  } catch (error) {
    if (editGen.current === gen) setSaveState("error");
    … // toasts unchanged
    return false;
  }
};

/** One schedule for both handlers (was duplicated in :339-347 and :353-358). */
const scheduleSave = () => {
  editGen.current += 1;
  if (timerRef.current) clearTimeout(timerRef.current);
  // No autosave while tailoring (the pre-tailor flush already ran) or stale (every save 409s).
  if (tailor.isPending || staleReason) return;
  setSaveState("saving");
  timerRef.current = setTimeout(() => { void saveNow(); }, 800);
};
// handleChange: …latestRef.current = next; setEdited(next); scheduleSave();
// handlePromptChange: promptRef.current = value; setPromptDraft(value); scheduleSave();

// Leaving within the debounce saves instead of dropping the tail (notes-editor's rule).
// saveNow changes every render; the cleanup must call the newest one.
const saveNowRef = useRef(saveNow);
useEffect(() => { saveNowRef.current = saveNow; });
useEffect(() => () => {
  if (!timerRef.current) return;
  clearTimeout(timerRef.current);
  timerRef.current = null;
  void saveNowRef.current();
}, []);

// Reload/close cannot flush; an in-app exit can. A failed save is unsaved either way.
useLeaveGuard(saveState === "saving", { reloadOnly: true });
useLeaveGuard(saveState === "error");
```
- `scheduleSave` replaces two copies of the same block, which is a small duplication win in a file
  that has 2 clones in the baseline.
- `setSaveState` after unmount is a no-op. A flush that fails after the page is gone still
  toasts ("Failed to save resolutions"), so the user learns it on the next page. The text itself
  is gone; see the edge cases.
- React StrictMode's dev double-mount runs the cleanup with no timer pending, so nothing fires.

**`SaveIndicator`** (always mounted, so the live region exists before its first message; a retry
on failure):
```tsx
function SaveIndicator({ state, onRetry }: { state: SaveState; onRetry: () => Promise<boolean> }) {
  const statusRef = useRef<HTMLSpanElement>(null);
  const refocus = useRef(false);
  // A STATE, not the ref: whether the button renders is decided during render, where
  // the compiler forbids ref reads. It keeps Try again mounted (and focused) while the
  // retry runs, since `state` flips to "saving" at once.
  const [retrying, setRetrying] = useState(false);
  // Try again unmounts once the retry lands; move focus to the status, not <body>.
  useEffect(() => {
    if (retrying || state !== "saved" || !refocus.current) return;
    refocus.current = false;
    statusRef.current?.focus();
  }, [state, retrying]);
  return (
    <span className="flex items-center gap-2 text-xs">
      <span ref={statusRef} tabIndex={-1} aria-live="polite"
        className={cn("flex items-center gap-1", state === "error" ? "text-destructive" : "text-muted-foreground")}>
        {state === "saving" && <Loader2 className="size-3 animate-spin" aria-hidden="true" />}
        {state === "saving" ? "Saving…" : state === "saved" ? "Saved" : state === "error" ? "Save failed" : null}
      </span>
      {state === "error" || retrying ? (
        <Button type="button" variant="link" size="xs" className="h-auto p-0 data-disabled:opacity-50"
          focusableWhenDisabled disabled={retrying}
          onClick={() => {
            refocus.current = true;
            setRetrying(true);
            void onRetry().finally(() => setRetrying(false));
          }}>
          Try again
        </Button>
      ) : null}
    </span>
  );
}
```
Wire it at :689 as `<SaveIndicator state={saveState} onRetry={saveNow} />`. If the retry fails
again, the button stays mounted, so focus stays on it. `focusableWhenDisabled` needs the explicit
`data-disabled:` dimming (conventions, *Status line*: `disabled:` matches only the native
attribute).

### Tests / pins
New `backend/tests/test_frontend_gap_autosave.py` (slice `_PAGE` the way `test_frontend_referrals.py`
does):
- `test_every_edit_says_saving`: `handleChange` and `handlePromptChange` both call
  `scheduleSave()`. `scheduleSave` bumps `editGen.current += 1`. `setSaveState("saving")` comes
  after the `if (tailor.isPending || staleReason) return;` line and before `setTimeout(`.
- `test_saved_only_when_nothing_newer`: in `saveNow`, `const gen = editGen.current` precedes
  `await run`, and both `setSaveState("saved")` and `setSaveState("error")` are guarded by
  `if (editGen.current === gen)`.
- `test_unmount_flushes_instead_of_dropping`: the mount-once cleanup contains
  `void saveNowRef.current()` after `clearTimeout(timerRef.current)`, and
  `saveNowRef.current = saveNow` is assigned in an effect.
- `test_failed_save_offers_retry_and_guards_leaving`: `SaveIndicator` renders "Save failed" and a
  "Try again" `Button` with `focusableWhenDisabled`. There are two `useLeaveGuard(` calls:
  `saveState === "saving", { reloadOnly: true }` and `saveState === "error"`.
- `test_indicator_live_region_is_always_mounted`: `SaveIndicator` has no `return null` before its
  `aria-live` span.

### Browser checks
1. Answer a gap; "Saved" appears. Type one more character. The line reads "Saving…" at once
   (not "Saved"), then "Saved".
2. Type a sentence continuously for 3 s under a DevTools network throttle (Slow 4G). The line never
   shows "Saved" until the last PATCH resolves.
3. Type, then click Back to job within 800 ms. Reopen the session: the last characters are there.
   Repeat through the sidebar.
4. Type, then reload within 800 ms: the browser warns.
5. Stop the backend and type: "Save failed" plus Try again, and a toast. Clicking a sidebar link
   asks "Leave without saving?". Restart the backend and press Try again from the keyboard:
   focus stays on the button while it runs, then moves to the status line reading "Saved".

### Edge cases / risks
- **Edits typed while tailoring are dropped.** The region is `pointer-events-none opacity-60`
  (:606-611), but keyboard typing into an already-focused textarea still works. `scheduleSave`
  returns early, and Tailor then navigates away. Pre-existing. Recommend `readOnly={tailor.isPending}`
  on the note textarea and the `UserInputControls` textarea. `readOnly` keeps focus; `inert` or
  `disabled` would drop it to `<body>`.
- **A stale session** returns early from `scheduleSave`, so the state is not "saving". The stale
  banner already says saving is disabled.
- **An unmount flush that fails** loses the tail with only a toast. The only way to keep it would
  be to block the exit on "saving", which asks about work that is almost always saved in
  milliseconds. Accept, and note it in the conventions.
- **`cannot_confirm` durability** is unchanged: the debounce still absorbs a mis-click undone
  within 800 ms. The unmount flush saves whatever is current on exit, which is correct.

### Docs
`docs/frontend-conventions.md` "Two save models" bullet (:599-606): add a sentence. "A debounced
autosave (the gap page) says Saving… from the first keystroke until the newest edit is on the
server, flushes on unmount, warns on reload while pending, and asks before an in-app exit only
after a failed save."

---

## U3 — Dialogs that drop typed text or paid-for LLM output on Esc, overlay or close

### Summary table
| Dialog | Lost today on Esc/overlay/Cancel | Keep or ask | Where the draft lives after the fix | Cleared when | In-flight / duplicate submit |
|---|---|---|---|---|---|
| U3.1 New base résumé | name, role, instruction, KB selection, **the suggested plan (LLM)**, summary, source, file; a plan still in flight is discarded on arrival | **Keep** | the form, kept mounted (`DialogContent keepMounted`) | a create navigates away; optional "Start over" (owner decision 3) | create: close is already blocked while busy (:110). plan: now lands in the kept form |
| U3.2 Ask for changes | instruction, **the proposal (LLM)** | **Keep, stale-guarded** | `InstructSheet` (already above `SheetContent`) | apply succeeds; Discard (proposal only) | propose: kept instance, one pending flag. Apply disabled when the proposal is stale |
| U3.3 Demonstrate skill | picked bullet, the prose, **the draft rewrite (LLM)** | **Keep** | one instance per opened skill in `NotesTable` | apply succeeds | per instance. The server's `content_hash` rejects a stale apply |
| U3.4 Send to résumé | selection, target, **the adapt proposal (LLM)**, row edits | **Keep** | `SendToResumeDialog`, now always mounted in `EntityDetail` | port or apply succeeds (key bump) | today: close mid-apply then reopen gives a fresh instance with an enabled Apply. Fixed by the persistent mount |
| U3.5 New career item | every field (`reset()` on close) | **Keep** | `NewEntityDialog` (already above `DialogContent`) | create succeeds | already shared (`create` is above the content, :90) |

**No `useDialogDraft` hook** (§0 finding 5): the fixes remove resets and change mount
lifetimes, so there is nothing a hook would de-duplicate.

**Cancel semantics (owner decision 3).** With keep-on-close, a "Cancel" button no longer cancels
anything. Recommendation: every close keeps the draft, the button is relabelled **Close**, and
only New base résumé gets **Start over** (a ghost button, left in the footer, shown when the
draft differs from a fresh one, no confirm because its label names the loss). Small forms need no
reset control; clearing two fields by hand is cheap.

### U3.1 New base résumé (`components/base-resumes/new-base-resume-dialog.tsx`)
**Locations:**
- :107-131 the wrapper, with the `busy` close guard at :110;
- :119-128 `<NewBaseResumeForm key={open ? "open" : "closed"} …>`, which remounts per open;
- :151-173 twelve `useState`s;
- :201-205 the `entities` query with `enabled: mode === "kb"`;
- :228-243 `proposePlan`;
- :375-381 `create`;
- :707-715 the footer.

Callers:
- `app/base-resumes/page.tsx:226-230`, always mounted;
- `components/setup/getting-started-card.tsx:179-190`, mounted only while a suggestion is picked:
  `{composeSuggestion ? <NewBaseResumeDialog key={role} open …/> : null}`, and `null` on close.

**Cause:** Base UI unmounts the popup on close, and all field state and both mutations live in
the popup (`NewBaseResumeForm`). The explicit `key` also remounts on every open. The getting-started
caller unmounts the whole dialog on close.

**Options:**

| Option | Diff | Behaviour |
|---|---|---|
| Lift 12 fields and 2 mutations to the wrapper (the Referrals shape) | Large: props through two layers | Keeps everything |
| **`keepMounted` on the portal (recommended)** | ~6 lines, plus one caller change | Keeps fields, a landed plan and a request in flight. This is Base UI's supported mode (`DialogPortal.d.ts:13-17`) |

**Fix:**
- `components/ui/dialog.tsx` `DialogContent`: add
  `keepMounted = false` to the destructured props, type it
  `/** Keep the popup, its state and its requests mounted while closed. */ keepMounted?: boolean`,
  and render `<DialogPortal keepMounted={keepMounted}>`. Popup and backdrop get `hidden` when
  closed (`DialogPopup.js:91`, `DialogBackdrop.js:44`), and preflight's
  `[hidden]{display:none !important}` beats the popup's `grid` class.
- The wrapper:
  - `<DialogContent size="lg" keepMounted>`;
  - replace `key={open ? "open" : "closed"}` with `key={formGen}`, where
    `const [formGen, setFormGen] = useState(0)`;
  - pass `open` and `onStartOver={() => setFormGen((g) => g + 1)}`.
- The form:
  - `enabled: open && mode === "kb"` on `entities`, or the kept form fetches the KB on every
    `/base-resumes` visit;
  - `const touched = Boolean(name || instruction || selected.size || plan || source || file) ||
    tag !== initialTag`, where `initialTag` is the `useState` initializer's value, kept in a
    `useState`;
  - in the footer, `{touched && <Button variant="ghost" className="mr-auto" disabled={busy}
    onClick={onStartOver}>Start over</Button>}`;
  - Cancel → `Close` (owner decision 3).
- `getting-started-card.tsx`: one kept instance per suggestion the user has opened (the same
  shape as U3.3), so switching suggestions keeps each draft:
```tsx
const [opened, setOpened] = useState<string[]>([]);      // role_category keys, in open order
const [openRole, setOpenRole] = useState<string | null>(null);
const compose = (role: string) => {
  setOpened((keys) => (keys.includes(role) ? keys : [...keys, role]));
  setOpenRole(role);
};
…
{opened.map((role) => (
  <NewBaseResumeDialog key={role} open={openRole === role} initialMode="kb" initialRole={role}
    existingResumes={[]} onOpenChange={(next) => { if (!next) setOpenRole(null); }} />
))}
```
**Edge:** Start over during a pending plan request drops the result on arrival (the old instance
is unmounted). That is intended. A double-click on Create before `isPending` renders fires two
POSTs (the same shape as next-plan item 11's referral double-create). Out of scope here; the
fix for item 11 should cover both.

### U3.2 Ask for changes (`components/resume-editor/instruct-sheet.tsx`)
**Locations:**
- :56-57 state;
- :59-66 `reset`, `handleOpenChange` (reset on close);
- :68-76 `propose`;
- :78-98 `apply`;
- :104 `<Sheet onOpenChange={handleOpenChange}>`;
- :119-125 Textarea `disabled={busy}`;
- :144-157 Propose `disabled={… || busy}`;
- :194-205 the footer.

Caller: `editor-body.tsx:606-613`. The menu item is disabled while the editor has unsaved changes
(:446-452).

**Cause:** state lives above `SheetContent`, but `handleOpenChange(false)` calls `reset()`, which
deletes the instruction and the paid proposal on Esc, overlay or Close.

**Staleness:** ops are index-based with no hash. After a Save changes the résumé, a kept proposal
would PATCH `/edits` into the wrong entries. Stamp each proposal with the `serverKey` of the saved
data it was made against.

**Fix:**
```tsx
export function InstructSheet({ open, onOpenChange, targetSlug, basis, onApplied }: {
  …;
  /** serverKey of the saved résumé data. A proposal made against another copy is stale. */
  basis: string;
}) {
  const [instruction, setInstruction] = useState("");
  const [proposal, setProposal] = useState<{ result: BaseResumeProposal; basis: string } | null>(null);
  // Kept across close: the proposal cost a model call. It edits by index, so once the
  // résumé moves on it can only be read, never applied.
  const stale = proposal !== null && proposal.basis !== basis;
  const propose = useMutation({
    mutationFn: (sent: { instruction: string; basis: string }) =>
      apiFetch<BaseResumeProposal>(`/api/base-resumes/${targetSlug}/propose`, {
        method: "POST", body: JSON.stringify({ instruction: sent.instruction }),
      }).then((result) => ({ result, basis: sent.basis })),
    onSuccess: setProposal,
    onError: (err: Error) => toast.error(err.message),
  });
  // apply.onSuccess: …existing…, then setInstruction(""); setProposal(null); onOpenChange(false);
  // <Sheet open={open} onOpenChange={onOpenChange}>   (handleOpenChange and reset are deleted)
```
- The Propose click becomes `propose.mutate({ instruction, basis })`. The rest of the file reads
  `proposal.result.*` where it read `proposal.*`.
- When `stale`:
  - render `<p className="text-muted-foreground text-xs">The resume changed since this was
    proposed. Propose again to get edits for this version.</p>` inside the proposal card;
  - Apply `disabled={busy || stale}`.
- `editor-body.tsx:606`: `basis={serverKey(live.data)}` (add `serverKey` to the existing
  `@/lib/studio` import at :65).
- **Focus, while touching this file:**
  - the Textarea goes from `disabled={busy}` to `readOnly={busy}`;
  - Propose and Apply get `focusableWhenDisabled` with `data-disabled:` dimming.

  A click on Propose currently disables the focused button, and focus drops to `<body>`.

**Edge:** a proposal that arrives after the sheet closed is kept (the sheet stays mounted in the
studio), so reopening shows it. That is the intended "keep". Leaving the studio (U1) drops it with
everything else, which is acceptable because the proposal is not unsaved *work*.

### U3.3 Demonstrate skill (`components/resume-health/demonstrate-skill-dialog.tsx`)
**Locations:**
- the dialog: :83-95 state and `reset`; :138-145 `onOpenChange` resets on close; :233-243 Cancel
  resets; :128-133 apply success;
- the caller, `components/resume-health/finding-cards.tsx`: :886 `const [skill, setSkill]`;
  :961 open; :1073-1088 `{skill && data && (<DemonstrateSkillDialog open={Boolean(skill)} …/>)}`,
  which unmounts on close.

**Fix:**
- In the dialog, delete `reset()` from `onOpenChange` and from Cancel (relabelled "Close").
  `onOpenChange={onOpenChange}`. `reset()` stays only in `applyMut.onSuccess`.
- In `NotesTable`, one kept instance per skill the user has opened:
```tsx
const [opened, setOpened] = useState<string[]>([]);
const openSkill = (subject: string) => {
  setOpened((s) => (s.includes(subject) ? s : [...s, subject]));
  setSkill(subject);
};
// :961  onClick={() => !done && openSkill(subject)}
{data && opened.map((s) => (
  <DemonstrateSkillDialog key={s} open={skill === s} onOpenChange={(o) => { if (!o) setSkill(null); }}
    skill={s} data={data} kind={kind} resumeKey={resumeKey} locked={locked}
    onApplied={() => { setDoneSkills((d) => new Set(d).add(s)); onApplied(); }}
    onReanalyze={onReanalyze} />
))}
```
**Edge:** after another fix re-analyses the report, `data` changes under a kept draft. The shown
`picked.text` is old, but the apply carries `expected_content_hash`, and the server answers with
the stale hint (`toastRewriteError` offers Re-analyze). No client guard is needed.

### U3.4 Send to résumé (`components/career/send-to-resume-dialog.tsx`, `entity-detail.tsx`)
**Locations:**
- the dialog: :76-78 `selected` initialised from `approved` at mount; :102-126 `finishPort`,
  which closes at :125; :254 `<Dialog onOpenChange={onOpenChange}>` (no pending guard);
  :475 Cancel;
- `entity-detail.tsx`: :85 `sendOpen`; :195-201 `{sendOpen ? <SendToResumeDialog …/> : null}`.

**Cause:** the conditional mount unmounts everything on close. That was also why `selected` could
be a mount-time initialiser: every open re-derived it from the current approved points.

**Fix:**
- `entity-detail.tsx`: always render the dialog, and clear it on success with a key:
```tsx
const [sendGen, setSendGen] = useState(0);
…
<SendToResumeDialog key={sendGen} open={sendOpen} onOpenChange={setSendOpen}
  onSent={() => setSendGen((g) => g + 1)} entity={entity.data} />
```
- In the dialog, `finishPort` ends with `onOpenChange(false); onSent();`. Derive the untouched
  selection, so points approved after mount are included and deleted ones drop out:
```tsx
// null = untouched: every approved point, as of now.
const [picked, setPicked] = useState<Set<string> | null>(null);
const approvedIds = useMemo(() => new Set(approved.map((p) => p.id)), [approved]);
const selected = useMemo(
  () => (picked === null ? approvedIds : new Set([...picked].filter((id) => approvedIds.has(id)))),
  [picked, approvedIds],
);
const toggle = (pointId: string) =>
  setPicked((current) => {
    const next = new Set(current ?? approvedIds);
    if (next.has(pointId)) next.delete(pointId);
    else next.add(pointId);
    return next;
  });
```
- Cancel at :475 → "Close" (owner decision 3). `resumes` keeps `enabled: open`.

**Edge:**
- The key bump unmounts the popup mid close-animation (100 ms fade), so it vanishes instantly
  after a successful port. That is acceptable.
- The toast's "View resume" action closes over `router` and `targetSlug` from the old instance.
  Both stay valid.
- The inline row editor's Esc (:340-346) already stops propagation, so the dialog stays open.
  Its discard-on-Esc is U4.2's pattern and is out of scope here.

### U3.5 New career item (`components/career/new-entity-dialog.tsx`, SYSTEM.md §11 item 32)
**Locations:**
- the dialog: :66-75 state; :77-87 `reset`; :125-131 create success (`reset()` at :127);
  :145-151 `onOpenChange` resets on close unless pending; :377-386 Cancel resets;
- `app/career/page.tsx:149-154`: `<NewEntityDialog key={newEntity.kind} …>` remounts when opened
  from another tab.

**Fix:**
- `onOpenChange={onOpenChange}`, so nothing resets on close.
- Cancel → `onClick={() => onOpenChange(false)}`, relabelled "Close".
- `reset()` stays only in create's `onSuccess`.
- `app/career/page.tsx`: drop `key={newEntity.kind}`.
- A new default kind applies only to an untouched draft:
```tsx
const pristine =
  !title.trim() && !org.trim() && !startDate.trim() && !endDate.trim() &&
  sectionTitle === (defaultSectionTitle ?? "") && sectionKey === (defaultSectionKey ?? "");
// Opened from another tab: an untouched form takes that tab's kind; typed text keeps
// the kind it was typed for.
const [shownDefault, setShownDefault] = useState(defaultKind);
if (defaultKind !== shownDefault) {
  setShownDefault(defaultKind);
  if (pristine) setKind(defaultKind);
}
```
This is React's adjust-state-while-rendering pattern, and it passes the compiler rules.

### Tests / pins (U3)
New `backend/tests/test_frontend_dialog_drafts.py`, one test per dialog. Name the gesture in each
docstring, as `test_frontend_referrals.py` does.
- `test_dialog_content_can_stay_mounted`: `components/ui/dialog.tsx` has
  `<DialogPortal keepMounted={keepMounted}>`.
- `test_new_base_resume_keeps_its_form`:
  - `key={open ? "open" : "closed"}` is absent;
  - `<DialogContent size="lg" keepMounted>` is present;
  - `enabled: open && mode === "kb"`;
  - `Start over` appears only inside a `touched &&` branch;
  - `getting-started-card.tsx` maps `opened` to instances with `open={openRole === role}`, and no
    longer has `composeSuggestion ? (`.
- `test_instruct_sheet_keeps_a_proposal_until_applied`:
  - `handleOpenChange` and `reset()` are absent;
  - `setProposal(null)` appears inside `apply`'s `onSuccess` and at the Discard button only;
  - `const stale = proposal !== null && proposal.basis !== basis`;
  - Apply's `disabled` includes `stale`;
  - `editor-body.tsx` passes `basis={serverKey(live.data)}`;
  - the Textarea uses `readOnly={busy}`, not `disabled={busy}`.
- `test_demonstrate_skill_keeps_its_draft`: the dialog's `onOpenChange` has no `reset()`, and
  `reset()` appears once outside its definition, in `applyMut`'s `onSuccess`. `finding-cards.tsx`
  maps `opened` with `open={skill === s}`, and `{skill && data && (` is absent.
- `test_send_to_resume_stays_mounted`: `entity-detail.tsx` has no `sendOpen ? (` and has
  `key={sendGen}`. The dialog has `picked === null ? approvedIds` and calls `onSent()` in
  `finishPort`.
- `test_new_entity_keeps_its_draft` (the §11 item 32 regression pin):
  - the Dialog's `onOpenChange={onOpenChange}`;
  - `reset();` appears exactly once (in `onSuccess`);
  - `key={newEntity.kind}` is absent from `app/career/page.tsx`;
  - `if (pristine) setKind(defaultKind)` is present.
- Existing pins to re-run:
  - `test_frontend_color_roles.py:239` (new-entity preset cards);
  - `test_frontend_placeholders.py:593` (new-entity placeholders);
  - `test_frontend_referrals.py` (untouched, but it documents the convention).

### Browser checks (U3)
1. New base résumé:
   - type a name, pick a role, press **Suggest a selection**, and press Esc while it is
     "Suggesting". Reopen: the name and role are there, and the plan arrives into the kept form;
   - overlay-click and reopen: unchanged;
   - Start over clears it;
   - a create navigates to the studio;
   - on `/base-resumes`, the network tab shows **no** `/api/kb/entities` request before the
     dialog is opened.
2. Getting started (empty tracker):
   - open suggestion A and type a name, close, open suggestion B and type, close;
   - reopen A: A's text is there.
3. Ask for changes:
   - propose, close with Esc, reopen: the instruction and proposal are there;
   - close, edit and Save the résumé, reopen: the "resume changed" note shows and Apply is
     disabled;
   - Propose again works.
4. Demonstrate skill: draft a rewrite, Esc, open another skill, return. The first draft is still
   there, and Apply works.
5. Send to résumé:
   - Adapt, edit a row, close, reopen: the review step and the edit are kept;
   - close during Apply and reopen at once: Apply shows pending (no second Apply);
   - after success, reopening starts fresh;
   - approve a new point on the page before opening: it is pre-selected.
6. New career item:
   - type a title on the Projects tab, Esc, open from the Education tab: the title is kept and
     the kind is still Project;
   - with an empty form, opening from Education gives Education;
   - a create clears it.
7. Keyboard: each reopened dialog lands initial focus as before, and closing returns focus to its
   trigger.
8. 375px: the New base résumé tab row (§11 item 31) is unchanged by this.

### Docs (U3)
- `docs/frontend-conventions.md` (:413-423), rewrite "A dialog holding a create form keeps its
  draft…" as **"A dialog keeps what the user typed, or paid for, across close."** It must say:
  - field state and the one request live above `DialogContent` (Referrals, NewEntity, Instruct,
    Send to résumé, Demonstrate);
  - or the popup stays mounted (`DialogContent keepMounted`, New base résumé);
  - a caller mounts such a dialog for the page's lifetime, never `{open ? <Dialog/> : null}`
    (one instance per subject where there are several);
  - only success clears it (plus Start over where offered);
  - a kept LLM proposal that edits by index carries the basis it was made against, and cannot be
    applied once that basis moves.

  Delete the sentence "`NewEntityDialog` still resets on close (SYSTEM.md §11 item 32)".
- SYSTEM.md §11 item 32 (:843-848): **delete the clause** "`NewEntityDialog` calls `reset()` on
  close, so Esc or an overlay click loses typed text (Referrals keeps its draft);". The rest of the
  item stays.

---

## U4 — Smaller unsaved-work gaps

### U4.1 Q&A cover-letter editor closes before the save lands (`components/qa-tab.tsx`)
**Locations:**
- :124-135 `editEntry` (`onSuccess`: toast and invalidate);
- :220-221 per-entry `isSaving`;
- :248 `onSave={(answer) => editEntry.mutate({ id: entry.id, answer })}`;
- :279 `onSave: (answer: string) => void`;
- :281-282 `editing`/`draft`;
- :302-311 the Edit button (`setDraft(entry.answer)` on open);
- :368-376 Save;
- :378-390 Cancel.

**Current code:**
```tsx
<Button size="sm" onClick={() => { onSave(draft); setEditing(false); }} disabled={isSaving}>
```
**Cause:**
- The editor closes on click. On failure it shows the OLD answer, and the typed text survives only
  in `draft` state, which the next Edit click overwrites (`setDraft(entry.answer ?? "")`, :306).
  So the text is effectively lost.
- On success, the old answer flashes until the invalidated refetch lands.
- Save disables itself on click, so focus drops to `<body>`, then the whole editor unmounts.

**Fix:**
```tsx
// QATab
const editEntry = useMutation({
  mutationFn: …unchanged,
  onSuccess: (updated) => {
    // Show the saved text at once; the editor closes on this, not before it.
    qc.setQueryData<QAEntry[]>(["qa", applicationId], (prev) =>
      prev?.map((e) => (e.id === updated.id ? updated : e)));
    toast.success("Saved");
    invalidate();
  },
  onError: …unchanged,   // toasts; the card stays in edit mode with the text
});
…
onSave={(answer) => editEntry.mutateAsync({ id: entry.id, answer })}

// QAEntryCard
onSave: (answer: string) => Promise<unknown>;
const editRef = useRef<HTMLButtonElement>(null);
const focusEditAfterClose = useRef(false);
useEffect(() => {   // referrals' focusAddAfterCreate pattern
  if (editing || !focusEditAfterClose.current) return;
  focusEditAfterClose.current = false;
  editRef.current?.focus();
}, [editing]);
const closeEditor = () => { focusEditAfterClose.current = true; setEditing(false); };
…
<IconButton ref={editRef} label="Edit" … />
<Button size="sm" focusableWhenDisabled className="data-disabled:opacity-50" disabled={isSaving}
  onClick={async () => {
    try { await onSave(draft); } catch { return; }   // failed: stay open, text intact
    closeEditor();
  }}>
  {isSaving ? "Saving…" : "Save"}
</Button>
// Cancel: onClick={() => { setDraft(entry.answer ?? ""); closeEditor(); }}
```
- "Saving..." (three dots) becomes "Saving…" (the ellipsis character, as everywhere else).
- Register the open editor only if owner decision 2 includes it:
  `useLeaveGuard(editing && draft !== (entry.answer ?? ""))`.

**Pins** (`backend/tests/test_frontend_qa_tab.py`, new):
- `onSave(draft);\n` followed by `setEditing(false)` is absent;
- `await onSave(draft)` precedes `closeEditor()` inside a `try` whose `catch` returns;
- the parent passes `editEntry.mutateAsync`;
- `qc.setQueryData<QAEntry[]>(["qa", applicationId]` is in `editEntry`'s `onSuccess`;
- Save has `focusableWhenDisabled`.

**Browser:**
- Stop the backend, edit a cover letter, Save: an error toast, the editor stays open, the text
  intact, and focus on Save.
- Restart, Save: the editor closes on the new text with no flash of the old one, and focus lands
  on Edit.

**Edge (found in passing, not fixed here):** Regenerate (:333-342) is enabled while you edit, and
also over a hand-edited, saved cover letter. It replaces the user's edited text with a new
generation and does not ask. That is owner decision 6.

### U4.2 Notes editor: Esc silently discards a multi-row edit (`components/career/notes-editor.tsx`)
**Locations:**
- :87-92 `cancel`;
- :150-155 Esc → `cancel()`;
- :156 the Textarea `disabled={save.isPending}`;
- :160-165 Cancel and Save (both `disabled` while saving);
- :41-51 save `onSuccess` sets `editing` false;
- :120-133 the Edit button.

The same Esc-cancel exists in `components/career/points-list.tsx:214-219` (`cancelEdit`, :160) and
`components/career/inbox-panel.tsx:336-341` (`cancelEdit`, :300).

**Cause:** Esc is a reflex key. `cancel()` throws the typed text away with no question. After
Cancel or a successful Save the textarea and buttons unmount, and focus drops to `<body>`.

**Fix:** one helper beside `useConfirm` in `components/confirm-dialog.tsx`:
```tsx
/** Ask before throwing typed text away; true at once when nothing changed. */
export function useConfirmDiscard() {
  const confirm = useConfirm();
  return useCallback(
    (changed: boolean) =>
      changed
        ? confirm({
            title: "Discard your changes?",
            description: "What you typed here will be lost.",
            confirmLabel: "Discard",
            cancelLabel: "Keep editing",
            destructive: true,
          })
        : Promise.resolve(true),
    [confirm],
  );
}
```
In `NotesEditor`:
```tsx
const confirmDiscard = useConfirmDiscard();
const editRef = useRef<HTMLButtonElement>(null);
const focusEditAfterClose = useRef(false);
useEffect(() => {
  if (editing || !focusEditAfterClose.current) return;
  focusEditAfterClose.current = false;
  editRef.current?.focus();
}, [editing]);
const requestCancel = async () => {
  if (!(await confirmDiscard(value !== notes))) return;   // Keep editing: focus returns to the textarea
  focusEditAfterClose.current = true;
  cancel();
};
// Esc: event.preventDefault(); void requestCancel();
// Cancel button: onClick={() => void requestCancel()}   (owner decision 4: Esc only, or Esc + Cancel)
// Save: onClick={() => { focusEditAfterClose.current = true; save.mutate(value); }} with focusableWhenDisabled
// Textarea: readOnly={save.isPending} instead of disabled
// Edit button: ref={editRef}
```
- If `save` fails, `editing` stays true, and the effect does nothing while `editing` is true. The
  flag stays raised until the next close, which is harmless.
- Apply the same `requestCancel` shape to `points-list.tsx` and `inbox-panel.tsx` if owner decision
  4 includes them (recommended: three textareas, one helper, no clone).

**Pins** (add to a new `backend/tests/test_frontend_kb_editors.py`):
- `useConfirmDiscard` is defined once, in `confirm-dialog.tsx`, with `destructive: true` and
  `cancelLabel: "Keep editing"`;
- in `notes-editor.tsx` the Escape branch calls `requestCancel()`, not `cancel()`;
- `confirmDiscard(value !== notes)` precedes `cancel()` in `requestCancel`;
- the Textarea uses `readOnly={save.isPending}`;
- the same for the other two files if included.

**Browser:**
- Type two lines and press Esc: "Discard your changes?" with focus on **Keep editing**. Keep
  editing returns to the textarea with the text. Esc then Discard closes, with focus on
  Edit/Add notes.
- Esc with no change closes at once.
- Save from the keyboard: focus lands on Edit.

### U4.3 Settings still say "Saves automatically" after a failed autosave
**Locations:**
- `lib/use-autosave.ts:29-62`: no failure state; `.catch(() => {})` swallows it.
- `components/settings/autosave-status.tsx:18-45`: `pending ? Saving… : ✓ Saves automatically`.

Callers:
- `useAutosave`: `quick-tailor-section.tsx:81-89`, `job-preferences-section.tsx:110-134`. The card
  shows the local value, so after a failure it shows values the server does not have.
- A raw mutation: `market-section.tsx:70-72` (`save.isPending`) and `mcp-workflow-section.tsx:62-64`.
  These controls show the server value, so a failure silently reverts the control while the status
  shows a check.

**Fix (`lib/use-autosave.ts`):**
```ts
const [failed, setFailed] = useState(false);
…
const flush = () => {
  const next = queued.current;
  inFlight.current = next;
  setPending(true);
  // A rejection is reported by the caller's own onError; here it only decides `failed`.
  commit(next).then(() => settle(true), () => settle(false));
};
// `failed`: the newest value is not on the server. Each commit sends the WHOLE value,
// so a later success carries every earlier change and clears it; an outcome with a
// newer value queued behind it decides nothing.
const settle = (ok: boolean) => {
  if (queued.current !== inFlight.current) { flush(); return; }
  inFlight.current = null;
  setPending(false);
  setFailed(!ok);
};
/** Send the newest value again: the failed state's Try again. */
const retry = () => { if (inFlight.current === null) flush(); };
return { value, update, pending, failed, retry };
```
Rewrite the doc comment's "A rejected commit still drains the queue…" paragraph to describe
`failed` and `retry`.

**`AutosaveStatus`**: add `"use client"` and the props `failed = false` and
`onRetry?: () => void`.
```tsx
<span className={`inline-flex items-center gap-2 text-xs ${className ?? ""}`}>
  <span ref={statusRef} tabIndex={-1} aria-live="polite"
    className={`inline-flex items-center gap-1.5 ${failed && !pending ? "text-destructive" : "text-muted-foreground"}`}>
    {pending ? (<><Loader2 className="size-3 animate-spin" aria-hidden="true" />Saving…</>)
      : failed ? (<><TriangleAlert className="size-3" aria-hidden="true" />Not saved</>)
      : (<><Check className="size-3" aria-hidden="true" />Saves automatically</>)}
  </span>
  {failed && onRetry ? (
    <Button type="button" variant="link" size="xs" focusableWhenDisabled disabled={pending}
      className="h-auto p-0 data-disabled:opacity-50"
      onClick={() => { refocus.current = true; onRetry(); }}>Try again</Button>
  ) : null}
</span>
```
- Add the effect `[failed]`: when `failed` turns false and `refocus.current` is set, focus
  `statusRef`. Try again stays mounted during the retry (`failed` holds until a success settles),
  so focus only moves once it unmounts.
- `text-destructive` on the card is pinned at 4.5:1 (conventions, colour roles).

**Callers:**
- quick-tailor and job-preferences:
  `const { value, update, pending, failed, retry } = useAutosave(…)`, then
  `<AutosaveStatus pending={pending} failed={failed} onRetry={retry} />`, then
  `useLeaveGuard(failed)`. The card holds edits the server lacks, so leaving asks.
- market and mcp-workflow: `<AutosaveStatus pending={save.isPending} failed={save.isError} />`.
  There is no retry, because the control already shows the saved value and re-picking is the
  retry. There is no leave guard either: nothing unsaved is on screen.

**Found in passing:** `mcp-workflow-section.tsx:73` `disabled={save.isPending}` on the Switch.
Toggling from the keyboard disables the focused switch, and focus drops to `<body>`. Base UI's
Switch has no `focusableWhenDisabled`. Fix it in this task: remove `disabled` and ignore toggles
while pending with `onCheckedChange={(c) => { if (!save.isPending) save.mutate(c); }}`. The switch
is controlled by the server value, so an ignored toggle does not move. Pin
`disabled={save.isPending}` absent from that file.

**Pins** (`backend/tests/test_frontend_settings_autosave.py`, new):
- `use-autosave.ts` returns `failed` and `retry`;
- `settle` calls `setFailed(!ok)` only after the `queued.current !== inFlight.current` early
  return;
- `.catch(() =>` is gone;
- `AutosaveStatus` renders "Not saved" and gates "Saves automatically" behind `!failed`;
- each of the four cards passes `failed=`, and the two `useAutosave` cards also pass
  `onRetry={retry}` and call `useLeaveGuard(failed)`.

Node test (optional, not CI): extract nothing. The hook needs React, so the pin is the guard.

**Browser:**
- Stop the backend and flip a quick-tailor switch: an error toast, "Not saved" in red, and Try
  again.
- A sidebar link asks. Restart and press Try again from the keyboard: "Saving…", then "Saves
  automatically", with focus on the status.
- Market: pick another market while the backend is down. The Select reverts and the status
  reads "Not saved" with no Try again. The next successful pick clears it.

### Docs (U4)
- Conventions "Two save models" (:599-606): "`AutosaveStatus` reports three states: Saving…, Not
  saved (after a failed write, with Try again where the card holds a value the server lacks), and
  Saves automatically. A card whose write failed registers the leave guard."
- Conventions Career KB bullet (:640-642): "local Save/Cancel editors with Escape" gets "Escape
  (and Cancel, per owner decision 4) over changed text asks through `useConfirmDiscard`; closing
  an editor returns focus to its Edit button."

---

## Owner decisions (user-facing; recommendation first)

1. **Browser Back/Forward in an editor with unsaved work.** **Recommend A (sentinel + ask)**, as its
   own task after U1's core.
   - B is stash-and-restore with a "Restore your unsaved edits?" banner.
   - C is to accept the gap and file it in §11.
   - A's visible costs: an edit drops the forward history, and a reload while parked leaves one
     dead Back press.
2. **Which surfaces register beyond the three editors, the gap page and failed settings.**
   **Recommend including** the dirty-Save cards (Persona, Autofill, Prompts), `/new`'s pasted JD,
   and the Q&A cover-letter editor. Each is one line now that every link is guarded. **The chat
   composer:** recommend *ask* (one line). Keeping a draft per session is the friendlier choice,
   but it is a new feature.
3. **What "Cancel" means once dialogs keep their drafts.** **Recommend** every close keeps the
   draft, the button reads **Close**, and only New base résumé gets **Start over** (no confirm).
   The alternative is keeping "Cancel" as a discard that asks when the form is touched, which
   means a confirm on a common button.
4. **Career KB editors: which gestures ask.** **Recommend** both Esc and Cancel ask when the text
   changed (matching raw JSON's confirmed Cancel), and apply it to all three textareas (notes,
   point, inbox draft), not just notes. The minimal version is Esc only, notes only.
5. **Leave prompt wording and buttons.** **Recommend** "Leave without saving?" / "Changes you
   haven't saved on this page will be lost." / **Leave** (destructive) / **Stay** (initial focus).
   Do not add "Save and leave": a studio Save chains a render and a re-score, and a third button
   needs a new confirm primitive.
6. **(Found in passing) Regenerate over an edited cover letter** replaces the user's edited text
   without asking. **Recommend** a confirm when the saved answer differs from the last generated
   one, in a later plan (it needs a "was edited" signal the entry does not carry today).

## Suggested task split
1. **U1 core** (M). The task:
   - `lib/leave-guard.ts` plus node tests;
   - `hooks/use-leave-guard.ts`, deleting the old hook;
   - `components/guarded-link.tsx`;
   - `LeaveGuardListeners` in `app/providers.tsx`;
   - the 31-file `next/link` import swap;
   - register the base studio, the tailored studio (`unsaved`) and the template editor;
   - `test_frontend_leave_guard.py`;
   - the conventions bullet and the *Tailored studio* sentence.

   Browser checks U1-1…6. Goes **first**: U2 and U4.3 call `useLeaveGuard`.
2. **U1 Back/Forward** (M, only if owner decision 1 = A). The listener, the `router.replace` from
   the sentinel, the pins, and browser checks U1-7/8. Depends on 1. Can be dropped with no effect
   on the others.
3. **U2 gap page** (S–M). `scheduleSave`, `editGen`, the unmount flush, `SaveIndicator` with
   retry, the two `useLeaveGuard` calls, `readOnly` while tailoring, pins, and the conventions
   sentence. Depends on 1 for the registration only; the rest can start in parallel and add the
   two lines after 1 merges.
4. **U3 dialogs** (M). **Independent of 1**, so it can run in parallel from the start. Splits
   cleanly in two:
   - 4a: the `keepMounted` primitive, New base résumé plus getting-started, and New career item
     (§11 item 32);
   - 4b: Ask for changes (basis stamp), Demonstrate skill, Send to résumé.

   Its pins, the conventions rewrite, and the §11 item 32 clause.
5. **U4 small gaps** (S–M). Three independent parts:
   - U4.1 Q&A (no dependency);
   - U4.2 `useConfirmDiscard` and the KB editors (no dependency);
   - U4.3 autosave failure and the MCP switch (depends on 1 for `useLeaveGuard(failed)`).

   Plus pins and the conventions sentences.
6. **Gate + docs sweep** (S):
   - `pytest tests/ mcp_server/tests/ -q`;
   - `ruff check .`;
   - `node --test lib/*.test.ts`;
   - `npx tsc --noEmit`, `npm run lint`, `npm run build`;
   - the frontend slop check, named, at ≤ 505/42;
   - `check_system_md.py` (≤ 999 lines);
   - a browser pass of every check above, light and dark, at 1280 and 375 (and 768 for the
     sidebar).

   Then the goal critique against the Goal Card.

Parallel lanes: {1 → 2}, {1 → 3}, {1 → 5 (U4.3)}, and {4, 5 (U4.1, U4.2)} from the start. Every
lane that edits `docs/frontend-conventions.md` should queue its text for task 6, the same way the
previous plan queued SYSTEM.md edits. The bullets touched overlap: "Two save models" is edited by
U2 and U4.
