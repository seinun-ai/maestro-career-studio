"use client";

import { useState } from "react";
import { Clock, DollarSign, GraduationCap, ListChecks, MapPin } from "lucide-react";
import type { ReactNode } from "react";

import { useRoleLabel } from "@/components/role-category-picker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMoney } from "@/hooks/use-money";
import type { Job } from "@/lib/types";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { formatShortDate } from "@/lib/format-date";
import { formatPay, payLine, periodWords, type FormattedPay } from "@/lib/money";

const JobFactsIcon = CONCEPT_ICONS.jobFacts;
const SkillsIcon = CONCEPT_ICONS.skills;
const JobWordsIcon = CONCEPT_ICONS.jobWords;
const WorkAuthorizationIcon = CONCEPT_ICONS.workAuthorization;
const StudentPermitIcon = CONCEPT_ICONS.studentPermit;

export interface ExtractedSkill {
  skill_name: string;
  skill_category?: string;
  requirement_level?: string;
}

export function extractSkills(json: Job["extracted_json"]): ExtractedSkill[] {
  if (!json || typeof json !== "object") return [];
  const raw = (json as Record<string, unknown>).skills;
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (item): item is ExtractedSkill =>
      typeof item === "object" &&
      item !== null &&
      typeof (item as ExtractedSkill).skill_name === "string",
  );
}

