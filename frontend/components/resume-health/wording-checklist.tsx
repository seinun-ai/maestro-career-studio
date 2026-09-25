"use client";

import { useLayoutEffect, useRef, useState, type RefObject } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { DiffText, SourceQuote, SuggestionCopyOnly } from "@/components/resume-health/judged-text";
import { WordListDialog, WORDING_QUERY_KEY } from "@/components/resume-health/word-list-dialog";
import { Button } from "@/components/ui/button";
import { focusIfDropped, useFocusOnNextCommit } from "@/hooks/use-focus-return";
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
  wordingBusy,
}: Shared & {
  note: LintFinding;
  onIgnore: (subject: string) => Promise<void>;
  /** A word list change (an Ignore anywhere in the group, a Save) is still saving and re-running. */
  wordingBusy: boolean;
}) {
  const rowRef = useRef<HTMLLIElement>(null);
  useSuccessorOnLeave(rowRef);
  const [applied, setApplied] = useState(false);
  const [changed, setChanged] = useState(false);
  // Apply and Remove leave with their button: "Applied" or "Removed" takes the focus.
  const appliedRef = useRef<HTMLParagraphElement>(null);
  const focusNext = useFocusOnNextCommit();
  const slip = note.rule === "language.slip";
  const fix = slip ? slipFix(note) : null;
  const thing = note.location.section === "summary" ? "summary" : "bullet";
  const currentText = data ? textAtLocation(data, note) : null;
  const op = data ? wordingEditOp(note) : null;
  const otherSection = note.location.section.startsWith("extra:");
  // An Other section has no edit op: its guarded wording is the one diff, shown to copy.
  const copyOnly = otherSection && note.suggestion != null && currentText != null;
  const word = note.subject ?? "";

  const apply = useMutation({
    mutationFn: (edit: LintEditOp) => applyResumeEdits(kind, resumeKey, [edit]),
    onMutate: () => setChanged(false),
    onSuccess: (result) => {
      setApplied(true);
      focusNext(appliedRef);
      notifyRenderNote(result);
      toast.success(slip ? "Applied and saved as a new version" : "Removed and saved as a new version");
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
    mutationFn: () => onIgnore(word),
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
          {fix != null && !copyOnly ? (
            <>
              {/* The fix as a word diff; its sentence is what a screen reader hears. */}
              <div aria-hidden>
                <DiffText oldText={word} newText={fix} />
              </div>
              <p className="sr-only">{note.issue}</p>
            </>
          ) : (
            <p className="text-foreground max-w-[65ch] text-sm">{note.issue}</p>
          )}
        </div>
        {/* Nothing to act on until the resume text has loaded. */}
        {data && (
          <div className="ml-auto flex shrink-0 items-center gap-1">
            {applied ? (
              <p ref={appliedRef} tabIndex={-1} className="text-muted-foreground px-2 text-xs outline-none">
                {slip ? "Applied" : "Removed"}
              </p>
            ) : (
              op && (
                <Button
                  size="xs"
                  variant="link"
                  data-wording-action
                  aria-label={slip ? `Apply fix to "${word}"` : `Remove "${word}"`}
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
                aria-label={`Ignore "${word}"`}
                disabled={busy || wordingBusy}
                focusableWhenDisabled
                className="text-muted-foreground hover:text-foreground data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={() => ignoreOnce()}
              >
                {ignore.isPending ? "Ignoring…" : "Ignore"}
              </Button>
            )}
          </div>
        )}
      </div>
      {data && !op && !applied &&
        (copyOnly && currentText != null && note.suggestion != null ? (
          <SuggestionCopyOnly currentText={currentText} suggestion={note.suggestion} />
        ) : note.rule === "language.cliche" ? (
          // A cliché is rewritten by hand, by design (no suggestion): its own advice, not a limit.
          <p className="text-muted-foreground max-w-[65ch] text-xs">{note.how}</p>
        ) : (
          // A fix the rewrite guards refused is left to the user.
          <p className="text-muted-foreground max-w-[65ch] text-xs">
            {slip ? (
              <>Can&apos;t apply this fix here. Correct it in the resume.</>
            ) : (
              <>Can&apos;t remove it here. Edit the {thing} in the resume.</>
            )}
          </p>
        ))}
      {changed && (
        <p role="alert" className="text-destructive max-w-[65ch] text-xs">
          This {thing} changed since the check.{" "}
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
 * from the user's word list. Zero score, never blocking. Always shown with a report, so Edit word
 * list is reachable with no hits. Self-contained so the report's layout can move it; the Notes
 * disclosure renders it today.
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
  // One word list change at a time, from its GET through its re-run: two Ignores would each PUT the
  // lists they read, and the later PUT would drop the earlier word. The ref shuts the gate inside the
  // first click (a second row's click can land before the re-render); the state disables the rest.
  const changing = useRef(false);
  const [wordingBusy, setWordingBusy] = useState(false);
  const exclusive = async (change: () => Promise<void>) => {
    if (changing.current) return;
    changing.current = true;
    setWordingBusy(true);
    try {
      await change();
    } finally {
      changing.current = false;
      setWordingBusy(false);
    }
  };
  // A failed re-run is the report's failure, not the word list's: the lists are already saved.
  const rerun = async () => {
    try {
      await onWordingChanged();
    } catch (err) {
      toast.error(couldnt("update the report", err));
    }
  };

  // Never flag gets the word on top of the lists as they are now (the PUT replaces all three).
  const ignoreWord = (subject: string) =>
    exclusive(async () => {
      const current = await getWording();
      const saved = await putWording(withIgnored(current, subject));
      qc.setQueryData(WORDING_QUERY_KEY, saved);
      toast.success(`"${normalizeWord(subject)}" added to Never flag`);
      await rerun();
    });

  return (
    // The rows' landmark: a row leaving with no neighbour that can take focus lands on the group.
    <div tabIndex={-1} className="rounded-md border outline-none">
      <div className="flex flex-wrap items-start justify-between gap-2 border-b px-3 py-2">
        <div className="min-w-0">
          <h3 className="text-sm font-medium">Wording ({notes.length})</h3>
          <p className="text-muted-foreground text-xs">These never change your score.</p>
        </div>
        <Button size="xs" variant="link" onClick={() => setEditOpen(true)}>
          Edit word list
        </Button>
      </div>
      {notes.length === 0 ? (
        <p className="text-muted-foreground px-3 py-2 text-sm">No wording issues.</p>
      ) : (
        <ul className="divide-y">
          {/* Keyed by the text too: a re-run on changed text keeps a note's id, and its row must not
              keep the old text's "Applied" or "changed since the check". */}
          {notes.map((note) => (
            <WordingRow
              key={`${note.id}:${note.content_hash ?? ""}`}
              note={note}
              onIgnore={ignoreWord}
              wordingBusy={wordingBusy}
              {...shared}
            />
          ))}
        </ul>
      )}
      <WordListDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        busy={wordingBusy}
        onSaved={() => void exclusive(() => rerun())}
      />
    </div>
  );
}
