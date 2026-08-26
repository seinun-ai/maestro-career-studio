"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import {
  ATTENTION_BADGE,
  ATTENTION_BADGE_LABEL,
} from "@/components/attention-zone";
import { useMutation } from "@tanstack/react-query";
import { MoreHorizontal } from "lucide-react";
import { toast } from "sonner";

import { DemonstrateSkillDialog } from "@/components/resume-health/demonstrate-skill-dialog";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { IconButton } from "@/components/icon-button";
import {
  answerAsk,
  ApiError,
  apiFetch,
  draftRewrite,
  unwaiveGate,
  validateTemplate,
  waiveGate,
} from "@/lib/api";
import { toastContentChanged } from "./report-errors";
import {
  answerMatchesFinding,
  groupNotesByRule,
  hoistBlurb,
  isBulletSubjectRule,
  isContentChangedError,
  isMechanicalPunctRule,
  isMetricAsk,
  levelNameOf,
  potentialPoints,
  punctFixOps,
  sharedCoaching,
  STALE_APPLY_HINT,
  type StoredAskAnswer,
  textAtLocation,
} from "@/lib/health-report";
import { wordDiff } from "@/lib/word-diff";
import { cn } from "@/lib/utils";
import type {
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

const EVIDENCE_LEVELS: { value: EvidenceLevel; label: string; detail: string }[] = [
  { value: "direct", label: "Direct", detail: "Outcome evidence" },
  { value: "analogue", label: "Analogue", detail: "Scale evidence" },
  { value: "adjacent", label: "Adjacent", detail: "Specific, no metric" },
  { value: "implied", label: "Implied", detail: "Contribution is vague" },
  { value: "unaddressed", label: "Unaddressed", detail: "Duty, not achievement" },
];

const EVIDENCE_LABELS = Object.fromEntries(
  EVIDENCE_LEVELS.map(({ value, label }) => [value, label]),
) as Record<EvidenceLevel, string>;

const LOCKED_BTN =
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
};

