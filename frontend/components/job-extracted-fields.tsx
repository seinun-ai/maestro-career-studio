"use client";

import { useState } from "react";
import {
  Briefcase,
  CheckCircle2,
  Clock,
  DollarSign,
  FileText,
  GraduationCap,
  ListChecks,
  MapPin,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Job } from "@/lib/types";

interface ExtractedSkill {
  skill_name: string;
  skill_category?: string;
  requirement_level?: string;
}

function extractSkills(json: Job["extracted_json"]): ExtractedSkill[] {
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

function formatMoney(
  value: string | number | null | undefined,
  currency: string | null | undefined = "USD",
): string | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return null;
  const code = (currency || "USD").toUpperCase();
  try {
    // Compact currency for resume-scale numbers; falls back below on exotic codes.
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: code,
      notation: n >= 1000 ? "compact" : "standard",
      maximumFractionDigits: n >= 1000 ? 1 : 0,
    }).format(n);
  } catch {
    if (n >= 10_000) return `${code} ${Math.round(n / 1000)}k`;
    if (n >= 1000) return `${code} ${(n / 1000).toFixed(1)}k`;
    return `${code} ${n}`;
  }
}

export function formatSalary(
  min: string | number | null,
  max: string | number | null,
  period: string | null,
  currency: string | null = null,
): string | null {
  const lo = formatMoney(min, currency);
  const hi = formatMoney(max, currency);
  if (!lo && !hi) return null;
  const range = lo && hi && lo !== hi ? `${lo}–${hi}` : (lo ?? hi);
  return period ? `${range} / ${period}` : range;
}

function formatYears(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  if (min !== null && max !== null)
    return min === max ? `${min} yrs` : `${min}–${max} yrs`;
  if (min !== null) return `${min}+ yrs`;
  return `up to ${max} yrs`;
}

function formatLocationLine(job: Job): string | null {
  const parts = [job.city, job.state, job.country].filter(
    (p): p is string => typeof p === "string" && p.trim().length > 0,
  );
  if (parts.length > 0) return parts.join(" · ");
  return job.location_raw ?? job.location ?? null;
}

/** Stored enum → label where plain capitalization reads wrong. */
const ENUM_LABELS: Record<string, string> = {
  full_time: "Full-time",
  part_time: "Part-time",
  on_site: "On-site",
};

function humanizeEnum(value: string | null | undefined): string | null {
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
    <div className="flex items-start gap-2 text-sm">
      <span className="text-muted-foreground mt-0.5 [&>svg]:size-4">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="text-muted-foreground text-[11px] tracking-wide uppercase">
          {label}
        </div>
        <div className={empty ? "text-muted-foreground/60" : ""}>
          {empty ? "—" : value}
        </div>
      </div>
    </div>
  );
}

function SkillGroup({
  title,
  variant,
  skills,
}: {
  title: string;
  variant: "default" | "secondary" | "outline";
  skills: ExtractedSkill[];
}) {
  if (skills.length === 0) return null;
  return (
    <div>
      <div className="text-muted-foreground mb-1.5 text-xs font-medium">
        {title} ({skills.length})
      </div>
      <div className="flex flex-wrap gap-1.5">
        {skills.map((s, i) => (
          <Badge key={`${s.skill_name}-${i}`} variant={variant}>
            {s.skill_name}
          </Badge>
        ))}
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
      <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold [&>svg]:size-4">
        {icon}
        {title}
      </h4>
      <ul className="text-muted-foreground list-disc space-y-1 pl-5 text-sm">
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
  hideTitle = false,
}: {
  job: Job;
  actionsSlot?: React.ReactNode;
  /** Hide company · title when the page header already shows it. */
  hideTitle?: boolean;
}) {
  const [showRaw, setShowRaw] = useState(false);

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
  const salaryLine = formatSalary(
    job.salary_min,
    job.salary_max,
    job.salary_period,
    job.salary_currency,
  );
  const salaryDisplay =
    salaryLine ??
    (job.salary_source_url
      ? "Pay scale linked"
      : null); // null pay is normal — omit the row rather than dash-warn
  const yearsLine = formatYears(job.years_experience_min, job.years_experience_max);
  const workAuthLine = humanizeEnum(job.work_authorization);
  const optLine = humanizeEnum(job.opt_accepted);
  const roleChips = (
    [
      ["Role family", humanizeEnum(job.role_category)],
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
              <p className="text-muted-foreground text-xs">
                Extracted job description
              </p>
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">Extracted fields</p>
          )}
          {actionsSlot}
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Only present values render: the chips carry no visible field
              names, so an empty dashed chip cannot say WHICH field is missing
              (the labelled StatLines below keep the — convention). */}
          {roleChips.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <Briefcase className="text-muted-foreground size-4" />
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
                      Pay scale linked
                    </a>
                  ) : (
                    salaryDisplay
                  )
                }
              />
            ) : null}
            <StatLine
              icon={<Clock />}
              label="Years experience"
              value={yearsLine}
            />
            <StatLine
              icon={<ShieldCheck />}
              label="Work authorization"
              value={workAuthLine}
            />
            <StatLine
              icon={<CheckCircle2 />}
              label="OPT accepted"
              value={optLine}
            />
          </dl>

          {skills.length > 0 && (
            <div className="space-y-3 border-t pt-4">
              <h4 className="flex items-center gap-2 text-sm font-semibold [&>svg]:size-4">
                <Sparkles />
                Skills ({skills.length})
              </h4>
              <SkillGroup
                title="Required"
                variant="default"
                skills={required}
              />
              <SkillGroup
                title="Preferred"
                variant="secondary"
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
          <FileText />
          {showRaw ? "Hide raw JD" : "Show raw JD"}
        </Button>
        {showRaw && (
          <pre className="bg-muted max-h-96 overflow-auto rounded-md p-3 text-xs whitespace-pre-wrap">
            {job.raw_text}
          </pre>
        )}
      </div>
    </>
  );
}
