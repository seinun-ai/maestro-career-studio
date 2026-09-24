"use client";

import { use } from "react";

import { HealthReportPage } from "@/components/resume-health/health-report-page";

export default function BaseResumeHealthPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  return (
    <HealthReportPage
      resumeKey={slug}
      backHref={`/base-resumes/${slug}`}
      backLabel="Back to resume"
    />
  );
}
