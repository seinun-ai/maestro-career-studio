"use client";

import { useId } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown } from "lucide-react";
import { toast } from "sonner";

import { LoadErrorState } from "@/components/load-error-state";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import {
  ApiKeysEditor,
  RECOMMENDED_KEY,
  followsSet,
  keyProblemIn,
  unreachableText,
  useOpenAIInfo,
  useRecommendedModels,
} from "@/components/settings/models-section";
import { SettingCard, SettingCardAction } from "@/components/settings/setting-card";
import { SwitchRow } from "@/components/settings/setting-layout";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
import { couldnt, loadErrorDetail } from "@/lib/error-text";
import {
  CONFIGURED,
  EVERYDAY_JOBS,
  PROVIDERS,
  everydayCan,
  everydayStatus,
  keysInUse,
  modelName,
  providerLabel,
  runsOn,
  type EverydayStatus,
  type Provider,
} from "@/lib/model-catalog";
import { isLoadFailure } from "@/lib/query-state";
import { cn } from "@/lib/utils";
import type { CapabilityReport, OpenAIInfo, RecommendedModelsInfo } from "@/lib/types";

/** "Claude", "OpenAI and Claude", "OpenAI, Claude and Gemini". */
function inWords(names: readonly string[]): string {
  return names.length < 2 ? (names[0] ?? "") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** Round means status: the dot's role for each state of the everyday jobs. */
const DOT: Record<EverydayStatus["kind"], string> = {
  works: "bg-success",
  untested: "bg-muted-foreground",
  "no-key": "bg-warning",
  cannot: "bg-warning",
};

/**
 * Settings › Basics' lead: where the everyday jobs run, whether they work, the model doing each, the
 * recommended set, and the API keys (the ones in use first, the others in a Fold).
 *
 * The status comes only from the saved capability tests (`capabilities` on `GET /api/settings/openai`,
 * written by the model test): a model never tested reads Not tested, never Works. The id stays
 * `api-keys`: every link that says "add a key" lands here (setup steps, `/new`'s notice).
 */
export function AiModelSection() {
  const info = useOpenAIInfo();
  const recommended = useRecommendedModels();
  const where = info.data ? runsOn(info.data) : [];
  return (
    <SettingCard
      id="api-keys"
      title={where.length > 0 ? `AI model: ${inWords(where)}` : "AI model"}
      errorTitle="Couldn't load your AI model settings."
      skeleton="h-48 w-full"
      query={info}
    >
      {/* Not gated on the recommended set: the keys are what a new install needs, so a failed read of
          the set leaves them here and says so in its own row. */}
      {(data) => <AiModelBody info={data} recommended={recommended} />}
    </SettingCard>
  );
}

function AiModelBody({
  info,
  recommended: query,
}: {
  info: OpenAIInfo;
  recommended: ReturnType<typeof useRecommendedModels>;
}) {
  const recommended = query.data;
  const qc = useQueryClient();
  const switchId = useId();
  const hintId = useId();
  const status = everydayStatus(info);
  const can = everydayCan(info);

  const save = useMutation({
    mutationFn: (body: { on: boolean; provider?: Provider }) =>
      apiFetch<RecommendedModelsInfo>("/api/settings/models/recommended", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: (result) => {
      qc.setQueryData(RECOMMENDED_KEY, result);
      // The four roles answer the set (or your own picks) now: every model reader refetches.
      void qc.invalidateQueries({ queryKey: ["settings", "openai"] });
    },
    onError: (err: Error) => toast.error(couldnt("save this setting", err)),
  });
  const saveOnce = useSingleFlight(save.mutate);
  const shown = save.isPending ? save.variables.on : (recommended?.on ?? false);
  const set = followsSet(recommended);

  return (
    <div className="grid gap-6">
      <SettingCardAction>
        {/* Says only Saving…, Saved or Not saved: the keys below keep an explicit Save, so "Saves
            automatically" at rest would be untrue of half the card. */}
        <AutosaveStatus pending={save.isPending} failed={save.isError} idle={false} />
        <TestButton info={info} />
        {recommended ? (
          <ChangeProvider
            info={info}
            recommended={recommended}
            busy={save.isPending}
            onPick={(provider) => saveOnce({ on: true, provider })}
          />
        ) : null}
      </SettingCardAction>

      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-body-medium">
        <span className="inline-flex items-center gap-1.5 font-medium">
          <span aria-hidden="true" className={cn("size-2 shrink-0 rounded-full", DOT[status.kind])} />
          {status.words}
        </span>
        {can.length > 0 ? <span className="text-muted-foreground">{can.join(" · ")}</span> : null}
      </p>

      <dl className="divide-y">
        {EVERYDAY_JOBS.map((job) => (
          <div key={job.role} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5">
            <dt className="text-muted-foreground text-body-medium">{job.words}</dt>
            <dd className="min-w-0 text-body-medium wrap-anywhere">{modelName(info.model_options, info[job.role])}</dd>
          </div>
        ))}
      </dl>

      {recommended ? (
        <div className="grid gap-1">
          <SwitchRow htmlFor={switchId} label="Use recommended models">
            <Switch
              id={switchId}
              aria-describedby={hintId}
              checked={shown}
              onCheckedChange={(on) => {
                if (!save.isPending) saveOnce({ on });
              }}
            />
          </SwitchRow>
          <p id={hintId} className="text-muted-foreground text-body-small">
            {set
              ? `${set}'s recommended models do each job. Your own picks come back when you turn this off.`
              : recommended.on
                ? "None of your saved keys has a recommended set, so each job uses the model you picked."
                : "Each job uses the model you pick in Advanced."}
          </p>
        </div>
      ) : isLoadFailure(query) ? (
        <LoadErrorState
          className="py-4"
          title="Couldn't load the recommended models."
          detail={loadErrorDetail(query.error)}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
        />
      ) : (
        <Skeleton className="h-11 w-full" />
      )}

      <ApiKeysEditor data={info} inUse={keysInUse(info)} />
    </div>
  );
}

/**
 * Tests the everyday jobs' models, one after another, and says one thing: the first key problem, else
 * the first model it couldn't reach, else the first job a model can't do, else that every job works.
 * The per-model Test is in Advanced › Model per job.
 */
function TestButton({ info }: { info: OpenAIInfo }) {
  const qc = useQueryClient();
  const models = [...new Set(EVERYDAY_JOBS.map((job) => info[job.role]))];
  const tested = models.some((model) => info.capabilities[model] !== undefined);
  const run = useMutation({
    mutationFn: async () => {
      const reports: CapabilityReport[] = [];
      for (const model of models) {
        reports.push(
          await apiFetch<CapabilityReport>("/api/settings/openai/probe", {
            method: "POST",
            body: JSON.stringify({ model }),
          }),
        );
      }
      return reports;
    },
    onSuccess: (reports) => {
      void qc.invalidateQueries({ queryKey: ["settings", "openai"] });
      const name = (model: string) => modelName(info.model_options, model);
      for (const report of reports) {
        const keyProblem = keyProblemIn(report);
        if (keyProblem) {
          toast.error(`Couldn't test ${name(report.model)}. ${keyProblem}`);
          return;
        }
      }
      const unreached = reports.find((report) => report.reachable === false);
      if (unreached) {
        // The provider's own text goes to the console, not the screen (the model test's rule).
        console.error("model test: unreachable", unreached.errors);
        toast.error(unreachableText(info, unreached.model, name(unreached.model)));
        return;
      }
      const byModel = new Map(reports.map((report) => [report.model, report]));
      const failed = EVERYDAY_JOBS.find((job) => {
        const report = byModel.get(info[job.role]);
        return report !== undefined && job.needs.some((need) => !report[need]);
      });
      if (failed) {
        toast.warning(`${name(info[failed.role])} can't ${failed.cannot}. Choose another model in Advanced.`);
      } else {
        toast.success("Every job works");
      }
    },
    onError: (err: Error) => toast.error(couldnt("test your models", err)),
  });
  const runOnce = useSingleFlight(run.mutate);
  return (
    <Button size="sm" variant="outline" pending={run.isPending} onClick={() => runOnce(undefined)}>
      {tested ? "Test again" : "Test"}
    </Button>
  );
}

/**
 * Moves every job to one provider at once: its recommended set (`PUT .../models/recommended` with the
 * provider), so your own picks stay for when you turn it off. A provider with no key, or with no set
 * (OpenRouter), can't be picked here; its key goes in the keys below.
 */
function ChangeProvider({
  info,
  recommended,
  busy,
  onPick,
}: {
  info: OpenAIInfo;
  recommended: RecommendedModelsInfo;
  busy: boolean;
  onPick: (provider: Provider) => void;
}) {
  const current = recommended.on ? recommended.active_provider : null;
  const choices = PROVIDERS.filter((p) => recommended.sets[p] !== undefined);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button size="sm" variant="outline">
            Change provider
            <ChevronDown aria-hidden="true" />
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="w-auto min-w-56">
        {choices.map((p) => {
          const keyed = info[CONFIGURED[p]];
          return (
            <DropdownMenuItem key={p} disabled={busy || !keyed || p === current} onClick={() => onPick(p)}>
              {p === current ? <Check aria-hidden="true" /> : <span aria-hidden="true" className="size-4" />}
              <span className="flex-1">{providerLabel(p)}</span>
              {keyed ? null : <span className="text-muted-foreground text-body-small">No key yet</span>}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
