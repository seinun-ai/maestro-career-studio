"use client";

import { AlertTriangle, CircleCheck, CircleHelp, ShieldAlert } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import type { KnockoutScan, KnockoutStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_COPY: Record<
  KnockoutStatus,
  { label: string; detail: string; icon: ReactNode; tone: string }
> = {
  conflict: {
    label: "Knock-out conflict",
    detail: "A stated requirement contradicts your profile.",
    icon: <ShieldAlert />,
    tone: "border-destructive/40 bg-destructive/5 text-destructive",
  },
  clear: {
    label: "Stated requirements clear",
    detail:
      "Work authorization, OPT, salary, and experience match your profile where the posting states them.",
    icon: <CircleCheck />,
    tone: "border-emerald-500/40 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400",
  },
  incomplete_profile: {
    label: "Profile can’t answer a stated requirement",
    detail: "Fill the missing answer in Settings to screen this posting.",
    icon: <CircleHelp />,
    tone: "border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-400",
  },
  // Deliberately NOT phrased as a pass: the posting states nothing to check.
  unstated: {
    label: "No screening requirements stated",
    detail:
      "The posting states no work-authorization, OPT, salary, or experience screens — that’s absence of signal, not a green light.",
    icon: <CircleHelp />,
    tone: "border-border bg-muted/40 text-muted-foreground",
  },
};

/** Rows worth a line of their own; passes are covered by the headline. */
const ROW_RESULTS = new Set(["conflict", "warning", "profile_missing"]);

export function JobKnockoutCard({ scan }: { scan: KnockoutScan | null | undefined }) {
  if (!scan) return null;
  const copy = STATUS_COPY[scan.status];
  const rows = scan.checks.filter((c) => ROW_RESULTS.has(c.result) && c.message);

  return (
    <div
      role="status"
      className={cn("rounded-lg border px-4 py-3 text-sm", copy.tone)}
    >
      <div className="flex items-center gap-2 font-medium [&>svg]:size-4">
        {copy.icon}
        {copy.label}
      </div>
      <p className="text-muted-foreground mt-1 text-xs">{copy.detail}</p>
      {rows.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs">
          {rows.map((c) => (
            <li key={c.kind} className="flex items-start gap-1.5">
              <AlertTriangle className="mt-0.5 size-3 shrink-0" />
              <span>{c.message}</span>
            </li>
          ))}
        </ul>
      )}
      {scan.status === "incomplete_profile" && (
        <Link
          href="/settings"
          className="mt-2 inline-block text-xs underline underline-offset-2"
        >
          Complete your autofill profile
        </Link>
      )}
    </div>
  );
}
