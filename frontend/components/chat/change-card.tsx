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
import { useBaseResumeName } from "@/hooks/use-base-resume-label";
import { restoreResumeVersion } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { notifyRenderNote } from "@/lib/render-note";
import type { ChatChangeCard } from "@/lib/types";

/** Rendered in the transcript for every mutating tool call ("footprint"). */
export function ChangeCard({ card }: { card: ChatChangeCard }) {
  const qc = useQueryClient();
  const baseName = useBaseResumeName(card.resume_key, card.resume_kind === "base");
  const [diffOpen, setDiffOpen] = useState(false);

  const revert = useMutation({
    mutationFn: () =>
      restoreResumeVersion(
        card.resume_kind,
        card.resume_key,
        card.version_number - 1,
      ),
    onSuccess: (restored) => {
      qc.invalidateQueries({ queryKey: ["resume-versions"] });
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      qc.invalidateQueries({ queryKey: ["application"] });
      notifyRenderNote(restored);
      toast.success("Undone. The previous version is back.");
    },
    onError: (err: Error) => toast.error(couldnt("undo the edit", err)),
  });

  // The card carries only the application's id, no job words, so a tailored
  // target stays "tailored resume" here.
  const targetLabel = card.resume_kind === "base" ? baseName : "tailored resume";

  return (
    <div className="border-primary/30 bg-primary/5 rounded-md border px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm">
          <Badge variant="secondary" className="text-xs">
            Edited
          </Badge>
          <span className="font-medium">{targetLabel}</span>
          <span className="text-muted-foreground text-xs">
            Version {card.version_number}, {card.ops_count}{" "}
            {card.ops_count === 1 ? "change" : "changes"}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => setDiffOpen(true)}>
            <FileDiff className="mr-1 size-3.5" /> See changes
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={card.version_number <= 1 || revert.isPending}
            onClick={() => revert.mutate()}
          >
            <RotateCcw className="mr-1 size-3.5" />
            {revert.isPending ? "Undoing…" : "Undo"}
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
              Changes in version {card.version_number} of{" "}
              {card.resume_kind === "base" ? baseName : "the tailored resume"}
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
