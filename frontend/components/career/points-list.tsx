"use client";

import { useRef, useState, type ComponentType } from "react";
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
import { useResumeKeyLabel } from "@/components/career/use-resume-key-label";
import { useDiscardableEditor } from "@/hooks/use-confirm-discard";
import { focusIfDropped } from "@/hooks/use-focus-return";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { agentDisplayName } from "@/lib/agent-name";
import { deleteKbPoint, patchKbPoint } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import type { KBPointOut, KBPointPatch, KBPointProvenance, KBPointState } from "@/lib/types";
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
    chip: "bg-emerald-600/10 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-300",
    dot: "bg-emerald-600 dark:bg-emerald-400",
  },
  {
    value: "retired",
    label: "Not used",
    chip: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground/45",
  },
];

// Where a bullet came from, in the user's words, never the pipeline's.
const ORIGIN_LABELS: Record<KBPointOut["origin"], string> = {
  manual: "You",
  ingested: "Document",
  chat: "Assistant",
  consolidated: "Merged",
  mcp: "Connected agent",
  gap_elicitation: "Your answer",
  base_sync: "From a resume",
};

/** A connected agent's bullet names the agent ("From Claude") when it said who it is. */
function originLabel(point: Pick<KBPointOut, "origin" | "origin_detail">): string {
  const agent = point.origin === "mcp" ? agentDisplayName(point.origin_detail) : null;
  return agent ? `From ${agent}` : ORIGIN_LABELS[point.origin];
}

// How sure the words are. `user_authored` is also what a bullet drafted from
// your document or resume carries, so it says where it came from, not that you
// typed it.
const PROVENANCE_LABELS: Record<KBPointProvenance, string> = {
  user_authored: "From your own material",
  user_stated: "You said it",
  derived_unverified: "AI inferred",
  user_cannot_confirm: "You couldn't confirm this",
};

/**
 * The one button beside a bullet that moves it on: Approve a draft, Stop using
 * an approved bullet, Use again a retired one. ONE element whose props change,
 * so the button the user pressed is the button that keeps focus.
 */
const STATE_ACTIONS: Record<
  KBPointState,
  { label: string; hint: string; to: KBPointState; icon: ComponentType<{ "aria-hidden"?: boolean }> }
