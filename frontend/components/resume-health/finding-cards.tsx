"use client";

import { useState } from "react";
import {
  ATTENTION_BADGE,
  ATTENTION_BADGE_LABEL,
} from "@/components/attention-zone";
import { useMutation } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { answerAsk, ApiError, apiFetch, unwaiveGate, waiveGate } from "@/lib/api";
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

function ClassificationOverride({
  finding,
  onChanged,
}: {
  finding: LintFinding;
  onChanged?: ClassificationOverrideHandler;
}) {
  const [open, setOpen] = useState(false);
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
      setOpen(false);
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
    <div className="mt-2 border-t pt-1.5">
      <button
        type="button"
        className="text-muted-foreground hover:text-foreground flex items-center gap-1 text-xs"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="size-3" />
        ) : (
          <ChevronRight className="size-3" />
        )}
        {finding.classification_source === "override"
          ? `Overridden as ${currentLabel}`
          : `Override classification · ${currentLabel}`}
      </button>
      {open && (
        <div className="mt-2 space-y-2 rounded-md bg-muted/30 p-2">
          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={level}
              onValueChange={(value) =>
                setLevel(value as EvidenceLevel | "automatic")
              }
              disabled={save.isPending}
            >
              <SelectTrigger size="sm" className="w-40" aria-label="Evidence level">
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
            <span className="text-muted-foreground text-xs">
              Current: {currentLabel}
            </span>
          </div>
          {level !== "automatic" && (
            <Textarea
              rows={2}
              aria-label="Reason for overriding the evidence level · optional"
              value={reason}
              maxLength={500}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Reason · optional"
              className="text-sm"
              disabled={save.isPending}
            />
          )}
          <div className="flex justify-end gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setOpen(false)}
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
          </div>
        </div>
      )}
    </div>
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
    <p className="text-sm leading-relaxed">
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
export function textAtLocation(
  data: ResumeData,
  finding: LintFinding,
): string | null {
  const { section, index, bullet_index } = finding.location;
  if (section === "summary") return data.summary ?? "";
  if (index == null || bullet_index == null) return null;
  const entries =
    section === "experience"
      ? data.experience
      : section === "projects"
        ? data.projects
        : section === "education"
          ? data.education
          : null;
  return entries?.[index]?.bullets?.[bullet_index] ?? null;
}

/**
 * The text the finding is about, quoted so the card is answerable without
 * hunting through the resume. Rendered only while no diff is on screen —
 * once a suggestion's tracked-changes view appears, that carries the text.
 */
function SourceQuote({ text }: { text: string }) {
  return (
    <blockquote className="text-muted-foreground border-muted-foreground/30 mt-1.5 border-l-2 pl-2 text-sm italic">
      {text}
    </blockquote>
  );
}

function DetailsDisclosure({ finding }: { finding: LintFinding }) {
  const [open, setOpen] = useState(false);
  if (!finding.why && !finding.how) return null;
  return (
    <>
      <button
        type="button"
        className="text-muted-foreground hover:text-foreground mt-1 flex items-center gap-1 text-xs"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ChevronDown className="size-3" />
        ) : (
          <ChevronRight className="size-3" />
        )}
        Why this matters & how to improve
      </button>
      {open && (
        <div className="text-muted-foreground mt-1 space-y-1 text-xs">
          {finding.why && (
            <p>
              <span className="text-foreground font-medium">Why: </span>
              {finding.why}
            </p>
          )}
          {finding.how && (
            <p>
              <span className="text-foreground font-medium">How: </span>
              {finding.how}
            </p>
          )}
        </div>
      )}
    </>
  );
}

/**
 * Shared diff + editable + Apply block, used by both `fix` findings and the
 * suggestion an `ask` finding produces once answered. Applies through /edits.
 */
