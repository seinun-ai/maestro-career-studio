"use client";

import { use, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Pencil,
  RefreshCw,
  SendHorizontal,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";

import {
  ApplicationDetailsMenu,
  OutputTab,
  useApplicationMutations,
} from "@/components/application-panel";
import { LoadErrorState } from "@/components/load-error-state";
import { QATab } from "@/components/qa-tab";
import { AtsScorePanel } from "@/components/ats-score-panel";
import { CompanyMonogram } from "@/components/company-monogram";
import { IconButton } from "@/components/icon-button";
import {
  JobExtractedFields,
  formatSalary,
} from "@/components/job-extracted-fields";
import { JobTrackingUrlField } from "@/components/job-tracking-url-field";
import { ProposalAgentPanel } from "@/components/proposals/proposal-agent-panel";
import {
  STATUS_BADGE_CLASS,
  STATUS_LABELS,
} from "@/components/proposals/proposals-section";
import {
  DeclineDialog,
  useProposalActions,
} from "@/components/proposals/triage-actions";
import { SavedJobChip, StatusChip } from "@/components/status-chip";
import { useConfirm } from "@/components/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiFetch, promoteJobToAgentQueue } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Job, JobDetail, ProposalStatus } from "@/lib/types";

// Tab values stay jd/fit/output/qa for deep-link compat (?tab=fit, ?tab=output).
const JOB_TABS = ["jd", "fit", "output", "qa"] as const;

function JobTabsList({ hasApp }: { hasApp: boolean }) {
  return (
    <TabsList>
      <TabsTrigger value="jd">Overview</TabsTrigger>
      <TabsTrigger value="fit">Score &amp; Tailor</TabsTrigger>
      <TabsTrigger value="output" disabled={!hasApp}>
        Resume
      </TabsTrigger>
      <TabsTrigger value="qa" disabled={!hasApp}>
        Q&amp;A
      </TabsTrigger>
    </TabsList>
  );
}

function readSequence(key: string): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = sessionStorage.getItem(key);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((v): v is string => typeof v === "string")
      : [];
  } catch {
    return [];
  }
}

