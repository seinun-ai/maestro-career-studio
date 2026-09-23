"use client";

import { useState } from "react";

/** `value`, or the last non-nullish value it had. A refetch clears a query's `error` while it runs; a surface
 *  still showing that failure (retrying) must keep its words, and a 404-as-state must stay that state. */
export function useLastSeen<T>(value: T | null | undefined): T | null | undefined {
  const [last, setLast] = useState(value);
  if (value != null && value !== last) setLast(value);
  return value ?? last;
}
