"use client";

import { use } from "react";
import { GuardedLink as Link } from "@/components/guarded-link";
import { useQuery } from "@tanstack/react-query";

import { EditorBody } from "@/components/resume-editor/editor-body";
import { FullscreenEditorPage } from "@/components/resume-editor/fullscreen-editor-page";
import { LoadErrorState } from "@/components/load-error-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRefreshFailedNotice } from "@/hooks/use-refresh-failed-notice";
import { apiFetch } from "@/lib/api";
import { loadErrorDetail } from "@/lib/error-text";
import { isLoadFailure } from "@/lib/query-state";
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

  useRefreshFailedNotice(query, "this resume");

  if (isLoadFailure(query)) {
    return (
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 p-6">
        <LoadErrorState
          title="Couldn't load this resume."
          detail={loadErrorDetail(query.error, "resume")}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
          action={
            <Button
              render={<Link href="/base-resumes">Back to base resumes</Link>}
              nativeButton={false}
              variant="outline"
            />
          }
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
