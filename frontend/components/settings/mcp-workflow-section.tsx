"use client";

import { useId } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { LoadErrorState } from "@/components/load-error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { apiFetch } from "@/lib/api";

type McpWorkflowSettings = { hints: boolean };
type McpWorkflowSetting = { key: string; value: McpWorkflowSettings };

/**
 * The user-held master switch for the MCP server's next-step workflow hints.
 *
 * There are deliberately TWO controls over these hints, because the two parties
 * know different things. The agent gets a per-call `brief` parameter — it is the
 * one running a twenty-posting triage loop, so only it knows a batch is in
 * progress. This switch is the user's half, and it is the master: off means no
 * hint is ever composed, whatever the agent asks for. It lives here rather than
 * in an env var because a config value read at process start cannot be changed
 * when a session pivots from capture to tailoring, and because being able to
 * flip it mid-use is what makes the two behaviours comparable in practice.
 */
export function McpWorkflowSection() {
  const qc = useQueryClient();
  const id = useId();

  const setting = useQuery({
    queryKey: ["settings", "mcp-workflow"],
    queryFn: () => apiFetch<McpWorkflowSetting>("/api/settings/mcp-workflow"),
  });

  // A single boolean saves on toggle rather than behind a Save button: there is
  // no partial state worth staging, and the quick-tailor card's dirty/save
  // model exists only because it batches six fields.
  const save = useMutation({
    mutationFn: (hints: boolean) =>
      apiFetch<McpWorkflowSetting>("/api/settings/mcp-workflow", {
        method: "PUT",
        body: JSON.stringify({ value: { ...setting.data?.value, hints } }),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "mcp-workflow"], result);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Agent workflow hints</CardTitle>
        <p className="text-muted-foreground text-sm">
          Adds a suggested next step to Career Studio&apos;s MCP tool results, so
          Claude or Codex can walk the tailoring workflow without being told each
          step. Turn it off to keep responses minimal.
        </p>
      </CardHeader>
      <CardContent>
        {setting.isError ? (
          <LoadErrorState
            className="py-8"
            title="Couldn't load this setting."
            detail={(setting.error as Error)?.message}
            retrying={setting.isFetching}
            onRetry={() => void setting.refetch()}
          />
        ) : setting.isLoading || !setting.data ? (
          <Skeleton className="h-11 w-full" />
        ) : (
          /* Same row geometry as the quick-tailor switches and Appearance. */
          <div className="flex items-center justify-between gap-4 px-3 py-2.5">
            <Label htmlFor={id} className="text-sm">
              Suggest the next step in MCP tool results
            </Label>
            <Switch
              id={id}
              checked={setting.data.value.hints}
              disabled={save.isPending}
              onCheckedChange={(checked) => save.mutate(checked)}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
