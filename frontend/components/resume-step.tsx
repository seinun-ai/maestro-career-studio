"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { GuardedLink as Link } from "@/components/guarded-link";
import { useRouter } from "next/navigation";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, RefreshCw, Upload } from "lucide-react";
import { toast } from "sonner";

import { AnchorPills } from "@/components/base-resumes/anchor-pills";
import { useConfirm } from "@/components/confirm-dialog";
import { useBaseResumeLabel, useBaseResumes } from "@/hooks/use-base-resume-label";
import { LoadErrorState } from "@/components/load-error-state";
import { UploadDialog } from "@/components/setup/upload-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { ProgressCount, ResumeSwatch, ResumeTag, ScoreBar } from "@/components/visual";
import { useCountUp } from "@/hooks/use-count-up";
import { useSingleFlight } from "@/hooks/use-single-flight";
import {
  ATS_SCORE_LEAD,
  LOW_COVERAGE_ON_EVERY_RESUME,
  SUBSCORE_LABELS,
  UNREADABLE_DATES_NOTE,
  datesUnreadable,
  noResumeForCountry,
  skippedCountriesLine,
} from "@/lib/ats-words";
import { couldnt, loadErrorDetail } from "@/lib/error-text";
import { gapCounts } from "@/lib/gap-counts";
import { countryName } from "@/lib/place-name";
import { isLoadFailure } from "@/lib/query-state";
import { cn } from "@/lib/utils";
import {
  ApiError,
  apiFetch,
  closeTailoringSession,
  createApplicationFromBase,
  createTailoringSession,
  getAtsCandidates,
  listAtsScores,
  listTailoringSessions,
  runAtsScores,
} from "@/lib/api";
import type { Application, AtsScore, BaseResumeSummary, TailoringSession } from "@/lib/types";
import { CONCEPT_ICONS } from "@/lib/concept-icons";

const MoreIcon = CONCEPT_ICONS.more;
const WarningIcon = CONCEPT_ICONS.warning;
const AnalyzeGapsIcon = CONCEPT_ICONS.analyzeGaps;

/** How many chips show before "N more": the design's top 3 by score. */
const CHIPS_SHOWN = 3;

/** "Match score" spelled out once, where step 2 first shows one (conventions: Canonical terms). */
function AtsScoreLead() {
  return (
    <p className="text-muted-foreground max-w-[60ch] text-body-medium">
      {ATS_SCORE_LEAD}
    </p>
  );
}

/** The server's low-coverage sentence, on the row or (older rows) inside its subscores. */
function coverageWarning(score: AtsScore): string | null {
  return score.coverage_warning || score.subscores_json?.coverage_warning || null;
}

/** One subscore as a meter out of 100: the number sits beside the bar, so no " of 100" is needed. */
function SubscoreBar({ label, value, weakest }: { label: string; value: number; weakest: boolean }) {
  return (
    <div className="space-y-0.5">
      <div className="flex items-center gap-2">
        <span aria-hidden="true" className="text-muted-foreground text-body-small">{label}</span>
        {/* A word only (D4): no colour, no threshold; the arrow icon means Lost elsewhere. */}
        {weakest && (
          <span className="inline-flex h-4 items-center rounded-full bg-surface-container px-1.5 text-label-small">Weakest</span>
        )}
      </div>
      <ScoreBar value={Math.round(value * 100)} max={100} label={label} width="flex-1" className="w-full" />
    </div>
  );
}

/** The index of the lowest value (ties go to the first); -1 when all are equal, since none is weakest. */
function lowestIndex(values: number[]): number {
  if (Math.max(...values) === Math.min(...values)) return -1;
  return values.reduce((low, v, i) => (v < values[low] ? i : low), 0);
}

/** One chip: a base resume, its colour, its Match score. */
export type ResumeChipOption = {
  slug: string;
  name: string;
  score: number;
  hue: number | null | undefined;
};

/**
 * The base resumes as a row of chips, one picked (step 2 of the job page; the gap page mounts it too). A radio
 * group: each chip is a label over a visually hidden radio, so arrow keys move the pick and the radio says it is
 * checked. Picked reads `secondary-container` with a leading Check (design system: selected in a set). Sorted by
 * score; the top 3 show, then "N more" reveals the rest. The picked chip always shows, even past the top 3.
 * `actions` sits at the row's right end (step 2's ⋯).
 */
