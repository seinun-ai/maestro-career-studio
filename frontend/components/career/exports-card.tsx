"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { couldnt } from "@/lib/error-text";
import { formatAbsoluteDateTime } from "@/lib/format-date";
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
      toast.success("Text copy refreshed");
    },
    onError: (error: Error) => toast.error(couldnt("refresh the text copy", error)),
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
              {couldnt("check the text copy", query.error)}
            </p>
            <Button size="sm" variant="outline" onClick={() => void query.refetch()}>
              Try again
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3">
            <div>
              {/* The download keeps its file name, career.md. Connected agents read the same
                  text (MCP get_career_export), so the row says who it is for. */}
              <p className="text-sm font-medium">A text copy for you and connected agents</p>
              <p className="text-muted-foreground text-xs">
                {metadata
                  ? // Every read rebuilds it when the career history changed (exports.get_career_export).
                    `Updated ${formatAbsoluteDateTime(metadata.generated_at)}. It updates itself when your career history changes.`
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
                Refresh
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
