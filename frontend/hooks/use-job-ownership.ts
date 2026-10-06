"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { Job, JobOwnership } from "@/lib/types";

async function listOwnership(): Promise<Map<string, JobOwnership>> {
  const result = new Map<string, JobOwnership>();
  for (let offset = 0; ; offset += 500) {
    const jobs = await apiFetch<Job[]>(`/api/jobs?limit=500&offset=${offset}`);
    for (const job of jobs) if (job.ownership) result.set(job.id, job.ownership);
    if (jobs.length < 500) return result;
  }
}

// Application/proposal projections do not carry stamped ownership. The job API owns this read.
export function useJobOwnershipMap() {
  return useQuery({ queryKey: ["jobs", "ownership"], queryFn: listOwnership,
    refetchOnWindowFocus: true });
}
