"use client";

import { useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, ChevronDownIcon, ChevronRightIcon } from "lucide-react";
import { toast } from "sonner";

import {
  CapabilityMatrix,
  EndpointControls,
} from "@/components/settings/llm-endpoint";
import { ModelCatalogPanel } from "@/components/settings/model-catalog-panel";
import { AboutSection } from "@/components/settings/about-section";
import { AppearanceSection } from "@/components/settings/appearance-section";
import { McpWorkflowSection } from "@/components/settings/mcp-workflow-section";
import { QuickTailorSection } from "@/components/settings/quick-tailor-section";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardSection } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import type {
  AutoApplySettings,
  CapabilityReport,
  OpenAIInfo,
  SettingValue,
} from "@/lib/types";
import { PageHeader, PageShell } from "@/components/page-shell";

// Only these are user-voice prompts worth surfacing by default; every other
// key is internal plumbing (extraction, KB pipeline, verification) and lives
// behind the "Advanced" disclosure below, keyed by its raw prompt name.
const ESSENTIAL_PROMPTS: { key: string; title: string; description: string }[] = [
  {
    key: "cover_letter",
    title: "Cover letter",
    description: "Voice and structure of generated cover letters.",
  },
  {
    key: "qa",
    title: "Application Q&A",
    description: "How free-response application questions are answered in your voice.",
  },
  {
    key: "gap_tailor",
    title: "Gap tailoring",
    description: "How resolved gap answers get folded into a tailored resume.",
  },
  {
    key: "chat_system",
    title: "Chat assistant",
    description: "System behavior for the main chat assistant.",
  },
];
const ESSENTIAL_KEYS = new Set(ESSENTIAL_PROMPTS.map((p) => p.key));

export default function SettingsPage() {
  return (
    <PageShell>
      <PageHeader
        title="Settings"
        subtitle="Models, API keys, prompts, and appearance."
        actions={
          <Button
            variant="outline"
            size="sm"
            nativeButton={false}
            render={
              <a
                href="https://github.com/seinun-ai/maestro-career-studio/blob/main/docs/GETTING_STARTED.md"
                target="_blank"
                rel="noopener noreferrer"
              >
                <BookOpen className="size-4" />
                Getting started guide
              </a>
            }
          />
        }
      />
      <PromptsSection />
      <QuickTailorSection />
      <McpWorkflowSection />
      <AutoApplySection />
      <OpenAISection />
      <AppearanceSection />
      <AboutSection />
    </PageShell>
  );
}

// Numeric knobs surfaced in the card; deprecated cooldown_days stays hidden
// but is preserved on save (the backend model is extra="forbid" and declines
// are posting-scoped now — the field is dormant, not meaningful).
const AUTO_APPLY_FIELDS: {
  key: "max_submissions_per_day" | "max_proposals_per_run" | "proposal_expiry_days" | "auto_pick_floor" | "auto_pick_margin";
  label: string;
  hint: string;
  min: number;
  max?: number;
}[] = [
  {
    key: "max_submissions_per_day",
    label: "Daily submission cap",
    hint: "Approving a proposal reserves a slot for 24 hours.",
    min: 1,
    max: 100,
  },
  {
    key: "max_proposals_per_run",
    label: "Proposals per hunt run",
    // No hint: the label already says it.
    hint: "",
    min: 1,
    max: 100,
  },
  {
    key: "proposal_expiry_days",
    label: "Unreviewed proposal expiry (days)",
    hint: "Accepted proposals never expire.",
    min: 1,
    max: 90,
  },
  {
    key: "auto_pick_floor",
    label: "Auto-pick score floor",
    hint: "Minimum ATS score to auto-pick a base resume.",
    min: 0,
    max: 100,
  },
  {
    key: "auto_pick_margin",
    label: "Auto-pick margin",
    hint: "Points the top base must beat the runner-up by.",
    min: 0,
    max: 100,
  },
];

