"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCard, SettingCardAction } from "@/components/settings/setting-card";
import { ACTION_ROW, SwitchRow } from "@/components/settings/setting-layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt } from "@/lib/error-text";
import { focusIfDropped } from "@/lib/focus";
import { RESUMES_FOLDER_KEY, RESUMES_FOLDER_URL } from "@/lib/resumes-folder";
import type { ResumesFolderSettings } from "@/lib/types";

const UNAVAILABLE: Record<"not_here" | "always_on_copy", string> = {
  not_here: "Your resumes are already in the applications folder of your Maestro checkout.",
  always_on_copy: "This copy keeps no resumes folder.",
};

type Patch = { enabled?: boolean; folder?: string | null };

/** Where Maestro saves a visible copy of each finished resume PDF (Settings › Basics › Resume PDFs). */
export function ResumesFolderSection() {
  const qc = useQueryClient();
  const id = useId();
  // The typed folder path; null = the field is closed. It lives here, beside the save that takes it,
  // and clears only once the server has taken it: a rejected path stays in the field to fix.
  const [draft, setDraft] = useState<string | null>(null);
  useLeaveGuard(draft !== null);
  const setting = useQuery({
    queryKey: RESUMES_FOLDER_KEY,
    queryFn: () => apiFetch<ResumesFolderSettings>(RESUMES_FOLDER_URL),
  });

  // The switch saves on toggle and the folder saves behind its own Save, so one mutation serves both.
  const save = useMutation({
    mutationFn: (patch: Patch) =>
      apiFetch<ResumesFolderSettings>(RESUMES_FOLDER_URL, {
        method: "PUT",
        body: JSON.stringify(patch),
      }),
    onSuccess: (result, patch) => {
      qc.setQueryData(RESUMES_FOLDER_KEY, result);
      if ("folder" in patch) {
        setDraft(null);
        toast.success("Resumes folder changed");
      }
    },
    onError: (error: Error, patch) =>
      toast.error(couldnt("folder" in patch ? "use that folder" : "save this setting", error)),
  });
  const saveOnce = useSingleFlight(save.mutate);

  return (
    <SettingCard
      id="resumes-folder"
      title="Resume PDFs"
      description="Maestro saves a copy of each finished resume PDF in a folder, so you can find it on your computer and in upload dialogs."
      errorTitle="Couldn't load the resumes folder."
      skeleton="h-11 w-full"
      query={setting}
    >
      {(data) =>
        !data.available ? (
          <p className="text-muted-foreground text-body-medium">
            {UNAVAILABLE[data.reason ?? "not_here"]}
          </p>
        ) : (
          <div className="grid gap-4">
            <SettingCardAction>
              <AutosaveStatus pending={save.isPending} failed={save.isError} idle={draft === null} />
            </SettingCardAction>
            <SwitchRow htmlFor={id} label="Save a copy of each resume">
              <Switch
                id={id}
                checked={data.enabled}
                onCheckedChange={(checked) => {
                  if (!save.isPending) saveOnce({ enabled: checked });
                }}
              />
            </SwitchRow>
            {data.enabled && (
              <FolderRow
                data={data}
                draft={draft}
                onDraft={setDraft}
                saving={save.isPending}
                onSave={(folder) => saveOnce({ folder })}
              />
            )}
            {/* Server-composed fixed sentence, never exception text (test_frontend_error_words _ALLOWED). */}
            {data.last_error && (
              <p className="text-destructive text-body-small">{data.last_error.message}</p>
            )}
          </div>
        )
      }
    </SettingCard>
  );
}

function FolderRow({
  data,
  draft,
  onDraft,
  saving,
  onSave,
}: {
  data: ResumesFolderSettings;
  draft: string | null;
  onDraft: (draft: string | null) => void;
  saving: boolean;
  onSave: (folder: string | null) => void;
}) {
  const inputId = useId();

  const open = useMutation({
    mutationFn: () => apiFetch<void>(`${RESUMES_FOLDER_URL}/open`, { method: "POST" }),
    onError: (error: Error) => toast.error(couldnt("open the folder", error)),
  });
  const openOnce = useSingleFlight(open.mutate);

  // The native dialog only fills the field. Nothing is saved until the user presses Save.
  const choose = useMutation({
    mutationFn: () =>
      apiFetch<{ folder: string | null }>(`${RESUMES_FOLDER_URL}/choose`, { method: "POST" }),
    onSuccess: (result) => {
      if (result.folder) onDraft(result.folder);
    },
    onError: (error: Error) => toast.error(couldnt("open the folder dialog", error)),
  });
  const chooseOnce = useSingleFlight(choose.mutate);
  // The field is frozen while a dialog or a save is out, so the answer lands in the field it came from.
  const busy = saving || choose.isPending;

  // Closing the editor (Save or Cancel) and resetting to the default each remove the focused
  // control, so focus goes to "Change folder" unless the user already moved it elsewhere.
  const changeRef = useRef<HTMLButtonElement>(null);
  const handoff = useRef({ editing: false, custom: data.custom });
  useEffect(() => {
    const prev = handoff.current;
    if ((prev.editing && draft === null) || (prev.custom && !data.custom)) focusIfDropped(changeRef.current);
    handoff.current = { editing: draft !== null, custom: data.custom };
  }, [draft, data.custom]);

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="min-w-0 text-body-medium wrap-anywhere">
          <CONCEPT_ICONS.resumesFolder
            className="text-muted-foreground mr-2 inline size-4 align-text-bottom"
            aria-hidden="true"
          />
          {data.folder_display}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" pending={open.isPending} onClick={() => openOnce(undefined)}>
            Open folder
          </Button>
          {draft === null && (
            <Button
              ref={changeRef}
              variant="outline"
              size="sm"
              onClick={() => onDraft(data.folder ?? "")}
            >
              Change folder
            </Button>
          )}
          {data.custom && draft === null && (
            <Button
              variant="ghost"
              size="sm"
              focusableWhenDisabled
              disabled={saving}
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={() => onSave(null)}
            >
              Use the default
            </Button>
          )}
        </div>
      </div>
      {draft !== null && (
        <div className="grid gap-1.5">
          <Label htmlFor={inputId}>Folder path</Label>
          <div className="flex items-center gap-2">
            <Input
              id={inputId}
              value={draft}
              // readOnly, not disabled, while it works: a disabled field drops focus to <body>.
              readOnly={busy}
              onChange={(event) => onDraft(event.target.value)}
            />
            {data.picker && (
              <Button
                variant="outline"
                pending={choose.isPending}
                focusableWhenDisabled
                disabled={saving}
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={() => chooseOnce(undefined)}
              >
                Choose…
              </Button>
            )}
          </div>
          <div className={ACTION_ROW}>
            <Button
              variant="ghost"
              focusableWhenDisabled
              disabled={choose.isPending}
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={() => onDraft(null)}
            >
              Cancel
            </Button>
            <Button
              variant="tonal"
              focusableWhenDisabled
              disabled={busy || !draft.trim()}
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={() => onSave(draft.trim())}
            >
              Save
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
