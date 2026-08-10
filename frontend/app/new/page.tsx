"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { JobExtractionSummary } from "@/components/job-extraction-summary";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ingestJob } from "@/lib/ingest-job";
import type { Job } from "@/lib/types";
import { PageHeader, PageShell } from "@/components/page-shell";

export default function NewApplicationPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [rawText, setRawText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [savedJob, setSavedJob] = useState<Job | null>(null);

  function onRawTextChange(value: string) {
    setRawText(value);
    setSavedJob(null);
  }

  async function ensureJob(): Promise<Job> {
    if (savedJob) return savedJob;
    const job = await ingestJob({
      raw_text: rawText,
      source_url: sourceUrl || null,
    });
    setSavedJob(job);
    return job;
  }

  const extractJob = useMutation({
    mutationFn: ensureJob,
    onSuccess: (job) => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["applications"] });
      if (job.already_existed) {
        toast.info("Already tracked. This job matches one you saved earlier.");
      } else {
        toast.success("Job extracted. Listed under Saved.");
      }
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const goToAtsScores = () => {
    if (savedJob) router.push(`/jobs/${savedJob.id}?tab=fit`);
  };

  const disabled = rawText.trim().length === 0;
  const busy = extractJob.isPending;

  return (
    <PageShell>
      <PageHeader
        title="New application"
        subtitle="Paste a job description to get started."
      />

      <div className="grid gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="raw_text">Job description</Label>
          <Textarea
            id="raw_text"
            placeholder="Paste the full job description here…"
            value={rawText}
            onChange={(e) => onRawTextChange(e.target.value)}
            rows={14}
            className="font-mono text-sm"
          />
        </div>

        <div className="grid gap-1.5">
          <Label htmlFor="source_url">
            Source URL{" "}
            <span className="text-muted-foreground font-normal">· optional</span>
          </Label>
          <Input
            id="source_url"
            placeholder="https://boards.example.com/job/123"
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <Button
          onClick={() => extractJob.mutate()}
          disabled={disabled || busy}
        >
          {extractJob.isPending ? "Extracting…" : "Extract job"}
        </Button>
      </div>

      {savedJob && (
        <JobExtractionSummary job={savedJob} onScoreAts={goToAtsScores} />
      )}
    </PageShell>
  );
}
