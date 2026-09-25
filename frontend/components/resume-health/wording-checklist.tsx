"use client";

import { useLayoutEffect, useRef, useState, type RefObject } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { DiffText, SourceQuote, SuggestionCopyOnly } from "@/components/resume-health/finding-cards";
import { WordListDialog, WORDING_QUERY_KEY } from "@/components/resume-health/word-list-dialog";
import { Button } from "@/components/ui/button";
import { focusIfDropped, useFocusHandoff, useFocusOnNextCommit } from "@/hooks/use-focus-return";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { ApiError, applyResumeEdits, getWording, putWording } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { focusSuccessor } from "@/lib/focus";
import {
  canIgnore,
  isContentChangedError,
  type LintEditOp,
  normalizeWord,
  slipFix,
  textAtLocation,
  withIgnored,
  wordingEditOp,
} from "@/lib/health-report";
import { notifyRenderNote } from "@/lib/render-note";
import type { LintFinding, ResumeData } from "@/lib/types";

/**
 * A row that leaves while it holds focus (a re-run after Ignore or Check again drops it) hands focus
 * to the next row's action, else the previous row's, else the group. A LAYOUT cleanup: React runs it
 * before it detaches the row, so its neighbours can still be read.
 */
function useSuccessorOnLeave(ref: RefObject<HTMLElement | null>) {
  useLayoutEffect(() => {
    const row = ref.current;
    return () => {
      if (!row || !row.contains(document.activeElement)) return;
      const next = focusSuccessor(row, "[data-wording-action]");
      queueMicrotask(() => focusIfDropped(next()));
    };
  }, [ref]);
}

type Shared = {
  data: ResumeData | null;
  kind: "base" | "application";
  resumeKey: string;
  onApplied: () => void;
  onReanalyze?: () => void;
};

function WordingRow({
  note,
  data,
  kind,
  resumeKey,
  onApplied,
  onReanalyze,
  onIgnore,
}: Shared & { note: LintFinding; onIgnore: (subject: string) => Promise<void> }) {
  const rowRef = useRef<HTMLLIElement>(null);
  useSuccessorOnLeave(rowRef);
  const [applied, setApplied] = useState(false);
  const [changed, setChanged] = useState(false);
  // Apply and Remove leave with their button: "Applied" takes the focus.
  const appliedRef = useRef<HTMLParagraphElement>(null);
  const focusNext = useFocusOnNextCommit();
  const slip = note.rule === "language.slip";
  const fix = slip ? slipFix(note) : null;
  const currentText = data ? textAtLocation(data, note) : null;
  const op = data ? wordingEditOp(note) : null;
  const otherSection = note.location.section.startsWith("extra:");

  const apply = useMutation({
    mutationFn: (edit: LintEditOp) => applyResumeEdits(kind, resumeKey, [edit]),
    onMutate: () => setChanged(false),
    onSuccess: (result) => {
      setApplied(true);
      focusNext(appliedRef);
      notifyRenderNote(result);
      toast.success("Applied and saved as a new version");
      onApplied();
    },
    onError: (err: Error) => {
      if (err instanceof ApiError && isContentChangedError(err)) return setChanged(true);
      toast.error(couldnt(slip ? "apply the fix" : "remove the word", err));
    },
  });
  // One edit per gesture: a double click would apply it twice.
  const applyOnce = useSingleFlight(apply.mutate);

  const ignore = useMutation({
    mutationFn: () => onIgnore(note.subject!),
    onError: (err: Error) => toast.error(couldnt("add it to Never flag", err)),
  });
  // One Ignore per gesture: its re-run takes the row away.
  const ignoreOnce = useSingleFlight(ignore.mutate);
  const busy = apply.isPending || ignore.isPending;

  return (
    <li ref={rowRef} className="space-y-1.5 px-3 py-2">
      <p className="text-muted-foreground text-xs break-words">{note.label}</p>
      {currentText && <SourceQuote text={currentText} clamp />}
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1 basis-48">
          {fix != null ? (
            <>
              {/* The fix as a word diff; its sentence is what a screen reader hears. */}
              <div aria-hidden>
                <DiffText oldText={note.subject!} newText={fix} />
              </div>
              <p className="sr-only">{note.issue}</p>
            </>
          ) : (
            <p className="text-foreground max-w-[65ch] text-sm">{note.issue}</p>
          )}
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-1">
          {applied ? (
            <p ref={appliedRef} tabIndex={-1} className="text-muted-foreground px-2 text-xs outline-none">
              Applied
            </p>
          ) : (
            op && (
              <Button
                size="xs"
                variant="link"
                data-wording-action
                disabled={busy}
                // Disables itself while applying: a native `disabled` drops focus.
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={() => applyOnce(op)}
              >
                {slip ? "Apply" : "Remove"}
              </Button>
            )
          )}
          {canIgnore(note.subject) && (
            <Button
              size="xs"
              variant="link"
              data-wording-action
              disabled={busy}
              focusableWhenDisabled
              className="text-muted-foreground hover:text-foreground data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={() => ignoreOnce()}
            >
              {ignore.isPending ? "Ignoring…" : "Ignore"}
            </Button>
          )}
        </div>
      </div>
      {/* Nothing to apply here: an Other section's guarded wording is shown to copy, and a fix the
          rewrite guards refused is left to the user. */}
      {!op && !applied &&
        (otherSection && note.suggestion != null && currentText != null ? (
          <SuggestionCopyOnly currentText={currentText} suggestion={note.suggestion} />
        ) : (
          <p className="text-muted-foreground max-w-[65ch] text-xs">
            {slip
              ? <>Can&apos;t apply this fix here. Correct it in the resume.</>
              : <>Can&apos;t remove it here. Edit the bullet in the resume.</>}
          </p>
        ))}
      {changed && (
        <p role="alert" className="text-destructive max-w-[65ch] text-xs">
          This bullet changed since the check.{" "}
          {onReanalyze ? (
            <button type="button" className="underline underline-offset-2" onClick={() => onReanalyze()}>
              Check again?
            </button>
          ) : (
            "Check again?"
          )}
        </p>
      )}
    </li>
  );
}

