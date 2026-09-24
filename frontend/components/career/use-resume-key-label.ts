"use client";

import { useCallback } from "react";
import { useQuery } from "@tanstack/react-query";

import { useBaseResumeLabel } from "@/hooks/use-base-resume-label";
import { apiFetch } from "@/lib/api";
import type { ApplicationSummary } from "@/lib/types";

// An application's id as a usage row stores it (`KBPortLog.resume_key` for a tailored resume).
const APPLICATION_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * A usage row's resume in words: a base resume by its name, a tailored resume by its job ("Tailored resume for
 * ML Engineer at Quarry Labs"), never its id humanized into "E4b214c9 B123". The applications list is the
 * tracker's own query (same key and fetch, so one cache entry), read only when a key needs it.
 */
export function useResumeKeyLabel(keys: readonly string[]) {
  const baseName = useBaseResumeLabel();
  const needsApplications = keys.some((key) => APPLICATION_ID.test(key));
  const apps = useQuery({
    queryKey: ["applications"],
    queryFn: () => apiFetch<ApplicationSummary[]>("/api/applications?limit=500"),
    enabled: needsApplications,
    staleTime: 60_000,
  });
  const data = apps.data;
  return useCallback(
    (key: string) => {
      if (!APPLICATION_ID.test(key)) return baseName(key);
      const app = data?.find((row) => row.id === key);
      const job = [app?.job_title, app?.job_company].filter(Boolean).join(" at ");
      return job ? `Tailored resume for ${job}` : "A tailored resume";
    },
    [baseName, data],
  );
}
