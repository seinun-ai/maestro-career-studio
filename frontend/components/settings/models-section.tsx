"use client";

import { useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  CapabilityMatrix,
  EndpointControls,
} from "@/components/settings/llm-endpoint";
import { ModelCatalogPanel } from "@/components/settings/model-catalog-panel";
import { SettingCard } from "@/components/settings/setting-card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import type { CapabilityReport, OpenAIInfo } from "@/lib/types";

export type ModelSettingsPatch = {
  fast_model?: string;
  smart_model?: string;
  chat_model?: string;
  openai_api_key?: string | null;
  gemini_api_key?: string | null;
  base_url?: string | null;
  json_mode?: string;
};

export function useOpenAIInfo() {
  return useQuery({
    queryKey: ["settings", "openai"],
    queryFn: () => apiFetch<OpenAIInfo>("/api/settings/openai"),
  });
}

/**
 * Writes to `/api/settings/openai`.
 *
 * Fields the caller omits are omitted from the request too, and the backend
 * leaves an omitted field's stored value alone. That is what lets a model
 * change avoid touching a stored API key — and, now that Models and API keys
 * are two cards, what lets either one write without echoing the other's state.
 */
export function useSaveModelSettings(onSaved?: (info: OpenAIInfo) => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: ModelSettingsPatch) =>
      apiFetch<OpenAIInfo>("/api/settings/openai", {
        method: "PUT",
        body: JSON.stringify(patch),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "openai"], result);
      onSaved?.(result);
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function ModelsSection() {
  const info = useOpenAIInfo();
  const [probing, setProbing] = useState<string | null>(null);
  const save = useSaveModelSettings(() => toast.success("Model settings saved"));

  const probe = useMutation({
    mutationFn: (model: string) =>
      apiFetch<CapabilityReport>("/api/settings/openai/probe", {
        method: "POST",
        body: JSON.stringify({ model }),
      }),
    onMutate: (model: string) => setProbing(model),
    onSettled: () => setProbing(null),
    onSuccess: (report) => {
      void info.refetch();
      const missing = (["text", "json", "tools"] as const).filter((c) => !report[c]);
      if (report.reachable === false) {
        // The call never reached the model, so this says nothing about it —
        // and nothing was recorded. Blaming the model here is what sent the
        // author hunting a model bug that was a mistyped key.
        const why = Object.values(report.errors ?? {})[0] ?? "the request failed";
        toast.error(
          `Could not reach the API, so ${report.model} was not tested: ${why}. ` +
            `Check the API key and endpoint, then test again.`,
        );
      } else if (missing.length === 0) {
        toast.success(`${report.model} supports everything`);
      } else {
        toast.warning(
          `${report.model} cannot do: ${missing.join(", ")}. Other surfaces still work.`,
        );
      }
    },
    onError: (err: Error) => toast.error(err.message),
  });

  return (
    <SettingCard
      id="models"
      title="Models"
      description="Which model answers for each role, the endpoint they run against, and a catalog you can grow with Sync."
      errorTitle="Couldn't load your model settings."
      skeleton="h-48 w-full"
      query={info}
    >
      {(data) => (
        <div className="space-y-4 text-sm">
          <ModelProfileNote />
          <div className="grid gap-3 sm:grid-cols-3">
            <ModelField
              label="Fast model"
              value={data.fast_model}
              options={data.model_options}
              custom={data.custom_endpoint}
              disabled={save.isPending}
              onChange={(value) => value && save.mutate({ fast_model: value })}
            />
            <ModelField
              label="Smart model"
              value={data.smart_model}
              options={data.model_options}
              custom={data.custom_endpoint}
              disabled={save.isPending}
              onChange={(value) => value && save.mutate({ smart_model: value })}
            />
            <ModelField
              label="Chat model · needs streaming tool calls, so test it"
              value={data.chat_model}
              options={data.model_options}
              custom={data.custom_endpoint}
              disabled={save.isPending}
              onChange={(value) => value && save.mutate({ chat_model: value })}
            />
          </div>
          <EndpointControls
            info={data}
            disabled={save.isPending}
            onSave={(patch) => save.mutate(patch)}
          />
          <CapabilityMatrix
            info={data}
            probing={probing}
            onProbe={(model) => probe.mutate(model)}
          />
          <ModelCatalogPanel info={data} />
        </div>
      )}
    </SettingCard>
  );
}

/**
 * The measured-profile note, behind a disclosure.
 *
 * It used to be five sentences sitting open in the card header — the longest
 * block of copy in Settings, above the controls it describes, read once and
 * then in the way forever. It is genuinely useful the first time and noise
 * every time after, which is what a disclosure is for.
 */
function ModelProfileNote() {
  const [open, setOpen] = useState(false);
  return (
    <div className="text-xs">
      <button
        type="button"
        className="text-muted-foreground hover:text-foreground underline underline-offset-4"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        Which models did you measure?
      </button>
      {open && (
        <p className="text-muted-foreground mt-2 max-w-prose">
          Two measured profiles, one per key: GPT-5.6 Luna on every tier (the
          default — most thorough JD extraction we tested, about a penny per
          application, slower) or Gemini 3.7 Flash on every tier (fastest, under
          3¢ per application, promo pricing doubles Jan 2027). In our tests the
          Fast model decided extraction coverage and score honesty; the Smart
          choice barely moved the result. Prices and tiers move constantly —
          treat this as a starting point, not a recommendation with a shelf
          life.
        </p>
      )}
    </div>
  );
}

