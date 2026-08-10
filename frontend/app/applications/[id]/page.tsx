"use client";

import { use, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { FileX2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import type { ApplicationDetail } from "@/lib/types";

export default function ApplicationDetailRedirect({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const { data, isError } = useQuery({
    queryKey: ["application", id],
    queryFn: () => apiFetch<ApplicationDetail>(`/api/applications/${id}`),
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => {
    if (data?.job_id) router.replace(`/jobs/${data.job_id}`);
  }, [data?.job_id, router]);

  if (isError) {
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
    <main className="mx-auto w-full max-w-6xl flex-1 space-y-4 p-6">
      <Skeleton className="h-10 w-1/3" />
      <Skeleton className="h-60 w-full" />
    </main>
  );
}
