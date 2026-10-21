"use client";

import { type ReactNode, useId, useLayoutEffect, useRef, useState } from "react";
import { Check, ExternalLink, MessageSquareText } from "lucide-react";

import { QASections } from "@/components/qa-tab";
import { TailoredResumeThumb } from "@/components/tailored-resume-thumb";
import { Button } from "@/components/ui/button";
import { LeadCard, type LeadAction } from "@/components/ui/lead-card";
import { DeltaChip } from "@/components/visual";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { focusIfDropped, focusTarget } from "@/lib/focus";
import { ownershipControlProps } from "@/lib/job-ownership";
import type { Standing } from "@/lib/job-standing";
import type { Application, Job } from "@/lib/types";

const CoverLetterIcon = CONCEPT_ICONS.coverLetter;

/** One of the lead card's rows: an icon, its name, what it holds, and a tonal toggle that opens its editor under it. */
function ApplyRow({
  icon,
  title,
  note,
  closedLabel,
  children,
}: {
  icon: ReactNode;
  title: string;
  note: string | null;
  /** The toggle's word while the editor is closed ("Write", "Answer"); open, it reads Hide. */
  closedLabel: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const titleId = useId();
  const panelId = useId();
  return (
    <div className="border-b last:border-b-0">
      <div className="flex items-center gap-3 py-3.5">
        {icon}
        <h2 id={titleId} className="min-w-0 flex-1 text-title-small">{title}</h2>
        {note ? <span className="text-body-small text-muted-foreground tabular-nums">{note}</span> : null}
        <Button
          variant="tonal"
          size="sm"
          aria-expanded={open}
          aria-controls={panelId}
          aria-describedby={titleId}
          onClick={() => setOpen(!open)}
        >
          {open ? "Hide" : closedLabel}
        </Button>
      </div>
      <div id={panelId} hidden={!open} className="pb-4">
        {children}
      </div>
    </div>
  );
}

/**
 * Step 4, Apply, as the page's lead card: the job's resume (its page, its band and its square), its Match score with
 * the gain over its base resume, where it stands, then the view's one filled button, Open the job post (a new tab on
 * the apply link, else the source link; without either, Mark applied is the filled one), Mark applied (outline, only
 * while a draft) and two rows that open the cover letter and the application questions. History follows the card.
 * No PDF line: step 3 holds the PDF. No button hands the form to the Companion: the web app cannot tell whether the
 * Companion is paired. What was submitted and the application's details are the page's folds.
 */
export function ApplyStep({
  app,
  job,
  readOnly,
  canRequest,
  setStatus,
  statusPending,
  pendingStatus,
  standing,
  score,
  resume,
}: {
  app: Application;
  job: Job;
  readOnly: boolean;
  canRequest: boolean;
  /** The page's one guarded status starter, shared with the header's StatusChip. */
  setStatus: (body: Partial<Application>) => void;
  /** A status change is in flight (from here or the chip), and the status it goes to. */
  statusPending: boolean;
  pendingStatus: string | null;
  /** Where the job stands (lib/job-standing.ts). */
  standing: Standing;
  /** The draft's tailored Match score and its base resume's (lib/job-steps.ts); null without a draft. */
  score: { score: number | null; base: number | null } | null;
  /** The job's base resume: its colour, its name, and whether a tailored score exists for it. */
  resume: { hue: number | null; name: string; tailored: boolean };
}) {
  const postHref = job.apply_url || job.source_url || null;
  const isDraft = (app.status ?? "draft") === "draft";

  // Mark applied: the StatusChip's `applied` transition through the page's one guarded starter. The optimistic
  // status hides the button that held focus, so the lead card's first control (Open the job post) takes it.
  const marked = useRef(false);
  const leadRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!marked.current || isDraft) return;
    marked.current = false;
    focusIfDropped(leadRef.current && focusTarget(leadRef.current));
  }, [isDraft]);
  const markHintId = useId();
  const applying = statusPending && pendingStatus === "applied";
  const mark = () => {
    marked.current = true;
    setStatus({ status: "applied" });
  };

  // The number the card leads with: the tailored score, else the base resume's own; the gain only with both.
  const shown = score?.score ?? score?.base ?? null;
  const gain = score?.score != null && score.base != null ? score.score - score.base : null;

  const action: LeadAction | undefined = postHref
    ? { label: "Open the job post", icon: <ExternalLink className="size-4" />, href: postHref, external: true }
    : isDraft
      ? {
          label: applying ? "Applying…" : "Mark applied",
          icon: <Check className="size-4" />,
          onClick: mark,
          pending: statusPending,
          disabled: !canRequest,
        }
      : undefined;

  return (
    <QASections
      applicationId={app.id}
      readOnly={readOnly}
      arrange={({ questions, coverLetter, history, facts }) => (
        <div className="space-y-6">
          <div ref={leadRef}>
            <LeadCard
              eyebrow={isDraft ? "Ready to apply" : "Your application"}
              media={<TailoredResumeThumb app={app} hue={resume.hue} name={resume.name} tailored={resume.tailored} />}
              action={action}
              secondary={
                postHref && isDraft ? (
                  <Button
                    variant="outline"
                    size="lg"
                    pending={statusPending}
                    {...ownershipControlProps(!canRequest)}
                    aria-describedby={markHintId}
                    onClick={mark}
                  >
                    <Check className="size-4" />
                    {applying ? "Applying…" : "Mark applied"}
                  </Button>
                ) : null
              }
              footer={
                <>
                  {isDraft ? (
                    <p id={markHintId} className="text-muted-foreground text-body-small">
                      {app.applied_at ? "Keeps the applied date you set." : "Sets today as the applied date."}{" "}
                      Interviewing, Offer and Rejected come after, on the status chip.
                    </p>
                  ) : null}
                  <div className="border-t">
                    <ApplyRow
                      icon={<CoverLetterIcon aria-hidden="true" className="size-4 shrink-0" />}
                      title="Cover letter"
                      // Said only once the answers loaded: while they load nobody knows.
                      note={facts.hasCoverLetter === undefined ? null : facts.hasCoverLetter ? "Written" : "Not written"}
                      closedLabel="Write"
                    >
                      {coverLetter}
                    </ApplyRow>
                    <ApplyRow
                      icon={<MessageSquareText aria-hidden="true" className="size-4 shrink-0" />}
                      title="Application questions"
                      note={facts.answered ? `${facts.answered} answered` : null}
                      closedLabel="Answer"
                    >
                      {questions}
                    </ApplyRow>
                  </div>
                </>
              }
            >
              {shown != null ? (
                <div className="flex flex-col gap-1">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="text-display-small tabular-nums">{shown.toFixed(1)}</span>
                    {gain != null ? (
                      <span className="inline-flex items-center gap-1.5 text-body-small text-muted-foreground">
                        <DeltaChip value={gain} />
                        from your base resume
                      </span>
                    ) : null}
                  </div>
                  <span className="text-muted-foreground text-body-medium">Match score</span>
                </div>
              ) : null}
              {standing.text ? <p className="text-body-medium">{standing.text}</p> : null}
            </LeadCard>
          </div>
          {history}
        </div>
      )}
    />
  );
}
