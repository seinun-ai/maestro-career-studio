"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Search } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ApiError, listKbEntities, mergeKbEntity } from "@/lib/api";
import type { KBEntitySummary } from "@/lib/types";

/**
 * The server's gate is `services/career_kb.py::_section_key` — strip +
 * casefold. JS has no casefold, so this strips and LOWERCASES, which on the
 * exotic pairs the two disagree about (German ß casefolds to "ss" but
 * lowercases to itself) can only ever be stricter. Stricter is the safe
 * direction: the picker may withhold a target the server would have accepted;
 * it can never offer one the server will refuse.
 */
const sectionKey = (entity: KBEntitySummary) =>
  (entity.section_key ?? "").trim().toLowerCase();

export function MergeEntityDialog({
  open,
  onOpenChange,
  source,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  source: KBEntitySummary;
}) {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("");
  const [picked, setPicked] = useState<KBEntitySummary | null>(null);
  const filterRef = useRef<HTMLInputElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  // Same query key and fetcher as the /career page, so this reads the list
  // already in the react-query cache rather than adding a prop that both the
  // Experience grid and the grouped Custom-sections grid would have to thread
  // through. No extra request: an identical key shares one cache entry.
  const entities = useQuery({
    queryKey: ["kb", "entities"],
    queryFn: () => listKbEntities(),
    enabled: open,
  });

  // Everything the server would refuse is filtered out here, so a target a
  // user can click is a target that merges.
  const sourceSection = sectionKey(source);
  const candidates = useMemo(
    () =>
      (entities.data ?? []).filter(
        (entity) =>
          entity.id !== source.id &&
          entity.kind === source.kind &&
          entity.status !== "archived" &&
          (source.kind !== "extra" || sectionKey(entity) === sourceSection),
      ),
    [entities.data, source.id, source.kind, sourceSection],
  );

  const needle = filter.trim().toLowerCase();
  const shown = needle
    ? candidates.filter((entity) => entity.title.toLowerCase().includes(needle))
    : candidates;

  const close = () => {
    onOpenChange(false);
    setFilter("");
    setPicked(null);
  };

  const merge = useMutation({
    mutationFn: (target: KBEntitySummary) => mergeKbEntity(source.id, target.id),
    onSuccess: (_detail, target) => {
      // Counts come from the SOURCE props, not the response: the response is
      // the surviving TARGET's detail, whose counts are its own pre-existing
      // points plus the moved ones. What moved is what the source held.
      const moved = source.point_count;
      toast.success(
        `Merged into ${target.title} — ${moved} ${moved === 1 ? "point" : "points"} moved`,
      );
      void queryClient.invalidateQueries({ queryKey: ["kb", "entities"] });
      void queryClient.invalidateQueries({ queryKey: ["kb", "drafts"] });
      void queryClient.invalidateQueries({ queryKey: ["kb", "entity", target.id] });
      close();
    },
    onError: (error: Error) => {
      toast.error(error.message);
      // 409 means the list on screen is a lie — the source is already gone.
      // Refetching is the only useful next step, so close and show reality
      // instead of leaving a dialog aimed at a row that no longer exists.
      if (error instanceof ApiError && error.status === 409) {
        void queryClient.invalidateQueries({ queryKey: ["kb", "entities"] });
        close();
      }
      // 400/404 are fixable in place (pick a different target), so the dialog
      // stays open with the server's sentence in the toast.
    },
  });

  // Confirming is irreversible, and the Enter that picked a target is the same
  // key a reflex press sends — so the confirm step lands on Cancel. `picked` is
  // a state change inside an ALREADY-OPEN popup, which `initialFocus` (mount
  // only) cannot see.
  useEffect(() => {
    if (picked) cancelRef.current?.focus();
  }, [picked]);

  const kindLabel =
    source.kind === "extra" ? source.section_title || "custom section" : source.kind;

  return (
    <Dialog
      open={open}
      onOpenChange={(next, details) => {
        if (next) {
          onOpenChange(true);
          return;
        }
        // Escape, the ✕, and outside clicks all funnel through here, so one
        // guard stops the dialog vanishing mid-request and leaving the user
        // unsure whether the merge landed.
        if (merge.isPending) {
          // cancel(), not a bare return: Base UI's setOpen skips BOTH the
          // floating-root dispatch and its internal state write when the
          // event is cancelled, so the store cannot drift from the rendered
          // state (a bare return masked the drift only because `open` is
          // controlled here).
          details.cancel();
          return;
        }
        close();
      }}
    >
      {/* initialFocus, not autoFocus: Base UI's Popup owns initial focus, so
          React's autoFocus prop never applies (confirm-dialog.tsx documents the
          incident). This dialog opens FROM a dropdown menu — exactly the case
          where the menu's own focus restore won the race and focus stayed
          OUTSIDE the modal. */}
      <DialogContent initialFocus={filterRef}>
        <DialogHeader>
          <DialogTitle>{picked ? "Merge these two?" : "Merge into…"}</DialogTitle>
          <DialogDescription>
            {picked
              ? `Moves ${source.point_count} ${source.point_count === 1 ? "point" : "points"} and ${source.document_count} ${source.document_count === 1 ? "document" : "documents"} onto ${picked.title}; ${source.title} is removed. This cannot be undone.`
              : `Fold ${source.title} into another ${kindLabel} entry. Its points and documents move across; it is removed.`}
          </DialogDescription>
        </DialogHeader>

        {picked ? null : (
          <div className="grid gap-3">
            <div className="relative">
              <Search
                className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2"
                aria-hidden="true"
              />
              <Input
                ref={filterRef}
                aria-label="Filter merge targets by title"
                placeholder="Search by title…"
                className="h-9 pl-8"
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
              />
            </div>

            {entities.isLoading ? (
              <p className="text-muted-foreground rounded-xl bg-muted/45 p-3 text-xs">
                Loading…
              </p>
            ) : entities.error ? (
              <p role="alert" className="text-destructive text-xs">
                {entities.error.message}
              </p>
            ) : shown.length === 0 ? (
              <p className="text-muted-foreground rounded-xl bg-muted/45 p-3 text-xs">
                {candidates.length === 0
                  ? source.kind === "extra"
                    ? `Nothing to merge into — a target has to be another active entry under ${kindLabel}.`
                    : "Nothing to merge into — a target has to be another active entry of the same kind."
                  : "No match for that title."}
              </p>
            ) : (
              <ul className="max-h-72 space-y-1.5 overflow-y-auto rounded-xl bg-muted/45 p-2">
                {shown.map((entity) => (
                  <li key={entity.id}>
                    <button
                      type="button"
                      className="hover:bg-background/80 focus-visible:ring-ring/50 w-full rounded-lg px-2.5 py-2 text-left transition-colors focus-visible:ring-3 focus-visible:outline-none"
                      onClick={() => setPicked(entity)}
                    >
                      <span className="block truncate text-sm font-medium">
                        {entity.title}
                      </span>
                      <span className="text-muted-foreground block truncate text-xs">
                        {[
                          entity.org,
                          [entity.start_date, entity.end_date].filter(Boolean).join(" – "),
                          `${entity.point_count} ${entity.point_count === 1 ? "point" : "points"}`,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {/* Typing narrows a list a screen reader cannot watch scroll by. */}
            <p aria-live="polite" className="text-muted-foreground text-xs">
              {entities.isLoading || entities.error
                ? ""
                : `${shown.length} ${shown.length === 1 ? "target" : "targets"}${
                    needle ? ` matching “${filter.trim()}”` : ""
                  }`}
            </p>
          </div>
        )}

        <DialogFooter>
          {picked ? (
            <>
              <Button
                className="rounded-full"
                variant="ghost"
                onClick={() => setPicked(null)}
                disabled={merge.isPending}
              >
                <ArrowLeft aria-hidden="true" /> Back
              </Button>
              <Button
                ref={cancelRef}
                className="rounded-full"
                variant="outline"
                onClick={close}
                disabled={merge.isPending}
              >
                Cancel
              </Button>
              <Button
                className="rounded-full px-4"
                variant="destructive"
                onClick={() => merge.mutate(picked)}
                disabled={merge.isPending}
              >
                {merge.isPending ? "Merging…" : "Merge"}
              </Button>
            </>
          ) : (
            <Button className="rounded-full" variant="outline" onClick={close}>
              Cancel
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