export function ResumeChips({
  resumes,
  picked,
  onPick,
  best,
  disabled = false,
  actions,
}: {
  resumes: readonly ResumeChipOption[];
  picked: string | null;
  onPick: (slug: string) => void;
  /** The best match's slug: its chip wears Best. */
  best: string | null;
  disabled?: boolean;
  actions?: ReactNode;
}) {
  const name = useId();
  const [expanded, setExpanded] = useState(false);
  const sorted = [...resumes].sort((a, b) => b.score - a.score);
  const shown = expanded
    ? sorted
    : sorted.filter((r, i) => i < CHIPS_SHOWN || r.slug === picked);
  const hidden = sorted.length - shown.length;
  return (
    <div className="flex items-start gap-2">
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
        <div role="radiogroup" aria-label="Base resume" className="flex min-w-0 flex-wrap items-center gap-2">
          {shown.map((r) => {
            const on = r.slug === picked;
            const isBest = r.slug === best;
            const score = r.score.toFixed(1);
            return (
              <label
                key={r.slug}
                title={r.name}
                className={cn(
                  "inline-flex h-8 min-w-0 cursor-pointer items-center gap-1.5 rounded-full border px-3 text-label-large whitespace-nowrap transition-colors duration-(--duration-short3) has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring",
                  on
                    ? "border-transparent bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"
                    : "border-border hover:bg-surface-container",
                  disabled && "pointer-events-none opacity-50",
                )}
              >
                <input
                  type="radio"
                  name={name}
                  value={r.slug}
                  checked={on}
                  disabled={disabled}
                  onChange={() => onPick(r.slug)}
                  aria-label={`${r.name}, Match score ${score}${isBest ? ", best" : ""}`}
                  className="sr-only"
                />
                {on && <Check className="size-3.5 shrink-0" aria-hidden="true" />}
                <ResumeSwatch hue={r.hue} />
                <span aria-hidden="true" className="max-w-48 min-w-0 truncate">{r.name}</span>
                <span aria-hidden="true" className="tabular-nums">{score}</span>
                {isBest && <Badge aria-hidden="true">Best</Badge>}
              </label>
            );
          })}
        </div>
        {hidden > 0 || expanded ? (
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-8 px-1"
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "Show fewer" : `${hidden} more`}
          </Button>
        ) : null}
      </div>
      {actions}
    </div>
  );
}

/**
 * The picked resume's score in one line, with the breakdown behind a popover: the subscores, the skills
 * covered, its Target pills, the dates note and its own warnings (shared ones sit above the chips).
 */
