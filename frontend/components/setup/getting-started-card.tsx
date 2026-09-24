"use client";

import { GuardedLink as Link } from "@/components/guarded-link";
import { useState } from "react";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Circle, CircleCheck, X } from "lucide-react";

import { NewBaseResumeDialog } from "@/components/base-resumes/new-base-resume-dialog";
import { LoadErrorState } from "@/components/load-error-state";
import { buildSetupSteps } from "@/components/setup/setup-steps";
import { UploadDialog } from "@/components/setup/upload-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import { errorDetail } from "@/lib/error-text";
import { isLoadFailure } from "@/lib/query-state";
import { anchorHref } from "@/lib/settings-tabs";
import type { SetupStatus } from "@/lib/types";

type Suggestion = SetupStatus["suggested_bases"][number];

const DISMISS_KEY = "maestro-cs:getting-started-dismissed";

/** Verb for each step's action button. The step list itself lives in
 *  setup-steps.ts — only this presentational wording belongs here. */
const ACTION_LABELS: Record<string, string> = {
  model_key: "Add API key",
  import: "Import resumes",
  autofill: "Add answers",
  job_preferences: "Set preferences",
  persona: "Write persona",
  template: "Choose template",
  engines: "See templates",
};

/** A dismissible setup checklist for the tracker before any jobs are captured. */
export function GettingStartedCard() {
  const [dismissed, setDismissed] = useState(
    () =>
      typeof window !== "undefined" &&
      window.localStorage.getItem(DISMISS_KEY) === "1",
  );
  // One kept dialog per suggestion the user has opened (in open order):
  // closing A and opening B keeps A's draft for when A comes back. Each keeps
  // its label, which its role picker shows in place of the key.
  const [opened, setOpened] = useState<Suggestion[]>([]);
  const [openRole, setOpenRole] = useState<string | null>(null);
  const compose = (suggestion: Suggestion) => {
    setOpened((all) =>
      all.some((s) => s.role_category === suggestion.role_category)
        ? all
        : [...all, suggestion],
    );
    setOpenRole(suggestion.role_category);
  };
  const [uploadOpen, setUploadOpen] = useState(false);
  const pathname = usePathname();
  const setupStatus = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => apiFetch<SetupStatus>("/api/setup/status"),
    refetchOnMount: "always",
  });

  const status = setupStatus.data;
  if (dismissed) return null;
  if (isLoadFailure(setupStatus)) {
    return (
      <LoadErrorState
        className="py-8"
        title="Couldn't load setup progress."
        detail={errorDetail(setupStatus.error)}
        retrying={setupStatus.isFetching}
        onRetry={() => void setupStatus.refetch()}
      />
    );
  }
  if (setupStatus.isLoading || !status || status.complete) return null;

  // A PDF step with nothing left to do is not a step (the strip drops it too);
  // it stays while a few templates still need TeX.
  const rows = buildSetupSteps(status, pathname).filter(
    (row) => !(row.id === "engines" && row.done && status.engines.pdflatex.available),
  );
  return (
    <>
      <Card className="border-primary/20 bg-primary/[0.03]">
        <CardContent className="pt-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium">Getting started</p>
              <p className="text-muted-foreground mt-0.5 text-sm">
                Do the required steps first.
              </p>
            </div>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Hide getting started"
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
                    <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      {row.title}
                      {row.required && !row.done ? (
                        <Badge variant="outline" className="font-normal">
                          Required
                        </Badge>
                      ) : null}
                    </p>
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
                      render={<Link href={anchorHref(row.home, row.anchor)} />}
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
                You want these roles but have no base resume for them yet.
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
                      onClick={() => compose(suggestion)}
                    >
                      Build from career history
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </CardContent>
      </Card>
      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
      {opened.map((suggestion) => (
        <NewBaseResumeDialog
          key={suggestion.role_category}
          open={openRole === suggestion.role_category}
          initialMode="kb"
          initialRole={suggestion}
          existingResumes={[]}
          onOpenChange={(next) => {
            if (!next) setOpenRole(null);
          }}
        />
      ))}
    </>
  );
}
