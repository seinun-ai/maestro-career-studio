/**
 * Who holds unsaved work, so every exit can ask first (docs/frontend-conventions.md,
 * "Leaving with unsaved work"). Module state, not React state: the readers are event
 * handlers (a link's onNavigate, page unload, popstate) that need the value at the
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

// ---------------------------------------------------------------------------
// Back and Forward (owner decision 1). Everything below is pure: the listeners
// (components/leave-guard-listeners.tsx) feed it history events and carry out
// the commands it returns, so node tests can drive every path.
//
// While an editor has in-app unsaved work, a duplicate of its history entry
// (the sentinel) sits above the real one. Back from the sentinel lands on the
// real entry, same URL and page still mounted, and that is the press we ask
// about. Every entry the app router writes carries a number (stamped by the
// listeners): the previous entry's number + 1. A popstate compares numbers, so
// it knows how far and in which direction it moved. The numbers are relative on
// purpose: Chrome keeps at most 50 entries and drops the oldest on a push
// without renumbering anything, so differences stay exact at the cap. Extra presses while the question is open are undone
// exactly, and a sentinel that is no longer needed is stepped over instead of
// being a dead press.
// ---------------------------------------------------------------------------

const POSITION = "__leaveGuardAt";
const SENTINEL = "__leaveGuard";

/**
 * How Next's own popstate listener treats the entry
 * (`next/dist/client/components/app-router.js`, `onPopState`).
 */
export type EntryKind =
  /** Written by the app router (`__NA`): Next renders it. */
  | "next"
  /** No state: a fragment (`#hash`) navigation such as the skip link. Next ignores it. */
  | "none"
  /** A state without `__NA`: Next reloads the page. */
  | "foreign";

export interface HistoryEntry {
  /** The entry's number (see above), or null when unstamped and not placeable. */
  at: number | null;
  kind: EntryKind;
  /** Our duplicate, parked above an editor's own entry. */
  sentinel: boolean;
  /** Path and query, no hash. Two entries with the same url show the same page. */
  url: string;
}

export function readEntry(state: unknown, url: string): HistoryEntry {
  if (!state || typeof state !== "object") return { at: null, kind: "none", sentinel: false, url };
  const fields = state as Record<string, unknown>;
  const at = fields[POSITION];
  return {
    at: typeof at === "number" ? at : null,
    kind: fields.__NA === true ? "next" : "foreign",
    sentinel: fields[SENTINEL] === true,
    url,
  };
}

export function isSentinelState(state: unknown): boolean {
  return readEntry(state, "").sentinel;
}

/** Next's state with the sentinel flag set or cleared. `__NA` and the tree stay as they are. */
export function markSentinel(state: object, sentinel: boolean): Record<string, unknown> {
  const marked: Record<string, unknown> = { ...(state as Record<string, unknown>) };
  if (sentinel) marked[SENTINEL] = true;
  else delete marked[SENTINEL];
  return marked;
}

/**
 * The position stamp. It spreads Next's state, so `__NA` and
 * `__PRIVATE_NEXTJS_INTERNALS_TREE` stay untouched: Next's patched pushState and
 * replaceState pass a state that carries `__NA` straight through, and a traverse
 * renders from that tree.
 */
export function stampState(state: object, at: number, sentinel: boolean): Record<string, unknown> {
  return { ...markSentinel(state, sentinel), [POSITION]: at };
}

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

/**
 * The stamp for an entry a pushState/replaceState just wrote. A push is the entry
 * it left + 1 (not `history.length - 1`: at Chrome's 50-entry cap the length stops
 * growing and every push would get the same number). A replace keeps the number,
 * and keeps the sentinel flag while the page stays the same (a `router.refresh`, or a
 * settings tab's `?tab=` write, rewrites the state without our fields).
 */
export function stampAfterWrite(
  how: "push" | "replace",
  before: HistoryEntry,
  written: HistoryEntry,
  length: number,
  believedAt: number | null,
): { at: number | null; sentinel: boolean } {
  if (how === "push") return { at: (before.at ?? believedAt ?? length - 2) + 1, sentinel: written.sentinel };
  return {
    at: written.at ?? before.at ?? believedAt,
    sentinel: written.sentinel || (before.sentinel && samePage(before.url, written.url)),
  };
}

