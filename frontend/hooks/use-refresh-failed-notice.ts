"use client";

import { useEffect } from "react";
import { toast } from "sonner";

/**
 * An editor whose background refresh failed keeps what it shows (`isLoadFailure` is false while the
 * query holds data): replacing it with the error lost the text typed since the last save. This says
 * the refresh failed, once per failure (`errorUpdatedAt`), without taking anything off the screen.
 */
export function useRefreshFailedNotice(
  query: { data: unknown; isError: boolean; errorUpdatedAt: number },
  what: string,
): void {
  const failedAt = query.isError && query.data !== undefined ? query.errorUpdatedAt : 0;
  useEffect(() => {
    if (!failedAt) return;
    toast.error(`Couldn't refresh ${what}. Your edits on screen are kept.`, {
      id: `refresh-failed:${what}`,
    });
  }, [failedAt, what]);
}
