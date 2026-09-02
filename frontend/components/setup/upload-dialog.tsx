"use client";

import { useState } from "react";
import Link from "next/link";
import { ResumeImportPanel } from "@/components/career/resume-import-dialog";
import { Dropzone } from "@/components/setup/dropzone";
import { RowIcon } from "@/components/setup/row-icon";
import { useDocumentQueue } from "@/components/setup/use-document-queue";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DOCUMENT_ACCEPT } from "@/lib/upload-accept";

const DOC_ACCEPT = DOCUMENT_ACCEPT;
const DOC_MAX_FILES = 10;
/** The backend's own cap (career_kb.ingest_document_first). */
const DOC_MAX_BYTES = 10 * 1024 * 1024;

/** Cover letters, certifications, reports — anything that is evidence about you
 *  but is not itself a resume. */
function DocumentLane({ onClose }: { onClose: () => void }) {
  const { rows, status, summary, add, run, cancel, reset } = useDocumentQueue();
  const busy = status === "running";
  const finished = status === "finished" && rows.length > 0;

  return (
    <div className="space-y-4">
      {/* State the outcome BEFORE the upload. These become drafts to review,
          not base resumes — conflating the two is the failure this lane split
          exists to prevent. */}
      <p className="text-muted-foreground text-xs">
        Each file is read for evidence about your career and filed against the
        matching Career KB entry, as <strong>draft points you review</strong>.
        These do not become base resumes.
      </p>

      <Dropzone
        accept={DOC_ACCEPT}
        maxFiles={DOC_MAX_FILES}
        maxBytes={DOC_MAX_BYTES}
        disabled={busy}
        hint={`PDF, DOCX, Markdown, text, or images · up to ${DOC_MAX_FILES} files, 10 MB each`}
        onFiles={(files, rejected) => add(files, rejected)}
      />

      {rows.length > 0 && (
        <ul className="space-y-1.5 text-sm">
          {rows.map((row, i) => (
            <li key={`${row.file.name}-${i}`} className="flex items-start gap-2">
              <RowIcon state={row.state} />
              <span className="min-w-0 flex-1">
                <span className="truncate">{row.file.name}</span>
                {row.state === "done" && (
                  <span className="text-muted-foreground block text-xs">
                    {row.created ? "New" : "Matched"} {row.kind} “{row.entity}” ·{" "}
                    {row.points} draft point{row.points === 1 ? "" : "s"}
                  </span>
                )}
                {row.state === "failed" && (
                  <span className="text-muted-foreground block text-xs">
                    {row.reason}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      {status === "halted" && summary.remaining > 0 && (
        <p className="text-muted-foreground text-xs">
          Stopped with {summary.remaining} file
          {summary.remaining === 1 ? "" : "s"} left. Anything already added is
          saved. Retry picks up where it stopped.
        </p>
      )}

      {finished && (
        <p className="text-sm">
          Added <strong>{summary.points}</strong> draft point
          {summary.points === 1 ? "" : "s"} across{" "}
          <strong>{summary.entitiesCreated + summary.entitiesMatched}</strong>{" "}
          entr{summary.entitiesCreated + summary.entitiesMatched === 1 ? "y" : "ies"}
          {summary.failed > 0 && <> · {summary.failed} skipped</>}.{" "}
          <Link className="underline" href="/career#kb-inbox" onClick={onClose}>
            Review them
          </Link>
          .
        </p>
      )}

      <div className="flex justify-end gap-2">
        {busy ? (
          <Button variant="outline" onClick={cancel}>
            Stop after this file
          </Button>
        ) : (
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        )}
        {finished ? (
          <Button variant="outline" onClick={reset}>
            Add more
          </Button>
        ) : (
          <Button disabled={busy || summary.remaining === 0} onClick={() => void run()}>
            {busy
              ? "Reading…"
              : status === "halted"
                ? `Retry ${summary.remaining}`
                : summary.remaining
                  ? `Add ${summary.remaining} document${summary.remaining === 1 ? "" : "s"}`
                  : "Add documents"}
          </Button>
        )}
      </div>

      {busy && (
        <p className="text-muted-foreground text-xs">
          Read one at a time, a few seconds each, so the same role is never
          created twice.
        </p>
      )}
    </div>
  );
}

/**
 * Upload, in two explicit lanes.
 *
 * The lanes are separate because the backend verbs differ in outcome: a resume
 * becomes a base resume you can tailor, while any other document becomes draft
 * KB points you review. Auto-classifying would sometimes turn a cover letter
 * into a base resume, and the user must know which they are getting BEFORE the
 * LLM runs.
 */
export function UploadDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [lane, setLane] = useState("resumes");
  const close = () => onOpenChange(false);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Add your documents</DialogTitle>
          <DialogDescription>
            Resumes become base resumes you can tailor. Everything else becomes
            evidence in your Career Knowledge Base.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={lane} onValueChange={(v) => setLane(v as string)}>
          <TabsList>
            <TabsTrigger value="resumes">Resumes</TabsTrigger>
            <TabsTrigger value="documents">Other documents</TabsTrigger>
          </TabsList>
          <TabsContent value="resumes" className="pt-4">
            {/* Remount per open so a previous run's report does not persist. */}
            <ResumeImportPanel key={open ? "open" : "closed"} onClose={close} />
          </TabsContent>
          <TabsContent value="documents" className="pt-4">
            <DocumentLane onClose={close} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
