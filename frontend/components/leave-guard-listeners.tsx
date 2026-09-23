"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

import { useConfirmLeave } from "@/components/guarded-link";
import {
  allowLeave,
  clearLeaveBypass,
  consumeLeaveBypass,
  leaveBlocked,
  onInAppBlockedChange,
  onSentinel,
  pushSentinel,
} from "@/lib/leave-guard";

/**
 * The app's ONE beforeunload listener (it used to be one per editor, which also meant
 * one per mounted editor). It reads the registry at the moment of the unload, so it
 * warns only while something is registered. It stays quiet for a hard navigation the
 * user already confirmed in GuardedLink, which would otherwise ask twice.
 */
export function LeaveGuardListeners() {
  const pathname = usePathname();
  const confirmLeave = useConfirmLeave();
  // A confirmed "Leave" that became a client navigation leaves no unload to bypass.
  useEffect(() => {
    clearLeaveBypass();
  }, [pathname]);
  useEffect(() => {
    let armed = false; // our duplicate is (or was) above the real entry
    let swallow = 0; // popstates we caused ourselves
    let asking = false;
    let drifted = 0; // extra Back presses while the question is open
    let afterSwallow: (() => void) | null = null;

    const applyAnswer = (leave: boolean) => {
      if (leave) {
        allowLeave();
        window.history.back();
      } else {
        pushSentinel();
        armed = true;
      }
    };

    const stop = onInAppBlockedChange((blocked) => {
      if (blocked && !armed && !asking) {
        pushSentinel();
        armed = true;
      } else if (!blocked && armed && !asking) {
        armed = false;
        // Saved while parked on the duplicate: step off it, or the next Back
        // is a dead press.
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
        if (swallow === 0 && afterSwallow) {
          const fn = afterSwallow;
          afterSwallow = null;
          // history.back() during popstate is ignored. Run the answer after
          // this traversal finishes.
          setTimeout(fn, 0);
        }
        return;
      }
      if (asking) {
        // A second Back would otherwise render that entry under the dialog.
        event.stopImmediatePropagation();
        drifted += 1;
        return;
      }
      if (!armed || onSentinel()) return;
      armed = false; // stepped off the duplicate: same URL, editor still mounted
      if (!leaveBlocked("in-app")) return;
      event.stopImmediatePropagation();
      asking = true;
      drifted = 0;
      void confirmLeave().then((leave) => {
        asking = false;
        const extra = drifted;
        drifted = 0;
        if (extra > 0) {
          swallow += extra;
          afterSwallow = () => applyAnswer(leave);
          window.history.go(extra);
          return;
        }
        applyAnswer(leave);
      });
    };
    // Next's own listener is bubble-phase (app-router.js). Capture runs first.
    window.addEventListener("popstate", onPopState, { capture: true });
    return () => {
      stop();
      window.removeEventListener("popstate", onPopState, { capture: true });
    };
  }, [confirmLeave]);
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
