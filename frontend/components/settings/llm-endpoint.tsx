"use client";

import { useId, useState } from "react";
import { ChevronRight } from "lucide-react";
import { toast } from "sonner";

import {
  useOpenAIInfo,
  useSaveModelSettings,
} from "@/components/settings/models-section";
import { SettingCard } from "@/components/settings/setting-card";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useSingleFlight } from "@/hooks/use-single-flight";
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
  // The typed address; null = untouched. It lives here, beside the save that takes it, and clears
  // only once the server has taken it: a rejected address stays in the field to fix. A JSON mode
  // pick is a save too, and leaves a typed address alone.
  const [draft, setDraft] = useState<string | null>(null);
  // A typed address survives a tab switch and a collapse, but a navigation dropped it silently.
  useLeaveGuard(draft !== null);
  const save = useSaveModelSettings((_info, patch) => {
    if ("base_url" in patch) setDraft(null);
    toast.success("Server settings saved");
  });
  const saveOnce = useSingleFlight(save.mutate);
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
          draft={draft}
          onDraft={setDraft}
          saving={save.isPending}
          onSave={saveOnce}
        />
      )}
    </SettingCard>
  );
}

/** A server-settings write, one per gesture. */
type SaveEndpoint = (patch: { base_url?: string | null; json_mode?: string }) => void;

type EndpointProps = {
  info: OpenAIInfo;
  draft: string | null;
  onDraft: (draft: string) => void;
  saving: boolean;
  onSave: SaveEndpoint;
};

/** Starts collapsed unless something is set. `hidden`, not unmounted: a typed
 *  address survives a collapse. */
function EndpointDisclosure(props: EndpointProps) {
  const { info } = props;
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
            "Not set. Models run on OpenAI and Gemini."
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
        <EndpointControls {...props} />
      </div>
    </div>
  );
}

function EndpointControls({ info, draft, onDraft, saving, onSave }: EndpointProps) {
  const value = draft ?? info.base_url ?? "";
  const endpointId = useId();
  const endpointHintId = useId();
  const jsonModeId = useId();
  const jsonModeHintId = useId();

  return (
    <div className="grid gap-4 @xl/setting:grid-cols-[2fr_1fr]">
      <div className="grid content-start gap-1.5">
        <Label htmlFor={endpointId} optional>
          Server address
        </Label>
        {/* Names only servers that run on this computer. A hosted service is
            not local: it receives the key and the resume, which the warning
            below says whenever the address is not local. */}
        <p id={endpointHintId} className="text-muted-foreground text-xs">
          The address of a model server on your computer, such as Ollama or LM
          Studio. It usually ends in /v1. Leave empty to use OpenAI and Gemini.
        </p>
        <div className="flex gap-2">
          <Input
            id={endpointId}
            aria-describedby={endpointHintId}
            value={value}
            // readOnly, not disabled, while it saves: a disabled field drops focus to <body>.
            readOnly={saving}
            onChange={(e) => onDraft(e.target.value)}
          />
          {/* Focusable while it saves. */}
          <Button
            variant="outline"
            focusableWhenDisabled
            disabled={saving || draft === null}
            className="data-disabled:pointer-events-none data-disabled:opacity-50"
            onClick={() => onSave({ base_url: draft?.trim() || null })}
          >
            Save
          </Button>
        </div>
        {isRemoteEndpoint(value) && (
          <p className="text-xs text-amber-700 dark:text-amber-500">
            Your API key and resume will be sent to this server. Use one you
            trust.
          </p>
        )}
      </div>
      <div className="grid content-start gap-1.5">
        {/* json_mode: Auto sends response_format only to OpenAI's own API; Off never
            sends it, which is what a server that rejects the field needs. */}
        <Label htmlFor={jsonModeId}>Strict reply format</Label>
        <p id={jsonModeHintId} className="text-muted-foreground text-xs">
          Asks the model to reply in the exact format the app reads. Leave on Auto. If your
          server shows errors, choose Off.
        </p>
        <Select
          value={info.json_mode}
          readOnly={saving}
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
