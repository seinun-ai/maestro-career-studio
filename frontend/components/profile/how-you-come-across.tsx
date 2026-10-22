"use client";

import { useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { TileCard, type TileView } from "@/components/profile/tile";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { SettingCardAction } from "@/components/settings/setting-card";
import { ACTION_ROW } from "@/components/settings/setting-layout";
import { useFocusOnNextCommit } from "@/hooks/use-focus-return";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { canApplyAsyncDraft } from "@/lib/onboarding";
import { useAutosave } from "@/lib/use-autosave";
import type { SettingValue } from "@/lib/types";

export function usePersonaQuery() {
  return useQuery({
    queryKey: ["settings", "persona"],
    queryFn: () => apiFetch<SettingValue>("/api/settings/persona"),
  });
}

/**
 * How you come across: the candidate's persona (vision, strengths, goals, working style). It sets the tone of
 * tailoring, cover letters and answers, and never adds facts to your resume.
 */
export function usePersonaTile(done: boolean | undefined, draftDisabledReason?: string): TileView {
  const persona = usePersonaQuery();
  const text = persona.data?.value.trim() ?? "";
  return {
    state: done ? { kind: "ready" } : { kind: "none" },
    summary: <span className="line-clamp-2">{persona.data ? text || "Not written yet" : "Loading…"}</span>,
    note: "Sets the tone of letters and answers",
    panel: <PersonaCard draftDisabledReason={draftDisabledReason} />,
  };
}

function PersonaCard({ draftDisabledReason }: { draftDisabledReason?: string }) {
  const query = usePersonaQuery();
  return (
    <TileCard
      tile="persona"
      description="How you'd describe yourself as a candidate: your goals, strengths and how you work. It sets the tone of tailoring, cover letters and answers, and never adds facts to your resume."
      errorTitle="Couldn't load your persona."
      query={query}
    >
      {(data) => (
        <PersonaEditor
          initial={data.value}
          draftDisabledReason={draftDisabledReason}
        />
      )}
    </TileCard>
  );
}

/**
 * Typing saves as you go, like the rest of Profile (owner, 2026-10-22); a draft from your career history does not.
 * The persona is rewritten into every cover letter, screening answer and tailored bullet, so a drafted one is read
 * before it is kept (inv-drafted-answers): it fills the box with Use this draft and Discard under it, and nothing
 * reaches the server until Use this draft. Editing the draft keeps it a draft; Use this draft keeps what the box
 * holds then.
 */
function PersonaEditor({
  initial,
  draftDisabledReason,
}: {
  initial: string;
  draftDisabledReason?: string;
}) {
  const qc = useQueryClient();
  // The drafted text waiting for Use this draft or Discard; null when none waits.
  const [review, setReview] = useState<string | null>(null);
  // Bumped on every edit so a draft that lands late can tell whether the user
  // has typed since it was requested.
  const editRevision = useRef(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // The draft row leaves on Use this draft or Discard, taking the pressed
  // button, and focus, with it.
  const focusNext = useFocusOnNextCommit();

  const save = useMutation({
    mutationFn: (next: string) =>
      apiFetch<SettingValue>("/api/settings/persona", {
        method: "PUT",
        body: JSON.stringify({ value: next }),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "persona"], result);
      void qc.invalidateQueries({ queryKey: ["setup-status"] });
    },
    // Errors still toast: a FAILED save is exactly the thing you must notice.
    onError: (err: Error) => toast.error(couldnt("save your persona", err)),
  });
  // One write in flight and only the newest text queued, so typing never sends a PUT per key.
  const { value, update, pending, failed, retry } = useAutosave(initial, (next) => save.mutateAsync(next));

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
      setReview(result.draft);
      editRevision.current += 1;
      toast.success("Draft ready to review");
    },
    onError: (err: Error) => toast.error(couldnt("draft your persona", err)),
  });

  // One request per gesture: a double click sent two model calls.
  const draftOnce = useSingleFlight(draft.mutate);

  useLeaveGuard(failed || review !== null);
  const reasonId = useId();

  return (
    <div className="grid gap-4">
      {/* Card-level actions, so they sit beside the title. Draft stays focusable
          while disabled: a native `disabled` dropped focus to <body> when a
          draft started, and hid the reason (a `title`) from the keyboard. */}
      <SettingCardAction>
        <AutosaveStatus pending={pending} failed={failed} idle={review === null} onRetry={retry} />
        <Button
          type="button"
          variant="outline"
          size="sm"
          focusableWhenDisabled
          disabled={draft.isPending || Boolean(draftDisabledReason)}
          aria-describedby={draftDisabledReason ? reasonId : undefined}
          className="data-disabled:pointer-events-none data-disabled:opacity-50"
          onClick={() => draftOnce(editRevision.current)}
        >
          {draft.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}
          Draft from my career history
        </Button>
      </SettingCardAction>
      {draftDisabledReason ? (
        <p id={reasonId} className="text-muted-foreground text-body-small">
          {draftDisabledReason}
        </p>
      ) : null}
      <Textarea
        ref={textareaRef}
        rows={10}
        value={review ?? value}
        aria-label="Persona"
        onChange={(e) => {
          const next = e.target.value;
          editRevision.current += 1;
          if (review !== null) setReview(next);
          else update(() => next);
        }}
      />
      {review !== null ? (
        <div className={ACTION_ROW}>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setReview(null);
              editRevision.current += 1;
              focusNext(textareaRef);
            }}
          >
            Discard
          </Button>
          <Button
            type="button"
            variant="tonal"
            size="sm"
            onClick={() => {
              update(() => review);
              setReview(null);
              focusNext(textareaRef);
            }}
          >
            Use this draft
          </Button>
        </div>
      ) : null}
    </div>
  );
}
