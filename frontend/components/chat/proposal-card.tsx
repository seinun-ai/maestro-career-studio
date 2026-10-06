"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { CardResolution } from "@/components/chat/card-resolution";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useBaseResumeName } from "@/hooks/use-base-resume-label";
import { applyResumeEdits, setChatCardState } from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt } from "@/lib/error-text";
import { notifyRenderNote } from "@/lib/render-note";
import type {
  ChatCardState,
  ChatProposal,
  UUID,
} from "@/lib/types";

const AiIcon = CONCEPT_ICONS.ai;

/**
 * Staged extraction result (upload → project bullets). Never added silently —
 * the user reviews the drafted project and adds or discards it explicitly.
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
  const baseName = useBaseResumeName(proposal.target_key, proposal.target_kind === "base");
  const [resolution, setResolution] = useState<"merged" | "discarded" | null>(
    cardState ? (cardState.status === "applied" ? "merged" : "discarded") : null,
  );

  const stamp = (status: "applied" | "discarded") => {
    if (messageId) {
      setChatCardState(messageId, status).catch(() => undefined);
    }
  };

  const merge = useMutation({
    mutationFn: () =>
      applyResumeEdits(proposal.target_kind, proposal.target_key, [
        { kind: "add_entry", section: "projects", value: proposal.project },
      ]),
    onSuccess: (result) => {
      setResolution("merged");
      stamp("applied");
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      qc.invalidateQueries({ queryKey: ["application"] });
      qc.invalidateQueries({ queryKey: ["resume-versions"] });
      notifyRenderNote(result);
      toast.success("Project added to the resume");
    },
    onError: (err: Error) => toast.error(couldnt("add the project", err)),
  });

  const targetLabel = proposal.target_kind === "base" ? baseName : "the tailored resume";

  return (
    <div className={`rounded-corner-md border border-dashed px-3 py-2${resolution ? " opacity-80" : ""}`}>
      <div className="flex items-center gap-2 text-body-medium">
        <Badge variant="outline" className="gap-1">
          <AiIcon className="size-3" aria-hidden="true" />
          Suggested project
        </Badge>
        <span className="font-medium">{proposal.project.name}</span>
        <span className="text-muted-foreground text-body-small">For {targetLabel}</span>
      </div>
      {proposal.project.tech && (
        <p className="text-muted-foreground mt-1 text-body-small">
          {proposal.project.tech}
        </p>
      )}
      <ul className="mt-2 ml-4 list-disc space-y-1 text-body-medium">
        {proposal.project.bullets.map((b, i) => (
          <li key={i}>{b}</li>
        ))}
      </ul>
      <div className="mt-2 flex justify-end gap-2">
        {resolution ? (
          <CardResolution done={resolution === "merged"} doneWord="Added" />
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
              {merge.isPending ? "Adding…" : "Add to resume"}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
