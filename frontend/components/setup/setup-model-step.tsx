"use client";

import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { GuardedLink as Link } from "@/components/guarded-link";
import { KEY_FIELDS, KeyField, type ModelSettingsPatch } from "@/components/settings/models-section";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Radio, RadioGroup } from "@/components/ui/radio-group";
import { CheckDraw, WorkingDots } from "@/components/visual";
import { CONNECTED_AGENTS_SETTINGS } from "@/lib/agent-links";
import { keyFormatProblem } from "@/lib/api-key-format";
import { apiFetch } from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt, REFUSED_KEY } from "@/lib/error-text";
import {
  CONFIGURED,
  EVERYDAY_JOBS,
  isRemoteEndpoint,
  modelName,
  providerLabel,
  type Provider,
} from "@/lib/model-catalog";
import {
  checkVerdict,
  modelPlan,
  movesOnUnchecked,
  planWords,
  refusedWords,
  type CheckVerdict,
  type ModelPlan,
} from "@/lib/setup-flow";
import type { CapabilityReport, OpenAIInfo, RecommendedModelsInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

type Pick = Provider | "server";

/** The one a new install starts on, so a beginner has a key to paste and nothing to choose. */
const SUGGESTED: Pick = "openai";

/** The five choices, named in words (no logos: Goal Card non-goals). */
const CARDS: { id: Pick; name: string; note: string }[] = [
  { id: "openai", name: providerLabel("openai"), note: "Suggested. GPT models" },
  { id: "anthropic", name: providerLabel("anthropic"), note: "Anthropic" },
  { id: "gemini", name: providerLabel("gemini"), note: "Google" },
  { id: "openrouter", name: providerLabel("openrouter"), note: "Many models, one key" },
  { id: "server", name: "Your own server", note: "Ollama or LM Studio" },
];

type Outcome =
  | { kind: "report"; report: CapabilityReport; name: string; passed: boolean; problem?: string; words?: string }
  | { kind: "saved"; words: string }
  | { kind: "error"; text: string };

/** Where the step starts: your own server when one is set, else a provider whose key is saved, else the suggested one. */
function startingPick(info: OpenAIInfo): Pick {
  if (info.custom_endpoint) return "server";
  return CARDS.find((card) => card.id !== "server" && info[CONFIGURED[card.id]] === true)?.id ?? SUGGESTED;
}

/**
 * Step 1, the AI model. It starts on the suggested provider, so a beginner only pastes a key; the five cards,
 * named in text, wait behind "Use a different AI", open when you already use another. Paste the key and press the nav's
 * Save and continue (it calls `saveRef`): the key is saved (`PUT /api/settings/openai`), the model it will use is
 * tested (`POST /api/settings/openai/probe`,
 * WorkingDots while it runs, a chip per result after), and only once it passes are the provider's
 * recommended models turned on (`PUT /api/settings/models/recommended`), unless your own picks already
 * run on it (lib/setup-flow.ts `modelPlan`). The line under the chips says which it chose. The flow moves on only
 * once the check passes; with nothing typed and a key or server already set, it moves on without one, unless
 * the last check failed (`movesOnUnchecked`). The probe checks only the saved key, so a pasted key the provider
 * refuses is removed again (`refusedWords` says what that left); a check that could not run keeps the key and
 * says so, and the next press moves on.
 */
export function SetupModelStep({
  info,
  headingRef,
  saveRef,
}: {
  info: OpenAIInfo;
  headingRef: RefObject<HTMLHeadingElement | null>;
  /** Set by this step: saves what was typed and checks it, true when the flow may move on. */
  saveRef: RefObject<(() => Promise<boolean>) | null>;
}) {
  const qc = useQueryClient();
  const [pick, setPick] = useState<Pick>(() => startingPick(info));
  // Fixed when the step opens: after that the disclosure is yours, and choosing a card never closes it.
  const [openOnArrival] = useState(() => startingPick(info) !== SUGGESTED);
  // The typed key; null = untouched, so Test checks the saved one.
  const [typed, setTyped] = useState<string | null>(null);
  const [address, setAddress] = useState(info.custom_endpoint ? (info.base_url ?? "") : "");
  const [serverModel, setServerModel] = useState(info.custom_endpoint ? info.fast_model : "");
  const [problem, setProblem] = useState<string | undefined>();
  const [testing, setTesting] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  // The last check's verdict: after a failed or refused one, the next press checks again.
  const [last, setLast] = useState<CheckVerdict | null>(null);
  const keyRef = useRef<HTMLInputElement>(null);
  const addressId = useId();
  const addressHintId = useId();
  const modelId = useId();
  const modelHintId = useId();

  const card = CARDS.find((c) => c.id === pick) ?? CARDS[0];

  const saveModels = (patch: ModelSettingsPatch) =>
    apiFetch<OpenAIInfo>("/api/settings/openai", {
      method: "PUT",
      body: JSON.stringify(patch),
    }).then((next) => {
      qc.setQueryData(["settings", "openai"], next);
      return next;
    });

  const test = async (): Promise<boolean> => {
    if (testing) return false;
    setOutcome(null);
    const base = address.trim();
    const model = serverModel.trim();
    const key = typed?.trim() ?? "";
    if (pick === "server") {
      if (!base || !model) {
        setProblem("Add the server address and the model name.");
        return false;
      }
    } else if (key) {
      const shape = keyFormatProblem(pick, key, info.custom_endpoint);
      if (shape) {
        setProblem(shape);
        keyRef.current?.focus();
        return false;
      }
    } else if (info[CONFIGURED[pick]] !== true) {
      setProblem(`Paste your ${card.name} API key first.`);
      keyRef.current?.focus();
      return false;
    }
    setProblem(undefined);
    setTesting(true);
    // Set once the pasted key is saved: a check that then cannot run leaves it saved, and says so.
    let saved = false;
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
        saved = true;
      }
      const rec = await apiFetch<RecommendedModelsInfo>("/api/settings/models/recommended");
      const plan: ModelPlan =
        pick === "server"
          ? { kind: "server", test: model, change: rec.on ? { on: false } : null }
          : modelPlan(pick, rec, current.model_options);
      const words = planWords(plan, card.name);
      if (!plan.test) {
        setTyped(null);
        setOutcome({ kind: "saved", words });
        setLast("passed");
        return true;
      }
      const report = await apiFetch<CapabilityReport>("/api/settings/openai/probe", {
        method: "POST",
        body: JSON.stringify({ model: plan.test }),
      });
      const provider = pick === "server" ? null : pick;
      const refused = provider !== null && Object.values(report.errors).some((e) => REFUSED_KEY.test(e));
      const verdict = checkVerdict(report, refused, provider === null);
      setLast(verdict);
      if (verdict === "refused" && provider) {
        // The probe can only check the saved key: a pasted key it refused is taken out again.
        saved = false;
        const after = key ? await saveModels({ [`${provider}_api_key`]: "" }) : current;
        const flag = CONFIGURED[provider];
        setOutcome({ kind: "error", text: refusedWords(card.name, Boolean(key), info[flag] === true, after[flag] === true) });
        keyRef.current?.focus();
        return false;
      }
      setTyped(null);
      const passed = verdict === "passed";
      // A key that has not passed changes no model: the recommended set waits for a working key.
      if (passed && plan.change) {
        await apiFetch<RecommendedModelsInfo>("/api/settings/models/recommended", {
          method: "PUT",
          body: JSON.stringify(plan.change),
        });
      }
      const name = modelName(current.model_options, plan.test);
      const problem =
        verdict === "unchecked"
          ? `Key saved, but ${card.name} couldn't be reached to check it. Press Save and continue to go on without the check.`
          : report.reachable === false
            ? "Couldn't reach your server. Check its address, then try again."
            : `${name} didn't answer. Try another model in Settings.`;
      setOutcome({ kind: "report", report, name, passed, problem: passed ? undefined : problem, words: passed ? words : undefined });
      return passed;
    } catch (err) {
      // A key saved before the failure stays saved: the check could not run, and the next press moves on.
      // A refused key whose removal failed keeps its refused verdict, so the next press checks again.
      if (saved) setLast("unchecked");
      else setLast((was) => (was === "refused" ? was : "failed"));
      setOutcome({
        kind: "error",
        text: saved
          ? "Key saved, but it couldn't be checked. Press Save and continue to go on without the check."
          : couldnt(pick === "server" ? "test your server" : "test your key", err),
      });
      return false;
    } finally {
      setTesting(false);
      // The key, the roles and the step's Done all changed: every reader sees it now.
      for (const key of [["settings", "openai"], ["settings", "models", "recommended"], ["setup-status"]]) {
        void qc.invalidateQueries({ queryKey: key });
      }
    }
  };

  // Save and continue: nothing typed with a key or server already set moves on, unless the last check failed;
  // anything typed is saved and checked.
  const saveAndCheck = (): Promise<boolean> => {
    const anySet =
      info.custom_endpoint || CARDS.some((c) => c.id !== "server" && info[CONFIGURED[c.id as Provider]] === true);
    const untouched =
      pick === "server"
        ? address.trim() === (info.custom_endpoint ? (info.base_url ?? "") : "") &&
          serverModel.trim() === (info.custom_endpoint ? info.fast_model : "")
        : !typed?.trim();
    if (movesOnUnchecked(untouched, anySet, last)) return Promise.resolve(true);
    return test();
  };
  useEffect(() => {
    saveRef.current = saveAndCheck;
  });

  return (
    <section aria-labelledby="setup-model-title" className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h2 id="setup-model-title" ref={headingRef} tabIndex={-1} className="text-headline-small outline-none">
          Add the AI that does the writing
        </h2>
        <p className="max-w-[65ch] text-body-medium text-muted-foreground">
          {pick === SUGGESTED ? `We suggest ${card.name}, at about $0.01 per application. ` : null}
          One key is enough, and you can change it any time in Settings.
        </p>
      </div>

      <details open={openOnArrival}>
        <summary className="w-fit cursor-pointer rounded-corner-sm text-body-medium text-primary outline-none focus-visible:ring-3 focus-visible:ring-ring">
          Use a different AI
        </summary>
        <RadioGroup<Pick>
          aria-label="AI provider"
          value={pick}
          onValueChange={(next) => {
            setPick(next);
            setTyped(null);
            setProblem(undefined);
            setOutcome(null);
          }}
          className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-3"
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
      </details>

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
        <div aria-live="polite" className="min-w-0">
          {testing ? (
            <WorkingDots label={pick === "server" ? "Checking your server" : "Checking your key"} />
          ) : outcome ? (
            <TestOutcome outcome={outcome} />
          ) : null}
        </div>
      </div>

      <p className="max-w-[65ch] text-body-medium">
        Already pay for Claude or ChatGPT? You can skip the key and connect that app in{" "}
        <Link className="underline" href={CONNECTED_AGENTS_SETTINGS}>
          Settings › Agent apps
        </Link>
        .
      </p>
    </section>
  );
}

/** After the check: Works and a chip per result, or what to fix. */
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
