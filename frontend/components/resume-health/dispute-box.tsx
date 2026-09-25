"use client";

import { useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { focusIfDropped } from "@/hooks/use-focus-return";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { disputeBullet } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { DISPUTE_DETAIL, disputeFailure } from "@/lib/health-report";
import type { DisputeResult, LintFinding } from "@/lib/types";

/** The page keeps the reply (by content hash) and runs the report again when the rating moved. */
export type DisputeHandler = (result: DisputeResult) => Promise<void>;

/**
 * A bullet the check rated can be disputed, unless the user set its rating by hand: the endpoint
 * refuses that one until the rating is back to automatic (the ⋯ menu's "This rating is wrong…").
 */
export function canDispute(finding: LintFinding): boolean {
  return Boolean(
    finding.content_hash &&
      finding.classification_level &&
      finding.classification_source !== "override",
  );
}

type Failure = { kind: "changed" } | { kind: "text"; text: string };

/**
 * "Not right?": the user tells the check, in their own words, why a flag is wrong. The trigger sits
 * on the card's control row, beside `controls` (an ask's Write new wording). The reply lives in the
 * page, keyed by the bullet's hash, so it survives the re-run that replaces this card when the
 * rating moved; a suggestion carrying a fact from the note renders through `renderSuggestion`
 * (the card's hash-guarded SuggestionBlock, copy-only for Other sections).
 */
export function DisputeBox({
  finding,
  kind,
  resumeKey,
  result,
  onDisputed,
  onReanalyze,
  locked,
  controls,
  renderSuggestion,
}: {
  finding: LintFinding;
  kind: "base" | "application";
  resumeKey: string;
  result?: DisputeResult;
  onDisputed?: DisputeHandler;
  onReanalyze?: () => void;
  locked?: boolean;
  controls?: ReactNode;
  renderSuggestion: (suggestion: string) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [failure, setFailure] = useState<Failure | null>(null);
  const noteId = useId();
  const hintId = useId();
  const panelId = useId();
  const replyRef = useRef<HTMLParagraphElement>(null);
  const offered = canDispute(finding) && Boolean(onDisputed) && !locked;

  // Send leaves with the form, and a re-run can replace the whole card: either way focus that fell
  // to <body> lands on the reply, the one thing that changed.
  useLayoutEffect(() => {
    if (result) focusIfDropped(replyRef.current);
  }, [result]);
  // A dispute that lifts the bullet out of the report removes this card while the reply holds focus.
  // A LAYOUT cleanup runs before React detaches it; after the commit, focus goes to the resolved
  // "Fixed" entry that now carries the reply (ResolvedFinding takes it if it mounts later).
  const hash = finding.content_hash;
  useLayoutEffect(() => {
    const reply = replyRef.current;
    return () => {
      if (!reply || document.activeElement !== reply) return;
      queueMicrotask(() =>
        focusIfDropped(document.querySelector<HTMLElement>(`[data-resolved-hash="${hash}"]`)),
      );
    };
  }, [result, hash]);

  const send = useMutation({
    mutationFn: () =>
      disputeBullet(kind, resumeKey, {
        location: {
          section: finding.location.section,
          index: finding.location.index,
          bullet_index: finding.location.bullet_index,
        },
        expected_content_hash: finding.content_hash!,
        note: note.trim(),
      }),
    onMutate: () => setFailure(null),
    onSuccess: (reply) => {
      setOpen(false);
      setNote("");
      onDisputed!(reply).catch((err: unknown) =>
        toast.error(couldnt("update the report", err)),
      );
    },
    onError: (err: Error) => {
      const why = disputeFailure(err);
      if (why === "changed") return setFailure({ kind: "changed" });
      if (why === "overridden") return setFailure({ kind: "text", text: DISPUTE_DETAIL.overridden });
      // The unreadable 502's detail is already "Couldn't re-read this bullet. Try again.": said once.
      const detail = err.message === DISPUTE_DETAIL.unreadable ? null : err;
      setFailure({ kind: "text", text: couldnt("re-read this bullet", detail) });
    },
  });
  // One dispute per gesture: a double click sent the note twice.
  const sendOnce = useSingleFlight(send.mutate);

  if (!offered && !controls && !result) return null;

  return (
    <>
      {(offered || controls) && (
        <div className="mt-2 flex items-center gap-2">
          {offered && (
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground text-sm underline-offset-2 hover:underline"
              aria-expanded={open}
              aria-controls={panelId}
              onClick={() => setOpen((v) => !v)}
            >
              Not right?
            </button>
          )}
          {controls && <div className="ml-auto">{controls}</div>}
        </div>
      )}
      {offered && open && (
        <div id={panelId} className="mt-2 grid max-w-[65ch] gap-1.5">
          <Label htmlFor={noteId}>Tell us why</Label>
          <Textarea
            id={noteId}
            rows={2}
            value={note}
            maxLength={1000}
            aria-describedby={hintId}
            onChange={(e) => setNote(e.target.value)}
            className="text-sm"
          />
          <p id={hintId} className="text-muted-foreground text-xs">
            For example: there&apos;s no number for this, it&apos;s confidential, or you misread it.
          </p>
          <div className="flex justify-end">
            <Button
              size="sm"
              variant="outline"
              disabled={note.trim().length === 0 || send.isPending}
              // Disables itself while sending: a native `disabled` drops focus.
              focusableWhenDisabled
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={() => sendOnce()}
            >
              {send.isPending ? "Sending…" : "Send"}
            </Button>
          </div>
        </div>
      )}
      {failure && (
        <p role="alert" className="text-destructive mt-2 max-w-[65ch] text-xs">
          {failure.kind === "changed" ? (
            <>
              This bullet changed since the check.{" "}
              {onReanalyze ? (
                <button
                  type="button"
                  className="underline underline-offset-2"
                  onClick={() => onReanalyze()}
                >
                  Check again?
                </button>
              ) : (
                "Check again?"
              )}
            </>
          ) : (
            failure.text
          )}
        </p>
      )}
      {result && (
        <>
          <p
            ref={replyRef}
            role="status"
            tabIndex={-1}
            className="text-foreground mt-2 max-w-[65ch] text-sm outline-none"
          >
            {result.reply}
          </p>
          {result.suggestion != null && renderSuggestion(result.suggestion)}
        </>
      )}
    </>
  );
}
