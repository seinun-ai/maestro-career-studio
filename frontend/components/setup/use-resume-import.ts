"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { kbImportConsolidate, kbImportResume } from "@/lib/api";
import { couldnt, errorDetail } from "@/lib/error-text";
import { notifyRenderNote } from "@/lib/render-note";
import type { ImportReport } from "@/lib/types";

/** The import's limits: ten files a run, 10 MB each (the backend's own cap). */
export const MAX_FILES = 10;
export const MAX_BYTES = 10 * 1024 * 1024;

export type ImportFileRow =
  | { file: File; state: "queued" }
  | { file: File; state: "parsing" }
  | { file: File; state: "done" }
  | { file: File; state: "failed"; reason: string };

export type ConsolidateState = "idle" | "queued" | "running" | "done" | "failed";

/**
 * The resume import, one copy for its two screens: the Import resumes and documents dialog's resume lane
 * (components/career/resume-import-dialog.tsx) and Setup's resume step. Each file becomes a base resume
 * (`POST /api/kb/import?consolidate=false`, one at a time so each row can say how it went), then one
 * consolidation pass adds what they say to career history (`POST /api/kb/import/consolidate`). The report
 * is the two responses together: the counts a screen shows come from it and nowhere else.
 */
export function useResumeImport() {
  const qc = useQueryClient();
  const [report, setReport] = useState<ImportReport | null>(null);
  const [rows, setRows] = useState<ImportFileRow[]>([]);
  const [consolidate, setConsolidate] = useState<ConsolidateState>("idle");
  const [busy, setBusy] = useState(false);

  const run = async (picked: File[]) => {
    setBusy(true);
    setRows(picked.map((file) => ({ file, state: "queued" as const })));
    setConsolidate(picked.length ? "queued" : "idle");
    const bases: ImportReport["bases"] = [];
    const skipped: ImportReport["skipped"] = [];

    for (let i = 0; i < picked.length; i++) {
      const file = picked[i];
      setRows((prev) => prev.map((r, idx) => (idx === i ? { file, state: "parsing" } : r)));
      try {
        const result = await kbImportResume(file, false);
        bases.push(...result.bases);
        skipped.push(...result.skipped);
        setRows((prev) => prev.map((r, idx) => (idx === i ? { file, state: "done" } : r)));
      } catch (err) {
        const reason = errorDetail(err) ?? "Couldn't read this file.";
        skipped.push({ filename: file.name, reason });
        setRows((prev) =>
          prev.map((r, idx) => (idx === i ? { file, state: "failed", reason } : r)),
        );
      }
    }

    // Every base rendered on the same host through the same default template,
    // so their notes are one string: say it once, not once per file.
    notifyRenderNote(bases.find((b) => b.render_note));

    let kb: ImportReport["kb"] = null;
    if (bases.length > 0) {
      setConsolidate("running");
      try {
        kb = await kbImportConsolidate(bases.map((b) => b.slug));
        setConsolidate("done");
      } catch (err) {
        setConsolidate("failed");
        toast.error(couldnt("import the resumes", err));
      }
    } else {
      setConsolidate("idle");
    }

    setReport({ bases, skipped, kb });
    qc.invalidateQueries({ queryKey: ["base-resumes"] });
    qc.invalidateQueries({ queryKey: ["kb"] });
    qc.invalidateQueries({ queryKey: ["setup-status"] });
    setBusy(false);
  };

  const reset = () => {
    setReport(null);
    setRows([]);
    setConsolidate("idle");
    setBusy(false);
  };

  return { report, rows, consolidate, busy, run, reset };
}
