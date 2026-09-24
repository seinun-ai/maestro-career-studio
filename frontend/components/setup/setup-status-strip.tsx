"use client";

import { useState } from "react";
import { GuardedLink as Link } from "@/components/guarded-link";
import { usePathname } from "next/navigation";
import { Check } from "lucide-react";

import { buildSetupSteps, type SetupStepView } from "@/components/setup/setup-steps";
import { UploadDialog } from "@/components/setup/upload-dialog";
import { cn } from "@/lib/utils";
import type { SetupStatus } from "@/lib/types";

const PILL =
  "inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background";

function pillClass(done: boolean) {
  return cn(
    PILL,
    done
      ? "bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"
      : "bg-muted text-muted-foreground hover:bg-muted/70 hover:text-foreground",
  );
}

function label(step: SetupStepView) {
  // A comma, not a colon: a pill's own text can hold one ("Autofill: 40% done").
  return `${step.label}, ${step.done ? "done" : "not finished"}`;
}

/** Incomplete setup steps for the top of the Profile page — each one actionable.
 *
 * Steps whose answer lives on THIS page focus in place rather than navigating,
 * through the page's own focus hook (`focus`): one per page, so a hash
 * landing polls and rings once. The step list itself comes from setup-steps.ts,
 * shared with the expanded getting-started card.
 */
export function SetupStatusStrip({
  status,
  loading,
  focus,
}: {
  status: SetupStatus | undefined;
  loading: boolean;
  focus: (anchor: string) => void;
}) {
  const pathname = usePathname();
  const [uploadOpen, setUploadOpen] = useState(false);

  if (loading || !status || status.complete) return null;

  // A healthy engines row is not an outstanding setup step: Typst always ships,
  // so it would sit here as a permanent done pill on every install. The strip is
  // for what is still unfinished; the full row lives in the getting-started card.
  const steps = buildSetupSteps(status, pathname).filter(
    (step) => !(step.id === "engines" && step.done),
  );

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
