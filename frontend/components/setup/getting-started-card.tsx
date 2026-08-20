"use client";

import Link from "next/link";
import { useState } from "react";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Circle, CircleCheck, X } from "lucide-react";

import { NewBaseResumeDialog } from "@/components/base-resumes/new-base-resume-dialog";
import { LoadErrorState } from "@/components/load-error-state";
import { buildSetupSteps } from "@/components/setup/setup-steps";
import { UploadDialog } from "@/components/setup/upload-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { SetupStatus } from "@/lib/types";

const DISMISS_KEY = "maestro-cs:getting-started-dismissed";

/** Verb for each step's action button. The step list itself lives in
 *  setup-steps.ts — only this presentational wording belongs here. */
const ACTION_LABELS: Record<string, string> = {
  import: "Import resumes",
  autofill: "Complete autofill",
  job_preferences: "Set preferences",
  persona: "Write persona",
  template: "Choose template",
};

/** A dismissible setup checklist for the tracker before any jobs are captured. */
export function GettingStartedCard() {
  const [dismissed, setDismissed] = useState(
    () =>
      typeof window !== "undefined" &&
      window.localStorage.getItem(DISMISS_KEY) === "1",
  );
  const [composeSuggestion, setComposeSuggestion] = useState<
    SetupStatus["suggested_bases"][number] | null
  >(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const pathname = usePathname();
  const setupStatus = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => apiFetch<SetupStatus>("/api/setup/status"),
    refetchOnMount: "always",
  });

  const status = setupStatus.data;
  if (dismissed) return null;
  if (setupStatus.isError) {
    return (
      <LoadErrorState
        className="py-8"
        title="Couldn't load setup progress."
        detail={(setupStatus.error as Error)?.message}
        retrying={setupStatus.isFetching}
        onRetry={() => void setupStatus.refetch()}
      />
    );
  }
  if (setupStatus.isLoading || !status || status.complete) return null;

  const rows = buildSetupSteps(status, pathname);
  return (
    <>
      <Card className="border-primary/20 bg-primary/[0.03]">
        <CardContent className="pt-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium">Getting started</p>
              <p className="text-muted-foreground mt-0.5 text-sm">
                Complete the essentials for a smoother application process.
              </p>
            </div>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Dismiss getting started checklist"
              onClick={() => {
                window.localStorage.setItem(DISMISS_KEY, "1");
                setDismissed(true);
              }}
            >
              <X className="size-4" />
            </Button>
          </div>

          <ul className="mt-5 divide-y">
            {rows.map((row) => {
              const Icon = row.done ? CircleCheck : Circle;
              return (
                <li
                  key={row.id}
                  className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3 first:pt-0 last:pb-0"
                >
                  <Icon
                    aria-hidden="true"
                    className={
                      row.done
                        ? "text-primary size-4"
                        : "text-muted-foreground size-4"
                    }
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{row.title}</p>
                    {row.detail ? (
                      <p className="text-muted-foreground mt-0.5 text-xs">
                        {row.detail}
                      </p>
                    ) : null}
                  </div>
                  {/* This card lives on routes that are no step's home, so
                      `focus` never resolves here. Linking to home#anchor is
                      correct for both link kinds anyway, and stays correct if
                      the card is ever rendered somewhere else. */}
                  {row.action.kind === "dialog" ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => setUploadOpen(true)}
                    >
                      {ACTION_LABELS[row.id]}
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      nativeButton={false}
                      render={<Link href={`${row.home}#${row.anchor}`} />}
                    >
                      {ACTION_LABELS[row.id]}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>

          {status.suggested_bases.length > 0 ? (
            <div className="mt-5 border-t pt-4">
              <p className="text-muted-foreground text-xs">
                You target these roles but have no base resume for them. Choose
                the Career KB entries that belong on each one.
              </p>
              <ul className="mt-3 space-y-2">
                {status.suggested_bases.map((suggestion) => (
                  <li
                    key={suggestion.role_category}
                    className="flex items-center justify-between gap-3"
                  >
                    <span className="text-sm font-medium">{suggestion.label}</span>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => setComposeSuggestion(suggestion)}
                    >
                      Compose from KB
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </CardContent>
      </Card>
      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
      {composeSuggestion ? (
        <NewBaseResumeDialog
          key={composeSuggestion.role_category}
          open
          initialMode="kb"
          initialRole={composeSuggestion.role_category}
          existingResumes={[]}
          onOpenChange={(next) => {
            if (!next) setComposeSuggestion(null);
          }}
        />
      ) : null}
    </>
  );
}
