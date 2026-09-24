"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { useOpenAIInfo } from "@/components/settings/models-section";
import { SettingCard, SettingCardAction } from "@/components/settings/setting-card";
import { RemoveButton } from "@/components/settings/setting-layout";
import { Button } from "@/components/ui/button";
import { CardSection } from "@/components/ui/card";
import { focusIfDropped } from "@/hooks/use-focus-return";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { providerLabel, showsModelId, sourceLabel } from "@/lib/model-catalog";
import type {
  DiscoveredModel,
  ModelOption,
  ModelSyncResult,
  OpenAIInfo,
} from "@/lib/types";

type SyncProvider = "openai" | "gemini";

/**
 * The models the role pickers offer, as its own card. It used to be the fourth block of the Models
 * card, a bordered sub-list with its own scroller inside a scrolling page.
 */
export function ModelCatalogSection() {
  const info = useOpenAIInfo();
  return (
    <SettingCard
      id="model-catalog"
      title="Available models"
      description="Models you can pick above: the built-in ones and any you add."
      errorTitle="Couldn't load the model list."
      skeleton="h-32 w-full"
      query={info}
    >
      {(data) => <ModelCatalogPanel info={data} />}
    </SettingCard>
  );
}

function ModelCatalogPanel({ info }: { info: OpenAIInfo }) {
  const qc = useQueryClient();
  const [discovery, setDiscovery] = useState<{
    provider: SyncProvider;
    models: DiscoveredModel[];
  } | null>(null);
  const [syncing, setSyncing] = useState<SyncProvider | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  // Armed by a Remove click: the model going, and where focus goes once its
  // row (and the focused button in it) has left the list.
  const leaving = useRef<{ id: string; next: () => HTMLElement | null } | null>(null);

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
          ? `Found ${result.models.length} ${providerLabel(provider)} models`
          : `No ${providerLabel(provider)} models found`,
      );
    },
    onError: (err: Error) => toast.error(couldnt("find models", err)),
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
      toast.success(`Added ${model.label}`);
    },
    onError: (err: Error) => toast.error(couldnt("add the model", err)),
  });

  // Takes the whole row, so the toast names the model the user saw.
  const remove = useMutation({
    mutationFn: (option: ModelOption) =>
      apiFetch<OpenAIInfo>(
        `/api/settings/openai/models/${encodeURIComponent(option.id)}`,
        { method: "DELETE" },
      ),
    onSuccess: (result, { id: modelId, label }) => {
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
      toast.success(`Removed ${label}`);
    },
    onError: (err: Error) => {
      leaving.current = null;
      toast.error(couldnt("remove the model", err));
    },
  });
  // A double click sent two POSTs, or two DELETEs whose second failed with an error toast.
  const addOnce = useSingleFlight(add.mutate);
  const removeOnce = useSingleFlight(remove.mutate);

  // After the list re-renders without the removed row: its focused Remove
  // went with it, so focus fell to <body>. An Add that lands mid-removal
  // re-renders the list with the row still in it, so wait for the row to go.
  useEffect(() => {
    const pending = leaving.current;
    if (!pending || info.model_options.some((option) => option.id === pending.id)) return;
    leaving.current = null;
    focusIfDropped(pending.next());
  }, [info.model_options]);

  const removeRow = (li: HTMLElement | null, option: ModelOption) => {
    // The next row's Remove, else the previous row's, else the list itself
    // (built-in rows have no button). `focusSuccessor` would land on a
    // built-in row's <li>, which cannot take focus, so this list names its own.
    const pick = (el: Element | null | undefined) =>
      el?.querySelector<HTMLElement>("button") ?? null;
    const neighbour = pick(li?.nextElementSibling) ?? pick(li?.previousElementSibling);
    leaving.current = {
      id: option.id,
      next: () => (neighbour?.isConnected ? neighbour : listRef.current),
    };
    removeOnce(option);
  };

  return (
    <div className="grid gap-4">
      <SettingCardAction>
        {(["openai", "gemini"] as const).map((provider) => (
          <Button
            key={provider}
            size="sm"
            variant="outline"
            focusableWhenDisabled
            disabled={syncing !== null}
            className="data-disabled:pointer-events-none data-disabled:opacity-50"
            onClick={() => sync.mutate(provider)}
          >
            {syncing === provider ? (
              <Loader2 className="size-3 animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw className="size-3" aria-hidden="true" />
            )}
            Find {providerLabel(provider)} models
          </Button>
        ))}
      </SettingCardAction>

      {/* min-w-0: a grid child is min-width:auto, so a long id widened the list past the card and
          `truncate` never applied; the Remove went off the card. */}
      <ul ref={listRef} tabIndex={-1} aria-label="Available models" className="min-w-0 divide-y outline-none">
        {info.model_options.map((option) => (
          <CatalogRow
            key={option.id}
            option={option}
            busy={remove.isPending}
            onRemove={(li) => removeRow(li, option)}
          />
        ))}
      </ul>

      {discovery ? (
        <CardSection className="grid min-w-0 gap-3">
          <p className="text-muted-foreground text-xs">
            Select + to add a model, then choose it above.
          </p>
          <ul
            aria-label={`${providerLabel(discovery.provider)} models`}
            className="max-h-72 min-w-0 divide-y overflow-y-auto"
          >
            {discovery.models.map((model) => (
              <li key={model.id} className="flex min-h-10 items-center gap-2 py-1 text-xs">
                <span className="min-w-0 flex-1 truncate font-mono" title={model.id}>
                  {model.id}
                </span>
                {/* The same element before and after: it flips to a check and
                    keeps focus, where the old "Added" span dropped it. */}
                <Button
                  size="icon-sm"
                  variant="ghost"
                  focusableWhenDisabled
                  disabled={model.in_catalog || add.isPending}
                  aria-label={model.in_catalog ? `${model.id} added` : `Add ${model.id}`}
                  className="data-disabled:pointer-events-none data-disabled:opacity-50"
                  onClick={() => addOnce(model)}
                >
                  {model.in_catalog ? <Check aria-hidden="true" /> : <Plus aria-hidden="true" />}
                </Button>
              </li>
            ))}
          </ul>
        </CardSection>
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
  onRemove: (li: HTMLElement | null) => void;
}) {
  // Only an added model can go. A built-in one ships with the app, and an
  // "In use" one is listed because a role names it.
  return (
    <li className="flex min-h-10 items-center gap-3 py-1.5">
      <div className="min-w-0 flex-1">
        {/* A cut-off name or id stays whole on hover (`title`) and to a screen reader (the text is
            all in the DOM; only its paint is clipped). */}
        <p className="truncate text-sm font-medium" title={option.label}>{option.label}</p>
        {showsModelId(option) ? (
          <p className="text-muted-foreground truncate font-mono text-xs" title={option.id}>
            {option.id}
          </p>
        ) : null}
      </div>
      <span className="text-muted-foreground shrink-0 text-xs">
        {providerLabel(option.provider)} · {sourceLabel(option.source)}
      </span>
      {option.source === "extra" ? (
        <RemoveButton
          label={`Remove ${option.id}`}
          disabled={busy}
          onClick={(event) => onRemove(event.currentTarget.closest("li"))}
        />
      ) : null}
    </li>
  );
}
