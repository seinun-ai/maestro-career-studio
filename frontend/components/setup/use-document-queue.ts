"use client";

import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError, kbIngestDocument } from "@/lib/api";

export type QueueRow =
  | { file: File; state: "queued" }
  | { file: File; state: "uploading" }
  | {
      file: File;
      state: "done";
      entity: string;
      kind: string;
      points: number;
      created: boolean;
    }
  | { file: File; state: "failed"; reason: string };

export type QueueStatus =
  /** Nothing queued yet. */
  | "idle"
  /** Working through the queue, one file at a time. */
  | "running"
  /** Halted with files still queued — provider outage or user cancel. */
  | "halted"
  /** Every file reached a terminal state. */
  | "finished";

export type QueueSummary = {
  points: number;
  entitiesCreated: number;
  entitiesMatched: number;
  failed: number;
  remaining: number;
};

/** Statuses that mean "the provider is down", not "this file is bad".
 *  502 is what the router raises when the LLM provider is unavailable; 0 is
 *  apiFetch's network-failure code. Both make the NEXT file pointless. */
function isOutage(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 502 || error.status === 0);
}

function message(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

/**
 * Sequential ingest queue for the document lane.
 *
 * Three rules here are load-bearing; none is an accident of implementation.
 *
 * 1. **Files go one at a time, never Promise.all.** Each ingest resolves the
 *    document against existing KB entities and may CREATE one. Two documents
 *    about the same job, sent concurrently, both see "no such entity" and mint
 *    two entities for one role. Sequential is a correctness requirement.
 *
 * 2. **A provider outage halts the queue; a bad file does not.** A 502 means
 *    every remaining file would fail the same way and burn an upload doing it,
 *    so the rest stay `queued` and the user can retry. A 422 (unreadable or
 *    scanned document) is about that file alone, so the batch continues.
 *
 * 3. **Cancel stops after the in-flight file, and completed work stays done.**
 *    The endpoint commits per call, so there is nothing to roll back and the UI
 *    must not imply otherwise.
 *
 * `rowsRef` mirrors `rows` because the run loop reads the list between awaits.
 * Reading React state there would see a stale closure, and reading it through a
 * setState updater would depend on flush timing — both are wrong.
 */
export function useDocumentQueue() {
  const qc = useQueryClient();
  const rowsRef = useRef<QueueRow[]>([]);
  const [rows, setRows] = useState<QueueRow[]>([]);
  const [status, setStatus] = useState<QueueStatus>("idle");
  const cancelled = useRef(false);
  const running = useRef(false);

  const commit = useCallback((next: QueueRow[]) => {
    rowsRef.current = next;
    setRows(next);
  }, []);

  const patch = useCallback(
    (index: number, row: QueueRow) => {
      commit(rowsRef.current.map((r, i) => (i === index ? row : r)));
    },
    [commit],
  );

  const run = useCallback(async () => {
    if (running.current) return;
    running.current = true;
    cancelled.current = false;
    setStatus("running");

    let halted = false;
    // Re-scan each iteration rather than snapshotting: `add` can append while
    // the queue is draining, and those files should be picked up too.
    for (;;) {
      if (cancelled.current) {
        halted = true;
        break;
      }
      const index = rowsRef.current.findIndex((r) => r.state === "queued");
      if (index === -1) break;

      const { file } = rowsRef.current[index];
      patch(index, { file, state: "uploading" });

      try {
        const result = await kbIngestDocument(file);
        patch(index, {
          file,
          state: "done",
          entity: result.entity_title,
          kind: result.entity_kind,
          points: result.point_count,
          created: result.created_entity,
        });
        qc.invalidateQueries({ queryKey: ["kb"] });
        qc.invalidateQueries({ queryKey: ["setup-status"] });
      } catch (error) {
        if (isOutage(error)) {
          // Put it back in the queue — it never got a fair attempt.
          patch(index, { file, state: "queued" });
          halted = true;
          break;
        }
        patch(index, { file, state: "failed", reason: message(error) });
      }
    }

    running.current = false;
    setStatus(halted ? "halted" : "finished");
  }, [patch, qc]);

  const add = useCallback(
    (files: File[], rejected: { file: File; reason: string }[] = []) => {
      commit([
        ...rowsRef.current,
        ...files.map((file): QueueRow => ({ file, state: "queued" })),
        ...rejected.map(
          (r): QueueRow => ({ file: r.file, state: "failed", reason: r.reason }),
        ),
      ]);
      setStatus((prev) => (prev === "finished" ? "idle" : prev));
    },
    [commit],
  );

  /** Stop after the in-flight file. Completed rows stay completed. */
  const cancel = useCallback(() => {
    cancelled.current = true;
  }, []);

  const reset = useCallback(() => {
    cancelled.current = true;
    commit([]);
    setStatus("idle");
  }, [commit]);

  const summary: QueueSummary = rows.reduce<QueueSummary>(
    (acc, row) => {
      if (row.state === "done") {
        acc.points += row.points;
        if (row.created) acc.entitiesCreated += 1;
        else acc.entitiesMatched += 1;
      } else if (row.state === "failed") {
        acc.failed += 1;
      } else {
        acc.remaining += 1;
      }
      return acc;
    },
    { points: 0, entitiesCreated: 0, entitiesMatched: 0, failed: 0, remaining: 0 },
  );

  return { rows, status, summary, add, run, cancel, reset };
}