export type GuardPhase =
  | { kind: "idle" }
  /** The question is open. Stay returns to `home`; Leave goes to `leaveTo`. */
  | { kind: "asking"; home: number | null; leaveTo: number | null }
  /** Our own `history.go` is in flight to `target`. */
  | { kind: "moving"; target: number; then: "stay" | "leave" | "skip" };

export interface GuardState {
  /** The entry the browser is on. */
  here: HistoryEntry;
  /** The url of the page on screen (the one Next rendered). */
  page: string;
  /** The last app-router entry that shows `page`: where Stay returns. */
  home: number | null;
  /** `history.length` at the last event: a stateless pop that grew it is a new fragment entry. */
  length: number;
  /** Entries seen at each position (pruned when a push drops the ones in front). */
  seen: Record<number, HistoryEntry>;
  /** Unsaved in-app work: `leaveBlocked("in-app")`. */
  blocked: boolean;
  phase: GuardPhase;
}

export type GuardEvent =
  | { type: "wrote"; how: "push" | "replace"; entry: HistoryEntry; length: number }
  | { type: "pop"; entry: HistoryEntry; length: number }
  | { type: "blocked"; blocked: boolean }
  | { type: "answer"; leave: boolean }
  /** A Leave's `history.go` brought neither a popstate nor an unload: nowhere to go. */
  | { type: "stalled" }
  /** The page came back from the back/forward cache. */
  | { type: "restored"; entry: HistoryEntry; length: number };

export type GuardCommand =
  /** `stopImmediatePropagation()`: Next must not render this popstate. */
  | { type: "stop" }
  | { type: "ask" }
  /** `history.go(delta)` once the popstate is over. `leaving`: expect a pop or an unload. */
  | { type: "go"; delta: number; leaving: boolean }
  | { type: "pushSentinel" }
  /** Push the page's own entry again (Stay from an entry we cannot place). */
  | { type: "restorePage" }
  /** Dispatch this entry's popstate again so Next renders it (it was held for the question). */
  | { type: "replay" }
  /** `router.replace` to the current URL: Next ignores a stateless entry, so render it ourselves. */
  | { type: "renderHere" }
  /** Leave with no earlier page in this tab: go to the app's home through the router. */
  | { type: "navigateAway" }
  | { type: "setBypass"; on: boolean };

type Step = [GuardState, GuardCommand[]];

const IDLE: GuardPhase = { kind: "idle" };
const STOP: GuardCommand = { type: "stop" };
const PUSH_SENTINEL: GuardCommand = { type: "pushSentinel" };
const NAVIGATE_AWAY: GuardCommand = { type: "navigateAway" };
const RENDER_HERE: GuardCommand = { type: "renderHere" };

export function startGuard(entry: HistoryEntry, length: number, blocked: boolean): GuardState {
  // Unstamped at load: a fresh navigation (a new tab, a typed URL) is the last
  // entry. So number 0 is a tab's first entry, and "below 0" means nothing earlier
  // (the cap only ever removes entries, it never adds earlier ones).
  const here = { ...entry, at: entry.at ?? length - 1 };
  return {
    here,
    page: entry.url,
    home: entry.kind === "next" ? here.at : null,
    length,
    seen: remember({}, here),
    blocked,
    phase: IDLE,
  };
}

export function stepGuard(s: GuardState, e: GuardEvent): Step {
  switch (e.type) {
    case "wrote":
      return wrote(s, e.how, e.entry, e.length);
    case "pop":
      return popped(s, e.entry, e.length);
    case "blocked":
      return blockedChanged({ ...s, blocked: e.blocked });
    case "answer":
      return s.phase.kind === "asking" ? answered(s, s.phase, e.leave) : [s, []];
    case "stalled":
      return s.phase.kind === "moving" && s.phase.then === "leave"
        ? [{ ...s, phase: IDLE }, [NAVIGATE_AWAY]]
        : [s, []];
    case "restored": {
      const here = { ...e.entry, at: e.entry.at ?? s.here.at };
      const home = here.kind === "next" ? here.at : null;
      return [{ ...s, here, page: here.url, home, length: e.length, phase: IDLE }, []];
    }
  }
}

function remember(seen: Record<number, HistoryEntry>, entry: HistoryEntry) {
  return entry.at === null ? seen : { ...seen, [entry.at]: entry };
}

/** A push drops every entry from `at` up. */
function forget(seen: Record<number, HistoryEntry>, at: number) {
  const kept: Record<number, HistoryEntry> = {};
  for (const [key, entry] of Object.entries(seen)) if (Number(key) < at) kept[Number(key)] = entry;
  return kept;
}

