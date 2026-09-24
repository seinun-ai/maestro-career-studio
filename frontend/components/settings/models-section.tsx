"use client";

import { useId, useRef, useState, type ReactNode, type Ref } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, X } from "lucide-react";
import { toast } from "sonner";

import { NewTabLink } from "@/components/new-tab-link";
import { SettingCard } from "@/components/settings/setting-card";
import { ACTION_ROW } from "@/components/settings/setting-layout";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useSingleFlight } from "@/hooks/use-single-flight";
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
import { keyFormatProblem, keysSavedText } from "@/lib/api-key-format";
import { apiFetch } from "@/lib/api";
import { couldnt, errorDetail } from "@/lib/error-text";
import { modelName, providerLabel, showsModelId } from "@/lib/model-catalog";
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
export function useSaveModelSettings(
  onSaved?: (info: OpenAIInfo, patch: ModelSettingsPatch) => void,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: ModelSettingsPatch) =>
      apiFetch<OpenAIInfo>("/api/settings/openai", {
        method: "PUT",
        body: JSON.stringify(patch),
      }),
    onSuccess: (result, patch) => {
      qc.setQueryData(["settings", "openai"], result);
      // A saved key completes the "API key" setup step; every setup-status
      // reader (the checklist, the Profile strip, /new's key notice) must see
      // it now, not after the 30-second stale window.
      qc.invalidateQueries({ queryKey: ["setup-status"] });
      onSaved?.(result, patch);
    },
    onError: (err: Error) => toast.error(couldnt("save your model settings", err)),
  });
}

/** The three model roles, each with what it does. */
const ROLES = [
  {
    key: "fast_model",
    label: "Fast model",
    hint: "Reads job descriptions and documents, and picks form answers.",
    patch: (v: string) => ({ fast_model: v }),
  },
  {
    key: "smart_model",
    label: "Smart model",
    hint: "Tailors resumes and writes drafts.",
    patch: (v: string) => ({ smart_model: v }),
  },
  {
    key: "chat_model",
    label: "Assistant model",
    hint: "Runs the Assistant. Use Test to check it works.",
    patch: (v: string) => ({ chat_model: v }),
  },
] as const;

/** What each capability actually gates, so a red mark says what stops working. */
const CAPABILITY_LABELS: { key: "text" | "json" | "tools"; label: string; gates: string }[] = [
  { key: "text", label: "Writing", gates: "cover letters and answers" },
  {
    key: "json",
    label: "Structured answers",
    gates: "reading jobs, tailoring, health checks and career history",
  },
  { key: "tools", label: "Assistant", gates: "the Assistant" },
];

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
      const missing = CAPABILITY_LABELS.filter(({ key }) => !report[key]).map(
        ({ label }) => label,
      );
      // The name the picker shows, not the id the server sent back.
      const name = modelName(info.data?.model_options ?? [], report.model);
      // With no key, or a refused one, every leg fails on the key: the key is the cause, not the
      // model or the connection ("Couldn't reach OpenAI" for a refused key sent people to the network).
      const keyProblem = keyProblemIn(report);
      if (keyProblem) {
        toast.error(`Couldn't test ${name}. ${keyProblem}`);
        return;
      }
      if (report.reachable === false) {
        // The call never reached the model, so this says nothing about it —
        // and nothing was recorded. Blaming the model here is what sent the
        // author hunting a model bug that was a mistyped key.
        // The server's reason goes to the console: it is the provider's own
        // text (a status code, a URL), not words for the screen.
        console.error("model test: unreachable", report.errors);
        toast.error(unreachableText(info.data, report.model, name));
        return;
      }
      if (missing.length === 0) {
        toast.success(`${name} works with every feature`);
      } else {
        toast.warning(
          `${name} can't do ${missing.join(", ")}.` +
            (missing.length < CAPABILITY_LABELS.length ? " Everything else works." : ""),
        );
      }
    },
    onError: (err: Error) => toast.error(couldnt("test the model", err)),
  });

  return (
    <SettingCard
      id="models"
      title="Models"
      description="Which model does each job."
      errorTitle="Couldn't load your model settings."
      skeleton="h-48 w-full"
      query={info}
    >
      {(data) => (
        <div className="grid gap-6">
          <ModelProfileNote />
          <div className="grid gap-4 @2xl/setting:grid-cols-3">
            {ROLES.map((role) => (
              <RoleModel
                key={role.key}
                role={role}
                info={data}
                saving={save.isPending}
                probing={probing}
                onChange={(value) => value && save.mutate(role.patch(value))}
                onProbe={(model) => probe.mutate(model)}
              />
            ))}
          </div>
          <p className="text-muted-foreground text-xs">
            Test a model to see what it can do. A model that fails the Assistant
            test still works everywhere else.
          </p>
        </div>
      )}
    </SettingCard>
  );
}

