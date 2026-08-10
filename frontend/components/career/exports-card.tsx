"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  careerExportDownloadUrl,
  listCareerExports,
  refreshCareerExport,
} from "@/lib/api";

export function CareerExportsCard() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["exports", "career"],
    queryFn: listCareerExports,
  });
  const refresh = useMutation({
    mutationFn: refreshCareerExport,
    onSuccess: (updated) => {
      queryClient.setQueryData(["exports", "career"], [updated]);
      toast.success("career.md refreshed");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const metadata = query.data?.[0];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Exports</CardTitle>
        <p className="text-muted-foreground text-sm">
          A portable Markdown snapshot derived from your Career KB.
        </p>
      </CardHeader>
      <CardContent>
        {query.isLoading ? (
          <Skeleton className="h-12 w-full" />
        ) : query.error ? (
          <div role="alert" className="space-y-2">
            <p className="text-destructive text-sm">{query.error.message}</p>
            <Button size="sm" variant="outline" onClick={() => void query.refetch()}>
              Try again
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3">
            <div>
              <p className="text-sm font-medium">career.md</p>
              <p className="text-muted-foreground text-xs">
                {metadata
                  ? `Generated ${new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(metadata.generated_at))}`
                  : "Not generated yet"}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                nativeButton={false}
                render={
                  <a href={careerExportDownloadUrl()} download="career.md">
                    <Download aria-hidden="true" /> Download
                  </a>
                }
              />
              <Button
                size="sm"
                variant="outline"
                disabled={refresh.isPending}
                onClick={() => refresh.mutate()}
              >
                {refresh.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />}
                Refresh
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
