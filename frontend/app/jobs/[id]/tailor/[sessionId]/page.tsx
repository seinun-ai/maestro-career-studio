"use client";

import { use, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { GuardedLink as Link } from "@/components/guarded-link";
import { focusIfDropped } from "@/hooks/use-focus-return";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useLoadFailureError } from "@/hooks/use-last-seen";
import { useRefreshFailedNotice } from "@/hooks/use-refresh-failed-notice";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  Library,
  Loader2,
  Wand2,
  Zap,
} from "lucide-react";
import { toast } from "sonner";

import { TriangleAlert } from "lucide-react";

import { GapCard } from "@/components/gap-analysis/gap-card";
import {
  buildPlacementTargets,
  enabledProjectNames,
  GapLocked,
  type PlacementTarget,
} from "@/components/gap-analysis/resolution-controls";
import { IconButton } from "@/components/icon-button";
import { useConfirm } from "@/components/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { LoadErrorState } from "@/components/load-error-state";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { couldnt, errorDetail } from "@/lib/error-text";
import { gapCounts } from "@/lib/gap-counts";
import { cn } from "@/lib/utils";
import {
  ApiError,
  apiFetch,
  closeTailoringSession,
  createApplicationFromBase,
  createTailoringSession,
  getTailoringSession,
  saveResolutions,
  tailorSession,
} from "@/lib/api";
import {
  baseResumeLabel,
  isAutoResolved,
  resolutionProvenance,
  type BaseResumeDetail,
  type GapCategory,
  type JobDetail,
  type Resolution,
} from "@/lib/types";

type SaveState = "idle" | "saving" | "saved" | "error";

function SaveIndicator({
  state,
  onRetry,
}: {
  state: SaveState;
  /** Omitted for a stale session: every save 409s, and the banner's action is the way out. */
  onRetry?: () => Promise<boolean>;
}) {
  const statusRef = useRef<HTMLSpanElement>(null);
  const refocus = useRef(false);
  // A state, not the ref: whether the button renders is decided during render,
  // where the compiler forbids ref reads. It keeps Try again mounted (and
  // focused) while the retry runs, since `state` flips to "saving" at once.
  const [retrying, setRetrying] = useState(false);
  // Try again unmounts once the retry lands; focus it dropped goes to the status.
  // Only dropped focus: the user may already be typing in a field again. A
  // layout effect, so no frame is painted with focus on <body>.
  useLayoutEffect(() => {
    if (retrying || state !== "saved" || !refocus.current) return;
    refocus.current = false;
    focusIfDropped(statusRef.current);
  }, [state, retrying]);
  return (
    <span className="flex items-center gap-2 text-xs">
      <span
        ref={statusRef}
        tabIndex={-1}
        aria-live="polite"
        className={cn(
          "flex items-center gap-1",
          state === "error" ? "text-destructive" : "text-muted-foreground",
        )}
      >
        {state === "saving" && (
          <Loader2 className="size-3 animate-spin" aria-hidden="true" />
        )}
        {state === "saving"
          ? "Saving…"
          : state === "saved"
            ? "Saved"
            : state === "error"
              ? "Not saved"
              : null}
      </span>
      {onRetry && (state === "error" || retrying) ? (
        <Button
          type="button"
          variant="link"
          size="xs"
          className="h-auto p-0 data-disabled:opacity-50"
          focusableWhenDisabled
          disabled={retrying}
          onClick={() => {
            refocus.current = true;
            setRetrying(true);
            void onRetry().then((ok) => {
              // A failed retry keeps Try again, and focus, where they are: the
              // next ordinary save must not pull focus to the status.
              if (!ok) refocus.current = false;
              setRetrying(false);
            });
          }}
        >
          Try again
        </Button>
      ) : null}
    </span>
  );
}