> = {
  draft: {
    label: "Approve bullet",
    hint: "Approve bullet",
    to: "approved",
    icon: Check,
  },
  approved: {
    label: "Stop using",
    hint: "Stop offering this bullet. Resumes that have it keep it.",
    to: "retired",
    icon: Archive,
  },
  retired: {
    label: "Use again",
    hint: "Offer this bullet again",
    to: "approved",
    icon: RotateCcw,
  },
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
          Bullets
          <Badge className="rounded-full" variant="secondary">
            {points.length}
          </Badge>
        </CardTitle>
        <p className="text-muted-foreground text-sm">
          Approved bullets are ready to add to a resume.
        </p>
      </CardHeader>
      <CardContent className="px-0">
        {ordered.length === 0 ? (
          <div className="mx-4 rounded-xl bg-muted/45 px-5 py-8 text-center">
            <p className="text-sm font-medium">No bullets yet</p>
            <p className="text-muted-foreground mt-1 text-xs">
              Add an update or a document to start.
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

  // The row's one state button. A state change re-sorts the list (drafts,
  // then approved, then not used), and moving a row can drop its focus: once
  // the list has refetched, a dropped focus comes back here.
  const actionRef = useRef<HTMLButtonElement>(null);

  const invalidate = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["kb", "entity", entityId] }),
      queryClient.invalidateQueries({ queryKey: ["kb", "entities"] }),
      queryClient.invalidateQueries({ queryKey: ["kb", "drafts"] }),
    ]);

  const update = useMutation({
    mutationFn: ({ payload }: { payload: KBPointPatch; message: string }) =>
      patchKbPoint(point.id, payload),
    onSuccess: async (updated, variables) => {
      setText(updated.text);
      setEditing(false);
      toast.success(variables.message);
      await invalidate();
      if (variables.payload.state) focusIfDropped(actionRef.current);
    },
    onError: (error: Error) => toast.error(couldnt("update the bullet", error)),
  });
  // One write per gesture: a double click on Approve sent two PATCHes.
  const updateOnce = useSingleFlight(update.mutate);

  const remove = useMutation({
    mutationFn: () => deleteKbPoint(point.id),
    onSuccess: () => {
      toast.success("Bullet deleted");
      invalidate();
    },
    onError: (error: Error) => toast.error(couldnt("delete the bullet", error)),
  });

  const pending = update.isPending || remove.isPending;
  const usageKeys = [...new Set(point.usage.map((usage) => usage.resume_key))];
  const resumeName = useResumeKeyLabel(usageKeys);
  const hasDrift = point.usage.some((usage) => usage.drifted);

  const cancelEdit = () => {
    setText(point.text);
    setEditing(false);
  };
  const { editRef, onCancel, onKeyDown, onSave } = useDiscardableEditor({
    editing,
    changed: text.trim() !== point.text,
    close: cancelEdit,
    busy: pending,
  });

  const changeState = (state: KBPointState) => {
    const messages: Record<KBPointState, string> = {
      draft: "Bullet moved to drafts",
      approved: point.state === "retired" ? "Using this bullet again" : "Bullet approved",
      retired: "Won't be offered again",
    };
    updateOnce({ payload: { state }, message: messages[state] });
  };
  const action = STATE_ACTIONS[point.state];
  const ActionIcon = action.icon;

  const requestDelete = async () => {
    const accepted = await confirm({
      title: "Delete this bullet?",
      description:
        point.usage.length > 0
          ? "This permanently deletes the bullet. Resumes that used it keep their text. You can't undo this."
          : "This permanently deletes the bullet. You can't undo this.",
      confirmLabel: "Delete bullet",
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
            Edit bullet
          </Label>
          <Textarea
            id={`kb-point-${point.id}`}
            rows={3}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            readOnly={pending}
            autoFocus
          />
          <div className="flex justify-end gap-2">
            <Button
              className="rounded-full"
              size="sm"
              variant="ghost"
              onClick={() => void onCancel()}
              disabled={pending}
            >
              <X aria-hidden="true" /> Cancel
            </Button>
            <Button
              className="rounded-full px-4 data-disabled:pointer-events-none data-disabled:opacity-50"
              size="sm"
              onClick={() =>
                onSave(() => updateOnce({ payload: { text: text.trim() }, message: "Bullet updated" }))
              }
              // An emptied bullet is not saved.
              disabled={!text.trim() || pending}
              focusableWhenDisabled
            >
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
              ref={editRef}
              size="icon-sm"
              variant="ghost"
              aria-label="Edit bullet"
              title="Edit bullet"
              onClick={() => {
                setText(point.text);
                setEditing(true);
              }}
              disabled={pending}
            >
              <Pencil aria-hidden="true" />
            </Button>
            <Button
              ref={actionRef}
              size="icon-sm"
              variant="ghost"
              aria-label={action.label}
              title={action.hint}
              onClick={() => changeState(action.to)}
              disabled={pending}
              // Disables itself while it works: a native `disabled` drops focus.
              focusableWhenDisabled
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
            >
              <ActionIcon aria-hidden />
            </Button>
            <Button
              size="icon-sm"
              variant="ghost"
              className="text-destructive hover:text-destructive"
              aria-label="Delete bullet"
              title="Delete bullet"
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
          title={point.origin_detail ? `Written by ${agentDisplayName(point.origin_detail) ?? point.origin_detail}` : undefined}
        >
          {originLabel(point)}
        </span>
        {point.usage.length > 0 ? (
          <span
            className="text-muted-foreground inline-flex h-6 items-center rounded-full bg-primary/10 px-2 text-xs"
            title={`Used in: ${usageKeys.map(resumeName).join(", ")}`}
          >
            {/* A bullet no longer offered can still sit on resumes it was
                added to: "Still on", so the chip never reads as offered. */}
            {point.state === "retired" ? "Still on" : "On"} {usageKeys.length}{" "}
            {usageKeys.length === 1 ? "resume" : "resumes"}
          </span>
        ) : null}
        {hasDrift ? (
          <span
            className="inline-flex h-6 items-center gap-1 rounded-full bg-amber-500/15 px-2 text-xs text-amber-800 dark:text-amber-200"
            title="A resume still uses older wording."
          >
            <TriangleAlert className="size-3" aria-hidden="true" /> Wording differs
          </span>
        ) : null}
        {point.tags.map((tag) => (
          <Badge key={tag} variant="secondary" className="rounded-full font-normal">
            {tag}
          </Badge>
        ))}
        {/* "You · You said it" said one thing twice. */}
        {point.origin === "manual" && point.provenance === "user_stated" ? null : (
          <span
            className="text-muted-foreground inline-flex h-6 items-center rounded-full bg-muted/70 px-2 text-xs"
            title={
              point.provenance
                ? undefined
                : "Added before we tracked where bullets come from."
            }
          >
            {point.provenance
              ? (PROVENANCE_LABELS[point.provenance] ?? "Unknown source")
              : "Unknown source"}
          </span>
        )}
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
            // Not a native `disabled`: the menu returns focus here, and a
            // disabled trigger dropped it to <body> while the change saved.
            aria-disabled={pending}
            aria-label={`Status: ${current.label}. Change status`}
            className={cn(
              "inline-flex h-6 items-center gap-1.5 rounded-full px-2 text-xs font-medium transition-[transform,box-shadow] duration-150 ease-out hover:shadow-sm active:scale-[0.97] focus-visible:outline-2 focus-visible:outline-ring aria-disabled:opacity-50",
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
              if (!pending && item.value !== state) onSelect(item.value);
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
