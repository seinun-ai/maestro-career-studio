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
