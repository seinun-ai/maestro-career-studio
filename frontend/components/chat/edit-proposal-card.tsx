"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { toast } from "sonner";

import { EditWordsList } from "@/components/edit-words-list";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiFetch, applyResumeEdits, setChatCardState } from "@/lib/api";
import { describeEdits, type EditWords, type ResumeLike } from "@/lib/describe-edit";
import { useBaseResumeLabel } from "@/hooks/use-base-resume-label";
import { notifyRenderNote } from "@/lib/render-note";
import type {
  ApplicationDetail,
  BaseResumeDetail,
  ChatCardState,
  ChatProposalOps,
  UUID,
} from "@/lib/types";

/**
 * Staged edit ops from propose_edits: the user approves the suggestion as one
 * click. Resolution is persisted via the card-state endpoint so reloads render
 * this card as resolved instead of re-offering it.
 */
export function EditProposalCard({
  proposal,
  messageId,
  cardState,
  onApplied,
}: {
  proposal: ChatProposalOps;
  messageId?: UUID;
  cardState?: ChatCardState;
  /** Fired once the ops actually land, so the composer can follow the resume
   *  this proposal targeted. Applying PATCHes directly and emits no change
   *  card, so there is no stream event to observe it by. */
  onApplied?: (kind: ChatProposalOps["target_kind"], key: string) => void;
}) {
  const qc = useQueryClient();
  const baseName = useBaseResumeLabel();
  const [resolution, setResolution] = useState<"applied" | "discarded" | null>(
    cardState?.status ?? null,
  );
  const pending = resolution === null;
  // The document Apply will hit. Same keys the studios and chat's pinned-resume
  // query use, so an open chat usually has it cached.
  const base = useQuery({
    queryKey: ["base-resumes", proposal.target_key],
    queryFn: () => apiFetch<BaseResumeDetail>(`/api/base-resumes/${proposal.target_key}`),
    enabled: pending && proposal.target_kind === "base",
  });
  const app = useQuery({
    queryKey: ["application", proposal.target_key],
    queryFn: () => apiFetch<ApplicationDetail>(`/api/applications/${proposal.target_key}`),
    enabled: pending && proposal.target_kind === "application",
  });
  // customized_json is an untyped record; the describer only reads known fields.
  const doc = (
    proposal.target_kind === "base" ? base.data?.data : app.data?.customized_json
  ) as ResumeLike | null | undefined;
  // Words freeze when the card resolves: after Apply the document has moved, and
  // a remove_entry's index would name the NEXT entry. After a reload there is no
  // frozen copy, so a resolved card describes without names (never wrong ones).
  const [frozen, setFrozen] = useState<EditWords[] | null>(null);
  const edits = frozen ?? describeEdits(proposal.ops, pending ? doc : null);

  const stamp = (status: "applied" | "discarded") => {
    if (messageId) {
      // Best-effort: the apply already succeeded; a stamp failure only means
      // the card renders as actionable again after reload.
      setChatCardState(messageId, status).catch(() => undefined);
    }
  };

  const apply = useMutation({
    mutationFn: () =>
      applyResumeEdits(proposal.target_kind, proposal.target_key, proposal.ops),
    onMutate: () => setFrozen(describeEdits(proposal.ops, doc)),
    onSuccess: (result) => {
      setResolution("applied");
      stamp("applied");
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      qc.invalidateQueries({ queryKey: ["application"] });
      qc.invalidateQueries({ queryKey: ["resume-versions"] });
      onApplied?.(proposal.target_kind, proposal.target_key);
      notifyRenderNote(result);
      toast.success("Suggestion applied to the resume");
    },
    onError: (err: Error) => {
      setFrozen(null);
      toast.error(err.message);
    },
  });

  const targetLabel =
    proposal.target_kind === "base"
      ? base.data?.display_name?.trim() || baseName(proposal.target_key)
      : "tailored resume";

  return (
    <div className="rounded-xl border border-dashed px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="outline" className="gap-1 text-xs">
          <Sparkles className="size-3" aria-hidden="true" /> Suggested edit
        </Badge>
        {proposal.summary ? (
          <span className="font-medium">{proposal.summary}</span>
        ) : null}
        <span className="text-muted-foreground text-xs">→ {targetLabel}</span>
      </div>
      <EditWordsList edits={edits} />
      <div className="mt-2 flex justify-end gap-2">
        {resolution ? (
          <span className="text-muted-foreground text-xs">
            {resolution === "applied" ? "Applied" : "Discarded"}
          </span>
        ) : (
          <>
            <Button
              variant="ghost"
              size="sm"
              className="rounded-full"
              onClick={() => {
                setFrozen(edits);
                setResolution("discarded");
                stamp("discarded");
              }}
            >
              Discard
            </Button>
            <Button
              size="sm"
              className="rounded-full px-4"
              disabled={apply.isPending}
              onClick={() => apply.mutate()}
            >
              {apply.isPending
                ? "Applying…"
                : `Apply ${proposal.ops_count} ${proposal.ops_count === 1 ? "edit" : "edits"}`}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
