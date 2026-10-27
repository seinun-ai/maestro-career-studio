"use client";

import { useId } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { GuardedLink as Link } from "@/components/guarded-link";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCard, SettingCardAction } from "@/components/settings/setting-card";
import { RadioGroup, Radio } from "@/components/ui/radio-group";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { inOrder } from "@/lib/in-order";
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
      + "Maestro's key isn't used for it.",
  },
  {
    value: "maestro",
    label: "Maestro's AI",
    line: "Maestro writes them with your API key. Your agent app steers.",
  },
];

/**
 * Who writes when an agent app (Claude, Codex) is connected: the `writer` half of the saved
 * `mcp_workflow` setting, whose other half is the next-step hints switch (`McpWorkflowSection`). Both
 * cards read and write the one record under one query key, so each PUT sends the whole value back.
 *
 * The user's choice alone: no agent tool writes it. The server enforces it, refusing a key-backed
 * write from an agent app while the agent app writes (backend/app/agent_writer.py); the web app and
 * the Companion always use the key. Saves go through `inOrder`, never a mutation `scope` (a scoped
 * mutation queues as paused in a hidden tab, SYSTEM.md section 12).
 */
export function AgentWriterSection() {
  const qc = useQueryClient();
  const optionId = useId();
  const keyLineId = useId();

  const setting = useQuery({
    queryKey: ["settings", "mcp-workflow"],
    queryFn: () => apiFetch<McpWorkflowSetting>("/api/settings/mcp-workflow"),
  });
  // The same read as every setup-status reader: a key saved in Basics invalidates it, so the line
  // below goes the moment one is added. A failed read says nothing: the line needs a confirmed no.
  const setup = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => apiFetch<SetupStatus>("/api/setup/status"),
    refetchOnMount: "always",
  });
  const needsKey = setup.data?.model_key.done === false;

  const save = useMutation({
    mutationFn: (value: McpWorkflowSettings) =>
      inOrder("mcp-workflow", () =>
        apiFetch<McpWorkflowSetting>("/api/settings/mcp-workflow", {
          method: "PUT",
          body: JSON.stringify({ value }),
        }),
      ),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "mcp-workflow"], result);
    },
    onError: (error: Error) => toast.error(couldnt("save this setting", error)),
  });

  return (
    <SettingCard
      id="agent-writer"
      title="Who writes for connected agents"
      description="For Claude, Codex and other agent apps connected to Maestro. This app and the Companion always use your API key."
      errorTitle="Couldn't load this setting."
      skeleton="h-24 w-full"
      query={setting}
    >
      {(data) => {
        // The pick shows at once and the saved value replaces it, so a second pick made while the
        // first saves is neither dropped nor shown as the old one.
        const shown = save.isPending ? save.variables.writer : data.value.writer;
        const keyLine = shown === "maestro" && needsKey;
        return (
          <>
            <SettingCardAction>
              <AutosaveStatus pending={save.isPending} failed={save.isError} />
            </SettingCardAction>
            <div className="grid gap-2">
              <RadioGroup<Writer>
                aria-label="Who writes for connected agents"
                value={shown}
                onValueChange={(writer) => save.mutate({ ...data.value, writer })}
              >
                {WRITERS.map((writer) => (
                  // Named by its label alone and described by its line (and, for Maestro's AI with
                  // no key, the line under the group), as the Screening answers radios are.
                  <label key={writer.value} className="flex items-start gap-2">
                    <Radio
                      value={writer.value}
                      aria-labelledby={`${optionId}-${writer.value}-label`}
                      aria-describedby={
                        writer.value === "maestro" && keyLine
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
              {keyLine ? (
                <p id={keyLineId} className="text-muted-foreground text-body-small">
                  Needs an API key:{" "}
                  <Link href={anchorHref("/settings", "api-keys")} className="underline underline-offset-4">
                    add one in Basics
                  </Link>
                  .
                </p>
              ) : null}
            </div>
          </>
        );
      }}
    </SettingCard>
  );
}
