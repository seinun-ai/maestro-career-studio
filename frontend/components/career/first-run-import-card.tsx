"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sparkles, X } from "lucide-react";

import { ResumeImportDialog } from "@/components/career/resume-import-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { KBEntitySummary } from "@/lib/types";

const DISMISS_KEY = "maestro-cs:first-run-import-dismissed";

/** Shown until the user has any Career KB content.
 *
 * The signal is deliberately "the KB is empty", not "there are no base resumes
 * except the shipped demo": keying off a hard-coded slug would add a second
 * magic-slug rule of the kind the codebase is already trying to retire, and the
 * KB is what import actually produces — so the card clears itself for the right
 * reason.
 *
 * Dismissible on purpose. A first-run wizard that traps the user is worse than
 * no guidance; the same import stays available from the Career KB page forever.
 */
export function FirstRunImportCard() {
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(
    () => typeof window !== "undefined" && window.localStorage.getItem(DISMISS_KEY) === "1",
  );

  const entities = useQuery({
    queryKey: ["kb", "entities"],
    queryFn: () => apiFetch<KBEntitySummary[]>("/api/kb/entities"),
  });

  // Never flash the card while loading, and never show it once the KB has content.
  if (dismissed || entities.isLoading || (entities.data?.length ?? 0) > 0) return null;

  return (
    <>
      <Card className="border-primary/20 bg-primary/[0.03]">
        <CardContent className="flex flex-wrap items-start justify-between gap-4 pt-6">
          <div className="flex gap-3">
            <Sparkles className="text-primary mt-0.5 size-5 shrink-0" />
            <div className="space-y-1">
              <p className="text-sm font-medium">Start with the resumes you already have</p>
              <p className="text-muted-foreground text-sm">
                Each one becomes a base resume, and their shared history
                becomes your Career Knowledge Base.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Button size="sm" onClick={() => setOpen(true)}>
              Import resumes
            </Button>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Dismiss"
              onClick={() => {
                window.localStorage.setItem(DISMISS_KEY, "1");
                setDismissed(true);
              }}
            >
              <X className="size-4" />
            </Button>
          </div>
        </CardContent>
      </Card>
      <ResumeImportDialog open={open} onOpenChange={setOpen} />
    </>
  );
}
