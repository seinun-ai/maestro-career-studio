"use client";

import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { useBaseResumes } from "@/hooks/use-base-resume-label";
import { notifyRenderOutcome } from "@/lib/render-note";
import { baseResumeLabel, type BaseResumePortProjectResult } from "@/lib/types";

export function ProjectPortDialog({
  open,
  onOpenChange,
  sourceSlug,
  projectIndex,
  projectName,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sourceSlug: string;
  projectIndex: number;
  projectName: string;
}) {
  const qc = useQueryClient();
  const [targetSlug, setTargetSlug] = useState("");

  const resumes = useBaseResumes();

  const targets = useMemo(
    () => (resumes.data ?? []).filter((r) => r.slug !== sourceSlug),
    [resumes.data, sourceSlug],
  );

  const port = useMutation({
    mutationFn: () =>
      apiFetch<BaseResumePortProjectResult>(
        `/api/base-resumes/${sourceSlug}/port-project`,
        {
          method: "POST",
          body: JSON.stringify({
            target_slug: targetSlug,
            project_index: projectIndex,
          }),
        },
      ),
    onSuccess: (result) => {
      // The port is committed before the target re-renders, so a render
      // failure comes back beside the success, not instead of it.
      notifyRenderOutcome(result, {
        staleLabel: baseResumeLabel(result.target_slug, resumes.data),
      });
      toast.success(
        `Copied to ${baseResumeLabel(result.target_slug, resumes.data)}. It's hidden there until you show it.`,
      );
      qc.invalidateQueries({ queryKey: ["base-resumes", result.target_slug] });
      onOpenChange(false);
      setTargetSlug("");
    },
    onError: (err: Error) => toast.error(couldnt("copy the project", err)),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) setTargetSlug("");
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Copy project to another resume</DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-sm">
          <strong>{projectName || "This project"}</strong> is added hidden, so
          you can check it before showing it.
        </p>
        <div className="grid gap-1.5">
          <Label htmlFor="port_target">Copy to</Label>
          <Select
            value={targetSlug}
            onValueChange={(v) => setTargetSlug(v ?? "")}
            disabled={targets.length === 0}
          >
            <SelectTrigger id="port_target" className="w-full">
              {/* A placeholder only covers the EMPTY state — once a slug is
                  picked, a childless SelectValue renders the raw value, so
                  this trigger showed `data_engineer`. */}
              <SelectValue placeholder="Choose a resume">
                {(value) => {
                  const hit = targets.find((r) => r.slug === value);
                  return hit
                    ? (hit.display_name ?? baseResumeLabel(hit.slug))
                    : baseResumeLabel(String(value ?? ""), resumes.data);
                }}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {targets.map((r) => (
                <SelectItem key={r.slug} value={r.slug}>
                  {r.display_name ?? baseResumeLabel(r.slug)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {targets.length === 0 && (
            <p className="text-muted-foreground text-xs">
              No other base resumes available.
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => port.mutate()}
            disabled={!targetSlug || port.isPending}
          >
            {port.isPending ? "Copying…" : "Copy"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
