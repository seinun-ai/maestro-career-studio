"use client";

import { useState, type RefObject } from "react";

import { Dropzone, type DropzoneRejection } from "@/components/setup/dropzone";
import { buildSetupSteps } from "@/components/setup/setup-steps";
import { MAX_BYTES, MAX_FILES, useResumeImport } from "@/components/setup/use-resume-import";
import { NumberRoll, ResumeTag, WorkingDots } from "@/components/visual";
import { useBaseResumeColor } from "@/hooks/use-base-resume-label";
import { importCounts } from "@/lib/setup-flow";
import type { ImportReport, SetupStatus } from "@/lib/types";
import { acceptedFilesHint, RESUME_FILE_ACCEPT } from "@/lib/upload-accept";

/**
 * Step 2, your resume: one drop zone. A dropped file goes straight into the resume import (the Import
 * resumes and documents dialog's own flow, `useResumeImport`): WorkingDots while each file is read, then
 * the counts the import's response gives, and only those (lib/setup-flow.ts `importCounts`).
 */
export function SetupResumeStep({
  status,
  headingRef,
}: {
  status: SetupStatus;
  headingRef: RefObject<HTMLHeadingElement | null>;
}) {
  const importer = useResumeImport();
  const [rejected, setRejected] = useState<DropzoneRejection[]>([]);
  const colorOf = useBaseResumeColor();
  // What is there already, in the Getting started card's words (setup-steps.ts).
  const have = buildSetupSteps(status, "/setup").find((step) => step.id === "import");
  const reading = importer.rows.find((row) => row.state === "parsing");
  // Files that did not import, with why: the report's once it is in, else the rows read so far.
  const notImported = [
    ...(importer.report
      ? importer.report.skipped.map((s) => ({ name: s.filename, reason: s.reason }))
      : importer.rows.flatMap((row) => (row.state === "failed" ? [{ name: row.file.name, reason: row.reason }] : []))),
    ...rejected.map((r) => ({ name: r.file.name, reason: r.reason })),
  ];

  return (
    <section aria-labelledby="setup-resume-title" className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h2 id="setup-resume-title" ref={headingRef} tabIndex={-1} className="text-headline-small outline-none">
          Bring your resume
        </h2>
        <p className="max-w-[65ch] text-body-medium text-muted-foreground">
          Each file becomes a base resume, and what it says joins your career history: the source every
          tailored resume is built from.
        </p>
      </div>

      {status.import_resumes.done && !importer.report && have?.detail ? (
        <p className="text-body-medium">You have {have.detail}. Drop another file to add it.</p>
      ) : null}

      <Dropzone
        accept={RESUME_FILE_ACCEPT}
        maxFiles={MAX_FILES}
        maxBytes={MAX_BYTES}
        disabled={importer.busy}
        hint={`${acceptedFilesHint(RESUME_FILE_ACCEPT)} Up to ${MAX_FILES} files, 10 MB each.`}
        onFiles={(picked, skipped) => {
          setRejected(skipped);
          if (picked.length > 0) void importer.run(picked);
        }}
      />

      {importer.busy ? (
        <WorkingDots
          label={
            reading
              ? `Reading ${reading.file.name}`
              : importer.consolidate === "running"
                ? "Adding to your career history"
                : "Reading your resume"
          }
        />
      ) : null}

      {notImported.length > 0 ? (
        <ul className="flex flex-col gap-1 text-body-small">
          {notImported.map((row) => (
            <li key={row.name} className="text-muted-foreground">
              <span className="font-medium text-foreground">{row.name}</span>: {row.reason}
            </li>
          ))}
        </ul>
      ) : null}

      {importer.report && !importer.busy ? <ImportFound report={importer.report} colorOf={colorOf} /> : null}
    </section>
  );
}

/** What the import found: a number per count its response has, then each new base resume by its square. */
function ImportFound({ report, colorOf }: { report: ImportReport; colorOf: (slug: string) => number | null }) {
  const counts = importCounts(report);
  if (counts.length === 0) return null;
  return (
    <div role="status" className="flex flex-col gap-4">
      <ul className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {counts.map((count) => (
          <li key={count.words} className="flex flex-col gap-1 rounded-corner-md bg-surface-container-low px-4 py-3">
            <NumberRoll value={count.n} className="text-headline-small" />
            <span className="text-body-small text-muted-foreground">{count.words}</span>
          </li>
        ))}
      </ul>
      {report.bases.length > 0 ? (
        <ul className="flex flex-wrap gap-x-4 gap-y-2">
          {report.bases.map((base) => (
            <li key={base.slug} className="min-w-0">
              <ResumeTag hue={colorOf(base.slug)}>
                <span className="truncate text-body-medium">{base.display_name}</span>
              </ResumeTag>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
