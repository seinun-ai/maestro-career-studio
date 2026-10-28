"use client";

import { useEffect, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { CompanyMonogram } from "@/components/company-monogram";
import { GuardedLink as Link } from "@/components/guarded-link";
import { LoadErrorState } from "@/components/load-error-state";
import { PageHeader, PageShell } from "@/components/page-shell";
import { DeclineDialog, useProposalActions } from "@/components/proposals/triage-actions";
import { SetupEntryCard, needsSetup } from "@/components/setup/setup-entry-card";
import { useOpenSetupOnFirstLaunch } from "@/components/setup/use-first-run";
import { Button } from "@/components/ui/button";
import { Fold } from "@/components/ui/fold";
import { LeadCard } from "@/components/ui/lead-card";
import { Skeleton } from "@/components/ui/skeleton";
import { NextStep, NumberRoll, ResumeTag, ScoreBar } from "@/components/visual";
import { useMoney } from "@/hooks/use-money";
import { apiFetch } from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt, loadErrorDetail } from "@/lib/error-text";
import { formatShortDate } from "@/lib/format-date";
import { needsYouLine } from "@/lib/inbox-lanes";
import { jobMetaLine } from "@/lib/job-meta";
import { isSyncQueued } from "@/lib/job-ownership";
import { formatPay, payLine, periodWords } from "@/lib/money";
import { isLoadFailure } from "@/lib/query-state";
import {
  STEP_WORDS,
  countWhere,
  countWords,
  dayHeading,
  moreStepLabel,
  moreSummary,
  nextUpAction,
  todayKey,
  todayPath,
  weekBars,
  weekLabel,
  weekLine,
  type BrowserZone,
} from "@/lib/today";
import {
  baseResumeLabel,
  type ApplicationStatus,
  type SetupStatus,
  type TodayCount,
  type TodayNextUp,
  type TodayResponse,
} from "@/lib/types";
import { cn } from "@/lib/utils";

/** Each count's icon, from the register (lib/concept-icons.ts). */
const COUNT_ICONS: Record<TodayCount["key"], LucideIcon> = {
  to_approve: CONCEPT_ICONS.agentInbox,
  to_check: CONCEPT_ICONS.baseResume,
  quiet: CONCEPT_ICONS.waiting,
  gaps_to_close: CONCEPT_ICONS.analyzeGaps,
  health_check: CONCEPT_ICONS.health,
};

/** The browser's zone, read each render: the server cannot know it. The offset goes with the name, since
 * a Windows install may have no zone database to look the name up in. */
function browserZone(): BrowserZone {
  return {
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
    offsetMinutes: -new Date().getTimezoneOffset(),
  };
}

/**
 * Today, the home page (`/` redirects here): Next up as the Lead, three counts under Also today, the rest in
 * one fold, then this week. One read, `GET /api/today`, picks and counts everything; Setup's entry card
 * takes the lead place for a new user with nothing to do yet, and a brand-new install opens Setup once.
 */
export default function TodayPage() {
  const zone = browserZone();
  const today = useQuery({
    queryKey: todayKey(zone),
    queryFn: () => apiFetch<TodayResponse>(todayPath(zone)),
  });
  // The Getting started card's key: one read of setup progress for every reader.
  const setup = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => apiFetch<SetupStatus>("/api/setup/status"),
  });
  // A brand-new install (no key, no resume) goes to Setup, once (components/setup/use-first-run.ts).
  useOpenSetupOnFirstLaunch(setup.data);
  const data = today.data;
  // A Skip that leaves nothing next takes its button away: focus goes to what takes the card's place (the
  // empty line, or Setup's card on a new install).
  const skipped = useRef(false);
  const lead = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!skipped.current || !data) return;
    skipped.current = false;
    if (!data.next_up) lead.current?.focus();
  }, [data]);

  return (
    <PageShell>
      <PageHeader
        title="Today"
        meta={data ? <span className="text-muted-foreground text-body-medium">{dayHeading(data.today)}</span> : null}
      />
      {isLoadFailure(today) ? (
        <LoadErrorState
          title="Couldn't load Today."
          detail={loadErrorDetail(today.error)}
          retrying={today.isFetching}
          onRetry={() => void today.refetch()}
        />
      ) : !data ? (
        <div className="flex flex-col gap-7">
          <Skeleton className="h-56 w-full rounded-corner-lg" />
          <div className="grid grid-cols-3 gap-3">
            <Skeleton className="h-24 rounded-corner-md" />
            <Skeleton className="h-24 rounded-corner-md" />
            <Skeleton className="h-24 rounded-corner-md" />
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-7">
          <div ref={lead} tabIndex={-1} className="outline-none">
            {data.next_up ? (
              <NextUp item={data.next_up} onSkipped={() => (skipped.current = true)} />
            ) : setup.isPending && setup.failureCount === 0 ? (
              // Setup's card or the empty line: whichever it is, not one and then the other. A failed setup
              // read stops the wait: Today's own read already says nothing is waiting.
              <Skeleton className="h-40 w-full rounded-corner-lg" />
            ) : setup.data && needsSetup(setup.data) ? (
              <SetupEntryCard status={setup.data} />
            ) : (
              <section aria-label="Next up" className="flex items-center gap-3 rounded-corner-lg bg-card p-7">
                <CONCEPT_ICONS.done aria-hidden="true" className="size-5 shrink-0 text-success" />
                <p className="text-title-medium">Nothing waiting on you.</p>
              </section>
            )}
          </div>
          {data.also.length > 0 ? <AlsoToday counts={data.also} /> : null}
          {data.more.length > 0 ? <More counts={data.more} /> : null}
          <ThisWeek week={data.week} />
        </div>
      )}
    </PageShell>
  );
}

