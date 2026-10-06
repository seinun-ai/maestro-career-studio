"use client";

import {
  CircleCheck,
  CircleDashed,
  CircleHelp,
  CircleX,
  Minus,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { GuardedLink as Link } from "@/components/guarded-link";

import { anchorHref } from "@/lib/settings-tabs";
import type { Job, KnockoutCheck, KnockoutScan } from "@/lib/types";
import { cn } from "@/lib/utils";

/** The word each check answers to, on its chip and in front of its server message. */
const LABEL_BY_KIND: Record<KnockoutCheck["kind"], string> = {
  work_authorization: "Work auth",
  opt: "OPT",
  salary: "Pay",
  experience: "Experience",
  on_site: "On-site",
};

type Summary = { icon: LucideIcon; word: string; tone: string; iconTone?: string };

/** One chip per check result. Icons are the register's (lib/concept-icons.ts): done, fails, warning, unknown,
 *  none, notRun. Colour never stands alone: every chip carries its word. A pass stays neutral ("good news is quiet"). */
const SUMMARY_BY_RESULT: Record<KnockoutCheck["result"], Summary> = {
  pass: { icon: CircleCheck, word: "OK", tone: "bg-surface-container", iconTone: "text-success" },
  conflict: { icon: CircleX, word: "Conflict", tone: "bg-error-container text-on-error-container" },
  warning: { icon: TriangleAlert, word: "Warning", tone: "bg-warning-container text-on-warning-container" },
  profile_missing: { icon: CircleHelp, word: "Add answer", tone: "bg-surface-container" },
  job_unstated: { icon: Minus, word: "Not listed", tone: "bg-surface-container text-muted-foreground" },
};
const NOT_RUN: Summary = { icon: CircleDashed, word: "Not run", tone: "bg-surface-container" };

/** Rows worth a line of their own; passes and unstated checks are covered by their chip. */
const ROW_RESULTS = new Set(["conflict", "warning", "profile_missing"]);

/** Which autofill group answers each knock-out check.
 *
 *  `experience` has no autofill field — it is scored off the resume — so it
 *  maps to nothing and the link falls back to the section. */
const CHECK_GROUP: Partial<Record<KnockoutCheck["kind"], string>> = {
  work_authorization: "work_auth",
  opt: "work_auth",
  salary: "preferences",
  on_site: "preferences",
};

/** Deep-link at the group holding the gap, not the section.
 *
 *  Same rule as `setup-steps.ts:112`: landing on a 900-line form and hunting
 *  for the unanswered question is barely better than landing on the wrong
 *  page, which is what this link used to do — it pointed at `/settings`, where
 *  the autofill card has never lived. The `autofill-<group>` ids are the
 *  fieldsets in `settings/autofill-section.tsx`; `anchorHref` adds the Autofill
 *  tab, so the server renders the panel that holds them. */
function autofillHref(kind: KnockoutCheck["kind"] | undefined): string {
  const group = kind ? CHECK_GROUP[kind] : undefined;
  return anchorHref("/profile", group ? `autofill-${group}` : "autofill");
}

type Unchecked = { kind: KnockoutCheck["kind"]; what: string; field: string; href: string; link: string };

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
      kind: "salary",
      what: "pay",
      // Autofill's Desired salary (knockout._salary_check), not Job preferences' Minimum salary.
      field: "desired salary (Profile › Autofill)",
      href: anchorHref("/profile", "autofill-preferences"),
      link: "Add your desired salary",
    });
  }
  if (job.years_experience_min != null && !has("experience")) {
    items.push({
      kind: "experience",
      what: "experience",
      field: "years of experience (Profile › About you)",
      href: anchorHref("/profile", "job-preferences-years"),
      link: "Add your years of experience",
    });
  }
  return items;
}

const CHIP = "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-label-medium [&>svg]:size-3.5";

