"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import type {
  BaseResumePortProjectResult,
  BaseResumeSummary,
} from "@/lib/types";
import { baseResumeLabel } from "@/lib/types";

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

  const resumes = useQuery({
    queryKey: ["base-resumes"],
    queryFn: () => apiFetch<BaseResumeSummary[]>("/api/base-resumes"),
    enabled: open,
  });

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
      toast.success(
        `Copied to ${baseResumeLabel(result.target_slug)} as archived`,
      );
      qc.invalidateQueries({ queryKey: ["base-resumes", result.target_slug] });
      onOpenChange(false);
      setTargetSlug("");
    },
    onError: (err: Error) => toast.error(err.message),
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
          <DialogTitle>Port project</DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-sm">
          Copy <strong>{projectName || "this project"}</strong> to another base
          resume. It will be added as <strong>archived</strong> (disabled) so you
          can enable and edit it there later.
        </p>
        <div className="grid gap-1.5">
          <Label htmlFor="port_target">Target base resume</Label>
          <Select
            value={targetSlug}
            onValueChange={(v) => setTargetSlug(v ?? "")}
            disabled={targets.length === 0}
          >
            <SelectTrigger id="port_target" className="w-full">
              {/* A placeholder only covers the EMPTY state — once a slug is
                  picked, a childless SelectValue renders the raw value, so
                  this trigger showed `data_engineer`. */}
              <SelectValue placeholder="Choose base resume">
                {(value) => {
                  const hit = targets.find((r) => r.slug === value);
                  return hit
                    ? (hit.display_name ?? baseResumeLabel(hit.slug))
                    : baseResumeLabel(String(value ?? ""));
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
            {port.isPending ? "Porting…" : "Port"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
