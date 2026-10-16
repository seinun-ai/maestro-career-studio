"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { useBaseResumeLabel } from "@/hooks/use-base-resume-label";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { createTailoringSession } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { jobResumeState, switchConfirm, type SwitchAction } from "@/lib/resume-pick";
import type { Application, TailoringSession } from "@/lib/types";

/**
 * The guard on every action that writes with a base resume other than the job's, or re-tailors the one you
 * applied with: step 2's actions, and the gap page's resume chips and Tailor. A pick on step 2 is only a preview;
 * the action asks first when the job's resume would be replaced (`lib/resume-pick.ts` words it for the job's
 * state), then starts or opens the gap analysis. `replace` navigates without a history entry (the gap page
 * swapping one analysis for another).
 */
export function useResumeSwitch({
  jobId,
  application,
  sessions,
  replace = false,
}: {
  jobId: string;
  application: Application | null;
  sessions: readonly TailoringSession[];
  replace?: boolean;
}) {
  const confirm = useConfirm();
  const baseName = useBaseResumeLabel();
  const qc = useQueryClient();
  const router = useRouter();
  const go = (path: string) => (replace ? router.replace(path) : router.push(path));

  const createSession = useMutation({
    mutationFn: (baseResume: string) => createTailoringSession(jobId, baseResume),
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ["tailoring-sessions", jobId] });
      if (session.health_warning) {
        toast.warning(session.health_warning, { duration: 8000 });
      }
      go(`/jobs/${jobId}/tailor/${session.id}`);
    },
    onError: (err: Error) => toast.error(couldnt("start the gap analysis", err)),
  });
  // A double click on Analyze gaps started two gap analyses.
  const createOnce = useSingleFlight(createSession.mutate);

  const state = jobResumeState(application, sessions);

  /** The confirm's words before `action` on `slug`, or null when nothing would be replaced. */
  const switchWords = (slug: string, action: SwitchAction) =>
    application
      ? switchConfirm({
          state,
          from: baseName(application.base_resume),
          to: baseName(slug),
          fromSlug: application.base_resume,
          toSlug: slug,
          action,
        })
      : null;

  /** True to go ahead: at once when nothing would be replaced, else the person's yes. */
  const confirmSwitch = async (slug: string, action: SwitchAction, returnFocus?: () => HTMLElement | null) => {
    const words = switchWords(slug, action);
    return words == null || confirm({ ...words, destructive: true, returnFocus });
  };

  /** Analyze gaps (and Restart gap analysis): a new gap analysis for `slug`, which replaces its open one. */
  const analyze = async (slug: string, returnFocus?: () => HTMLElement | null) => {
    if (await confirmSwitch(slug, "analyze", returnFocus)) createOnce(slug);
  };

  /** Continue gap analysis: the open one, after the same question. */
  const continueOn = async (slug: string, sessionId: string, returnFocus?: () => HTMLElement | null) => {
    if (await confirmSwitch(slug, "continue", returnFocus)) go(`/jobs/${jobId}/tailor/${sessionId}`);
  };

  /** The resume's newest open gap analysis, else a new one: its answers stay with it. */
  const openOrCreate = async (slug: string, returnFocus?: () => HTMLElement | null) => {
    const open = sessions
      .filter((s) => s.status === "open" && s.base_resume === slug)
      .reduce<TailoringSession | null>((newest, s) => (!newest || s.created_at > newest.created_at ? s : newest), null);
    return open ? continueOn(slug, open.id, returnFocus) : analyze(slug, returnFocus);
  };

  return {
    switchWords,
    confirmSwitch,
    analyze,
    continueOn,
    openOrCreate,
    /** The resume a gap analysis is starting for, while it starts. */
    creating: createSession.isPending ? (createSession.variables ?? null) : null,
  };
}
