"use client";

import { useId, useLayoutEffect, useRef, useState, type ReactNode, type Ref, type RefObject } from "react";
import { GuardedLink as Link } from "@/components/guarded-link";
import {
  ATTENTION_BADGE_LABEL,
} from "@/components/attention-zone";
import { useMutation } from "@tanstack/react-query";
import { MoreHorizontal } from "lucide-react";
import { toast } from "sonner";

import { DemonstrateSkillDialog } from "@/components/resume-health/demonstrate-skill-dialog";
import { DisputeBox, type DisputeHandler } from "@/components/resume-health/dispute-box";
import { DiffText, SourceQuote, SuggestionCopyOnly } from "@/components/resume-health/judged-text";
import { WordingChecklist } from "@/components/resume-health/wording-checklist";
import {
  emptyMetricAsk,
  MetricAskInput,
  metricContextFromValue,
  type MetricAskValue,
} from "@/components/resume-health/metric-ask-input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { IconButton } from "@/components/icon-button";
import {
  answerAsk,
  ApiError,
  applyResumeEdits,
  unwaiveGate,
  validateTemplate,
  waiveGate,
} from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { toastContentChanged, toastRewriteError } from "./report-errors";
import {
  answerMatchesFinding,
  bulletEditOp,
  groupNotesByRule,
  isBulletSubjectRule,
  isContentChangedError,
  isMechanicalPunctRule,
  isMetricAsk,
  levelNameOf,
  groupPoints,
  punctFixOps,
  sharedCoaching,
  skillGroupOf,
  splitWordingNotes,
  STALE_APPLY_HINT,
  type StoredAskAnswer,
  textAtLocation,
} from "@/lib/health-report";
import { focusIfDropped, useEditToggle, useFocusOnNextCommit } from "@/hooks/use-focus-return";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { notifyRenderNote } from "@/lib/render-note";
import { cn } from "@/lib/utils";
import type {
  DisputeResult,
  EvidenceLevel,
  LintFinding,
  LintGate,
  ResumeData,
} from "@/lib/types";

type ClassificationOverrideHandler = (
  contentHash: string,
  level: EvidenceLevel | null,
  reason: string,
) => Promise<void>;

// What each rating means, in the user's words; the scorer's names (direct,
// analogue, …) stay the stored values.
const EVIDENCE_LEVELS: { value: EvidenceLevel; label: string }[] = [
  { value: "direct", label: "Shows a result" },
  { value: "analogue", label: "Partial result" },
  { value: "adjacent", label: "Specific, no result" },
  { value: "implied", label: "Vague" },
  { value: "unaddressed", label: "Lists a duty" },
];

export const EVIDENCE_LABELS = Object.fromEntries(
  EVIDENCE_LEVELS.map(({ value, label }) => [value, label]),
) as Record<EvidenceLevel, string>;

export const LOCKED_BTN =
  "disabled:pointer-events-auto aria-disabled:pointer-events-auto";

export type FindingCardShared = {
  data: ResumeData;
  kind: "base" | "application";
  resumeKey: string;
  onApplied: () => void;
  onClassificationChanged?: ClassificationOverrideHandler;
  onReanalyze?: () => void;
  locked?: boolean;
  nScoreable?: number | null;
  hideHow?: boolean;
  storedAnswer?: StoredAskAnswer;
  /** The latest "Not right?" reply for this bullet, kept by the page across re-runs. */
  dispute?: DisputeResult;
  /** This bullet's dispute is the page's latest action: a card mounting now opens on the reply. */
  disputeFresh?: boolean;
  /** The fresh dispute's card landed on its reply, or was collapsed: it is fresh no more. */
  onDisputeSeen?: () => void;
  onDisputed?: DisputeHandler;
};

export type ExpandedFindingChromeProps = {
  ref?: Ref<HTMLDivElement>;
  finding: LintFinding;
  cardClassName: string;
  overflow: ReactNode;
  onCollapse: () => void;
  quote: string | null;
  how?: string | null;
  hideHow?: boolean;
  children: ReactNode;
};

export function ExpandedFindingChrome({
  ref,
  finding,
  cardClassName,
  overflow,
  onCollapse,
  quote,
  how,
  hideHow,
  children,
}: ExpandedFindingChromeProps) {
  return (
    <div ref={ref} className={cn("min-w-0 rounded-md border px-3 py-2", cardClassName)}>
      <div className="flex items-start justify-between gap-2">
        <button
          type="button"
          className="flex min-w-0 flex-1 flex-wrap items-center gap-2 text-left"
          onClick={onCollapse}
          aria-expanded
        >
          {/* A long label ("Harbor Loop Logistics · bullet 3") wraps inside
              the card: at 375 it pushed the page sideways. */}
          <span className="text-muted-foreground min-w-0 text-body-small break-words">
            {finding.label} ·
          </span>
          <LevelChip finding={finding} />
        </button>
        {overflow}
      </div>
      {quote && <SourceQuote text={quote} />}
      {how && !hideHow && (
        <p className="mt-1.5 max-w-[65ch] text-body-medium">{how}</p>
      )}
      {children}
    </div>
  );
}

