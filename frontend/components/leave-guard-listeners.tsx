"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useConfirmLeave } from "@/components/guarded-link";
import {
  allowLeave,
  clearLeaveBypass,
  consumeLeaveBypass,
  leaveBlocked,
  markSentinel,
  onInAppBlockedChange,
  readEntry,
  stampAfterWrite,
  stampState,
  startGuard,
  stepGuard,
  type GuardCommand,
  type GuardEvent,
  type GuardState,
  type HistoryEntry,
} from "@/lib/leave-guard";

/*
 * Back and Forward with unsaved work (owner decision 1). The decisions live in the
 * pure machine in lib/leave-guard.ts; this file feeds it and carries out its commands.
 *
 * Next internals this relies on (Next 16.3.0; an upgrade re-runs browser check U1-7
 * and the Back/Forward scenarios in the lane doc):
 * - `next/dist/client/components/app-router.js` patches `history.pushState` and
 *   `replaceState`. A state that already carries `__NA` passes straight through with
 *   no router action, so the sentinel and the position stamp (both spread Next's
 *   state) keep Next's tree, and a traverse to them renders this route.
 * - Its `popstate` listener is on `window`, bubble phase. Ours is capture phase, so it
 *   runs first, and `stopImmediatePropagation` keeps Next from rendering. Next ignores
 *   a pop with no state (a `#fragment` navigation) and reloads for a state without
 *   `__NA`; the machine reads entries the same way.
 */

/** Where Leave goes when the tab has no earlier page (it was opened on the editor). */
const LEAVE_FALLBACK = "/";
/** A Leave's `history.go` that brings neither a popstate nor an unload had nowhere to go. */
const STALL_MS = 1500;

// One tab, one history, one machine. Module state, like the registry: the writers
// are the history patch and event handlers, and nothing renders from it.
let guard: GuardState | null = null;
let replaying = false;
let stallTimer: ReturnType<typeof setTimeout> | undefined;
let pageSnapshot: { state: object; href: string } | null = null;

function currentEntry(): HistoryEntry {
  return readEntry(window.history.state, window.location.pathname + window.location.search);
}

function machine(): GuardState {
  guard ??= startGuard(currentEntry(), window.history.length, leaveBlocked("in-app"));
  return guard;
}

function feed(event: GuardEvent): GuardCommand[] {
  const [next, commands] = stepGuard(machine(), event);
  guard = next;
  // The page's own entry, for a Stay the machine cannot place (restorePage).
  const state = window.history.state as object | null;
  if (state && next.here.kind === "next" && next.here.url === next.page) {
    pageSnapshot = { state, href: window.location.href };
  }
  return commands;
}

interface StampHooks {
  replace: History["replaceState"];
  afterWrite?: (how: "push" | "replace", before: HistoryEntry) => void;
}
const HOOKS = Symbol.for("maestro.leaveGuard.history");

/**
 * Stamp every entry the app router writes with its position in the tab's history,
 * so each popstate knows how far and in which direction it moved. The patch sits
 * under Next's own (this module runs before Next's app router effect captures
 * `history.pushState`) and is installed once; a hot reload swaps only `afterWrite`.
 */
function installPositionStamps() {
  const history = window.history as History & { [HOOKS]?: StampHooks };
  let hooks = history[HOOKS];
  if (!hooks) {
    const push = history.pushState.bind(history);
    const replace = history.replaceState.bind(history);
    const installed: StampHooks = { replace };
    history.pushState = function pushState(data, unused, url) {
      const before = currentEntry();
      push(data, unused, url);
      installed.afterWrite?.("push", before);
    };
    history.replaceState = function replaceState(data, unused, url) {
      const before = currentEntry();
      replace(data, unused, url);
      installed.afterWrite?.("replace", before);
    };
    history[HOOKS] = installed;
    hooks = installed;
  }
  const { replace } = hooks;
  hooks.afterWrite = (how, before) => {
    const written = currentEntry();
    if (written.kind !== "next") return; // only app-router entries carry a position
    const { at, sentinel } = stampAfterWrite(how, before, written, history.length, machine().here.at);
    if (at !== null) replace(stampState(history.state as object, at, sentinel), "", window.location.href);
    feed({ type: "wrote", how, entry: currentEntry(), length: history.length });
  };
}

if (typeof window !== "undefined") installPositionStamps();

