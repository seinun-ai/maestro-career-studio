"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive } from "lucide-react";
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
import { couldnt } from "@/lib/error-text";
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

/** Where focus goes once an action's refetch has re-rendered the list, read when the user acted. */
type HandOff = (getTarget: () => HTMLElement | null) => void;

/**
 * Similar bullets on one item, one card per group, each its own decision: Combine into one, Stop
 * using one of them, or Not the same. Every action refetches the item, so the bullets list behind
 * the dialog follows while it stays open.
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
  });
  // The Tidy bullets button leaves once fewer than two bullets are active, so Done can find its
  // opener gone: the return falls back to the main area, never <body>.
  const returnToOpener = useOpenerReturn(open);

  // A card that leaves (combined, or kept apart) or a row that leaves (Stop using) takes the
  // focused button with it. Armed once the refetch has resolved, so the check runs after the
  // commit that renders the new list.
  const pendingFocus = useRef<(() => HTMLElement | null) | null>(null);
  useEffect(() => {
    const getTarget = pendingFocus.current;
    if (!getTarget) return;
    pendingFocus.current = null;
    focusIfDropped(getTarget());
  });
  const handOff: HandOff = (getTarget) => {
    pendingFocus.current = getTarget;
  };

  const report = groom.data;
  const state = report ? groomState(report) : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* scroll-pb-20: the sticky footer is about 65px tall, and a control focused by Tab scrolls clear of it. */}
      <DialogContent size="lg" finalFocus={returnToOpener} className="scroll-pb-20">
        <DialogHeader>
          <DialogTitle>Similar bullets on {entityTitle}</DialogTitle>
          <DialogDescription>
            These say nearly the same thing. Keep one as the bullet and fold the others into it as wordings.
            Nothing changes on your resumes.
          </DialogDescription>
          <p className="text-muted-foreground text-body-small">{KEEPER_RULE}</p>
        </DialogHeader>

        {/* The landmark a handed-off focus falls back to once the last card has gone. */}
        <div tabIndex={-1} className="outline-none">
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
                <ClusterCard key={cluster.keeper_id} entityId={entityId} cluster={cluster} handOff={handOff} />
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
  handOff,
}: {
  entityId: UUID;
  cluster: GroomCluster;
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

  const combine = useMutation({
    mutationFn: ({ keeperId }: { keeperId: UUID; losers: GroomMember[]; keeperText: string }) =>
      combineKbPoints(keeperId, otherIds(cluster, keeperId)),
    onSuccess: async (response, { losers, keeperText }) => {
      const plan = undoCombinePlan(losers, response.repointed);
      toast.success(combinedToast(losers.length, keeperText), {
        action: {
          label: "Undo",
          onClick: () =>
            Promise.all(plan.restore.map((r) => patchKbPoint(r.id, { state: r.state, unmerge: true })))
              .then(() => Promise.all(plan.recombine.map((r) => combineKbPoints(r.keeperId, r.pointIds))))
              .then(() => invalidate())
              .catch((error: Error) => toast.error(couldnt("undo the combine", error))),
        },
      });
      const target = nextCard();
      await invalidate();
      handOff(target);
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
      await invalidate();
      handOff(() =>
        card?.isConnected ? card.querySelector<HTMLElement>("[data-groom-combine]") : otherwise(),
      );
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
      const target = nextCard();
      await invalidate();
      handOff(target);
    },
    onError: (error: Error) => toast.error(couldnt("save that these are different", error)),
  });
  const apartOnce = useSingleFlight(apart.mutate);

  const pending = combine.isPending || retire.isPending || apart.isPending;

  return (
    <li ref={cardRef} className="rounded-corner-lg bg-surface-container-low p-3">
      <p id={`${groupId}-score`} className="text-muted-foreground text-label-medium">
        {Math.round(cluster.score * 100)}% similar
      </p>
      <RadioGroup<UUID>
        aria-labelledby={`${groupId}-score`}
        className="mt-2 gap-2"
        value={selected}
        onValueChange={(value) => setPicked(value)}
        // readOnly, not disabled: a disabled radio that holds focus drops it to <body>.
        readOnly={pending}
      >
        {cluster.members.map((member) => {
          const keep = member.id === selected;
          const rowId = `${groupId}-${member.id}`;
          return (
            <div key={member.id} className="flex items-start gap-2">
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
                  disabled={pending}
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
          disabled={pending}
          pending={apart.isPending}
        >
          Not the same
        </Button>
        <Button
          data-groom-combine=""
          size="sm"
          onClick={() =>
            combineOnce({
              keeperId: selected,
              // Each with its prior state, which Undo puts back.
              losers: cluster.members.filter((m) => m.id !== selected),
              keeperText: keeper?.text ?? "",
            })
          }
          disabled={pending}
          pending={combine.isPending}
        >
          Combine into one
        </Button>
      </div>
    </li>
  );
}
