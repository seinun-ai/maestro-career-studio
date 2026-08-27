"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDownIcon, ChevronRightIcon } from "lucide-react";
import { toast } from "sonner";

import { SettingCard } from "@/components/settings/setting-card";
import { Button } from "@/components/ui/button";
import { CardSection } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import type { SettingValue } from "@/lib/types";

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

export function PromptsSection() {
  const prompts = useQuery({
    queryKey: ["settings", "prompts"],
    queryFn: () => apiFetch<SettingValue[]>("/api/settings/prompts"),
  });
  const [advancedOpen, setAdvancedOpen] = useState(false);

  return (
    <SettingCard
      id="prompts"
      title="Prompts"
      description="Override the voice used for cover letters, outreach, Q&A, and chat."
      errorTitle="Couldn't load your prompts."
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
          <div className="space-y-3">
            {essential.map(({ meta, prompt }) => (
              <PromptCard
                key={meta.key}
                prompt={prompt}
                title={meta.title}
                description={meta.description}
              />
            ))}
            <div className="pt-1">
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground flex items-center gap-1 text-xs"
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

  // The curated prompts have human titles on screen; an advanced one is only
  // ever known by its key. Report whichever the user is actually looking at
  // rather than always printing the raw key.
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
      toast.success(`${name} saved`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const reset = useMutation({
    mutationFn: () =>
      apiFetch<SettingValue>(`/api/settings/prompts/${prompt.key}/reset`, {
        method: "POST",
      }),
    onSuccess: (result) => {
      apply(result);
      setValue(result.value);
      toast.success(`${name} reset to default`);
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
            aria-label={`${name} prompt text`}
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