/** One check's chip. Its accessible text is "Label: word"; a chip that can be acted on links to its field. */
function CheckChip({ label, summary, href, hint }: { label: string; summary: Summary; href?: string; hint?: string }) {
  const { icon: Icon, word, tone, iconTone } = summary;
  const body = (
    <>
      <Icon aria-hidden className={iconTone} />
      {`${label}: ${word}`}
    </>
  );
  return href ? (
    <Link href={href} title={hint} className={cn(CHIP, tone, "underline-offset-2 hover:underline")}>
      {body}
    </Link>
  ) : (
    <span className={cn(CHIP, tone)}>{body}</span>
  );
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
  // A job that lists pay or years the profile can't answer is not "no requirements listed".
  const notChecked = scan.status === "unstated" && unchecked.length > 0;
  const rows = scan.checks.filter((c) => ROW_RESULTS.has(c.result) && c.message);
  const conflict = scan.checks.find((c) => c.result === "conflict");
  const missing = scan.checks.find((c) => c.result === "profile_missing");

  const strip = (
    <>
      <ul aria-label="Knock-out checks" className="flex flex-wrap gap-1.5">
        {scan.checks.map((c) => {
          const summary = SUMMARY_BY_RESULT[c.result];
          return (
            <li key={c.kind}>
              <CheckChip
                label={LABEL_BY_KIND[c.kind]}
                summary={summary}
                href={c.result === "profile_missing" ? autofillHref(c.kind) : undefined}
              />
            </li>
          );
        })}
        {unchecked.map((item) => (
          <li key={item.kind}>
            <CheckChip label={LABEL_BY_KIND[item.kind]} summary={NOT_RUN} href={item.href} hint={item.link} />
          </li>
        ))}
      </ul>
      {rows.length > 0 && (
        <ul className="mt-2 space-y-1 text-body-small">
          {rows.map((c) => {
            const Icon = SUMMARY_BY_RESULT[c.result].icon;
            return (
              <li key={c.kind} className="flex items-start gap-1.5">
                <Icon aria-hidden className="mt-0.5 size-3 shrink-0" />
                <span>{`${LABEL_BY_KIND[c.kind]}: ${c.message}`}</span>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
  const hasStrip = scan.checks.length > 0 || unchecked.length > 0;
  const stripBlock = hasStrip ? <div className="mt-2">{strip}</div> : null;

  if (scan.status === "conflict" || scan.status === "incomplete_profile") {
    const isConflict = scan.status === "conflict";
    const Icon = isConflict ? CircleX : CircleHelp;
    return (
      <div role="status" className="space-y-2">
        <div
          className={cn(
            "rounded-corner-md px-4 py-3 text-body-medium",
            isConflict
              ? "border border-transparent bg-error-container text-on-error-container"
              : "bg-warning-container text-on-warning-container",
          )}
        >
          <div className="flex items-center gap-2 font-medium [&>svg]:size-4">
            <Icon aria-hidden />
            {isConflict
              ? `You may not qualify${conflict ? `: ${LABEL_BY_KIND[conflict.kind]}` : ""}`
              : "Your profile is missing an answer"}
          </div>
          {isConflict ? null : (
            <>
              <p className="mt-1 text-body-small">Add it to your profile to check this job.</p>
              <Link
                href={autofillHref(missing?.kind)}
                className="mt-2 inline-block text-body-small underline underline-offset-2"
              >
                Complete your profile
              </Link>
            </>
          )}
        </div>
        {hasStrip ? <div className="rounded-corner-md border border-border px-3 py-2">{strip}</div> : null}
      </div>
    );
  }

  // `clear` is any pass or warning (knockout.py): a warning chip can sit under it, and a check the
  // profile could not answer is left out, so the line claims only that nothing conflicts.
  const line = notChecked
    ? { icon: <CircleDashed aria-hidden className="size-4" />, label: "Checks not run yet" }
    : scan.status === "clear"
      ? { icon: <CircleCheck aria-hidden className="size-4 text-success" />, label: "No knock-outs" }
      : { icon: <Minus aria-hidden className="size-4" />, label: "No requirements listed" };
  return (
    <div role="status" className="rounded-corner-md border border-border px-3 py-2 text-body-medium">
      <div className={cn("flex items-center gap-2 font-medium", scan.status !== "clear" && "text-muted-foreground")}>
        {line.icon}
        {line.label}
        {scan.status === "unstated" && !notChecked ? (
          <span className="sr-only">{". Nothing here to check. That doesn't mean you qualify."}</span>
        ) : null}
      </div>
      {stripBlock}
    </div>
  );
}
