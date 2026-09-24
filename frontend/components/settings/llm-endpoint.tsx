"use client";

import { useId, useState } from "react";
import { ChevronRight } from "lucide-react";
import { toast } from "sonner";

import {
  useOpenAIInfo,
  useSaveModelSettings,
} from "@/components/settings/models-section";
import { SettingCard } from "@/components/settings/setting-card";
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
import { isRemoteEndpoint } from "@/lib/model-catalog";
import type { OpenAIInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * A model server of the user's own (Ollama, LM Studio), as its own card. Most installs never touch
 * it, so it sits last among the model cards and starts collapsed.
 */
export function CustomEndpointSection() {
  const info = useOpenAIInfo();
  const save = useSaveModelSettings(() => toast.success("Server settings saved"));
  return (
    <SettingCard
      id="custom-endpoint"
      title="Custom AI server"
      description="Run models on your own server, such as Ollama or LM Studio."
      errorTitle="Couldn't load your server settings."
      skeleton="h-10 w-full"
      query={info}
    >
      {(data) => (
        <EndpointDisclosure
          info={data}
          disabled={save.isPending}
          onSave={(patch, onSuccess) => save.mutate(patch, { onSuccess })}
        />
      )}
    </SettingCard>
  );
}

/** A server-settings write. `onSuccess` runs only once the server has taken it. */
type SaveEndpoint = (
  patch: { base_url?: string | null; json_mode?: string },
  onSuccess?: () => void,
) => void;

/** Starts collapsed unless something is set. `hidden`, not unmounted: a typed
 *  address survives a collapse. */
function EndpointDisclosure({
  info,
  disabled,
  onSave,
}: {
  info: OpenAIInfo;
  disabled: boolean;
  onSave: SaveEndpoint;
}) {
  const [open, setOpen] = useState(Boolean(info.base_url) || info.json_mode !== "auto");
  const panelId = useId();
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted-foreground min-w-0 text-sm wrap-anywhere">
          {info.base_url ? (
            <>
              Using <code className="font-mono text-xs">{info.base_url}</code>
            </>
          ) : (
            "Not set. Models run on the OpenAI and Gemini APIs."
          )}
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((o) => !o)}
        >
          <ChevronRight
            className={cn("transition-transform", open && "rotate-90")}
            aria-hidden="true"
          />
          Advanced
        </Button>
      </div>
      <div id={panelId} hidden={!open}>
        <EndpointControls info={info} disabled={disabled} onSave={onSave} />
      </div>
    </div>
  );
}

function EndpointControls({
  info,
  disabled,
  onSave,
}: {
  info: OpenAIInfo;
  disabled: boolean;
  onSave: SaveEndpoint;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const value = draft ?? info.base_url ?? "";
  const endpointId = useId();
  const endpointHintId = useId();
  const jsonModeId = useId();
  const jsonModeHintId = useId();

  return (
    <div className="grid gap-4 @xl/setting:grid-cols-[2fr_1fr]">
      <div className="grid content-start gap-1.5">
        <Label htmlFor={endpointId} optional>
          OpenAI-compatible endpoint
        </Label>
        <p id={endpointHintId} className="text-muted-foreground text-xs">
          Point at Ollama, LM Studio, vLLM or OpenRouter and nothing leaves this
          machine. Leave empty for the OpenAI API.
        </p>
        <div className="flex gap-2">
          <Input
            id={endpointId}
            aria-describedby={endpointHintId}
            placeholder="e.g. http://host.docker.internal:11434/v1"
            value={value}
            disabled={disabled}
            onChange={(e) => setDraft(e.target.value)}
          />
          {/* The draft clears only once the server takes it: a rejected
              address stays in the field to fix. Focusable while it saves. */}
          <Button
            variant="outline"
            focusableWhenDisabled
            disabled={disabled || draft === null}
            className="data-disabled:pointer-events-none data-disabled:opacity-50"
            onClick={() =>
              onSave({ base_url: draft?.trim() || null }, () => setDraft(null))
            }
          >
            Save
          </Button>
        </div>
        {isRemoteEndpoint(value) && (
          <p className="text-xs text-amber-700 dark:text-amber-500">
            Your API key and resume text will be sent to this server. Only point
            it somewhere you trust.
          </p>
        )}
      </div>
      <div className="grid content-start gap-1.5">
        <Label htmlFor={jsonModeId}>JSON mode</Label>
        <p id={jsonModeHintId} className="text-muted-foreground text-xs">
          Auto sends <code>response_format</code> only to the OpenAI API. Some
          servers reject the field outright.
        </p>
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
  );
}