function ClassificationOverrideDialog({
  finding,
  open,
  onOpenChange,
  onChanged,
}: {
  finding: LintFinding;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChanged?: ClassificationOverrideHandler;
}) {
  const [level, setLevel] = useState<EvidenceLevel | "automatic">(
    finding.classification_level ?? "automatic",
  );
  const [reason, setReason] = useState(
    finding.classification_source === "override"
      ? (finding.classification_reason ?? "")
      : "",
  );
  const reasonId = useId();

  const save = useMutation({
    mutationFn: () =>
      onChanged!(
        finding.content_hash!,
        level === "automatic" ? null : level,
        reason,
      ),
    onSuccess: () => {
      onOpenChange(false);
      toast.success(
        level === "automatic"
          ? "Back to automatic rating"
          : "Rating changed. Report updated.",
      );
    },
    onError: (err: Error) => toast.error(couldnt("change the rating", err)),
  });

  if (!finding.content_hash || !finding.classification_level || !onChanged) {
    return null;
  }

  const currentLabel = EVIDENCE_LABELS[finding.classification_level];
  const selectedLabel =
    level === "automatic" ? "Automatic" : EVIDENCE_LABELS[level];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Correct this rating</DialogTitle>
        </DialogHeader>
        <div className="grid gap-1.5">
          <Select
            value={level}
            onValueChange={(value) =>
              setLevel(value as EvidenceLevel | "automatic")
            }
            disabled={save.isPending}
          >
            <SelectTrigger size="sm" className="w-full" aria-label="Rating">
              <SelectValue>{selectedLabel}</SelectValue>
            </SelectTrigger>
            <SelectContent align="start">
              <SelectItem value="automatic">Automatic</SelectItem>
              {EVIDENCE_LEVELS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-muted-foreground text-body-small">
            Now: {currentLabel}. Saving updates the report.
          </p>
          {level !== "automatic" && (
            <div className="grid gap-1.5 pt-2">
              <Label htmlFor={reasonId} optional>
                Reason
              </Label>
              <Textarea
                id={reasonId}
                rows={2}
                value={reason}
                maxLength={500}
                onChange={(event) => setReason(event.target.value)}
                className="text-body-medium"
                disabled={save.isPending}
              />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={save.isPending}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => save.mutate()}
            disabled={save.isPending}
          >
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FindingOverflow({
  finding,
  onClassificationChanged,
}: {
  finding: LintFinding;
  onClassificationChanged?: ClassificationOverrideHandler;
}) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const canOverride = Boolean(
    finding.content_hash && finding.classification_level && onClassificationChanged,
  );
  if (!canOverride) return null;
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <IconButton
              label="More actions for this issue"
              icon={<MoreHorizontal className="size-4" />}
              size="icon-xs"
            />
          }
        />
        <DropdownMenuContent align="end" className="min-w-48">
          {/* What it is for: the rating the check gave this bullet is wrong,
              and the dialog sets the right one (or back to automatic). */}
          <DropdownMenuItem onClick={() => setDialogOpen(true)}>
            This rating is wrong…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ClassificationOverrideDialog
        finding={finding}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onChanged={onClassificationChanged}
      />
    </>
  );
}

/** Header count chips, worst first, read from `healthCounts` (`gate` is the
 *  failed must-fix checks only, `serious` the failed serious ones). Shared by
 *  the report page and the studio's health link; `one`/`many` keep "1 note",
 *  "3 notes". */
export const COUNT_META: { key: string; one: string; many: string }[] = [
  { key: "gate", one: "must fix", many: "must fix" },
  {
    key: "serious",
    one: "serious problem",
    many: "serious problems",
  },
  {
    key: "critical",
    one: "critical",
    many: "critical",
  },
  {
    key: "ask",
    one: "question",
    many: "questions",
  },
  {
    key: "note",
    one: "note",
    many: "notes",
  },
];

/** "1 question", "3 notes": a count and its noun agree. */
export function countWords(key: string, count: number): string {
  const meta = COUNT_META.find((m) => m.key === key);
  const noun = meta ? (count === 1 ? meta.one : meta.many) : key;
  return `${count} ${noun}`;
}

/** A Fix or Question card's edge. Its kind is said by the action (Review, Answer)
 *  and the question line, so the edge is the neutral one (owner-approved UX change 5). */
const TYPE_CARD: Record<"fix" | "ask", { card: string }> = {
  fix: { card: "border-border" },
  ask: { card: "border-border" },
};

export const GRADE_STYLES: Record<string, string> = {
  A: "bg-success-container text-on-success-container",
  B: "bg-success-container text-on-success-container",
  C: "bg-warning-container text-on-warning-container",
  D: "bg-attention-container text-on-attention-container",
  F: "bg-error-container text-on-error-container",
};

function SuggestionBlock({
  finding,
  currentText,
  suggestion,
  kind,
  resumeKey,
  onApplied,
  onReanalyze,
  locked,
}: {
  finding: LintFinding;
  currentText: string;
  suggestion: string;
  kind: "base" | "application";
  resumeKey: string;
  onApplied: () => void;
  onReanalyze?: () => void;
  locked?: boolean;
}) {
  if (finding.location.section.startsWith("extra:")) {
    return (
      <SuggestionCopyOnly currentText={currentText} suggestion={suggestion} />
    );
  }
  return (
    <SuggestionEditor
      finding={finding}
      currentText={currentText}
      suggestion={suggestion}
      kind={kind}
      resumeKey={resumeKey}
      onApplied={onApplied}
      onReanalyze={onReanalyze}
      locked={locked}
    />
  );
}

/**
 * A card's one suggestion: the hash-guarded editor (copy-only for Other sections, which have no
 * bullet edit op), or the plain wording when the card has no text to compare it with.
 */
