"use client";

import { useId, useState } from "react";
import { Check, Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { CapabilityReport, OpenAIInfo } from "@/lib/types";

/** What each capability actually gates, so a red mark says what stops working. */
const CAPABILITY_LABELS: { key: keyof CapabilityReport; label: string; gates: string }[] = [
  { key: "text", label: "Text", gates: "cover letters, screening answers" },
  { key: "json", label: "JSON", gates: "extraction, tailoring, health, KB ingest" },
  { key: "tools", label: "Tools", gates: "the chat agent" },
];

/** True when the endpoint is neither empty nor a local address.
 *
 * Whatever is configured here receives the stored API key AND the prompt bodies
 * (resume text, job descriptions), because the OpenAI client is constructed with
 * both. That is fine for a local model server and worth one sentence of warning
 * for anything else — the field accepts any host on purpose, so the check is
 * advisory, not a block. */
function isRemoteEndpoint(raw: string): boolean {
  const value = raw.trim();
  if (!value) return false;
  try {
    const host = new URL(value).hostname;
    return !(
      host === "localhost" ||
      host === "127.0.0.1" ||
      host === "::1" ||
      host === "host.docker.internal" ||
      host.endsWith(".local")
    );
  } catch {
    return false; // not a parseable URL yet — the backend rejects it on save
  }
}

export function EndpointControls({
  info,
  disabled,
  onSave,
}: {
  info: OpenAIInfo;
  disabled: boolean;
  onSave: (patch: { base_url?: string | null; json_mode?: string }) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const value = draft ?? info.base_url ?? "";
  const endpointId = useId();
  const endpointHintId = useId();
  const jsonModeId = useId();
  const jsonModeHintId = useId();

  return (
    <div className="space-y-3 border-t pt-3">
      <div className="grid gap-3 sm:grid-cols-[2fr_1fr]">
        <div className="grid gap-1.5">
          <Label
            htmlFor={endpointId}
            className="text-muted-foreground text-xs font-normal"
            optional
          >
            OpenAI-compatible endpoint
          </Label>
          <span id={endpointHintId} className="text-muted-foreground block text-xs">
            Point at Ollama, LM Studio, vLLM or OpenRouter and nothing leaves this
            machine. Leave empty for the OpenAI API.
          </span>
          <div className="flex gap-2">
            <Input
              id={endpointId}
              aria-describedby={endpointHintId}
              placeholder="http://host.docker.internal:11434/v1"
              value={value}
              disabled={disabled}
              onChange={(e) => setDraft(e.target.value)}
            />
            <Button
              variant="outline"
              disabled={disabled || draft === null}
              onClick={() => {
                onSave({ base_url: draft?.trim() || null });
                setDraft(null);
              }}
            >
              Save
            </Button>
          </div>
          {isRemoteEndpoint(value) && (
            <span className="text-xs text-amber-700 dark:text-amber-500">
              Your API key and resume text will be sent to this server. Only point
              it somewhere you trust.
            </span>
          )}
        </div>
        <div className="grid gap-1.5">
          <Label
            htmlFor={jsonModeId}
            className="text-muted-foreground text-xs font-normal"
          >
            JSON mode
          </Label>
          <span id={jsonModeHintId} className="text-muted-foreground block text-xs">
            Auto sends <code>response_format</code> only to the OpenAI API. Some
            servers reject the field outright.
          </span>
          <Select
            value={info.json_mode}
            disabled={disabled}
            onValueChange={(v) => v && onSave({ json_mode: v })}
          >
            <SelectTrigger id={jsonModeId} aria-describedby={jsonModeHintId}>
              {/* Children, not a bare SelectValue: Base UI renders the raw
                  value otherwise, so this trigger read "auto"/"on"/"off". */}
              <SelectValue>
                {(value) =>
                  value === "on"
                    ? "Always on"
                    : value === "off"
                      ? "Off"
                      : "Auto"
                }
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">Auto</SelectItem>
              <SelectItem value="on">Always on</SelectItem>
              <SelectItem value="off">Off</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  );
}

export function CapabilityMatrix({
  info,
  onProbe,
  probing,
}: {
  info: OpenAIInfo;
  onProbe: (model: string) => void;
  probing: string | null;
}) {
  // A model can hold two roles at once; test it once, show it once.
  const models = [...new Set([info.fast_model, info.smart_model, info.chat_model])];

  return (
    <div className="space-y-2 border-t pt-3">
      <p className="text-muted-foreground text-xs">
        Measured, not assumed. A model that cannot call tools still works
        everywhere except chat.
      </p>
      <ul className="space-y-1.5">
        {models.map((model) => {
          const report = info.capabilities[model];
          return (
            <li
              key={model}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs"
            >
              <span className="min-w-0 flex-1 truncate font-medium">{model}</span>
              {report ? (
                CAPABILITY_LABELS.map(({ key, label, gates }) => {
                  const ok = report[key] === true;
                  return (
                    <span
                      key={key}
                      className="flex items-center gap-1"
                      title={
                        ok
                          ? `${label}: supported. Enables ${gates}`
                          : `${label}: ${report.errors[key] ?? "unsupported"}. Disables ${gates}`
                      }
                    >
                      {ok ? (
                        <Check className="size-3 text-emerald-600" />
                      ) : (
                        <X className="text-destructive size-3" />
                      )}
                      {label}
                    </span>
                  );
                })
              ) : (
                <span className="text-muted-foreground">Not tested</span>
              )}
              <Button
                size="sm"
                variant="ghost"
                disabled={probing !== null}
                onClick={() => onProbe(model)}
              >
                {probing === model ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : (
                  "Test"
                )}
              </Button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
