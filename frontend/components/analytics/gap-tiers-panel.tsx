"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { buildQuery } from "@/components/charts/chart-kit";
import type { TopSkillsFilters } from "@/components/charts/top-skills-chart";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import type {
  BuildAreaCategory,
  BuildAreaRow,
  BuildAreaStatus,
  BuildAreaTier,
} from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * KB-evidence chip. Shown inside a tier, where the tier already states the
 * action — so the labels describe evidence, never prescribe work. ("missing"
 * is not always "go learn it": a surface row can be missing from the KB while
 * already sitting on a resume, just stale, mis-placed, or worded differently.)
 */
const STATUS_META: Record<
  BuildAreaStatus,
  { label: string; hint: string; chip: string }
> = {
  missing: {
    label: "Not in your KB",
    hint: "No Career KB evidence for this skill.",
    chip: "bg-amber-500/15 text-amber-800 dark:bg-amber-400/15 dark:text-amber-200",
  },
  in_kb: {
    label: "In your KB",
    hint: "Evidence exists in your Career KB. Send it to a resume.",
    chip: "bg-primary/10 text-primary",
  },
  ported: {
    label: "Ported before",
    hint: "Already on some resumes. Adapt it to the ones that miss it.",
    chip: "bg-muted text-muted-foreground",
  },
};

/**
 * What a surface row actually needs. "wording" is deliberately absent: that
 * word belongs to the wording tier alone, and mirror_wording here is the
 * adds_credit sibling — real headroom, which is why the backend put it in
 * surface rather than the footnote.
 */
const CATEGORY_LABEL: Record<BuildAreaCategory, string> = {
  missing_skills: "no evidence on this resume",
  mirror_wording: "exact token missing",
  dual_place: "needs corroborating",
  resurface_recent: "stale evidence",
  adjacent: "adjacent skill",
};

/**
 * Version skew between the running backend and this branch is routine here, and
 * a backend predating the tier field sends no `tier` at all. Defaulting the
 * unrecognized case to "surface" degrades to the old flat list under a heading
 * that is merely vague; filtering those rows out instead would assert
 * "No true skill gaps" over a response full of real ones.
 */
function tierOf(row: BuildAreaRow): BuildAreaTier {
  return row.tier === "build" || row.tier === "wording" ? row.tier : "surface";
}

export function GapTiersPanel({ filters }: { filters: TopSkillsFilters }) {
  const query = buildQuery(filters);
  const { data, isLoading, error } = useQuery({
    queryKey: ["explore", "build-areas", filters],
    queryFn: () =>
      apiFetch<BuildAreaRow[]>(
        `/api/explore/build-areas?limit=20${query ? `&${query}` : ""}`,
      ),
  });

  if (isLoading) return <Skeleton className="h-56 w-full" />;
  if (error) {
    return (
      <p role="alert" className="text-destructive text-sm">
        {(error as Error).message}
      </p>
    );
  }
  const rows = data ?? [];
  if (rows.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No frequent gaps yet. Score a few jobs first.
      </p>
    );
  }

  const build = rows.filter((row) => tierOf(row) === "build");
  const surface = rows.filter((row) => tierOf(row) === "surface");
  const wording = rows.filter((row) => tierOf(row) === "wording");

  // Scale bars against the scored rows only. Wording rows carry n_jobs === 0,
  // so an all-wording response would make maxJobs 0 (NaN%), and an empty list
  // would make a bare Math.max() -Infinity.
  const maxJobs = Math.max(
    0,
    ...build.map((row) => row.n_jobs),
    ...surface.map((row) => row.n_jobs),
  );

  // An empty Build section is a real answer, not an error — but it only
  // licenses the first clause. "The work is below" needs there to be a below.
  const buildEmpty =
    surface.length > 0
      ? "No true skill gaps — nothing here is a skill you have to go learn. The work is in Surface below: documentation, not learning."
      : "No true skill gaps — nothing here is a skill you have to go learn.";

  return (
    <div className="grid gap-6">
      <TierSection
        title="Build"
        blurb="Nothing on your resume and nothing in your Career KB. These are the ones you actually have to go learn or earn."
        rows={build}
        maxJobs={maxJobs}
        emptyText={buildEmpty}
      />
      {surface.length > 0 ? (
        <TierSection
          title="Surface"
          blurb="Not skills to learn — the evidence is usually already there, in your Career KB or on a resume. Each row names what it actually needs."
          rows={surface}
          maxJobs={maxJobs}
        />
      ) : null}
      {wording.length > 0 ? <WordingFootnote rows={wording} /> : null}
    </div>
  );
}

