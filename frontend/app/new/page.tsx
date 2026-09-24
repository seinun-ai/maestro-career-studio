"use client";

import { useId, useState } from "react";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { GuardedLink as Link } from "@/components/guarded-link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { JobExtractionSummary } from "@/components/job-extraction-summary";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import { ingestJob } from "@/lib/ingest-job";
import { anchorHref } from "@/lib/settings-tabs";
import type { Job, SetupStatus } from "@/lib/types";
import { PageHeader, PageShell } from "@/components/page-shell";

export default function NewApplicationPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [rawText, setRawText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [savedJob, setSavedJob] = useState<Job | null>(null);

  // Extract is an LLM call: with no provider key it can only fail, so say so
  // before the paste, not after it. A failed status fetch blocks nothing:
  // `needsKey` is true only on a confirmed "not done". Same query key as the
  // setup checklist, which saving a key in Settings invalidates; refetched on
  // every mount like its other readers, so a key added any other way (.env,
  // another tab) re-enables Extract without waiting out the stale window.
  const setup = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => apiFetch<SetupStatus>("/api/setup/status"),
    refetchOnMount: "always",
  });
  const needsKey = setup.data?.model_key.done === false;
  // A disabled button says nothing about why; point it at the notice.
  const keyNoticeId = useId();

  function onRawTextChange(value: string) {
    setRawText(value);
    setSavedJob(null);
  }

  function onSourceUrlChange(value: string) {
    setSourceUrl(value);
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
  const extract = useSingleFlight(extractJob.mutate);
  useLeaveGuard(rawText.trim().length > 0 && savedJob === null);

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

      {needsKey ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-amber-500/40 bg-amber-500/[0.08] px-3 py-2 text-sm dark:border-amber-400/40 dark:bg-amber-400/[0.08]">
          <span id={keyNoticeId} className="text-amber-800 dark:text-amber-200">
            Extract reads the posting with a model, so it needs a provider API key.
          </span>
          <Button
            size="sm"
            variant="outline"
            nativeButton={false}
            render={<Link href={anchorHref("/settings", "api-keys")} />}
          >
            Add API key
          </Button>
        </div>
      ) : null}

      <div className="grid gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="raw_text">Job description</Label>
          <Textarea
            id="raw_text"
            value={rawText}
            onChange={(e) => onRawTextChange(e.target.value)}
            rows={14}
            className="font-mono text-sm"
          />
        </div>

        <div className="grid gap-1.5">
          <Label htmlFor="source_url" optional>Source URL</Label>
          <Input
            id="source_url"
            placeholder="e.g. https://boards.example.com/job/123"
            value={sourceUrl}
            onChange={(e) => onSourceUrlChange(e.target.value)}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          onClick={() => extract(undefined)}
          disabled={disabled || busy || needsKey}
          // Disables itself while extracting: a disabled <button> drops focus
          // to <body> (dimmed on data-disabled, as Save is).
          focusableWhenDisabled
          className="data-disabled:pointer-events-none data-disabled:opacity-50"
          aria-describedby={needsKey ? keyNoticeId : undefined}
        >
          {extractJob.isPending ? "Extracting…" : "Extract job"}
        </Button>
        <p className="text-muted-foreground text-sm">
          {needsKey
            ? "Add an API key to extract."
            : "The job is listed under Saved. Scoring comes next."}
        </p>
      </div>

      {savedJob && (
        <JobExtractionSummary job={savedJob} onScoreAts={goToAtsScores} />
      )}
    </PageShell>
  );
}
