"use client";

import { AlertTriangle, CircleCheck, CircleHelp, ShieldAlert } from "lucide-react";
import { GuardedLink as Link } from "@/components/guarded-link";
import type { ReactNode } from "react";

import { anchorHref } from "@/lib/settings-tabs";
import type { Job, KnockoutCheck, KnockoutScan, KnockoutStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_COPY: Record<
  KnockoutStatus,
  { label: string; detail: string; icon: ReactNode; tone: string }
> = {
  conflict: {
    label: "You may not qualify",
    detail: "The job lists a requirement your profile doesn't meet.",
    icon: <ShieldAlert />,
    tone: "border-destructive/40 bg-destructive/5 text-destructive",
  },
  // `clear` is any pass or warning (knockout.py): a warning row can sit under it, and a check the
  // profile could not answer is left out, so it claims only that nothing conflicts.
  clear: {
    label: "Nothing rules you out",
    detail: "Nothing the job lists conflicts with your profile.",
    icon: <CircleCheck />,
    tone: "border-emerald-500/40 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400",
  },
  incomplete_profile: {
    label: "Your profile is missing an answer",
    detail: "Add it to your profile to check this job.",
    icon: <CircleHelp />,
    tone: "border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-400",
  },
  // Deliberately NOT phrased as a pass: nothing the job lists could be checked.
  unstated: {
    label: "No requirements listed",
    detail: "Nothing here to check. That doesn't mean you qualify.",
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
 *  fieldsets in `settings/autofill-section.tsx`; `anchorHref` adds the Autofill
 *  tab, so the server renders the panel that holds them. */
function autofillHref(scan: KnockoutScan): string {
  const missing = scan.checks.find((c) => c.result === "profile_missing");
  const group = missing ? CHECK_GROUP[missing.kind] : undefined;
  return anchorHref("/profile", group ? `autofill-${group}` : "autofill");
}

type Unchecked = { what: string; field: string; href: string; link: string };

/**
 * What the job lists that the scan could not compare. knockout.py leaves the salary check out when the
 * profile has no desired salary (or the pay is not yearly) and the experience check out when the profile
 * has no years, and says nothing, so "unstated" read "No requirements listed" on a job listing both.
 * The yearly rule mirrors `_salary_check`.
 */
function uncheckedItems(job: Job, scan: KnockoutScan): Unchecked[] {
  const has = (kind: KnockoutCheck["kind"]) => scan.checks.some((c) => c.kind === kind);
  const ceiling = Number(job.salary_max ?? job.salary_min ?? Number.NaN);
  const yearly =
    Number.isFinite(ceiling) &&
    (job.salary_period === "year" || (job.salary_period == null && ceiling >= 10000));
  const items: Unchecked[] = [];
  if (yearly && !has("salary")) {
    items.push({
      what: "pay",
      field: "desired salary",
      href: anchorHref("/profile", "autofill-preferences"),
      link: "Add your desired salary",
    });
  }
  if (job.years_experience_min != null && !has("experience")) {
    items.push({
      what: "experience",
      field: "years of experience",
      href: anchorHref("/profile", "job-preferences-years"),
      link: "Add your years of experience",
    });
  }
  return items;
}

function uncheckedSentence(items: Unchecked[]): string {
  const what = items.map((i) => i.what).join(" or ");
  const fields = items.map((i) => i.field).join(" and ");
  return `Can't check ${what} yet: add your ${fields} to your profile.`;
}

export function JobKnockoutCard({
  scan,
  job,
}: {
  scan: KnockoutScan | null | undefined;
  job: Job;
}) {
  if (!scan) return null;
  const unchecked = uncheckedItems(job, scan);
  const missing = unchecked.length > 0 ? uncheckedSentence(unchecked) : null;
  // A job that lists pay or years the profile can't answer is not "no requirements listed".
  const notChecked = scan.status === "unstated" && missing !== null;
  const copy = notChecked
    ? { ...STATUS_COPY.unstated, label: "Not checked yet", detail: missing }
    : STATUS_COPY[scan.status];
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
      {missing && !notChecked ? <p className="text-muted-foreground mt-1 text-xs">{missing}</p> : null}
      {unchecked.map((item) => (
        <Link
          key={item.what}
          href={item.href}
          className="mt-2 mr-3 inline-block text-xs underline underline-offset-2"
        >
          {item.link}
        </Link>
      ))}
      {scan.status === "incomplete_profile" && (
        <Link
          href={autofillHref(scan)}
          className="mt-2 inline-block text-xs underline underline-offset-2"
        >
          Complete your profile
        </Link>
      )}
    </div>
  );
}
