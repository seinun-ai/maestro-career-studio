"use client";

import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import type { Job } from "@/lib/types";

function normalizeUrl(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function JobTrackingUrlField({
  jobId,
  sourceUrl,
  queryKeys = [["job-detail", jobId], ["jobs"]],
  id = "job-tracking-url",
  label = "Application URL",
  description = "Job posting or employer portal. Open it to check status.",
}: {
  jobId: string;
  sourceUrl: string | null;
  queryKeys?: string[][];
  id?: string;
  label?: string;
  description?: string;
}) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState(sourceUrl ?? "");
  // Re-sync the draft when the server value changes (adjust-state-during-render
  // pattern; avoids the setState-in-effect cascading-render lint error).
  const [prevSourceUrl, setPrevSourceUrl] = useState(sourceUrl);
  if (prevSourceUrl !== sourceUrl) {
    setPrevSourceUrl(sourceUrl);
    setDraft(sourceUrl ?? "");
  }

  const patch = useMutation({
    mutationFn: (url: string | null) =>
      apiFetch<Job>(`/api/jobs/${jobId}`, {
        method: "PATCH",
        body: JSON.stringify({ source_url: url }),
      }),
    onSuccess: () => {
      for (const key of queryKeys) {
        qc.invalidateQueries({ queryKey: key });
      }
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const save = () => {
    const next = normalizeUrl(draft);
    const prev = sourceUrl ?? null;
    if (next === prev) return;
    patch.mutate(next);
  };

  const href = sourceUrl?.trim();

  return (
    <div className="grid gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id} className="text-xs">
          {label}
        </Label>
        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
          >
            Open
            <ExternalLink className="size-3" />
          </a>
        ) : null}
      </div>
      <Input
        id={id}
        type="url"
        placeholder="https://…"
        className="h-8 text-sm"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={save}
        disabled={patch.isPending}
      />
      {description ? (
        <p className="text-muted-foreground text-xs">{description}</p>
      ) : null}
    </div>
  );
}
