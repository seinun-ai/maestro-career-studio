"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Inbox, Pencil, Trash2, X } from "lucide-react";
import { toast } from "sonner";

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
import { deleteKbPoint, patchKbPoint } from "@/lib/api";
import type { KBEntitySummary, KBInboxPoint, KBPointPatch } from "@/lib/types";

type DraftGroup = {
  entityId: string;
  entityTitle: string;
  points: KBInboxPoint[];
};

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

  return (
    <Card id="inbox" className="scroll-mt-6 border-0 bg-muted/45 shadow-none ring-0">
      <CardHeader className="pb-1">
        <CardTitle className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-full bg-background/80">
            <Inbox className="text-primary size-4" aria-hidden="true" />
          </span>
          Draft inbox
          {!isLoading && <Badge className="rounded-full" variant="secondary">{drafts.length}</Badge>}
        </CardTitle>
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
                  <DraftRow key={point.id} point={point} entities={entities} />
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
}: {
  point: KBInboxPoint;
  entities: KBEntitySummary[];
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(point.text);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["kb", "drafts"] });
    void queryClient.invalidateQueries({ queryKey: ["kb", "entities"] });
    void queryClient.invalidateQueries({ queryKey: ["kb", "entity"] });
  };

  const update = useMutation({
    mutationFn: ({ payload }: { payload: KBPointPatch; success: string }) =>
      patchKbPoint(point.id, payload),
    onSuccess: (updated, variables) => {
      setText(updated.text);
      setEditing(false);
      toast.success(variables.success);
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const discard = useMutation({
    mutationFn: () => deleteKbPoint(point.id),
    onSuccess: () => {
      toast.success("Draft discarded");
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const pending = update.isPending || discard.isPending;
  const selectedEntity = entities.find((entity) => entity.id === point.entity_id);
  const cancelEdit = () => {
    setText(point.text);
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
            onChange={(event) => setText(event.target.value)}
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