function CardSuggestion({
  currentText,
  suggestion,
  ...rest
}: {
  finding: LintFinding;
  currentText: string | null;
  suggestion: string;
  kind: "base" | "application";
  resumeKey: string;
  onApplied: () => void;
  onReanalyze?: () => void;
  locked?: boolean;
}) {
  if (currentText == null) {
    return (
      <p className="text-muted-foreground mt-2 max-w-[65ch] border-t pt-2 text-body-small">{suggestion}</p>
    );
  }
  return <SuggestionBlock currentText={currentText} suggestion={suggestion} {...rest} />;
}

export function SuggestionEditor({
  finding,
  currentText,
  suggestion,
  kind,
  resumeKey,
  onApplied,
  onReanalyze,
  locked,
  expectedHash,
}: {
  finding: LintFinding;
  currentText: string;
  suggestion: string;
  kind: "base" | "application";
  resumeKey: string;
  onApplied: () => void;
  onReanalyze?: () => void;
  locked?: boolean;
  expectedHash?: string | null;
}) {
  const [draft, setDraft] = useState(suggestion);
  const [applied, setApplied] = useState(false);
  // Apply leaves with its button: "Applied" takes the focus.
  const appliedRef = useRef<HTMLParagraphElement>(null);
  const focusNext = useFocusOnNextCommit();

  const apply = useMutation({
    mutationFn: () =>
      applyResumeEdits(kind, resumeKey, [
        bulletEditOp(finding.location, draft, expectedHash ?? finding.content_hash),
      ]),
    onSuccess: (result) => {
      setApplied(true);
      focusNext(appliedRef);
      notifyRenderNote(result);
      toast.success("Applied and saved as a new version");
      onApplied();
    },
    onError: (err: Error) => toastRewriteError(err, onReanalyze),
  });
  // One edit per gesture: a double click applied the wording twice.
  const applyOnce = useSingleFlight(apply.mutate);

  if (applied) {
    return (
      <p
        ref={appliedRef}
        tabIndex={-1}
        className="text-muted-foreground mt-2 border-t pt-2 text-body-small outline-none"
      >
        Applied
      </p>
    );
  }

  const canApply = draft.trim().length > 0;

  return (
    <div className="mt-2 space-y-2 border-t pt-2">
      <div className="bg-surface-container-low rounded-md p-2">
        <DiffText oldText={currentText} newText={draft || suggestion} />
      </div>
      <Textarea
        rows={3}
        aria-label="New wording"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        className="max-w-[65ch] text-body-medium"
        disabled={locked}
      />
      <div className="flex justify-end">
        {/* Tonal: the report's one filled button is Start the questions. */}
        <Button
          size="sm"
          variant="tonal"
          disabled={!canApply || apply.isPending || locked}
          title={locked ? STALE_APPLY_HINT : undefined}
          focusableWhenDisabled
          className={
            locked
              ? `${LOCKED_BTN} data-disabled:opacity-50`
              : "data-disabled:pointer-events-none data-disabled:opacity-50"
          }
          onClick={() => applyOnce()}
        >
          {apply.isPending ? "Applying…" : "Apply suggestion"}
        </Button>
      </div>
    </div>
  );
}

function LevelChip({ finding }: { finding: LintFinding }) {
  const name = levelNameOf(finding);
  if (!name) return null;
  const label = EVIDENCE_LABELS[name as EvidenceLevel] ?? name;
  return (
    <span className="text-muted-foreground text-body-small">{label}</span>
  );
}

function CollapsedRow({
  finding,
  quote,
  actionLabel,
  onExpand,
  overflow,
}: {
  finding: LintFinding;
  quote: string | null;
  actionLabel: string;
  onExpand: () => void;
  overflow: ReactNode;
}) {
  // The group header states the rule, so the row names its place in full ("<entry> · bullet 3"),
  // then the bullet as judged text and the bullet's own question. The label wraps inside the card:
  // a long entry name must not push the action and ⋯ off it.
  return (
    <div className="flex min-w-0 flex-wrap items-start gap-2">
      <div className="flex min-w-0 flex-1 basis-48 flex-col items-start gap-1 text-left">
        <button type="button" onClick={onExpand} aria-expanded={false} className="text-left">
          <span className="text-muted-foreground min-w-0 text-body-small break-words">
            {finding.label} · <LevelChip finding={finding} />
            {finding.zone === "hot" && <> · {ATTENTION_BADGE_LABEL}</>}
          </span>
        </button>
        {quote ? (
          <span className="block w-full min-w-0">
            <SourceQuote text={quote} clamp />
          </span>
        ) : (
          <span className="text-muted-foreground block w-full min-w-0 text-body-medium">
            {finding.issue}
          </span>
        )}
        {finding.question && (
          <p className="text-foreground max-w-[65ch] text-body-medium">{finding.question}</p>
        )}
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-2">
        <Button
          size="xs"
          variant="link"
          // Every row's action has its own name: "Answer: Data Analyst · Acme · bullet 3".
          aria-label={`${actionLabel}: ${finding.label}`}
          onClick={onExpand}
        >
          {actionLabel}
        </Button>
        {overflow}
      </div>
    </div>
  );
}

/**
 * A tab's group: the rule its rows break, stated once. The title is the rule (a detector's title, or
 * the issue sentence every row shares), then the points the whole group could gain, then the why and
 * how when every row shares them (the rows then leave their own out).
 */
export function FindingGroupHeader({
  title,
  findings,
  nScoreable,
}: {
  title: string;
  findings: LintFinding[];
  nScoreable?: number | null;
}) {
  const points = groupPoints(findings, nScoreable);
  const coaching = sharedCoaching(findings);
  return (
    <div className="space-y-1">
      <h3 className="text-title-small">
        {title} <span className="text-body-medium text-muted-foreground">({findings.length})</span>
      </h3>
      {points > 0 && <p className="text-muted-foreground text-body-small">Up to +{points} points</p>}
      {coaching && (
        <p className="text-muted-foreground max-w-[65ch] text-body-medium">
          {coaching.why} {coaching.how}
        </p>
      )}
    </div>
  );
}

