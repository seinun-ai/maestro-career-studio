"use client";

import { useLayoutEffect, useRef, type ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { EVIDENCE_LABELS, ResolvedFinding } from "@/components/resume-health/finding-cards";
import { SourceQuote } from "@/components/resume-health/judged-text";
import { Button } from "@/components/ui/button";
import { focusIfDropped } from "@/hooks/use-focus-return";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { couldnt } from "@/lib/error-text";
import { focusSuccessor } from "@/lib/focus";
import { textAtLocation } from "@/lib/health-report";
import type { LintFinding, ResumeData, StoredDispute } from "@/lib/types";

/**
 * One row of the Done tab: the bullet it is about and one text-style action that undoes it. The row
 * leaves once the re-run after that action lands, so it hands focus to the next row's action, else
 * the previous row's, else the Done list (a LAYOUT cleanup: React runs it before it detaches the row,
 * while its neighbours can still be read).
 */
function DoneRow({
  label,
  quote,
  children,
  action,
  busyAction,
  failure,
  onAct,
}: {
  label: string;
  quote: string | null;
  children: ReactNode;
  action: string;
  busyAction: string;
  failure: string;
  onAct: () => Promise<void>;
}) {
  const ref = useRef<HTMLLIElement>(null);
  useLayoutEffect(() => {
    const row = ref.current;
    return () => {
      if (!row || !row.contains(document.activeElement)) return;
      const next = focusSuccessor(row, "[data-done-action]");
      queueMicrotask(() => focusIfDropped(next()));
    };
  }, []);
  const act = useMutation({
    mutationFn: onAct,
    onError: (err: Error) => toast.error(couldnt(failure, err)),
  });
  // One undo per gesture: a double click reopened twice and ran the check twice.
  const actOnce = useSingleFlight(act.mutate);
  return (
    <li ref={ref} className="min-w-0 rounded-md border px-3 py-2">
      <div className="flex min-w-0 flex-wrap items-start gap-2">
        <div className="flex min-w-0 flex-1 basis-48 flex-col gap-1">
          <span className="text-muted-foreground text-body-small break-words">{label}</span>
          {quote && <SourceQuote text={quote} clamp />}
          {children}
        </div>
        <Button
          size="xs"
          variant="link"
          data-done-action
          aria-label={`${action}: ${label}`}
          disabled={act.isPending}
          // Disables itself while it works: a native `disabled` drops focus.
          focusableWhenDisabled
          className="ml-auto shrink-0 data-disabled:pointer-events-none data-disabled:opacity-50"
          onClick={() => actOnce()}
        >
          {act.isPending ? busyAction : action}
        </Button>
      </div>
    </li>
  );
}

/**
 * The Done tab: what this session fixed, what the user marked not right (each with Reopen), and the
 * ratings they set by hand (each with Back to automatic). A bullet a dispute lifted out of the report
 * also shows in the tab it came from, where its Fixed entry carries the reply and takes focus; here it
 * is listed plainly, so only one entry on the page is that focus target.
 */
export function DoneTab({
  resolved,
  disputes,
  disputesFailed,
  onRetryDisputes,
  overrides,
  data,
  onReopen,
  onBackToAutomatic,
}: {
  resolved: LintFinding[];
  disputes: StoredDispute[];
  disputesFailed: boolean;
  onRetryDisputes: () => void;
  overrides: LintFinding[];
  data: ResumeData | null;
  onReopen: (hash: string) => Promise<void>;
  onBackToAutomatic: (hash: string) => Promise<void>;
}) {
  const empty = resolved.length === 0 && disputes.length === 0 && overrides.length === 0;
  return (
    <section tabIndex={-1} className="space-y-6 outline-none">
      {empty && !disputesFailed && (
        <p className="text-muted-foreground text-body-medium">Nothing here yet.</p>
      )}
      {resolved.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-title-small">Fixed this session ({resolved.length})</h3>
          {resolved.map((finding) => (
            <ResolvedFinding key={finding.id} finding={finding} />
          ))}
        </div>
      )}
      {disputesFailed ? (
        <p className="text-body-medium">
          Couldn&apos;t load what you marked not right.{" "}
          <Button size="xs" variant="link" className="h-auto px-0" onClick={onRetryDisputes}>
            Try again
          </Button>
        </p>
      ) : (
        disputes.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-title-small">Marked not right ({disputes.length})</h3>
            <ul className="space-y-2">
              {disputes.map((d) => (
                <DoneRow
                  key={`${d.content_hash}:${d.location.section}:${d.location.index ?? ""}:${d.location.bullet_index ?? ""}`}
                  label={d.label}
                  quote={d.text}
                  action="Reopen"
                  busyAction="Reopening…"
                  failure="reopen it"
                  onAct={() => onReopen(d.content_hash)}
                >
                  <p className="max-w-[65ch] text-body-medium">You said: {d.note}</p>
                  <p className="text-muted-foreground max-w-[65ch] text-body-medium">{d.reply}</p>
                </DoneRow>
              ))}
            </ul>
          </div>
        )
      )}
      {overrides.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-title-small">Corrected ratings ({overrides.length})</h3>
          <ul className="space-y-2">
            {overrides.map((f) => (
              <DoneRow
                key={f.id}
                label={f.label}
                quote={data ? textAtLocation(data, f) : null}
                action="Back to automatic"
                busyAction="Resetting…"
                failure="set the rating back to automatic"
                onAct={() => onBackToAutomatic(f.content_hash!)}
              >
                <p className="max-w-[65ch] text-body-medium">
                  You rated it: {f.classification_level ? EVIDENCE_LABELS[f.classification_level] : "—"}
                  {f.classification_reason ? `. ${f.classification_reason}` : ""}
                </p>
              </DoneRow>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
