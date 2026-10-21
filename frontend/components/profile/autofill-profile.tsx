"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { apiFetch } from "@/lib/api";
import { forSaving, profileForEditing, type Profile } from "@/lib/autofill-options";
import { couldnt } from "@/lib/error-text";
import type { SettingEnvelope } from "@/lib/types";
import { useAutosave } from "@/lib/use-autosave";

/** What one editor's `AutosaveStatus` shows. */
export type SaveState = { pending: boolean; failed: boolean; onRetry: () => void };

type AutofillEditing = {
  profile: Profile;
  /** Change the profile from one editor (`surface`: "contact", "diversity", "next-up"…). It saves as you go. */
  update: (surface: string, next: (current: Profile) => Profile) => void;
  saveState: (surface: string) => SaveState;
};

const AutofillContext = createContext<AutofillEditing | null>(null);

/**
 * The answers for job forms, held once for every Profile editor that changes them (Contact, Work permits,
 * Start and pay, Education, Languages, Your own questions, the Diversity and Eligibility folds, Next up).
 * They save as you go: one write in flight and only the newest queued (`useAutosave`), each write the
 * whole profile without the one-set `work_auth` view, so the server keeps the per-country map
 * (`forSaving`). No toast on a save, a toast on a failure; the editor that made the last edit shows the
 * status, so two open editors never both announce one save. A refetch that brings another writer's change
 * (the Companion's pause row learns answers into this profile) is taken only while every edit is already
 * on the server (`adopt`).
 */
export function AutofillProfileProvider({ served, children }: { served: Profile; children: ReactNode }) {
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: (next: Profile) =>
      apiFetch<SettingEnvelope<Profile>>("/api/settings/autofill", {
        method: "PUT",
        body: JSON.stringify({ value: forSaving(next) }),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "autofill"], result);
      void qc.invalidateQueries({ queryKey: ["setup-status"] });
    },
    onError: (err: Error) => toast.error(couldnt("save your answers", err)),
  });
  const [initial] = useState(() => profileForEditing(served));
  const answers = useAutosave<Profile>(initial, (next) => save.mutateAsync(next));
  const [last, setLast] = useState<string | null>(null);
  // A failed write leaves answers on screen the server lacks.
  useLeaveGuard(answers.failed);

  const seen = useRef(served);
  const { adopt } = answers;
  useEffect(() => {
    if (served === seen.current) return;
    seen.current = served;
    adopt(profileForEditing(served));
  }, [served, adopt]);

  const editing: AutofillEditing = {
    profile: answers.value,
    update: (surface, next) => {
      setLast(surface);
      answers.update(next);
    },
    saveState: (surface) => ({
      pending: answers.pending && last === surface,
      failed: answers.failed && last === surface,
      onRetry: answers.retry,
    }),
  };
  return <AutofillContext value={editing}>{children}</AutofillContext>;
}

export function useAutofillProfile(): AutofillEditing {
  const editing = useContext(AutofillContext);
  if (!editing) throw new Error("useAutofillProfile must be used inside <AutofillProfileProvider>");
  return editing;
}