export function FixCard({
  finding,
  data,
  kind,
  resumeKey,
  onApplied,
  onClassificationChanged,
  onReanalyze,
  locked,
  hideHow,
  dispute,
  disputeFresh,
  onDisputeSeen,
  onDisputed,
}: FindingCardShared & { finding: LintFinding }) {
  // A card the re-run after the latest dispute put in place opens on its reply and takes focus
  // there; collapsing it ends that, so re-expanding never moves focus to an old reply.
  const fresh = dispute != null && Boolean(disputeFresh);
  const [expanded, setExpanded] = useState(fresh);
  const [landOnReply, setLandOnReply] = useState(fresh);
  const endLanding = () => {
    if (!landOnReply) return;
    setLandOnReply(false);
    onDisputeSeen?.();
  };
  // Review leaves with the collapsed row: focus goes into the opened card
  // (its first field, else its first control), never to <body>.
  const cardRef = useRef<HTMLDivElement>(null);
  const focusNext = useFocusOnNextCommit();
  const currentText = textAtLocation(data, finding);
  const meta = TYPE_CARD.fix;
  const renderSuggestion = (s: string) => (
    <CardSuggestion
      finding={finding}
      currentText={currentText}
      suggestion={s}
      kind={kind}
      resumeKey={resumeKey}
      onApplied={onApplied}
      onReanalyze={onReanalyze}
      locked={locked}
    />
  );
  // One suggestion per card: a dispute's is newer than the check's own.
  const disputeSuggestion = dispute?.suggestion ?? null;
  const overflow = (
    <FindingOverflow
      finding={finding}
      onClassificationChanged={onClassificationChanged}
    />
  );

  if (!expanded) {
    return (
      <div className={cn("rounded-md border px-3 py-2", meta.card)}>
        <CollapsedRow
          finding={finding}
          quote={currentText}
          actionLabel="Review"
          onExpand={() => {
            setExpanded(true);
            focusNext(cardRef);
          }}
          overflow={overflow}
        />
      </div>
    );
  }

  const showQuote =
    finding.suggestion == null &&
    disputeSuggestion == null &&
    currentText != null &&
    currentText.trim().length > 0;

  return (
    <ExpandedFindingChrome
      ref={cardRef}
      finding={finding}
      cardClassName={meta.card}
      overflow={overflow}
      onCollapse={() => {
        setExpanded(false);
        endLanding();
      }}
      quote={showQuote ? currentText : null}
      how={finding.how}
      hideHow={hideHow}
    >
      {finding.suggestion != null && disputeSuggestion == null && renderSuggestion(finding.suggestion)}
      <DisputeBox
        finding={finding}
        kind={kind}
        resumeKey={resumeKey}
        result={dispute}
        land={landOnReply}
        onLanded={endLanding}
        onDisputed={onDisputed}
        onReanalyze={onReanalyze}
        locked={locked}
        renderSuggestion={renderSuggestion}
      />
    </ExpandedFindingChrome>
  );
}

