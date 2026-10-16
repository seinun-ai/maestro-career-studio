"use client";

import { type ReactNode, type RefObject, useId, useLayoutEffect, useRef, useState } from "react";
import { Check, ChevronDown, ExternalLink, FileText } from "lucide-react";

import { ApplicationDetails } from "@/components/application-panel";
import { SubmittedLatest } from "@/components/job-submitted-tab";
import { QASections } from "@/components/qa-tab";
import { PdfFileLine } from "@/components/pdf-file-line";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { focusIfDropped } from "@/lib/focus";
import { ownershipControlProps } from "@/lib/job-ownership";
import type { StepKey } from "@/lib/job-steps";
import type { Application, Job } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Step 4, Apply, inside one card. Left: Open the job post and apply, the application's questions and their
 * history, What was submitted in full once opened, Mark applied while the job is a draft, and the Application
 * details disclosure. Right: the PDF line, the Cover letter card and, once something was filled, What was
 * submitted's latest answers. No button hands the form to the Companion: the web app cannot tell whether
 * the Companion is paired.
 */
export function ApplyStep({
  app,
  job,
  jobId,
  readOnly,
  canRequest,
  setStatus,
  statusPending,
  pendingStatus,
  active,
  receipt,
  receiptRef,
  receiptFirst,
  onOpenStep,
}: {
  app: Application;
  job: Job;
  jobId: string;
  readOnly: boolean;
  canRequest: boolean;
  /** The page's one guarded status starter, shared with the header's StatusChip. */
  setStatus: (body: Partial<Application>) => void;
  /** A status change is in flight (from here or the chip), and the status it goes to. */
  statusPending: boolean;
  pendingStatus: string | null;
  /** Step 4 is the one showing: the receipt's query runs only then. */
  active: boolean;
  /** The page's What was submitted section, or null while nothing was filled. */
  receipt: ReactNode;
  receiptRef: RefObject<HTMLElement | null>;
  /** A ?tab=submitted link opened the page: the receipt is open, above everything else. */
  receiptFirst: boolean;
  onOpenStep: (key: StepKey) => void;
}) {
  const postHref = job.apply_url || job.source_url || null;
  const isDraft = (app.status ?? "draft") === "draft";

  // The whole receipt: closed until the card's link opens it (open, and first, when a link asked for it).
  const [receiptOpen, setReceiptOpen] = useState(receiptFirst);
  const receiptId = useId();
  const jumpToReceipt = useRef(false);
  useLayoutEffect(() => {
    if (!jumpToReceipt.current || !receiptOpen) return;
    jumpToReceipt.current = false;
    receiptRef.current?.scrollIntoView({ block: "start" });
    receiptRef.current?.focus({ preventScroll: true });
  }, [receiptOpen, receiptRef]);
  const toggleReceipt = () => {
    jumpToReceipt.current = !receiptOpen;
    setReceiptOpen(!receiptOpen);
  };
  const receiptBlock = receipt ? (
    <div id={receiptId} hidden={!receiptOpen}>
      {receipt}
    </div>
  ) : null;

  // Mark applied: the StatusChip's `applied` transition through the page's one guarded starter. The optimistic
  // status hides the button that held focus, so the Application details toggle below takes it.
  const marked = useRef(false);
  const detailsToggle = useRef<HTMLButtonElement>(null);
  useLayoutEffect(() => {
    if (!marked.current || isDraft) return;
    marked.current = false;
    focusIfDropped(detailsToggle.current);
  }, [isDraft]);
  const markHintId = useId();
  const applying = statusPending && pendingStatus === "applied";

  const [detailsOpen, setDetailsOpen] = useState(false);
  const detailsId = useId();

  return (
    <QASections
      applicationId={app.id}
      readOnly={readOnly}
      arrange={({ questions, coverLetter, history }) => (
        <Card>
          <CardContent className="flex flex-wrap items-start gap-6">
            <div className="min-w-0 flex-[1_1_28rem] space-y-4">
              {receiptFirst ? receiptBlock : null}
              {postHref ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    nativeButton={false}
                    render={<a href={postHref} target="_blank" rel="noopener noreferrer" />}
                  >
                    <ExternalLink className="size-4" />
                    Open the job post and apply
                  </Button>
                </div>
              ) : null}
              {questions}
              {history}
              {receiptFirst ? null : receiptBlock}
              {isDraft ? (
                <div className="space-y-2 border-t pt-4">
                  <h2 className="text-title-small">Done applying?</h2>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <Button
                      variant={postHref ? "tonal" : "default"}
                      pending={statusPending}
                      {...ownershipControlProps(!canRequest)}
                      aria-describedby={markHintId}
                      onClick={() => {
                        marked.current = true;
                        setStatus({ status: "applied" });
                      }}
                    >
                      <Check className="size-4" />
                      {applying ? "Applying…" : "Mark applied"}
                    </Button>
                    <p id={markHintId} className="text-muted-foreground text-body-small">
                      {app.applied_at ? "Keeps the applied date you set." : "Sets today as the applied date."}{" "}
                      Interviewing, Offer and Rejected come after, on the status chip.
                    </p>
                  </div>
                </div>
              ) : null}
              <div className="border-t pt-4">
                {/* The page's disclosure toggle (step 3's Score breakdown): a small link button with its chevron. */}
                <Button
                  ref={detailsToggle}
                  variant="link"
                  size="sm"
                  className="h-auto px-1"
                  aria-expanded={detailsOpen}
                  aria-controls={detailsId}
                  onClick={() => setDetailsOpen(!detailsOpen)}
                >
                  Application details
                  <ChevronDown
                    aria-hidden="true"
                    className={cn("size-3.5 transition-[rotate] duration-short3 ease-standard", detailsOpen && "rotate-180")}
                  />
                </Button>
                <div id={detailsId} hidden={!detailsOpen} className="pt-3">
                  {detailsOpen ? (
                    <ApplicationDetails
                      app={app}
                      jobId={jobId}
                      jobSourceUrl={job.source_url}
                      readOnly={readOnly}
                      canRequest={canRequest}
                    />
                  ) : null}
                </div>
              </div>
            </div>

            <div className="min-w-0 max-w-[360px] flex-[1_1_300px] space-y-4">
              {app.pdf_path ? (
                <PdfFileLine app={app} />
              ) : (
                <div className="bg-surface-container-low flex flex-wrap items-center gap-x-2 gap-y-1 rounded-corner-md px-4 py-2">
                  <FileText aria-hidden="true" className="text-muted-foreground size-4 shrink-0" />
                  <span className="text-body-medium">No PDF yet</span>
                  {/* A job with no resume of its own (marked applied as is) has nothing step 3 can make a PDF of. */}
                  {app.customized_json ? (
                    <Button variant="link" size="sm" className="ml-auto h-auto px-0" onClick={() => onOpenStep("output")}>
                      Create the PDF on Tailored resume
                    </Button>
                  ) : null}
                </div>
              )}
              {coverLetter}
              {receipt ? (
                <Card>
                  <CardHeader>
                    <CardTitle>
                      <h2>What was submitted</h2>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <SubmittedLatest
                      jobId={jobId}
                      active={active}
                      receiptId={receiptId}
                      receiptOpen={receiptOpen}
                      onToggleReceipt={toggleReceipt}
                    />
                  </CardContent>
                </Card>
              ) : null}
            </div>
          </CardContent>
        </Card>
      )}
    />
  );
}