function NextUp({ item, onSkipped }: { item: TodayNextUp; onSkipped: () => void }) {
  const money = useMoney();
  const pay = item.pay ? formatPay(item.pay, money) : null;
  // D8: a converted figure keeps the posted amount under it.
  const posted =
    pay?.converted && pay.posted && money.showPosted
      ? `${pay.posted}${periodWords(pay.postedPeriod) ? ` ${periodWords(pay.postedPeriod)}` : ""} as posted`
      : null;
  const line = jobMetaLine([item.company, item.location, pay ? payLine(pay) : null]);
  const action = nextUpAction(item);
  const asks = item.kind === "needs_you" && item.status ? needsYouLine(item.status, item.reason) : null;
  return (
    <LeadCard
      eyebrow="Next up"
      action={{ label: action.label, href: action.href }}
      secondary={<SkipControl item={item} onSkipped={onSkipped} />}
      aside={item.steps.length > 0 ? <WhereItIs item={item} now={action.label} /> : undefined}
    >
      <div className="flex min-w-0 items-center gap-3.5">
        <CompanyMonogram name={item.company} className="size-12 text-title-large" />
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="text-headline-small">{item.title ?? "Untitled role"}</h2>
          {line ? <p className="text-muted-foreground text-body-medium">{line}</p> : null}
          {posted ? <p className="text-muted-foreground text-body-small">{posted}</p> : null}
        </div>
      </div>
      {item.base_resume || item.score != null ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-body-medium">
          {item.base_resume ? (
            <ResumeTag hue={item.base_resume.color_hue}>
              {baseResumeLabel(item.base_resume.slug, [{ slug: item.base_resume.slug, display_name: item.base_resume.name }])}
            </ResumeTag>
          ) : null}
          {item.score != null ? <ScoreBar value={item.score} label="Match score" /> : null}
        </div>
      ) : null}
      {asks ? <p className="max-w-[65ch] text-body-medium">{asks}</p> : null}
    </LeadCard>
  );
}

