"use client";

import { useId } from "react";
import { Check } from "lucide-react";

import type { Step, StepKey } from "@/lib/job-steps";
import { cn } from "@/lib/utils";

/** The disc by the step's state: a done tick, the stage's own step ringed, a later one quiet. */
const DISC: Record<Step["state"], string> = {
  done: "bg-success-container text-on-success-container",
  current: "border-2 border-ring text-primary",
  next: "bg-surface-container text-muted-foreground",
};

/** What a screen reader hears after the name: the disc says it to the eye. */
const STATE_WORDS: Record<Step["state"], string> = { done: ", done", current: ", current step", next: "" };

const CELL =
  "flex h-full w-full min-w-0 items-start gap-3 rounded-t-corner-sm border-b-2 px-3 pt-2 pb-2.5 text-left";

/**
 * The job page's four steps, where its tab row was (lib/job-steps.ts says each step's state and line).
 * `current` is the step whose panel shows: its cell is underlined and `aria-current="step"`. A step is a
 * button when it is done, current or reachable (a later step with something to show, such as a draft from
 * before a re-analysis); a later step with nothing to show is plain text, never a disabled button or a
 * tooltip: its line says what opens it, and nothing is locked. A button's name is "Step N: title" and its
 * state; its line is the description. While `busy` (the gap page's tailor or another write runs), the cells dim
 * and a button stays focusable (`aria-disabled`) while a press does nothing, as `ResumeChips busy` does.
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
    <nav aria-label="Steps" className="border-b">
      <ol className="-mb-px grid grid-cols-4">
        {steps.map((step) => {
          const shown = step.key === current;
          const button = step.reachable || step.state !== "next";
          const nameId = `${ids}-${step.key}-name`;
          const lineId = `${ids}-${step.key}-line`;
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
                <span
                  id={nameId}
                  className={cn("block text-title-small", step.state === "next" && "text-muted-foreground")}
                >
                  <span className="sr-only">{`Step ${step.number}: `}</span>
                  {step.title}
                  {STATE_WORDS[step.state] ? <span className="sr-only">{STATE_WORDS[step.state]}</span> : null}
                </span>
                {step.summary ? (
                  <span id={lineId} className="text-muted-foreground block text-body-small">
                    {step.summary}
                  </span>
                ) : null}
              </span>
            </>
          );
          const edge = shown ? "border-primary" : "border-transparent";
          return (
            <li key={step.key} className="min-w-0">
              {button ? (
                <button
                  type="button"
                  aria-current={shown ? "step" : undefined}
                  aria-labelledby={nameId}
                  aria-describedby={step.summary ? lineId : undefined}
                  aria-disabled={busy || undefined}
                  onClick={() => {
                    if (!busy) onSelect(step.key);
                  }}
                  className={cn(
                    CELL,
                    edge,
                    "hover:bg-surface-container-low transition-colors duration-(--duration-short3) ease-(--ease-standard)",
                    "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
                    "aria-disabled:cursor-default aria-disabled:opacity-50 aria-disabled:hover:bg-transparent",
                  )}
                >
                  {body}
                </button>
              ) : (
                <div className={cn(CELL, edge, busy && "opacity-50")} aria-current={shown ? "step" : undefined}>
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
