"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type {
  DiscoveredModel,
  ModelOption,
  ModelSyncResult,
  OpenAIInfo,
} from "@/lib/types";

type SyncProvider = "openai" | "gemini";

export function ModelCatalogPanel({ info }: { info: OpenAIInfo }) {
  const qc = useQueryClient();
  const [discovery, setDiscovery] = useState<{
    provider: SyncProvider;
    models: DiscoveredModel[];
  } | null>(null);
  const [syncing, setSyncing] = useState<SyncProvider | null>(null);

  const sync = useMutation({
    mutationFn: (provider: SyncProvider) =>
      apiFetch<ModelSyncResult>("/api/settings/openai/sync", {
        method: "POST",
        body: JSON.stringify({ provider }),
      }),
    onMutate: (provider) => setSyncing(provider),
    onSettled: () => setSyncing(null),
    onSuccess: (result, provider) => {
      setDiscovery({ provider, models: result.models });
      toast.success(
        result.models.length
          ? `Found ${result.models.length} ${provider} models`
          : `No chat-like ${provider} models returned`,
      );
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const add = useMutation({
    mutationFn: (model: DiscoveredModel) =>
      apiFetch<OpenAIInfo>("/api/settings/openai/models", {
        method: "POST",
        body: JSON.stringify({
          id: model.id,
          provider: model.provider,
          label: model.label,
        }),
      }),
    onSuccess: (result, model) => {
      qc.setQueryData(["settings", "openai"], result);
      setDiscovery((prev) =>
        prev
          ? {
              ...prev,
              models: prev.models.map((row) =>
                row.id === model.id ? { ...row, in_catalog: true } : row,
              ),
            }
          : prev,
      );
      toast.success(`Added ${model.id}`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const remove = useMutation({
    mutationFn: (modelId: string) =>
      apiFetch<OpenAIInfo>(
        `/api/settings/openai/models/${encodeURIComponent(modelId)}`,
        { method: "DELETE" },
      ),
    onSuccess: (result, modelId) => {
      qc.setQueryData(["settings", "openai"], result);
      setDiscovery((prev) =>
        prev
          ? {
              ...prev,
              models: prev.models.map((row) =>
                row.id === modelId ? { ...row, in_catalog: false } : row,
              ),
            }
          : prev,
      );
      toast.success(`Removed ${modelId}`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  return (
    <div className="space-y-3 border-t pt-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs font-medium">Available models</p>
          <p className="text-muted-foreground text-xs">
            Built-in seeds plus models you add from Sync. Role dropdowns pick from
            this list.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={syncing !== null}
            onClick={() => sync.mutate("openai")}
          >
            {syncing === "openai" ? (
              <Loader2 className="size-3 animate-spin" />
            ) : (
              <RefreshCw className="size-3" />
            )}
            Sync OpenAI
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={syncing !== null}
            onClick={() => sync.mutate("gemini")}
          >
            {syncing === "gemini" ? (
              <Loader2 className="size-3 animate-spin" />
            ) : (
              <RefreshCw className="size-3" />
            )}
            Sync Gemini
          </Button>
        </div>
      </div>

      <ul className="max-h-48 space-y-1 overflow-y-auto text-xs">
        {info.model_options.map((option) => (
          <CatalogRow
            key={option.id}
            option={option}
            busy={remove.isPending}
            onRemove={() => remove.mutate(option.id)}
          />
        ))}
      </ul>

      {discovery ? (
        <div className="space-y-2 rounded-lg border p-3">
          <p className="text-muted-foreground text-xs">
            {discovery.provider === "openai" ? "OpenAI" : "Gemini"} discovery —{" "}
            <span className="font-medium text-foreground">+</span> adds to the
            catalog; then choose it under Fast, Smart, or Chat.
          </p>
          <ul className="max-h-56 space-y-1 overflow-y-auto">
            {discovery.models.map((model) => (
              <li
                key={model.id}
                className="flex items-center gap-2 text-xs"
              >
                <span className="min-w-0 flex-1 truncate font-mono">{model.id}</span>
                {model.in_catalog ? (
                  <span className="text-muted-foreground shrink-0">Added</span>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="size-7 shrink-0 p-0"
                    aria-label={`Add ${model.id}`}
                    disabled={add.isPending}
                    onClick={() => add.mutate(model)}
                  >
                    <Plus className="size-3.5" />
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function CatalogRow({
  option,
  busy,
  onRemove,
}: {
  option: ModelOption;
  busy: boolean;
  onRemove: () => void;
}) {
  const isExtra = option.source === "extra";
  // Never call a configured-only id a seed: it is in this list because a role
  // names it, not because we ship it.
  const isConfigured = option.source === "configured";
  return (
    <li className="flex items-center gap-2">
      <span className="min-w-0 flex-1 truncate">
        <span className="font-medium">{option.label}</span>{" "}
        <span className="text-muted-foreground font-mono">{option.id}</span>
      </span>
      <span className="text-muted-foreground shrink-0 capitalize">
        {option.provider}
        {isExtra ? "" : isConfigured ? " · in use" : " · seed"}
      </span>
      {isExtra ? (
        <Button
          size="sm"
          variant="ghost"
          className="text-destructive size-7 shrink-0 p-0"
          aria-label={`Remove ${option.id}`}
          disabled={busy}
          onClick={onRemove}
        >
          <Trash2 className="size-3.5" />
        </Button>
      ) : null}
    </li>
  );
}
