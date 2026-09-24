"use client";

import { use, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { GuardedLink as Link } from "@/components/guarded-link";
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
  humanizeEnum,
} from "@/components/job-extracted-fields";
import { JobKnockoutCard } from "@/components/job-knockout-card";
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
import { useSingleFlight } from "@/hooks/use-single-flight";
import { proposalByLine, queuedToast } from "@/lib/agent-name";
import { apiFetch, promoteJobToAgentQueue } from "@/lib/api";
import { couldnt, errorDetail } from "@/lib/error-text";
import { finalFocusOn, focusIfDropped, focusTarget } from "@/lib/focus";
import { isLoadFailure } from "@/lib/query-state";
import { jobMetaLine } from "@/lib/job-meta";
import { cn } from "@/lib/utils";
import type { Job, JobDetail, ProposalStatus } from "@/lib/types";

// Tab values stay jd/fit/output/qa for deep-link compat (?tab=fit, ?tab=output).
const JOB_TABS = ["jd", "fit", "output", "qa"] as const;

/**
 * Why Resume and Q&A are locked: they show a job's application, which tailoring, Use resume as is
 * (the gap page) and Mark applied without tailoring (Score and tailor) each create.
 */
const LOCKED_REASON =
  "Resume and Q&A open once this job has its own resume: tailor one, use yours as is, or mark the job applied.";

function JobTabsList({ hasApp, reasonId }: { hasApp: boolean; reasonId: string }) {
  // A greyed tab with no stated reason is a dead end for a first-time user: the
  // reason is visible beside the tabs (below) and each locked tab points at it.
  // The base trigger styles set pointer-events-none while disabled, which
  // suppresses the native title tooltip too; re-enable it on the locked pair
  // only. The disabled attribute still swallows the click.
  const lockedProps = hasApp
    ? {}
    : {
        disabled: true,
        title: LOCKED_REASON,
        "aria-describedby": reasonId,
        className:
          "disabled:pointer-events-auto aria-disabled:pointer-events-auto",
      };
  return (
    <TabsList>
      <TabsTrigger value="jd">Overview</TabsTrigger>
      <TabsTrigger value="fit">Score and tailor</TabsTrigger>
      <TabsTrigger value="output" {...lockedProps}>
        Resume
      </TabsTrigger>
      <TabsTrigger value="qa" {...lockedProps}>
        Q&amp;A
      </TabsTrigger>
    </TabsList>
  );
}

