"use client";

import { use, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { GuardedLink as Link } from "@/components/guarded-link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  RefreshCw,
  SendHorizontal,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { useApplicationMutations } from "@/components/application-panel";
import { ApplyStep } from "@/components/apply-step";
import { TailoredResumeStep } from "@/components/tailored-resume-step";
import { LoadErrorState } from "@/components/load-error-state";
import { ResumeStep } from "@/components/resume-step";
import { CompanyMonogram } from "@/components/company-monogram";
import { IconButton } from "@/components/icon-button";
import {
  JobExtractedFields,
  formatSalary,
  humanizeEnum,
} from "@/components/job-extracted-fields";
import { JobKnockoutCard, KnockoutLine } from "@/components/job-knockout-card";
import { JobSteps } from "@/components/job-steps";
import { JobSubmittedTab } from "@/components/job-submitted-tab";
import { JobTrackingUrlField } from "@/components/job-tracking-url-field";
import { JobOwnershipMark, JobOwnershipNotice } from "@/components/job-ownership";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { ResumeTag } from "@/components/visual/resume-swatch";
import { ScoreBar } from "@/components/visual/score-bar";
import { useBaseResumeColor } from "@/hooks/use-base-resume-label";
import { useJobSteps } from "@/hooks/use-job-steps";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { proposalByLine, queuedToast } from "@/lib/agent-name";
import { apiFetch, promoteJobToAgentQueue } from "@/lib/api";
import { couldnt, loadErrorDetail } from "@/lib/error-text";
import { finalFocusOn, focusIfDropped, focusTarget } from "@/lib/focus";
import { headerProposalPill, historyStatusOf, proposalHasContent } from "@/lib/inbox-readiness";
import { isLoadFailure } from "@/lib/query-state";
import { jobMetaLine } from "@/lib/job-meta";
import { TAB_TO_STEP, currentStep, stepForTab, type StepKey } from "@/lib/job-steps";
import { jobOwnershipView, ownershipControlProps } from "@/lib/job-ownership";
import { cn } from "@/lib/utils";
import type { Job, JobDetail, ProposalStatus } from "@/lib/types";
import { CONCEPT_ICONS } from "@/lib/concept-icons";

const QueueIcon = CONCEPT_ICONS.queue;
const ApproveIcon = CONCEPT_ICONS.approve;
const MoreIcon = CONCEPT_ICONS.more;

/** The proposal statuses that wait on you: the job opens on step 1, where the agent's card is. */
const PROPOSAL_WAITS_ON_YOU = new Set(["pending_review", "needs_decision", "needs_human"]);

/** Step 3 or 4 before the job has its own resume (a link to ?tab=output or ?tab=qa): say so, and point at step 2. */
function NothingTailoredYet({ onOpenFit }: { onOpenFit: () => void }) {
  return (
    <div className="text-muted-foreground flex flex-col items-center gap-2 rounded-corner-md border border-dashed p-8 text-center text-body-medium">
      <p>Nothing tailored yet.</p>
      <Button size="sm" variant="link" onClick={onOpenFit}>
        Go to Resume and gaps
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
  // `?tab=` keeps the values the app has always written (jd/fit/output/qa/submitted): /new and the
  // Companion open fit, the gap page and the studio's Back open output. No `?tab=`: the stage's step.
  const requestedTab = Array.isArray(tabParam) ? tabParam[0] : tabParam;
  const [chosenStep, setChosenStep] = useState<StepKey | null>(
    requestedTab != null && Object.hasOwn(TAB_TO_STEP, requestedTab) ? stepForTab(requestedTab) : null,
  );
  const setStep = (key: StepKey) => setChosenStep(key);
  // Once opened by link, What was submitted stays on step 4: the job's own flag may predate the fill.
  const [submittedSeen] = useState(requestedTab === "submitted");
  const receiptRef = useRef<HTMLElement | null>(null);
  // Step 1's job details open by default on every stage; Hide details is the reader's own choice.
  const [detailsOpen, setDetailsOpen] = useState(true);
  const detailsId = useId();
  // A step's panel mounts when first shown and then stays, hidden: an answer being edited on step 4
  // survives a look at step 2 (the tabs' keepMounted rule).
  const [visited, setVisited] = useState<ReadonlySet<StepKey>>(() => new Set());
  const [declineOpen, setDeclineOpen] = useState(false);
  const qc = useQueryClient();
  const router = useRouter();
  const confirm = useConfirm();
  const actionsRef = useRef<HTMLDivElement>(null);
  // Queue, Skip and Delete proposal leave the header with the status they change, taking focus with
  // them: the header's first control takes it, in the commit that changes the status. A Skip's dialog
  // closes first, so it hands focus there itself.
  const triaged = useRef(false);
  const skipped = useRef(false);
  const proposalActions = useProposalActions({
    onDone: (_ids, became) => {
      if (became === "rejected") {
        skipped.current = true;
        setDeclineOpen(false);
      }
    },
    onUndone: () => {
      triaged.current = false;
    },
    onQueued: () => setDeclineOpen(false),
  });
  const headerFirst = () => actionsRef.current && focusTarget(actionsRef.current);

  const { data, isLoading, isError, error, isFetching, fetchStatus, refetch, errorUpdateCount } = useQuery({
    queryKey: ["job-detail", id],
    queryFn: () => apiFetch<JobDetail>(`/api/jobs/${id}/detail`),
    // A Companion fill happens in another window: coming back asks again, so the What was
    // submitted tab appears without a reload. One local call, and the content on screen stays.
    refetchOnWindowFocus: true,
  });

  const application = data?.application ?? null;
  const ownership = jobOwnershipView(data?.job.ownership);
  // The four steps and what the header reads with them (the score pill, the proposal, where the job stands).
  const { proposalQuery, baseName, scoreShown, standing, steps } = useJobSteps(id, data);
  const colorOf = useBaseResumeColor();
  const scoreResume = scoreShown?.tailored ? application?.base_resume ?? "" : scoreShown?.targetId ?? "";
  const proposalId = data?.job.proposal_id ?? null;
  const { patch } = useApplicationMutations({
    applicationId: application?.id ?? "",
    jobId: id,
  });
  // The one status starter: the header's StatusChip and step 4's Mark applied (a double click sent two PATCHes).
  const setStatus = useSingleFlight(patch.mutate);

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
    onError: (err: Error) => toast.error(couldnt("queue the job", err)),
  });
  // A double click filed two accepted proposals for one job.
  const promoteOnce = useSingleFlight(promote.mutate);
  const triagedStatus = data?.job.proposal_status;
  useLayoutEffect(() => {
    if (!triaged.current) return;
    triaged.current = false;
    focusIfDropped(actionsRef.current && focusTarget(actionsRef.current));
  }, [triagedStatus]);

  // Use resume as is on step 2, and Continue to Apply or Tailor again on step 3, open another step and hide the
  // button that held focus: the step it opened takes it.
  const stepsRef = useRef<HTMLDivElement>(null);
  const focusOpenedStep = useRef(false);
  useLayoutEffect(() => {
    if (!focusOpenedStep.current) return;
    focusOpenedStep.current = false;
    const active = document.activeElement;
    if (active && active !== document.body && !active.closest("[hidden]")) return;
    stepsRef.current?.querySelector<HTMLElement>('[aria-current="step"]')?.focus({ preventScroll: true });
  });

  // Prev/next: proposals list writes cs-proposals-seq; Jobs (/applications) writes
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

  // The header's ⋯: confirms opened from its items return focus to it (the item is gone by then).
  const moreRef = useRef<HTMLButtonElement>(null);
  const moreTrigger = () => moreRef.current;

  // Before the loading gate: `data` stays undefined after a failure, so the
  // gate below would hold the skeleton on screen for good.
  if (isLoadFailure({ data, isError, fetchStatus, errorUpdateCount })) {
    return (
      <main className="mx-auto w-full max-w-6xl flex-1 space-y-4 p-6">
        <LoadErrorState
          title="Couldn't load this job."
          detail={loadErrorDetail(error, "job")}
          retrying={isFetching}
          onRetry={() => void refetch()}
          action={
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href="/applications">Back to Jobs</Link>}
            />
          }
        />
      </main>
    );
  }

  if (isLoading || !data || !standing || !steps) {
    return (
      <main className="mx-auto w-full max-w-6xl flex-1 space-y-4 p-6">
        <Skeleton className="animate-shimmer h-16 w-2/3" />
        <Skeleton className="animate-shimmer h-60 w-full" />
      </main>
    );
  }

  const { job } = data;
  const hasApp = !!application;
  const showSubmitted = Boolean(data.has_filled_answers) || submittedSeen;
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
  const proposalBy = proposalStatus
    ? proposalByLine(job.proposal_proposed_by, proposalStatus) : null;
  const isProposalStatus = (s: string | null): s is ProposalStatus =>
    !!s && s in STATUS_LABELS;
  const pill = isProposalStatus(proposalStatus)
    ? headerProposalPill({
        hasApplication: hasApp,
        status: proposalStatus,
        reason: proposalQuery.data?.reason,
        reasonPending: proposalQuery.isLoading,
        fallbackLabel: STATUS_LABELS[proposalStatus],
      })
    : null;

  const showAccept = proposalStatus === "pending_review";
  const showKeep = proposalStatus === "needs_decision";
  const showDecline =
    proposalStatus === "pending_review" ||
    proposalStatus === "accepted" ||
    proposalStatus === "needs_decision" ||
    proposalStatus === "needs_human";
  // A closed proposal on a job you applied to is history, not something to delete from the header.
  const showDeleteProposal =
    !!proposalId &&
    standing.kind !== "applied" &&
    !(hasApp && historyStatusOf(proposalStatus as ProposalStatus, proposalQuery.data?.reason) === "submitted") &&
    (proposalStatus === "needs_decision" ||
      proposalStatus === "needs_human" ||
      proposalStatus === "rejected" ||
      proposalStatus === "expired");
  const triagePending = proposalActions.pending;

  // The rung sits beside `job` on the detail, not in it (useJobSteps reads it the same way).
  const stage = data.stage ?? "saved";
  // The step is fixed once, from the first data: a refetch or a triage that moves the stage never switches
  // the panel under you. A link's ?tab= wins; a proposal waiting on you opens step 1.
  const initialStep: StepKey =
    proposalStatus && PROPOSAL_WAITS_ON_YOU.has(proposalStatus) ? "job" : currentStep(stage);
  if (chosenStep == null) setChosenStep(initialStep);
  const step: StepKey = chosenStep ?? initialStep;
  // Not behind an application: a form can be filled before one exists.
  const receipt = showSubmitted ? (
    <section
      aria-label="What was submitted"
      tabIndex={-1}
      ref={receiptRef}
      className="scroll-mt-6 rounded-corner-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <JobSubmittedTab jobId={id} active={step === "qa"} onOpenTab={application ? setStep : undefined} />
    </section>
  ) : null;
  if (!visited.has(step)) setVisited(new Set(visited).add(step));

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
                  : "Previous job in Jobs"
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
            label={fromProposals ? "Back to Agent inbox" : "Back to Jobs"}
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
            className="mt-0.5 size-10 text-body-large"
          />
          <div className="min-w-0 grow basis-[16rem]">
            {/* Wraps, never truncates: at 375 a long title lost its end, and this is the one place it shows. */}
            <h1 className="text-title-large font-medium tracking-tight break-words">
              {job.title ?? "Untitled role"}
            </h1>
            <p className="text-muted-foreground truncate text-body-medium" title={metaLine}>
              {metaLine}
            </p>
            {ownership.mark ? <div className="mt-2"><JobOwnershipMark jobId={id} ownership={job.ownership} /></div> : null}
          </div>
          <div ref={actionsRef} className="mt-1 ml-auto flex flex-wrap items-center justify-end gap-2">
            {pill ? (
              <Badge
                className={cn("shrink-0", STATUS_BADGE_CLASS[pill.styleStatus])}
                variant="secondary"
                title={proposalBy ?? undefined}
              >
                {/* The status is the pill's text (the ONE status vocabulary); who filed it is heard first
                    and shown on hover. An application's own status replaces the pill: one status here. */}
                {proposalBy ? <span className="sr-only">{proposalBy}, status </span> : null}
                {pill.label}
              </Badge>
            ) : proposalStatus && !hasApp && !isProposalStatus(proposalStatus) ? (
              <SavedJobChip proposalStatus={proposalStatus} />
            ) : null}
            {showAccept && proposalId ? (
              <Button
                size="sm"
                variant="outline"
                disabled={triagePending || !ownership.canRequest}
                // Focusable while it runs: a natively disabled button dropped focus to <body>.
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={() => {
                  triaged.current = true;
                  proposalActions.transition({ id: proposalId, status: "accepted" });
                }}
              >
                <QueueIcon className="size-3.5" />
                Queue
              </Button>
            ) : null}
            {showKeep && proposalId ? (
              <Button
                size="sm"
                variant="outline"
                // Waits for the proposal's link: a second, different application would be refused.
                disabled={triagePending || !proposalQuery.data}
                {...ownershipControlProps(!ownership.canWrite)}
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={() => {
                  triaged.current = true;
                  proposalActions.transition({
                    id: proposalId,
                    status: "pending_review",
                    applicationId: proposalQuery.data?.application ? undefined : application?.id,
                  });
                }}
              >
                <ApproveIcon className="size-3.5" />
                Keep it
              </Button>
            ) : null}
            {showDecline && proposalId ? (
              <Button
                size="sm"
                variant="outline"
                disabled={triagePending || !ownership.canRequest}
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
                disabled={triagePending || !ownership.canWrite}
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
            {scoreShown ? (
              // The resume's name shows only at 2xl: at 1280 it squeezed a long job title onto two lines.
              // The hover title and the meter's accessible name carry it at every width.
              <span
                title={`${scoreShown.label}${scoreShown.tailored ? " (tailored)" : ""}: ${scoreShown.value.toFixed(1)}, ${baseName(scoreResume)}`}
                className="bg-surface-container-low inline-flex h-7 min-w-0 items-center gap-2 rounded-full px-2.5 text-label-medium"
              >
                <span aria-hidden="true" className="text-muted-foreground">{scoreShown.label}</span>
                <ScoreBar
                  value={scoreShown.value}
                  valueText={scoreShown.value.toFixed(1)}
                  label={`${scoreShown.label}${scoreShown.tailored ? ", tailored" : ""}, ${baseName(scoreResume)}`}
                />
                {scoreShown.tailored ? <span aria-hidden="true" className="text-muted-foreground">(tailored)</span> : null}
                {/* The square goes with the name: below 2xl neither shows. */}
                <ResumeTag hue={colorOf(scoreResume)} className="hidden min-w-0 2xl:inline-flex">
                  <span aria-hidden="true" className="text-muted-foreground truncate">{baseName(scoreResume)}</span>
                </ResumeTag>
              </span>
            ) : null}
            {hasApp && application ? (
              <StatusChip
                status={application.status}
                pending={patch.isPending}
                disabled={!ownership.canRequest}
                onSelect={(status) => setStatus({ status })}
              />
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
            {/* The rare actions, behind one ⋯: queue it for an agent, read the job description again, delete. */}
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <IconButton
                    ref={moreRef}
                    label="More actions"
                    icon={<MoreIcon className="size-4" />}
                    size="icon-sm"
                    className="text-muted-foreground shrink-0"
                  />
                }
              />
              <DropdownMenuContent align="end" className="w-max">
                {!hasApp && !job.proposal_status ? (
                  <DropdownMenuItem
                    disabled={promote.isPending || !ownership.canWrite}
                    onClick={() => promoteOnce()}
                  >
                    <SendHorizontal />
                    {promote.isPending ? "Queueing…" : "Queue in Agent inbox"}
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuItem
                  disabled={reExtract.isPending || !ownership.canWrite}
                  onClick={async () => {
                    const ok = await confirm({
                      title: "Refresh the job details?",
                      description:
                        "This reads the job description again and replaces the job details and skills.",
                      confirmLabel: "Refresh details",
                      returnFocus: moreTrigger,
                    });
                    if (!ok) return;
                    reExtract.mutate();
                  }}
                >
                  <RefreshCw className={reExtract.isPending ? "animate-spin" : undefined} />
                  {reExtract.isPending ? "Refreshing…" : "Refresh details"}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  variant="destructive"
                  disabled={deleteJob.isPending || !ownership.canWrite}
                  onClick={async () => {
                    const ok = await confirm({
                      title: "Delete this job?",
                      description:
                        "This also deletes its application, match scores, gap analyses, answers and any Agent inbox proposals for it.",
                      confirmLabel: "Delete",
                      destructive: true,
                      returnFocus: moreTrigger,
                    });
                    if (!ok) return;
                    deleteJob.mutate();
                  }}
                >
                  <Trash2 />
                  Delete job
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>
        <JobOwnershipNotice ownership={job.ownership} />

        {/* The four steps, where the tabs were. A later step is shown, never locked: its line says what opens it. */}
        <div ref={stepsRef} className="space-y-4">
          <JobSteps steps={steps} current={step} onSelect={setStep} />

          {visited.has("job") ? (
            <div hidden={step !== "job"} className="space-y-4">
              {/* Only a proposal that carries something: a question, a reason, a note, a plan someone wrote,
                  drafted answers or screenshots. A load failure shows its error card. Never folded away. */}
              {proposalId && (proposalQuery.isError || (proposalQuery.data && proposalHasContent(proposalQuery.data))) ? (
                <ProposalAgentPanel proposalId={proposalId} />
              ) : null}
              {/* The receipt: step 1's line, and the details under it, open by default. */}
              <div className="bg-surface-container-low flex items-center justify-between gap-3 rounded-corner-md px-4 py-2">
                <p className="text-body-medium">{steps[0].summary}</p>
                <Button
                  size="sm"
                  variant="link"
                  aria-expanded={detailsOpen}
                  aria-controls={detailsId}
                  onClick={() => setDetailsOpen(!detailsOpen)}
                >
                  {detailsOpen ? "Hide details" : "View details"}
                </Button>
              </div>
              <div id={detailsId} hidden={!detailsOpen} className="space-y-4">
                <JobKnockoutCard scan={data?.knockout} job={job} />
                <JobExtractedFields
                  job={job}
                  hideTitle
                  statusSlot={<KnockoutLine scan={data?.knockout} job={job} />}
                />
                <JobTrackingUrlField jobId={id} sourceUrl={job.source_url} readOnly={!ownership.canWrite} />
              </div>
            </div>
          ) : null}

          {visited.has("fit") ? (
            <div hidden={step !== "fit"} className="space-y-4">
              {/* Use resume as is makes the job's resume: step 3 shows it. */}
              <ResumeStep
                jobId={id}
                application={application}
                readOnly={!ownership.canWrite}
                onUsedAsIs={() => {
                  focusOpenedStep.current = true;
                  setStep("output");
                }}
                onOpenTailored={() => {
                  focusOpenedStep.current = true;
                  setStep("output");
                }}
              />
              {/* The before/after compare lives on step 3, next to the artifact it describes: link to it. */}
              {application?.customized_json ? (
                <button
                  type="button"
                  onClick={() => setStep("output")}
                  className="text-primary inline-flex items-center gap-1 text-body-medium hover:underline"
                >
                  Compare with your base resume in Tailored resume
                  <ArrowRight className="size-3.5" />
                </button>
              ) : null}
            </div>
          ) : null}

          {visited.has("output") ? (
            application ? (
              <div hidden={step !== "output"} className="space-y-4">
                {/* Continue to Apply and Tailor again open another step and hide the button that held focus. */}
                <TailoredResumeStep
                  app={application}
                  jobId={id}
                  readOnly={!ownership.canWrite}
                  onOpenStep={(key) => {
                    focusOpenedStep.current = true;
                    setStep(key);
                  }}
                />
              </div>
            ) : (
              // A link to ?tab=output on a job with no resume of its own yet.
              <div hidden={step !== "output"}>
                <NothingTailoredYet onOpenFit={() => setStep("fit")} />
              </div>
            )
          ) : null}

          {visited.has("qa") ? (
            <div hidden={step !== "qa"} className="space-y-4">
              {application ? (
                // Step 4: the questions, Mark applied and the application's details; the cover letter and the receipt.
                <ApplyStep
                  app={application}
                  job={job}
                  jobId={id}
                  readOnly={!ownership.canWrite}
                  canRequest={ownership.canRequest}
                  setStatus={setStatus}
                  statusPending={patch.isPending}
                  pendingStatus={patch.variables?.status ?? null}
                  active={step === "qa"}
                  receipt={receipt}
                  receiptRef={receiptRef}
                  receiptFirst={submittedSeen}
                />
              ) : (
                <>
                  {/* A link that opened the receipt (?tab=submitted) puts it first; else it follows. */}
                  {submittedSeen ? receipt : null}
                  <NothingTailoredYet onOpenFit={() => setStep("fit")} />
                  {submittedSeen ? null : receipt}
                </>
              )}
            </div>
          ) : null}
        </div>

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
                fromProposals ? "Next job in Agent inbox" : "Next job in Jobs"
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