function extractStringList(
  json: Job["extracted_json"],
  key: "responsibilities" | "qualifications",
): string[] {
  if (!json || typeof json !== "object") return [];
  const raw = (json as Record<string, unknown>)[key];
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

/** A job's pay as `formatPay` reads it. */
export function jobPay(job: Job) {
  return {
    min: job.salary_min,
    max: job.salary_max,
    currency: job.salary_currency,
    period: job.salary_period,
  };
}

/** Under a converted figure: what the post said, and the date of the rate used. */
function postedNote(pay: FormattedPay): string | null {
  if (!pay.converted || !pay.posted) return null;
  const words = periodWords(pay.postedPeriod);
  const posted = `${pay.posted}${words ? ` ${words}` : ""} as posted`;
  return pay.rateDate ? `${posted} · rate of ${formatShortDate(pay.rateDate)}` : posted;
}

function formatYears(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  if (min !== null && max !== null)
    return min === max ? `${min} years` : `${min}–${max} years`;
  if (min !== null) return `${min}+ years`;
  return `up to ${max} years`;
}

function formatLocationLine(job: Job): string | null {
  const parts = [job.city, job.state, job.country].filter(
    (p): p is string => typeof p === "string" && p.trim().length > 0,
  );
  if (parts.length > 0) return parts.join(" · ");
  return job.location_raw ?? job.location ?? null;
}

/**
 * Stored enum → label where plain capitalization reads wrong. Keys are the
 * STORED values (`schemas/job_extraction.py`): work mode is stored as
 * `on_site` (`work_mode_key`); `onsite` is how rows saved before that read.
 */
const ENUM_LABELS: Record<string, string> = {
  full_time: "Full-time",
  part_time: "Part-time",
  on_site: "On-site",
  onsite: "On-site",
  citizen_or_gc_required: "Citizen or green card required",
  no_sponsorship: "No sponsorship",
  sponsorship_available: "Sponsorship available",
  stem_opt_ok: "STEM OPT accepted",
  unstated: "Not stated",
  unknown: "Not stated",
};

export function humanizeEnum(value: string | null | undefined): string | null {
  if (!value) return null;
  const mapped = ENUM_LABELS[value];
  if (mapped) return mapped;
  const words = value.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function StatLine({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
}) {
  const empty = value == null || value === "";
  return (
    <div className="flex items-start gap-2 text-body-medium">
      <span className="text-muted-foreground mt-0.5 [&>svg]:size-4">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="text-muted-foreground text-label-small">
          {label}
        </div>
        <div className={empty ? "text-muted-foreground/60" : ""}>
          {empty ? "—" : value}
        </div>
      </div>
    </div>
  );
}

/** The three requirement groups, each under its word (colour alone never says Required vs Preferred). */
function SkillGroup({
  title,
  variant,
  skills,
  limit,
}: {
  title: string;
  variant: "default" | "tonal" | "outline";
  skills: ExtractedSkill[];
  /** Show at most this many badges, then "+N more"; the heading count stays the full total. */
  limit?: number;
}) {
  if (skills.length === 0) return null;
  const shown = limit === undefined ? skills : skills.slice(0, Math.max(0, limit));
  const extra = skills.length - shown.length;
  return (
    <div>
      <div className="text-muted-foreground mb-1.5 text-label-medium">
        {title} ({skills.length})
      </div>
      <div className="flex flex-wrap gap-1.5">
        {shown.map((s, i) => (
          <Badge key={`${s.skill_name}-${i}`} variant={variant}>
            {s.skill_name}
          </Badge>
        ))}
        {extra > 0 && (
          <span className="text-muted-foreground self-center text-body-small">
            +{extra} more
          </span>
        )}
      </div>
    </div>
  );
}

function BulletSection({
  icon,
  title,
  items,
}: {
  icon: React.ReactNode;
  title: string;
  items: string[];
}) {
  if (items.length === 0) return null;
  return (
    <section>
      <h4 className="mb-2 flex items-center gap-2 text-title-small [&>svg]:size-4">
        {icon}
        {title}
      </h4>
      <ul className="text-muted-foreground list-disc space-y-1 pl-5 text-body-medium">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

export function JobExtractedFields({
  job,
  actionsSlot,
  statusSlot,
  hideTitle = false,
}: {
  job: Job;
  actionsSlot?: React.ReactNode;
  /** Shown first inside the card (the job page's knock-out line). */
  statusSlot?: React.ReactNode;
  /** Hide company · title when the page header already shows it. */
  hideTitle?: boolean;
}) {
  const [showRaw, setShowRaw] = useState(false);
  // The catalog's label ("AI/ML Engineer"), never the key title-cased.
  const roleLabelOf = useRoleLabel();

  const skills = extractSkills(job.extracted_json);
  const required = skills.filter((s) => s.requirement_level === "required");
  const preferred = skills.filter((s) => s.requirement_level === "preferred");
  const mentioned = skills.filter(
    (s) =>
      !s.requirement_level ||
      (s.requirement_level !== "required" && s.requirement_level !== "preferred"),
  );
  const responsibilities = extractStringList(job.extracted_json, "responsibilities");
  const qualifications = extractStringList(job.extracted_json, "qualifications");

  const locationLine = formatLocationLine(job);
  const money = useMoney();
  const pay = formatPay(jobPay(job), money);
  const salaryLine = pay ? payLine(pay) : null;
  // Converted: the posted amount stays in view. No rate: the figure is the post's own, and says so.
  const salaryNote = !pay
    ? null
    : pay.noRate && money.ratesReady
      ? "As posted: no exchange rate for this currency"
      : money.showPosted
        ? postedNote(pay)
        : null;
  const salaryDisplay =
    salaryLine ??
    (job.salary_source_url
      ? "See pay range"
      : null); // null pay is normal — omit the row rather than dash-warn
  const yearsLine = formatYears(job.years_experience_min, job.years_experience_max);
  const workAuthLine = humanizeEnum(job.work_authorization);
  const optLine = humanizeEnum(job.opt_accepted);
  const roleChips = (
    [
      ["Role", job.role_category ? roleLabelOf(job.role_category) : null],
      ["Level", humanizeEnum(job.level)],
      ["Employment type", humanizeEnum(job.employment_type)],
      ["Work mode", humanizeEnum(job.work_mode)],
    ] as [field: string, value: string | null][]
  ).filter((pair): pair is [string, string] => pair[1] !== null);

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
          {!hideTitle ? (
            <div className="space-y-0.5">
              <CardTitle>
                {job.company ?? "—"} · {job.title ?? "—"}
              </CardTitle>
              <p className="text-muted-foreground text-body-small">
                Job description
              </p>
            </div>
          ) : (
            <p className="text-muted-foreground text-body-medium">Job details</p>
          )}
          {actionsSlot}
        </CardHeader>
        <CardContent className="space-y-5">
          {statusSlot}
          {/* Only present values render: the chips carry no visible field
              names, so an empty dashed chip cannot say WHICH field is missing
              (the labelled StatLines below keep the — convention). */}
          {roleChips.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <JobFactsIcon className="text-muted-foreground size-4" />
              {roleChips.map(([field, value]) => (
                <Badge key={field} variant="outline" title={`${field}: ${value}`}>
                  {value}
                </Badge>
              ))}
            </div>
          )}

          <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
            <StatLine icon={<MapPin />} label="Location" value={locationLine} />
            {salaryDisplay ? (
              <StatLine
                icon={<DollarSign />}
                label="Salary"
                value={
                  job.salary_source_url && !salaryLine ? (
                    <a
                      href={job.salary_source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-foreground underline-offset-2 hover:underline"
                    >
                      See pay range
                    </a>
                  ) : (
                    <>
                      {salaryDisplay}
                      {salaryNote && (
                        <span className="text-muted-foreground block text-body-small">
                          {salaryNote}
                        </span>
                      )}
                    </>
                  )
                }
              />
            ) : null}
            <StatLine
              icon={<Clock />}
              label="Years of experience"
              value={yearsLine}
            />
            <StatLine
              icon={<WorkAuthorizationIcon />}
              label="Work authorization"
              value={workAuthLine}
            />
            <StatLine
              icon={<StudentPermitIcon />}
              label="OPT (US student work permit) accepted"
              value={optLine}
            />
          </dl>

          {skills.length > 0 && (
            <div className="space-y-3 border-t pt-4">
              <h4 className="flex items-center gap-2 text-title-small [&>svg]:size-4">
                <SkillsIcon />
                Skills ({skills.length})
              </h4>
              <SkillGroup
                title="Required"
                variant="default"
                skills={required}
              />
              <SkillGroup
                title="Preferred"
                variant="tonal"
                skills={preferred}
              />
              <SkillGroup
                title="Mentioned"
                variant="outline"
                skills={mentioned}
              />
            </div>
          )}

          {(responsibilities.length > 0 || qualifications.length > 0) && (
            <div className="grid gap-6 border-t pt-4 sm:grid-cols-2">
              <BulletSection
                icon={<ListChecks />}
                title="Responsibilities"
                items={responsibilities}
              />
              <BulletSection
                icon={<GraduationCap />}
                title="Qualifications"
                items={qualifications}
              />
            </div>
          )}
        </CardContent>
      </Card>

      <div className="mt-5 space-y-3">
        <Button variant="outline" size="sm" onClick={() => setShowRaw((s) => !s)}>
          <JobWordsIcon />
          {showRaw ? "Hide full job description" : "Show full job description"}
        </Button>
        {showRaw && (
          <pre className="bg-muted max-h-96 overflow-auto rounded-corner-md p-3 text-body-small whitespace-pre-wrap">
            {job.raw_text}
          </pre>
        )}
      </div>
    </>
  );
}
