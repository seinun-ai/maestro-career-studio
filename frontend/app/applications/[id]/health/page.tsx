"use client";

import { use } from "react";

import { HealthReportPage } from "@/components/resume-health/health-report-page";

export default function ApplicationHealthPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <HealthReportPage
      kind="application"
      resumeKey={id}
      backHref={`/applications/${id}/resume`}
      backLabel="Back to editor"
    />
  );
}
