"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { AutosaveStatus } from "@/components/settings/autosave-status";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { SettingCard, SettingCardAction } from "@/components/settings/setting-card";
import { SwitchRow } from "@/components/settings/setting-layout";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { useAutosave } from "@/lib/use-autosave";
import type { QuickTailorProfile, QuickTailorSetting } from "@/lib/types";

type BooleanPreference = Exclude<keyof QuickTailorProfile, "instruction">;

const SWITCH_ROWS: {
  key: BooleanPreference;
  label: string;
}[] = [
  {
    key: "keywords_into_skills",
    label: "Add missing job description keywords to Skills",
  },
  {
    key: "mirror_wording",
    label: "Use the job description's wording when your experience backs it up",
  },
  {
    key: "summary_rename",
    label: "Match your summary and title to the job",
  },
  {
    key: "project_keyword_injection",
    label: "Add keywords to projects",
  },
];

export function QuickTailorSection() {
  const profile = useQuery({
    queryKey: ["settings", "quick-tailor"],
    queryFn: () => apiFetch<QuickTailorSetting>("/api/settings/quick-tailor"),
  });

  return (
    <SettingCard
      id="quick-tailor"
      title="Quick tailor"
      description="What Quick tailor may change on your resume, on the gap analysis page and in the Companion."
      errorTitle="Couldn't load Quick tailor settings."
      skeleton="h-48 w-full"
      query={profile}
    >
      {(data) => <QuickTailorEditor initial={data.value} />}
    </SettingCard>
  );
}

/**
 * Autosaves. These are pure preferences — nothing is spent and nothing runs
 * when they change; they are read later, at tailor time — so by the rule in
 * `autosave-status.tsx` they must not sit behind a Save button. They did, and
 * that made this the one preferences card on the page that staged its edits.
 */
function QuickTailorEditor({ initial }: { initial: QuickTailorProfile }) {
  const qc = useQueryClient();

  const save = useMutation({
    mutationFn: (next: QuickTailorProfile) =>
      apiFetch<QuickTailorSetting>("/api/settings/quick-tailor", {
        method: "PUT",
        body: JSON.stringify({ value: next }),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "quick-tailor"], result);
    },
    // Errors still toast: a FAILED save is exactly the thing you must notice.
    onError: (error: Error) => toast.error(couldnt("save Quick tailor settings", error)),
  });

  const { value: profile, update, pending, failed, retry } = useAutosave(initial, (next) =>
    save.mutateAsync(next),
  );
  useLeaveGuard(failed);

  return (
    <div className="grid gap-6">
      <SettingCardAction>
        <AutosaveStatus pending={pending} failed={failed} onRetry={retry} />
      </SettingCardAction>

      <div className="divide-y">
        {SWITCH_ROWS.map((row) => {
          const id = `quick-tailor-${row.key}`;
          return (
            <SwitchRow key={row.key} htmlFor={id} label={row.label}>
              <Switch
                id={id}
                checked={profile[row.key]}
                onCheckedChange={(checked) =>
                  update((current) => ({ ...current, [row.key]: checked }))
                }
              />
            </SwitchRow>
          );
        })}
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor="quick-tailor-instruction" optional>
          Extra instruction
        </Label>
        <p id="quick-tailor-instruction-hint" className="text-muted-foreground text-xs">
          Used every time Quick tailor runs.
        </p>
        <Input
          id="quick-tailor-instruction"
          aria-describedby="quick-tailor-instruction-hint"
          value={profile.instruction}
          onChange={(event) =>
            update((current) => ({ ...current, instruction: event.target.value }))
          }
        />
      </div>
    </div>
  );
}
