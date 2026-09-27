"use client";

import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useConfirmLeave } from "@/components/guarded-link";
import { fetchBase, rowText, sameWhere, type PassRow } from "@/components/resume-health/pass-rows";
import { focusIfDropped } from "@/hooks/use-focus-return";
import { useSingleFlight } from "@/hooks/use-single-flight";
import {
  ApiError,
  applyResumeEdits,
  listResumeVersions,
  restoreResumeVersion,
  runLintReport,
} from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import {
  batchEditOps,
  isContentChangedError,
  latestVersionNumber,
  saveBatch,
  staleFindingIds,
  textAtLocation,
  type PassStatus,
} from "@/lib/health-report";
import { notifyRenderNote, notifyRenderOutcome } from "@/lib/render-note";

type Rows = Dispatch<SetStateAction<PassRow[] | null>>;
type Batch = { sent: PassRow[]; v0: number };

/**
 * The question pass's writes to the resume: Accept (one row or all shown) as ONE hash-guarded
 * `/edits` call through `saveBatch`, the toast's Undo (a restore that lands only over this write),
 * and Write it again (the check re-run for one changed row). Rows move through `setRows`.
 */
export function usePassWrites({
  kind,
  resumeKey,
  setRows,
}: {
  kind: "base";
  resumeKey: string;
  setRows: Rows;
}) {
  const qc = useQueryClient();
  const router = useRouter();
  const confirmLeave = useConfirmLeave();

  const setStatus = (keys: Set<string>, status: PassStatus, only?: PassStatus) =>
    setRows(
      (current) =>
        current &&
        current.map((row) => (keys.has(row.key) && (!only || row.status === only) ? { ...row, status } : row)),
    );
  const keysOf = (rows: PassRow[]) => new Set(rows.map((row) => row.key));
  const invalidateAfterWrite = () => {
    qc.invalidateQueries({ queryKey: ["base-resumes"] });
    qc.invalidateQueries({ queryKey: ["resume-versions"] });
    qc.invalidateQueries({ queryKey: ["resume-lint", kind, resumeKey] });
  };

  // ONE /edits call for the whole batch: one op per row, each with its hash. One transaction, one version.
  const writeBatch = (sent: PassRow[]) =>
    applyResumeEdits(kind, resumeKey, batchEditOps(sent.map((row) => ({ finding: row.finding, text: rowText(row) }))));
  const saveRows = (targets: PassRow[]) =>
    saveBatch(targets, {
      // V0 before the write: Undo restores it only while this batch's version (V0 + 1) is the latest.
      latestVersion: async () =>
        latestVersionNumber(
          await qc.fetchQuery({
            queryKey: ["resume-versions", kind, resumeKey],
            queryFn: () => listResumeVersions(kind, resumeKey),
            staleTime: 0,
          }),
        ),
      write: writeBatch,
      // The 409 does not say which op failed: the rows whose text no longer matches their hash did.
      changedKeys: async (sent) => {
        const fresh = await qc.fetchQuery({
          queryKey: ["base-resumes", resumeKey],
          queryFn: () => fetchBase(resumeKey),
          staleTime: 0,
        });
        const ids = await staleFindingIds(sent.map((row) => row.finding), fresh.data);
        return new Set(sent.filter((row) => ids.has(row.finding.id)).map((row) => row.key));
      },
      isChanged: (err) => err instanceof ApiError && isContentChangedError(err),
      keyOf: (row) => row.key,
    });

  const save = useMutation({
    mutationFn: saveRows,
    onMutate: (targets) => setStatus(keysOf(targets), "saving"),
    onSuccess: ({ sent, changed, undoTo, result }, targets) => {
      setStatus(changed, "changed");
      setStatus(keysOf(sent), "saved");
      setStatus(keysOf(targets), "drafted", "saving");
      if (!result) return;
      notifyRenderNote(result);
      invalidateAfterWrite();
      if (undoTo == null) {
        // No Undo: this write is not the version right after the one read before it.
        toast.success("Saved");
        return;
      }
      toast.success("Saved as a new version", {
        duration: 10_000,
        action: { label: "Undo", onClick: () => undoOnce({ sent, v0: undoTo }) },
      });
    },
    onError: (err, targets) => {
      setStatus(keysOf(targets), "drafted", "saving");
      toast.error(couldnt("save the new wording", err));
    },
  });
  // One write per gesture, and one at a time: a second batch would read the same V0.
  const saveOnce = useSingleFlight(save.mutate);

  const openResume = async () => {
    // Version history is on the resume's page (its ⋯ menu). A page with unsaved work asks first.
    if (await confirmLeave()) router.push(`/base-resumes/${resumeKey}`);
  };
  // Where focus goes once the toast's Undo has gone: the first row's Accept after an undo, its Saved
  // line when the undo failed.
  const landOn = useRef<string | null>(null);
  const undo = useMutation({
    mutationFn: ({ v0 }: Batch) => restoreResumeVersion(kind, resumeKey, v0, { ifLatest: v0 + 1 }),
    onSuccess: (restored, { sent }) => {
      setStatus(keysOf(sent), "drafted");
      landOn.current = sent[0]?.key ?? null;
      invalidateAfterWrite();
      notifyRenderOutcome(restored, { staleLabel: "The resume" });
      toast.success(sent.length === 1 ? "Change undone" : "Changes undone");
    },
    onError: (err, { sent }) => {
      landOn.current = sent[0]?.key ?? null;
      if (err instanceof ApiError && err.status === 409) {
        // Something wrote after this batch: restoring would throw that away too.
        toast.error("Can't undo: the resume changed since. Use version history.", {
          action: { label: "Open the resume", onClick: () => void openResume() },
        });
        return;
      }
      toast.error(couldnt("undo", err));
    },
  });
  const undoOnce = useSingleFlight(undo.mutate);
  useEffect(() => {
    const key = landOn.current;
    if (!key) return;
    const row = `[data-pass-row="${key}"]`;
    const target = document.querySelector<HTMLElement>(`${row} [data-accept], ${row} [data-saved]`);
    if (!target) return;
    landOn.current = null;
    focusIfDropped(target);
  });

  // Write it again: a changed bullet is checked again, then asked again. One at a time (the rows'
  // other Write it again buttons wait while one checks).
  const rechecking = useRef(false);
  const recheck = async (row: PassRow) => {
    if (rechecking.current) return;
    rechecking.current = true;
    setStatus(new Set([row.key]), "checking");
    const patch = (next: Partial<PassRow>) =>
      setRows((current) => current && current.map((r) => (r.key === row.key ? { ...r, ...next } : r)));
    try {
      const fresh = await runLintReport(kind, resumeKey);
      const detail = await qc.fetchQuery({
        queryKey: ["base-resumes", resumeKey],
        queryFn: () => fetchBase(resumeKey),
        staleTime: 0,
      });
      void qc.invalidateQueries({ queryKey: ["resume-lint", kind, resumeKey] });
      const next = fresh.findings.find((f) => f.type === "ask" && sameWhere(f.location, row.finding.location));
      // The typed answer stays: the new bullet usually asks the same thing.
      patch(
        next
          ? { finding: next, original: textAtLocation(detail.data, next), status: "answering", suggestion: null, edited: null }
          : { status: "gone" },
      );
    } catch (err) {
      patch({ status: "changed" });
      toast.error(couldnt("check the resume", err));
    } finally {
      rechecking.current = false;
    }
  };

  return { saveOnce, saving: save.isPending, recheck };
}