/** The key problem a test's errors name, in words ("Add an API key in Settings › AI & models."), if any. */
function keyProblemIn(report: CapabilityReport): string | undefined {
  return Object.values(report.errors)
    .map((error) => errorDetail(new Error(error)))
    .find((detail) => detail?.includes("API key"));
}

/** A model test that never reached the model, and what to check: the custom AI server's address
 *  when one is set, else the provider's API key (there is no address to check then). */
function unreachableText(info: OpenAIInfo | undefined, model: string, name: string): string {
  if (!info || info.custom_endpoint) {
    return `Couldn't reach your AI server, so ${name} wasn't tested. Check the server address, then try again.`;
  }
  const option = info.model_options.find((o) => o.id === model);
  if (!option) {
    return `Couldn't reach the AI provider, so ${name} wasn't tested. Check your API key, then try again.`;
  }
  const provider = providerLabel(option.provider);
  return `Couldn't reach ${provider}, so ${name} wasn't tested. Check your ${provider} API key, then try again.`;
}

/** One role: its picker, then the chosen model's measured capabilities. */
function RoleModel({
  role,
  info,
  saving,
  probing,
  onChange,
  onProbe,
}: {
  role: (typeof ROLES)[number];
  info: OpenAIInfo;
  saving: boolean;
  probing: string | null;
  onChange: (value: string | null) => void;
  onProbe: (model: string) => void;
}) {
  const hintId = useId();
  const model = info[role.key];
  return (
    <div className="grid content-start gap-1.5">
      <ModelField
        label={role.label}
        hint={role.hint}
        hintId={hintId}
        value={model}
        options={info.model_options}
        custom={info.custom_endpoint}
        saving={saving}
        onChange={onChange}
      />
      <ModelCapability
        report={info.capabilities[model]}
        name={modelName(info.model_options, model)}
        probing={probing === model}
        busy={probing !== null}
        onProbe={() => onProbe(model)}
      />
    </div>
  );
}

/** The chosen model's measured capabilities, under its picker. A model two
 *  roles share shows in both. */
function ModelCapability({
  report,
  name,
  probing,
  busy,
  onProbe,
}: {
  report: CapabilityReport | undefined;
  name: string;
  probing: boolean;
  busy: boolean;
  onProbe: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      {report ? (
        CAPABILITY_LABELS.map(({ key, label, gates }) => (
          <CapabilityMark
            key={key}
            ok={report[key] === true}
            label={label}
            gates={gates}
            error={report.errors[key]}
          />
        ))
      ) : (
        <span className="text-muted-foreground">Not tested</span>
      )}
      {/* Named for its model, and it keeps its label while it runs: a bare
          spinner left the button with no name. */}
      <Button
        type="button"
        size="xs"
        variant="ghost"
        focusableWhenDisabled
        disabled={busy}
        aria-label={`Test ${name}`}
        className="data-disabled:pointer-events-none data-disabled:opacity-50"
        onClick={onProbe}
      >
        {probing ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}
        Test
      </Button>
    </div>
  );
}

