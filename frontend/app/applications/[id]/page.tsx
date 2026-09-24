"use client";

import { use, useEffect } from "react";
import { GuardedLink as Link } from "@/components/guarded-link";
import { useLoadFailureError } from "@/hooks/use-last-seen";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { FileX2 } from "lucide-react";

import { LoadErrorState } from "@/components/load-error-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, apiFetch } from "@/lib/api";
import { loadErrorDetail } from "@/lib/error-text";
import type { ApplicationDetail } from "@/lib/types";

export default function ApplicationDetailRedirect({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const query = useQuery({
    queryKey: ["application", id],
    queryFn: () => apiFetch<ApplicationDetail>(`/api/applications/${id}`),
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => {
    if (query.data?.job_id) router.replace(`/jobs/${query.data.job_id}`);
  }, [query.data?.job_id, router]);

  // Remembered through a retry, and null on the first render of a revisit, so
  // "no longer exists" never flashes the generic error (useLoadFailureError).
  const lastError = useLoadFailureError(query);

  if (lastError != null) {
    const missing = lastError instanceof ApiError && lastError.status === 404;
    if (missing) {
      return (
        <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
          <FileX2 className="text-muted-foreground/50 size-8" />
          <p className="text-sm font-medium">
            This application no longer exists.
          </p>
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href="/applications">Back to applications</Link>}
          />
        </main>
      );
    }
    return (
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col items-center justify-center p-6">
        <LoadErrorState
          title="Couldn't load this application."
          detail={loadErrorDetail(lastError, "application")}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
          action={
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href="/applications">Back to applications</Link>}
            />
          }
        />
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 space-y-4 p-6">
      <Skeleton className="h-10 w-1/3" />
      <Skeleton className="h-60 w-full" />
    </main>
  );
}
