"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  Check,
  ChevronDown,
  Pencil,
  RotateCcw,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { deleteKbPoint, patchKbPoint } from "@/lib/api";
import type { KBPointOut, KBPointPatch, KBPointState } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATES: { value: KBPointState; label: string; chip: string; dot: string }[] = [
  {
    value: "draft",
    label: "Draft",
    chip: "bg-amber-500/15 text-amber-800 dark:bg-amber-400/15 dark:text-amber-200",
    dot: "bg-amber-500 dark:bg-amber-400",
  },
  {
    value: "approved",
    label: "Approved",
    chip: "bg-emerald-600/10 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300",
    dot: "bg-emerald-600 dark:bg-emerald-400",
  },
  {
    value: "retired",
    label: "Retired",
    chip: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground/45",
  },
];

const ORIGIN_LABELS: Record<KBPointOut["origin"], string> = {
  manual: "Manual",
  ingested: "Document",
  chat: "Capture",
  consolidated: "Consolidated",
  mcp: "Agent",
  gap_elicitation: "Gap answer",
};

const STATE_ORDER: Record<KBPointState, number> = {
  draft: 0,
  approved: 1,
  retired: 2,
};

export function PointsList({
  entityId,
  points,
}: {
  entityId: string;
  points: KBPointOut[];
}) {
  const ordered = [...points].sort(
    (left, right) =>
      STATE_ORDER[left.state] - STATE_ORDER[right.state] ||
      Date.parse(right.updated_at) - Date.parse(left.updated_at),
  );

  return (
    <Card className="rounded-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Career points
          <Badge className="rounded-full" variant="secondary">
            {points.length}
          </Badge>
        </CardTitle>
        <p className="text-muted-foreground text-sm">
          Approved points are ready to send to a resume.
        </p>
      </CardHeader>
      <CardContent className="px-0">
        {ordered.length === 0 ? (
          <div className="mx-4 rounded-xl bg-muted/45 px-5 py-8 text-center">
            <p className="text-sm font-medium">No career points yet</p>
            <p className="text-muted-foreground mt-1 text-xs">
              Capture an update or upload a source document to get started.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-foreground/10">
            {ordered.map((point) => (
              <PointRow key={point.id} entityId={entityId} point={point} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PointRow({ entityId, point }: { entityId: string; point: KBPointOut }) {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(point.text);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["kb", "entity", entityId] });
    void queryClient.invalidateQueries({ queryKey: ["kb", "entities"] });
    void queryClient.invalidateQueries({ queryKey: ["kb", "drafts"] });
  };

  const update = useMutation({
    mutationFn: ({ payload }: { payload: KBPointPatch; message: string }) =>
      patchKbPoint(point.id, payload),
    onSuccess: (updated, variables) => {
      setText(updated.text);
      setEditing(false);
      toast.success(variables.message);
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: () => deleteKbPoint(point.id),
    onSuccess: () => {
      toast.success("Point deleted");
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const pending = update.isPending || remove.isPending;
  const usageKeys = point.usage.map((usage) => usage.resume_key);
  const hasDrift = point.usage.some((usage) => usage.drifted);

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
    update.mutate({ payload: { text: value }, message: "Point updated" });
  };

  const changeState = (state: KBPointState) => {
    const messages: Record<KBPointState, string> = {
      draft: "Point moved to drafts",
      approved: point.state === "retired" ? "Point restored" : "Point approved",
      retired: "Point retired",
    };
    update.mutate({ payload: { state }, message: messages[state] });
  };

  const requestDelete = async () => {
    const accepted = await confirm({
      title: "Delete this point?",
      description:
        point.usage.length > 0
          ? "Its prior resume usage stays in historical resume versions, but this provenance link will be removed."
          : "This permanently removes the point from the Career KB.",
      confirmLabel: "Delete point",
      destructive: true,
    });
    if (accepted) remove.mutate();
  };

  return (
    <article
      className={cn(
        "group/point px-4 py-3.5 transition-colors duration-150 ease-out hover:bg-muted/30",
        point.state === "draft" && "bg-amber-500/5",
        point.state === "retired" && "opacity-70",
      )}
    >
      {editing ? (
        <div className="space-y-2">
          <Label htmlFor={`kb-point-${point.id}`} className="sr-only">
            Edit career point
          </Label>
          <Textarea
            id={`kb-point-${point.id}`}
            rows={3}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                cancelEdit();
              }
            }}
            disabled={pending}
            autoFocus
          />
          <div className="flex justify-end gap-2">
            <Button className="rounded-full" size="sm" variant="ghost" onClick={cancelEdit} disabled={pending}>
              <X aria-hidden="true" /> Cancel
            </Button>
            <Button className="rounded-full px-4" size="sm" onClick={saveText} disabled={!text.trim() || pending}>
              Save
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-3">
          <p className="min-w-0 flex-1 text-sm leading-relaxed whitespace-pre-wrap">
            {point.text}
          </p>
          <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity duration-150 group-hover/point:opacity-100 focus-within:opacity-100 pointer-coarse:opacity-100">
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Edit point"
              title="Edit point"
              onClick={() => {
                setText(point.text);
                setEditing(true);
              }}
              disabled={pending}
            >
              <Pencil aria-hidden="true" />
            </Button>
            {point.state === "draft" ? (
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="Approve point"
                title="Approve point"
                onClick={() => changeState("approved")}
                disabled={pending}
              >
                <Check aria-hidden="true" />
              </Button>
            ) : null}
            {point.state === "approved" ? (
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="Retire point"
                title="Retire point"
                onClick={() => changeState("retired")}
                disabled={pending}
              >
                <Archive aria-hidden="true" />
              </Button>
            ) : null}
            {point.state === "retired" ? (
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="Restore point"
                title="Restore point"
                onClick={() => changeState("approved")}
                disabled={pending}
              >
                <RotateCcw aria-hidden="true" />
              </Button>
            ) : null}
            <Button
              size="icon-sm"
              variant="ghost"
              className="text-destructive hover:text-destructive"
              aria-label="Delete point"
              title="Delete point"
              onClick={() => void requestDelete()}
              disabled={pending}
            >
              <Trash2 aria-hidden="true" />
            </Button>
          </div>
        </div>
      )}

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <PointStateChip state={point.state} pending={pending} onSelect={changeState} />
        <span
          className="text-muted-foreground inline-flex h-6 items-center rounded-full bg-muted/70 px-2 text-xs"
          title={point.origin_detail ? `Written by ${point.origin_detail}` : undefined}
        >
          {ORIGIN_LABELS[point.origin]}
        </span>
        {point.usage.length > 0 ? (
          <span
            className="text-muted-foreground inline-flex h-6 items-center rounded-full bg-primary/10 px-2 text-xs"
            title={`Used in: ${usageKeys.join(", ")}`}
          >
            in {point.usage.length} {point.usage.length === 1 ? "resume" : "resumes"}
          </span>
        ) : null}
        {hasDrift ? (
          <span
            className="inline-flex h-6 items-center gap-1 rounded-full bg-amber-500/15 px-2 text-xs text-amber-800 dark:text-amber-200"
            title="At least one resume still has an older phrasing"
          >
            <TriangleAlert className="size-3" aria-hidden="true" /> Drifted
          </span>
        ) : null}
        {point.tags.map((tag) => (
          <Badge key={tag} variant="secondary" className="rounded-full font-normal">
            {tag}
          </Badge>
        ))}
      </div>
    </article>
  );
}

function PointStateChip({
  state,
  pending,
  onSelect,
}: {
  state: KBPointState;
  pending: boolean;
  onSelect: (state: KBPointState) => void;
}) {
  const current = STATES.find((item) => item.value === state) ?? STATES[0];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button
            type="button"
            disabled={pending}
            aria-label={`Point state: ${current.label}. Change state`}
            className={cn(
              "inline-flex h-6 items-center gap-1.5 rounded-full px-2 text-xs font-medium transition-[transform,box-shadow] duration-150 ease-out hover:shadow-sm active:scale-[0.97] focus-visible:outline-2 focus-visible:outline-ring/60 disabled:opacity-50",
              current.chip,
            )}
          >
            <span className={cn("size-1.5 rounded-full", current.dot)} />
            {current.label}
            <ChevronDown className="size-3 opacity-50" aria-hidden="true" />
          </button>
        }
      />
      <DropdownMenuContent align="start" className="w-40">
        {STATES.map((item) => (
          <DropdownMenuItem
            key={item.value}
            onClick={() => {
              if (item.value !== state) onSelect(item.value);
            }}
          >
            <span className={cn("size-2 rounded-full", item.dot)} />
            <span className="flex-1">{item.label}</span>
            {item.value === state ? <Check className="text-muted-foreground size-3.5" /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
