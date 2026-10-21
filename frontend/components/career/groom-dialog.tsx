"use client";

import { useId, useLayoutEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive } from "lucide-react";
import { toast } from "sonner";

import { HintTip } from "@/components/hint-tip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Radio, RadioGroup } from "@/components/ui/radio-group";
import { Skeleton } from "@/components/ui/skeleton";
import { useOpenerReturn } from "@/hooks/use-focus-return";
import { useSingleFlight } from "@/hooks/use-single-flight";
import {
  bulkKbPointState,
  combineKbPoints,
  forgetKeepApartKbPoints,
  getKbGroom,
  keepApartKbPoints,
  patchKbPoint,
} from "@/lib/api";
import { couldnt, errorDetail } from "@/lib/error-text";
import { focusIfDropped, focusSuccessor } from "@/lib/focus";
import {
  KEEPER_RULE,
  combinedToast,
  groomState,
  otherIds,
  pairsOf,
  undoCombinePlan,
} from "@/lib/kb-groom";
import type { GroomCluster, GroomMember, UUID } from "@/lib/types";

const STATE_WORDS: Record<GroomMember["state"], string> = {
  draft: "Draft",
  approved: "Approved",
  retired: "Not used",
};

/**
 * Arms a focus hand-off: once `source` (the card or row an action removes) leaves the document,
 * focus that fell to <body> goes to `target()`.
 */
type HandOff = (source: HTMLElement | null, target: () => HTMLElement | null) => void;

/**
 * Similar bullets on one item, one card per group, each its own decision: Combine into one, Stop
 * using one of them, or Not the same. Every action refetches the item, so the bullets list behind
 * the dialog follows while it stays open. When an action's refetch removes the card or row that
 * held focus, focus moves on to the next card's Combine into one (see `handOffArm`).
 */