function NoDraftYet({ onOpenFit }: { onOpenFit: () => void }) {
  return (
    <div className="text-muted-foreground flex flex-col items-center gap-3 rounded-md border border-dashed p-8 text-center text-sm">
      <p>{"Your resume and answers appear here once you start a draft."}</p>
      <Button size="sm" variant="outline" onClick={onOpenFit}>
        Go to Score and tailor
      </Button>
    </div>
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
  const lockedReasonId = useId();
  const actionsRef = useRef<HTMLDivElement>(null);
  // Queue, Skip and Delete proposal leave the header with the status they change, taking focus with
  // them: the header's first control takes it, in the commit that changes the status. A Skip's dialog
  // closes first, so it hands focus there itself.
  const triaged = useRef(false);
  const skipped = useRef(false);
  const proposalActions = useProposalActions({
    onDone: (_ids, became) => {
      if (became === "accepted") toast.success("Queued. A connected agent can apply to it now.");
      if (became === "rejected") {
        toast.success("Skipped");
        skipped.current = true;
        setDeclineOpen(false);
      }
    },
    onUndone: () => {
      triaged.current = false;
    },
  });
  const headerFirst = () => actionsRef.current && focusTarget(actionsRef.current);

  const { data, isLoading, isError, error, isFetching, fetchStatus, refetch, errorUpdateCount } = useQuery({
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
      toast.success("Job details refreshed");
      qc.invalidateQueries({ queryKey: ["job-detail", id] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err: Error) => toast.error(couldnt("refresh the job details", err)),
  });

  // Queue for agent leaves the header once the job has a proposal, taking focus with it: the
  // header's first control (the new proposal's Skip) takes it, in the commit that drops the button.
  const queued = useRef(false);
  // One-click promote into the agent queue (same rule as the tracker action:
  // only offered when the job has no proposal yet).
  const promote = useMutation({
    mutationFn: () => promoteJobToAgentQueue(id),
    onSuccess: (queue) => toast.success(queuedToast(queue)),
    // Whatever happened, a proposal may now exist (filed, then the accept failed): show it.
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["job-detail", id] });
      qc.invalidateQueries({ queryKey: ["proposals"] });
      qc.invalidateQueries({ queryKey: ["jobs", "without-application"] });
    },
    onError: (err: Error) => {
      queued.current = false;
      toast.error(couldnt("queue the job", err));
    },
  });
  // A double click filed two accepted proposals for one job.
  const promoteOnce = useSingleFlight(promote.mutate);
  const hasProposal = Boolean(data?.job.proposal_status);
  useLayoutEffect(() => {
    if (!queued.current || !hasProposal) return;
    queued.current = false;
    if (actionsRef.current) focusIfDropped(focusTarget(actionsRef.current));
  }, [hasProposal]);
  const triagedStatus = data?.job.proposal_status;
  useLayoutEffect(() => {
    if (!triaged.current) return;
    triaged.current = false;
    focusIfDropped(actionsRef.current && focusTarget(actionsRef.current));
  }, [triagedStatus]);

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
    onError: (err: Error) => toast.error(couldnt("delete the job", err)),
  });

  const reExtractButton = useMemo(
    () => (
      <Button
        variant="outline"
        size="sm"
        onClick={async () => {
          const ok = await confirm({
            title: "Refresh the job details?",
            description:
              "This reads the job description again and replaces the job details and skills.",
            confirmLabel: "Refresh details",
          });
          if (!ok) return;
          reExtract.mutate();
        }}
        disabled={reExtract.isPending}
      >
        <RefreshCw
          className={reExtract.isPending ? "animate-spin" : undefined}
        />
        {reExtract.isPending ? "Refreshing…" : "Refresh details"}
      </Button>
    ),
    [confirm, reExtract],
  );

  // Before the loading gate: `data` stays undefined after a failure, so the
  // gate below would hold the skeleton on screen for good.
  if (isLoadFailure({ data, isError, fetchStatus, errorUpdateCount })) {
    return (
      <main className="mx-auto w-full max-w-6xl flex-1 space-y-4 p-6">
        <LoadErrorState
          title="Couldn't load this job."
          detail={errorDetail(error)}
          retrying={isFetching}
          onRetry={() => void refetch()}
          action={
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href="/applications">Back to applications</Link>}
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
  const metaLine = jobMetaLine([
    job.company ?? "Unknown company",
    job.location,
    humanizeEnum(job.work_mode),
    salary,
    humanizeEnum(job.level),
  ]);

  const proposalStatus = job.proposal_status ?? null;
  const proposalId = job.proposal_id ?? null;
  const proposalBy = proposalStatus
    ? proposalByLine(job.proposal_proposed_by, proposalStatus) : null;
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
  const triagePending = proposalActions.pending;

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
                  ? "Previous job in Agent inbox"
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
            label={fromProposals ? "Back to Agent inbox" : "Back to applications"}
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
            {/* Wraps, never truncates: at 375 a long title lost its end, and this is the one place it shows. */}
            <h1 className="text-[22px] font-medium tracking-tight break-words">
              {job.title ?? "Untitled role"}
            </h1>
            <p className="text-muted-foreground truncate text-sm" title={metaLine}>
              {metaLine}
            </p>
          </div>
          <div ref={actionsRef} className="mt-1 ml-auto flex flex-wrap items-center justify-end gap-2">
            {isProposalStatus(proposalStatus) ? (
              <Badge
                className={cn("shrink-0", STATUS_BADGE_CLASS[proposalStatus])}
                variant="secondary"
                title={proposalBy ?? undefined}
              >
                {/* The status is the pill's text (the ONE status vocabulary);
                    who filed it is heard first and shown on hover. The
                    Overview card shows it visibly. */}
                {proposalBy ? <span className="sr-only">{proposalBy}, status </span> : null}
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
                // Focusable while it runs: a natively disabled button dropped focus to <body>.
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={() => {
                  triaged.current = true;
                  proposalActions.transition({ id: proposalId, status: "accepted" });
                }}
              >
                <Check className="size-3.5" />
                Queue
              </Button>
            ) : null}
            {showDecline && proposalId ? (
              <Button
                size="sm"
                variant="outline"
                disabled={triagePending}
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
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
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={() => {
                  triaged.current = true;
                  proposalActions.remove({ id: proposalId, next: headerFirst });
                }}
              >
                <Trash2 className="size-3.5" />
                Delete proposal
              </Button>
            ) : null}
            {!hasApp && !job.proposal_status ? (
              <Button
                variant="outline"
                size="sm"
                // Focusable while it queues: a disabled button dropped focus to <body>.
                focusableWhenDisabled
                disabled={promote.isPending}
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={() => {
                  queued.current = true;
                  promoteOnce();
                }}
              >
                <SendHorizontal />
                {promote.isPending ? "Queueing…" : "Queue in Agent inbox"}
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
                label="Open job link"
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
                    "This also deletes its application, ATS scores, gap analyses, answers and any Agent inbox proposals for it.",
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
              just the one you have to remember to open first. It is filled,
              not outlined: promoting a control to every tab and then styling
              it like the row's furniture buries it again — this is what you
              came to the job for once a draft exists. */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <JobTabsList hasApp={hasApp} reasonId={lockedReasonId} />
            {hasApp ? null : (
              <p id={lockedReasonId} className="text-muted-foreground basis-full text-xs">
                {LOCKED_REASON}
              </p>
            )}
            {application?.customized_json ? (
              <Button
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
            <JobKnockoutCard scan={data?.knockout} job={job} />
            <JobExtractedFields
              job={job}
              hideTitle
              actionsSlot={reExtractButton}
            />
            <JobTrackingUrlField jobId={id} sourceUrl={job.source_url} />
          </TabsContent>

          <TabsContent value="fit" className="mt-0 space-y-4">
            <AtsScorePanel jobId={id} applicationStatus={application?.status ?? null} />
            {/* The before/after compare lives on the Resume tab, next to the
                artifact it describes — link instead of double-mounting it. */}
            {application?.customized_json ? (
              <button
                type="button"
                onClick={() => setTab("output")}
                className="text-primary inline-flex items-center gap-1 text-sm hover:underline"
              >
                Compare with your base resume on the Resume tab
                <ArrowRight className="size-3.5" />
              </button>
            ) : null}
          </TabsContent>

          {application ? (
            <>
              <TabsContent value="output" className="mt-0 space-y-4">
                <OutputTab app={application} jobId={id} />
              </TabsContent>
              <TabsContent value="qa" className="mt-0 space-y-4">
                <QATab applicationId={application.id} />
              </TabsContent>
            </>
          ) : (
            // A link to ?tab=output or ?tab=qa on a job with no draft opened a blank panel.
            <>
              <TabsContent value="output" className="mt-0">
                <NoDraftYet onOpenFit={() => setTab("fit")} />
              </TabsContent>
              <TabsContent value="qa" className="mt-0">
                <NoDraftYet onOpenFit={() => setTab("fit")} />
              </TabsContent>
            </>
          )}
        </Tabs>

        {proposalId ? (
          <DeclineDialog
            open={declineOpen}
            onOpenChange={setDeclineOpen}
            pending={triagePending}
            finalFocus={() => {
              if (!skipped.current) return true; // cancelled: back to Skip
              skipped.current = false;
              return finalFocusOn(headerFirst());
            }}
            onConfirm={(reason) => {
              triaged.current = true;
              proposalActions.transition({ id: proposalId, status: "rejected", reason });
            }}
          />
        ) : null}
      </div>

      {seqPos >= 0 ? (
        <div className="flex w-8 shrink-0 flex-col items-center pt-1.5">
          {nextJobId ? (
            <IconButton
              label={
                fromProposals ? "Next job in Agent inbox" : "Next job in list"
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
