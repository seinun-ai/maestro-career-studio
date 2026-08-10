"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileDiff, RotateCcw } from "lucide-react";
import { toast } from "sonner";

import { VersionDiffView } from "@/components/resume-versions/version-diff-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { restoreResumeVersion } from "@/lib/api";
import { baseResumeLabel } from "@/lib/types";
import type { ChatChangeCard } from "@/lib/types";

/** Rendered in the transcript for every mutating tool call ("footprint"). */
export function ChangeCard({ card }: { card: ChatChangeCard }) {
  const qc = useQueryClient();
  const [diffOpen, setDiffOpen] = useState(false);

  const revert = useMutation({
    mutationFn: () =>
      restoreResumeVersion(
        card.resume_kind,
        card.resume_key,
        card.version_number - 1,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["resume-versions"] });
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      qc.invalidateQueries({ queryKey: ["application"] });
      toast.success("Reverted. The previous content is current again.");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const targetLabel =
    card.resume_kind === "base"
      ? baseResumeLabel(card.resume_key)
      : "tailored resume";

  return (
    <div className="border-primary/30 bg-primary/5 rounded-md border px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm">
          <Badge variant="secondary" className="text-xs">
            Edited
          </Badge>
          <span className="font-medium">{targetLabel}</span>
          <span className="text-muted-foreground text-xs">
            v{card.version_number} · {card.ops_count}{" "}
            {card.ops_count === 1 ? "change" : "changes"}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => setDiffOpen(true)}>
            <FileDiff className="mr-1 size-3.5" /> Diff
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={card.version_number <= 1 || revert.isPending}
            onClick={() => revert.mutate()}
          >
            <RotateCcw className="mr-1 size-3.5" />
            {revert.isPending ? "Reverting…" : "Revert"}
          </Button>
        </div>
      </div>
      {card.summary && (
        <p className="text-muted-foreground mt-1 text-xs">{card.summary}</p>
      )}
      <Dialog open={diffOpen} onOpenChange={setDiffOpen}>
        <DialogContent className="flex max-h-[80vh] w-[min(92vw,34rem)] max-w-[min(92vw,34rem)] flex-col overflow-hidden">
          <DialogHeader>
            <DialogTitle>
              Changes in v{card.version_number} · {targetLabel}
            </DialogTitle>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-y-auto pr-1">
            <VersionDiffView
              kind={card.resume_kind}
              resumeKey={card.resume_key}
              version={card.version_number}
            />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