export function AskCard({
  finding,
  data,
  kind,
  resumeKey,
  onApplied,
  onClassificationChanged,
  onReanalyze,
  locked,
  hideHow,
  storedAnswer,
  dispute,
  disputeFresh,
  onDisputeSeen,
  onDisputed,
}: FindingCardShared & { finding: LintFinding }) {
  // As on FixCard: opens on a fresh dispute's reply, and collapsing ends the landing.
  const fresh = dispute != null && Boolean(disputeFresh);
  const [expanded, setExpanded] = useState(fresh);
  const [landOnReply, setLandOnReply] = useState(fresh);
  const endLanding = () => {
    if (!landOnReply) return;
    setLandOnReply(false);
    onDisputeSeen?.();
  };
  const [answerDraft, setAnswerDraft] = useState<string | null>(null);
  const [metricDraft, setMetricDraft] = useState<MetricAskValue | null>(null);
  const [localSuggestion, setLocalSuggestion] = useState<
    string | null | undefined
  >(undefined);
  const [notRewritable, setNotRewritable] = useState(false);
  // Answer, and later Write new wording, leave with their buttons: focus goes
  // into the card (the answer field, then the new wording), never to <body>.
  const cardRef = useRef<HTMLDivElement>(null);
  const focusNext = useFocusOnNextCommit();
  const currentText = textAtLocation(data, finding);
  const meta = TYPE_CARD.ask;
  const metricAsk = isMetricAsk(finding);
  const [useAlternative, setUseAlternative] = useState(false);
  const storedFresh = answerMatchesFinding(storedAnswer, finding.content_hash);
  const staleDraft = Boolean(storedAnswer && !storedFresh);
  const answer = answerDraft ?? (storedFresh ? storedAnswer.answer : "");
  const metric =
    metricDraft ??
    (storedFresh
      ? {
          ...emptyMetricAsk(),
          somethingElse: true,
          freeText: storedAnswer.answer,
        }
      : emptyMetricAsk());
  const suggestion =
    localSuggestion !== undefined
      ? localSuggestion
      : storedFresh
        ? storedAnswer.suggestion
        : null;
  const overflow = (
    <FindingOverflow
      finding={finding}
      onClassificationChanged={onClassificationChanged}
    />
  );
  const renderSuggestion = (s: string) => (
    <CardSuggestion
      finding={finding}
      currentText={currentText}
      suggestion={s}
      kind={kind}
      resumeKey={resumeKey}
      onApplied={onApplied}
      onReanalyze={onReanalyze}
      locked={locked}
    />
  );
  // One suggestion per card: a dispute's is newer than the answer's.
  const disputeSuggestion = dispute?.suggestion ?? null;

  const context = metricAsk && !useAlternative ? metricContextFromValue(metric) : answer.trim();

  const draft = useMutation({
    mutationFn: () => answerAsk(kind, resumeKey, finding.id, context),
    onSuccess: (result) => {
      setLocalSuggestion(result.suggestion);
      focusNext(cardRef);
    },
    onError: (err: Error) => {
      if (err instanceof ApiError && isContentChangedError(err)) {
        toastContentChanged(onReanalyze);
        return;
      }
      if (err instanceof ApiError && err.status === 422) {
        setNotRewritable(true);
      } else {
        toast.error(couldnt("write new wording", err));
      }
    },
  });
  // One draft per gesture: a double click asked for new wording twice.
  const draftOnce = useSingleFlight(draft.mutate);

  if (!expanded) {
    return (
      <div className={cn("rounded-md border px-3 py-2", meta.card)}>
        <CollapsedRow
          finding={finding}
          quote={currentText}
          actionLabel="Answer"
          onExpand={() => {
            setExpanded(true);
            focusNext(cardRef);
          }}
          overflow={overflow}
        />
      </div>
    );
  }

  const showQuote =
    suggestion == null &&
    disputeSuggestion == null &&
    currentText != null &&
    currentText.trim().length > 0;
  const answering = !(suggestion != null || notRewritable);

  return (
    <ExpandedFindingChrome
      ref={cardRef}
      finding={finding}
      cardClassName={meta.card}
      overflow={overflow}
      onCollapse={() => {
        setExpanded(false);
        endLanding();
      }}
      quote={showQuote ? currentText : null}
      how={finding.how}
      hideHow={hideHow}
    >
      {finding.question && (
        <p className="text-foreground mt-1 max-w-[65ch] text-body-medium">
          {useAlternative ? finding.alt_question : finding.question}
        </p>
      )}
      {staleDraft && (
        <p className="text-warning mt-1 text-body-small">
          This bullet changed after you answered. Write the new wording again.
        </p>
      )}

      {suggestion != null ? (
        disputeSuggestion == null && renderSuggestion(suggestion)
      ) : notRewritable ? (
        <p className="text-muted-foreground mt-2 max-w-[65ch] border-t pt-2 text-body-small">
          There&apos;s no single bullet to rewrite here. Add this to your resume directly.
        </p>
      ) : (
        <div className="mt-2 space-y-2 border-t pt-2">
          {metricAsk && finding.alt_question && (
            <button
              type="button"
              className="text-primary text-body-medium underline-offset-2 hover:underline"
              aria-expanded={useAlternative}
              onClick={() => { setUseAlternative((v) => !v); focusNext(cardRef); }}
              disabled={locked}
            >
              {useAlternative ? "Use the number fields" : "No number? Answer this instead"}
            </button>
          )}
          {metricAsk && !useAlternative ? (
            <MetricAskInput
              label={finding.measure_target ? `Number for: ${finding.measure_target}` : undefined}
              value={metric}
              onChange={setMetricDraft}
              disabled={locked}
            />
          ) : (
            <Textarea
              rows={2}
              aria-label="Your answer"
              value={answer}
              onChange={(e) => setAnswerDraft(e.target.value)}
              className="max-w-[65ch] text-body-medium"
              disabled={locked}
            />
          )}
        </div>
      )}
      <DisputeBox
        finding={finding}
        kind={kind}
        resumeKey={resumeKey}
        result={dispute}
        land={landOnReply}
        onLanded={endLanding}
        onDisputed={onDisputed}
        onReanalyze={onReanalyze}
        locked={locked}
        // "Not right?" sits beside the answer's own control while the card asks.
        controls={answering ? (
          <Button
            size="sm"
            variant="tonal"
            disabled={
              context.length === 0 || draft.isPending || locked
            }
            title={locked ? STALE_APPLY_HINT : undefined}
            // Disables itself while writing: a native `disabled` drops focus.
            focusableWhenDisabled
            // Locked keeps pointer events, so its hint shows on hover.
            className={
              locked
                ? `${LOCKED_BTN} data-disabled:opacity-50`
                : "data-disabled:pointer-events-none data-disabled:opacity-50"
            }
            onClick={() => draftOnce()}
          >
            {draft.isPending ? "Writing…" : "Write new wording"}
          </Button>
        ) : null}
        renderSuggestion={renderSuggestion}
      />
    </ExpandedFindingChrome>
  );
}

/**
 * The Notes tab: the Wording group, the rule table and the unscored skills. None changes the score.
 * Too-long bullets are the Shorten tab's (`ShortenList`), and "No numbers anywhere" is the summary
 * band's callout, so neither reaches here.
 */