function wrote(s: GuardState, how: "push" | "replace", entry: HistoryEntry, length: number): Step {
  if (how === "replace" && entry.at !== null && s.here.at !== null && entry.at !== s.here.at) {
    // A replace on another entry than ours: the browser has already moved and its
    // popstate is still to come (Next committed a render in between). Leave the
    // move to that popstate, or it would lose where it came from.
    return [{ ...s, length, seen: remember(s.seen, entry) }, []];
  }
  const seen = how === "push" && entry.at !== null ? forget(s.seen, entry.at) : s.seen;
  const home = entry.kind === "next" ? entry.at : s.home;
  const phase = how === "push" ? IDLE : s.phase;
  return [{ ...s, here: entry, page: entry.url, home, length, seen: remember(seen, entry), phase }, []];
}

/**
 * Where a stateless (fragment) entry sits: one step from where we were. A pop that
 * grew `history.length` is a new fragment navigation, one above. At the 50-entry
 * cap the length no longer grows, so otherwise it is the neighbour we have not
 * seen as an app-router entry (a skip link on the sentinel: the entry below is
 * the editor's own, so the fragment is above).
 */
function placeFragment(s: GuardState, length: number): number | null {
  const from = s.here.at;
  if (from === null) return null;
  if (length > s.length) return from + 1;
  const open = [from - 1, from + 1].filter(
    (at) => at >= 0 && (s.seen[at] === undefined || s.seen[at].kind === "none"),
  );
  return open.length === 1 ? open[0] : null;
}

function popped(s: GuardState, entry: HistoryEntry, length: number): Step {
  const at = entry.at ?? (entry.kind === "none" ? placeFragment(s, length) : null);
  const here = { ...entry, at };
  const seen = remember(s.seen, here);
  const t: GuardState = { ...s, here, length, seen };
  const out: GuardCommand[] = [];
  const leaving = s.phase.kind === "moving" && s.phase.then === "leave";
  // A same-document pop means no unload is coming, so a Leave's bypass ends here.
  // Except a pop Next answers with a reload: that unload was already confirmed.
  if (!(leaving && entry.kind === "foreign")) out.push({ type: "setBypass", on: false });
  if (entry.kind === "foreign") return [{ ...t, phase: IDLE }, out];
  if (s.phase.kind === "asking") {
    // The question is modal. Hold the page; the answer undoes these presses.
    if (entry.kind === "next") out.push(STOP);
    return [t, out];
  }
  if (s.phase.kind === "moving") {
    if (at === s.phase.target) return arrive({ ...t, phase: IDLE }, s.phase.then, out);
    t.phase = IDLE; // someone else moved history: judge this pop on its own
  }
  return judge(t, s.here, out);
}

/** Our own `history.go` landed. */
function arrive(t: GuardState, then: "stay" | "leave" | "skip", out: GuardCommand[]): Step {
  const e = t.here;
  if (samePage(e.url, t.page)) {
    if (e.kind === "next") showSamePage(t, e, false, out);
    // Re-park only while something is still unsaved.
    if (then === "stay" && t.blocked && e.kind === "next" && !e.sentinel) out.push(PUSH_SENTINEL);
    return [t, out];
  }
  t.page = e.url;
  if (e.kind === "next") t.home = e.at;
  else out.push(RENDER_HERE);
  return [t, out];
}