/**
 * The Wording checklist: spelling and grammar slips the check found, and clichés and filler words
 * from the user's word list. Zero score, never blocking. Self-contained so the report's layout can
 * move it; the Notes table renders it today.
 */
export function WordingChecklist({
  notes,
  onWordingChanged,
  ...shared
}: Shared & {
  notes: LintFinding[];
  /** Runs the report again: a word list change changes which notes exist. */
  onWordingChanged: () => Promise<void>;
}) {
  const qc = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  // The group can leave while it holds focus (the last hit ignored): focus goes to the Notes section.
  const groupRef = useRef<HTMLDivElement>(null);
  useFocusHandoff(groupRef);

  // Never flag gets the word on top of the lists as they are now (the PUT replaces all three).
  const ignoreWord = async (subject: string) => {
    const current = await getWording();
    const saved = await putWording(withIgnored(current, subject));
    qc.setQueryData(WORDING_QUERY_KEY, saved);
    toast.success(`"${normalizeWord(subject)}" added to Never flag`);
    // Saved: a failed re-run is the report's failure, not the Ignore's.
    await onWordingChanged().catch((err: unknown) => toast.error(couldnt("update the report", err)));
  };

  return (
    <div ref={groupRef} tabIndex={-1} className="rounded-md border outline-none">
      <div className="flex flex-wrap items-start justify-between gap-2 border-b px-3 py-2">
        <div className="min-w-0">
          <h3 className="text-sm font-medium">Wording ({notes.length})</h3>
          <p className="text-muted-foreground text-xs">These never change your score.</p>
        </div>
        <Button size="xs" variant="link" onClick={() => setEditOpen(true)}>
          Edit word list
        </Button>
      </div>
      <ul className="divide-y">
        {/* Keyed by the text too: a re-run on changed text keeps a note's id, and its row must not
            keep the old text's "Applied" or "changed since the check". */}
        {notes.map((note) => (
          <WordingRow
            key={`${note.id}:${note.content_hash ?? ""}`}
            note={note}
            onIgnore={ignoreWord}
            {...shared}
          />
        ))}
      </ul>
      <WordListDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        onSaved={() =>
          onWordingChanged().catch((err: unknown) => toast.error(couldnt("update the report", err)))
        }
      />
    </div>
  );
}
