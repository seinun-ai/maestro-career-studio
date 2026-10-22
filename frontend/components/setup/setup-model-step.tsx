"use client";

import { useId, useRef, useState, type RefObject } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { KEY_FIELDS, KeyField, keyProblemIn, type ModelSettingsPatch } from "@/components/settings/models-section";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Radio, RadioGroup } from "@/components/ui/radio-group";
import { CheckDraw, WorkingDots } from "@/components/visual";
import { keyFormatProblem } from "@/lib/api-key-format";
import { apiFetch } from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt } from "@/lib/error-text";
import {
  CONFIGURED,
  EVERYDAY_JOBS,
  isRemoteEndpoint,
  modelName,
  providerLabel,
  type Provider,
} from "@/lib/model-catalog";
import { modelPlan, planWords, testPassed, type ModelPlan } from "@/lib/setup-flow";
import type { CapabilityReport, OpenAIInfo, RecommendedModelsInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

type Pick = Provider | "server";

/** The five choices, named in words (no logos: Goal Card non-goals). */
const CARDS: { id: Pick; name: string; note: string }[] = [
  { id: "anthropic", name: providerLabel("anthropic"), note: "Anthropic" },
  { id: "openai", name: providerLabel("openai"), note: "GPT models" },
  { id: "gemini", name: providerLabel("gemini"), note: "Google" },
  { id: "openrouter", name: providerLabel("openrouter"), note: "Many models, one key" },
  { id: "server", name: "Your own server", note: "Ollama or LM Studio" },
];

type Outcome =
  | { kind: "report"; report: CapabilityReport; name: string; passed: boolean; problem?: string; words?: string }
  | { kind: "saved"; words: string }
  | { kind: "error"; text: string };

/** Where a new install starts: your own server when one is set, else a provider whose key is saved. */
function startingPick(info: OpenAIInfo): Pick | null {
  if (info.custom_endpoint) return "server";
  return CARDS.find((card) => card.id !== "server" && info[CONFIGURED[card.id]] === true)?.id ?? null;
}

/**
 * Step 1, the AI model. Pick a provider (five cards, named in text), paste its key and press Test: the key
 * is saved (`PUT /api/settings/openai`), the model it will use is tested (`POST /api/settings/openai/probe`,
 * WorkingDots while it runs, a chip per result after), and only once it passes are the provider's
 * recommended models turned on (`PUT /api/settings/models/recommended`), unless your own picks already
 * run on it (lib/setup-flow.ts `modelPlan`). The line under the chips says which it chose.
 */
export function SetupModelStep({ info, headingRef }: { info: OpenAIInfo; headingRef: RefObject<HTMLHeadingElement | null> }) {
  const qc = useQueryClient();
  const [pick, setPick] = useState<Pick | null>(() => startingPick(info));
  // The typed key; null = untouched, so Test checks the saved one.
  const [typed, setTyped] = useState<string | null>(null);
  const [address, setAddress] = useState(info.custom_endpoint ? (info.base_url ?? "") : "");
  const [serverModel, setServerModel] = useState(info.custom_endpoint ? info.fast_model : "");
  const [problem, setProblem] = useState<string | undefined>();
  const [testing, setTesting] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const keyRef = useRef<HTMLInputElement>(null);
  const addressId = useId();
  const addressHintId = useId();
  const modelId = useId();
  const modelHintId = useId();

  const card = CARDS.find((c) => c.id === pick);

  const saveModels = (patch: ModelSettingsPatch) =>
    apiFetch<OpenAIInfo>("/api/settings/openai", {
      method: "PUT",
      body: JSON.stringify(patch),
    }).then((next) => {
      qc.setQueryData(["settings", "openai"], next);
      return next;
    });

  const test = async () => {
    if (!pick || !card || testing) return;
    setOutcome(null);
    const base = address.trim();
    const model = serverModel.trim();
    const key = typed?.trim() ?? "";
    if (pick === "server") {
      if (!base || !model) {
        setProblem("Add the server address and the model name.");
        return;
      }
    } else if (key) {
      const shape = keyFormatProblem(pick, key, info.custom_endpoint);
      if (shape) {
        setProblem(shape);
        keyRef.current?.focus();
        return;
      }
    } else if (info[CONFIGURED[pick]] !== true) {
      setProblem(`Paste your ${card.name} API key first.`);
      keyRef.current?.focus();
      return;
    }
    setProblem(undefined);
    setTesting(true);
    try {
      let current = info;
      if (pick === "server") {
        current = await saveModels({
          base_url: base,
          fast_model: model,
          smart_model: model,
          chat_model: model,
          reasoning_model: model,
        });
      } else if (key) {
        current = await saveModels({ [`${pick}_api_key`]: key });
        setTyped(null);
      }
      const rec = await apiFetch<RecommendedModelsInfo>("/api/settings/models/recommended");
      const plan: ModelPlan =
        pick === "server"
          ? { kind: "server", test: model, change: rec.on ? { on: false } : null }
          : modelPlan(pick, rec, current.model_options);
      const words = planWords(plan, card.name);
      if (!plan.test) {
        setOutcome({ kind: "saved", words });
        return;
      }
      const report = await apiFetch<CapabilityReport>("/api/settings/openai/probe", {
        method: "POST",
        body: JSON.stringify({ model: plan.test }),
      });
      const refused = keyProblemIn(report);
      const passed = testPassed(report, Boolean(refused));
      // A key that has not passed changes no model: the recommended set waits for a working key.
      if (passed && plan.change) {
        await apiFetch<RecommendedModelsInfo>("/api/settings/models/recommended", {
          method: "PUT",
          body: JSON.stringify(plan.change),
        });
      }
      const unreachable =
        report.reachable === false
          ? pick === "server"
            ? "Couldn't reach your server. Check its address, then try again."
            : `Couldn't reach ${card.name}. Check your API key, then try again.`
          : undefined;
      const name = modelName(current.model_options, plan.test);
      setOutcome({
        kind: "report",
        report,
        name,
        passed,
        problem: refused ?? unreachable ?? (passed ? undefined : `${name} didn't answer. Try another model in Settings.`),
        words: passed ? words : undefined,
      });
    } catch (err) {
      setOutcome({ kind: "error", text: couldnt(pick === "server" ? "test your server" : "test your key", err) });
    } finally {
      setTesting(false);
      // The key, the roles and the step's Done all changed: every reader sees it now.
      for (const key of [["settings", "openai"], ["settings", "models", "recommended"], ["setup-status"]]) {
        void qc.invalidateQueries({ queryKey: key });
      }
    }
  };

  return (
    <section aria-labelledby="setup-model-title" className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h2 id="setup-model-title" ref={headingRef} tabIndex={-1} className="text-headline-small outline-none">
          Pick the AI that does the writing
        </h2>
        <p className="max-w-[65ch] text-body-medium text-muted-foreground">
          Your key is saved on this computer and sent only to that provider. You can change it any time in
          Settings.
        </p>
      </div>

      <RadioGroup<Pick>
        aria-label="AI provider"
        value={pick ?? undefined}
        onValueChange={(next) => {
          setPick(next);
          setTyped(null);
          setProblem(undefined);
          setOutcome(null);
        }}
        className="grid grid-cols-2 gap-3 lg:grid-cols-3"
      >
        {CARDS.map((c) => (
          <label
            key={c.id}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-corner-md border bg-card p-4 transition-colors duration-(--duration-short3) ease-standard",
              pick === c.id ? "border-primary" : "border-border hover:bg-surface-container-low",
            )}
          >
            <Radio value={c.id} />
            <span className="flex min-w-0 flex-col">
              <span className="text-title-small">{c.name}</span>
              <span className="text-body-small text-muted-foreground">{c.note}</span>
            </span>
          </label>
        ))}
      </RadioGroup>

      {card ? (
        <div className="flex max-w-xl flex-col gap-4">
          {pick === "server" ? (
            <>
              <div className="grid gap-1.5">
                <Label htmlFor={addressId}>Server address</Label>
                <p id={addressHintId} className="text-body-small text-muted-foreground">
                  The address of a model server on your computer. It usually ends in /v1.
                </p>
                <Input
                  id={addressId}
                  aria-describedby={addressHintId}
                  value={address}
                  readOnly={testing}
                  onChange={(e) => setAddress(e.target.value)}
                />
                {isRemoteEndpoint(address) ? (
                  <p className="text-body-small text-warning">
                    This address isn&apos;t on your computer, and your resume will be sent to it. Use a server
                    you trust.
                  </p>
                ) : null}
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={modelId}>Model name</Label>
                <p id={modelHintId} className="text-body-small text-muted-foreground">
                  The model as your server names it. Every job uses it.
                </p>
                <Input
                  id={modelId}
                  aria-describedby={modelHintId}
                  value={serverModel}
                  readOnly={testing}
                  onChange={(e) => setServerModel(e.target.value)}
                />
              </div>
              {problem ? <p className="text-body-small text-destructive">{problem}</p> : null}
            </>
          ) : (
            <KeyField
              label={`${card.name} API key`}
              hintUnset={
                <>
                  {KEY_FIELDS[card.id as Provider].hint} It&apos;s saved on this computer and sent only to {card.name}.
                </>
              }
              configured={info[CONFIGURED[card.id as Provider]] === true}
              source={info[KEY_FIELDS[card.id as Provider].source]}
              value={typed}
              saving={testing}
              problem={problem}
              inputRef={keyRef}
              onChange={(next) => {
                setTyped(next);
                setProblem(undefined);
              }}
            />
          )}
          <div className="flex flex-wrap items-center gap-4">
            <Button type="button" variant="tonal" size="lg" pending={testing} onClick={() => void test()}>
              Test
            </Button>
            <div aria-live="polite" className="min-w-0">
              {testing ? (
                <WorkingDots label={pick === "server" ? "Checking your server" : "Checking your key"} />
              ) : outcome ? (
                <TestOutcome outcome={outcome} />
              ) : null}
            </div>
          </div>
        </div>
      ) : (
        <p className="text-body-medium text-muted-foreground">Pick one to add its key.</p>
      )}
    </section>
  );
}

