"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { describeOp } from "@/components/chat/edit-proposal-card";
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
import { apiFetch } from "@/lib/api";
import type { BaseResumeDetail, BaseResumeProposal } from "@/lib/types";

/** Starters, not a menu: each one seeds the textarea and stays editable. The
 *  first three are edits, the last two are questions — the sheet answers both
 *  shapes and the examples say so. */
const STARTERS = [
  "Tighten the summary to two sentences",
  "Lead each role with its highest-impact bullet",
  "Reposition this toward data engineering",
  "Which areas are weakest for a senior data scientist target?",
  "What roles could this resume pivot to?",
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
  onApplied,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  targetSlug: string;
  /** The PATCHed record, so the editor adopts it instead of a stale form. */
  onApplied: (result: BaseResumeDetail) => void;
}) {
  const qc = useQueryClient();
  const [instruction, setInstruction] = useState("");
  const [proposal, setProposal] = useState<BaseResumeProposal | null>(null);

  const reset = () => {
    setInstruction("");
    setProposal(null);
  };
  const handleOpenChange = (next: boolean) => {
    onOpenChange(next);
    if (!next) reset();
  };

  const propose = useMutation({
    mutationFn: () =>
      apiFetch<BaseResumeProposal>(`/api/base-resumes/${targetSlug}/propose`, {
        method: "POST",
        body: JSON.stringify({ instruction }),
      }),
    onSuccess: setProposal,
    onError: (err: Error) => toast.error(err.message),
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
      toast.success(
        `Applied ${proposal?.ops_count ?? 0} ${proposal?.ops_count === 1 ? "edit" : "edits"}. PDF re-rendered.`,
      );
      handleOpenChange(false);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const busy = propose.isPending || apply.isPending;
  const hasOps = (proposal?.ops_count ?? 0) > 0;

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>Ask for changes</SheetTitle>
          <p className="text-muted-foreground text-sm">
            Describe an edit, or ask for ideas. Nothing changes until you apply
            a proposal, and the model may not invent facts that are not on the
            resume.
          </p>
        </SheetHeader>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-2">
          <div className="grid gap-1.5">
            <Label htmlFor="instruct_text">Instruction</Label>
            <Textarea
              id="instruct_text"
              rows={4}
              placeholder="e.g. Tighten the summary and lead with the platform work"
              value={instruction}
              disabled={busy}
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
              onClick={() => propose.mutate()}
            >
              {propose.isPending ? (
                <Loader2 className="animate-spin" />
              ) : (
                <Sparkles aria-hidden />
              )}
              {propose.isPending ? "Thinking…" : proposal ? "Propose again" : "Propose"}
            </Button>
          </div>

          {proposal && (
            <div className="rounded-xl border border-dashed px-3 py-2.5">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Badge variant="outline" className="gap-1 text-xs">
                  <Sparkles className="size-3" aria-hidden="true" />
                  {hasOps ? "Suggested edit" : "Answer"}
                </Badge>
                {proposal.summary ? (
                  <span className="font-medium">{proposal.summary}</span>
                ) : null}
              </div>
              {proposal.notes ? (
                <p className="mt-2 text-sm whitespace-pre-wrap">{proposal.notes}</p>
              ) : null}
              {hasOps ? (
                <ul className="text-muted-foreground mt-2 space-y-1 text-xs">
                  {proposal.ops.map((op, i) => (
                    <li key={i} className="truncate font-mono">
                      {describeOp(op)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground mt-2 text-xs">
                  No edits proposed. Ask for a change in those words if you
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
              <Button variant="outline" disabled={busy} onClick={() => setProposal(null)}>
                Discard
              </Button>
              <Button disabled={busy} onClick={() => apply.mutate()}>
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