function ScoreSummary({
  score,
  resume,
  name,
  showCoverage,
  sharedWarnings,
}: {
  score: AtsScore;
  resume: BaseResumeSummary | undefined;
  name: string;
  /** False when the banner already says every resume shows too few of the job's skills. */
  showCoverage: boolean;
  /** Gate warnings every resume carries: the banner says them once, so the popover leaves them out. */
  sharedWarnings: Set<string>;
}) {
  const [open, setOpen] = useState(false);
  const shownScore = useCountUp(score.composite);
  const subscoreValues = SUBSCORE_LABELS.map(({ key }) => score.subscores_json[key] ?? 0);
  const weakestAt = lowestIndex(subscoreValues);
  const extracted = score.jd_skills_extracted_count ?? 0;
  const matched = score.jd_skills_matched_count ?? 0;
  const gateWarnings = (score.subscores_json.gate_warnings ?? []).filter((w) => !sharedWarnings.has(w));
  const coverage = showCoverage ? coverageWarning(score) : null;
  return (
    <div className="bg-surface-container-low flex flex-wrap items-center gap-x-6 gap-y-1 rounded-corner-md px-4 py-2">
      <div className="text-headline-small tabular-nums">
        {shownScore.toFixed(1)}
        <span className="text-muted-foreground text-body-medium"> / 100</span>
      </div>
      {extracted > 0 && (
        <p className="text-body-medium">
          <span className="text-muted-foreground">Skills covered</span>{" "}
          <span className="tabular-nums">{matched} of {extracted}</span>
        </p>
      )}
      {weakestAt >= 0 && (
        <p className="text-body-medium">
          <span className="text-muted-foreground">Weakest</span> {SUBSCORE_LABELS[weakestAt].label}
        </p>
      )}
      {/* The details of one resume's score, anchored to its button: a panel, not a dialog. */}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          render={
            <Button type="button" variant="link" size="sm" className="ml-auto h-auto px-0" aria-expanded={open}>
              Score breakdown
            </Button>
          }
        />
        <PopoverContent align="end" className="w-80 space-y-3 shadow-level2">
          <div className="grid gap-1">
            <PopoverTitle>
              <ResumeTag hue={resume?.color_hue} className="max-w-full">
                <span className="min-w-0 truncate" title={name}>{name}</span>
              </ResumeTag>
            </PopoverTitle>
            {resume && <AnchorPills resume={resume} />}
          </div>
          <div className="grid gap-y-1.5">
            {SUBSCORE_LABELS.map(({ key, label }, i) => (
              <SubscoreBar key={key} label={label} value={subscoreValues[i]} weakest={i === weakestAt} />
            ))}
          </div>
          {extracted > 0 && (
            <div className="space-y-0.5">
              <span className="text-muted-foreground text-body-small">Skills covered</span>
              <ScoreBar
                value={matched}
                max={extracted}
                label="Skills covered"
                valueText={`${matched} of ${extracted}`}
                width="flex-1"
                className="w-full"
              />
            </div>
          )}
          {datesUnreadable(score.subscores_json.format_flags) && (
            <p className="text-muted-foreground text-body-small">{UNREADABLE_DATES_NOTE}</p>
          )}
          {(gateWarnings.length > 0 || coverage) && (
            <ul className="space-y-1 text-body-small">
              {gateWarnings.map((warning) => (
                <li key={warning} className="text-warning flex gap-1.5">
                  <WarningIcon className="mt-px size-3.5 shrink-0" aria-hidden="true" />
                  {warning}
                </li>
              ))}
              {coverage && (
                <li className="text-warning flex gap-1.5">
                  <WarningIcon className="mt-px size-3.5 shrink-0" aria-hidden="true" />
                  {/* The server's sentence already gives the counts ("Your resume shows only 1 of this job's 8 skills (13%)."). */}
                  {coverage}
                </li>
              )}
            </ul>
          )}
        </PopoverContent>
      </Popover>
    </div>
  );
}

/**
 * Step 2 of the job page, Resume and gaps: pick a base resume, see its Match score in one line, and analyze its
 * gaps (or continue the open gap analysis). Scores on the first visit when no base score shows (fast, no LLM);
 * Analyze gaps creates a gap analysis (an LLM pass) and opens it. The rare actions sit behind ⋯. A job has one
 * application, so switching the resume after tailoring confirms first: tailoring another replaces the draft.
 */