function AutoApplySection() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["settings", "auto-apply"],
    queryFn: () =>
      apiFetch<{ key: string; value: AutoApplySettings }>(
        "/api/settings/auto-apply",
      ),
  });
  const [draft, setDraft] = useState<AutoApplySettings | null>(null);
  const [blockInput, setBlockInput] = useState("");
  const value = draft ?? query.data?.value ?? null;

  const save = useMutation({
    mutationFn: (next: AutoApplySettings) =>
      apiFetch<{ key: string; value: AutoApplySettings }>(
        "/api/settings/auto-apply",
        { method: "PUT", body: JSON.stringify({ value: next }) },
      ),
    onSuccess: () => {
      toast.success("Auto-apply settings saved");
      setDraft(null);
      qc.invalidateQueries({ queryKey: ["settings", "auto-apply"] });
      // The proposals funnel strip renders the cap readout — refresh it.
      qc.invalidateQueries({ queryKey: ["proposals", "funnel"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const patch = (partial: Partial<AutoApplySettings>) => {
    if (!value) return;
    setDraft({ ...value, ...partial });
  };

  const addBlocked = () => {
    const name = blockInput.trim();
    if (!name || !value) return;
    if (value.company_blocklist.some((c) => c.toLowerCase() === name.toLowerCase())) {
      setBlockInput("");
      return;
    }
    patch({ company_blocklist: [...value.company_blocklist, name] });
    setBlockInput("");
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Auto-apply</CardTitle>
        <p className="text-muted-foreground text-sm">
          Guardrails for the agent hunt-and-apply lane.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {!value ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              {AUTO_APPLY_FIELDS.map((f) => (
                // `grid`, not `space-y`: a bare <label> is display:inline, so
                // on a block stack it shared a line with the input and the two
                // visibly overlapped. Grid puts every child on its own row, and
                // the shared <Label> is a flex container rather than inline.
                <div key={f.key} className="grid gap-1.5">
                  <Label htmlFor={`aa-${f.key}`}>{f.label}</Label>
                  {/* Hint above the control and wired with aria-describedby:
                      read it before you type, not after. A field whose label
                      already says it carries no hint at all. */}
                  {f.hint && (
                    <p
                      id={`aa-${f.key}-hint`}
                      className="text-muted-foreground text-xs"
                    >
                      {f.hint}
                    </p>
                  )}
                  <Input
                    id={`aa-${f.key}`}
                    aria-describedby={f.hint ? `aa-${f.key}-hint` : undefined}
                    type="number"
                    min={f.min}
                    max={f.max}
                    value={value[f.key]}
                    onChange={(e) => {
                      const n = Number(e.target.value);
                      if (Number.isFinite(n)) patch({ [f.key]: n });
                    }}
                    className="max-w-[10rem]"
                  />
                </div>
              ))}
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="aa-blocklist">Company blocklist</Label>
              <p id="aa-blocklist-hint" className="text-muted-foreground text-xs">
                The hunt never captures or proposes these companies. Skipping a
                single posting does not block its company.
              </p>
              {value.company_blocklist.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {value.company_blocklist.map((name) => (
                    <span
                      key={name}
                      className="bg-muted inline-flex h-7 items-center gap-1 rounded-full pl-3 pr-1.5 text-xs"
                    >
                      {name}
                      <button
                        type="button"
                        aria-label={`Remove ${name} from blocklist`}
                        className="hover:bg-background rounded-full px-1 text-muted-foreground"
                        onClick={() =>
                          patch({
                            company_blocklist: value.company_blocklist.filter(
                              (c) => c !== name,
                            ),
                          })
                        }
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              ) : null}
              <div className="flex max-w-sm gap-2">
                <Input
                  id="aa-blocklist"
                  aria-describedby="aa-blocklist-hint"
                  placeholder="e.g. Acme Corp"
                  value={blockInput}
                  onChange={(e) => setBlockInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addBlocked();
                    }
                  }}
                />
                <Button type="button" variant="outline" onClick={addBlocked}>
                  Add
                </Button>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Button
                type="button"
                disabled={!draft || save.isPending}
                onClick={() => draft && save.mutate(draft)}
              >
                {save.isPending ? "Saving…" : "Save"}
              </Button>
              {draft ? (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setDraft(null)}
                >
                  Cancel
                </Button>
              ) : null}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function PromptsSection() {
  const prompts = useQuery({
    queryKey: ["settings", "prompts"],
    queryFn: () => apiFetch<SettingValue[]>("/api/settings/prompts"),
  });
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const byKey = new Map(prompts.data?.map((p) => [p.key, p]));
  const essential = ESSENTIAL_PROMPTS.map((meta) => ({
    meta,
    prompt: byKey.get(meta.key),
  })).filter((e) => e.prompt);
  const advanced = prompts.data?.filter((p) => !ESSENTIAL_KEYS.has(p.key)) ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Prompts</CardTitle>
        <p className="text-muted-foreground text-xs">
          Override the voice used for cover letters, outreach, Q&amp;A, and chat.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {prompts.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <>
            {essential.map(({ meta, prompt }) => (
              <PromptCard
                key={meta.key}
                prompt={prompt!}
                title={meta.title}
                description={meta.description}
              />
            ))}
            <div className="pt-1">
              <button
                type="button"
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                onClick={() => setAdvancedOpen((o) => !o)}
              >
                {advancedOpen ? (
                  <ChevronDownIcon className="size-3.5" />
                ) : (
                  <ChevronRightIcon className="size-3.5" />
                )}
                Advanced prompts ({advanced.length})
              </button>
              {advancedOpen && (
                <div className="mt-3 space-y-3">
                  {advanced.map((p) => (
                    <PromptCard key={p.key} prompt={p} />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function PromptCard({
  prompt,
  title,
  description,
}: {
  prompt: SettingValue;
  title?: string;
  description?: string;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(prompt.value);

  const save = useMutation({
    mutationFn: () =>
      apiFetch<SettingValue>(`/api/settings/prompts/${prompt.key}`, {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    onSuccess: (result) => {
      qc.setQueryData<SettingValue[]>(["settings", "prompts"], (prev) =>
        prev?.map((p) => (p.key === result.key ? result : p)),
      );
      toast.success(`${prompt.key} saved`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const reset = useMutation({
    mutationFn: () =>
      apiFetch<SettingValue>(`/api/settings/prompts/${prompt.key}/reset`, {
        method: "POST",
      }),
    onSuccess: (result) => {
      qc.setQueryData<SettingValue[]>(["settings", "prompts"], (prev) =>
        prev?.map((p) => (p.key === result.key ? result : p)),
      );
      setValue(result.value);
      toast.success(`${prompt.key} reset`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  return (
    <CardSection className="p-0">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 p-3 text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <div className="min-w-0">
          {title ? (
            <>
              <p className="text-sm font-medium">{title}</p>
              <p className="text-muted-foreground text-xs">{description}</p>
            </>
          ) : (
            <p className="font-mono text-sm">{prompt.key}</p>
          )}
        </div>
        <span className="text-muted-foreground shrink-0 text-xs">
          {open ? "Collapse" : "Expand"}
        </span>
      </button>
      {open && (
        <div className="space-y-2 border-t p-3">
          {title && (
            <p className="text-muted-foreground font-mono text-xs">{prompt.key}</p>
          )}
          <Textarea
            rows={10}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="font-mono text-xs"
            aria-label={`${title || prompt.key} prompt text`}
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => save.mutate()}
              disabled={save.isPending || value === prompt.value}
            >
              {save.isPending ? "Saving…" : "Save"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => reset.mutate()}
              disabled={reset.isPending}
            >
              {reset.isPending ? "Resetting…" : "Reset to default"}
            </Button>
          </div>
        </div>
      )}
    </CardSection>
  );
}

function OpenAISection() {
  const qc = useQueryClient();
  const info = useQuery({
    queryKey: ["settings", "openai"],
    queryFn: () => apiFetch<OpenAIInfo>("/api/settings/openai"),
  });
  const [openaiKey, setOpenaiKey] = useState<string | null>(null);
  const [geminiKey, setGeminiKey] = useState<string | null>(null);

  // The API never returns key material, so these inputs hold only what the
  // user types this session. null = untouched, which means the PUT omits the
  // field entirely and the stored key survives.
  const currentOpenaiKey = openaiKey ?? "";
  const currentGeminiKey = geminiKey ?? "";

  const [probing, setProbing] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (payload: {
      fast_model: string;
      smart_model: string;
      chat_model: string;
      openai_api_key?: string | null;
      gemini_api_key?: string | null;
      base_url?: string | null;
      json_mode?: string;
    }) =>
      apiFetch<OpenAIInfo>("/api/settings/openai", {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "openai"], result);
      setOpenaiKey(null);
      setGeminiKey(null);
      toast.success("Model settings saved");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const probe = useMutation({
    mutationFn: (model: string) =>
      apiFetch<CapabilityReport>("/api/settings/openai/probe", {
        method: "POST",
        body: JSON.stringify({ model }),
      }),
    onMutate: (model: string) => setProbing(model),
    onSettled: () => setProbing(null),
    onSuccess: (report) => {
      qc.invalidateQueries({ queryKey: ["settings", "openai"] });
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

  const updateModel = (
    field: "fast_model" | "smart_model" | "chat_model",
    value: string | null,
  ) => {
    if (!info.data || !value) return;
    // Key fields are omitted on purpose: the backend leaves an absent key
    // untouched, so changing a model can never clear a stored key.
    save.mutate({
      fast_model: field === "fast_model" ? value : info.data.fast_model,
      smart_model: field === "smart_model" ? value : info.data.smart_model,
      chat_model: field === "chat_model" ? value : info.data.chat_model,
    });
  };

  const saveKeys = () => {
    if (!info.data) return;
    // Send only the key the user actually edited. An untouched field stays
    // absent (preserved); a field cleared to empty sends null (removes it).
    save.mutate({
      fast_model: info.data.fast_model,
      smart_model: info.data.smart_model,
      chat_model: info.data.chat_model,
      ...(openaiKey !== null ? { openai_api_key: openaiKey || null } : {}),
      ...(geminiKey !== null ? { gemini_api_key: geminiKey || null } : {}),
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Models &amp; API keys</CardTitle>
        <p className="text-muted-foreground text-xs">
          Fast / Smart / Chat roles, provider keys, and a catalog you can grow
          with Sync.
        </p>
        <p className="text-muted-foreground text-xs">
          Two measured profiles, one per key: GPT-5.6 Luna on every tier (the
          default — most thorough JD extraction we tested, about a penny per
          application, slower) or Gemini 3.7 Flash on every tier (fastest,
          under 3¢ per application, promo pricing doubles Jan 2027). In our
          tests the Fast model decided extraction coverage and score honesty;
          the Smart choice barely moved the result. Prices and tiers move
          constantly — treat this as a starting point, not a recommendation
          with a shelf life.
        </p>
      </CardHeader>
      <CardContent>
        {info.isLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : info.data ? (
          <div className="space-y-4 text-sm">
            <div className="grid gap-3 sm:grid-cols-3">
              <ModelField
                label="Fast model"
                value={info.data.fast_model}
                options={info.data.model_options}
                custom={info.data.custom_endpoint}
                disabled={save.isPending}
                onChange={(value) => updateModel("fast_model", value)}
              />
              <ModelField
                label="Smart model"
                value={info.data.smart_model}
                options={info.data.model_options}
                custom={info.data.custom_endpoint}
                disabled={save.isPending}
                onChange={(value) => updateModel("smart_model", value)}
              />
              <ModelField
                label="Chat model · needs streaming tool calls, so test it"
                value={info.data.chat_model}
                options={info.data.model_options}
                custom={info.data.custom_endpoint}
                disabled={save.isPending}
                onChange={(value) => updateModel("chat_model", value)}
              />
            </div>
            <EndpointControls
              info={info.data}
              disabled={save.isPending}
              onSave={(patch) =>
                save.mutate({
                  fast_model: info.data.fast_model,
                  smart_model: info.data.smart_model,
                  chat_model: info.data.chat_model,
                  ...patch,
                })
              }
            />
            <CapabilityMatrix
              info={info.data}
              probing={probing}
              onProbe={(model) => probe.mutate(model)}
            />
            <ModelCatalogPanel info={info.data} />
            <div className="space-y-3 border-t pt-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span id="openai-api-key-label" className="text-muted-foreground">
                      OpenAI API key
                    </span>
                    {info.data.api_key_configured ? (
                      <span className="text-emerald-600 font-medium">Configured</span>
                    ) : (
                      <span className="text-destructive font-medium">Not configured</span>
                    )}
                  </div>
                  <Input
                    type="password"
                    // Named by the caption alone. The wrapping <label> also
                    // contains the live "Configured / Not configured" status,
                    // which would otherwise be read as part of the field's
                    // name and change as you type.
                    aria-labelledby="openai-api-key-label"
                    placeholder={
                      info.data.api_key_configured ? "Saved · type to replace" : "sk-..."
                    }
                    value={currentOpenaiKey}
                    onChange={(e) => setOpenaiKey(e.target.value)}
                    disabled={save.isPending}
                  />
                </label>
                <label className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span id="gemini-api-key-label" className="text-muted-foreground">
                      Gemini API key
                    </span>
                    {info.data.gemini_api_key_configured ? (
                      <span className="text-emerald-600 font-medium">Configured</span>
                    ) : (
                      <span className="text-destructive font-medium">Not configured</span>
                    )}
                  </div>
                  <Input
                    type="password"
                    aria-labelledby="gemini-api-key-label"
                    placeholder={
                      info.data.gemini_api_key_configured
                        ? "Saved · type to replace"
                        : "AIza..."
                    }
                    value={currentGeminiKey}
                    onChange={(e) => setGeminiKey(e.target.value)}
                    disabled={save.isPending}
                  />
                </label>
              </div>
              <div className="flex items-center justify-between">
                <p className="text-muted-foreground text-xs">
                  Leave blank to use defaults from <code>.env</code>.
                </p>
                <Button
                  size="sm"
                  onClick={saveKeys}
                  disabled={save.isPending || (openaiKey === null && geminiKey === null)}
                >
                  {save.isPending ? "Saving..." : "Save API keys"}
                </Button>
              </div>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
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
  const labelId = useId();
  return (
    <label className="space-y-1.5">
      <span id={labelId} className="text-muted-foreground text-xs">
        {label}
      </span>
      <Input
        aria-labelledby={labelId}
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
    </label>
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
  const labelId = useId();
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
    <label className="space-y-1.5">
      <span id={labelId} className="text-muted-foreground text-xs">
        {label}
      </span>
      <Select value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger className="w-full" aria-labelledby={labelId}>
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
    </label>
  );
}
