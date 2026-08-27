"use client";

import { useId } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { AutosaveStatus } from "@/components/settings/autosave-status";
import { AutosaveRow, SettingCard } from "@/components/settings/setting-card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { apiFetch } from "@/lib/api";
import type { McpWorkflowSetting } from "@/lib/types";

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
  // no partial state worth staging. It used to do so SILENTLY, which is the
  // half of the rule that was missing — with no Save button and no indicator,
  // "nothing happened" and "saved instantly" look identical.
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
    <SettingCard
      id="agent-hints"
      title="Agent workflow hints"
      description="Adds a suggested next step to Career Studio's MCP tool results, so Claude or Codex can walk the tailoring workflow without being told each step. Turn it off to keep responses minimal."
      errorTitle="Couldn't load this setting."
      skeleton="h-11 w-full"
      query={setting}
    >
      {(data) => (
        <>
          <AutosaveRow>
            <AutosaveStatus pending={save.isPending} />
          </AutosaveRow>
          {/* Same row geometry as the quick-tailor switches. */}
          <div className="flex items-center justify-between gap-4 px-3 py-2.5">
            <Label htmlFor={id} className="text-sm">
              Suggest the next step in MCP tool results
            </Label>
            <Switch
              id={id}
              checked={data.value.hints}
              disabled={save.isPending}
              onCheckedChange={(checked) => save.mutate(checked)}
            />
          </div>
        </>
      )}
    </SettingCard>
  );
}
