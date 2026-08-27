"use client";

import { AlertTriangle, CircleCheck, CircleHelp, ShieldAlert } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import type { KnockoutCheck, KnockoutScan, KnockoutStatus } from "@/lib/types";
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
    detail: "Fill the missing answer in your profile to screen this posting.",
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

/** Which autofill group answers each knock-out check.
 *
 *  `experience` has no autofill field — it is scored off the resume — so it
 *  maps to nothing and the link falls back to the section. */
const CHECK_GROUP: Partial<Record<KnockoutCheck["kind"], string>> = {
  work_authorization: "work_auth",
  opt: "work_auth",
  salary: "preferences",
};

/** Deep-link at the group holding the gap, not the section.
 *
 *  Same rule as `setup-steps.ts:112`: landing on a 900-line form and hunting
 *  for the unanswered question is barely better than landing on the wrong
 *  page, which is what this link used to do — it pointed at `/settings`, where
 *  the autofill card has never lived. The `autofill-<group>` ids are the
 *  fieldsets in `settings/autofill-section.tsx`. */
function autofillHref(scan: KnockoutScan): string {
  const missing = scan.checks.find((c) => c.result === "profile_missing");
  const group = missing ? CHECK_GROUP[missing.kind] : undefined;
  return group ? `/profile#autofill-${group}` : "/profile#autofill";
}

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
          href={autofillHref(scan)}
          className="mt-2 inline-block text-xs underline underline-offset-2"
        >
          Complete your autofill profile
        </Link>
      )}
    </div>
  );
}
