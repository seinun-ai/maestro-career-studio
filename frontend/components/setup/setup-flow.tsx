"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import { useQuery } from "@tanstack/react-query";

import { LoadErrorState } from "@/components/load-error-state";
import { PageHeader, PageShell } from "@/components/page-shell";
import { useEeoConsentQuery } from "@/components/profile/diversity-consent";
import { useOpenAIInfo } from "@/components/settings/models-section";
import { SetupAnswersStep } from "@/components/setup/setup-answers-step";
import { SetupDone } from "@/components/setup/setup-done";
import { SetupModelStep } from "@/components/setup/setup-model-step";
import { SetupResumeStep } from "@/components/setup/setup-resume-step";
import { SetupWhereStep } from "@/components/setup/setup-where-step";
import { markSetupSeen } from "@/components/setup/use-first-run";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { loadErrorDetail } from "@/lib/error-text";
import { isLoadFailure } from "@/lib/query-state";
import {
  SETUP_STEPS,
  firstOpenStep,
  formQuestions,
  progressWords,
  stepsDone,
  type AutofillProfile,
  type StepsDone,
} from "@/lib/setup-flow";
import type {
  EeoConsent,
  JobPreferences,
  MarketSettingResponse,
  OpenAIInfo,
  SettingEnvelope,
  SetupStatus,
} from "@/lib/types";
import { cn } from "@/lib/utils";

/** What every step reads, loaded once: a step mounts with its data in hand. */
export type SetupData = {
  status: SetupStatus;
  info: OpenAIInfo;
  market: MarketSettingResponse;
  prefs: JobPreferences;
  profile: AutofillProfile;
  /** The diversity consent: Setup stores a diversity answer only once it is on record. */
  consent: EeoConsent;
};

/** What the diversity question chose, once its consent was given: answer them here, or decline them all. */
export type DiversityChoice = "answer" | "decline" | null;

/**
 * Setup, the first run (design refresh Task 7.1, board "Setup in four steps"): a rail of four steps with a
 * time each and a progress bar, then the step. Every step writes through an endpoint that already exists
 * (backend/tests/test_frontend_setup_flow.py), and which step is done is read from what it wrote
 * (lib/setup-flow.ts `stepsDone`), never stored. It opens on the first step not done. Skip for now is under
 * every step, and Back is free: the rail goes to any step.
 */
export function SetupFlow() {
  // Opened once: Today stops sending a brand-new install here (use-first-run.ts).
  useEffect(() => markSetupSeen(), []);
  const status = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => apiFetch<SetupStatus>("/api/setup/status"),
    refetchOnMount: "always",
  });
  const info = useOpenAIInfo();
  const market = useQuery({
    queryKey: ["settings", "market"],
    queryFn: () => apiFetch<MarketSettingResponse>("/api/settings/market"),
  });
  const prefs = useQuery({
    queryKey: ["settings", "job-preferences"],
    queryFn: () => apiFetch<SettingEnvelope<JobPreferences>>("/api/settings/job-preferences"),
  });
  const profile = useQuery({
    queryKey: ["settings", "autofill"],
    queryFn: () => apiFetch<SettingEnvelope<AutofillProfile>>("/api/settings/autofill"),
  });
  const consent = useEeoConsentQuery();
  const queries = [status, info, market, prefs, profile, consent];
  const loadFailed = queries.some((q) => isLoadFailure(q));
  const failure = queries.find((q) => isLoadFailure(q));

  return (
    <PageShell>
      <PageHeader title="Setup" />
      {loadFailed ? (
        <LoadErrorState
          title="Couldn't load setup."
          detail={loadErrorDetail(failure?.error)}
          retrying={queries.some((q) => q.isFetching)}
          onRetry={() => queries.forEach((q) => void (isLoadFailure(q) && q.refetch()))}
        />
      ) : status.data && info.data && market.data && prefs.data && profile.data && consent.data ? (
        <SetupScreens
          data={{
            status: status.data,
            info: info.data,
            market: market.data,
            prefs: prefs.data.value,
            profile: profile.data.value,
            consent: consent.data.value,
          }}
        />
      ) : (
        <div className="grid items-start gap-10 md:grid-cols-[15rem_minmax(0,1fr)]">
          <Skeleton className="h-72 w-full rounded-corner-md" />
          <Skeleton className="h-96 w-full rounded-corner-lg" />
        </div>
      )}
    </PageShell>
  );
}

function SetupScreens({ data }: { data: SetupData }) {
  const applyIn = data.market.apply_in;
  const done = stepsDone(data.status, applyIn);
  const questions = formQuestions(applyIn, data.market.markets ?? []);
  // The step shown: 0 to 3, and the done screen after them.
  const [step, setStep] = useState(() => firstOpenStep(done));
  const [question, setQuestion] = useState(0);
  const [diversity, setDiversity] = useState<DiversityChoice>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const moved = useRef(false);

  const go = (next: number) => {
    moved.current = true;
    setQuestion(0);
    setStep(Math.max(0, Math.min(SETUP_STEPS.length, next)));
  };
  // A new step takes focus at its heading, so a keyboard or screen reader user starts there. Not on load.
  useEffect(() => {
    if (moved.current) headingRef.current?.focus();
  }, [step]);

  const last = Math.max(0, questions.length - 1);
  const atQuestion = Math.min(question, last);
  const nav =
    SETUP_STEPS[step]?.id === "answers"
      ? {
          onBack: () => (atQuestion > 0 ? setQuestion(atQuestion - 1) : go(step - 1)),
          onContinue: () => (atQuestion < last ? setQuestion(atQuestion + 1) : go(step + 1)),
        }
      : { onBack: step > 0 ? () => go(step - 1) : undefined, onContinue: () => go(step + 1) };

  return (
    <div className="grid items-start gap-10 md:grid-cols-[15rem_minmax(0,1fr)]">
      <SetupRail step={step} done={done} go={go} />
      <div key={step} className="flex min-w-0 max-w-3xl animate-fade-rise flex-col gap-8">
        <StepBody
          step={step}
          data={data}
          done={done}
          headingRef={headingRef}
          questions={questions}
          question={atQuestion}
          onQuestion={setQuestion}
          diversity={diversity}
          onDiversity={setDiversity}
          go={go}
        />
        {step < SETUP_STEPS.length ? <StepNav {...nav} onSkip={() => go(step + 1)} /> : null}
      </div>
    </div>
  );
}

