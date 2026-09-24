"use client";

import { useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDownIcon, ChevronRightIcon } from "lucide-react";
import { toast } from "sonner";

import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { SettingCard } from "@/components/settings/setting-card";
import { ACTION_ROW } from "@/components/settings/setting-layout";
import { Button } from "@/components/ui/button";
import { CardSection } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import type { SettingValue } from "@/lib/types";

type PromptMeta = { key: string; title: string; description: string };

// Only these are user-voice prompts worth surfacing by default; every other
// key is internal plumbing (reading jobs, career history, checks) and lives
// behind the "More instructions" disclosure below.
const ESSENTIAL_PROMPTS: PromptMeta[] = [
  {
    key: "cover_letter",
    title: "Cover letter",
    description: "Tone and structure of cover letters.",
  },
  {
    key: "qa",
    title: "Application questions",
    description: "How your written answers to application questions sound.",
  },
  {
    key: "gap_tailor",
    title: "Tailoring from your answers",
    description: "How your gap answers go into a tailored resume.",
  },
  {
    key: "chat_system",
    title: "Assistant",
    description: "How the Assistant behaves.",
  },
];
const ESSENTIAL_KEYS = new Set(ESSENTIAL_PROMPTS.map((p) => p.key));

// Words for the other prompts (one per file in backend/app/prompts/). A key
// this map lacks still shows, titled by the key itself.
const PROMPT_TITLES = new Map<string, Omit<PromptMeta, "key">>([
  ["autofill_choose", { title: "Autofill choices", description: "How Companion picks answers for form choices." }],
  ["base_from_kb_plan", { title: "New base resume plan", description: "How items are picked for a new base resume." }],
  ["base_resume_instruct", { title: "Ask for changes", description: "How the studio suggests edits." }],
  ["coherence_check", { title: "Wording checks", description: "How a tailored resume is checked for flow." }],
  ["extract_jd", { title: "Reading job descriptions", description: "How a job description becomes job details." }],
  ["gap_enrichment", { title: "Gap suggestions", description: "How gaps get suggested answers." }],
  ["kb_adapt", { title: "Rewording bullets", description: "How bullets are reworded for a resume." }],
  ["kb_capture", { title: "Quick capture", description: "How an update becomes draft bullets." }],
  ["kb_cluster_points", { title: "Merging bullets", description: "How similar bullets are combined." }],
  ["kb_document_ingest", { title: "Reading documents", description: "How a document becomes draft bullets." }],
  ["kb_entity_resolve", { title: "Matching items", description: "How a new bullet finds its item." }],
  ["kb_mint", { title: "Drafting bullets", description: "How bullets are drafted from a document." }],
  ["kb_resume_parse", { title: "Reading resume files", description: "How an imported resume is read." }],
  ["persona_draft", { title: "Persona draft", description: "How your persona is drafted." }],
  ["resume_bullet_classify", { title: "Rating bullets", description: "How the health check rates each bullet." }],
  ["resume_bullet_rewrite", { title: "Rewriting bullets", description: "How the health check writes new wording." }],
  ["resume_finding_verify", { title: "Checking issues", description: "How the health check confirms an issue." }],
  ["tailoring_skill", { title: "Tailoring skills", description: "How skills are added while tailoring." }],
]);

