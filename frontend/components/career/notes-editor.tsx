"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, TriangleAlert, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { patchKbEntity } from "@/lib/api";
import { cn } from "@/lib/utils";

export function NotesEditor({
  entityId,
  notes,
}: {
  entityId: string;
  notes: string;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(notes);

  // Dirtiness tracking for the unmount flush. The UI saves explicitly (Save
  // button), but navigating away mid-edit must not silently drop typed notes:
  // valueRef holds the live textarea value, lastSavedRef the last-persisted
  // value, and dirtyRef whether they diverge. On unmount we fire the PATCH.
  const valueRef = useRef(notes);
  const lastSavedRef = useRef(notes);
  const dirtyRef = useRef(false);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["kb", "entities"] });
    void queryClient.invalidateQueries({ queryKey: ["kb", "drafts"] });
  };

  const save = useMutation({
    mutationFn: (next: string) => patchKbEntity(entityId, { notes: next }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["kb", "entity", entityId], updated);
      const saved = updated.notes ?? "";
      valueRef.current = saved;
      lastSavedRef.current = saved;
      dirtyRef.current = false;
      setValue(saved);
      setEditing(false);
      invalidate();
      toast.success("Context notes saved");
    },
    onError: (error: Error) => toast.error(`Notes not saved: ${error.message}`),
  });

  const mutateRef = useRef(save.mutate);
  useEffect(() => {
    mutateRef.current = save.mutate;
  }, [save.mutate]);

  // Keep the saved baseline aligned with server data whenever the user isn't
  // mid-edit, so the unmount flush compares the live value against the right one.
  useEffect(() => {
    if (dirtyRef.current) return;
    valueRef.current = notes;
    lastSavedRef.current = notes;
  }, [notes]);

  // Mount-once cleanup: flush unsaved edits on unmount (e.g. navigation) so
  // typed notes survive even without an explicit Save click.
  useEffect(
    () => () => {
      if (dirtyRef.current && valueRef.current !== lastSavedRef.current) {
        mutateRef.current(valueRef.current);
      }
    },
    [],
  );

  const startEditing = () => {
    setValue(notes);
    valueRef.current = notes;
    lastSavedRef.current = notes;
    dirtyRef.current = false;
    setEditing(true);
  };

  const cancel = () => {
    setValue(notes);
    valueRef.current = notes;
    dirtyRef.current = false;
    setEditing(false);
  };

  const handleChange = (next: string) => {
    setValue(next);
    valueRef.current = next;
    dirtyRef.current = next !== lastSavedRef.current;
  };

  const hasNotes = notes.trim().length > 0;
  const visibleNotes = editing ? value : notes;
  const staleLines = useMemo(
    () =>
      visibleNotes
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.startsWith("⚠ stale?")),
    [visibleNotes],
  );

  return (
    <Card className="group/notes rounded-2xl">
      <CardHeader className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
        <div>
          <CardTitle>Context notes</CardTitle>
          <p className="text-muted-foreground mt-1 text-sm">
            Private context for future AI-generated career materials.
          </p>
        </div>
        {!editing ? (
          <Button
            size="sm"
            variant="ghost"
            className={cn(
              "rounded-full",
              hasNotes &&
                "opacity-0 transition-opacity duration-150 group-hover/notes:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100",
            )}
            onClick={startEditing}
          >
            <Pencil aria-hidden="true" /> {hasNotes ? "Edit" : "Add notes"}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-3">
        {editing ? (
          <>
            <Label htmlFor={`kb-notes-${entityId}`} className="sr-only">
              Career item context notes
            </Label>
            <Textarea
              id={`kb-notes-${entityId}`}
              rows={9}
              value={value}
              onChange={(event) => handleChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  cancel();
                }
              }}
              placeholder="Stack, scale, constraints, collaborators, and what you personally owned…"
              disabled={save.isPending}
              autoFocus
            />
            <div className="flex items-center justify-end gap-2">
              <Button className="rounded-full" size="sm" variant="ghost" onClick={cancel} disabled={save.isPending}>
                <X aria-hidden="true" /> Cancel
              </Button>
              <Button className="rounded-full px-4" size="sm" onClick={() => save.mutate(value)} disabled={save.isPending || value === notes}>
                {save.isPending ? "Saving…" : "Save notes"}
              </Button>
            </div>
          </>
        ) : notes.trim() ? (
          <div className="text-sm leading-7 whitespace-pre-wrap">{notes}</div>
        ) : (
          <div className="rounded-xl bg-muted/45 px-5 py-7 text-center">
            <p className="text-sm font-medium">No context notes yet</p>
            <p className="text-muted-foreground mt-1 text-xs">
              Add details that do not belong on a resume.
            </p>
          </div>
        )}

        {staleLines.length > 0 ? (
          <div role="alert" className="rounded-xl bg-amber-500/15 p-3 text-amber-900 dark:text-amber-100">
            <p className="flex items-center gap-2 text-xs font-semibold">
              <TriangleAlert className="size-4" aria-hidden="true" />
              Review possibly stale facts
            </p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
              {staleLines.map((line, index) => (
                <li key={`${line}-${index}`}>{line}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
