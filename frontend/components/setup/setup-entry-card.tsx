"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { Circle } from "lucide-react";

import { buildSetupSteps } from "@/components/setup/setup-steps";
import { UploadDialog } from "@/components/setup/upload-dialog";
import { LeadCard, type LeadAction } from "@/components/ui/lead-card";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { anchorHref } from "@/lib/settings-tabs";
import type { SetupStatus } from "@/lib/types";

/** Each required step's button: the Getting started card's words (getting-started-card.tsx). */
const ACTION_LABELS: Record<string, string> = {
  model_key: "Add API key",
  import: "Import resumes",
};

/** A new user: no API key (nothing can read a job) or no resume (nothing to tailor from). */
export function needsSetup(status: SetupStatus): boolean {
  return !status.model_key.done || !status.import_resumes.done;
}

/**
 * Setup's entry card, in Today's lead place while a required step is open (`needsSetup`). It lists the
 * two required steps from the one step list (setup-steps.ts) with their state in words, and its one
 * button is the first step not done: the key on Settings, the resume import in place.
 */
export function SetupEntryCard({ status }: { status: SetupStatus }) {
  const pathname = usePathname();
  const [uploadOpen, setUploadOpen] = useState(false);
  const required = buildSetupSteps(status, pathname).filter((step) => step.required);
  const next = required.find((step) => !step.done);
  if (!next) return null;
  const left = required.filter((step) => !step.done).length;
  const label = ACTION_LABELS[next.id] ?? next.title;
  const action: LeadAction =
    next.action.kind === "dialog"
      ? { label, onClick: () => setUploadOpen(true) }
      : { label, href: anchorHref(next.home, next.anchor) };
  return (
    <>
      <LeadCard eyebrow="Set up" action={action}>
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
      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
    </>
  );
}
