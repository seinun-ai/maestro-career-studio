"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { FullscreenEditorPage } from "@/components/resume-editor/fullscreen-editor-page";
import { TailoredResumeStudio } from "@/components/resume-editor/tailored-resume-studio";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import type { ApplicationDetail } from "@/lib/types";

export default function ApplicationTailoredResumePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ review?: string | string[] }>;
}) {
  const { id } = use(params);
  // `?review=1` — set by the post-tailor CTA, so the studio opens on the
  // provenance-labeled change list. Everything else opens the plain editor.
  const { review: reviewParam } = use(searchParams);
  const reviewDefault =
    (Array.isArray(reviewParam) ? reviewParam[0] : reviewParam) === "1";
  const query = useQuery({
    queryKey: ["application", id],
    queryFn: () => apiFetch<ApplicationDetail>(`/api/applications/${id}`),
  });

  if (query.isError) {
    return (
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 p-6">
        <p className="text-destructive">Failed to load application.</p>
        <Button
          variant="outline"
          nativeButton={false}
          render={<Link href={`/applications/${id}`}>Back to application</Link>}
        />
      </main>
    );
  }

  if (query.isLoading || !query.data) {
    return (
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 p-6">
        <Skeleton className="h-10 w-60" />
        <Skeleton className="h-96 w-full" />
      </main>
    );
  }

  const app = query.data;
  const jobLabel =
    app.job?.title && app.job?.company
      ? `${app.job.title} · ${app.job.company}`
      : (app.job?.title ?? app.job?.company ?? "Application");
  const backHref = `/jobs/${app.job_id}?tab=output`;

  return (
    <FullscreenEditorPage>
      <TailoredResumeStudio
        application={app}
        jobId={app.job_id}
        jobLabel={jobLabel}
        backHref={backHref}
        reviewDefault={reviewDefault}
      />
    </FullscreenEditorPage>
  );
}
