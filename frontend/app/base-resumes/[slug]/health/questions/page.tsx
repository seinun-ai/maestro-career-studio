"use client";

import { use } from "react";

import { QuestionPass } from "@/components/resume-health/question-pass";

/** The health report's question pass: every question on one page (Start the questions opens it). */
export default function HealthQuestionsPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ from?: string | string[] }>;
}) {
  const { slug } = use(params);
  // Read, not used: it makes the route dynamic, so the pass's useSearchParams (`?from=`) needs no
  // Suspense boundary. The prop itself keeps its arrival value after a replaceState (SYSTEM.md §12).
  use(searchParams);
  return <QuestionPass resumeKey={slug} />;
}
