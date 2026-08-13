"use client";

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import {
  useIsMutating,
  useMutation,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { Check, Inbox, Pencil, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { deleteKbPoint, patchKbPoint, bulkKbPointState } from "@/lib/api";
import type { KBEntitySummary, KBInboxPoint, KBPointPatch, UUID } from "@/lib/types";

type DraftGroup = {
  entityId: string;
  entityTitle: string;
  points: KBInboxPoint[];
};

// Every write in this panel — bulk approve, per-row approve/save/reassign,
// discard — carries this key, so `useIsMutating` over it gives the panel ONE
// pending flag covering all of them. Without a shared flag the bulk call and a
// per-row control ran concurrently: approve-all followed by an instant Discard
// deleted a point the bulk request had just approved, or reported a spurious
// "not found" for a row the server had already moved.
const KB_POINT_MUTATION_KEY = ["kb", "point-write"] as const;

// Approving, editing, reassigning and discarding a draft all move the same
// three lists. This was copy-pasted at three call sites; kept in one place so
// they cannot drift apart.
const KB_POINT_QUERY_KEYS = [
  ["kb", "drafts"],
  ["kb", "entities"],
  ["kb", "entity"],
] as const;

/** Resolves once the affected lists have actually refetched. */
function invalidateKbPoints(queryClient: QueryClient) {
  return Promise.all(
    KB_POINT_QUERY_KEYS.map((queryKey) =>
      queryClient.invalidateQueries({ queryKey }),
    ),
  );
}

export function InboxPanel({
  drafts,
  entities,
  isLoading,
  error,
  onRetry,
}: {
  drafts: KBInboxPoint[];
  entities: KBEntitySummary[];
  isLoading: boolean;
  error: Error | null;
  onRetry: () => void;
}) {
  const groups = useMemo(() => {
    const grouped = new Map<string, DraftGroup>();
    for (const draft of drafts) {
      const group = grouped.get(draft.entity_id) ?? {
        entityId: draft.entity_id,
        entityTitle: draft.entity_title,
        points: [],
      };
      group.points.push(draft);
      grouped.set(draft.entity_id, group);
    }
    return [...grouped.values()];
  }, [drafts]);

  const queryClient = useQueryClient();
  const confirm = useConfirm();

  // Rows own their editor text, so the panel only tracks WHICH rows hold an
  // unsaved edit. Bulk approve sends ids alone, and the server approves the
  // stored text — so a row whose open editor fixes a transcription typo would
  // be approved with the wrong wording and the correction silently dropped.
  // Those rows are excluded from the bulk call instead (chosen over flushing
  // them first: excluding needs one boolean per row, flushing would mean
  // lifting every editor's text into this component).
  const [dirtyIds, setDirtyIds] = useState<ReadonlySet<string>>(() => new Set());
  const setRowDirty = useCallback((id: UUID, dirty: boolean) => {
    setDirtyIds((prev) => {
      if (prev.has(id) === dirty) return prev;
      const next = new Set(prev);
      if (dirty) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  const approvableIds = useMemo(
    () => drafts.filter((draft) => !dirtyIds.has(draft.id)).map((d) => d.id),
    [drafts, dirtyIds],
  );
  const skipped = drafts.length - approvableIds.length;

  // Shared by every control in the panel, bulk and per-row alike.
  const pending = useIsMutating({ mutationKey: KB_POINT_MUTATION_KEY }) > 0;

  const approveAll = useMutation({
    mutationKey: KB_POINT_MUTATION_KEY,
    mutationFn: async (ids: UUID[]) => {
      const ok = await confirm({
        title: `Approve ${ids.length} ${ids.length === 1 ? "point" : "points"}?`,
        description:
          skipped > 0
            ? `They join your career record. ${skipped} draft${skipped === 1 ? "" : "s"} with unsaved edits ${skipped === 1 ? "is" : "are"} not included.`
            : "They join your career record. You can still edit them there afterwards.",
        confirmLabel: "Approve",
      });
      if (!ok) return null;
      return bulkKbPointState(ids, "approved");
    },
    onSuccess: async (body, ids) => {
      if (!body) return;
      // Counted against the ids SENT, not against results.length: a response
      // that omits an id entirely is a failure, and results.length arithmetic
      // reported it as a success.
      const approved = body.results.filter((row) => row.ok).length;
      const failed = ids.length - approved;
      if (failed === 0) {
        toast.success(
          `Approved ${approved} ${approved === 1 ? "point" : "points"}`,
        );
      } else {
        const detail =
          body.results.find((row) => !row.ok)?.detail ?? "no reason given";
        toast.error(
          `Approved ${approved} of ${ids.length} — ${failed} failed: ${detail}`,
        );
      }
      // Awaited, not fire-and-forget. react-query holds the mutation pending
      // until this resolves, so the button stays disabled until the list has
      // refetched and a double click cannot re-submit the same ids.
      await invalidateKbPoints(queryClient);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  return (
    <Card id="inbox" className="scroll-mt-6 border-0 bg-muted/45 shadow-none ring-0">
      <CardHeader className="pb-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <span className="flex size-8 items-center justify-center rounded-full bg-background/80">
              <Inbox className="text-primary size-4" aria-hidden="true" />
            </span>
            Draft inbox
            {!isLoading && <Badge className="rounded-full" variant="secondary">{drafts.length}</Badge>}
          </CardTitle>
          {drafts.length > 0 && !isLoading && !error && (
            <div className="flex flex-col items-end gap-1">
              <Button
                className="rounded-full px-4"
                size="sm"
                onClick={() => approveAll.mutate(approvableIds)}
                disabled={pending || approvableIds.length === 0}
              >
                <Check aria-hidden="true" />
                {approveAll.isPending ? "Approving…" : "Approve all shown"}
              </Button>
              {skipped > 0 && (
                <p className="text-muted-foreground text-xs">
                  {skipped} with unsaved edits skipped — save or discard them
                  first.
                </p>
              )}
            </div>
          )}
        </div>
        <p className="text-muted-foreground text-sm">
          Review AI-written points before they become part of your career record.
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        {isLoading ? (
          <div className="space-y-3" aria-label="Loading career drafts">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-36 w-full" />
            <Skeleton className="h-28 w-full" />
          </div>
        ) : error ? (
          <div role="alert" className="rounded-xl bg-destructive/10 p-4">
            <p className="text-sm font-medium">Couldn&apos;t load the draft inbox.</p>
            <p className="text-muted-foreground mt-1 text-xs">{error.message}</p>
            <Button className="mt-3" size="sm" variant="outline" onClick={onRetry}>
              Try again
            </Button>
          </div>
        ) : groups.length === 0 ? (
          <div className="rounded-xl bg-background/65 py-7 text-center">
            <span className="mx-auto flex size-9 items-center justify-center rounded-full bg-emerald-600/10 text-emerald-700 dark:text-emerald-300">
              <Check className="size-4" aria-hidden="true" />
            </span>
            <p className="mt-2 text-sm font-medium">Inbox clear</p>
            <p className="text-muted-foreground text-xs">
              Captures and rewritten consolidation points will appear here.
            </p>
          </div>
        ) : (
          groups.map((group) => (
            <section key={group.entityId} aria-labelledby={`draft-group-${group.entityId}`}>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 id={`draft-group-${group.entityId}`} className="font-medium">
                  <Link className="hover:underline" href={`/career/${group.entityId}`}>
                    {group.entityTitle}
                  </Link>
                </h3>
                <Badge className="rounded-full" variant="secondary">
                  {group.points.length} {group.points.length === 1 ? "draft" : "drafts"}
                </Badge>
              </div>
              <div className="space-y-2">
                {group.points.map((point) => (
                  <DraftRow
                    key={point.id}
                    point={point}
                    entities={entities}
                    pending={pending}
                    onDirtyChange={setRowDirty}
                  />
                ))}
              </div>
            </section>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function DraftRow({
  point,
  entities,
  pending,
  onDirtyChange,
}: {
  point: KBInboxPoint;
  entities: KBEntitySummary[];
  /** Panel-wide flag: true while ANY draft write is in flight, bulk or row. */
  pending: boolean;
  onDirtyChange: (id: UUID, dirty: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(point.text);

  const update = useMutation({
    mutationKey: KB_POINT_MUTATION_KEY,
    mutationFn: ({ payload }: { payload: KBPointPatch; success: string }) =>
      patchKbPoint(point.id, payload),
    onSuccess: async (updated, variables) => {
      setText(updated.text);
      setEditing(false);
      onDirtyChange(point.id, false);
      toast.success(variables.success);
      await invalidateKbPoints(queryClient);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const discard = useMutation({
    mutationKey: KB_POINT_MUTATION_KEY,
    mutationFn: () => deleteKbPoint(point.id),
    onSuccess: async () => {
      onDirtyChange(point.id, false);
      toast.success("Draft discarded");
      await invalidateKbPoints(queryClient);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const selectedEntity = entities.find((entity) => entity.id === point.entity_id);
  // The panel excludes dirty rows from "Approve all shown", so every path that
  // changes or resets the editor has to report the row's state.
  const changeText = (value: string) => {
    setText(value);
    onDirtyChange(point.id, value.trim() !== point.text);
  };
  const cancelEdit = () => {
    setText(point.text);
    onDirtyChange(point.id, false);
    setEditing(false);
  };
  const saveText = () => {
    const value = text.trim();
    if (!value || value === point.text) {
      cancelEdit();
      return;
    }
    update.mutate({ payload: { text: value }, success: "Draft updated" });
  };

  const approve = () => {
    const value = text.trim();
    update.mutate({
      payload: {
        state: "approved",
        ...(value && value !== point.text ? { text: value } : {}),
      },
      success: "Point approved",
    });
  };

  return (
    <article className="group/draft rounded-xl bg-background/80 p-3 shadow-sm ring-1 ring-foreground/5">
      {editing ? (
        <div className="space-y-2">
          <Label htmlFor={`draft-text-${point.id}`} className="sr-only">
            Edit draft point
          </Label>
          <Textarea
            id={`draft-text-${point.id}`}
            value={text}
            onChange={(event) => changeText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                cancelEdit();
              }
            }}
            rows={3}
            disabled={pending}
            autoFocus
          />
          <div className="flex gap-2">
            <Button className="rounded-full px-4" size="sm" onClick={saveText} disabled={!text.trim() || pending}>
              Save
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="rounded-full"
              onClick={cancelEdit}
              disabled={pending}
            >
              <X aria-hidden="true" /> Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-2">
          <p className="min-w-0 flex-1 text-sm leading-relaxed">{point.text}</p>
          <Button
            size="icon-sm"
            variant="ghost"
            className="opacity-0 transition-opacity duration-150 group-hover/draft:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100"
            aria-label="Edit draft"
            title="Edit draft"
            onClick={() => setEditing(true)}
            disabled={pending}
          >
            <Pencil aria-hidden="true" />
          </Button>
        </div>
      )}

      {point.merge_sources && point.merge_sources.length > 0 && (
        <div className="mt-3 rounded-xl bg-muted/55 p-3">
          <p className="mb-2 text-xs font-medium">Original resume phrasings</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {point.merge_sources.map((source, index) => (
              <div
                key={`${source.resume_key}-${source.section}-${index}`}
                className="rounded-lg bg-background/80 p-2"
              >
                <p className="text-muted-foreground mb-1 text-[0.7rem] font-medium uppercase tracking-wide">
                  {source.resume_key} · {source.section}
                </p>
                <p className="text-xs leading-relaxed">{source.text}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-end gap-2 pt-1">
        <Button className="rounded-full px-4" size="sm" onClick={approve} disabled={!text.trim() || pending}>
          <Check aria-hidden="true" />
          {update.isPending ? "Saving…" : "Approve"}
        </Button>
        <div className="min-w-44 flex-1 sm:max-w-64">
          <Label htmlFor={`draft-entity-${point.id}`} className="sr-only">
            Reassign draft
          </Label>
          <Select
            value={point.entity_id}
            onValueChange={(entityId) => {
              if (!entityId || entityId === point.entity_id) return;
              const target = entities.find((entity) => entity.id === entityId);
              update.mutate({
                payload: { entity_id: entityId },
                success: `Draft reassigned${target ? ` to ${target.title}` : ""}`,
              });
            }}
            disabled={pending || entities.length < 2}
          >
            <SelectTrigger id={`draft-entity-${point.id}`} className="w-full">
              <SelectValue>{selectedEntity?.title ?? point.entity_title}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {entities.map((entity) => (
                <SelectItem key={entity.id} value={entity.id}>
                  {entity.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button
          size="sm"
          variant="destructive"
          className="rounded-full opacity-0 transition-opacity duration-150 group-hover/draft:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100"
          onClick={() => discard.mutate()}
          disabled={pending}
        >
          <Trash2 aria-hidden="true" />
          {discard.isPending ? "Discarding…" : "Discard"}
        </Button>
      </div>
    </article>
  );
}
