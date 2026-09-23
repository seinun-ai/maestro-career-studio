"use client";

import { useState } from "react";

import { isLoadFailure, type LoadQuery } from "@/lib/query-state";

/** `value`, or the last non-nullish value it had. A refetch clears a query's `error` while it runs; a surface
 *  still showing that failure (retrying) must keep its words, and a 404-as-state must stay that state. */
export function useLastSeen<T>(value: T | null | undefined): T | null | undefined {
  const [last, setLast] = useState(value);
  if (value != null && value !== last) setLast(value);
  return value ?? last;
}

/**
 * The error a failed load shows, or null while the surface shows none. A surface that treats a status as a
 * state (a missing application, no health report yet) branches on this, not on `query.error`: react-query
 * clears the error while a retry runs, so the error is remembered.
 *
 * A failed query with no data also refetches when its surface mounts again, and the first render of that
 * remount has no error to remember yet. It reads as null (loading), never as the generic failure, so a
 * revisited 404 shows the skeleton for the moment the refetch takes instead of flashing "Couldn't load…
 * Retrying…".
 */
export function useLoadFailureError(query: LoadQuery & { error: unknown }): unknown {
  const error = useLastSeen(query.error);
  return isLoadFailure(query) ? (error ?? null) : null;
}
