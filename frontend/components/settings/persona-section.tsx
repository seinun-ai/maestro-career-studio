"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { SettingCard } from "@/components/settings/setting-card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { canApplyAsyncDraft } from "@/lib/onboarding";
import type { SettingValue } from "@/lib/types";

const PLACEHOLDER = [
  "e.g.",
  "Vision: build data products that actually ship.",
  "Strengths: pragmatic ML, clear writing, fast prototyping.",
  "Goals: senior DS/MLE role on a product team.",
  "How I work: bias to shipping, evidence over opinion.",
].join("\n");

/**
 * The candidate's persona: vision, strengths, goals, working style.
 *
 * This was `TextSettingSection`, a generic parameterised by `settingKey` —
 * except the type of that prop was the single literal `"persona"`. It had been
 * built to serve persona and a `memory` sibling; memory is gone, so the
 * generality was 255 lines of machinery serving one caller. If a second
 * freeform text setting ever appears, generalise then, from two real examples.
 */
export function PersonaSection({
  draftDisabledReason,
}: {
  /** Why "Draft from my career" cannot run yet, or undefined when it can. */
  draftDisabledReason?: string;
}) {
  const query = useQuery({
    queryKey: ["settings", "persona"],
    queryFn: () => apiFetch<SettingValue>("/api/settings/persona"),
  });

  return (
    <SettingCard
      id="persona"
      title="Persona"
      description="Vision, strengths, goals, and how you work. Shapes the voice of tailoring, Q&A, and outreach. Never adds facts to your resume."
      errorTitle="Couldn't load your persona."
      query={query}
    >
      {(data) => (
        <PersonaEditor
          initial={data.value}
          draftDisabledReason={draftDisabledReason}
        />
      )}
    </SettingCard>
  );
}

/**
 * Explicit Save / Discard, and deliberately NOT autosave.
 *
 * It used to be both: a save fired on blur AND a Save/Discard pair appeared
 * once dirty, so the same edit could be committed two ways and leaving the
 * field committed silently. Persona is not a preference — it is rewritten into
 * every cover letter, screening answer and tailored bullet — so under the rule
 * in `autosave-status.tsx` it is the explicit-Save kind. Dropping the blur half
 * also retires the queued-write machinery it needed.
 */
function PersonaEditor({
  initial,
  draftDisabledReason,
}: {
  initial: string;
  draftDisabledReason?: string;
}) {
  const qc = useQueryClient();
  const [value, setValue] = useState(initial);
  const [saved, setSaved] = useState(initial);
  // Bumped on every edit so a draft that lands late can tell whether the user
  // has typed since it was requested.
  const editRevision = useRef(0);

  const save = useMutation({
    mutationFn: (next: string) =>
      apiFetch<SettingValue>("/api/settings/persona", {
        method: "PUT",
        body: JSON.stringify({ value: next }),
      }),
    onSuccess: (result) => {
      setSaved(result.value);
      qc.setQueryData(["settings", "persona"], result);
      void qc.invalidateQueries({ queryKey: ["setup-status"] });
      toast.success("Persona saved");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const draft = useMutation({
    mutationFn: (requestRevision: number) =>
      apiFetch<{ draft: string }>("/api/settings/persona/draft", {
        method: "POST",
      }).then((result) => ({ ...result, requestRevision })),
    onSuccess: (result) => {
      if (!canApplyAsyncDraft(result.requestRevision, editRevision.current)) {
        toast.info("Draft finished, but your newer edits were kept.");
        return;
      }
      setValue(result.draft);
      editRevision.current += 1;
      toast.success("Draft ready to review");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const dirty = value !== saved;

  return (
    <>
      <div className="mb-3 flex justify-end">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => draft.mutate(editRevision.current)}
          disabled={draft.isPending || Boolean(draftDisabledReason)}
          title={draftDisabledReason}
        >
          {draft.isPending ? <Loader2 className="animate-spin" /> : null}
          Draft from my career
        </Button>
      </div>
      <Textarea
        rows={10}
        value={value}
        placeholder={PLACEHOLDER}
        aria-label="Persona"
        onChange={(e) => {
          setValue(e.target.value);
          editRevision.current += 1;
        }}
      />
      {dirty ? (
        <div className="mt-3 flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setValue(saved);
              editRevision.current += 1;
            }}
            disabled={save.isPending}
          >
            Discard
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() => save.mutate(value)}
            disabled={save.isPending}
          >
            {save.isPending ? <Loader2 className="animate-spin" /> : null}
            Save
          </Button>
        </div>
      ) : null}
    </>
  );
}