export function ResumeStep({
  jobId,
  application,
  readOnly = false,
  onUsedAsIs,
}: {
  jobId: string;
  /** The job's application, or null with none: its status hides Mark applied, its draft guards a switch. */
  application: Application | null;
  readOnly?: boolean;
  /** Use resume as is made the job's resume: the page opens step 3. */
  onUsedAsIs?: () => void;
}) {
  const applicationStatus = application?.status ?? null;
  const applied = applicationStatus != null && applicationStatus !== "draft";
  const baseName = useBaseResumeLabel();
  const qc = useQueryClient();
  const router = useRouter();
  const confirm = useConfirm();

  // "Score them anyway" switches this view to every resume, those set for other countries too. The
  // flag is in the key, under the ["ats-scores", jobId] prefix every invalidation names.
  const [includeOtherCountries, setIncludeOtherCountries] = useState(false);
  const scores = useQuery({
    queryKey: ["ats-scores", jobId, { includeOtherCountries }],
    queryFn: () => listAtsScores(jobId, { includeOtherCountries }),
    // The chips stay while the switched list loads (conventions: a source switch keeps its rows).
    placeholderData: keepPreviousData,
  });
  // Which resumes the job's country left out. Enrichment only: a failure shows no line.
  const candidates = useQuery({
    queryKey: ["ats-scores", jobId, "candidates"],
    queryFn: () => getAtsCandidates(jobId),
  });
  const jobCountry = candidates.data?.job_country ?? null;
  // Once they are scored anyway, the line would be untrue.
  const skipped = includeOtherCountries ? [] : (candidates.data?.skipped ?? []);

  // The engine scores every SELECTABLE base resume, the same set
  // GET /api/base-resumes returns. With none, "Score my resumes" can only
  // return an empty list again, so the empty state offers the import instead.
  const bases = useBaseResumes();
  const noBases = bases.isSuccess && bases.data.length === 0;
  const baseCount = bases.data?.length ?? 0;
  // The archived-inclusive list, the one `baseName` reads: a score can outlive its resume's archiving.
  const { data: allResumes } = useBaseResumes(true);
  const [importOpen, setImportOpen] = useState(false);
  // Where focus goes when the import dialog closes: back to its opener while it
  // is still there (the prompt's button, else ⋯ when the menu opened it), else
  // this wrapper, since an import swaps the prompt for the skeleton and the
  // button is gone.
  const rootRef = useRef<HTMLDivElement>(null);
  const importButtonRef = useRef<HTMLButtonElement>(null);
  const moreRef = useRef<HTMLButtonElement>(null);
  const importFinalFocus = () => {
    const opener = importButtonRef.current ?? moreRef.current;
    return opener?.isConnected ? opener : rootRef.current;
  };

  // Open gap analyses let the picked resume offer "Continue gap analysis". On
  // loading/error this stays empty, so the body falls back to Analyze gaps.
  const sessions = useQuery({
    queryKey: ["tailoring-sessions", jobId],
    queryFn: () => listTailoringSessions(jobId),
  });

  // Newest OPEN session per base resume (created_at desc; ISO strings sort lexically).
  const openSessionByBase = new Map<string, TailoringSession>();
  let newestOpen: TailoringSession | null = null;
  for (const s of sessions.data ?? []) {
    if (s.status !== "open") continue;
    const existing = openSessionByBase.get(s.base_resume);
    if (!existing || s.created_at > existing.created_at) {
      openSessionByBase.set(s.base_resume, s);
    }
    if (!newestOpen || s.created_at > newestOpen.created_at) newestOpen = s;
  }

  // The variable marks the gesture: "manual" is Update scores, which confirms with a toast (an automatic run
  // does not); "all" is Score them anyway, in the event that switches the view (its state is not read back yet).
  const run = useMutation<Awaited<ReturnType<typeof runAtsScores>>, Error, "manual" | "all" | void>({
    mutationFn: (gesture) =>
      runAtsScores(jobId, { includeOtherCountries: gesture === "all" || includeOtherCountries }),
    // Awaited: the run stays pending until the list has refetched, so the
    // skeleton hands straight to the chips with no empty-state frame.
    onSuccess: async (_result, manual) => {
      await qc.invalidateQueries({ queryKey: ["ats-scores", jobId] });
      if (manual === "manual") toast.success("Match scores updated");
    },
    onError: (err: Error) => toast.error(couldnt("score your resumes", err)),
  });
  // One run per gesture, and one at a time: a double click on Update scores sent a second POST that
  // collided with the first on the base-score key and toasted a failure after the success.
  const runOnce = useSingleFlight(run.mutate);

  // A ⋯ item: the menu closes onto ⋯, which stays, so focus has somewhere to be while the view switches.
  const scoreOtherCountries = () => {
    setIncludeOtherCountries(true);
    runOnce("all");
  };

  const createSession = useMutation({
    mutationFn: (baseResume: string) => createTailoringSession(jobId, baseResume),
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ["tailoring-sessions", jobId] });
      if (session.health_warning) {
        toast.warning(session.health_warning, { duration: 8000 });
      }
      router.push(`/jobs/${jobId}/tailor/${session.id}`);
    },
    onError: (err: Error) => toast.error(couldnt("start the gap analysis", err)),
  });
  // A double click on Analyze gaps started two gap analyses.
  const createOnce = useSingleFlight(createSession.mutate);

  // "Use resume as is": the job's resume is the base, unchanged (a perfect fit, or nothing worth tailoring).
  // The gap page's own path: from-base, then close the open gap analysis, best-effort (the application exists).
  const asIs = useMutation({
    mutationFn: async ({ baseResume, sessionId }: { baseResume: string; sessionId: string | null }) => {
      const app = await createApplicationFromBase(jobId, baseResume, []);
      if (sessionId) {
        try {
          await closeTailoringSession(sessionId);
        } catch (error) {
          console.warn("Failed to close the gap analysis after using the base resume as is", error);
        }
      }
      return app;
    },
    onSuccess: async () => {
      qc.invalidateQueries({ queryKey: ["ats-scores", jobId] });
      qc.invalidateQueries({ queryKey: ["tailoring-sessions", jobId] });
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      // Awaited: step 3 opens on the application, never on "Nothing tailored yet".
      await qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      toast.success("Application created from your base resume");
      onUsedAsIs?.();
    },
    onError: (err: Error) => toast.error(couldnt("use your resume as is", err)),
  });
  // A double click made two applications for one job: both POSTs found none to reuse.
  const asIsOnce = useSingleFlight(asIs.mutate);

  const asIsClick = async (baseResume: string, sessionId: string | null) => {
    // From-base replaces the job's draft, whatever its base: never clobber a tailored draft silently.
    if (application?.customized_json) {
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
    asIsOnce({ baseResume, sessionId });
  };

  // "Mark applied without tailoring": the user override for skipping tailoring
  // entirely (applied off-platform with the untouched base). One action:
  // from-base application (reuse policy updates the job's newest app for that
  // base — replaces any tailored draft, version history keeps it) + status
  // applied, which also auto-closes any open proposal on the job server-side.
  const appliedAsIs = useMutation({
    mutationFn: async (baseResume: string) => {
      const app = await createApplicationFromBase(jobId, baseResume);
      await apiFetch(`/api/applications/${app.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "applied" }),
      });
    },
    onSuccess: () => {
      toast.success("Marked as applied");
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["jobs", "without-application"] });
      qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      qc.invalidateQueries({ queryKey: ["proposals"] });
    },
    onError: (err: Error) => toast.error(couldnt("mark the job applied", err)),
  });
  const markAppliedOnce = useSingleFlight(appliedAsIs.mutate);

  const appliedAsIsClick = async (baseResume: string) => {
    const ok = await confirm({
      title: "Mark as applied without tailoring?",
      description:
        `This marks the job Applied with ${baseName(baseResume)}, unchanged. ` +
        "It replaces any tailored draft (Version history keeps it) " +
        "and closes any open proposal in your Agent inbox for this job.",
      confirmLabel: "Mark applied",
      // The item is gone once the menu closes: the confirm returns to ⋯.
      returnFocus: () => moreRef.current,
    });
    if (ok) markAppliedOnce(baseResume);
  };

  const baseRows = (scores.data ?? [])
    .filter((s) => s.phase === "base")
    .sort((a, b) => b.composite - a.composite);

  // The picked resume: the reader's own pick, else the newest open gap analysis's, else the application's,
  // else the best match. A pick the list no longer holds (scored away by a country switch) falls back too.
  const [chosen, setChosen] = useState<string | null>(null);
  const has = (slug: string | null | undefined): slug is string =>
    slug != null && baseRows.some((row) => row.target_id === slug);
  const picked = has(chosen)
    ? chosen
    : has(newestOpen?.base_resume)
      ? newestOpen.base_resume
      : has(application?.base_resume)
        ? application.base_resume
        : (baseRows[0]?.target_id ?? null);

  // Switching after tailoring: a job has one application, so tailoring another resume replaces its draft.
  // The pick is controlled: until the confirm says yes, the chip stays where it was.
  const pick = async (slug: string) => {
    if (slug === picked) return;
    const draftBase = application?.customized_json ? application.base_resume : null;
    if (readOnly || draftBase == null || draftBase === slug) {
      setChosen(slug);
      return;
    }
    const ok = await confirm({
      title: `Switch to ${baseName(slug)}?`,
      description:
        `This job already has a tailored ${baseName(draftBase)} resume. ` +
        "Tailoring with another resume replaces that draft and removes its PDF. Version history keeps the old one. " +
        `Answers you gave in the gaps for ${baseName(draftBase)} stay with it.`,
      confirmLabel: "Switch and analyze gaps",
      destructive: true,
    });
    if (!ok) return;
    setChosen(slug);
    // An open gap analysis for that resume keeps its answers: open it rather than start one that replaces it.
    const open = openSessionByBase.get(slug);
    if (open) router.push(`/jobs/${jobId}/tailor/${open.id}`);
    else createOnce(slug);
  };

  // First visit: no base score to show yet — run the (fast, deterministic) engine once. Counted on the
  // BASE rows the read returns, not every row: an application's tailored score is no chip, and a base
  // scored before it was set for another country is hidden, so either alone left the empty state with
  // no run (the bases set for the job's country were never scored).
  const autoRan = useRef(false);
  const noBaseRows = scores.isSuccess && baseRows.length === 0;
  useEffect(() => {
    if (readOnly) return;
    if (noBaseRows && !autoRan.current) {
      autoRan.current = true;
      runOnce();
    }
  }, [noBaseRows, runOnce, readOnly]);

  // A resume imported from the prompt below lands in ["base-resumes"] (the
  // import dialog invalidates it). Score against it once the dialog closes,
  // but only on a CONFIRMED none -> some transition, never on the first load.
  // - Arm only on a SETTLED empty list: a cached `[]` from an earlier visit
  //   still reads as empty while its refetch is in flight, and if the refetch
  //   returns resumes this would score a second time, racing the first-visit
  //   auto-run above (two concurrent runs collide on the base-score unique key
  //   and toast an error).
  // - Never fire while a run is in flight, for the same reason.
  // - Wait for the dialog to close: scoring swaps the prompt for a skeleton,
  //   which would unmount the dialog mid-report, before the user has
  //   confirmed each new resume's target role.
  const sawNoBases = useRef(false);
  useEffect(() => {
    if (readOnly) return;
    if (noBases && !bases.isFetching) {
      sawNoBases.current = true;
    } else if (sawNoBases.current && baseCount > 0 && !importOpen && !run.isPending) {
      sawNoBases.current = false;
      runOnce();
    }
  }, [noBases, bases.isFetching, baseCount, importOpen, run.isPending, runOnce, readOnly]);

  // Score the imported resumes in the SAME event as the close: mutate() marks
  // the run pending synchronously, and the render that drops the prompt reads
  // it through useSyncExternalStore, so it paints the skeleton, never the
  // empty state. The effect above stays as the fallback for a base
  // list that lands after the dialog closed.
  // The resume count when the dialog opened, for the rescore after ⋯'s Import (below).
  const basesAtOpen = useRef<number | null>(null);
  const onImportOpenChange = (open: boolean) => {
    setImportOpen(open);
    if (open) basesAtOpen.current = baseCount;
    if (!readOnly && !open && sawNoBases.current && baseCount > 0 && !run.isPending) {
      sawNoBases.current = false;
      basesAtOpen.current = null;
      runOnce();
    }
  };

  // ⋯'s Import, with resumes already scored: a resume it added has no score for this job yet, so score once
  // the dialog has closed and the list has grown (the import invalidates it; the refetch may land after the close).
  useEffect(() => {
    if (readOnly || importOpen || basesAtOpen.current == null || bases.isFetching || run.isPending) return;
    if (baseCount > basesAtOpen.current) runOnce();
    basesAtOpen.current = null;
  }, [readOnly, importOpen, bases.isFetching, baseCount, run.isPending, runOnce]);

  function renderBody() {
    if (isLoadFailure(scores)) {
      return (
        <LoadErrorState
          title="Couldn't load match scores."
          detail={loadErrorDetail(scores.error)}
          retrying={scores.isFetching}
          onRetry={() => void scores.refetch()}
        />
      );
    }

    // Idle with a SETTLED empty list means the first-visit auto-run is about
    // to fire, so the skeleton shows instead of an empty-state frame. A failed
    // refetch keeps its old `[]` in `data`, and the auto-run waits for success,
    // so without `isSuccess` the skeleton would hide the error for good.
    if (
      scores.isLoading ||
      (baseRows.length === 0 &&
        (run.isPending || (!readOnly && run.isIdle && noBaseRows)))
    ) {
      return (
        <Card>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              {Array.from({ length: CHIPS_SHOWN }).map((_, i) => (
                <Skeleton key={i} className="h-8 w-40 rounded-full" />
              ))}
            </div>
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-36 w-full" />
          </CardContent>
        </Card>
      );
    }

    if (baseRows.length === 0) {
      // A 422 means the job itself can't be scored (e.g. no extracted skills) —
      // retrying can't succeed, so show the reason instead of a dead-end button.
      // It is checked first: an import cannot fix a job-level fact either.
      const unscorable =
        run.error instanceof ApiError && run.error.status === 422
          ? couldnt("score this job", run.error)
          : null;
      // `importOpen` keeps the prompt behind the open dialog after the import
      // lands, while its report is still on screen (see the effect above).
      if (!unscorable && (noBases || importOpen)) {
        return (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <p className="text-title-small">No base resumes to score against.</p>
            <p className="text-muted-foreground max-w-[50ch] text-body-medium">
              Import your resumes to score this job against each one.
            </p>
            <Button ref={importButtonRef} size="sm" disabled={readOnly} onClick={() => setImportOpen(true)}>
              Import resumes and documents
            </Button>
          </div>
        );
      }
      return (
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          {!unscorable && <AtsScoreLead />}
          <p className="text-muted-foreground text-body-medium">{unscorable ?? "No match scores yet."}</p>
          {!unscorable && (
            <Button
              size="sm"
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={() => runOnce()}
              focusableWhenDisabled
              disabled={run.isPending || readOnly}
            >
              {run.isPending && <Loader2 className="animate-spin" />}
              {run.isPending ? "Scoring…" : "Score my resumes"}
            </Button>
          )}
        </div>
      );
    }

    // Every resume under the coverage line is a fact about the job, not about one resume: said once, above them.
    const lowCoverageEverywhere =
      baseRows.length > 1 && baseRows.every((row) => coverageWarning(row) != null);

    // Gate warnings every resume carries are a fact about the job, said once above the chips.
    const sharedWarnings = new Set<string>(
      baseRows.length > 1
        ? (baseRows[0].subscores_json.gate_warnings ?? []).filter((w) =>
            baseRows.every((row) => row.subscores_json.gate_warnings?.includes(w)),
          )
        : [],
    );

    const pickedRow = baseRows.find((row) => row.target_id === picked) ?? baseRows[0];
    const pickedSlug = pickedRow.target_id;
    const pickedName = baseName(pickedSlug);
    const openSession = openSessionByBase.get(pickedSlug) ?? null;
    const creating = createSession.isPending && createSession.variables === pickedSlug;
    const busy = createSession.isPending || asIs.isPending;
    // The gap page's own counts: stored resolutions include skips and gaps it no longer lists.
    const { answered, total: totalGaps } = openSession
      ? gapCounts(
          openSession.gaps_json.categories.flatMap((c) => c.gaps.map((g) => g.gap_id)),
          openSession.resolutions_json,
        )
      : { answered: 0, total: 0 };
    // The job's resume came from this one (tailored, or used as is): "no gap analysis yet" would be untrue.
    const pickedIsTheJobs = Boolean(application?.customized_json) && application?.base_resume === pickedSlug;
    const chips = baseRows.map((row) => ({
      slug: row.target_id,
      name: baseName(row.target_id),
      score: row.composite,
      hue: allResumes?.find((r) => r.slug === row.target_id)?.color_hue,
    }));

    const asIsButton = (sessionId: string | null) => (
      <Button
        variant="outline"
        onClick={() => void asIsClick(pickedSlug, sessionId)}
        // Focusable while it runs: a natively disabled button dropped focus to <body>.
        focusableWhenDisabled
        pending={asIs.isPending}
        disabled={busy || readOnly}
      >
        Use resume as is
      </Button>
    );

    return (
      <div className="space-y-3">
        {lowCoverageEverywhere && (
          <div className="flex gap-2 rounded-corner-md bg-warning-container p-2 text-body-medium text-on-warning-container">
            <WarningIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <p>{LOW_COVERAGE_ON_EVERY_RESUME}</p>
          </div>
        )}
        {sharedWarnings.size > 0 && (
          <div className="flex gap-2 rounded-corner-md bg-warning-container p-2 text-body-medium text-on-warning-container">
            <WarningIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <ul className="space-y-1">
              {[...sharedWarnings].map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        )}
        <Card data-pending={run.isPending ? "true" : undefined}>
          <CardContent className="space-y-4">
            <AtsScoreLead />
            <div className="space-y-1.5">
              <ResumeChips
                resumes={chips}
                picked={pickedSlug}
                onPick={(slug) => void pick(slug)}
                best={baseRows[0].target_id}
                disabled={busy}
                actions={
                  <div className="flex h-8 shrink-0 items-center gap-2">
                    {run.isPending && (
                      <span role="status" className="text-muted-foreground inline-flex items-center gap-1.5 text-body-small">
                        <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                        Updating scores…
                      </span>
                    )}
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        render={
                          <Button ref={moreRef} size="icon-sm" variant="ghost" aria-label="More actions for resumes">
                            <MoreIcon />
                          </Button>
                        }
                      />
                      <DropdownMenuContent align="end" className="w-auto min-w-56">
                        <DropdownMenuItem disabled={run.isPending || readOnly} onClick={() => runOnce("manual")}>
                          <RefreshCw />
                          {run.isPending ? "Updating scores…" : "Update scores"}
                        </DropdownMenuItem>
                        {jobCountry && skipped.length > 0 && (
                          // A run in flight would drop this one (one at a time), and the view would switch unscored.
                          <DropdownMenuItem disabled={run.isPending || readOnly} onClick={scoreOtherCountries}>
                            <RefreshCw />
                            Score them anyway
                          </DropdownMenuItem>
                        )}
                        {applied ? null : (
                          <DropdownMenuItem
                            disabled={readOnly || appliedAsIs.isPending}
                            onClick={() => void appliedAsIsClick(pickedSlug)}
                          >
                            <Check /> Mark applied without tailoring
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuSeparator />
                        <DropdownMenuItem disabled={readOnly} onClick={() => onImportOpenChange(true)}>
                          <Upload /> Import resumes and documents
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                }
              />
              {jobCountry && skipped.length > 0 && (
                <p className="text-body-small text-muted-foreground">
                  {skippedCountriesLine(skipped.length, countryName(jobCountry))}
                </p>
              )}
              {jobCountry && candidates.data?.fallback && (
                <p className="text-body-small text-muted-foreground">
                  {noResumeForCountry(countryName(jobCountry))}
                </p>
              )}
            </div>
            <ScoreSummary
              key={pickedSlug}
              score={pickedRow}
              resume={allResumes?.find((r) => r.slug === pickedSlug)}
              name={pickedName}
              showCoverage={!lowCoverageEverywhere}
              sharedWarnings={sharedWarnings}
            />
            {openSession && !creating ? (
              <div className="flex flex-wrap items-center gap-3 rounded-corner-md border p-4">
                {totalGaps > 0 && <ProgressCount done={answered} total={totalGaps} noun="answered" />}
                <div className="ml-auto flex flex-wrap items-center gap-2">
                  {answered === 0 && asIsButton(openSession.id)}
                  <Button
                    disabled={readOnly}
                    aria-disabled={readOnly || undefined}
                    nativeButton={false}
                    render={
                      <Link href={`/jobs/${jobId}/tailor/${openSession.id}`}>
                        Continue gap analysis
                      </Link>
                    }
                  />
                </div>
              </div>
            ) : (
              <div className="space-y-3 rounded-corner-md border border-dashed p-4">
                <p className="text-title-small">
                  {pickedIsTheJobs ? `${pickedName} is this job's resume` : `No gap analysis for ${pickedName} yet`}
                </p>
                <p className="text-muted-foreground max-w-[70ch] text-body-medium">
                  Analyze gaps finds the skills this job asks for that the resume does not show. It fills what your
                  career history can answer and asks you about the rest. About 10 seconds. It opens on its own page,
                  with these steps on top.
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    onClick={() => createOnce(pickedSlug)}
                    // Focusable while it starts: a natively disabled button dropped focus to <body>.
                    focusableWhenDisabled
                    pending={creating}
                    disabled={busy || readOnly}
                  >
                    {creating ? null : <AnalyzeGapsIcon />}
                    {creating ? "Analyzing gaps…" : "Analyze gaps"}
                  </Button>
                  {asIsButton(null)}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div ref={rootRef} tabIndex={-1} className="outline-none">
      {renderBody()}
      <UploadDialog
        open={importOpen}
        onOpenChange={onImportOpenChange}
        finalFocus={importFinalFocus}
      />
    </div>
  );
}