export function SuggestionEditor({
  finding,
  currentText,
  suggestion,
  kind,
  resumeKey,
  onApplied,
}: {
  finding: LintFinding;
  currentText: string;
  suggestion: string;
  kind: "base" | "application";
  resumeKey: string;
  onApplied: () => void;
}) {
  const [draft, setDraft] = useState(suggestion);
  const [applied, setApplied] = useState(false);

  const apply = useMutation({
    mutationFn: () => {
      const { section, index, bullet_index } = finding.location;
      const op =
        section === "summary"
          ? { kind: "replace_summary", value: draft }
          : {
              kind: "replace_bullet",
              section,
              index,
              bullet_index,
              value: draft,
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
    onError: (err: Error) =>
      toast.error(err instanceof ApiError ? err.message : String(err)),
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
        className="text-sm"
      />
      <div className="flex justify-end">
        <Button
          size="sm"
          disabled={!canApply || apply.isPending}
          onClick={() => apply.mutate()}
        >
          {apply.isPending ? "Applying…" : "Apply suggestion"}
        </Button>
      </div>
    </div>
  );
}

function CardHeader({
  finding,
  meta,
}: {
  finding: LintFinding;
  meta: { label: string; chip: string };
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-2">
        <Badge variant="secondary" className={cn("shrink-0 text-xs", meta.chip)}>
          {meta.label}
        </Badge>
        <span className="truncate text-xs font-medium">{finding.label}</span>
      </div>
      {finding.zone === "hot" && (
        <Badge
          variant="secondary"
          className={`${ATTENTION_BADGE} shrink-0 text-xs`}
        >
          {ATTENTION_BADGE_LABEL}
        </Badge>
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
}: {
  finding: LintFinding;
  data: ResumeData;
  kind: "base" | "application";
  resumeKey: string;
  onApplied: () => void;
  onClassificationChanged?: ClassificationOverrideHandler;
}) {
  const currentText = textAtLocation(data, finding);
  const meta = TYPE_CHIP.fix;
  // Once a suggestion exists the diff below repeats the current text; the
  // plain quote is only needed while there is no diff on screen.
  const showQuote =
    finding.suggestion == null &&
    currentText != null &&
    currentText.trim().length > 0;

  return (
    <div className={cn("rounded-md border px-3 py-2", meta.card)}>
      <CardHeader finding={finding} meta={meta} />
      {showQuote && <SourceQuote text={currentText} />}
      <p className="mt-1.5 text-sm">{finding.issue}</p>
      <DetailsDisclosure finding={finding} />
      <ClassificationOverride
        finding={finding}
        onChanged={onClassificationChanged}
      />
      {finding.suggestion != null && currentText != null && (
        <SuggestionEditor
          finding={finding}
          currentText={currentText}
          suggestion={finding.suggestion}
          kind={kind}
          resumeKey={resumeKey}
          onApplied={onApplied}
        />
      )}
    </div>
  );
}

export function AskCard({
  finding,
  data,
  kind,
  resumeKey,
  onApplied,
  onClassificationChanged,
}: {
  finding: LintFinding;
  data: ResumeData;
  kind: "base" | "application";
  resumeKey: string;
  onApplied: () => void;
  onClassificationChanged?: ClassificationOverrideHandler;
}) {
  const [answer, setAnswer] = useState("");
  const [suggestion, setSuggestion] = useState<string | null>(null);
  const [notRewritable, setNotRewritable] = useState(false);
  const currentText = textAtLocation(data, finding);
  const meta = TYPE_CHIP.ask;
  // The question refers to this text — quote it so the ask is answerable.
  // Once a drafted suggestion appears, its diff replaces the quote.
  const showQuote =
    suggestion == null && currentText != null && currentText.trim().length > 0;

  const draft = useMutation({
    mutationFn: () => answerAsk(kind, resumeKey, finding.id, answer),
    onSuccess: (result) => setSuggestion(result.suggestion),
    onError: (err: Error) => {
      if (err instanceof ApiError && err.status === 422) {
        setNotRewritable(true);
      } else {
        toast.error(err instanceof ApiError ? err.message : String(err));
      }
    },
  });

  return (
    <div className={cn("rounded-md border px-3 py-2", meta.card)}>
      <CardHeader finding={finding} meta={meta} />
      {showQuote && <SourceQuote text={currentText} />}
      <p className="mt-1.5 text-sm">{finding.issue}</p>
      {finding.question && (
        <p className="text-muted-foreground mt-1 text-sm italic">
          {finding.question}
        </p>
      )}
      <DetailsDisclosure finding={finding} />
      <ClassificationOverride
        finding={finding}
        onChanged={onClassificationChanged}
      />

      {suggestion != null && currentText != null ? (
        <SuggestionEditor
          finding={finding}
          currentText={currentText}
          suggestion={suggestion}
          kind={kind}
          resumeKey={resumeKey}
          onApplied={onApplied}
        />
      ) : notRewritable || (suggestion != null && currentText == null) ? (
        <p className="text-muted-foreground mt-2 border-t pt-2 text-xs">
          {suggestion != null && currentText == null
            ? suggestion
            : "There's no single bullet to rewrite here. Add this to your resume directly."}
        </p>
      ) : (
        <div className="mt-2 space-y-2 border-t pt-2">
          <Textarea
            rows={2}
            aria-label="Your answer"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder="Your answer…"
            className="text-sm"
          />
          <div className="flex justify-end">
            <Button
              size="sm"
              disabled={answer.trim().length === 0 || draft.isPending}
              onClick={() => draft.mutate()}
            >
              {draft.isPending ? "Drafting…" : "Draft rewrite with this"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function NoteItem({
  finding,
  data,
  onClassificationChanged,
}: {
  finding: LintFinding;
  /** When supplied, an expanded note quotes the bullet it refers to. */
  data?: ResumeData;
  onClassificationChanged?: ClassificationOverrideHandler;
}) {
  const [open, setOpen] = useState(false);
  // The bullet the note is about, when its location resolves to one. Notes
  // without a bullet location (e.g. a section-level note) have no quote.
  const quote = data ? textAtLocation(data, finding) : null;
  return (
    <div className="text-muted-foreground rounded-md border px-3 py-2">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          {open ? (
            <ChevronDown className="size-3 shrink-0" />
          ) : (
            <ChevronRight className="size-3 shrink-0" />
          )}
          <span className="truncate text-xs font-medium">{finding.label}</span>
        </span>
        <span className="shrink-0 rounded-md bg-slate-500/10 px-1.5 py-0.5 text-[10px]">
          No score impact
        </span>
      </button>
      {open && <p className="mt-1.5 text-sm">{finding.issue}</p>}
      {open && quote != null && quote.trim().length > 0 && (
        <SourceQuote text={quote} />
      )}
      {open && (
        <ClassificationOverride
          finding={finding}
          onChanged={onClassificationChanged}
        />
      )}
    </div>
  );
}

/** Gate banner — driven by report.gates (only fail + waived render here). */
function FailedGate({
  gate,
  kind,
  resumeKey,
  onChanged,
}: {
  gate: LintGate;
  kind: "base" | "application";
  resumeKey: string;
  onChanged: () => void;
}) {
  const [showReason, setShowReason] = useState(false);
  const [reason, setReason] = useState("");

  const waive = useMutation({
    mutationFn: () => waiveGate(kind, resumeKey, gate.id, reason),
    onSuccess: () => {
      toast.success("Gate waived");
      onChanged();
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
      {gate.detail && <p className="mt-1 text-sm">{gate.detail}</p>}

      {showReason ? (
        <div className="mt-2 space-y-2">
          <Textarea
            rows={2}
            aria-label="Reason for waiving this gate"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why is this acceptable? (recorded with the waiver)"
            className="text-sm"
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
  onChanged: () => void;
}) {
  const unwaive = useMutation({
    mutationFn: () => unwaiveGate(kind, resumeKey, gate.id),
    onSuccess: () => {
      toast.success("Waiver removed");
      onChanged();
    },
    onError: (err: Error) =>
      toast.error(err instanceof ApiError ? err.message : String(err)),
  });

  return (
    <div className="text-muted-foreground bg-muted/40 flex items-center justify-between gap-2 rounded-md border px-3 py-2">
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
  );
}

export function GateBanner({
  gates,
  kind,
  resumeKey,
  onChanged,
}: {
  gates: LintGate[];
  kind: "base" | "application";
  resumeKey: string;
  onChanged: () => void;
}) {
  const failed = gates.filter((g) => g.status === "fail");
  const waived = gates.filter((g) => g.status === "waived");
  if (failed.length === 0 && waived.length === 0) return null;
  return (
    <div className="space-y-2">
      {failed.map((gate) => (
        <FailedGate
          key={gate.id}
          gate={gate}
          kind={kind}
          resumeKey={resumeKey}
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