export default function JobDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tab?: string | string[]; from?: string | string[] }>;
}) {
  const { id } = use(params);
  const resolvedSearch = use(searchParams);
  const { tab: tabParam } = resolvedSearch;
  const fromRaw = resolvedSearch.from;
  const fromParam = Array.isArray(fromRaw) ? fromRaw[0] : fromRaw;
  const fromProposals = fromParam === "proposals";
  // `?tab=fit` deep-links (e.g. from the gap-analysis page after tailoring).
  const requestedTab = Array.isArray(tabParam) ? tabParam[0] : tabParam;
  const [tab, setTab] = useState<string>(
    requestedTab && (JOB_TABS as readonly string[]).includes(requestedTab)
      ? requestedTab
      : "jd",
  );
  const [declineOpen, setDeclineOpen] = useState(false);
  const qc = useQueryClient();
  const router = useRouter();
  const confirm = useConfirm();
  const proposalActions = useProposalActions();

  const { data, isLoading, isError, error, isFetching, refetch } = useQuery({
    queryKey: ["job-detail", id],
    queryFn: () => apiFetch<JobDetail>(`/api/jobs/${id}/detail`),
  });

  const application = data?.application ?? null;
  const { patch } = useApplicationMutations({
    applicationId: application?.id ?? "",
    jobId: id,
  });

  const reExtract = useMutation({
    mutationFn: () =>
      apiFetch<Job>(`/api/jobs/${id}/re-extract`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Job re-extracted");
      qc.invalidateQueries({ queryKey: ["job-detail", id] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // One-click promote into the agent queue (same rule as the tracker action:
  // only offered when the job has no proposal yet).
  const promote = useMutation({
    mutationFn: () => promoteJobToAgentQueue(id),
    onSuccess: () => {
      toast.success("Queued for the next apply run");
      qc.invalidateQueries({ queryKey: ["job-detail", id] });
      qc.invalidateQueries({ queryKey: ["proposals"] });
      qc.invalidateQueries({ queryKey: ["jobs", "without-application"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Prev/next: proposals list writes cs-proposals-seq; Applications writes
  // cs-tracker-seq. ?from=proposals selects which queue and back target.
  const sequence = useMemo<string[]>(
    () =>
      readSequence(fromProposals ? "cs-proposals-seq" : "cs-tracker-seq"),
    [fromProposals],
  );
  const seqPos = sequence.indexOf(id);
  const prevJobId = seqPos > 0 ? sequence[seqPos - 1] : null;
  const nextJobId =
    seqPos >= 0 && seqPos < sequence.length - 1 ? sequence[seqPos + 1] : null;
  const jobHref = (jobId: string) =>
    fromProposals ? `/jobs/${jobId}?from=proposals` : `/jobs/${jobId}`;

  const deleteJob = useMutation({
    mutationFn: () => apiFetch<void>(`/api/jobs/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Job deleted");
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["applications"] });
      router.push(fromProposals ? "/proposals" : "/applications");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const reExtractButton = useMemo(
    () => (
      <Button
        variant="outline"
        size="sm"
        onClick={async () => {
          const ok = await confirm({
            title: "Re-run JD extraction?",
            description:
              "All extracted fields and skill rows for this job will be replaced.",
            confirmLabel: "Re-extract",
          });
          if (!ok) return;
          reExtract.mutate();
        }}
        disabled={reExtract.isPending}
      >
        <RefreshCw
          className={reExtract.isPending ? "animate-spin" : undefined}
        />
        {reExtract.isPending ? "Re-extracting…" : "Re-extract"}
      </Button>
    ),
    [confirm, reExtract],
  );

  // Before the loading gate: `data` stays undefined after a failure, so the
  // gate below would hold the skeleton on screen for good.
  if (isError) {
    return (
      <main className="mx-auto w-full max-w-6xl flex-1 space-y-4 p-6">
        <LoadErrorState
          title="Couldn't load this job."
          detail={(error as Error)?.message}
          retrying={isFetching}
          onRetry={() => void refetch()}
          action={
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href="/applications">Back to Applications</Link>}
            />
          }
        />
      </main>
    );
  }

  if (isLoading || !data) {
    return (
      <main className="mx-auto w-full max-w-6xl flex-1 space-y-4 p-6">
        <Skeleton className="animate-shimmer h-16 w-2/3" />
        <Skeleton className="animate-shimmer h-60 w-full" />
      </main>
    );
  }

  const { job } = data;
  const hasApp = !!application;
  const salary = formatSalary(
    job.salary_min,
    job.salary_max,
    job.salary_period,
    job.salary_currency,
  );
  const metaBits = [
    job.location,
    job.work_mode,
    salary,
    job.level,
  ].filter(Boolean) as string[];

  const proposalStatus = job.proposal_status ?? null;
  const proposalId = job.proposal_id ?? null;
  const isProposalStatus = (s: string | null): s is ProposalStatus =>
    !!s && s in STATUS_LABELS;

  const showAccept = proposalStatus === "pending_review";
  const showDecline =
    proposalStatus === "pending_review" ||
    proposalStatus === "accepted" ||
    proposalStatus === "needs_decision" ||
    proposalStatus === "needs_human";
  const showDeleteProposal =
    !!proposalId &&
    (proposalStatus === "needs_decision" ||
      proposalStatus === "needs_human" ||
      proposalStatus === "rejected" ||
      proposalStatus === "expired");
  const triagePending =
    proposalActions.transition.isPending || proposalActions.remove.isPending;

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 gap-1 p-6 sm:gap-2">
      {/* Prev on the left, next on the right — left/right motion matches the
          chevrons. Rails stay reserved while in a list sequence so the body
          does not jump when you hit either end. */}
      {seqPos >= 0 ? (
        <div className="flex w-8 shrink-0 flex-col items-center pt-1.5">
          {prevJobId ? (
            <IconButton
              label={
                fromProposals
                  ? "Previous proposal in list"
                  : "Previous job in list"
              }
              icon={<ChevronLeft className="size-4" />}
              size="icon-sm"
              nativeButton={false}
              render={
                <Link
                  href={jobHref(prevJobId)}
                  className="text-muted-foreground"
                />
              }
            />
          ) : null}
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col gap-4">
        {/* flex-wrap + a real basis on the title block, not `flex-1`: with
            basis-0 the title never triggers a wrap, so the shrink-0 action
            cluster claimed its whole max-content width and squeezed the title
            to width:0 — and `truncate` hides an element of zero width entirely,
            so the page rendered with no title at all below ~600px. */}
        <header className="flex flex-wrap items-start gap-3">
          <IconButton
            label={fromProposals ? "Back to proposals" : "Back to applications"}
            icon={<ArrowLeft className="size-4" />}
            size="icon-sm"
            className="mt-1.5 shrink-0"
            nativeButton={false}
            render={
              <Link
                href={fromProposals ? "/proposals" : "/applications"}
                className="text-muted-foreground"
              />
            }
          />
          <CompanyMonogram
            name={job.company}
            className="mt-0.5 size-10 text-base"
          />
          <div className="min-w-0 grow basis-[16rem]">
            <h1 className="truncate text-[22px] font-medium tracking-tight">
              {job.title ?? "Untitled role"}
            </h1>
            <p className="text-muted-foreground truncate text-sm">
              {job.company ?? "Unknown company"}
              {metaBits.length ? ` · ${metaBits.join(" · ")}` : ""}
            </p>
          </div>
          <div className="mt-1 ml-auto flex flex-wrap items-center justify-end gap-2">
            {isProposalStatus(proposalStatus) ? (
              <Badge
                className={cn("shrink-0", STATUS_BADGE_CLASS[proposalStatus])}
                variant="secondary"
              >
                {STATUS_LABELS[proposalStatus]}
              </Badge>
            ) : proposalStatus ? (
              <SavedJobChip proposalStatus={proposalStatus} />
            ) : null}
            {showAccept && proposalId ? (
              <Button
                size="sm"
                variant="outline"
                disabled={triagePending}
                onClick={() => {
                  proposalActions.transition.mutate(
                    { id: proposalId, status: "accepted" },
                    {
                      onSuccess: () =>
                        toast.success("Accepted — queued for apply"),
                    },
                  );
                }}
              >
                <Check className="size-3.5" />
                Accept
              </Button>
            ) : null}
            {showDecline && proposalId ? (
              <Button
                size="sm"
                variant="outline"
                disabled={triagePending}
                onClick={() => setDeclineOpen(true)}
              >
                <X className="size-3.5" />
                Skip
              </Button>
            ) : null}
            {showDeleteProposal && proposalId ? (
              <Button
                size="sm"
                variant="ghost"
                disabled={triagePending}
                onClick={() => proposalActions.remove.mutate(proposalId)}
              >
                <Trash2 className="size-3.5" />
                Delete proposal
              </Button>
            ) : null}
            {!hasApp && !job.proposal_status ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => promote.mutate()}
                disabled={promote.isPending}
              >
                <SendHorizontal />
                {promote.isPending ? "Queueing…" : "Queue for agent"}
              </Button>
            ) : null}
            {hasApp && application ? (
              <>
                <StatusChip
                  status={application.status}
                  pending={patch.isPending}
                  onSelect={(status) => patch.mutate({ status })}
                />
                <ApplicationDetailsMenu
                  app={application}
                  jobId={id}
                  jobSourceUrl={job.source_url}
                />
              </>
            ) : null}
            {job.source_url ? (
              <IconButton
                label="Open application URL"
                icon={<ExternalLink className="size-4" />}
                size="icon-sm"
                className="text-muted-foreground shrink-0"
                nativeButton={false}
                render={
                  <a
                    href={job.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  />
                }
              />
            ) : null}
            <IconButton
              label="Delete job"
              icon={<Trash2 className="size-4" />}
              size="icon-sm"
              className="text-muted-foreground hover:text-destructive shrink-0"
              disabled={deleteJob.isPending}
              onClick={async () => {
                const ok = await confirm({
                  title: "Delete this job?",
                  description:
                    "Its application, ATS scores, tailoring sessions, and Q&A history will go with it.",
                  confirmLabel: "Delete",
                  destructive: true,
                });
                if (!ok) return;
                deleteJob.mutate();
              }}
            />
          </div>
        </header>

        <Tabs
          value={tab}
          onValueChange={(value) => setTab(String(value))}
          className="gap-4"
        >
          {/* "Edit resume" is promoted OUT of the Resume tab (design §4.5): once a
              tailored draft exists the studio is reachable from every tab, not
              just the one you have to remember to open first. */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <JobTabsList hasApp={hasApp} />
            {application?.customized_json ? (
              <Button
                variant="outline"
                size="sm"
                nativeButton={false}
                render={
                  <Link href={`/applications/${application.id}/resume`}>
                    <Pencil className="size-4" />
                    Edit resume
                  </Link>
                }
              />
            ) : null}
          </div>

          <TabsContent value="jd" className="mt-0 space-y-4">
            {proposalId ? <ProposalAgentPanel proposalId={proposalId} /> : null}
            <JobExtractedFields
              job={job}
              hideTitle
              actionsSlot={reExtractButton}
            />
            <JobTrackingUrlField jobId={id} sourceUrl={job.source_url} />
          </TabsContent>

          <TabsContent value="fit" className="mt-0 space-y-4">
            <AtsScorePanel jobId={id} />
            {/* The before/after compare lives on the Resume tab, next to the
                artifact it describes — link instead of double-mounting it. */}
            {application?.customized_json ? (
              <button
                type="button"
                onClick={() => setTab("output")}
                className="text-primary inline-flex items-center gap-1 text-sm hover:underline"
              >
                See before/after comparison on the Resume tab
                <ArrowRight className="size-3.5" />
              </button>
            ) : null}
          </TabsContent>

          {application && (
            <>
              <TabsContent value="output" className="mt-0 space-y-4">
                <OutputTab app={application} jobId={id} />
              </TabsContent>
              <TabsContent value="qa" className="mt-0 space-y-4">
                <QATab applicationId={application.id} />
              </TabsContent>
            </>
          )}
        </Tabs>

        {proposalId ? (
          <DeclineDialog
            open={declineOpen}
            onOpenChange={setDeclineOpen}
            pending={proposalActions.transition.isPending}
            onConfirm={(reason) => {
              proposalActions.transition.mutate(
                { id: proposalId, status: "rejected", reason },
                {
                  onSuccess: () => {
                    toast.success("Skipped");
                    setDeclineOpen(false);
                  },
                },
              );
            }}
          />
        ) : null}
      </div>

      {seqPos >= 0 ? (
        <div className="flex w-8 shrink-0 flex-col items-center pt-1.5">
          {nextJobId ? (
            <IconButton
              label={
                fromProposals ? "Next proposal in list" : "Next job in list"
              }
              icon={<ChevronRight className="size-4" />}
              size="icon-sm"
              nativeButton={false}
              render={
                <Link
                  href={jobHref(nextJobId)}
                  className="text-muted-foreground"
                />
              }
            />
          ) : null}
        </div>
      ) : null}
    </main>
  );
}
