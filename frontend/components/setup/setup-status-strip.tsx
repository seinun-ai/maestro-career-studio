"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Check } from "lucide-react";

import { buildSetupSteps, type SetupStepView } from "@/components/setup/setup-steps";
import { UploadDialog } from "@/components/setup/upload-dialog";
import { useFocusSection } from "@/lib/use-focus-section";
import { cn } from "@/lib/utils";
import type { SetupStatus } from "@/lib/types";

const PILL =
  "inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";

function pillClass(done: boolean) {
  return cn(
    PILL,
    done
      ? "bg-primary/10 text-primary dark:bg-primary/15 hover:bg-primary/20"
      : "bg-muted text-muted-foreground hover:bg-muted/70 hover:text-foreground",
  );
}

function label(step: SetupStepView) {
  return `${step.label}: ${step.done ? "done" : "not finished"}`;
}

/** Incomplete setup steps for the top of the Profile page — each one actionable.
 *
 * Steps whose answer lives on THIS page focus in place rather than navigating;
 * the step list itself comes from setup-steps.ts, shared with the expanded
 * getting-started card.
 */
export function SetupStatusStrip({
  status,
  loading,
}: {
  status: SetupStatus | undefined;
  loading: boolean;
}) {
  const pathname = usePathname();
  const focus = useFocusSection();
  const [uploadOpen, setUploadOpen] = useState(false);

  if (loading || !status || status.complete) return null;

  const steps = buildSetupSteps(status, pathname);

  return (
    <>
      <div className="flex flex-wrap gap-1.5" aria-label="Getting started progress">
        {steps.map((step) => {
          const icon = step.done ? (
            <Check aria-hidden="true" className="size-3" />
          ) : null;

          if (step.action.kind === "navigate") {
            return (
              <Link
                key={step.id}
                href={step.action.href}
                aria-label={label(step)}
                className={pillClass(step.done)}
              >
                {icon}
                {step.label}
              </Link>
            );
          }

          const onClick =
            step.action.kind === "dialog"
              ? () => setUploadOpen(true)
              : () => focus(step.anchor);

          return (
            <button
              key={step.id}
              type="button"
              onClick={onClick}
              aria-label={label(step)}
              className={pillClass(step.done)}
            >
              {icon}
              {step.label}
            </button>
          );
        })}
      </div>
      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
    </>
  );
}
