"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { LOCKED_BTN, SuggestionEditor } from "@/components/resume-health/finding-cards";
import { SourceQuote } from "@/components/resume-health/judged-text";
import { toastRewriteError } from "@/components/resume-health/report-errors";
import { Button } from "@/components/ui/button";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { draftRewrite } from "@/lib/api";
import { STALE_APPLY_HINT, textAtLocation } from "@/lib/health-report";
import { cn } from "@/lib/utils";
import type { LintFinding, ResumeData } from "@/lib/types";

type Draft = { finding: LintFinding; suggestion: string; content_hash: string };

/**
 * The Shorten tab: each too-long bullet with one text-style Shorten, which drafts a shorter version
 * (`draft-rewrite`, objective "condense", hash-guarded) into the same editor every Apply uses.
 * Focus never drops: Shorten stays focusable while it drafts, and an applied draft stays on screen
 * (its editor's "Applied" line takes focus) until the next check removes the row.
 */
export function ShortenList({
  notes,
  data,
  kind,
  resumeKey,
  onApplied,
  locked,
  onReanalyze,
}: {
  notes: LintFinding[];
  data: ResumeData;
  kind: "base" | "application";
  resumeKey: string;
  onApplied: () => void;
  locked?: boolean;
  onReanalyze?: () => void;
}) {
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  // Applied rows keep their editor (showing "Applied") and lose their Shorten.
  const [applied, setApplied] = useState<ReadonlySet<string>>(new Set());
  const condense = useMutation({
    mutationFn: (finding: LintFinding) =>
      draftRewrite(kind, resumeKey, {
        location: {
          section: finding.location.section,
          index: finding.location.index,
          bullet_index: finding.location.bullet_index,
        },
        objective: "condense",
        expected_content_hash: finding.content_hash ?? undefined,
      }).then((result) => ({ finding, ...result })),
    onSuccess: (result) => setDrafts((d) => ({ ...d, [result.finding.id]: result })),
    onError: (err: Error) => toastRewriteError(err, onReanalyze, "write new wording"),
  });
  // One draft per gesture: a double click asked for a shorter version twice.
  const condenseOnce = useSingleFlight(condense.mutate);
  return (
    <ul className="space-y-2">
      {notes.map((note) => {
        const current = textAtLocation(data, note) ?? note.subject ?? "";
        const draft = drafts[note.id];
        return (
          <li key={note.id} className="min-w-0 rounded-md border px-3 py-2">
            <div className="flex min-w-0 flex-wrap items-start gap-2">
              <div className="flex min-w-0 flex-1 basis-48 flex-col gap-1">
                <span className="text-muted-foreground text-body-small break-words">{note.label}</span>
                <SourceQuote text={current || note.issue} clamp />
                <p className="text-muted-foreground max-w-[65ch] text-body-small">{note.issue}</p>
              </div>
              {!applied.has(note.id) && (
                <Button
                  size="xs"
                  variant="link"
                  aria-label={`Shorten: ${note.label}`}
                  disabled={locked || condense.isPending}
                  title={locked ? STALE_APPLY_HINT : undefined}
                  // Disables itself while it drafts: a native `disabled` drops focus.
                  focusableWhenDisabled
                  className={cn(
                    "ml-auto shrink-0",
                    locked ? LOCKED_BTN : "data-disabled:pointer-events-none data-disabled:opacity-50",
                  )}
                  onClick={() => condenseOnce(note)}
                >
                  {condense.isPending && condense.variables?.id === note.id ? "Shortening…" : "Shorten"}
                </Button>
              )}
            </div>
            {draft && (
              <SuggestionEditor
                // A new draft for the row is a new editor (its own draft text and Applied state).
                key={`${draft.content_hash}:${draft.suggestion}`}
                finding={note}
                currentText={current}
                suggestion={draft.suggestion}
                kind={kind}
                resumeKey={resumeKey}
                onApplied={() => {
                  setApplied((a) => new Set(a).add(note.id));
                  onApplied();
                }}
                onReanalyze={onReanalyze}
                locked={locked}
                expectedHash={draft.content_hash}
              />
            )}
          </li>
        );
      })}
    </ul>
  );
}
