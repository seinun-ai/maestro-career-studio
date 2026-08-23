"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
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
  type PlacementTarget,
} from "@/components/gap-analysis/resolution-controls";
import { IconButton } from "@/components/icon-button";
import { useConfirm } from "@/components/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
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
  type BaseResumeDetail,
  type GapCategory,
  type JobDetail,
  type Resolution,
} from "@/lib/types";

type SaveState = "idle" | "saving" | "saved" | "error";

function SaveIndicator({ state }: { state: SaveState }) {
  if (state === "idle") return null;
  return (
    <span
      className={cn(
        "flex items-center gap-1 text-xs",
        state === "error" ? "text-destructive" : "text-muted-foreground",
      )}
      aria-live="polite"
    >
      {state === "saving" && <Loader2 className="size-3 animate-spin" />}
      {state === "saving" ? "Saving…" : state === "saved" ? "Saved" : "Save failed"}
    </span>
  );
}

function CategorySection({
  category,
  resolutionMap,
  targets,
  projects,
  baseResumeError,
  onChange,
}: {
  category: GapCategory;
  resolutionMap: Map<string, Resolution>;
  targets: PlacementTarget[] | null;
  projects: string[] | null;
  baseResumeError: boolean;
  onChange: (gapId: string, resolution: Resolution | null) => void;
}) {
  const [open, setOpen] = useState(true);
  const done = category.gaps.filter((gap) => resolutionMap.has(gap.gap_id)).length;
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
        <Badge variant={done === category.gaps.length ? "default" : "secondary"}>
          {done}/{category.gaps.length}
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
  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  const saveNow = async (): Promise<boolean> => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    // A stale session rejects every save (409); flushing would only spam a
    // misleading toast. The user must Start Over — nothing to save here.
    if (staleReason) return true;
    if (latestRef.current === null && promptRef.current === null) return true; // nothing edited yet
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
      setSaveState("saved");
      return true;
    } catch (error) {
      setSaveState("error");
      if (error instanceof ApiError && error.status === 409) {
        // Surface the SERVER detail (e.g. "This gap analysis is stale — …")
        // rather than a hardcoded "no longer open" — the session may well be
        // open, just stale. Invalidating refreshes stale_reason so the stale
        // banner appears and future autosaves bail out (see saveNow's guard).
        toast.error(error.message);
        void qc.invalidateQueries({ queryKey: ["tailoring-session", sessionId] });
      } else {
        toast.error(
          error instanceof Error ? error.message : "Failed to save resolutions",
        );
      }
      return false;
    }
  };

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
          `ATS score: ${base.composite.toFixed(1)} → ${tailored.composite.toFixed(1)} (${sign}${delta.composite.toFixed(1)})`,
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
          `${skips.length} ${skips.length === 1 ? "answer was" : "answers were"} not saved to your Career KB`,
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
        toast.error("This session is no longer open. Refreshing.");
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
          "Your quick-tailor defaults had nothing they were allowed to add here. " +
            "Answer a gap yourself, or use the base resume as-is.",
        );
        return;
      }
      toast.error(error.message);
    },
  });

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
    if (timerRef.current) clearTimeout(timerRef.current);
    // No autosave while tailoring (the pre-tailor flush already ran, and a PATCH
    // landing after the tailor commits would 409) or while stale (every save
    // 409s — the user must Start Over).
    if (!tailor.isPending && !staleReason) {
      timerRef.current = setTimeout(() => {
        void saveNow();
      }, 800);
    }
  };

  const handlePromptChange = (value: string) => {
    promptRef.current = value;
    setPromptDraft(value);
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!tailor.isPending && !staleReason) {
      timerRef.current = setTimeout(() => {
        void saveNow();
      }, 800);
    }
  };

  // --- Use base resume as-is (perfect-fit / nothing-to-tailor escape hatch) ----
  const useAsIs = useMutation({
    mutationFn: async () => {
      const data = session.data;
      if (!data) throw new Error("Session not loaded");
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
    onError: (error: Error) => toast.error(error.message),
  });

  // --- Stale session: frozen gaps no longer match the current base/JD ---------
  // (`staleReason` is declared above so the autosave path can read it.)
  const startOver = useMutation({
    mutationFn: () => {
      const data = session.data;
      if (!data) throw new Error("Session not loaded");
      return createTailoringSession(jobId, data.base_resume);
    },
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["tailoring-sessions", jobId] });
      router.replace(`/jobs/${jobId}/tailor/${created.id}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  // --- Derived counts ---------------------------------------------------------
  const categories = session.data?.gaps_json.categories ?? [];
  const gaps = categories.flatMap((category) => category.gaps);
  const resolutionMap = new Map(resolutions.map((r) => [r.gap_id, r] as const));
  let addressed = 0;
  let skipped = 0;
  for (const gap of gaps) {
    const resolution = resolutionMap.get(gap.gap_id);
    if (!resolution) continue;
    // cannot_confirm is a skip for the DOCUMENT (its KB record is durable):
    // it must not count as "addressed" or Tailor would run with nothing to do.
    if (resolution.action === "skip" || resolution.action === "cannot_confirm") {
      skipped += 1;
    } else addressed += 1;
  }
  const total = gaps.length;
  const open = total - addressed - skipped;
  // Gaps the KB resolver solved from the user's own evidence and pre-applied.
  // Counted off the LIVE list, so an Undo drops the banner's count immediately.
  const autoResolved = resolutions.filter(isAutoResolved).length;
  // F6d — a summary gap is ALWAYS present, so `total === 0` no longer means "clean".
  // "Strong match" is when the only gap left is that always-present summary (no skill,
  // coverage, title, gate, or format gaps) — surface an honest positive state instead
  // of a misleading "no gaps found", while still letting the user tailor.
  const substantiveGaps = gaps.filter((gap) => gap.kind !== "summary");
  const strongMatch = substantiveGaps.length === 0;
  const hasSummaryGap = gaps.some((gap) => gap.kind === "summary");

  const onTailorClick = async () => {
    if (!session.data) return;
    if (addressed === 0) {
      toast.error(
        "Resolve at least one gap first. Skips alone give the tailor nothing to do.",
      );
      return;
    }
    if (open > 0) {
      const ok = await confirm({
        title: `${open} ${open === 1 ? "gap is" : "gaps are"} still open`,
        description:
          "Open gaps are left as-is. The tailored resume reflects only the resolutions you made.",
        confirmLabel: "Tailor anyway",
      });
      if (!ok) return;
    }
    // Flush any pending debounced save so the tailor sees the latest edits.
    const saved = await saveNow();
    if (!saved) return;
    tailor.mutate(undefined);
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
    const ok = await confirm({
      title: `Quick tailor ${open} open ${open === 1 ? "gap" : "gaps"}?`,
      description:
        "Applies your saved quick-tailor defaults to every gap you haven't " +
        "answered, then tailors. Gaps you've already resolved are left exactly " +
        "as they are. Every change is listed with its source in the review step " +
        "afterward, and can be reverted one at a time.",
      confirmLabel: "Quick tailor",
    });
    if (!ok) return;
    const saved = await saveNow();
    if (!saved) return;
    tailor.mutate(true);
  };

  // --- Render branches --------------------------------------------------------
  if (session.isLoading) {
    return (
      <main className="mx-auto w-full max-w-4xl flex-1 space-y-4 p-6">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </main>
    );
  }

  if (session.isError || !session.data) {
    const notFound =
      session.error instanceof ApiError && session.error.status === 404;
    return (
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
        <h1 className="text-lg font-medium">
          {notFound ? "Tailoring session not found" : "Failed to load session"}
        </h1>
        <p className="text-muted-foreground text-sm">
          {notFound
            ? "It may have been deleted along with its job."
            : (session.error instanceof Error ? session.error.message : "Unknown error")}
        </p>
        <div className="flex gap-2">
          {!notFound && (
            <Button variant="outline" onClick={() => session.refetch()}>
              Retry
            </Button>
          )}
          <Button
            nativeButton={false}
            render={<Link href={`/jobs/${jobId}`}>Back to job</Link>}
          />
        </div>
      </main>
    );
  }

  if (session.data.status !== "open") {
    // Sessions can end up here as "tailored" (the normal terminal state),
    // "superseded" (a newer session for the same base resume replaced it —
    // e.g. "Start over"), or "abandoned" (closed without tailoring — e.g.
    // "Use base resume as-is").
    let heading = "This session is already tailored";
    let description = "The tailored resume lives on the job's application.";
    if (session.data.status === "superseded") {
      heading = "This gap analysis was superseded";
      description =
        "A newer session replaced it. Continue from the job's Score & Tailor tab.";
    } else if (session.data.status === "abandoned") {
      heading = "This gap analysis was closed";
      description =
        "Start a fresh analysis anytime from the job's Score & Tailor tab.";
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
            <TriangleAlert className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
            <p className="text-sm">
              This analysis is out of date: {staleReason} since it was created. Saving and tailoring are disabled.
            </p>
          </div>
          <Button
            size="sm"
            className="rounded-full"
            onClick={() => startOver.mutate()}
            disabled={startOver.isPending}
          >
            {startOver.isPending ? "Starting…" : "Start new analysis"}
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
            {baseResumeLabel(session.data.base_resume)} · score before tailoring:{" "}
            <span className="text-foreground font-medium tabular-nums">
              {gapsJson.base_composite.toFixed(1)}
            </span>
            <span className="text-muted-foreground"> / 100</span>
          </p>
        </div>
        <p className="text-muted-foreground mt-1 shrink-0 text-sm tabular-nums">
          <span className="text-foreground font-medium">{addressed}</span> of {total}{" "}
          gaps addressed
        </p>
      </header>

      <div
        className={cn(
          "flex flex-1 flex-col gap-5",
          tailor.isPending && "pointer-events-none opacity-60",
        )}
      >
        {gapsJson.coverage_warning && (
          <div className="border-amber-500/30 bg-amber-500/10 animate-fade-rise flex items-start gap-3 rounded-xl border p-4 text-amber-900 dark:text-amber-200">
            <TriangleAlert className="size-5 shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
            <div className="space-y-1 text-sm">
              <p className="font-medium">{gapsJson.coverage_warning}</p>
              {gapsJson.jd_skills_extracted_count ? (
                <p className="text-xs text-muted-foreground">
                  Only {gapsJson.jd_skills_matched_count ?? 0} of {gapsJson.jd_skills_extracted_count} skills in this posting were recognized ({Math.round((gapsJson.coverage_ratio ?? 0) * 100)}% coverage).
                </p>
              ) : null}
            </div>
          </div>
        )}
        {strongMatch && !gapsJson.coverage_warning && (
          <div className="border-primary/30 bg-primary/5 rounded-xl border p-4">
            <p className="text-foreground text-sm font-medium">Strong match</p>
            <p className="text-muted-foreground text-sm">
              {hasSummaryGap
                ? "This resume already covers the JD well. Sharpen your value proposition in the summary below, then tailor."
                : "This resume already covers the JD well. Tailor as-is."}
            </p>
          </div>
        )}
        {autoResolved > 0 && (
          <div className="border-primary/25 bg-primary/[0.04] animate-fade-rise flex items-center gap-2.5 rounded-xl border px-4 py-3">
            <Library className="text-primary size-4 shrink-0" />
            <p className="text-sm">
              <span className="font-medium">
                {autoResolved} {autoResolved === 1 ? "gap" : "gaps"}
              </span>{" "}
              auto-resolved from your own evidence — review below.
            </p>
          </div>
        )}
        {autoResolved === 0 && !strongMatch && open > 0 && (
          <p className="text-muted-foreground text-sm">
            Nothing here could be resolved automatically — these gaps need your
            judgment. <span className="font-medium">Add keyword</span> places the
            JD&apos;s exact term, <span className="font-medium">Answer</span> feeds
            the tailor your real experience, and{" "}
            <span className="font-medium">Skip</span> leaves a gap as-is.
          </p>
        )}
        {categories.map((category) => (
          <CategorySection
            key={category.key}
            category={category}
            resolutionMap={resolutionMap}
            targets={targets}
            projects={projects}
            baseResumeError={baseResume.isError}
            onChange={handleChange}
          />
        ))}

        <section className="space-y-2">
          <Label htmlFor="tailor-instructions" className="font-medium">
            Anything specific about how this should be tailored?{" "}
            <span className="text-muted-foreground font-normal">(optional)</span>
          </Label>
          <Textarea
            id="tailor-instructions"
            value={userPrompt}
            onChange={(event) => handlePromptChange(event.target.value)}
            placeholder="e.g. emphasize leadership, keep it to one page, lead with the fintech project…"
            rows={3}
          />
        </section>
      </div>

      <div className="bg-background/95 sticky bottom-0 z-10 -mx-6 mt-auto border-t px-6 py-3 backdrop-blur">
        <div className="mx-auto flex w-full max-w-4xl items-center gap-3">
          <p className="text-muted-foreground text-sm tabular-nums">
            <span className="text-foreground font-medium">{addressed}</span> addressed
            · <span className="text-foreground font-medium">{skipped}</span> skipped ·{" "}
            <span className="text-foreground font-medium">{open}</span> open
          </p>
          <div className="ml-auto flex items-center gap-3">
            <SaveIndicator state={saveState} />
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
                        "This job already has a tailored resume draft. Using the base as-is replaces it and removes its rendered PDF. Version history keeps the old draft.",
                      confirmLabel: "Replace draft",
                      destructive: true,
                    });
                    if (!ok) return;
                  }
                  useAsIs.mutate();
                }}
                disabled={useAsIs.isPending || tailor.isPending || !!staleReason}
              >
                {useAsIs.isPending && <Loader2 className="animate-spin" />}
                Use base resume as-is
              </Button>
            )}
            {open > 0 && (
              <Button
                variant="outline"
                onClick={onQuickTailorClick}
                disabled={tailor.isPending || useAsIs.isPending || !!staleReason}
                title="Fill the open gaps from your saved defaults, then tailor"
              >
                <Zap />
                Quick tailor
              </Button>
            )}
            <Button
              onClick={onTailorClick}
              disabled={tailor.isPending || useAsIs.isPending || !!staleReason}
            >
              {tailor.isPending ? <Loader2 className="animate-spin" /> : <Wand2 />}
              {tailor.isPending ? "Tailoring, about 30s" : "Tailor resume"}
            </Button>
          </div>
        </div>
      </div>
    </main>
  );
}
