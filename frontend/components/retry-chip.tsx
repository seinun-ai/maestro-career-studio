"use client";

import { useRef, type ReactNode } from "react";

import { useFocusHandoff } from "@/hooks/use-focus-return";

/**
 * A header chip whose check failed, pressed to retry it (the health grade, the
 * Career KB sync pill). It follows `LoadErrorState`'s Try again: the caller
 * keeps it mounted through the retry (`isLoadFailure`), it stays focusable
 * while retrying (`aria-disabled`, not a native `disabled`, which drops a
 * keyboard user's focus to <body>), and recovery hands focus to the nearest
 * `tabIndex={-1}` ancestor or the main area.
 */
export function RetryChip({
  className,
  title,
  icon,
  label,
  retrying,
  onRetry,
}: {
  className: string;
  title: string;
  icon: ReactNode;
  label: string;
  retrying: boolean;
  onRetry: () => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  useFocusHandoff(ref);
  return (
    <button
      ref={ref}
      type="button"
      className={className}
      title={title}
      aria-disabled={retrying || undefined}
      onClick={() => {
        if (!retrying) onRetry();
      }}
    >
      {icon}
      {retrying ? "Retrying…" : label}
    </button>
  );
}