/** Stamp the current entry if Next wrote it before the patch was in place. */
function stampCurrentEntry() {
  const here = currentEntry();
  const hooks = (window.history as History & { [HOOKS]?: StampHooks })[HOOKS];
  if (here.kind === "next" && here.at === null) hooks?.afterWrite?.("replace", here);
}

/**
 * Park a duplicate of this entry above it. Only an app-router entry can be duplicated
 * (a stateless #fragment entry cannot). The machine never assumes the push happened:
 * it learns the sentinel from the entry the history patch reports.
 */
function pushSentinel() {
  const state = window.history.state as object | null;
  if (!state || currentEntry().kind !== "next") return;
  window.history.pushState(markSentinel(state, true), "", window.location.href);
}

function restorePage() {
  if (!pageSnapshot) return;
  window.history.pushState(markSentinel(pageSnapshot.state, false), "", pageSnapshot.href);
}

/** Next held its render for the question: hand it this entry's popstate now. */
function replay() {
  replaying = true;
  try {
    window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
  } finally {
    replaying = false;
  }
}

function isReplaying() {
  return replaying;
}

function settleLeave() {
  clearTimeout(stallTimer);
  stallTimer = undefined;
}

function watchLeave(onStall: () => void) {
  settleLeave();
  stallTimer = setTimeout(onStall, STALL_MS);
}

/**
 * The app's ONE beforeunload listener (it used to be one per editor, which also meant
 * one per mounted editor). It reads the registry at the moment of the unload, so it
 * warns only while something is registered. It stays quiet for a hard navigation the
 * user already confirmed ("Leave"), which would otherwise ask twice.
 */
export function LeaveGuardListeners() {
  const pathname = usePathname();
  const router = useRouter();
  const confirmLeave = useConfirmLeave();
  // A confirmed "Leave" that became a client navigation leaves no unload to bypass.
  useEffect(() => {
    clearLeaveBypass();
  }, [pathname]);
  useEffect(() => {
    const perform = (command: GuardCommand) => {
      switch (command.type) {
        case "go":
          if (command.leaving) watchLeave(() => run(feed({ type: "stalled" })));
          window.history.go(command.delta);
          return;
        case "pushSentinel":
          pushSentinel();
          return;
        case "restorePage":
          restorePage();
          return;
        case "replay":
          replay();
          return;
        case "renderHere":
          allowLeave();
          router.replace(window.location.pathname + window.location.search + window.location.hash);
          return;
        case "navigateAway":
          allowLeave();
          router.push(LEAVE_FALLBACK);
          return;
      }
    };
    const run = (commands: GuardCommand[], event?: PopStateEvent) => {
      const later: GuardCommand[] = [];
      for (const command of commands) {
        if (command.type === "stop") event?.stopImmediatePropagation();
        else if (command.type === "setBypass") {
          if (command.on) allowLeave();
          else clearLeaveBypass();
        } else if (command.type === "ask") {
          void confirmLeave().then((leave) => run(feed({ type: "answer", leave })));
        } else later.push(command);
      }
      if (later.length === 0) return;
      // Chrome ignores history.go() called while a popstate is being dispatched.
      if (event) setTimeout(() => later.forEach(perform), 0);
      else later.forEach(perform);
    };
    // Every popstate goes through the machine. Capture phase: Next's listener is bubble.
    const onPopState = (event: PopStateEvent) => {
      if (isReplaying()) return;
      settleLeave();
      run(feed({ type: "pop", entry: currentEntry(), length: window.history.length }), event);
    };
    const onPageShow = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      run(feed({ type: "restored", entry: currentEntry(), length: window.history.length }));
    };
    stampCurrentEntry();
    const stop = onInAppBlockedChange((blocked) => run(feed({ type: "blocked", blocked })));
    run(feed({ type: "blocked", blocked: leaveBlocked("in-app") }));
    window.addEventListener("popstate", onPopState, { capture: true });
    window.addEventListener("pageshow", onPageShow);
    return () => {
      stop();
      settleLeave();
      window.removeEventListener("popstate", onPopState, { capture: true });
      window.removeEventListener("pageshow", onPageShow);
    };
  }, [confirmLeave, router]);
  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      settleLeave(); // a Leave that reached another document did not stall
      if (!leaveBlocked("unload") || consumeLeaveBypass()) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, []);
  return null;
}