export function GroomDialog({
  entityId,
  entityTitle,
  open,
  onOpenChange,
}: {
  entityId: UUID;
  entityTitle: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const groom = useQuery({
    queryKey: ["kb", "groom", entityId],
    queryFn: () => getKbGroom(entityId),
    enabled: open,
    // Not the app's 30 s: a bullet retired or edited on the page since the last open would come
    // back as a group with live buttons. Every open reads afresh, the old list dimmed meanwhile.
    staleTime: 0,
  });
  // A refetch with a list on screen: shown dimmed, and no card acts on a report being replaced.
  const refreshing = groom.isFetching && !groom.isPending;
  // The Tidy bullets button leaves once fewer than two bullets are active, so Done can find its
  // opener gone: the return falls back to the main area, never <body>.
  const returnToOpener = useOpenerReturn(open);

  // A card that leaves (combined, or kept apart) or a row that leaves (Stop using) takes the
  // focused button with it. An action arms the hand-off as soon as its write lands, before any
  // refetch starts, so whichever refetch removes the element finds it armed. The check is a
  // LAYOUT effect: it runs in the commit that removes the element, before Base UI's own
  // microtask would move a dropped focus to the dialog itself. The groom report's refetch
  // rendering with the element still there means it never left: the arm is dropped.
  const handOffArm = useRef<{
    source: HTMLElement;
    target: () => HTMLElement | null;
    armedAt: number;
  } | null>(null);
  const reportAt = Math.max(groom.dataUpdatedAt, groom.errorUpdatedAt);
  useLayoutEffect(() => {
    const arm = handOffArm.current;
    if (!arm) return;
    // Done mid-action: the dialog's own return (to Tidy bullets) wins.
    if (!open) {
      handOffArm.current = null;
      return;
    }
    if (arm.source.isConnected) {
      if (reportAt > arm.armedAt) handOffArm.current = null;
      return;
    }
    handOffArm.current = null;
    focusIfDropped(arm.target());
  });
  const handOff: HandOff = (source, target) => {
    handOffArm.current = source ? { source, target, armedAt: Date.now() } : null;
  };

  const report = groom.data;
  const state = report ? groomState(report) : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* scroll-pb-20: the sticky footer is about 65px tall, and a control focused by Tab scrolls clear of it. */}
      <DialogContent size="lg" finalFocus={returnToOpener} className="scroll-pb-20">
        <DialogHeader>
          <div className="flex items-center gap-1">
            <DialogTitle>Similar bullets on {entityTitle}</DialogTitle>
            <HintTip label="Which bullet is kept">{KEEPER_RULE}</HintTip>
          </div>
          <DialogDescription>
            These say nearly the same thing. Keep one as the bullet and fold the others into it as wordings.
            Nothing changes on your resumes.
          </DialogDescription>
        </DialogHeader>

        {/* The landmark a handed-off focus falls back to once the last card has gone. */}
        <div tabIndex={-1} className="outline-none" data-pending={refreshing ? "true" : undefined}>
          {groom.isPending ? (
            <div className="grid gap-3" aria-hidden="true">
              <Skeleton className="h-32 rounded-corner-lg" />
              <Skeleton className="h-32 rounded-corner-lg" />
            </div>
          ) : groom.isError ? (
            <div className="flex items-center justify-between gap-3 rounded-corner-md bg-surface-container-low p-3">
              <p role="alert" className="text-destructive text-body-small">
                {couldnt("look for similar bullets", groom.error)}
              </p>
              <Button size="sm" variant="outline" onClick={() => void groom.refetch()} pending={groom.isFetching}>
                Retry
              </Button>
            </div>
          ) : state === "failed" ? (
            <div className="flex items-center justify-between gap-3 rounded-corner-md bg-surface-container-low p-3">
              <p className="text-body-small">{"Couldn't compare wording right now."}</p>
              <Button size="sm" variant="outline" onClick={() => void groom.refetch()} pending={groom.isFetching}>
                Retry
              </Button>
            </div>
          ) : state === "empty" ? (
            <p className="text-muted-foreground rounded-corner-md bg-surface-container-low p-3 text-body-small">
              No similar bullets here.
            </p>
          ) : (
            <ul className="grid gap-3">
              {report?.clusters.map((cluster) => (
                <ClusterCard
                  key={cluster.keeper_id}
                  entityId={entityId}
                  cluster={cluster}
                  locked={refreshing}
                  handOff={handOff}
                />
              ))}
            </ul>
          )}
        </div>

        <DialogFooter sticky>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ClusterCard({
  entityId,
  cluster,
  locked,
  handOff,
}: {
  entityId: UUID;
  cluster: GroomCluster;
  /** The report is being refetched: nothing here may act on what it shows. */
  locked: boolean;
  handOff: HandOff;
}) {
  const queryClient = useQueryClient();
  const groupId = useId();
  const cardRef = useRef<HTMLLIElement>(null);
  const [picked, setPicked] = useState<UUID>(cluster.keeper_id);
  // A refetch can drop the picked member; the proposed keeper stands in.
  const selected = cluster.members.some((m) => m.id === picked) ? picked : cluster.keeper_id;
  const keeper = cluster.members.find((m) => m.id === selected);

  const invalidate = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["kb", "groom", entityId] }),
      queryClient.invalidateQueries({ queryKey: ["kb", "entity", entityId] }),
      queryClient.invalidateQueries({ queryKey: ["kb", "entities"] }),
      queryClient.invalidateQueries({ queryKey: ["kb", "drafts"] }),
    ]);
  // Read once the write lands and before the refetch, while this card and its neighbours are
  // attached: the next card's Combine into one, else the previous card's, else the list's landmark.
  const nextCard = () => focusSuccessor(cardRef.current, "[data-groom-combine]");

  // Undo of a Combine: each folded bullet back in its prior state, then the wordings the combine
  // moved off it back onto it, but only onto the ones that came back.
  const undoCombine = async (plan: ReturnType<typeof undoCombinePlan>) => {
    const settled = await Promise.allSettled(
      plan.restore.map((r) => patchKbPoint(r.id, { state: r.state, unmerge: true })),
    );
    const back = new Set(plan.restore.filter((_, i) => settled[i].status === "fulfilled").map((r) => r.id));
    const failed = settled.find((r): r is PromiseRejectedResult => r.status === "rejected");
    try {
      await Promise.all(
        plan.recombine.filter((r) => back.has(r.keeperId)).map((r) => combineKbPoints(r.keeperId, r.pointIds)),
      );
    } finally {
      // The restores landed either way: the list behind the dialog shows them.
      await invalidate();
    }
    if (!failed) return;
    if (back.size === 0) throw failed.reason;
    toast.error(
      `Put back ${back.size} of ${plan.restore.length} bullets. ${errorDetail(failed.reason) ?? "Try again."}`,
    );
  };

  const combine = useMutation({
    mutationFn: ({ keeperId, losers }: { keeperId: UUID; losers: GroomMember[]; keeperText: string }) =>
      combineKbPoints(
        keeperId,
        losers.map((m) => m.id),
      ),
    onSuccess: async (response, { losers, keeperText }) => {
      const plan = undoCombinePlan(losers, response.repointed);
      toast.success(combinedToast(losers.length, keeperText), {
        action: {
          label: "Undo",
          onClick: () =>
            undoCombine(plan).catch((error: Error) => toast.error(couldnt("undo the combine", error))),
        },
      });
      handOff(cardRef.current, nextCard());
      await invalidate();
    },
    onError: (error: Error) => toast.error(couldnt("combine the bullets", error)),
  });
  const combineOnce = useSingleFlight(combine.mutate);

  const retire = useMutation({
    mutationFn: async (member: GroomMember) => {
      const { results } = await bulkKbPointState([member.id], "retired");
      const row = results.find((r) => r.id === member.id);
      if (!row?.ok) throw new Error(row?.detail ?? "Try again.");
    },
    onSuccess: async (_none, member) => {
      toast.success("Won't be offered again", {
        action: {
          label: "Undo",
          onClick: () =>
            patchKbPoint(member.id, { state: member.state })
              .then(() => invalidate())
              .catch((error: Error) => toast.error(couldnt("undo the change", error))),
        },
      });
      // The row leaves; the group re-forms from the rest, or leaves too when one is left.
      const card = cardRef.current;
      const otherwise = nextCard();
      handOff(card?.querySelector<HTMLElement>(`[data-groom-member="${member.id}"]`) ?? null, () =>
        card?.isConnected ? card.querySelector<HTMLElement>("[data-groom-combine]") : otherwise(),
      );
      await invalidate();
    },
    onError: (error: Error) => toast.error(couldnt("stop using the bullet", error)),
  });
  const retireOnce = useSingleFlight(retire.mutate);

  const apart = useMutation({
    mutationFn: (ids: UUID[]) => keepApartKbPoints(ids),
    onSuccess: async (_pairs, ids) => {
      toast.success("Won't suggest these again", {
        action: {
          label: "Undo",
          onClick: () =>
            forgetKeepApartKbPoints(ids)
              .then(() => invalidate())
              .catch((error: Error) => toast.error(couldnt("undo the change", error))),
        },
      });
      handOff(cardRef.current, nextCard());
      await invalidate();
    },
    onError: (error: Error) => toast.error(couldnt("save that these are different", error)),
  });
  const apartOnce = useSingleFlight(apart.mutate);

  const pending = combine.isPending || retire.isPending || apart.isPending;
  // Locked buttons keep a focus they hold (focusableWhenDisabled): a refetch must not drop it.
  const busy = pending || locked;

  return (
    <li ref={cardRef} className="rounded-corner-lg bg-surface-container-low p-3">
      <Badge id={`${groupId}-score`} variant="secondary" className="tabular-nums">
        {Math.round(cluster.score * 100)}% similar
      </Badge>
      <RadioGroup<UUID>
        aria-labelledby={`${groupId}-score`}
        className="mt-2 gap-2"
        value={selected}
        onValueChange={(value) => setPicked(value)}
        // readOnly, not disabled: a disabled radio that holds focus drops it to <body>.
        readOnly={busy}
      >
        {cluster.members.map((member) => {
          const keep = member.id === selected;
          const rowId = `${groupId}-${member.id}`;
          return (
            <div key={member.id} data-groom-member={member.id} className="flex items-start gap-2">
              <label className="flex min-w-0 flex-1 items-start gap-2">
                <Radio value={member.id} aria-labelledby={`${rowId}-text`} aria-describedby={`${rowId}-meta`} />
                <span className="grid min-w-0 gap-0.5">
                  {keep ? <span className="text-label-medium text-primary">Keep this one</span> : null}
                  <span id={`${rowId}-text`} className="text-body-medium">
                    {member.text}
                  </span>
                  <span id={`${rowId}-meta`} className="text-muted-foreground text-body-small">
                    {[
                      STATE_WORDS[member.state],
                      member.usage_count > 0
                        ? `used on ${member.usage_count} ${member.usage_count === 1 ? "resume" : "resumes"}`
                        : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
              </label>
              {keep ? null : (
                <Button
                  size="xs"
                  variant="ghost"
                  title="Stop offering this bullet. Resumes that have it keep it."
                  onClick={() => retireOnce(member)}
                  disabled={busy}
                  focusableWhenDisabled
                  pending={retire.isPending && retire.variables?.id === member.id}
                >
                  <Archive aria-hidden="true" /> Stop using
                </Button>
              )}
            </div>
          );
        })}
      </RadioGroup>
      <div className="mt-3 flex justify-end gap-2">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => apartOnce(pairsOf(cluster))}
          disabled={busy}
          focusableWhenDisabled
          pending={apart.isPending}
        >
          Not the same
        </Button>
        <Button
          data-groom-combine=""
          size="sm"
          onClick={() => {
            const others = new Set(otherIds(cluster, selected));
            combineOnce({
              keeperId: selected,
              // Each with its prior state, which Undo puts back.
              losers: cluster.members.filter((m) => others.has(m.id)),
              keeperText: keeper?.text ?? "",
            });
          }}
          disabled={busy}
          focusableWhenDisabled
          pending={combine.isPending}
        >
          Combine into one
        </Button>
      </div>
    </li>
  );
}
