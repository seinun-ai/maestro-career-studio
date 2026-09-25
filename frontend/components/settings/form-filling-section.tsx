"use client";

import { useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { NewTabLink } from "@/components/new-tab-link";
import { KeyField } from "@/components/settings/models-section";
import { SettingCard } from "@/components/settings/setting-card";
import { ACTION_ROW } from "@/components/settings/setting-layout";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import type { JevInfo } from "@/lib/types";

type JevPatch = Partial<Pick<JevInfo, "base_url" | "model" | "engine">> & {
  api_key?: string | null;
};

// Both serve Jev on the same path; the model id differs by provider.
const PROVIDERS = [
  { url: "https://openrouter.ai/api", label: "OpenRouter", model: "typesafe/jev-1.13" },
  { url: "https://api.typesafe.ai", label: "TypeSafe", model: "jev-latest" },
] as const;

const ENGINES: Record<JevInfo["engine"], string> = { fast: "Fast model", jev: "Jev" };

function useJevInfo() {
  return useQuery({
    queryKey: ["settings", "jev"],
    queryFn: () => apiFetch<JevInfo>("/api/settings/jev"),
  });
}

/** Jev (TypeSafe AI) as the Companion's form-filling decision engine: its key,
 *  where it is served from, and whether the fill pass uses it. The fast model
 *  stays the default and answers whatever Jev cannot place. */
export function FormFillingSection() {
  const info = useJevInfo();
  const qc = useQueryClient();
  // The API never returns the key: null = untouched, so the PUT omits it.
  const [key, setKey] = useState<string | null>(null);
  useLeaveGuard(key !== null);
  const providerId = useId();
  const engineId = useId();
  const engineHintId = useId();

  const save = useMutation({
    mutationFn: (patch: JevPatch) =>
      apiFetch<JevInfo>("/api/settings/jev", { method: "PUT", body: JSON.stringify(patch) }),
    onSuccess: (result, patch) => {
      const before = qc.getQueryData<JevInfo>(["settings", "jev"]);
      qc.setQueryData(["settings", "jev"], result);
      setKey(null);
      // The server forgets a key when the provider changes: a key is only ever
      // sent to the company it came from.
      if (patch.base_url && before?.api_key_configured && !result.api_key_configured) {
        toast.message("Add a key for the new provider. The old one was removed.");
      }
    },
    onError: (err: Error) => toast.error(couldnt("save your form filling settings", err)),
  });
  const saveOnce = useSingleFlight(save.mutate);

  const probe = useMutation({
    mutationFn: () =>
      apiFetch<{ ok: boolean; error: string | null }>("/api/settings/jev/probe", {
        method: "POST",
      }),
    onSuccess: (r) =>
      r.ok ? toast.success("Jev answered.") : toast.error(r.error ?? "Jev didn't answer."),
    onError: (err: Error) => toast.error(couldnt("test your Jev key", err)),
  });

  return (
    <SettingCard
      id="form-filling"
      title="Form filling"
      description="Jev picks answers for application forms in about a tenth of a second. Questions that need a written answer still go to your fast model."
      errorTitle="Couldn't load your form filling settings."
      skeleton="h-32 w-full"
      query={info}
    >
      {(data) => (
        <div className="grid gap-6">
          <div className="grid items-end gap-4 @lg/setting:grid-cols-2">
            <KeyField
              label="Jev API key"
              hintUnset={
                <>
                  An <NewTabLink href="https://openrouter.ai/keys">OpenRouter</NewTabLink> key
                  works, or one from typesafe.ai.
                </>
              }
              configured={data.api_key_configured}
              source={data.api_key_configured ? "settings" : "none"}
              value={key}
              saving={save.isPending}
              onChange={setKey}
            />
            <div className="grid gap-1.5">
              <Label htmlFor={providerId}>Provider</Label>
              {/* readOnly, not disabled, while a pick saves (ModelSelect's rule). */}
              <Select
                value={data.base_url}
                readOnly={save.isPending}
                onValueChange={(url) => {
                  const provider = PROVIDERS.find((p) => p.url === url);
                  if (provider) saveOnce({ base_url: provider.url, model: provider.model });
                }}
              >
                <SelectTrigger id={providerId} className="w-full">
                  <SelectValue>
                    {PROVIDERS.find((p) => p.url === data.base_url)?.label ?? data.base_url}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {PROVIDERS.map((p) => (
                    <SelectItem key={p.url} value={p.url}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={engineId}>Form filling decisions</Label>
            <p id={engineHintId} className="text-muted-foreground text-xs">
              {data.api_key_configured
                ? "Used when the Companion fills a form with saved answers and AI."
                : "Save a Jev API key to choose Jev."}
            </p>
            <Select
              value={data.engine}
              disabled={!data.api_key_configured}
              readOnly={save.isPending}
              onValueChange={(engine) => {
                if (engine) saveOnce({ engine: engine as JevInfo["engine"] });
              }}
            >
              <SelectTrigger id={engineId} aria-describedby={engineHintId} className="w-full">
                <SelectValue>{ENGINES[data.engine]}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="fast">{ENGINES.fast}</SelectItem>
                <SelectItem value="jev">{ENGINES.jev}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className={ACTION_ROW}>
            <Button
              size="sm"
              variant="outline"
              disabled={!data.api_key_configured || probe.isPending}
              onClick={() => probe.mutate()}
            >
              {probe.isPending ? "Testing…" : "Test"}
            </Button>
            <Button
              size="sm"
              disabled={save.isPending || key === null}
              onClick={() => saveOnce({ api_key: key?.trim() || null })}
            >
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      )}
    </SettingCard>
  );
}
