"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { RoleCategoryPicker } from "@/components/role-category-picker";
import { Dropzone } from "@/components/setup/dropzone";
import { RowIcon } from "@/components/setup/row-icon";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { kbImportConsolidate, kbImportResume } from "@/lib/api";
import type { ImportReport } from "@/lib/types";

const ACCEPT = ".json,.pdf,.docx,.md,.txt,.tex";
const MAX_FILES = 10;
const MAX_BYTES = 10 * 1024 * 1024;

type FileRow =
  | { file: File; state: "queued" }
  | { file: File; state: "parsing" }
  | { file: File; state: "done" }
  | { file: File; state: "failed"; reason: string };

type ConsolidateState = "idle" | "queued" | "running" | "done" | "failed";

/** The resume lane's body, without dialog chrome.
 *
 * Split out so the two-lane upload dialog can host it as a tab without a second
 * copy of this flow existing. Remount it (via `key`) to reset.
 *
 * One action does two things — mints a base resume per file AND folds their
 * content into the Career KB. The summary says so in those words: if it did
 * not, the KB would look like it had duplicated the user's resumes, and the
 * trust is gone on first contact.
 */
export function ResumeImportPanel({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [rejected, setRejected] = useState<{ file: File; reason: string }[]>([]);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [rows, setRows] = useState<FileRow[]>([]);
  const [consolidate, setConsolidate] = useState<ConsolidateState>("idle");
  const [busy, setBusy] = useState(false);

  const runImport = async (picked: File[]) => {
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
        const reason = err instanceof Error ? err.message : String(err);
        skipped.push({ filename: file.name, reason });
        setRows((prev) =>
          prev.map((r, idx) => (idx === i ? { file, state: "failed", reason } : r)),
        );
      }
    }

    let kb: ImportReport["kb"] = null;
    if (bases.length > 0) {
      setConsolidate("running");
      try {
        kb = await kbImportConsolidate(bases.map((b) => b.slug));
        setConsolidate("done");
      } catch (err) {
        setConsolidate("failed");
        toast.error(err instanceof Error ? err.message : String(err));
      }
    } else {
      setConsolidate("idle");
    }

    setReport({ bases, skipped, kb });
    setFiles([]);
    qc.invalidateQueries({ queryKey: ["base-resumes"] });
    qc.invalidateQueries({ queryKey: ["kb"] });
    qc.invalidateQueries({ queryKey: ["setup-status"] });
    setBusy(false);
  };

  const reset = () => {
    setFiles([]);
    setRejected([]);
    setReport(null);
    setRows([]);
    setConsolidate("idle");
    setBusy(false);
  };

  const pointsAdded = report?.kb?.points_approved ?? 0;
  const showQueue = busy || (rows.length > 0 && !report);

  return (
    <>
        {!report ? (
          <div className="space-y-4">
            <Dropzone
              accept={ACCEPT}
              maxFiles={MAX_FILES}
              maxBytes={MAX_BYTES}
              disabled={busy}
              hint={`PDF, DOCX, Markdown, text, or the app’s own JSON · up to ${MAX_FILES} files, 10 MB each`}
              onFiles={(picked, skippedFiles) => {
                setFiles(picked);
                setRejected(skippedFiles);
              }}
            />

            {showQueue ? (
              <ul className="space-y-1.5 text-sm">
                {rows.map((row, i) => (
                  <li key={`${row.file.name}-${i}`} className="flex items-start gap-2">
                    <RowIcon state={row.state} />
                    <span className="min-w-0 flex-1">
                      {/* block, not inline: truncate is inert on inline spans
                          (overflow doesn't apply) — SYSTEM.md §8's recurring
                          min-w-0/truncate family. */}
                      <span className="block truncate">{row.file.name}</span>
                      {row.state === "failed" && (
                        <span className="text-muted-foreground block text-xs">
                          {row.reason}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
                {consolidate !== "idle" && (
                  <li className="flex items-start gap-2">
                    <RowIcon
                      state={
                        consolidate === "running"
                          ? "running"
                          : consolidate === "queued"
                            ? "queued"
                            : consolidate
                      }
                    />
                    <span className="text-sm">Building your Career KB…</span>
                  </li>
                )}
              </ul>
            ) : (
              files.length > 0 && (
                <ul className="space-y-1 text-sm">
                  {files.map((f) => (
                    <li key={f.name} className="text-muted-foreground truncate">
                      {f.name}
                    </li>
                  ))}
                </ul>
              )
            )}

            {consolidate === "running" && (
              <div className="space-y-2">
                <Skeleton className="h-3 w-64" />
                <Skeleton className="h-8 w-full" />
              </div>
            )}

            {rejected.length > 0 && (
              <ul className="space-y-1 text-xs">
                {rejected.map((r) => (
                  <li key={r.file.name} className="text-muted-foreground truncate">
                    <span className="font-medium">{r.file.name}</span>: {r.reason}
                  </li>
                ))}
              </ul>
            )}

            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={onClose} disabled={busy}>
                Cancel
              </Button>
              <Button
                disabled={!files.length || busy}
                className="gap-2"
                onClick={() => runImport(files)}
              >
                {busy && <Loader2 className="size-4 animate-spin" />}
                {busy
                  ? "Importing…"
                  : files.length
                    ? `Import ${files.length} resume${files.length === 1 ? "" : "s"}`
                    : "Import resumes"}
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* The disclosure. Both effects, stated plainly, including that the
                imported points are already approved and can be reviewed. */}
            <p className="text-sm">
              Created <strong>{report.bases.length}</strong> base resume
              {report.bases.length === 1 ? "" : "s"}
              {pointsAdded > 0 && (
                <>
                  {" "}
                  and added <strong>{pointsAdded}</strong> approved point
                  {pointsAdded === 1 ? "" : "s"} to your Career KB
                </>
              )}
              .
            </p>

            {report.bases.length > 0 && (
              <div className="space-y-2">
                <p className="text-muted-foreground text-xs">
                  Confirm the target role for each — suggestions are guesses.
                </p>
                <ul className="space-y-2">
                  {report.bases.map((b) => (
                    <li key={b.slug} className="flex items-center justify-between gap-3">
                      <span className="truncate text-sm">{b.display_name}</span>
                      <RoleCategoryPicker
                        slug={b.slug}
                        roleCategory={b.role_category}
                        roleLabel={b.role_label}
                        proposed={b.proposed}
                        className="w-48 shrink-0"
                      />
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {report.skipped.length > 0 && (
              <div className="space-y-1">
                <p className="text-sm font-medium">Skipped</p>
                <ul className="text-muted-foreground space-y-1 text-xs">
                  {report.skipped.map((s) => (
                    <li key={s.filename}>
                      <span className="font-medium">{s.filename}</span>: {s.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={reset}>
                Import more
              </Button>
              <Button onClick={onClose}>Done</Button>
            </div>
          </div>
        )}
    </>
  );
}

/** Standalone resume import, for callers that want only this lane. */
export function ResumeImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Import your resumes</DialogTitle>
          <DialogDescription>
            Each file becomes a base resume you can tailor, and its content is
            added to your Career Knowledge Base.
          </DialogDescription>
        </DialogHeader>
        {/* Remount on each open so a previous run's report does not persist. */}
        <ResumeImportPanel
          key={open ? "open" : "closed"}
          onClose={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
