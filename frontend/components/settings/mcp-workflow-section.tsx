"use client";

import { useId } from "react";
import { useQuery } from "@tanstack/react-query";

import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCard, SettingCardAction } from "@/components/settings/setting-card";
import { SwitchRow } from "@/components/settings/setting-layout";
import { Switch } from "@/components/ui/switch";
import { MCP_WORKFLOW_KEY, useSaveMcpWorkflow } from "@/hooks/use-save-mcp-workflow";
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
  const id = useId();

  const setting = useQuery({
    queryKey: MCP_WORKFLOW_KEY,
    queryFn: () => apiFetch<McpWorkflowSetting>("/api/settings/mcp-workflow"),
  });

  // A single boolean saves on toggle rather than behind a Save button: there is
  // no partial state worth staging. It used to do so SILENTLY, which is the
  // half of the rule that was missing — with no Save button and no indicator,
  // "nothing happened" and "saved instantly" look identical. The record also holds who writes
  // (AgentWriterSection), so the save is the shared one, which keeps that half.
  const save = useSaveMcpWorkflow();

  return (
    <SettingCard
      id="agent-hints"
      title="Next-step hints for connected agents"
      description="Adds a suggested next step to what the app tells a connected agent. Claude or Codex can then go from scoring to tailoring to applying without being told each step. Turn it off for shorter replies."
      errorTitle="Couldn't load this setting."
      skeleton="h-11 w-full"
      query={setting}
    >
      {(data) => (
        <>
          <SettingCardAction>
            <AutosaveStatus pending={save.isPending} failed={save.isError} />
          </SettingCardAction>
          <SwitchRow htmlFor={id} label="Suggest the next step to connected agents">
            <Switch
              id={id}
              checked={data.value.hints}
              onCheckedChange={(checked) => {
                if (!save.isPending) save.mutate({ hints: checked });
              }}
            />
          </SwitchRow>
        </>
      )}
    </SettingCard>
  );
}
