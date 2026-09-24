"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { couldnt } from "@/lib/error-text";
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
      toast.success("Career history file updated");
    },
    onError: (error: Error) => toast.error(couldnt("update the file", error)),
  });
  const metadata = query.data?.[0];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Download</CardTitle>
        <p className="text-muted-foreground text-sm">
          A text file of your whole career history.
        </p>
      </CardHeader>
      <CardContent>
        {query.isLoading ? (
          <Skeleton className="h-12 w-full" />
        ) : query.error ? (
          <div role="alert" className="space-y-2">
            <p className="text-destructive text-sm">
              {couldnt("check the career history file", query.error)}
            </p>
            <Button size="sm" variant="outline" onClick={() => void query.refetch()}>
              Try again
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3">
            <div>
              {/* The download keeps its file name, career.md. */}
              <p className="text-sm font-medium">Career history file</p>
              <p className="text-muted-foreground text-xs">
                {metadata
                  ? `Updated ${new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(metadata.generated_at))}`
                  : "Not created yet"}
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
                Update
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
