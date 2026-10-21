"use client";

import { useQueryClient } from "@tanstack/react-query";

import type { ApplicationSummary, Job } from "@/lib/types";

/**
 * The job's title and company as a Jobs list already in the cache holds them (the applications list, or the saved
 * jobs of either source), read once, so the job page's header draws them in the navigation's first frame while its
 * detail loads: the row's monogram and title morph only into a pair that is on the page in that frame. Null when no
 * list holds the job (a link from elsewhere): the page then shows its skeleton.
 */
export function useCachedJobHeading(jobId: string): { title: string | null; company: string | null } | null {
  const qc = useQueryClient();
  for (const [, rows] of qc.getQueriesData<ApplicationSummary[]>({ queryKey: ["applications"] })) {
    const row = Array.isArray(rows) ? rows.find((r) => r.job_id === jobId) : undefined;
    if (row) return { title: row.job_title, company: row.job_company };
  }
  for (const [, rows] of qc.getQueriesData<Job[]>({ queryKey: ["jobs", "without-application"] })) {
    const row = Array.isArray(rows) ? rows.find((r) => r.id === jobId) : undefined;
    if (row) return { title: row.title, company: row.company };
  }
  return null;
}
