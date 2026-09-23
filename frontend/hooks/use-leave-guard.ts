"use client";

import { useEffect, useId } from "react";

import { setLeaveGuard } from "@/lib/leave-guard";

/**
 * Register unsaved work while `when` holds. In-app links (GuardedLink) then ask
 * before leaving, and reload/close shows the browser's own warning.
 * `reloadOnly`: work an in-app exit still saves (it flushes on unmount), so only a
 * page unload, which runs no cleanup, needs the warning.
 */
export function useLeaveGuard(
  when: boolean,
  { reloadOnly = false }: { reloadOnly?: boolean } = {},
) {
  const owner = useId();
  const scope = when ? (reloadOnly ? "unload" : "all") : null;
  useEffect(() => {
    setLeaveGuard(owner, scope);
    return () => setLeaveGuard(owner, null);
  }, [owner, scope]);
}