function StepBody({
  step,
  data,
  done,
  headingRef,
  questions,
  question,
  onQuestion,
  diversity,
  onDiversity,
  go,
}: {
  step: number;
  data: SetupData;
  done: StepsDone;
  headingRef: RefObject<HTMLHeadingElement | null>;
  questions: ReturnType<typeof formQuestions>;
  question: number;
  onQuestion: (index: number) => void;
  diversity: DiversityChoice;
  onDiversity: (choice: DiversityChoice) => void;
  go: (step: number) => void;
}) {
  switch (SETUP_STEPS[step]?.id) {
    case "model":
      return <SetupModelStep info={data.info} headingRef={headingRef} />;
    case "resume":
      return <SetupResumeStep status={data.status} headingRef={headingRef} />;
    case "where":
      return <SetupWhereStep market={data.market} prefs={data.prefs} headingRef={headingRef} />;
    case "answers":
      return (
        <SetupAnswersStep
          profile={data.profile}
          consent={data.consent}
          questions={questions}
          question={question}
          onQuestion={onQuestion}
          onDone={() => go(SETUP_STEPS.length)}
          diversity={diversity}
          onDiversity={onDiversity}
          headingRef={headingRef}
        />
      );
    default:
      return (
        <SetupDone
          status={data.status}
          done={done}
          profile={data.profile}
          questions={questions}
          diversity={diversity}
          headingRef={headingRef}
          go={go}
        />
      );
  }
}

/** The rail: how many steps are done, then each step with its time ("Done" once it is), current marked. */
function SetupRail({ step, done, go }: { step: number; done: StepsDone; go: (step: number) => void }) {
  const doneCount = SETUP_STEPS.filter((s) => done[s.id]).length;
  const label = progressWords(doneCount);
  return (
    <nav aria-label="Setup steps" className="flex flex-col gap-6 md:sticky md:top-6">
      <div className="flex flex-col gap-2">
        <span aria-hidden="true" className="text-label-medium text-muted-foreground tabular-nums">
          {label}
        </span>
        <div
          role="progressbar"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={SETUP_STEPS.length}
          aria-valuenow={doneCount}
          className="h-1.5 overflow-hidden rounded-full bg-surface-container"
        >
          <div
            className="h-full rounded-full bg-primary transition-[width] duration-(--duration-medium2) ease-(--ease-standard)"
            style={{ width: `${(doneCount / SETUP_STEPS.length) * 100}%` }}
          />
        </div>
      </div>
      <ol className="flex flex-col gap-1">
        {SETUP_STEPS.map((s, i) => (
          <li key={s.id}>
            <button
              type="button"
              onClick={() => go(i)}
              aria-current={i === step ? "step" : undefined}
              className={cn(
                "flex w-full cursor-pointer items-center gap-3 rounded-corner-md px-3 py-2.5 text-left outline-none transition-colors duration-(--duration-short3) ease-standard focus-visible:ring-3 focus-visible:ring-ring",
                i === step
                  ? "bg-secondary-container text-on-secondary-container"
                  : "hover:bg-surface-container-low",
              )}
            >
              <StepMark index={i} done={done[s.id]} current={i === step} />
              <span className="flex min-w-0 flex-col">
                <span className="text-title-small">{s.title}</span>
                <span className={cn("text-body-small", i === step ? "" : "text-muted-foreground")}>
                  {done[s.id] ? "Done" : s.time}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ol>
      <p className="text-body-small text-muted-foreground">Each answer saves on this computer as you go.</p>
    </nav>
  );
}

function StepMark({ index, done, current }: { index: number; done: boolean; current: boolean }) {
  if (done) return <CONCEPT_ICONS.done aria-hidden="true" className="size-6 shrink-0 text-success" />;
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex size-6 shrink-0 items-center justify-center rounded-full text-label-medium tabular-nums",
        current ? "bg-primary-container text-on-primary-container" : "bg-surface-container text-foreground",
      )}
    >
      {index + 1}
    </span>
  );
}

/** Under every step: Back (none on the first), Skip for now, and Continue, the view's one filled button. */
function StepNav({ onBack, onSkip, onContinue }: { onBack?: () => void; onSkip: () => void; onContinue: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {onBack ? (
        <Button type="button" variant="ghost" size="lg" className="text-primary" onClick={onBack}>
          Back
        </Button>
      ) : null}
      <span className="flex-1" />
      <Button type="button" variant="ghost" size="lg" className="text-muted-foreground" onClick={onSkip}>
        Skip for now
      </Button>
      <Button type="button" size="lg" onClick={onContinue}>
        Continue
      </Button>
    </div>
  );
}
