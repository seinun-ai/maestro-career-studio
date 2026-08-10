"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiFetch, setChatCardState } from "@/lib/api";
import { baseResumeLabel } from "@/lib/types";
import type { ChatCardState, ChatProposal, UUID } from "@/lib/types";

/**
 * Staged extraction result (upload → project points). Never merged silently —
 * the user reviews the drafted entry and merges or discards it explicitly.
 * Resolution persists via the card-state endpoint so reloads don't re-offer it.
 */
export function ProposalCard({
  proposal,
  messageId,
  cardState,
}: {
  proposal: ChatProposal;
  messageId?: UUID;
  cardState?: ChatCardState;
}) {
  const qc = useQueryClient();
  const [resolution, setResolution] = useState<"merged" | "discarded" | null>(
    cardState ? (cardState.status === "applied" ? "merged" : "discarded") : null,
  );

  const stamp = (status: "applied" | "discarded") => {
    if (messageId) {
      setChatCardState(messageId, status).catch(() => undefined);
    }
  };

  const merge = useMutation({
    mutationFn: () => {
      const path =
        proposal.target_kind === "base"
          ? `/api/base-resumes/${proposal.target_key}/edits`
          : `/api/applications/${proposal.target_key}/edits`;
      return apiFetch(path, {
        method: "PATCH",
        body: JSON.stringify({
          ops: [{ kind: "add_entry", section: "projects", value: proposal.project }],
        }),
      });
    },
    onSuccess: () => {
      setResolution("merged");
      stamp("applied");
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      qc.invalidateQueries({ queryKey: ["application"] });
      qc.invalidateQueries({ queryKey: ["resume-versions"] });
      toast.success("Project merged into the resume");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const targetLabel =
    proposal.target_kind === "base"
      ? baseResumeLabel(proposal.target_key)
      : "tailored resume";

  return (
    <div className="rounded-md border border-dashed px-3 py-2">
      <div className="flex items-center gap-2 text-sm">
        <Badge variant="outline" className="text-xs">
          Proposed project
        </Badge>
        <span className="font-medium">{proposal.project.name}</span>
        <span className="text-muted-foreground text-xs">→ {targetLabel}</span>
      </div>
      {proposal.project.tech && (
        <p className="text-muted-foreground mt-1 text-xs">
          {proposal.project.tech}
        </p>
      )}
      <ul className="mt-2 ml-4 list-disc space-y-1 text-sm">
        {proposal.project.bullets.map((b, i) => (
          <li key={i}>{b}</li>
        ))}
      </ul>
      <div className="mt-2 flex justify-end gap-2">
        {resolution ? (
          <span className="text-muted-foreground text-xs">
            {resolution === "merged" ? "Merged" : "Discarded"}
          </span>
        ) : (
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setResolution("discarded");
                stamp("discarded");
              }}
            >
              Discard
            </Button>
            <Button
              size="sm"
              disabled={merge.isPending}
              onClick={() => merge.mutate()}
            >
              {merge.isPending ? "Merging…" : "Merge into resume"}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
