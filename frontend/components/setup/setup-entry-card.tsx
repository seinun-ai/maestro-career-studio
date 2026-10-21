"use client";

import { usePathname } from "next/navigation";
import { Circle } from "lucide-react";

import { buildSetupSteps } from "@/components/setup/setup-steps";
import { LeadCard } from "@/components/ui/lead-card";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import type { SetupStatus } from "@/lib/types";

/** A new user: no API key (nothing can read a job) or no resume (nothing to tailor from). */
export function needsSetup(status: SetupStatus): boolean {
  return !status.model_key.done || !status.import_resumes.done;
}

/**
 * Setup's entry card, in Today's lead place while a required step is open (`needsSetup`). It lists the
 * two required steps from the one step list (setup-steps.ts) with their state in words, and its one
 * button opens Setup (`/setup`, components/setup/setup-flow.tsx), which starts on the first step not done.
 */
export function SetupEntryCard({ status }: { status: SetupStatus }) {
  const pathname = usePathname();
  const required = buildSetupSteps(status, pathname).filter((step) => step.required);
  const left = required.filter((step) => !step.done).length;
  if (left === 0) return null;
  return (
    <LeadCard
      eyebrow="Set up"
      action={{ label: left === required.length ? "Start setup" : "Finish setup", href: "/setup" }}
    >
      <h2 className="text-headline-small">
        {left === 1 ? "One step before your first job" : "Two steps before your first job"}
      </h2>
      <ol className="flex flex-col gap-3">
        {required.map((step) => (
          <li key={step.id} className="flex items-start gap-3">
            {step.done ? (
              <CONCEPT_ICONS.done aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-success" />
            ) : (
              <Circle aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            )}
            <span className="flex min-w-0 flex-col">
              <span className="flex flex-wrap items-baseline gap-x-2 text-title-small">
                {step.title}
                {step.done ? <span className="text-success text-label-medium">Done</span> : null}
              </span>
              {step.detail ? <span className="text-muted-foreground text-body-small">{step.detail}</span> : null}
            </span>
          </li>
        ))}
      </ol>
    </LeadCard>
  );
}