export type ExpandedFindingChromeProps = {
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
    <div className={cn("rounded-md border px-3 py-2", cardClassName)}>
      <div className="flex items-start justify-between gap-2">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
          onClick={onCollapse}
          aria-expanded
        >
          <Badge
            variant="secondary"
            className="text-muted-foreground shrink-0 text-xs"
          >
            {finding.label}
          </Badge>
          <LevelChip finding={finding} />
        </button>
        {overflow}
      </div>
      {quote && <SourceQuote text={quote} />}
      {how && !hideHow && (
        <p className="mt-1.5 max-w-[65ch] text-sm">{how}</p>
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
          ? "Automatic classification restored"
          : "Classification updated and report re-analyzed",
      );
    },
    onError: (err: Error) =>
      toast.error(err instanceof ApiError ? err.message : String(err)),
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
          <DialogTitle>Override classification</DialogTitle>
        </DialogHeader>
        <div className="grid gap-1.5">
          <Select
            value={level}
            onValueChange={(value) =>
              setLevel(value as EvidenceLevel | "automatic")
            }
            disabled={save.isPending}
          >
            <SelectTrigger size="sm" className="w-full" aria-label="Evidence level">
              <SelectValue>{selectedLabel}</SelectValue>
            </SelectTrigger>
            <SelectContent align="start">
              <SelectItem value="automatic">Automatic</SelectItem>
              {EVIDENCE_LEVELS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  <span>{option.label}</span>
                  <span className="text-muted-foreground text-xs">
                    {option.detail}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-muted-foreground text-xs">
            Current: {currentLabel}. Saving re-runs the report.
          </p>
          {level !== "automatic" && (
            <Textarea
              rows={2}
              aria-label="Reason for overriding the evidence level · optional"
              value={reason}
              maxLength={500}
              onChange={(event) => setReason(event.target.value)}
              placeholder="e.g. this metric lives in the next bullet"
              className="text-sm"
              disabled={save.isPending}
            />
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
            {save.isPending ? "Re-analyzing…" : "Save override"}
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
              label="More actions"
              icon={<MoreHorizontal className="size-4" />}
              size="icon-xs"
            />
          }
        />
        <DropdownMenuContent align="end" className="min-w-48">
          <DropdownMenuItem onClick={() => setDialogOpen(true)}>
            Override classification
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

/** Header count chips — v2 counts keys. Shared by the sheet and report page. */
export const COUNT_META: { key: string; label: string; chip: string }[] = [
  { key: "gate", label: "Gate", chip: "bg-red-500/10 text-red-600 dark:text-red-400" },
  {
    key: "critical",
    label: "Critical",
    chip: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  },
  {
    key: "ask",
    label: "Ask",
    chip: "bg-violet-500/10 text-violet-700 dark:text-violet-400",
  },
  {
    key: "note",
    label: "Note",
    chip: "bg-slate-500/10 text-slate-600 dark:text-slate-400",
  },
];

const TYPE_CHIP: Record<"fix" | "ask", { label: string; chip: string; card: string }> = {
  fix: {
    label: "Fix",
    chip: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
    card: "border-amber-500/40",
  },
  ask: {
    label: "Ask",
    chip: "bg-violet-500/10 text-violet-700 dark:text-violet-400",
    card: "border-violet-500/30",
  },
};

export const GRADE_STYLES: Record<string, string> = {
  A: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  B: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-500",
  C: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  D: "bg-orange-500/15 text-orange-700 dark:text-orange-400",
  F: "bg-red-500/15 text-red-600 dark:text-red-400",
};

function DiffText({ oldText, newText }: { oldText: string; newText: string }) {
  return (
    <p className="max-w-[65ch] text-sm leading-relaxed">
      {wordDiff(oldText, newText).map((token, i) => (
        <span
          key={i}
          className={cn(
            token.kind === "removed" &&
              "bg-red-500/10 text-red-600 line-through dark:text-red-400",
            token.kind === "added" &&
              "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
          )}
        >
          {token.text}{" "}
        </span>
      ))}
    </p>
  );
}

/** Current text at a finding's location, for the tracked-changes view. */

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

function SuggestionCopyOnly({
  currentText,
  suggestion,
}: {
  currentText: string;
  suggestion: string;
}) {
  return (
    <div className="mt-2 space-y-2 border-t pt-2">
      <div className="bg-muted/40 rounded-md p-2">
        <DiffText oldText={currentText} newText={suggestion} />
      </div>
      <p className="text-muted-foreground max-w-[65ch] text-xs">
        Custom-section bullets can&apos;t be applied from health yet — copy the
        rewrite into the editor.
      </p>
    </div>
  );
}

function SourceQuote({ text, truncated }: { text: string; truncated?: boolean }) {
  return (
    <blockquote
      className={cn(
        "border-muted-foreground/30 border-l-2 pl-2 text-sm",
        // Truncated one-liners are glanceable labels; keep them quiet. An
        // expanded quote is body text the user actually reads — regular
        // posture, near-full contrast, so it can't be mistaken for disabled.
        truncated
          ? "text-muted-foreground truncate italic"
          : "text-foreground/80 max-w-[65ch]",
      )}
    >
      {text}
    </blockquote>
  );
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

  const apply = useMutation({
    mutationFn: () => {
      const { section, index, bullet_index } = finding.location;
      const hashValue = expectedHash ?? finding.content_hash;
      const hash =
        hashValue != null ? { expected_content_hash: hashValue } : {};
      const op =
        section === "summary"
          ? { kind: "replace_summary", value: draft, ...hash }
          : {
              kind: "replace_bullet",
              section,
              index,
              bullet_index,
              value: draft,
              ...hash,
            };
      const path =
        kind === "base"
          ? `/api/base-resumes/${resumeKey}/edits`
          : `/api/applications/${resumeKey}/edits`;
      return apiFetch(path, {
        method: "PATCH",
        body: JSON.stringify({ ops: [op] }),
      });
    },
    onSuccess: () => {
      setApplied(true);
      toast.success("Applied and saved as a new version");
      onApplied();
    },
    onError: (err: Error) => {
      if (err instanceof ApiError && isContentChangedError(err)) {
        toastContentChanged(onReanalyze);
        return;
      }
      toast.error(err instanceof ApiError ? err.message : String(err));
    },
  });

  if (applied) {
    return (
      <p className="text-muted-foreground mt-2 border-t pt-2 text-xs">Applied</p>
    );
  }

  const canApply = draft.trim().length > 0;

  return (
    <div className="mt-2 space-y-2 border-t pt-2">
      <div className="bg-muted/40 rounded-md p-2">
        <DiffText oldText={currentText} newText={draft || suggestion} />
      </div>
      <Textarea
        rows={3}
        aria-label="Rewritten bullet"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        className="max-w-[65ch] text-sm"
        disabled={locked}
      />
      <div className="flex justify-end">
        <Button
          size="sm"
          disabled={!canApply || apply.isPending || locked}
          title={locked ? STALE_APPLY_HINT : undefined}
          className={locked ? LOCKED_BTN : undefined}
          onClick={() => apply.mutate()}
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
    <Badge variant="secondary" className="shrink-0 text-xs capitalize">
      {label}
    </Badge>
  );
}

function CollapsedRow({
  finding,
  quote,
  actionLabel,
  pts,
  onExpand,
  overflow,
}: {
  finding: LintFinding;
  quote: string | null;
  actionLabel: string;
  pts?: number | null;
  onExpand: () => void;
  overflow: ReactNode;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <button
        type="button"
        className="flex min-w-0 flex-1 items-center gap-2 text-left"
        onClick={onExpand}
        aria-expanded={false}
      >
        <Badge
          variant="secondary"
          className="text-muted-foreground shrink-0 text-xs"
        >
          {finding.label}
        </Badge>
        {quote ? (
          <SourceQuote text={quote} truncated />
        ) : (
          <span className="text-muted-foreground truncate text-sm">
            {finding.issue}
          </span>
        )}
        <LevelChip finding={finding} />
        {finding.zone === "hot" && (
          <Badge
            variant="secondary"
            className={`${ATTENTION_BADGE} shrink-0 text-xs`}
          >
            {ATTENTION_BADGE_LABEL}
          </Badge>
        )}
        {pts != null && pts > 0 ? (
        <span className="text-muted-foreground shrink-0 text-xs">
          +{pts} pts
        </span>
      ) : null}
      </button>
      <Button size="xs" variant="outline" onClick={onExpand}>
        {actionLabel}
      </Button>
      {overflow}
    </div>
  );
}

export function FindingGroupHeader({
  title,
  findings,
  id,
}: {
  title: string;
  findings: LintFinding[];
  id: string;
}) {
  const blurb = hoistBlurb(findings);
  const coaching = sharedCoaching(findings);
  return (
    <div id={id} className="scroll-mt-6 space-y-1">
      <h3 className="text-sm font-medium">{title}</h3>
      {blurb ? (
        <p className="text-muted-foreground max-w-[65ch] text-sm">{blurb}</p>
      ) : coaching ? (
        <p className="text-muted-foreground max-w-[65ch] text-sm">
          {coaching.why} {coaching.how}
        </p>
      ) : null}
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
  nScoreable,
  hideHow,
}: FindingCardShared & { finding: LintFinding }) {
  const [expanded, setExpanded] = useState(false);
  const currentText = textAtLocation(data, finding);
  const meta = TYPE_CHIP.fix;
  const pts = potentialPoints(levelNameOf(finding), nScoreable);
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
          pts={pts}
          onExpand={() => setExpanded(true)}
          overflow={overflow}
        />
      </div>
    );
  }

  const showQuote =
    finding.suggestion == null &&
    currentText != null &&
    currentText.trim().length > 0;

  return (
    <ExpandedFindingChrome
      finding={finding}
      cardClassName={meta.card}
      overflow={overflow}
      onCollapse={() => setExpanded(false)}
      quote={showQuote ? currentText : null}
      how={finding.how}
      hideHow={hideHow}
    >
      {finding.suggestion != null && currentText != null && (
        <SuggestionBlock
          finding={finding}
          currentText={currentText}
          suggestion={finding.suggestion}
          kind={kind}
          resumeKey={resumeKey}
          onApplied={onApplied}
          onReanalyze={onReanalyze}
          locked={locked}
        />
      )}
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
  nScoreable,
  hideHow,
  storedAnswer,
}: FindingCardShared & { finding: LintFinding }) {
  const [expanded, setExpanded] = useState(false);
  const [answerDraft, setAnswerDraft] = useState<string | null>(null);
  const [metricDraft, setMetricDraft] = useState<MetricAskValue | null>(null);
  const [localSuggestion, setLocalSuggestion] = useState<
    string | null | undefined
  >(undefined);
  const [notRewritable, setNotRewritable] = useState(false);
  const currentText = textAtLocation(data, finding);
  const meta = TYPE_CHIP.ask;
  const pts = potentialPoints(levelNameOf(finding), nScoreable);
  const metricAsk = isMetricAsk(finding.question);
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

  const context = metricAsk ? metricContextFromValue(metric) : answer.trim();

  const draft = useMutation({
    mutationFn: () => answerAsk(kind, resumeKey, finding.id, context),
    onSuccess: (result) => setLocalSuggestion(result.suggestion),
    onError: (err: Error) => {
      if (err instanceof ApiError && isContentChangedError(err)) {
        toastContentChanged(onReanalyze);
        return;
      }
      if (err instanceof ApiError && err.status === 422) {
        setNotRewritable(true);
      } else {
        toast.error(err instanceof ApiError ? err.message : String(err));
      }
    },
  });

  if (!expanded) {
    return (
      <div className={cn("rounded-md border px-3 py-2", meta.card)}>
        <CollapsedRow
          finding={finding}
          quote={currentText}
          actionLabel="Answer"
          pts={pts}
          onExpand={() => setExpanded(true)}
          overflow={overflow}
        />
      </div>
    );
  }

  const showQuote =
    suggestion == null && currentText != null && currentText.trim().length > 0;

  return (
    <ExpandedFindingChrome
      finding={finding}
      cardClassName={meta.card}
      overflow={overflow}
      onCollapse={() => setExpanded(false)}
      quote={showQuote ? currentText : null}
      how={finding.how}
      hideHow={hideHow}
    >
      {finding.question && (
        <p className="text-muted-foreground mt-1 max-w-[65ch] text-sm italic">
          {finding.question}
        </p>
      )}
      {staleDraft && (
        <p className="text-amber-700 dark:text-amber-400 mt-1 text-xs">
          Saved draft is stale — the bullet changed
        </p>
      )}

      {suggestion != null && currentText != null ? (
        <SuggestionBlock
          finding={finding}
          currentText={currentText}
          suggestion={suggestion}
          kind={kind}
          resumeKey={resumeKey}
          onApplied={onApplied}
          onReanalyze={onReanalyze}
          locked={locked}
        />
      ) : notRewritable || (suggestion != null && currentText == null) ? (
        <p className="text-muted-foreground mt-2 max-w-[65ch] border-t pt-2 text-xs">
          {suggestion != null && currentText == null
            ? suggestion
            : "There's no single bullet to rewrite here. Add this to your resume directly."}
        </p>
      ) : (
        <div className="mt-2 space-y-2 border-t pt-2">
          {metricAsk ? (
            <MetricAskInput
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
              className="max-w-[65ch] text-sm"
              disabled={locked}
            />
          )}
          <div className="flex justify-end">
            <Button
              size="sm"
              disabled={
                context.length === 0 || draft.isPending || locked
              }
              title={locked ? STALE_APPLY_HINT : undefined}
              className={locked ? LOCKED_BTN : undefined}
              onClick={() => draft.mutate()}
            >
              {draft.isPending ? "Drafting…" : "Draft rewrite with this"}
            </Button>
          </div>
        </div>
      )}
    </ExpandedFindingChrome>
  );
}


export function NotesTable({
  notes,
  data,
  kind,
  resumeKey,
  onApplied,
  locked,
  onReanalyze,
}: {
  notes: LintFinding[];
  data?: ResumeData | null;
  kind: "base" | "application";
  resumeKey: string;
  onApplied: () => void;
  locked?: boolean;
  onReanalyze?: () => void;
}) {
  const groups = groupNotesByRule(notes);
  const [skill, setSkill] = useState<string | null>(null);
  const [doneSkills, setDoneSkills] = useState<Set<string>>(new Set());
  const [expandedQuotes, setExpandedQuotes] = useState<Set<string>>(new Set());
  const [condenseDraft, setCondenseDraft] = useState<{
    finding: LintFinding;
    suggestion: string;
    content_hash: string;
  } | null>(null);

  const applyOps = useMutation({
    mutationFn: (ops: Record<string, unknown>[]) => {
      const path =
        kind === "base"
          ? `/api/base-resumes/${resumeKey}/edits`
          : `/api/applications/${resumeKey}/edits`;
      return apiFetch(path, {
        method: "PATCH",
        body: JSON.stringify({ ops }),
      });
    },
    onSuccess: () => {
      toast.success("Applied and saved as a new version");
      onApplied();
    },
    onError: (err: Error) => {
      if (err instanceof ApiError && isContentChangedError(err)) {
        toastContentChanged(onReanalyze);
        return;
      }
      toast.error(err instanceof ApiError ? err.message : String(err));
    },
  });

  const condense = useMutation({
    mutationFn: (finding: LintFinding) =>
      draftRewrite(kind, resumeKey, {
        location: {
          section: finding.location.section,
          index: finding.location.index,
          bullet_index: finding.location.bullet_index,
        },
        objective: "condense",
        expected_content_hash: finding.content_hash ?? undefined,
      }).then((result) => ({ finding, ...result })),
    onSuccess: (result) => setCondenseDraft(result),
    onError: (err: Error) => {
      if (err instanceof ApiError && isContentChangedError(err)) {
        toastContentChanged(onReanalyze);
        return;
      }
      toast.error(err instanceof ApiError ? err.message : String(err));
    },
  });

  return (
    <section id="notes" className="scroll-mt-6 space-y-2">
      <h2 className="text-muted-foreground text-sm font-medium">
        No score impact ({notes.length})
      </h2>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full table-fixed text-sm">
          <tbody>
            {groups.map((group) => {
              const ops =
                data && isMechanicalPunctRule(group.rule)
                  ? punctFixOps(group.rule, group.subjects, data)
                  : null;
              const bulletRows = isBulletSubjectRule(group.rule);
              const undemonstrated = group.rule === "skills.undemonstrated";
              const subjectLine =
                !bulletRows && !undemonstrated && group.subjects.length > 0
                  ? group.subjects.slice(0, 8).join(", ") +
                    (group.subjects.length > 8 ? ", …" : "")
                  : null;
              return (
                <tr key={group.rule} className="border-b last:border-b-0">
                  <td className="px-3 py-2 align-top">
                    <p className="font-medium">
                      {group.title} ({group.count})
                    </p>
                    {undemonstrated && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {group.subjects.map((subject) => {
                          const done = doneSkills.has(subject);
                          return (
                            <button
                              key={subject}
                              type="button"
                              className={cn(
                                "rounded-full border px-2 py-0.5 text-xs",
                                done
                                  ? "text-muted-foreground line-through"
                                  : "hover:bg-muted",
                              )}
                              onClick={() => !done && setSkill(subject)}
                              disabled={done || locked || !data}
                            >
                              {subject}
                              {done ? " · done" : ""}
                            </button>
                          );
                        })}
                      </div>
                    )}
                    {subjectLine && (
                      <p className="text-muted-foreground mt-0.5 max-w-[65ch] text-xs">
                        {subjectLine}
                      </p>
                    )}
                    {group.shapeNote &&
                      group.notes.map((note) => (
                        <p
                          key={note.id}
                          className="text-muted-foreground mt-0.5 max-w-[65ch] text-xs"
                        >
                          {note.issue} {note.how}
                        </p>
                      ))}
                    {bulletRows && (
                      <ul className="mt-1.5 space-y-1">
                        {group.notes.map((note) => {
                          const quote = note.subject ?? note.issue;
                          const open = expandedQuotes.has(note.id);
                          return (
                            <li
                              key={note.id}
                              className="flex items-start justify-between gap-2"
                            >
                              <button
                                type="button"
                                className="text-muted-foreground min-w-0 flex-1 text-left text-xs italic"
                                onClick={() =>
                                  setExpandedQuotes((s) => {
                                    const next = new Set(s);
                                    if (next.has(note.id)) next.delete(note.id);
                                    else next.add(note.id);
                                    return next;
                                  })
                                }
                              >
                                <span className={open ? "whitespace-pre-wrap" : "truncate block"}>
                                  {quote}
                                </span>
                              </button>
                              {group.rule === "bullet.too_long" && (
                                <Button
                                  size="xs"
                                  variant="outline"
                                  disabled={locked || condense.isPending}
                                  title={locked ? STALE_APPLY_HINT : undefined}
                                  className={locked ? LOCKED_BTN : undefined}
                                  onClick={() => condense.mutate(note)}
                                >
                                  Condense
                                </Button>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                    {condenseDraft &&
                      group.notes.some((n) => n.id === condenseDraft.finding.id) &&
                      data && (
                        <div className="mt-2">
                          <SuggestionEditor
                            finding={condenseDraft.finding}
                            currentText={
                              textAtLocation(data, condenseDraft.finding) ??
                              condenseDraft.finding.subject ??
                              ""
                            }
                            suggestion={condenseDraft.suggestion}
                            kind={kind}
                            resumeKey={resumeKey}
                            onApplied={() => {
                              setCondenseDraft(null);
                              onApplied();
                            }}
                            onReanalyze={onReanalyze}
                            locked={locked}
                            expectedHash={condenseDraft.content_hash}
                          />
                        </div>
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
      {skill && data && (
        <DemonstrateSkillDialog
          open={Boolean(skill)}
          onOpenChange={(open) => {
            if (!open) setSkill(null);
          }}
          skill={skill}
          data={data}
          kind={kind}
          resumeKey={resumeKey}
          locked={locked}
          onApplied={() => {
            setDoneSkills((s) => new Set(s).add(skill));
            onApplied();
          }}
          onReanalyze={onReanalyze}
        />
      )}
    </section>
  );
}

function FailedGate({
  gate,
  kind,
  resumeKey,
  onChanged,
}: {
  gate: LintGate;
  kind: "base" | "application";
  resumeKey: string;
  onChanged: () => Promise<void>;
}) {
  const [showReason, setShowReason] = useState(false);
  const [reason, setReason] = useState("");

  const waive = useMutation({
    mutationFn: async () => {
      await waiveGate(kind, resumeKey, gate.id, reason);
      await onChanged();
    },
    onSuccess: () => {
      toast.success("Gate waived");
    },
    onError: (err: Error) =>
      toast.error(err instanceof ApiError ? err.message : String(err)),
  });

  const accent =
    gate.tier === "fatal"
      ? "border-red-500/50 bg-red-500/5"
      : "border-amber-500/50 bg-amber-500/5";

  return (
    <div className={cn("rounded-md border px-3 py-2", accent)}>
      <div className="flex items-center gap-2">
        <Badge
          variant="secondary"
          className={cn(
            "shrink-0 text-xs",
            gate.tier === "fatal"
              ? "bg-red-500/10 text-red-600 dark:text-red-400"
              : "bg-amber-500/10 text-amber-700 dark:text-amber-400",
          )}
        >
          {gate.tier === "fatal" ? "Blocker" : "Serious"}
        </Badge>
        <span className="text-sm font-medium">{gate.label}</span>
      </div>
      {gate.detail && <p className="mt-1 max-w-[65ch] text-sm">{gate.detail}</p>}
      {gate.fix_hint && (
        <p className="text-muted-foreground mt-1 max-w-[65ch] text-xs">
          {gate.fix_hint}
        </p>
      )}

      {showReason ? (
        <div className="mt-2 space-y-2">
          <p className="text-muted-foreground max-w-[65ch] text-xs">
            Waiving lifts this gate&apos;s score cap for this resume. It doesn&apos;t change the
            resume. The gate stays waived across future edits until you unwaive it here.
          </p>
          <Textarea
            rows={2}
            aria-label="Reason for waiving this gate"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. this template is certified elsewhere"
            className="max-w-[65ch] text-sm"
          />
          <div className="flex justify-end gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setShowReason(false)}
              disabled={waive.isPending}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={reason.trim().length === 0 || waive.isPending}
              onClick={() => waive.mutate()}
            >
              {waive.isPending ? "Waiving…" : "Confirm waive"}
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-2 flex justify-end">
          <Button size="sm" variant="outline" onClick={() => setShowReason(true)}>
            Waive…
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
}: {
  gate: LintGate;
  kind: "base" | "application";
  resumeKey: string;
  onChanged: () => Promise<void>;
}) {
  const unwaive = useMutation({
    mutationFn: async () => {
      await unwaiveGate(kind, resumeKey, gate.id);
      await onChanged();
    },
    onSuccess: () => {
      toast.success("Waiver removed");
    },
    onError: (err: Error) =>
      toast.error(err instanceof ApiError ? err.message : String(err)),
  });

  return (
    <div className="text-muted-foreground bg-muted/40 rounded-md border px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate text-sm">{gate.label} (waived)</span>
        <Button
          size="sm"
          variant="ghost"
          disabled={unwaive.isPending}
          onClick={() => unwaive.mutate()}
        >
          {unwaive.isPending ? "…" : "Unwaive"}
        </Button>
      </div>
      {gate.detail && <p className="mt-1 max-w-[65ch] text-sm">{gate.detail}</p>}
      {gate.waiver_reason && (
        <p className="mt-1 text-xs">
          <span className="text-foreground font-medium">Waiver reason: </span>
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
}: {
  gate: LintGate;
  templateId?: string | null;
  onChanged: () => Promise<void>;
}) {
  const certify = useMutation({
    mutationFn: async () => {
      if (!templateId) throw new Error("No template on this resume");
      await validateTemplate(templateId);
      await onChanged();
    },
    onSuccess: () => toast.success("Template certified. Re-running the report."),
    onError: (err: Error) =>
      toast.error(err instanceof ApiError ? err.message : String(err)),
  });

  return (
    <div className="rounded-md border border-border bg-muted/40 px-3 py-2">
      <div className="flex items-center gap-2">
        <Badge variant="secondary" className="bg-muted text-muted-foreground shrink-0 text-xs">
          Not assessed
        </Badge>
        <span className="text-sm font-medium">{gate.label}</span>
      </div>
      <p className="text-muted-foreground mt-1 max-w-[65ch] text-sm">
        {gate.label} — not checked. This template hasn&apos;t been certified.
        {gate.detail ? ` ${gate.detail}` : ""}
      </p>
      <div className="mt-2 flex justify-end">
        {templateId ? (
          <Button
            size="sm"
            variant="outline"
            disabled={certify.isPending}
            onClick={() => certify.mutate()}
          >
            {certify.isPending ? "Certifying…" : "Certify"}
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
  const failed = gates.filter((g) => g.status === "fail");
  const waived = gates.filter((g) => g.status === "waived");
  const notAssessed = gates.filter((g) => g.status === "not_assessed");
  if (failed.length === 0 && waived.length === 0 && notAssessed.length === 0) {
    return null;
  }
  return (
    <div id="gates" className="scroll-mt-6 space-y-2">
      {failed.map((gate) => (
        <FailedGate
          key={gate.id}
          gate={gate}
          kind={kind}
          resumeKey={resumeKey}
          onChanged={onChanged}
        />
      ))}
      {notAssessed.map((gate) => (
        <NotAssessedGate
          key={gate.id}
          gate={gate}
          templateId={templateId}
          onChanged={onChanged}
        />
      ))}
      {waived.map((gate) => (
        <WaivedGate
          key={gate.id}
          gate={gate}
          kind={kind}
          resumeKey={resumeKey}
          onChanged={onChanged}
        />
      ))}
    </div>
  );
}

export function ResolvedFinding({ finding }: { finding: LintFinding }) {
  return (
    <div className="text-muted-foreground rounded-md border border-dashed px-3 py-2 text-sm line-through">
      Resolved · {finding.label}
    </div>
  );
}
