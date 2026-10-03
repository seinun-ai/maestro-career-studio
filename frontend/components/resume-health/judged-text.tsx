"use client";

import { useEffect, useRef, useState } from "react";

import { wordDiff } from "@/lib/word-diff";
import { cn } from "@/lib/utils";

/**
 * Resume text as the health report shows it: upright, full contrast, wrapped to a reading measure
 * (docs/frontend-conventions.md, "Judged resume text"). Shared by the finding cards and the Wording
 * checklist.
 */

export function DiffText({ oldText, newText }: { oldText: string; newText: string }) {
  return (
    <p className="max-w-[65ch] text-body-medium leading-6">
      {wordDiff(oldText, newText).map((token, i) => (
        <span
          key={i}
          className={cn(
            token.kind === "removed" &&
              "bg-destructive/10 text-destructive line-through",
            token.kind === "added" &&
              "bg-success-container text-on-success-container",
          )}
        >
          {token.text}{" "}
        </span>
      ))}
    </p>
  );
}


export function SuggestionCopyOnly({
  currentText,
  suggestion,
}: {
  currentText: string;
  suggestion: string;
}) {
  return (
    <div className="mt-2 space-y-2 border-t pt-2">
      <div className="bg-surface-container-low rounded-md p-2">
        <DiffText oldText={currentText} newText={suggestion} />
      </div>
      <p className="text-muted-foreground max-w-[65ch] text-body-small">
        Can&apos;t apply this here yet. Copy the new wording into the resume.
      </p>
    </div>
  );
}


export function SourceQuote({ text, clamp }: { text: string; clamp?: boolean }) {
  const [open, setOpen] = useState(false);
  const [cut, setCut] = useState(false);
  const quoteRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    const el = quoteRef.current;
    if (!clamp || open || !el) return;
    // Measured, never guessed from length: only a quote the clamp actually cuts
    // offers "Show all" (a toggle under every short bullet was the clutter).
    const observer = new ResizeObserver(() => setCut(el.scrollHeight > el.clientHeight + 1));
    observer.observe(el);
    return () => observer.disconnect();
  }, [clamp, open, text]);
  return (
    <div className="border-l-2 border-border pl-3">
      <p
        ref={quoteRef}
        className={cn("text-foreground max-w-[65ch] text-body-medium", clamp && !open && "line-clamp-3")}
      >
        {text}
      </p>
      {clamp && (open || cut) && (
        <button
          type="button"
          className="text-primary mt-0.5 text-body-small underline-offset-2 hover:underline"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Show less" : "Show all"}
        </button>
      )}
    </div>
  );
}

