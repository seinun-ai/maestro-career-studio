"use client";

import { useId } from "react";
import { useQuery } from "@tanstack/react-query";

import { GuardedLink as Link } from "@/components/guarded-link";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCard, SettingCardAction } from "@/components/settings/setting-card";
import { RadioGroup, Radio } from "@/components/ui/radio-group";
import { MCP_WORKFLOW_KEY, useSaveMcpWorkflow } from "@/hooks/use-save-mcp-workflow";
import { apiFetch } from "@/lib/api";
import { anchorHref } from "@/lib/settings-tabs";
import type { McpWorkflowSetting, McpWorkflowSettings, SetupStatus } from "@/lib/types";

type Writer = McpWorkflowSettings["writer"];

/** The two answers, each with its one line. */
const WRITERS: { value: Writer; label: string; line: string }[] = [
  {
    value: "agent",
    label: "Your agent app",
    line:
      "It writes the tailored wording, letters, answers and notes with its own AI. "
      + "Your API key isn't used for them.",
  },
  {
    value: "maestro",
    label: "Maestro's AI",
    line:
      "Maestro writes the tailored wording, letters, answers and notes with your API key. "
      + "Your agent app steers.",
  },
];

/**
 * Who writes when an agent app (Claude, Codex) is connected: the `writer` half of the saved
 * `mcp_workflow` setting, whose other half is the next-step hints switch (`McpWorkflowSection`). Both
 * cards save through `useSaveMcpWorkflow`, which sends the whole value with only their own field changed.
 *
 * The user's choice alone: no agent tool writes it. The server enforces it, refusing a key-backed
 * write from an agent app while the agent app writes (backend/app/agent_writer.py); the web app and
 * the Companion always use the key.
 */
export function AgentWriterSection() {
  const optionId = useId();
  const keyLineId = useId();

  const setting = useQuery({
    queryKey: MCP_WORKFLOW_KEY,
    queryFn: () => apiFetch<McpWorkflowSetting>("/api/settings/mcp-workflow"),
  });
  const save = useSaveMcpWorkflow();
  // The pick shows at once and the saved value replaces it, so a second pick made while the first
  // saves is neither dropped nor shown as the old one.
  const saved = setting.data?.value.writer;
  const shown = save.isPending ? (save.variables.writer ?? saved) : saved;

  // Asked only while Maestro's AI is shown, through the read every setup-status reader shares: a key
  // saved in Basics invalidates it, so the line goes the moment one is added. A failed read says
  // nothing: the line needs a confirmed no.
  const setup = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => apiFetch<SetupStatus>("/api/setup/status"),
    refetchOnMount: "always",
    enabled: shown === "maestro",
  });
  const keyLine = shown === "maestro" && setup.data?.model_key.done === false;

  return (
    <SettingCard
      id="agent-writer"
      title="Who writes for connected agents"
      description="For Claude, Codex and other agent apps connected to Maestro. The Maestro app and the Companion always use your API key."
      errorTitle="Couldn't load this setting."
      skeleton="h-24 w-full"
      query={setting}
    >
      {(data) => (
        <>
          <SettingCardAction>
            <AutosaveStatus pending={save.isPending} failed={save.isError} />
          </SettingCardAction>
          <div className="grid gap-2">
            <RadioGroup<Writer>
              aria-label="Who writes for connected agents"
              value={shown ?? data.value.writer}
              onValueChange={(writer) => save.mutate({ writer })}
            >
              {WRITERS.map((writer) => (
                // Named by its label alone and described by its line (and, for Maestro's AI, the key
                // line's region under the group), as the Screening answers radios are.
                <label key={writer.value} className="flex items-start gap-2">
                  <Radio
                    value={writer.value}
                    aria-labelledby={`${optionId}-${writer.value}-label`}
                    aria-describedby={
                      writer.value === "maestro"
                        ? `${optionId}-${writer.value}-line ${keyLineId}`
                        : `${optionId}-${writer.value}-line`
                    }
                  />
                  <span className="grid gap-0.5">
                    <span id={`${optionId}-${writer.value}-label`} className="text-label-large">
                      {writer.label}
                    </span>
                    <span
                      id={`${optionId}-${writer.value}-line`}
                      className="text-muted-foreground text-body-small"
                    >
                      {writer.line}
                    </span>
                  </span>
                </label>
              ))}
            </RadioGroup>
            {/* Always mounted, so the line is announced as it appears (FieldMessage's pattern);
                `empty:absolute` takes it out of the grid while empty. */}
            <div id={keyLineId} aria-live="polite" className="empty:absolute">
              {keyLine ? (
                <p className="text-muted-foreground text-body-small">
                  Needs an API key:{" "}
                  <Link href={anchorHref("/settings", "api-keys")} className="underline underline-offset-4">
                    add one in Basics
                  </Link>
                  .
                </p>
              ) : null}
            </div>
          </div>
        </>
      )}
    </SettingCard>
  );
}
