"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiFetch, setChatCardState } from "@/lib/api";
import { baseResumeLabel } from "@/lib/types";
import type { ChatCardState, ChatProposalOps, UUID } from "@/lib/types";

/** One line per op: "replace_bullet · experience[0].bullets[1] — “new text…”".
 *  Shared with the base-resume instruction sheet, which renders the same op
 *  vocabulary for the same one-click apply. */
export function describeOp(op: Record<string, unknown>): string {
  const kind = String(op.kind ?? "?");
  let path = "";
  if (op.section != null) {
    path = String(op.section);
    if (op.index != null) path += `[${op.index}]`;
    if (op.bullet_index != null) path += `.bullets[${op.bullet_index}]`;
  } else if (op.section_key != null) {
    path = String(op.section_key);
  } else if (op.category != null) {
    path = `skills · ${op.category}`;
  }
  const value = op.value ?? op.text ?? op.item ?? op.items;
  let preview = "";
  if (typeof value === "string") {
    preview = value.length > 90 ? `${value.slice(0, 90)}…` : value;
  } else if (Array.isArray(value)) {
    preview = value.filter((v) => typeof v === "string").join(" · ").slice(0, 90);
  }
  return [kind, path, preview && `“${preview}”`].filter(Boolean).join(" · ");
}

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
  const [resolution, setResolution] = useState<"applied" | "discarded" | null>(
    cardState?.status ?? null,
  );

  const stamp = (status: "applied" | "discarded") => {
    if (messageId) {
      // Best-effort: the apply already succeeded; a stamp failure only means
      // the card renders as actionable again after reload.
      setChatCardState(messageId, status).catch(() => undefined);
    }
  };

  const apply = useMutation({
    mutationFn: () => {
      const path =
        proposal.target_kind === "base"
          ? `/api/base-resumes/${proposal.target_key}/edits`
          : `/api/applications/${proposal.target_key}/edits`;
      return apiFetch(path, {
        method: "PATCH",
        body: JSON.stringify({ ops: proposal.ops }),
      });
    },
    onSuccess: () => {
      setResolution("applied");
      stamp("applied");
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      qc.invalidateQueries({ queryKey: ["application"] });
      qc.invalidateQueries({ queryKey: ["resume-versions"] });
      onApplied?.(proposal.target_kind, proposal.target_key);
      toast.success("Suggestion applied to the resume");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const targetLabel =
    proposal.target_kind === "base"
      ? baseResumeLabel(proposal.target_key)
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
      <ul className="text-muted-foreground mt-2 space-y-1 text-xs">
        {proposal.ops.map((op, i) => (
          <li key={i} className="truncate font-mono">
            {describeOp(op)}
          </li>
        ))}
      </ul>
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
