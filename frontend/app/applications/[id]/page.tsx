"use client";

import { use, useEffect } from "react";
import { useLastSeen } from "@/hooks/use-last-seen";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { FileX2 } from "lucide-react";

import { LoadErrorState } from "@/components/load-error-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, apiFetch } from "@/lib/api";
import { isLoadFailure } from "@/lib/query-state";
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

  const lastError = useLastSeen(query.error);

  if (isLoadFailure(query)) {
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
            render={<Link href="/applications">Back to Applications</Link>}
          />
        </main>
      );
    }
    return (
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col items-center justify-center p-6">
        <LoadErrorState
          title="Couldn't load this application."
          detail={lastError instanceof Error ? lastError.message : undefined}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
          action={
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href="/applications">Back to Applications</Link>}
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