export function ApiKeysSection() {
  const info = useOpenAIInfo();
  // The API never returns key material, so these inputs hold only what the
  // user types this session. null = untouched, which means the PUT omits the
  // field entirely and the stored key survives.
  const [openaiKey, setOpenaiKey] = useState<string | null>(null);
  const [geminiKey, setGeminiKey] = useState<string | null>(null);

  const save = useSaveModelSettings(() => {
    setOpenaiKey(null);
    setGeminiKey(null);
    toast.success("API keys saved");
  });

  return (
    <SettingCard
      id="api-keys"
      title="API keys"
      description="Provider credentials. Leave a field blank to fall back to .env."
      errorTitle="Couldn't load your API key status."
      skeleton="h-32 w-full"
      query={info}
    >
      {(data) => (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <KeyField
              label="OpenAI API key"
              placeholderUnset="sk-..."
              configured={data.api_key_configured}
              source={data.openai_key_source}
              value={openaiKey}
              disabled={save.isPending}
              onChange={setOpenaiKey}
            />
            <KeyField
              label="Gemini API key"
              placeholderUnset="AIza..."
              configured={data.gemini_api_key_configured}
              source={data.gemini_key_source}
              value={geminiKey}
              disabled={save.isPending}
              onChange={setGeminiKey}
            />
          </div>
          <div className="flex items-center justify-between">
            <p className="text-muted-foreground text-xs">
              Leave blank to use defaults from <code>.env</code>.
            </p>
            <Button
              size="sm"
              disabled={
                save.isPending || (openaiKey === null && geminiKey === null)
              }
              onClick={() =>
                // Send only the key the user actually edited. An untouched
                // field stays absent (preserved); a field cleared to empty
                // sends null (removes it).
                save.mutate({
                  ...(openaiKey !== null ? { openai_api_key: openaiKey || null } : {}),
                  ...(geminiKey !== null ? { gemini_api_key: geminiKey || null } : {}),
                })
              }
            >
              {save.isPending ? "Saving…" : "Save API keys"}
            </Button>
          </div>
        </div>
      )}
    </SettingCard>
  );
}

function KeyField({
  label,
  placeholderUnset,
  configured,
  source,
  value,
  disabled,
  onChange,
}: {
  label: string;
  placeholderUnset: string;
  configured: boolean;
  source: OpenAIInfo["openai_key_source"];
  value: string | null;
  disabled: boolean;
  onChange: (next: string) => void;
}) {
  const labelId = useId();
  return (
    <div className="grid gap-1.5">
      <div className="flex items-center justify-between text-xs">
        <Label id={labelId} className="text-muted-foreground text-xs font-normal">
          {label}
        </Label>
        {configured ? (
          // Saying WHERE the key lives matters: one saved here beats .env, so
          // a stale in-app key with a blank .env still reads "configured"
          // while every call 401s.
          <span className="font-medium text-emerald-600">
            {source === "env" ? "Configured · from .env" : "Configured · in-app"}
          </span>
        ) : (
          <span className="text-destructive font-medium">Not configured</span>
        )}
      </div>
      <Input
        type="password"
        // Named by the caption alone. The status beside it is live text that
        // would otherwise be read as part of the field's name.
        aria-labelledby={labelId}
        placeholder={configured ? "Saved · type to replace" : placeholderUnset}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
    </div>
  );
}

/** Dropdown for curated hosted models; free text once a custom endpoint is set.
 *
 *  `model_options` lists models we have verified. It cannot enumerate what an
 *  arbitrary Ollama or vLLM host serves, so forcing a dropdown there would make
 *  every local model unselectable. */
function ModelField({
  label,
  value,
  options,
  custom,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  options: OpenAIInfo["model_options"];
  custom: boolean;
  disabled: boolean;
  onChange: (value: string | null) => void;
}) {
  if (custom) {
    return (
      <FreeTextModel
        label={label}
        value={value}
        disabled={disabled}
        onChange={onChange}
      />
    );
  }
  return (
    <ModelSelect
      label={label}
      value={value}
      options={options}
      disabled={disabled}
      onChange={onChange}
    />
  );
}

function FreeTextModel({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  disabled: boolean;
  onChange: (value: string | null) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const id = useId();
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id} className="text-muted-foreground text-xs font-normal">
        {label}
      </Label>
      <Input
        id={id}
        value={draft ?? value}
        placeholder="llama3.2:3b"
        disabled={disabled}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          const next = (draft ?? "").trim();
          if (draft !== null && next && next !== value) onChange(next);
          setDraft(null);
        }}
      />
    </div>
  );
}

function ModelSelect({
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  options: OpenAIInfo["model_options"];
  disabled: boolean;
  onChange: (value: string | null) => void;
}) {
  const selected = options.find((option) => option.id === value);
  const stale = Boolean(value) && selected === undefined;
  const id = useId();
  const groups = [
    {
      key: "openai",
      title: "OpenAI",
      options: options.filter((option) => option.provider === "openai"),
    },
    {
      key: "gemini",
      title: "Gemini",
      options: options.filter((option) => option.provider === "gemini"),
    },
  ].filter((group) => group.options.length > 0);

  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id} className="text-muted-foreground text-xs font-normal">
        {label}
      </Label>
      <Select value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue>{stale ? value : selected?.label}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {stale ? (
            <SelectItem value={value} disabled>
              «{value}» · unavailable
            </SelectItem>
          ) : null}
          {groups.map((group) => (
            <SelectGroup key={group.key}>
              <SelectLabel>{group.title}</SelectLabel>
              {group.options.map((option) => (
                <SelectItem key={option.id} value={option.id}>
                  <span>{option.label}</span>
                  <span className="text-muted-foreground font-mono text-xs">
                    {option.id}
                  </span>
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
