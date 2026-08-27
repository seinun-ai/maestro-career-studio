"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { AutosaveStatus } from "@/components/settings/autosave-status";
import { AutosaveRow, SettingCard } from "@/components/settings/setting-card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { apiFetch } from "@/lib/api";
import { useAutosave } from "@/lib/use-autosave";
import type { QuickTailorProfile, QuickTailorSetting } from "@/lib/types";

type BooleanPreference = Exclude<keyof QuickTailorProfile, "instruction">;

const SWITCH_ROWS: {
  key: BooleanPreference;
  label: string;
}[] = [
  {
    key: "keywords_into_skills",
    label: "Add missing JD keywords to skills",
  },
  {
    key: "mirror_wording",
    label: "Mirror JD wording where evidence exists",
  },
  {
    key: "summary_rename",
    label: "Refresh summary / title alignment",
  },
  {
    key: "project_keyword_injection",
    label: "Allow placements into projects",
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
      description="What one-shot tailoring is allowed to change. Used by Quick tailor on the gap analysis page and by the browser extension's Fast tailor."
      errorTitle="Couldn't load your quick-tailor profile."
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
    onError: (error: Error) => toast.error(error.message),
  });

  const { value: profile, update, pending } = useAutosave(initial, (next) =>
    save.mutateAsync(next),
  );

  return (
    <div className="space-y-5">
      <AutosaveRow>
        <AutosaveStatus pending={pending} />
      </AutosaveRow>

      <div className="space-y-3">
        {SWITCH_ROWS.map((row) => {
          const id = `quick-tailor-${row.key}`;
          return (
            <div
              key={row.key}
              className="flex items-center justify-between gap-4 px-3 py-2.5"
            >
              <Label htmlFor={id} className="text-sm">
                {row.label}
              </Label>
              <Switch
                id={id}
                checked={profile[row.key]}
                onCheckedChange={(checked) =>
                  update((current) => ({ ...current, [row.key]: checked }))
                }
              />
            </div>
          );
        })}
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor="quick-tailor-instruction" className="text-xs" optional>
          Standing instruction
        </Label>
        <Input
          id="quick-tailor-instruction"
          value={profile.instruction}
          placeholder="e.g. keep bullets under two lines"
          onChange={(event) =>
            update((current) => ({ ...current, instruction: event.target.value }))
          }
        />
      </div>
    </div>
  );
}
