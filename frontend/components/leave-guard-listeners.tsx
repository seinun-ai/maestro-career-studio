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
