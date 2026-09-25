"use client";

import { use } from "react";

import { HealthReportPage } from "@/components/resume-health/health-report-page";

export default function BaseResumeHealthPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ tab?: string | string[] }>;
}) {
  const { slug } = use(params);
  // Read, not used: it makes the route dynamic, so the report's useSearchParams (`?tab=`) needs no
  // Suspense boundary. The prop itself keeps its arrival value after a replaceState (SYSTEM.md §12).
  use(searchParams);
  return (
    <HealthReportPage
      resumeKey={slug}
      backHref={`/base-resumes/${slug}`}
      backLabel="Back to resume"
      questionsHref={`/base-resumes/${slug}/health/questions`}
    />
  );
}