function CategorySection({
  category,
  resolutions,
  resolutionMap,
  targets,
  projects,
  baseResumeError,
  onChange,
}: {
  category: GapCategory;
  resolutions: Resolution[];
  resolutionMap: Map<string, Resolution>;
  targets: PlacementTarget[] | null;
  projects: string[] | null;
  baseResumeError: boolean;
  onChange: (gapId: string, resolution: Resolution | null) => void;
}) {
  const [open, setOpen] = useState(true);
  // The footer's words: "open" means neither answered nor skipped.
  const counts = gapCounts(
    category.gaps.map((gap) => gap.gap_id),
    resolutions,
  );
  return (
    <section className="space-y-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center gap-2 text-left"
      >
        <ChevronDown
          className={cn(
            "text-muted-foreground size-4 shrink-0 transition-transform",
            !open && "-rotate-90",
          )}
        />
        <span className="text-sm font-medium">{category.title}</span>
        <Badge variant={counts.open === 0 ? "default" : "secondary"}>
          {counts.open > 0 ? `${counts.open} open` : "Nothing open"}
        </Badge>
        <span className="text-muted-foreground ml-auto hidden truncate text-xs sm:inline">
          {category.description}
        </span>
      </button>
      {open && (
        <div className="space-y-2 pl-6">
          {category.gaps.map((gap) => (
            <GapCard
              key={gap.gap_id}
              gap={gap}
              resolution={resolutionMap.get(gap.gap_id)}
              targets={targets}
              projects={projects}
              baseResumeError={baseResumeError}
              onChange={(resolution) => onChange(gap.gap_id, resolution)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export default function TailorSessionPage({
  params,
}: {
  params: Promise<{ id: string; sessionId: string }>;
}) {
  const { id: jobId, sessionId } = use(params);
  const qc = useQueryClient();
  const router = useRouter();
  const confirm = useConfirm();
  const notesHintId = useId();

  const session = useQuery({
    queryKey: ["tailoring-session", sessionId],
    queryFn: () => getTailoringSession(sessionId),
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 2,
  });

  const slug = session.data?.base_resume;
  const jobDetail = useQuery({
    queryKey: ["job-detail", jobId],
    queryFn: () => apiFetch<JobDetail>(`/api/jobs/${jobId}/detail`),
  });

  const baseResume = useQuery({
    queryKey: ["base-resumes", slug],
    queryFn: () => apiFetch<BaseResumeDetail>(`/api/base-resumes/${slug}`),
    enabled: !!slug,
  });

  // Working copy of the resolution list: the server list until the first local
  // edit, then the edited list. `latestRef` mirrors the edited list for the
  // async save path (null = no edits this visit, nothing to flush).
  //
  // SEEDING MATTERS (design §4.2): the KB resolver PRE-STORES auto-resolutions in
  // resolutions_json at session creation, and the autosave below PATCHes with
  // replace=true — the list it sends is the whole truth. Because both the
  // working copy and the save fallback start from `session.data.resolutions_json`,
  // `handleChange` builds each next list ON TOP of the stored autos, so the first
  // autosave carries them forward instead of deleting every gap the resolver
  // solved. Do not initialize `edited` to `[]`.
  const [edited, setEdited] = useState<Resolution[] | null>(null);
  const resolutions: Resolution[] = edited ?? session.data?.resolutions_json ?? [];
  const latestRef = useRef<Resolution[] | null>(null);

  // Optional "how should this be tailored?" note. Mirrors the resolutions pattern:
  // `promptDraft` is null until the first local edit, then the edited string.
  // `promptRef` feeds the async save path — null means untouched this visit, so
  // the PATCH omits user_prompt and the server leaves the stored value alone.
  const [promptDraft, setPromptDraft] = useState<string | null>(null);
  const promptRef = useRef<string | null>(null);
  const userPrompt = promptDraft ?? session.data?.user_prompt ?? "";

  // A stale session's frozen gaps no longer match the current base/JD, so the
  // server rejects any save (409). Declared here (used by autosave below) so the
  // schedule sites and saveNow can bail out instead of looping 409s forever.
  const staleReason = session.data?.stale_reason ?? null;

  // --- Autosave: 800ms debounce, serialized PATCHes of the FULL list --------
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chainRef = useRef<Promise<void>>(Promise.resolve());
  // Bumped by every edit. A save reports "Saved" or "Not saved" only if no edit
  // came after it began; otherwise a newer save is queued and will report.
  const editGen = useRef(0);

  const saveNow = async (): Promise<boolean> => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    // A stale session rejects every save (409); flushing would only spam a
    // misleading toast. The user must Start Over — nothing to save here.
    if (staleReason) return true;
    if (latestRef.current === null && promptRef.current === null) return true; // nothing edited yet
    const gen = editGen.current;
    setSaveState("saving");
    // Serialize behind any in-flight save so responses can't land out of order;
    // each attempt reads the refs at execution time, so the last write wins.
    // replace=true: the full list is the whole truth — retracted resolutions
    // (undo, cleared inputs, abandoned action switches) are deleted server-side.
    // When only the prompt was edited, keep the server's resolution list intact.
    const attempt = () =>
      saveResolutions(
        sessionId,
        latestRef.current ?? session.data?.resolutions_json ?? [],
        true,
        promptRef.current ?? undefined,
      ).then(() => undefined);
    const run = chainRef.current.then(attempt, attempt);
    chainRef.current = run.then(
      () => undefined,
      () => undefined,
    );
    try {
      await run;
      if (editGen.current === gen) setSaveState("saved");
      return true;
    } catch (error) {
      if (editGen.current === gen) setSaveState("error");
      if (error instanceof ApiError && error.status === 409) {
        // Surface the SERVER detail when it is a sentence for the user (the
        // analysis may well be open, just stale) rather than a hardcoded "no
        // longer open". Invalidating refreshes stale_reason so the stale
        // banner appears and future autosaves bail out (see saveNow's guard).
        toast.error(errorDetail(error) ?? "This gap analysis is out of date. Start a new one.");
        void qc.invalidateQueries({ queryKey: ["tailoring-session", sessionId] });
      } else {
        toast.error(couldnt("save your answers", error));
      }
      return false;
    }
  };

  // saveNow changes every render; the unmount cleanup must call the newest one.
  const saveNowRef = useRef(saveNow);
  useEffect(() => {
    saveNowRef.current = saveNow;
  });
  // Leaving within the debounce saves instead of dropping the tail.
  useEffect(
    () => () => {
      if (!timerRef.current) return;
      clearTimeout(timerRef.current);
      timerRef.current = null;
      void saveNowRef.current();
    },
    [],
  );
  // One tailor per gesture: the lock spans the confirm, the pre-tailor save and
  // the ~30 s LLM call. `tailor.isPending` stays false until the save lands, so
  // a second click in that window sent a second tailor. While it holds, every
  // gap input is locked (`GapLocked`) and autosave holds back.
  const tailorLock = useRef(false);
  const [tailorBusy, setTailorBusy] = useState(false);
  const endTailor = () => {
    tailorLock.current = false;
    setTailorBusy(false);
  };

  // Reload/close cannot flush; an in-app exit can. A failed save is unsaved either way.
  useLeaveGuard(saveState === "saving", { reloadOnly: true });
  useLeaveGuard(saveState === "error");

  // --- Tailor ---------------------------------------------------------------
  const tailor = useMutation({
    mutationFn: (applyProfile?: boolean) =>
      tailorSession(sessionId, undefined, applyProfile),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      qc.invalidateQueries({ queryKey: ["ats-scores", jobId] });
      qc.invalidateQueries({ queryKey: ["tailoring-sessions", jobId] });
      qc.setQueryData(["tailoring-session", sessionId], result.session);
      if (result.compare) {
        const { base, tailored, delta } = result.compare;
        const sign = delta.composite >= 0 ? "+" : "";
        toast.success(
          `ATS score: ${base.composite.toFixed(1)} to ${tailored.composite.toFixed(1)} (${sign}${delta.composite.toFixed(1)})`,
        );
      } else if (result.compare_error) {
        // compare_error with null compare still means tailoring SUCCEEDED.
        toast.warning(result.compare_error);
      } else {
        toast.success("Resume tailored");
      }
      // Quiet, non-blocking note: gap answers the Career KB write-back
      // skipped, with the server-composed reasons — a flywheel drop must
      // never be silent (the page navigates away, so the toast IS the note).
      const skips = result.kb_writeback_skips ?? [];
      if (skips.length > 0) {
        toast.message(
          `${skips.length} ${skips.length === 1 ? "answer wasn't" : "answers weren't"} added to your career history`,
          { description: skips.map((skip) => skip.detail).join(" · ") },
        );
      }
      // Review-first (design §4.5): land in the studio's diff mode, where every
      // change is listed with its provenance and can be reverted one at a time —
      // the consent surface for everything the resolver auto-applied. The job's
      // Resume tab (compare + PDF) is one click away, and is still the landing
      // spot if the tailor somehow produced no application to open.
      const applicationId = result.session.application_id;
      router.push(
        applicationId
          ? `/applications/${applicationId}/resume?review=1`
          : `/jobs/${jobId}?tab=output`,
      );
    },
    onError: (error: Error, applyProfile) => {
      // A failed tailor USED to mean the server changed nothing — that is
      // tailor()'s transaction boundary (nothing commits before score_target),
      // which is why only the 409 path refetched. `apply_profile` breaks that
      // assumption: the profile fill commits BEFORE tailor() runs, so a failure
      // here can leave resolutions this page has never seen. Refetch, and drop
      // the local working copy so the server's list wins — `saveNow()` already
      // flushed the user's own edits before the mutation, so nothing is lost.
      // Without this the footer keeps stale counts, keeps offering Quick tailor
      // (local `open` never moved), and every retry re-fails the same way.
      if (applyProfile) {
        setEdited(null);
        latestRef.current = null;
        void qc.invalidateQueries({ queryKey: ["tailoring-session", sessionId] });
      }
      if (error instanceof ApiError && error.status === 409) {
        toast.error("This gap analysis was closed. Reloading.");
        void qc.invalidateQueries({ queryKey: ["tailoring-session", sessionId] });
        return;
      }
      // The backend's "no actionable resolutions" is accurate but not
      // actionable. On the Quick tailor path it means the profile had nothing it
      // was allowed to add, so point at the two real ways forward.
      if (
        applyProfile &&
        error instanceof ApiError &&
        error.status === 400 &&
        error.message === "No actionable resolutions to tailor"
      ) {
        toast.error(
          "Quick tailor had nothing to add here. Answer a gap yourself, or use your resume as is.",
        );
        return;
      }
      toast.error(couldnt("tailor your resume", error));
    },
  });

  // One schedule for both handlers. "Saving…" covers the debounce: an edit
  // waiting its turn is being saved.
  const scheduleSave = () => {
    editGen.current += 1;
    if (timerRef.current) clearTimeout(timerRef.current);
    // A stale session rejects every save (409). The edit stays on screen
    // unsaved, so say so, which also keeps the leave guard up.
    if (staleReason) {
      setSaveState("error");
      return;
    }
    // No autosave while tailoring: a PATCH landing after the tailor commits
    // would 409. `runTailor` saves anything held back if the tailor fails.
    if (tailorLock.current) return;
    setSaveState("saving");
    timerRef.current = setTimeout(() => {
      void saveNow();
    }, 800);
  };

  const handleChange = (gapId: string, resolution: Resolution | null) => {
    let next: Resolution[];
    if (resolution === null) {
      next = resolutions.filter((r) => r.gap_id !== gapId);
    } else if (resolutions.some((r) => r.gap_id === gapId)) {
      next = resolutions.map((r) => (r.gap_id === gapId ? resolution : r));
    } else {
      next = [...resolutions, resolution];
    }
    latestRef.current = next;
    setEdited(next);
    scheduleSave();
  };

  const handlePromptChange = (value: string) => {
    promptRef.current = value;
    setPromptDraft(value);
    scheduleSave();
  };

  // --- Use resume as is (perfect-fit / nothing-to-tailor escape hatch) ----------
  const useAsIs = useMutation({
    mutationFn: async () => {
      const data = session.data;
      if (!data) throw new Error("Still loading. Try again in a moment.");
      const application = await createApplicationFromBase(jobId, data.base_resume, []);
      // Best-effort cleanup: the application is already created at this point,
      // so a failure to close the now-redundant session must not block the user.
      try {
        await closeTailoringSession(sessionId);
      } catch (error) {
        console.warn("Failed to close tailoring session after using base resume as-is", error);
      }
      return application;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      qc.invalidateQueries({ queryKey: ["ats-scores", jobId] });
      qc.invalidateQueries({ queryKey: ["tailoring-session", sessionId] });
      qc.invalidateQueries({ queryKey: ["tailoring-sessions", jobId] });
      toast.success("Application created from your base resume");
      router.push(`/jobs/${jobId}?tab=output`);
    },
    onError: (error: Error) => toast.error(couldnt("use your resume as is", error)),
  });
  // A double click made two applications for one job: both POSTs found none to reuse.
  const applyAsIsOnce = useSingleFlight(useAsIs.mutate);

  // --- Stale session: frozen gaps no longer match the current base/JD ---------
  // (`staleReason` is declared above so the autosave path can read it.)
  const startOver = useMutation({
    mutationFn: () => {
      const data = session.data;
      if (!data) throw new Error("Still loading. Try again in a moment.");
      return createTailoringSession(jobId, data.base_resume);
    },
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["tailoring-sessions", jobId] });
      router.replace(`/jobs/${jobId}/tailor/${created.id}`);
    },
    onError: (error: Error) => toast.error(couldnt("start over", error)),
  });

  // --- Derived counts ---------------------------------------------------------
  const categories = session.data?.gaps_json.categories ?? [];
  const gaps = categories.flatMap((category) => category.gaps);
  const resolutionMap = new Map(resolutions.map((r) => [r.gap_id, r] as const));
  // cannot_confirm is a skip for the DOCUMENT (its KB record is durable): it
  // must not count as answered, or Tailor would run with nothing to do.
  const {
    answered: addressed,
    skipped,
    open,
  } = gapCounts(
    gaps.map((gap) => gap.gap_id),
    resolutions,
  );
  // Gaps the resolver pre-applied. Counted off the LIVE list, so an Undo drops
  // the banner's count immediately. The job's own wording is not the user's
  // evidence, so the banner names it apart.
  const autoResolved = resolutions.filter(isAutoResolved);
  const fromWording = autoResolved.filter(
    (r) => resolutionProvenance(r)?.source === "wording_auto",
  ).length;
  const fromYours = autoResolved.length - fromWording;
  // F6d — a summary gap is ALWAYS present, so `total === 0` no longer means "clean".
  // "Strong match" is when the only gap left is that always-present summary (no skill,
  // coverage, title, gate, or format gaps) — surface an honest positive state instead
  // of a misleading "no gaps found", while still letting the user tailor.
  const substantiveGaps = gaps.filter((gap) => gap.kind !== "summary");
  const strongMatch = substantiveGaps.length === 0;
  const hasSummaryGap = gaps.some((gap) => gap.kind === "summary");

  /** Confirm, flush the pending save, then tailor: one sequence, one lock. */
  const runTailor = async (ask: () => Promise<boolean>, applyProfile?: boolean) => {
    if (tailorLock.current) return;
    tailorLock.current = true;
    setTailorBusy(true);
    if (!(await ask())) return endTailor();
    // Flush any pending debounced save so the tailor sees the latest edits.
    const gen = editGen.current;
    const saved = await saveNow();
    if (!saved) return endTailor();
    tailor.mutate(applyProfile, {
      // Success navigates away with the lock still held.
      onError: () => {
        endTailor();
        // An edit that slipped in while tailoring was held back; the user is
        // still here, so save it now. Not after Quick tailor: its onError
        // drops the working copy for the server's list, and a save from this
        // render's copy could overwrite the profile fill it committed.
        if (editGen.current !== gen && !applyProfile) scheduleSave();
      },
    });
  };

  const onTailorClick = async () => {
    if (!session.data) return;
    if (addressed === 0) {
      toast.error(
        "Answer at least one gap first. Skipped gaps change nothing.",
      );
      return;
    }
    await runTailor(async () =>
      open > 0
        ? confirm({
            title: `${open} ${open === 1 ? "gap is" : "gaps are"} still open`,
            description:
              "Open gaps stay as they are. Only your answers go into the tailored resume.",
            confirmLabel: "Tailor anyway",
          })
        : true,
    );
  };

  /**
   * Quick tailor: fill every gap still open from the saved quick-tailor profile,
   * then tailor. The ONE difference from `onTailorClick` is what happens to the
   * open gaps — resolutions already stored (hand-made or auto) always win, which
   * the server enforces by filtering the plan against existing gap_ids.
   *
   * Shown only when `open > 0`; with nothing open it would be identical to
   * "Tailor resume", and two buttons with one behavior is how a UI starts lying.
   */
  const onQuickTailorClick = async () => {
    if (!session.data) return;
    await runTailor(
      () =>
        confirm({
          title: `Quick tailor ${open} open ${open === 1 ? "gap" : "gaps"}?`,
          description:
            "Fills the open gaps your Quick tailor settings allow, then tailors. " +
            "Your answers stay as they are. You can review and undo each change afterward.",
          confirmLabel: "Quick tailor",
        }),
      true,
    );
  };

  useRefreshFailedNotice(session, "this gap analysis");

  // --- Render branches --------------------------------------------------------
  // A 404 is "this session is gone", not a generic failure. Remember the error:
  // a refetch clears it, and the not-found copy would otherwise flash away. A
  // revisit's first render has none yet and shows the skeleton instead.
  const sessionError = useLoadFailureError(session);
  const sessionMissing = sessionError instanceof ApiError && sessionError.status === 404;

  if (sessionError != null) {
    if (sessionMissing) {
      return (
        <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
          <h1 className="text-lg font-medium">This gap analysis no longer exists</h1>
          <p className="text-muted-foreground text-sm">
            It may have been deleted along with its job.
          </p>
          <Button
            nativeButton={false}
            render={<Link href={`/jobs/${jobId}`}>Back to job</Link>}
          />
        </main>
      );
    }
    return (
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
        <LoadErrorState
          title="Couldn't load this gap analysis."
          detail={errorDetail(sessionError)}
          retrying={session.isFetching}
          onRetry={() => void session.refetch()}
          action={
            <Button
              nativeButton={false}
              render={<Link href={`/jobs/${jobId}`}>Back to job</Link>}
            />
          }
        />
      </main>
    );
  }

  if (session.isLoading || !session.data) {
    return (
      <main className="mx-auto w-full max-w-4xl flex-1 space-y-4 p-6">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </main>
    );
  }

  if (session.data.status !== "open") {
    // Sessions can end up here as "tailored" (the normal terminal state),
    // "superseded" (a newer session for the same base resume replaced it —
    // e.g. "Start over"), or "abandoned" (closed without tailoring — e.g.
    // "Use resume as is").
    let heading = "This gap analysis is done";
    let description = "Your tailored resume is on the job's Resume tab.";
    if (session.data.status === "superseded") {
      heading = "A newer gap analysis replaced this one";
      description = "Continue from the job's Score and tailor tab.";
    } else if (session.data.status === "abandoned") {
      heading = "This gap analysis was closed";
      description = "Start a new one from the job's Score and tailor tab.";
    }
    return (
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
        <CheckCircle2 className="text-primary size-10" />
        <h1 className="text-lg font-medium">{heading}</h1>
        <p className="text-muted-foreground text-sm">{description}</p>
        <div className="flex gap-2">
          <Button
            nativeButton={false}
            render={
              <Link href={`/jobs/${jobId}?tab=output`}>View tailored resume</Link>
            }
          />
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href={`/jobs/${jobId}`}>Back to job</Link>}
          />
        </div>
      </main>
    );
  }

  const gapsJson = session.data.gaps_json;
  const targets = baseResume.data ? buildPlacementTargets(baseResume.data.data) : null;
  const projects = baseResume.data ? enabledProjectNames(baseResume.data.data) : null;

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-4 p-6 pb-0">
      {staleReason ? (
        <div className="animate-fade-rise flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <TriangleAlert className="size-4 shrink-0 text-amber-700 dark:text-amber-400" />
            <p className="text-sm">
              This gap analysis is out of date because {staleReason}.{" "}
              Your changes here won&apos;t be saved. Start a new one to keep going.
            </p>
          </div>
          <Button
            size="sm"
            className="rounded-full"
            onClick={() => startOver.mutate()}
            disabled={startOver.isPending}
          >
            {startOver.isPending ? "Starting…" : "Start new gap analysis"}
          </Button>
        </div>
      ) : null}
      <header className="flex items-start gap-2">
        <IconButton
          label="Back to job"
          icon={<ArrowLeft className="size-4" />}
          size="icon-sm"
          className="mt-0.5 shrink-0"
          nativeButton={false}
          render={<Link href={`/jobs/${jobId}`} className="text-muted-foreground" />}
        />
        <div className="min-w-0 flex-1">
          <h1 className="text-[22px] font-medium tracking-tight">Gap analysis</h1>
          <p className="text-muted-foreground text-sm">
            {baseResume.data?.display_name?.trim() || baseResumeLabel(session.data.base_resume)} · ATS score before tailoring:{" "}
            <span className="text-foreground font-medium tabular-nums">
              {gapsJson.base_composite.toFixed(1)}
            </span>
            <span className="text-muted-foreground"> / 100</span>
          </p>
        </div>
      </header>

      <div
        className={cn(
          "flex flex-1 flex-col gap-5",
          tailorBusy && "pointer-events-none opacity-60",
        )}
      >
        <GapLocked value={tailorBusy}>
        {gapsJson.coverage_warning && (
          <div className="border-amber-500/30 bg-amber-500/10 animate-fade-rise flex items-start gap-3 rounded-xl border p-4 text-amber-900 dark:text-amber-200">
            <TriangleAlert className="size-5 shrink-0 text-amber-700 dark:text-amber-400 mt-0.5" />
            <div className="space-y-1 text-sm">
              {/* The server's sentence already gives the counts. */}
              <p className="font-medium">{gapsJson.coverage_warning}</p>
            </div>
          </div>
        )}
        {strongMatch && !gapsJson.coverage_warning && (
          <div className="border-primary/30 bg-primary/5 rounded-xl border p-4">
            <p className="text-foreground text-sm font-medium">Strong match</p>
            <p className="text-muted-foreground text-sm">
              {hasSummaryGap
                ? "This resume already fits the job well. Strengthen your summary below, then tailor."
                : "This resume already fits the job well."}
            </p>
          </div>
        )}
        {autoResolved.length > 0 && (
          <div className="border-primary/25 bg-primary/[0.04] animate-fade-rise flex items-center gap-2.5 rounded-xl border px-4 py-3">
            <Library className="text-primary size-4 shrink-0" />
            <p className="text-sm">
              <span className="font-medium">
                {autoResolved.length} {autoResolved.length === 1 ? "gap was" : "gaps were"}
              </span>{" "}
              {fromYours === 0
                ? "filled in with the job's own words"
                : fromWording === 0
                  ? "filled in from your resumes and career history"
                  : "filled in from your resumes, your career history and the job's own words"}
              . Review them below.
            </p>
          </div>
        )}
        {autoResolved.length === 0 && !strongMatch && open > 0 && (
          <p className="text-muted-foreground text-sm">
            These gaps need your input. <span className="font-medium">Add keyword</span>{" "}
            uses the job&apos;s exact words, <span className="font-medium">Answer</span>{" "}
            adds your real experience, <span className="font-medium">Attach project</span>{" "}
            points to a project on your resume, and <span className="font-medium">Skip</span>{" "}
            leaves a gap as it is. <span className="font-medium">I can&apos;t confirm this</span>{" "}
            means you don&apos;t have it, and we won&apos;t ask again.
          </p>
        )}
        {categories.map((category) => (
          <CategorySection
            key={category.key}
            category={category}
            resolutions={resolutions}
            resolutionMap={resolutionMap}
            targets={targets}
            projects={projects}
            baseResumeError={baseResume.isError}
            onChange={handleChange}
          />
        ))}
        </GapLocked>

        <section className="space-y-2">
          <Label htmlFor="tailor-instructions" className="font-medium" optional>
            Tailoring notes
          </Label>
          <p id={notesHintId} className="text-muted-foreground text-xs">
            What to stress, or limits like page count.
          </p>
          <Textarea
            id="tailor-instructions"
            value={userPrompt}
            readOnly={tailorBusy}
            onChange={(event) => handlePromptChange(event.target.value)}
            aria-describedby={notesHintId}
            rows={3}
          />
        </section>
      </div>

      <div className="bg-background/95 sticky bottom-0 z-10 -mx-6 mt-auto border-t px-6 py-3 backdrop-blur">
        {/* Wraps at narrow widths: the counts keep one line, and the actions
            drop below them instead of squeezing the counts into a column. */}
        <div className="mx-auto flex w-full max-w-4xl flex-wrap items-center gap-x-3 gap-y-2">
          <p className="text-muted-foreground shrink-0 text-sm whitespace-nowrap tabular-nums">
            <span className="text-foreground font-medium">{addressed}</span> answered
            · <span className="text-foreground font-medium">{skipped}</span> skipped ·{" "}
            <span className="text-foreground font-medium">{open}</span> open
          </p>
          <div className="ml-auto flex flex-wrap items-center justify-end gap-3">
            <SaveIndicator state={saveState} onRetry={staleReason ? undefined : saveNow} />
            {addressed === 0 && (
              <Button
                variant="outline"
                onClick={async () => {
                  // Reuse policy makes from-base overwrite the job's newest
                  // application for this base — never clobber a tailored
                  // draft silently (review finding).
                  const existing = jobDetail.data?.application;
                  if (existing?.customized_json) {
                    const ok = await confirm({
                      title: "Replace the existing tailored draft?",
                      description:
                        "Using your base resume as is replaces this job's tailored resume and removes its PDF. " +
                        "Version history keeps the old one.",
                      confirmLabel: "Replace draft",
                      destructive: true,
                    });
                    if (!ok) return;
                  }
                  applyAsIsOnce();
                }}
                // Focusable while it runs: a natively disabled button dropped focus to <body>.
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                focusableWhenDisabled
                disabled={useAsIs.isPending || tailorBusy || !!staleReason}
              >
                {useAsIs.isPending && <Loader2 className="animate-spin" />}
                Use resume as is
              </Button>
            )}
            {open > 0 && (
              <Button
                variant="outline"
                className="data-disabled:opacity-50"
                onClick={onQuickTailorClick}
                focusableWhenDisabled
                disabled={tailorBusy || useAsIs.isPending || !!staleReason}
                title="Fill open gaps from your Quick tailor settings, then tailor"
              >
                <Zap />
                Quick tailor
              </Button>
            )}
            {/* Focusable while disabled: the confirm hands focus back here as the lock takes it. */}
            <Button
              className="data-disabled:opacity-50"
              onClick={onTailorClick}
              focusableWhenDisabled
              disabled={tailorBusy || useAsIs.isPending || !!staleReason}
            >
              {tailor.isPending ? <Loader2 className="animate-spin" /> : <Wand2 />}
              {tailor.isPending ? "Tailoring… about 30 seconds" : "Tailor resume"}
            </Button>
          </div>
        </div>
      </div>
    </main>
  );
}
