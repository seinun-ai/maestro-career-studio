"use client";

import { useMemo, useState, type RefObject } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { EditWordsList } from "@/components/edit-words-list";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
import { describeEdits } from "@/lib/describe-edit";
import { couldnt } from "@/lib/error-text";
import { notifyRenderNote } from "@/lib/render-note";
import { serverKey } from "@/lib/studio";
import type { BaseResumeDetail, BaseResumeProposal, ResumeData } from "@/lib/types";

/** Starters, not a menu: each one seeds the textarea and stays editable. The
 *  first three are edits, the last two are questions — the sheet answers both
 *  shapes and the examples say so. */
const STARTERS = [
  "Shorten the summary",
  "Put the strongest bullet first",
  "Aim this at data engineering",
  "What's weakest for a senior data scientist?",
  "What other roles fit this resume?",
];

/**
 * A free instruction against the base resume: an edit ("tighten the summary")
 * comes back as typed ops the user applies in one click through the ordinary
 * PATCH /edits door; a question ("what could this pivot to?") comes back as
 * prose. Nothing changes until Apply — the same propose-then-approve shape as
 * chat's suggestion card and the KB plan step.
 */
export function InstructSheet({
  open,
  onOpenChange,
  targetSlug,
  resume,
  onApplied,
  finalFocus,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  targetSlug: string;
  /** The SERVER copy the proposal was made against and Apply will hit, never
   *  the unsaved form: its entries are what the ops' indices point at. */
  resume: ResumeData | null | undefined;
  /** The PATCHed record, so the editor adopts it instead of a stale form. */
  onApplied: (result: BaseResumeDetail) => void;
  /** Where focus returns on close (the studio's ⋯ button). */
  finalFocus?: RefObject<HTMLElement | null>;
}) {
  const qc = useQueryClient();
  const [instruction, setInstruction] = useState("");
  // Kept across close (Esc, the overlay, Close): the proposal cost a model
  // call. Its ops edit by index, so each one carries the saved copy it was
  // made against, and once the resume moves on it can be read, not applied.
  const [kept, setKept] = useState<{ result: BaseResumeProposal; basis: string } | null>(null);
  const proposal = kept?.result ?? null;
  // Serializes the whole resume: once per saved copy, not per keystroke.
  const basis = useMemo(() => serverKey(resume), [resume]);
  const stale = kept !== null && kept.basis !== basis;

  const propose = useMutation({
    mutationFn: (sent: { instruction: string; basis: string }) =>
      apiFetch<BaseResumeProposal>(`/api/base-resumes/${targetSlug}/propose`, {
        method: "POST",
        body: JSON.stringify({ instruction: sent.instruction }),
      }).then((result) => ({ result, basis: sent.basis })),
    onSuccess: setKept,
    onError: (err: Error) => toast.error(couldnt("suggest edits", err)),
  });

  const apply = useMutation({
    mutationFn: () =>
      apiFetch<BaseResumeDetail>(`/api/base-resumes/${targetSlug}/edits`, {
        method: "PATCH",
        body: JSON.stringify({ ops: proposal?.ops ?? [] }),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["base-resumes", targetSlug], result);
      void qc.invalidateQueries({ queryKey: ["base-resumes"] });
      void qc.invalidateQueries({
        queryKey: ["resume-versions", "base", targetSlug],
      });
      onApplied(result);
      notifyRenderNote(result);
      toast.success(
        `Applied ${proposal?.ops_count ?? 0} ${proposal?.ops_count === 1 ? "edit" : "edits"}. PDF updated.`,
      );
      setInstruction("");
      setKept(null);
      onOpenChange(false);
    },
    onError: (err: Error) => toast.error(couldnt("apply the edits", err)),
  });

  // One request per click: a second Apply repeated the ops (add_bullet,
  // add_entry twice), and a second Propose paid for two proposals.
  const proposeOnce = useSingleFlight(propose.mutate);
  const applyOnce = useSingleFlight(apply.mutate);
  const busy = propose.isPending || apply.isPending;
  const hasOps = (proposal?.ops_count ?? 0) > 0;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-2xl" finalFocus={finalFocus}>
        <SheetHeader>
          <SheetTitle>Ask for changes</SheetTitle>
          <p className="text-muted-foreground text-sm">
            Describe a change or ask a question. Nothing changes until you apply
            it. AI won&apos;t add facts that aren&apos;t on your resume.
          </p>
        </SheetHeader>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-2">
          <div className="grid gap-1.5">
            <Label htmlFor="instruct_text">What should change?</Label>
            <Textarea
              id="instruct_text"
              rows={4}
              value={instruction}
              readOnly={busy}
              onChange={(e) => setInstruction(e.target.value)}
            />
            <div className="flex flex-wrap gap-1.5">
              {STARTERS.map((text) => (
                <Button
                  key={text}
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-7 rounded-full text-xs"
                  disabled={busy}
                  onClick={() => setInstruction(text)}
                >
                  {text}
                </Button>
              ))}
            </div>
          </div>

          <div>
            <Button
              type="button"
              variant={proposal ? "outline" : "default"}
              size="sm"
              disabled={!instruction.trim() || busy}
              // Stays focusable while it works: a disabled button that has
              // focus drops it to the page.
              focusableWhenDisabled
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={() => proposeOnce({ instruction, basis })}
            >
              {propose.isPending ? (
                <Loader2 className="animate-spin" />
              ) : (
                <Sparkles aria-hidden />
              )}
              {propose.isPending ? "Working…" : proposal ? "Suggest again" : "Suggest edits"}
            </Button>
          </div>

          {proposal && (
            <div className="rounded-xl border border-dashed px-3 py-2.5">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Badge variant="outline" className="gap-1 text-xs">
                  <Sparkles className="size-3" aria-hidden="true" />
                  {hasOps ? `Suggested ${proposal.ops_count === 1 ? "edit" : "edits"}` : "Answer"}
                </Badge>
                {proposal.summary ? (
                  <span className="font-medium">{proposal.summary}</span>
                ) : null}
              </div>
              {proposal.notes ? (
                <p className="mt-2 text-sm whitespace-pre-wrap">{proposal.notes}</p>
              ) : null}
              {stale ? (
                <p className="text-muted-foreground mt-2 text-xs">
                  The resume changed since these edits were suggested. Suggest
                  again to get edits for this version.
                </p>
              ) : null}
              {hasOps ? (
                // A stale proposal is described without names: its indices
                // point into a copy the resume no longer is.
                <EditWordsList edits={describeEdits(proposal.ops, stale ? null : resume)} />
              ) : (
                <p className="text-muted-foreground mt-2 text-xs">
                  No edits suggested. Ask for a change in those words if you
                  want one made.
                </p>
              )}
            </div>
          )}
        </div>

        <SheetFooter className="border-t px-4 py-3">
          <SheetClose render={<Button variant="ghost">Close</Button>} />
          {proposal && hasOps && (
            <>
              <Button variant="outline" disabled={busy} onClick={() => setKept(null)}>
                Discard
              </Button>
              <Button
                disabled={busy || stale}
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={() => applyOnce()}
              >
                {apply.isPending
                  ? "Applying…"
                  : `Apply ${proposal.ops_count} ${proposal.ops_count === 1 ? "edit" : "edits"}`}
              </Button>
            </>
          )}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
