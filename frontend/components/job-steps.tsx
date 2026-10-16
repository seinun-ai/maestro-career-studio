"use client";

import { Check } from "lucide-react";

import type { Step, StepKey } from "@/lib/job-steps";
import { cn } from "@/lib/utils";

/** The disc by the step's state: a done tick, the stage's own step ringed, a later one quiet. */
const DISC: Record<Step["state"], string> = {
  done: "bg-success text-primary-foreground",
  current: "border-2 border-ring text-primary",
  next: "bg-surface-container text-muted-foreground",
};

const CELL =
  "flex h-full w-full min-w-0 items-start gap-3 rounded-t-corner-sm border-b-2 px-3 pt-2 pb-2.5 text-left";

/**
 * The job page's four steps, where its tab row was (lib/job-steps.ts says each step's state and line).
 * `current` is the step whose panel shows: its cell is underlined and `aria-current="step"`. A done or
 * current step is a button (done may follow current: a draft from before a re-analysis stays reachable);
 * a step with nothing to show yet is plain text, never a disabled button or a tooltip: its line says what
 * opens it, and nothing is locked.
 */
export function JobSteps({
  steps,
  current,
  onSelect,
}: {
  steps: readonly Step[];
  current: StepKey;
  onSelect: (key: StepKey) => void;
}) {
  return (
    <nav aria-label="Steps" className="border-b">
      <ol className="-mb-px grid grid-cols-4">
        {steps.map((step) => {
          const shown = step.key === current;
          const body = (
            <>
              <span
                aria-hidden="true"
                className={cn(
                  "grid size-6 shrink-0 place-items-center rounded-full text-label-medium tabular-nums",
                  DISC[step.state],
                )}
              >
                {step.state === "done" ? <Check className="size-3.5" /> : step.number}
              </span>
              <span className="min-w-0">
                <span className={cn("block text-title-small", step.state === "next" && "text-muted-foreground")}>
                  <span className="sr-only">{`Step ${step.number}: `}</span>
                  {step.title}
                  {step.state === "done" ? <span className="sr-only">, done</span> : null}
                </span>
                {step.summary ? (
                  <span className="text-muted-foreground block text-body-small">{step.summary}</span>
                ) : null}
              </span>
            </>
          );
          const edge = shown ? "border-primary" : "border-transparent";
          return (
            <li key={step.key} className="min-w-0">
              {step.state === "next" ? (
                <div className={cn(CELL, edge)} aria-current={shown ? "step" : undefined}>
                  {body}
                </div>
              ) : (
                <button
                  type="button"
                  aria-current={shown ? "step" : undefined}
                  onClick={() => onSelect(step.key)}
                  className={cn(
                    CELL,
                    edge,
                    "hover:bg-surface-container-low transition-colors duration-(--duration-short3) ease-(--ease-standard)",
                    "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
                  )}
                >
                  {body}
                </button>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