export function NotesTable({
  notes,
  data,
  kind,
  resumeKey,
  onApplied,
  locked,
  onReanalyze,
  onWordingChanged,
}: {
  notes: LintFinding[];
  data?: ResumeData | null;
  kind: "base" | "application";
  resumeKey: string;
  onApplied: () => void;
  locked?: boolean;
  onReanalyze?: () => void;
  /** Runs the report again after the word list changed (an Ignore, the word list's Save). */
  onWordingChanged: () => Promise<void>;
}) {
  // Wording notes (spelling and grammar slips, clichés, filler) are one checklist of their own.
  const { wording, other } = splitWordingNotes(notes);
  const allGroups = groupNotesByRule(other);
  const skills = allGroups.find((g) => g.rule === "skills.undemonstrated") ?? null;
  const groups = allGroups.filter((g) => g !== skills);
  const [skill, setSkill] = useState<string | null>(null);
  // One kept dialog per skill the user has opened, so a drafted rewrite
  // survives closing it and opening another skill.
  const [opened, setOpened] = useState<string[]>([]);
  const openSkill = (subject: string) => {
    setOpened((s) => (s.includes(subject) ? s : [...s, subject]));
    setSkill(subject);
  };
  const [doneSkills, setDoneSkills] = useState<Set<string>>(new Set());
  // An Apply marks its row "Done", which disables its action, and Base UI's return
  // to a disabled button lands on <body>. Focus goes to the opener while it is
  // live, else the next skill still to do, else the notes section itself (a
  // tabIndex={-1} target Base UI would pass to its first tabbable child).
  const sectionRef = useRef<HTMLElement>(null);
  const returnFrom = (subject: string) => () => {
    const chips = Array.from(
      sectionRef.current?.querySelectorAll<HTMLButtonElement>("button[data-skill]") ?? [],
    );
    const at = Math.max(0, chips.findIndex((chip) => chip.dataset.skill === subject));
    const live = [...chips.slice(at), ...chips.slice(0, at)].find((chip) => !chip.disabled);
    if (live) return live;
    queueMicrotask(() => focusIfDropped(sectionRef.current));
    return false;
  };

  const applyOps = useMutation({
    mutationFn: (ops: Record<string, unknown>[]) =>
      applyResumeEdits(kind, resumeKey, ops),
    onSuccess: (result) => {
      notifyRenderNote(result);
      toast.success("Applied and saved as a new version");
      onApplied();
    },
    onError: (err: Error) => toastRewriteError(err, onReanalyze),
  });

  return (
    <section ref={sectionRef} id="notes" tabIndex={-1} className="scroll-mt-6 space-y-3 outline-none">
      <p className="text-muted-foreground text-body-medium">These don&apos;t change your score.</p>
      {/* Always, even with no hits: Edit word list lives in its header. */}
      <WordingChecklist
        notes={wording}
        data={data ?? null}
        kind={kind}
        resumeKey={resumeKey}
        onApplied={onApplied}
        onReanalyze={onReanalyze}
        onWordingChanged={onWordingChanged}
      />
      {groups.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full table-fixed text-body-medium">
            <tbody>
              {groups.map((group) => {
                const ops =
                  data && isMechanicalPunctRule(group.rule)
                    ? punctFixOps(group.rule, group.subjects, data)
                    : null;
                const bulletRows = isBulletSubjectRule(group.rule);
                const subjectLine =
                  !bulletRows && group.subjects.length > 0
                    ? group.subjects.slice(0, 8).join(", ") +
                      (group.subjects.length > 8 ? ", …" : "")
                    : null;
                return (
                  <tr key={group.rule} className="border-b last:border-b-0">
                    <td className="px-3 py-2 align-top">
                      <p className="font-medium">
                        {group.title} ({group.count})
                      </p>
                      {subjectLine && (
                        <p className="text-muted-foreground mt-0.5 max-w-[65ch] text-body-small">
                          {subjectLine}
                        </p>
                      )}
                      {group.shapeNote &&
                        group.notes.map((note) => (
                          <p
                            key={note.id}
                            className="text-muted-foreground mt-0.5 max-w-[65ch] text-body-small"
                          >
                            {note.issue} {note.how}
                          </p>
                        ))}
                      {bulletRows && (
                        <ul className="mt-1.5 space-y-1">
                          {group.notes.map((note) => (
                            <li key={note.id} className="min-w-0">
                              <SourceQuote text={note.subject ?? note.issue} clamp />
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td className="w-28 px-3 py-2 align-top text-right">
                      {ops ? (
                        <Button
                          size="xs"
                          variant="outline"
                          disabled={locked || applyOps.isPending}
                          title={locked ? STALE_APPLY_HINT : undefined}
                          className={locked ? LOCKED_BTN : undefined}
                          onClick={() => applyOps.mutate(ops)}
                        >
                          Fix all
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {skills && (
        <div className="space-y-1.5">
          <h3 className="text-title-small">
            {skills.title} ({skills.count})
          </h3>
          <p className="text-muted-foreground max-w-[65ch] text-body-medium">{skills.notes[0].how}</p>
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-body-medium">
              <thead className="text-muted-foreground text-left text-body-small">
                <tr className="border-b">
                  <th scope="col" className="px-3 py-2 text-label-medium">Skill</th>
                  <th scope="col" className="px-3 py-2 text-label-medium">Listed in</th>
                  <th scope="col" className="px-3 py-2 text-label-medium">
                    <span className="sr-only">Action</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {skills.subjects.map((subject) => {
                  const done = doneSkills.has(subject);
                  return (
                    <tr key={subject} className="border-b last:border-b-0">
                      <td className="px-3 py-1.5 break-words">{subject}</td>
                      <td className="text-muted-foreground px-3 py-1.5">
                        {skillGroupOf(data, subject) ?? "—"}
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        <Button
                          size="xs"
                          variant="link"
                          data-skill={subject}
                          // The visible words first (WCAG 2.5.3), then the skill: every row's name differs.
                          aria-label={done ? `Done: ${subject}` : `Show it in a bullet: ${subject}`}
                          onClick={() => !done && openSkill(subject)}
                          disabled={done || locked || !data}
                        >
                          {done ? "Done" : "Show it in a bullet"}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {data && opened.map((s) => (
        <DemonstrateSkillDialog
          key={s}
          open={skill === s}
          onOpenChange={(open) => {
            if (!open) setSkill(null);
          }}
          skill={s}
          data={data}
          kind={kind}
          resumeKey={resumeKey}
          locked={locked}
          onApplied={() => {
            setDoneSkills((d) => new Set(d).add(s));
            onApplied();
          }}
          onReanalyze={onReanalyze}
          finalFocus={returnFrom(s)}
        />
      ))}
    </section>
  );
}

/**
 * A check that flips (Mark as OK, Undo) swaps its row for the other kind, and
 * the button the user pressed leaves with the old row. The row that replaces it
 * takes the focus back onto its own action: `land` marks the check just changed.
 * `land` is set BEFORE the refetch that swaps the rows, so the new row mounts
 * with it, and a layout effect moves focus in the swap's own commit: a passive
 * effect after a later `land` commit left focus on <body> for a frame or two.
 */
function useLandFocus(land: boolean, target?: RefObject<HTMLButtonElement | null>) {
  const own = useRef<HTMLButtonElement>(null);
  const actionRef = target ?? own;
  useLayoutEffect(() => {
    if (land) focusIfDropped(actionRef.current);
  }, [land, actionRef]);
  return actionRef;
}

function FailedGate({
  gate,
  kind,
  resumeKey,
  onChanged,
  land,
  onLanded,
}: {
  gate: LintGate;
  kind: "base" | "application";
  resumeKey: string;
  onChanged: () => Promise<void>;
  land: boolean;
  onLanded: (gateId: string) => void;
}) {
  // "Mark as OK…" opens the reason box with focus in it; Cancel returns here.
  const { editing: showReason, editRef, openerRef, open, close } = useEditToggle<HTMLDivElement>();
  const [reason, setReason] = useState("");
  useLandFocus(land, openerRef);

  const markOk = useMutation({
    mutationFn: async () => {
      await waiveGate(kind, resumeKey, gate.id, reason);
      // Before the refetch that swaps this row out: its replacement mounts knowing to take focus.
      onLanded(gate.id);
      await onChanged();
    },
    onSuccess: () => {
      toast.success("Marked as OK");
    },
    onError: (err: Error) => toast.error(couldnt("mark it as OK", err)),
  });
  // One waiver per gesture: a double click sent the request twice.
  const waiveOnce = useSingleFlight(markOk.mutate);

  const accent =
    gate.tier === "fatal"
      ? "border-destructive/50 bg-destructive/5"
      : "border-border";

  return (
    <div className={cn("min-w-0 rounded-md border px-3 py-2", accent)}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant="secondary"
          className={cn(
            "shrink-0",
            gate.tier === "fatal"
              ? "bg-destructive/10 text-destructive"
              : "bg-warning-container text-on-warning-container",
          )}
        >
          {gate.tier === "fatal" ? "Must fix" : "Serious"}
        </Badge>
        <span className="min-w-0 text-title-small break-words">{gate.label}</span>
      </div>
      {gate.detail && <p className="mt-1 max-w-[65ch] text-body-medium break-words">{gate.detail}</p>}
      {gate.fix_hint && (
        <p className="text-muted-foreground mt-1 max-w-[65ch] text-body-small break-words">
          {gate.fix_hint}
        </p>
      )}

      {showReason ? (
        <div ref={editRef} className="mt-2 space-y-2">
          <p className="text-muted-foreground max-w-[65ch] text-body-small">
            Your score won&apos;t be limited by this any more. Your resume isn&apos;t
            changed. You can undo this here.
          </p>
          <Textarea
            rows={2}
            aria-label="Why is this OK?"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="max-w-[65ch] text-body-medium"
          />
          <div className="flex justify-end gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={close}
              disabled={markOk.isPending}
            >
              Cancel
            </Button>
            {/* Tonal: the report's one filled button is Start the questions. */}
            <Button
              size="sm"
              variant="tonal"
              disabled={reason.trim().length === 0 || markOk.isPending}
              onClick={() => waiveOnce()}
              // Disables itself while saving: a native `disabled` drops focus.
              focusableWhenDisabled
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
            >
              {markOk.isPending ? "Saving…" : "Mark as OK"}
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-2 flex justify-end">
          <Button
            ref={openerRef}
            size="sm"
            variant="outline"
            onClick={open}
          >
            Mark as OK…
          </Button>
        </div>
      )}
    </div>
  );
}

function WaivedGate({
  gate,
  kind,
  resumeKey,
  onChanged,
  land,
  onLanded,
}: {
  gate: LintGate;
  kind: "base" | "application";
  resumeKey: string;
  onChanged: () => Promise<void>;
  land: boolean;
  onLanded: (gateId: string) => void;
}) {
  const actionRef = useLandFocus(land);
  const unwaive = useMutation({
    mutationFn: async () => {
      await unwaiveGate(kind, resumeKey, gate.id);
      onLanded(gate.id);
      await onChanged();
    },
    onSuccess: () => {
      toast.success("Check turned back on");
    },
    onError: (err: Error) => toast.error(couldnt("undo", err)),
  });
  // One undo per gesture: a double click sent the request twice.
  const unwaiveOnce = useSingleFlight(unwaive.mutate);

  return (
    <div className="text-muted-foreground bg-surface-container-low min-w-0 rounded-md border px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate text-body-medium">{gate.label} (marked OK)</span>
        <Button
          ref={actionRef}
          size="sm"
          variant="ghost"
          disabled={unwaive.isPending}
          onClick={() => unwaiveOnce()}
          // Disables itself while undoing: a native `disabled` drops focus.
          focusableWhenDisabled
          className="data-disabled:pointer-events-none data-disabled:opacity-50"
        >
          {unwaive.isPending ? "Undoing…" : "Undo"}
        </Button>
      </div>
      {gate.detail && <p className="mt-1 max-w-[65ch] text-body-medium break-words">{gate.detail}</p>}
      {gate.waiver_reason && (
        <p className="mt-1 text-body-small break-words">
          <span className="text-foreground font-medium">Reason: </span>
          {gate.waiver_reason}
        </p>
      )}
    </div>
  );
}

function NotAssessedGate({
  gate,
  templateId,
  onChanged,
  land,
}: {
  gate: LintGate;
  templateId?: string | null;
  onChanged: () => Promise<void>;
  land: boolean;
}) {
  const actionRef = useLandFocus(land);
  const certify = useMutation({
    mutationFn: async () => {
      if (!templateId) throw new Error("This resume has no template selected.");
      await validateTemplate(templateId);
      await onChanged();
    },
    onSuccess: () => toast.success("Template checked. Updating the report."),
    onError: (err: Error) => toast.error(couldnt("check the template", err)),
  });

  return (
    <div className="rounded-md border border-border bg-surface-container-low px-3 py-2">
      <div className="flex items-center gap-2">
        <Badge variant="secondary" className="bg-muted text-muted-foreground shrink-0">
          Not checked
        </Badge>
        <span className="text-title-small">{gate.label}</span>
      </div>
      <p className="text-muted-foreground mt-1 max-w-[65ch] text-body-medium">
        {gate.label} wasn&apos;t checked because this template hasn&apos;t been checked yet.
        {gate.detail ? ` ${gate.detail}` : ""}
      </p>
      <div className="mt-2 flex justify-end">
        {templateId ? (
          <Button
            ref={actionRef}
            size="sm"
            variant="outline"
            disabled={certify.isPending}
            onClick={() => certify.mutate()}
            focusableWhenDisabled
            className="data-disabled:pointer-events-none data-disabled:opacity-50"
          >
            {certify.isPending ? "Checking…" : "Check template"}
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            nativeButton={false}
            render={<Link href="/templates">Open templates</Link>}
          />
        )}
      </div>
    </div>
  );
}

export function GateBanner({
  gates,
  kind,
  resumeKey,
  onChanged,
  templateId,
}: {
  gates: LintGate[];
  kind: "base" | "application";
  resumeKey: string;
  onChanged: () => Promise<void>;
  templateId?: string | null;
}) {
  // The check just marked OK or turned back on: its new row takes the focus.
  const [landOn, setLandOn] = useState<string | null>(null);
  const failed = gates.filter((g) => g.status === "fail");
  const waived = gates.filter((g) => g.status === "waived");
  const notAssessed = gates.filter((g) => g.status === "not_assessed");
  if (failed.length === 0 && waived.length === 0 && notAssessed.length === 0) {
    return null;
  }
  // "Checks", not "Must fix": the group holds serious, waived and unchecked
  // checks too. "Must fix" is the fatal tier's badge only.
  return (
    <section id="gates" className="scroll-mt-6 space-y-2">
      <h2 className="text-title-small">Checks</h2>
      {failed.map((gate) => (
        <FailedGate
          key={gate.id}
          gate={gate}
          kind={kind}
          resumeKey={resumeKey}
          onChanged={onChanged}
          land={landOn === gate.id}
          onLanded={setLandOn}
        />
      ))}
      {notAssessed.map((gate) => (
        <NotAssessedGate
          key={gate.id}
          gate={gate}
          templateId={templateId}
          onChanged={onChanged}
          land={landOn === gate.id}
        />
      ))}
      {waived.map((gate) => (
        <WaivedGate
          key={gate.id}
          gate={gate}
          kind={kind}
          resumeKey={resumeKey}
          onChanged={onChanged}
          land={landOn === gate.id}
          onLanded={setLandOn}
        />
      ))}
    </section>
  );
}

export function ResolvedFinding({
  finding,
  dispute,
  currentText,
}: {
  finding: LintFinding;
  /** The dispute whose re-run lifted this bullet out of the report: its reply stays in view. */
  dispute?: { reply: string; suggestion: string | null };
  currentText?: string | null;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // A dispute that lifted this bullet took its card, and the reply that held focus, with it. The
  // entry takes focus when it mounts after the card left; DisputeBox hands it over when the card
  // leaves after the entry mounted.
  useLayoutEffect(() => {
    if (dispute) focusIfDropped(ref.current);
  }, [dispute]);
  return (
    <div
      ref={ref}
      tabIndex={dispute ? -1 : undefined}
      data-resolved-hash={dispute ? (finding.content_hash ?? undefined) : undefined}
      className="rounded-md border border-dashed px-3 py-2 text-body-medium outline-none"
    >
      <p className="text-muted-foreground line-through">Fixed: {finding.label}</p>
      {dispute && (
        <>
          <p role="status" className="text-foreground mt-1 max-w-[65ch]">
            {dispute.reply}
          </p>
          {/* A fact from the note, as wording to copy: the bullet has left the report, so there is
              no card to apply it from. */}
          {dispute.suggestion != null &&
            (currentText != null ? (
              <SuggestionCopyOnly currentText={currentText} suggestion={dispute.suggestion} />
            ) : (
              <p className="text-muted-foreground mt-2 max-w-[65ch] border-t pt-2 text-body-small">
                {dispute.suggestion}
              </p>
            ))}
        </>
      )}
    </div>
  );
}
