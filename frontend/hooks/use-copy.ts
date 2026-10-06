"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { couldnt } from "@/lib/error-text";

/** Copy text, then hold `copied` for a moment so the control can say so. A refused copy says why:
 *  with the default toast, or with `onError` instead of it (never both, so one failure is one message). */
export function useCopy({
  holdMs = 1200,
  onError,
}: { holdMs?: number; onError?: (err: unknown) => void } = {}) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const copy = useCallback(
    async (text: string): Promise<boolean> => {
      try {
        await navigator.clipboard.writeText(text);
      } catch (err) {
        if (onError) onError(err);
        else toast.error(couldnt("copy that", err));
        return false;
      }
      setCopied(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), holdMs);
      return true;
    },
    [holdMs, onError],
  );
  return { copied, copy };
}
