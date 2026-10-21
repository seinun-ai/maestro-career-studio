"use client";

import { useId } from "react";

import { CONCEPT_ICONS } from "@/lib/concept-icons";
import type { Step, StepKey } from "@/lib/job-steps";
import { cn } from "@/lib/utils";

const DoneIcon = CONCEPT_ICONS.done;

/** What a screen reader hears after the name: the mark says it to the eye. */
const STATE_WORDS: Record<Step["state"], string> = { done: ", done", current: ", current step", next: "" };

const CELL =
  "flex h-full w-full min-w-0 flex-col gap-2 rounded-corner-sm px-1 pt-1 pb-1.5 text-left";

/** The mark by the name: done is the register's CircleCheck in `success`, the stage's own step a ringed dot in
 * `primary`, a later step its number on a quiet disc. */
function StepMark({ step }: { step: Step }) {
  if (step.state === "done") return <DoneIcon aria-hidden="true" className="size-4 shrink-0 text-success" />;
  if (step.state === "current") {
    return (
      <span aria-hidden="true" className="grid size-4 shrink-0 place-items-center rounded-full border-2 border-primary">
        <span className="size-1.5 rounded-full bg-primary" />
      </span>
    );
  }
  return (
    <span
      aria-hidden="true"
      className="grid size-4 shrink-0 place-items-center rounded-full bg-surface-container text-label-small text-muted-foreground tabular-nums"
    >
      {step.number}
    </span>
  );
}

/** The 4px bar over each step: full when done, empty when later, the current step's own share when the data has
 * one, and a tonal track that claims no share when it has none (lib/job-steps.ts `progress`). Decoration: the
 * state is in the name. */
function StepBar({ progress }: { progress: number | null }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "block h-1 w-full overflow-hidden rounded-full",
        progress === null ? "bg-primary-container" : "bg-surface-container-highest",
      )}
    >
      {progress ? <span className="block h-full rounded-full bg-primary" style={{ width: `${progress * 100}%` }} /> : null}
    </span>
  );
}

/**
 * The job page's four steps, where its tab row was (lib/job-steps.ts says each step's state, number and bar).
 * Each is a 4px bar, then its mark, its name and its one number; no sentences. `current` is the step whose
 * panel shows: its name is in `primary` and it is `aria-current="step"`. A step is a button when it is done,
 * current or reachable (a later step with something to show, such as a draft from before a re-analysis); a
 * later step with nothing to show is plain text, never a disabled button or a tooltip, and nothing is locked.
 * A button's name is "Step N: title" and its state; its number is the description. While `busy` (the gap
 * page's tailor or another write runs), the cells dim and a button stays focusable (`aria-disabled`) while a
 * press does nothing, as `ResumeChips busy` does.
 */
export function JobSteps({
  steps,
  current,
  onSelect,
  busy = false,
}: {
  steps: readonly Step[];
  current: StepKey;
  onSelect: (key: StepKey) => void;
  busy?: boolean;
}) {
  const ids = useId();
  return (
    <nav aria-label="Steps">
      <ol className="grid grid-cols-4 gap-2">
        {steps.map((step) => {
          const shown = step.key === current;
          const button = step.reachable || step.state !== "next";
          const nameId = `${ids}-${step.key}-name`;
          const lineId = `${ids}-${step.key}-line`;
          const body = (
            <>
              <StepBar progress={step.progress} />
              <span className="flex w-full min-w-0 items-center gap-2">
                <StepMark step={step} />
                <span
                  id={nameId}
                  className={cn(
                    "min-w-0 truncate text-title-small",
                    shown ? "text-primary" : step.state === "next" && "text-muted-foreground",
                  )}
                >
                  <span className="sr-only">{`Step ${step.number}: `}</span>
                  {step.title}
                  {STATE_WORDS[step.state] ? <span className="sr-only">{STATE_WORDS[step.state]}</span> : null}
                </span>
                {step.metric ? (
                  <span id={lineId} className="ml-auto shrink-0 text-body-small text-muted-foreground tabular-nums">
                    {step.metric}
                  </span>
                ) : null}
              </span>
            </>
          );
          return (
            <li key={step.key} className="min-w-0">
              {button ? (
                <button
                  type="button"
                  aria-current={shown ? "step" : undefined}
                  aria-labelledby={nameId}
                  aria-describedby={step.metric ? lineId : undefined}
                  aria-disabled={busy || undefined}
                  onClick={() => {
                    if (!busy) onSelect(step.key);
                  }}
                  className={cn(
                    CELL,
                    "hover:bg-surface-container-low transition-colors duration-(--duration-short3) ease-(--ease-standard)",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                    "aria-disabled:cursor-default aria-disabled:opacity-50 aria-disabled:hover:bg-transparent",
                  )}
                >
                  {body}
                </button>
              ) : (
                <div className={cn(CELL, busy && "opacity-50")} aria-current={shown ? "step" : undefined}>
                  {body}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