function TierSection({
  title,
  blurb,
  rows,
  maxJobs,
  emptyText,
}: {
  title: string;
  blurb: string;
  rows: BuildAreaRow[];
  maxJobs: number;
  /**
   * Shown in place of the rows when there are none. Visibility is the caller's
   * call, not this component's: a section with no rows and no emptyText renders
   * a bare heading, so don't render one.
   */
  emptyText?: string;
}) {
  return (
    <section>
      <h2 className="text-sm font-medium">{title}</h2>
      <p className="text-muted-foreground mt-0.5 text-xs">{blurb}</p>
      {rows.length === 0 ? (
        <p className="text-muted-foreground mt-3 text-sm">{emptyText}</p>
      ) : (
        <div className="mt-2 divide-y divide-foreground/10">
          {rows.map((row) => (
            <GapRow key={row.skill} row={row} maxJobs={maxJobs} />
          ))}
        </div>
      )}
    </section>
  );
}

function GapRow({ row, maxJobs }: { row: BuildAreaRow; maxJobs: number }) {
  // Both are constants on a build row — status is always "missing" and
  // category always "missing_skills"; that pair is what makes it a build row,
  // and the section blurb already says so. Only surface rows learn from them.
  const isSurface = tierOf(row) === "surface";
  const meta = isSurface ? STATUS_META[row.status] : null;
  const categoryLabel =
    isSurface && row.category ? CATEGORY_LABEL[row.category] : null;
  const width = maxJobs > 0 ? Math.max(6, (row.n_jobs / maxJobs) * 100) : 6;
  return (
    <div className="py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{row.skill}</span>
        {row.requirement_level ? (
          <span className="text-muted-foreground text-xs">
            {row.requirement_level}
          </span>
        ) : null}
        {meta ? (
          <span
            className={cn(
              "inline-flex h-6 items-center rounded-full px-2 text-xs font-medium",
              meta.chip,
            )}
            title={meta.hint}
          >
            {meta.label}
          </span>
        ) : null}
        {categoryLabel ? (
          <span className="text-muted-foreground text-xs">{categoryLabel}</span>
        ) : null}
      </div>
      <div className="mt-2 h-1.5 w-full max-w-md overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full"
          style={{ width: `${width}%`, backgroundColor: "var(--chart-1)" }}
        />
      </div>
      <p className="text-muted-foreground mt-1.5 text-xs">
        Missing in {row.n_jobs} {row.n_jobs === 1 ? "job" : "jobs"} · ≈
        {row.avg_potential_points} ATS pts each
        {row.kb_entities.length > 0 ? (
          <>
            {" · evidence: "}
            <Link href="/career" className="text-primary hover:underline">
              {row.kb_entities.join(", ")}
            </Link>
          </>
        ) : null}
      </p>
    </div>
  );
}

function WordingFootnote({ rows }: { rows: BuildAreaRow[] }) {
  return (
    <details className="rounded-lg bg-muted/40 px-3 py-2.5">
      <summary className="text-muted-foreground cursor-pointer text-xs">
        <span className="text-foreground font-medium">Wording only:</span>{" "}
        {rows.length} {rows.length === 1 ? "skill" : "skills"} where your resume
        already matches at full credit and only the JD&rsquo;s literal token is
        missing. Adding it will not change your score — quick tailor mirrors
        these for you while &ldquo;Mirror JD wording&rdquo; is on.
      </summary>
      <ul className="mt-2 grid gap-1">
        {rows.map((row) => (
          <li
            key={row.skill}
            className="flex items-center justify-between gap-3 text-xs"
          >
            <span className="min-w-0 truncate">{row.skill}</span>
            <span className="text-muted-foreground shrink-0">
              {row.wording_jobs} {row.wording_jobs === 1 ? "job" : "jobs"}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}