/** After Test: Works and a chip per result, or what to fix. */
function TestOutcome({ outcome }: { outcome: Outcome }) {
  if (outcome.kind === "error") return <p className="text-body-medium text-destructive">{outcome.text}</p>;
  if (outcome.kind === "saved") {
    return (
      <p className="flex flex-col gap-1 text-body-medium">
        <span className="flex items-center gap-2">
          <CheckDraw />
          Key saved. It&apos;s checked the first time it&apos;s used.
        </span>
        <span className="text-body-small text-muted-foreground">{outcome.words}</span>
      </p>
    );
  }
  const { report, passed } = outcome;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {passed ? (
          <span className="flex items-center gap-1.5 text-title-small">
            <CheckDraw />
            Works
          </span>
        ) : null}
        {report.reachable === false
          ? null
          : EVERYDAY_JOBS.map((job) => {
              // Settings › Basics' words for the three everyday jobs, each passed when every result it needs did.
              const ok = job.needs.every((need) => report[need] === true);
              const key = job.role;
              const label = job.can[0].toUpperCase() + job.can.slice(1);
              const Icon = ok ? CONCEPT_ICONS.done : CONCEPT_ICONS.fails;
              return (
                <span
                  key={key}
                  className={cn(
                    "inline-flex h-6 items-center gap-1 rounded-full px-2 text-label-medium",
                    ok ? "bg-success-container text-on-success-container" : "bg-error-container text-on-error-container",
                  )}
                >
                  <Icon aria-hidden="true" className="size-3" />
                  {label}
                  <span className="sr-only">{ok ? ": yes" : ": no"}</span>
                </span>
              );
            })}
      </div>
      {outcome.problem ? <p className="text-body-small text-destructive">{outcome.problem}</p> : null}
      {outcome.words ? (
        <p className="text-body-small text-muted-foreground">
          Tested {outcome.name}. {outcome.words}
        </p>
      ) : null}
    </div>
  );
}