/** A popstate the user caused, with no question open. */
function judge(t: GuardState, from: HistoryEntry, out: GuardCommand[]): Step {
  const e = t.here;
  const dir = from.at !== null && e.at !== null ? Math.sign(e.at - from.at) : 0;
  if (samePage(e.url, t.page)) {
    // Same page (the sentinel's real entry, a #fragment, another tab or chat session): nothing
    // unmounts. The one press that asks is Back off the duplicate, the press the sentinel
    // exists for. With nothing unsaved the duplicate is left over, so take the step the user
    // asked for.
    const at = e.at;
    const offDuplicate = from.sentinel && dir < 0 && !e.sentinel && at !== null;
    // Forward onto a leftover duplicate: step over it when there is more ahead.
    const overDuplicate =
      !t.blocked && e.sentinel && !from.sentinel && dir > 0 && at !== null && t.seen[at + 1] !== undefined;
    if (e.kind === "next") showSamePage(t, e, offDuplicate || overDuplicate, out);
    if (offDuplicate) return t.blocked ? ask(t, from.at, at - 1, out) : skip(t, at, at - 1, out);
    if (overDuplicate) return skip(t, at, at + 1, out);
    return [t, out];
  }
  if (t.blocked) {
    // Another page (a long-press jump, or no sentinel): the URL moved, the page stays.
    if (e.kind === "next") out.push(STOP);
    return ask(t, t.home, e.at, out);
  }
  if (e.kind !== "next") return [t, out]; // Next ignores a stateless entry
  t.page = e.url;
  t.home = e.at;
  const above = e.at === null ? undefined : t.seen[e.at + 1];
  if (dir > 0 && e.at !== null && above?.sentinel && samePage(above.url, e.url)) {
    // Forward onto a page whose leftover duplicate sits right above it: take both
    // steps, so the next Forward moves on and the next Back skips the pair.
    return skip(t, e.at, e.at + 1, out);
  }
  return [t, out];
}

/**
 * An app-router entry of the page on screen. "Same page" (the pathname) decides only that
 * nothing asks; whether Next renders is decided by the URL. The same URL (the sentinel's real
 * entry) has nothing new to show, so Next is stopped. Another query (a tab, a chat session:
 * Next keeps the page mounted across it) must render, or the address bar and the screen
 * disagree. `hold`: a question or a step over the duplicate follows, so the page on screen
 * stays until that is settled.
 */
function showSamePage(t: GuardState, e: HistoryEntry, hold: boolean, out: GuardCommand[]): void {
  if (e.url === t.page) t.home = e.at;
  else if (!hold) {
    t.page = e.url;
    t.home = e.at;
    return;
  }
  out.push(STOP);
}

function ask(t: GuardState, home: number | null, leaveTo: number | null, out: GuardCommand[]): Step {
  out.push({ type: "ask" });
  return [{ ...t, phase: { kind: "asking", home, leaveTo } }, out];
}

function skip(t: GuardState, from: number, target: number, out: GuardCommand[]): Step {
  // Nothing earlier in this tab (it was opened on this page): leave to the app's home.
  if (target < 0) return [t, [...out, NAVIGATE_AWAY]];
  out.push({ type: "go", delta: target - from, leaving: false });
  return [{ ...t, phase: { kind: "moving", target, then: "skip" } }, out];
}

function blockedChanged(t: GuardState): Step {
  // Idle on an app-router entry means that entry is the page on screen: every
  // path that ends idle there has set `page` to its url.
  const h = t.here;
  const park = t.blocked && t.phase.kind === "idle" && h.kind === "next" && !h.sentinel;
  return [t, park ? [PUSH_SENTINEL] : []];
}

function answered(
  s: GuardState,
  q: { home: number | null; leaveTo: number | null },
  leave: boolean,
): Step {
  const t: GuardState = { ...s, phase: IDLE };
  const h = t.here;
  const at = h.at;
  if (!leave) {
    if (q.home !== null && at !== null) {
      if (at === q.home) return [t, t.blocked && !h.sentinel ? [PUSH_SENTINEL] : []];
      const phase: GuardPhase = { kind: "moving", target: q.home, then: "stay" };
      return [{ ...t, phase }, [{ type: "go", delta: q.home - at, leaving: false }]];
    }
    // We cannot place this entry. The page is still on screen; put its URL back on top.
    if (h.url === t.page) return [t, []];
    return [t, t.blocked ? [{ type: "restorePage" }, PUSH_SENTINEL] : [{ type: "restorePage" }]];
  }
  if (q.leaveTo !== null && q.leaveTo < 0) return [t, [NAVIGATE_AWAY]];
  if (at !== null && at === q.leaveTo) {
    // Already there: Next's render was held for the question. Render it now.
    const home = h.kind === "next" ? at : t.home;
    return [{ ...t, page: h.url, home }, [h.kind === "next" ? { type: "replay" } : RENDER_HERE]];
  }
  if (at === null || q.leaveTo === null) return [t, [h.url === t.page ? NAVIGATE_AWAY : RENDER_HERE]];
  const phase: GuardPhase = { kind: "moving", target: q.leaveTo, then: "leave" };
  return [
    { ...t, phase },
    [
      { type: "setBypass", on: true },
      { type: "go", delta: q.leaveTo - at, leaving: true },
    ],
  ];
}