function CapabilityMark({
  ok,
  label,
  gates,
  error,
}: {
  ok: boolean;
  label: string;
  gates: string;
  error: string | undefined;
}) {
  // The provider's own error is not words for the screen: only a plain one (a key problem, named) is added.
  const detail = error ? errorDetail(new Error(error)) : undefined;
  const reason = ok
    ? `${label}: supported. Enables ${gates}`
    : `${label}: not supported. Disables ${gates}.${detail ? ` ${detail}` : ""}`;
  // The reason is read as text, not only from `title`, which a keyboard or a
  // screen reader never reaches. The mark and the chip say it visually.
  return (
    <span className="flex items-center gap-1" title={reason}>
      {ok ? (
        <Check className="size-3 text-emerald-600" aria-hidden="true" />
      ) : (
        <X className="text-destructive size-3" aria-hidden="true" />
      )}
      <span aria-hidden="true">{label}</span>
      <span className="sr-only">{reason}</span>
    </span>
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
    <div className="grid gap-2 text-xs">
      <button
        type="button"
        className="text-muted-foreground hover:text-foreground justify-self-start underline underline-offset-4"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        Which model should I pick?
      </button>
      {open && (
        // Words, not figures: prices move faster than a release, so the
        // providers' own pages carry them. The comparison is README's
        // measured table (Choose your models deliberately).
        <p className="text-muted-foreground max-w-prose">
          GPT-5.6 Luna gives the most thorough results and cost less per
          application in our tests, but it is slower. Gemini 3.7 Flash is the
          fastest. In our tests the Fast model mattered most. Prices change
          often, so check the current ones:{" "}
          <NewTabLink href="https://openai.com/api/pricing/">OpenAI pricing</NewTabLink>{" "}
          and{" "}
          <NewTabLink href="https://ai.google.dev/gemini-api/docs/pricing">Gemini API pricing</NewTabLink>.
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
  // A typed key survives a tab switch, but a navigation dropped it silently.
  useLeaveGuard(openaiKey !== null || geminiKey !== null);

  // A key in the wrong shape, refused at Save before anything is sent (lib/api-key-format.ts).
  const [openaiProblem, setOpenaiProblem] = useState<string | undefined>();
  const [geminiProblem, setGeminiProblem] = useState<string | undefined>();
  const openaiRef = useRef<HTMLInputElement>(null);
  const geminiRef = useRef<HTMLInputElement>(null);

  const saveKeys = useSaveModelSettings((_info, patch) => {
    setOpenaiKey(null);
    setGeminiKey(null);
    // Saving calls no provider: the key is checked the first time it is used.
    toast.success(keysSavedText(patch));
  });
  const saveKeysOnce = useSingleFlight(saveKeys.mutate);

  const onSave = (customServer: boolean) => {
    const openaiWrong = openaiKey !== null ? keyFormatProblem("openai", openaiKey, customServer) : undefined;
    const geminiWrong = geminiKey !== null ? keyFormatProblem("gemini", geminiKey, customServer) : undefined;
    setOpenaiProblem(openaiWrong);
    setGeminiProblem(geminiWrong);
    if (openaiWrong || geminiWrong) {
      (openaiWrong ? openaiRef : geminiRef).current?.focus();
      return;
    }
    // Send only the key the user actually edited. An untouched field stays absent (preserved); a
    // field cleared to empty sends null (removes it). Spaces from a copy are not part of a key.
    saveKeysOnce({
      ...(openaiKey !== null ? { openai_api_key: openaiKey.trim() || null } : {}),
      ...(geminiKey !== null ? { gemini_api_key: geminiKey.trim() || null } : {}),
    });
  };

  return (
    <SettingCard
      id="api-keys"
      title="API keys"
      // A custom AI server on this computer needs no key (llm._get_client).
      description="Lets the app use OpenAI or Gemini. You need one unless you use a custom AI server."
      errorTitle="Couldn't load your API keys."
      skeleton="h-32 w-full"
      query={info}
    >
      {(data) => (
        <div className="grid gap-6">
          {/* items-end: only a configured key has the hint line, so the two
              inputs line up at the bottom rather than the captions at the top.
              Two columns only when the card body has room (32rem): at 768 the
              viewport's `sm:` gave each key 208px, too narrow for its status. */}
          <div className="grid items-end gap-4 @lg/setting:grid-cols-2">
            <KeyField
              label="OpenAI API key"
              hintUnset={
                <>
                  Get one at{" "}
                  <NewTabLink href="https://platform.openai.com/api-keys">platform.openai.com</NewTabLink>. It starts with sk-.
                </>
              }
              configured={data.api_key_configured}
              source={data.openai_key_source}
              value={openaiKey}
              saving={saveKeys.isPending}
              problem={openaiProblem}
              inputRef={openaiRef}
              onChange={(next) => {
                setOpenaiKey(next);
                setOpenaiProblem(undefined);
              }}
            />
            <KeyField
              label="Gemini API key"
              hintUnset={
                <>
                  Get one at{" "}
                  <NewTabLink href="https://aistudio.google.com/apikey">aistudio.google.com</NewTabLink>. It starts with AIza.
                </>
              }
              configured={data.gemini_api_key_configured}
              source={data.gemini_key_source}
              value={geminiKey}
              saving={saveKeys.isPending}
              problem={geminiProblem}
              inputRef={geminiRef}
              onChange={(next) => {
                setGeminiKey(next);
                setGeminiProblem(undefined);
              }}
            />
          </div>
          <div className={ACTION_ROW}>
            <Button
              size="sm"
              focusableWhenDisabled
              disabled={
                saveKeys.isPending || (openaiKey === null && geminiKey === null)
              }
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={() => onSave(data.custom_endpoint)}
            >
              {saveKeys.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      )}
    </SettingCard>
  );
}

function KeyField({
  label,
  hintUnset,
  configured,
  source,
  value,
  saving,
  problem,
  inputRef,
  onChange,
}: {
  label: string;
  /** Where to get a key and what it looks like, while none is saved. */
  hintUnset: ReactNode;
  configured: boolean;
  source: OpenAIInfo["openai_key_source"];
  value: string | null;
  saving: boolean;
  /** Why the typed key was refused at Save, shown under the field until it changes. */
  problem?: string;
  inputRef?: Ref<HTMLInputElement>;
  onChange: (next: string) => void;
}) {
  const labelId = useId();
  const hintId = useId();
  const problemId = useId();
  return (
    <div className="grid gap-1.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5 text-xs">
        <Label id={labelId}>{label}</Label>
        {configured ? (
          // Saying WHERE the key lives matters: one saved here beats .env, so
          // a stale in-app key with a blank .env still reads as set while
          // every call 401s. "Set outside the app" is the .env key.
          <span className="font-medium text-emerald-700 dark:text-emerald-400">
            {source === "env" ? "Set outside the app" : "Saved"}
          </span>
        ) : (
          <span className="text-destructive font-medium">Not added</span>
        )}
      </div>
      {/* The key's format while none is saved, and how to replace one once
          it is: a hint, never an example in the blank field. */}
      <p id={hintId} className="text-muted-foreground text-xs">
        {configured ? "Type a new key to replace the saved one." : hintUnset}
      </p>
      <Input
        type="password"
        // Named by the caption alone. The status beside it is live text that
        // would otherwise be read as part of the field's name.
        ref={inputRef}
        aria-labelledby={labelId}
        aria-describedby={problem ? `${problemId} ${hintId}` : hintId}
        aria-invalid={problem ? true : undefined}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        // readOnly, not disabled, while the keys save: a disabled field drops focus to <body>.
        readOnly={saving}
      />
      {problem ? (
        <p id={problemId} className="text-destructive text-xs">
          {problem}
        </p>
      ) : null}
    </div>
  );
}

/** Dropdown for curated hosted models; free text once a custom endpoint is set.
 *
 *  `model_options` lists models we have verified. It cannot enumerate what an
 *  arbitrary Ollama or vLLM host serves, so forcing a dropdown there would make
 *  every local model unselectable. The hint sits between the label and the
 *  control, wired with `aria-describedby`. */
function ModelField({
  label,
  hint,
  hintId,
  value,
  options,
  custom,
  saving,
  onChange,
}: {
  label: string;
  hint: string;
  hintId: string;
  value: string;
  options: OpenAIInfo["model_options"];
  custom: boolean;
  saving: boolean;
  onChange: (value: string | null) => void;
}) {
  if (custom) {
    return (
      <FreeTextModel
        label={label}
        hint={hint}
        hintId={hintId}
        value={value}
        saving={saving}
        onChange={onChange}
      />
    );
  }
  return (
    <ModelSelect
      label={label}
      hint={hint}
      hintId={hintId}
      value={value}
      options={options}
      saving={saving}
      onChange={onChange}
    />
  );
}

function FreeTextModel({
  label,
  hint,
  hintId,
  value,
  saving,
  onChange,
}: {
  label: string;
  hint: string;
  hintId: string;
  value: string;
  saving: boolean;
  onChange: (value: string | null) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const id = useId();
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <p id={hintId} className="text-muted-foreground text-xs">
        {hint} Type the model name your server uses.
      </p>
      <Input
        id={id}
        aria-describedby={hintId}
        value={draft ?? value}
        readOnly={saving}
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
  hint,
  hintId,
  value,
  options,
  saving,
  onChange,
}: {
  label: string;
  hint: string;
  hintId: string;
  value: string;
  options: OpenAIInfo["model_options"];
  saving: boolean;
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
      <Label htmlFor={id}>{label}</Label>
      <p id={hintId} className="text-muted-foreground text-xs">{hint}</p>
      {/* readOnly, not disabled, while a pick saves: the list closes onto its trigger, and a
          disabled trigger dropped focus to <body> after every pick (RolePicker's rule). */}
      <Select value={value} onValueChange={onChange} readOnly={saving}>
        <SelectTrigger id={id} aria-describedby={hintId} className="w-full">
          <SelectValue>{stale ? value : selected?.label}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {stale ? (
            <SelectItem value={value} disabled>
              {value} (no longer available)
            </SelectItem>
          ) : null}
          {groups.map((group) => (
            <SelectGroup key={group.key}>
              <SelectLabel>{group.title}</SelectLabel>
              {group.options.map((option) => (
                // The id is secondary, under the name, and only when it says
                // something the name does not.
                <SelectItem key={option.id} value={option.id}>
                  <span className="grid">
                    <span>{option.label}</span>
                    {showsModelId(option) ? (
                      <span className="text-muted-foreground font-mono text-xs">
                        {option.id}
                      </span>
                    ) : null}
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
