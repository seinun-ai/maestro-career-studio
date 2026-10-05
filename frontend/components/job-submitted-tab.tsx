"use client";

import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ClipboardList } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { LoadErrorState } from "@/components/load-error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { loadErrorDetail } from "@/lib/error-text";
import {
  SOURCE_LABELS,
  fieldAnchor,
  firstFlagged,
  receiptHeading,
  splitVoluntary,
} from "@/lib/filled-answers";
import { formatShortDate } from "@/lib/format-date";
import { isLoadFailure } from "@/lib/query-state";
import type { FilledAnswers, FilledField, FilledStep } from "@/lib/types";

/** Opens the Resume or Q&A tab. Absent while the job has no application: both tabs are locked. */
type OpenTab = (tab: "output" | "qa") => void;

/**
 * What was submitted: every answer the Companion or a connected agent filled into this job's form,
 * the latest per question, with where it came from and what to check. Read-only.
 * `active`: tab panels stay mounted, so the receipt is fetched only once its tab is opened.
 */
export function JobSubmittedTab({
  jobId,
  active,
  onOpenTab,
}: {
  jobId: string;
  active: boolean;
  onOpenTab?: OpenTab;
}) {
  const query = useQuery({
    queryKey: ["filled-answers", jobId],
    queryFn: () => apiFetch<FilledAnswers>(`/api/jobs/${jobId}/filled-answers`),
    enabled: active,
    // The panel stays mounted, so the app's 30s freshness would show a receipt from before a fill:
    // opening the tab always asks again.
    staleTime: 0,
  });
  if (isLoadFailure(query)) {
    return (
      <LoadErrorState
        title="Couldn't load what was submitted."
        detail={loadErrorDetail(query.error)}
        retrying={query.isFetching}
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (!query.data) return <Skeleton className="h-48 w-full" />;
  if (query.data.steps.length === 0) {
    return (
      <EmptyState
        icon={ClipboardList}
        title="Nothing filled yet."
        description="When the Companion or a connected agent fills this job's form, every answer shows here."
      />
    );
  }
  return <Receipt receipt={query.data} onOpenTab={onOpenTab} />;
}

function Receipt({ receipt, onOpenTab }: { receipt: FilledAnswers; onOpenTab?: OpenTab }) {
  const voluntaryId = useId();
  const { steps, voluntary } = splitVoluntary(receipt.steps);
  const first = firstFlagged(steps, voluntary, voluntaryId);
  const date = receipt.captured_at ? formatShortDate(receipt.captured_at) : "";
  return (
    <div className="space-y-4">
      <p className="text-body-medium">
        {receiptHeading(receipt, steps.length, date)}
        {receipt.flag_count > 0 && first ? (
          <>
            {" · "}
            <button
              type="button"
              className="text-warning hover:underline"
              onClick={() => document.getElementById(first)?.focus()}
            >
              {`${receipt.flag_count} to check`}
            </button>
          </>
        ) : null}
      </p>
      {steps.map((step, s) => (
        <StepBlock key={`${step.step}-${s}`} step={step} index={s} onOpenTab={onOpenTab} />
      ))}
      {voluntary.length > 0 ? <Voluntary id={voluntaryId} fields={voluntary} /> : null}
    </div>
  );
}

function StepBlock({
  step,
  index,
  onOpenTab,
}: {
  step: FilledStep;
  index: number;
  onOpenTab?: OpenTab;
}) {
  return (
    <section className="space-y-3 rounded-corner-md border p-4">
      <h3 className="text-title-small">{`Page ${index + 1}`}</h3>
      {step.sections.map((section, k) => (
        <div key={`${section.section}-${k}`} className="space-y-2">
          {section.section ? (
            <p className="text-title-small text-muted-foreground">{section.section}</p>
          ) : null}
          <ul className="space-y-3">
            {section.fields.map((field, f) => (
              <AnswerRow
                key={fieldAnchor(index, k, f)}
                id={fieldAnchor(index, k, f)}
                field={field}
                onOpenTab={onOpenTab}
              />
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

function AnswerRow({
  id,
  field,
  hidden = false,
  onOpenTab,
}: {
  id: string;
  field: FilledField;
  hidden?: boolean;
  onOpenTab?: OpenTab;
}) {
  return (
    <li id={id} tabIndex={-1} className="grid gap-1 outline-none">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-title-small">{field.question}</span>
        <Badge variant="secondary">{SOURCE_LABELS[field.source]}</Badge>
        {field.edited_by_you ? (
          <span className="text-body-small text-muted-foreground">Edited by you</span>
        ) : null}
      </div>
      <AnswerValue field={field} hidden={hidden} onOpenTab={onOpenTab} />
      {field.flags.map((flag) => (
        <p key={flag.id} className="flex items-center gap-1 text-body-small text-warning">
          <AlertTriangle className="size-3.5 shrink-0" aria-hidden />
          {flag.reason}
        </p>
      ))}
    </li>
  );
}

function AnswerValue({
  field,
  hidden,
  onOpenTab,
}: {
  field: FilledField;
  hidden: boolean;
  onOpenTab?: OpenTab;
}) {
  if (field.source === "upload") return <UploadLine field={field} onOpenTab={onOpenTab} />;
  if (hidden) return <p className="text-body-small text-muted-foreground">Answer hidden</p>;
  if (field.eeo && field.answer === null) {
    return (
      <p className="text-body-small text-muted-foreground">
        {field.eeo_answered ? "Answered. Not kept without your consent." : "Not answered."}
      </p>
    );
  }
  if (Array.isArray(field.answer)) {
    return (
      <ul className="list-disc pl-5 text-body-medium">
        {field.answer.map((item, i) => (
          <li key={`${item}-${i}`}>{item}</li>
        ))}
      </ul>
    );
  }
  return <p className="whitespace-pre-wrap text-body-medium">{field.answer ?? "Left blank"}</p>;
}

function UploadLine({ field, onOpenTab }: { field: FilledField; onOpenTab?: OpenTab }) {
  const resume = field.slot !== "cover_letter";
  const name = Array.isArray(field.answer) ? field.answer.join(", ") : (field.answer ?? "a file");
  const label = resume
    ? `Resume attached: ${name}${field.version ? ` (version ${field.version})` : ""}`
    : `Cover letter attached: ${name}`;
  if (!onOpenTab) return <p className="text-body-medium">{label}</p>;
  return (
    <button
      type="button"
      className="text-left text-body-medium text-primary hover:underline"
      onClick={() => onOpenTab(resume ? "output" : "qa")}
    >
      {label}
    </button>
  );
}

/** Voluntary (EEO) answers: kept only under consent, and shown on demand, per visit. */
function Voluntary({ id, fields }: { id: string; fields: FilledField[] }) {
  const [open, setOpen] = useState(false);
  return (
    <section id={id} tabIndex={-1} className="space-y-3 rounded-corner-md border p-4 outline-none">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-title-small">Diversity questions (voluntary)</h3>
        <Button size="sm" variant="outline" aria-expanded={open} onClick={() => setOpen((was) => !was)}>
          {open ? "Hide answers" : "Show answers"}
        </Button>
      </div>
      <ul className="space-y-3">
        {fields.map((field, i) => (
          <AnswerRow key={`${id}-${i}`} id={`${id}-${i}`} field={field} hidden={!open} />
        ))}
      </ul>
    </section>
  );
}