function patchStatus(id: string, status: ApplicationStatus) {
  return apiFetch<unknown>(`/api/applications/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });
}

/**
 * Next up's Skip, the quiet control beside its button. A ready PDF's application turns Skipped, and the toast's
 * Undo puts it back to Draft; an agent's job waiting on you takes the job page's Skip (the reason dialog, the
 * proposal Skipped). An offer has none: it needs an answer, not a skip. Today refetches and the next job takes
 * the card. On a job the other copy owns, the change waits for the next sync; the server passes over it meanwhile.
 */
function SkipControl({ item, onSkipped }: { item: TodayNextUp; onSkipped: () => void }) {
  const qc = useQueryClient();
  const [declineOpen, setDeclineOpen] = useState(false);
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["today"] });
    void qc.invalidateQueries({ queryKey: ["applications"] });
    void qc.invalidateQueries({ queryKey: ["jobs"] });
    void qc.invalidateQueries({ queryKey: ["job-detail", item.job_id] });
  };
  const skipDraft = useMutation({
    mutationFn: (id: string) => patchStatus(id, "skipped"),
    onSuccess: (data, id) => {
      onSkipped();
      refresh();
      if (isSyncQueued(data)) {
        toast.success("Sent at the next sync");
        return;
      }
      toast.success("Job skipped", {
        action: {
          label: "Undo",
          onClick: () =>
            patchStatus(id, "draft")
              .then(refresh)
              .catch((err: Error) => toast.error(couldnt("undo the skip", err))),
        },
      });
    },
    onError: (err: Error) => toast.error(couldnt("skip the job", err)),
  });
  const proposalActions = useProposalActions({
    onDone: () => {
      onSkipped();
      setDeclineOpen(false);
    },
    onQueued: () => setDeclineOpen(false),
  });

  if (item.kind === "pdf_ready" && item.application_id) {
    const id = item.application_id;
    return (
      <Button variant="outline" size="lg" pending={skipDraft.isPending} onClick={() => skipDraft.mutate(id)}>
        Skip
      </Button>
    );
  }
  if (item.kind === "needs_you" && item.proposal_id) {
    const id = item.proposal_id;
    return (
      <>
        <Button
          variant="outline"
          size="lg"
          disabled={proposalActions.pending}
          focusableWhenDisabled
          onClick={() => setDeclineOpen(true)}
        >
          Skip
        </Button>
        <DeclineDialog
          open={declineOpen}
          onOpenChange={setDeclineOpen}
          pending={proposalActions.pending}
          onConfirm={(reason) => proposalActions.transition({ id, status: "rejected", reason })}
        />
      </>
    );
  }
  return null;
}

/** "Where this job is": the steps the server dates, done, then the move this card's button makes. */
function WhereItIs({ item, now }: { item: TodayNextUp; now: string }) {
  return (
    <>
      <span className="text-label-medium text-muted-foreground">Where this job is</span>
      <ol className="flex flex-col gap-2.5">
        {item.steps.map((step) => (
          <li key={step.key} className="flex items-center gap-2.5">
            <CONCEPT_ICONS.done aria-hidden="true" className="size-4 shrink-0 text-success" />
            <span>{STEP_WORDS[step.key]}</span>
            <span className="ml-auto text-body-small text-muted-foreground tabular-nums">{formatShortDate(step.at)}</span>
          </li>
        ))}
        <li aria-current="step" className="flex items-center gap-2.5">
          <span
            aria-hidden="true"
            className="inline-flex size-4 shrink-0 items-center justify-center rounded-full border-2 border-primary"
          >
            <span className="size-1.5 rounded-full bg-primary" />
          </span>
          <span className="text-title-small">{now}</span>
          <span className="ml-auto text-label-medium text-primary">now</span>
        </li>
      </ol>
    </>
  );
}

function AlsoToday({ counts }: { counts: TodayCount[] }) {
  return (
    <section aria-labelledby="also-today" className="flex flex-col gap-2.5">
      <h2 id="also-today" className="text-title-small text-muted-foreground">Also today</h2>
      <ul className="grid grid-cols-3 gap-3">
        {counts.map((count) => {
          const Icon = COUNT_ICONS[count.key];
          const where = countWhere(count);
          return (
            <li key={count.key} className="flex">
              <Link
                href={count.href}
                className="flex w-full flex-col gap-2.5 rounded-corner-md bg-card px-4.5 py-4 outline-none transition-colors duration-(--duration-short3) ease-standard hover:bg-surface-container-low focus-visible:ring-3 focus-visible:ring-ring"
              >
                <span className="flex items-center justify-between gap-3">
                  <Icon aria-hidden="true" className="size-4.5 shrink-0 text-muted-foreground" />
                  <NumberRoll value={count.count} className="text-headline-medium" />
                </span>
                <span className="text-title-small">{countWords(count)}</span>
                {where ? <span className="-mt-1.5 text-body-small text-muted-foreground">{where}</span> : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function More({ counts }: { counts: TodayCount[] }) {
  return (
    <Fold title={`${counts.length} more`} summary={moreSummary(counts)}>
      <ul className="divide-y">
        {counts.map((count) => {
          const Icon = COUNT_ICONS[count.key];
          return (
            <li key={count.key} className="group/row flex items-center gap-3 py-2.5">
              <Icon aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 text-body-medium">
                <span className="text-title-small tabular-nums">{count.count}</span> {countWords(count)}
              </span>
              <NextStep label={moreStepLabel(count)} href={count.href} />
            </li>
          );
        })}
      </ul>
    </Fold>
  );
}

function ThisWeek({ week }: { week: TodayResponse["week"] }) {
  const bars = weekBars(week.days);
  const stats = [
    { n: week.replies, one: "reply", many: "replies" },
    { n: week.interviews, one: "interview", many: "interviews" },
  ];
  return (
    <section
      aria-labelledby="this-week"
      className="flex flex-wrap items-end gap-8 rounded-corner-md bg-surface-container-low px-6 py-5"
    >
      <div className="flex flex-col gap-1">
        <h2 id="this-week" className="text-title-small text-muted-foreground">This week</h2>
        <span className="text-display-small tabular-nums">{week.applied}</span>
        <span className="text-body-small text-muted-foreground">{weekLine(week)}</span>
      </div>
      <p className="flex flex-col gap-1 text-body-small text-muted-foreground">
        {stats.map((stat) => (
          <span key={stat.one}>
            <span className="text-title-medium text-foreground tabular-nums">{stat.n}</span>{" "}
            {stat.n === 1 ? stat.one : stat.many}
          </span>
        ))}
      </p>
      <div role="img" aria-label={weekLabel(bars)} className="grid h-24 flex-[1_1_360px] grid-cols-7 gap-2.5">
        {bars.map((bar) => (
          <div key={bar.date} aria-hidden="true" className="flex min-w-0 flex-col items-center gap-1.5">
            <div className="flex w-full flex-1 items-end">
              <div
                className={cn(
                  "w-full rounded-corner-xs",
                  bar.applied > 0 ? "bg-chart-1" : "h-1 bg-surface-container-high",
                )}
                style={bar.applied > 0 ? { height: `${bar.pct}%` } : undefined}
              />
            </div>
            <span className={cn("text-label-small", bar.today ? "text-foreground" : "text-muted-foreground")}>
              {bar.day}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
