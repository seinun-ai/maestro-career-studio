"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { RoleCategoryPicker } from "@/components/role-category-picker";
import { Dropzone } from "@/components/setup/dropzone";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { apiFetch } from "@/lib/api";
import type { ImportReport } from "@/lib/types";

const ACCEPT = ".json,.pdf,.docx,.md,.txt,.tex";
const MAX_FILES = 10;
const MAX_BYTES = 10 * 1024 * 1024;

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

  const runImport = useMutation({
    mutationFn: async (picked: File[]) => {
      const form = new FormData();
      picked.forEach((f) => form.append("files", f));
      return apiFetch<ImportReport>("/api/kb/import", { method: "POST", body: form });
    },
    onSuccess: (result) => {
      setReport(result);
      setFiles([]);
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      qc.invalidateQueries({ queryKey: ["kb"] });
      qc.invalidateQueries({ queryKey: ["setup-status"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const reset = () => {
    setFiles([]);
    setRejected([]);
    setReport(null);
    runImport.reset();
  };

  const pointsAdded = report?.kb?.points_approved ?? 0;

  return (
    <>
        {!report ? (
          <div className="space-y-4">
            <Dropzone
              accept={ACCEPT}
              maxFiles={MAX_FILES}
              maxBytes={MAX_BYTES}
              disabled={runImport.isPending}
              hint={`PDF, DOCX, Markdown, text, or the app’s own JSON · up to ${MAX_FILES} files, 10 MB each`}
              onFiles={(picked, skipped) => {
                setFiles(picked);
                setRejected(skipped);
              }}
            />

            {files.length > 0 && (
              <ul className="space-y-1 text-sm">
                {files.map((f) => (
                  <li key={f.name} className="text-muted-foreground truncate">
                    {f.name}
                  </li>
                ))}
              </ul>
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
              <Button variant="ghost" onClick={onClose}>
                Cancel
              </Button>
              <Button
                disabled={!files.length || runImport.isPending}
                onClick={() => runImport.mutate(files)}
              >
                {runImport.isPending
                  ? "Importing…"
                  : files.length
                    ? `Import ${files.length} resume${files.length === 1 ? "" : "s"}`
                    : "Import resumes"}
              </Button>
            </div>
            {runImport.isPending && (
              <p className="text-muted-foreground text-xs">
                Reading each file and merging shared history. This can take a
                minute for several resumes.
              </p>
            )}
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
                  Confirm the target role for each. We only guess when it is unambiguous.
                </p>
                <ul className="space-y-2">
                  {report.bases.map((b) => (
                    <li key={b.slug} className="flex items-center justify-between gap-3">
                      <span className="truncate text-sm">{b.display_name}</span>
                      <RoleCategoryPicker
                        slug={b.slug}
                        roleCategory={b.role_category}
                        roleLabel={b.role_label}
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
