"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { EditorBody } from "@/components/resume-editor/editor-body";
import { FullscreenEditorPage } from "@/components/resume-editor/fullscreen-editor-page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import type { BaseResumeDetail } from "@/lib/types";

export default function BaseResumeEditorPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const query = useQuery({
    queryKey: ["base-resumes", slug],
    queryFn: () => apiFetch<BaseResumeDetail>(`/api/base-resumes/${slug}`),
  });

  if (query.isError) {
    return (
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 p-6">
        <p className="text-destructive">Failed to load resume.</p>
        <Button
          render={<Link href="/base-resumes">Back to list</Link>}
          nativeButton={false}
          variant="outline"
        />
      </main>
    );
  }

  if (query.isLoading || !query.data) {
    return (
      <main className="flex w-full flex-1 flex-col gap-4 p-6">
        <Skeleton className="h-10 w-60" />
        <Skeleton className="h-96 w-full" />
      </main>
    );
  }

  return (
    <FullscreenEditorPage>
      <EditorBody slug={slug} initial={query.data} />
    </FullscreenEditorPage>
  );
}