export function PromptsSection() {
  const prompts = useQuery({
    queryKey: ["settings", "prompts"],
    queryFn: () => apiFetch<SettingValue[]>("/api/settings/prompts"),
  });
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const advancedId = useId();

  return (
    <SettingCard
      id="prompts"
      title="AI instructions"
      description="Change how the AI writes cover letters, answers, tailoring and Assistant replies."
      errorTitle="Couldn't load your AI instructions."
      query={prompts}
    >
      {(data) => {
        const byKey = new Map(data.map((p) => [p.key, p]));
        const essential = ESSENTIAL_PROMPTS.flatMap((meta) => {
          const prompt = byKey.get(meta.key);
          return prompt ? [{ meta, prompt }] : [];
        });
        const advanced = data.filter((p) => !ESSENTIAL_KEYS.has(p.key));

        return (
          <div className="grid gap-3">
            {essential.map(({ meta, prompt }) => (
              <PromptCard
                key={meta.key}
                prompt={prompt}
                title={meta.title}
                description={meta.description}
              />
            ))}
            <div className="grid gap-3">
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground flex items-center gap-1 justify-self-start text-xs"
                aria-expanded={advancedOpen}
                aria-controls={advancedId}
                onClick={() => setAdvancedOpen((o) => !o)}
              >
                {advancedOpen ? (
                  <ChevronDownIcon className="size-3.5" aria-hidden="true" />
                ) : (
                  <ChevronRightIcon className="size-3.5" aria-hidden="true" />
                )}
                More instructions ({advanced.length})
              </button>
              {/* Hidden, never unmounted: a collapse used to drop every typed
                  draft in here, and its leave-guard registration with it. */}
              <div id={advancedId} hidden={!advancedOpen} className="grid gap-3">
                {advanced.map((p) => (
                  <PromptCard key={p.key} prompt={p} {...PROMPT_TITLES.get(p.key)} />
                ))}
              </div>
            </div>
          </div>
        );
      }}
    </SettingCard>
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

  // Every known prompt has a title on screen; one the map lacks is known only
  // by its key. Report whichever the user is actually looking at.
  const name = title ?? prompt.key;

  const apply = (result: SettingValue) => {
    qc.setQueryData<SettingValue[]>(["settings", "prompts"], (prev) =>
      prev?.map((p) => (p.key === result.key ? result : p)),
    );
  };

  const save = useMutation({
    mutationFn: () =>
      apiFetch<SettingValue>(`/api/settings/prompts/${prompt.key}`, {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    onSuccess: (result) => {
      apply(result);
      toast.success(`${name} instructions saved`);
    },
    onError: (err: Error) => toast.error(couldnt("save the instructions", err)),
  });

  const reset = useMutation({
    mutationFn: () =>
      apiFetch<SettingValue>(`/api/settings/prompts/${prompt.key}/reset`, {
        method: "POST",
      }),
    onSuccess: (result) => {
      apply(result);
      setValue(result.value);
      toast.success(`${name} instructions reset to default`);
    },
    onError: (err: Error) => toast.error(couldnt("reset the instructions", err)),
  });
  useLeaveGuard(value !== prompt.value);
  const saveOnce = useSingleFlight(save.mutate);
  const resetOnce = useSingleFlight(reset.mutate);
  const bodyId = useId();

  return (
    <CardSection className="p-0">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 p-3 text-left"
        aria-expanded={open}
        aria-controls={open ? bodyId : undefined}
        onClick={() => setOpen((o) => !o)}
      >
        <div className="min-w-0">
          {title ? (
            <>
              <p className="text-sm font-medium">{title}</p>
              <p className="text-muted-foreground text-xs">{description}</p>
            </>
          ) : (
            // An advanced prompt's key is one unbreakable word (`resume_finding_verify`): at 375
            // it pushed the row, and its Expand, past the card. `wrap-anywhere` lets it break.
            <p className="font-mono text-sm wrap-anywhere">{prompt.key}</p>
          )}
        </div>
        <span className="text-muted-foreground shrink-0 text-xs">
          {open ? "Hide" : "Edit"}
        </span>
      </button>
      {open && (
        <div id={bodyId} className="grid gap-3 px-3 pb-3">
          <Textarea
            rows={10}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="font-mono text-xs"
            aria-label={`${name} instructions`}
          />
          <div className={ACTION_ROW}>
            <Button
              size="sm"
              variant="outline"
              focusableWhenDisabled
              disabled={reset.isPending}
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={() => resetOnce()}
            >
              {reset.isPending ? "Resetting…" : "Reset to default"}
            </Button>
            <Button
              size="sm"
              focusableWhenDisabled
              disabled={save.isPending || value === prompt.value}
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={() => saveOnce()}
            >
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      )}
    </CardSection>
  );
}
