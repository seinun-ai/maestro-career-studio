"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { inOrder } from "@/lib/in-order";
import type { McpWorkflowSetting, McpWorkflowSettings } from "@/lib/types";

/** The saved `mcp_workflow` setting's read (`GET /api/settings/mcp-workflow`). */
export const MCP_WORKFLOW_KEY = ["settings", "mcp-workflow"] as const;

/**
 * `PUT /api/settings/mcp-workflow`. One record holds two settings with a card each in Settings › Agent apps:
 * the next-step hints switch (mcp-workflow-section.tsx) and who writes (agent-writer-section.tsx). A caller
 * passes only the field it changes.
 *
 * The PUT takes the whole value, so each save is queued (`inOrder`, never a mutation `scope`: a scoped
 * mutation queues as paused in a hidden tab, SYSTEM.md section 12) and, once its turn comes, merges the
 * change into the latest cached value and caches the server's answer before the next save reads it.
 * TanStack's `onSuccess` would run after the next queued call had already read the cache, so a writer pick
 * followed by a quick hints flip sent the old writer back. No toast on a save (each card shows its
 * autosave status); a failure toasts.
 */
export function useSaveMcpWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (change: Partial<McpWorkflowSettings>) =>
      inOrder("mcp-workflow", async () => {
        // A refetch that started before this save would land the old value over the one cached below.
        await qc.cancelQueries({ queryKey: MCP_WORKFLOW_KEY });
        const saved = qc.getQueryData<McpWorkflowSetting>(MCP_WORKFLOW_KEY)?.value;
        const result = await apiFetch<McpWorkflowSetting>("/api/settings/mcp-workflow", {
          method: "PUT",
          body: JSON.stringify({ value: { ...saved, ...change } }),
        });
        qc.setQueryData(MCP_WORKFLOW_KEY, result);
        return result;
      }),
    onError: (error: Error) => toast.error(couldnt("save this setting", error)),
  });
}
