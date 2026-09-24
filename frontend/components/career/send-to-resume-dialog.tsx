"use client";

import { useMemo, useRef, useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { ArrowLeft, Pencil, Plus, Sparkles, X } from "lucide-react";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { kbAdapt, kbAdaptApply, kbPort } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { useBaseResumes } from "@/hooks/use-base-resume-label";
import { useFocusOnNextCommit } from "@/hooks/use-focus-return";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { notifyRenderOutcome } from "@/lib/render-note";
import type {
  KBAdaptAction,
  KBAdaptDropped,
  KBEntityDetail,
  KBPortResponse,
} from "@/lib/types";
import { baseResumeLabel } from "@/lib/types";
import { cn } from "@/lib/utils";

type ReviewRow = {
  key: number;
  text: string;
  sourcePointIds: string[];
  replaces: number | null;
  action: KBAdaptAction;
  reason: string | null;
  included: boolean;
};

const ACTION_CHIPS: Record<KBAdaptAction, { label: string; chip: string }> = {
  rewritten: { label: "Rewritten", chip: "bg-primary/10 text-primary" },
  merged: { label: "Merged", chip: "bg-primary/10 text-primary" },
  replace: { label: "Replaces existing", chip: "bg-primary/10 text-primary" },
  kept: { label: "Kept as is", chip: "bg-muted text-muted-foreground" },
};

/**
 * Mounted for the page's lifetime: closing keeps the selection, the target, an
 * adapt proposal (a model call) and any row edits, and a reopen mid-Apply shows
 * that Apply still running. The caller re-keys it on `onSent`, the only clear.
 */
export function SendToResumeDialog({
  open,
  onOpenChange,
  onSent,
  entity,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** A port or apply landed: the caller starts the next send fresh. */
  onSent: () => void;
  entity: KBEntityDetail;
}) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const approved = useMemo(
    () => entity.points.filter((point) => point.state === "approved"),
    [entity.points],
  );
  const pointText = useMemo(
    () => new Map(entity.points.map((point) => [point.id, point.text])),
    [entity.points],
  );
  // null = untouched: every approved point, as of now. The dialog outlives
  // many opens, so points approved since mount are included and deleted ones
  // drop out.
  const [picked, setPicked] = useState<Set<string> | null>(null);
  const approvedIds = useMemo(() => new Set(approved.map((p) => p.id)), [approved]);
  const selected = useMemo(
    () => (picked === null ? approvedIds : new Set([...picked].filter((id) => approvedIds.has(id)))),
    [picked, approvedIds],
  );
  const [targetSlug, setTargetSlug] = useState("");
  const [step, setStep] = useState<"select" | "review">("select");
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [dropped, setDropped] = useState<KBAdaptDropped[]>([]);
  const [existingBullets, setExistingBullets] = useState<string[]>([]);
  const [editingKey, setEditingKey] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  // Adapt's button goes with the select step; its success lands on Apply.
  const applyRef = useRef<HTMLButtonElement>(null);
  const focusNext = useFocusOnNextCommit();

  // Certifications and custom sections port directly — there is nothing to adapt.
  const adaptable = entity.kind !== "certification" && entity.kind !== "extra";

  const resumes = useBaseResumes(false, { enabled: open });
  const targets = resumes.data ?? [];
  const selectedTarget = targets.find((resume) => resume.slug === targetSlug);
  const targetLabel = baseResumeLabel(targetSlug, targets);

  const finishPort = (response: KBPortResponse) => {
    const item = response.report.items[0];
    const ported = item?.ported_point_ids.length ?? 0;
    const skipped = item?.skipped_duplicate_point_ids.length ?? 0;
    queryClient.setQueryData(["base-resumes", targetSlug], response.resume);
    void queryClient.invalidateQueries({ queryKey: ["base-resumes"] });
    void queryClient.invalidateQueries({
      queryKey: ["resume-versions", "base", targetSlug],
    });
    void queryClient.invalidateQueries({ queryKey: ["kb", "entity", entity.id] });
    // The port is committed before the target re-renders, so a render failure
    // now comes back beside the success (it used to be a 4xx for a port that
    // had already landed), not instead of it.
    notifyRenderOutcome(response.resume, { staleLabel: targetLabel });
    toast.success(
      `Added to ${targetLabel}. ${ported} ${ported === 1 ? "bullet" : "bullets"} added${skipped ? `, ${skipped} already there` : ""}.`,
      {
        action: {
          label: "View resume",
          onClick: () => router.push(`/base-resumes/${targetSlug}`),
        },
      },
    );
    onOpenChange(false);
    onSent();
  };

  const port = useMutation({
    mutationFn: () =>
      kbPort({
        target_slug: targetSlug,
        items: [
          {
            entity_id: entity.id,
            point_ids: [...selected],
            ...(entity.kind === "extra"
              ? {
                  section_key:
                    entity.section_key ??
                    (entity.detail?.section_key as string | undefined) ??
                    undefined,
                }
              : {}),
          },
        ],
      }),
    onSuccess: finishPort,
    onError: (error: Error) => toast.error(couldnt("add to the resume", error)),
  });

  const adapt = useMutation({
    mutationFn: () =>
      kbAdapt({
        target_slug: targetSlug,
        entity_id: entity.id,
        point_ids: [...selected],
      }),
    onSuccess: (proposal) => {
      setRows(
        proposal.bullets.map((bullet, index) => ({
          key: index,
          text: bullet.text,
          sourcePointIds: bullet.source_point_ids,
          replaces: bullet.replaces_bullet_index,
          action: bullet.action,
          reason: bullet.reason,
          included: true,
        })),
      );
      setDropped(proposal.dropped);
      setExistingBullets(proposal.existing_bullets);
      setEditingKey(null);
      setStep("review");
      focusNext(applyRef);
    },
    onError: (error: Error) => toast.error(couldnt("adapt the bullets", error)),
  });

  const apply = useMutation({
    mutationFn: () =>
      kbAdaptApply({
        target_slug: targetSlug,
        entity_id: entity.id,
        bullets: rows
          .filter((row) => row.included && row.text.trim())
          .map((row) => ({
            text: row.text.trim(),
            source_point_ids: row.sourcePointIds,
            replaces_bullet_index: row.replaces,
            replaces_text:
              row.replaces !== null ? (existingBullets[row.replaces] ?? null) : null,
          })),
      }),
    onSuccess: finishPort,
    onError: (error: Error) => toast.error(couldnt("add to the resume", error)),
  });

  // One request per click: a double click read isPending === false twice
  // and sent the points, or paid for the adaptation, twice.
  const portOnce = useSingleFlight(port.mutate);
  const adaptOnce = useSingleFlight(adapt.mutate);
  const applyOnce = useSingleFlight(apply.mutate);
  const pending = port.isPending || adapt.isPending || apply.isPending;

  const toggle = (pointId: string) =>
    setPicked((current) => {
      const next = new Set(current ?? approvedIds);
      if (next.has(pointId)) next.delete(pointId);
      else next.add(pointId);
      return next;
    });

  const toggleRow = (key: number) =>
    setRows((current) =>
      current.map((row) =>
        row.key === key ? { ...row, included: !row.included } : row,
      ),
    );

  const startEdit = (row: ReviewRow) => {
    setEditingKey(row.key);
    setEditText(row.text);
  };

  const saveEdit = () => {
    const value = editText.trim();
    if (value) {
      setRows((current) =>
        current.map((row) =>
          row.key === editingKey ? { ...row, text: value, included: true } : row,
        ),
      );
    }
    setEditingKey(null);
  };

  const restoreDropped = (item: KBAdaptDropped) => {
    const text = pointText.get(item.point_id);
    if (!text) return;
    setRows((current) => [
      ...current,
      {
        key: current.length ? Math.max(...current.map((row) => row.key)) + 1 : 0,
        text,
        sourcePointIds: [item.point_id],
        replaces: null,
        action: "kept",
        reason: null,
        included: true,
      },
    ]);
    setDropped((current) => current.filter((d) => d.point_id !== item.point_id));
  };

  const nothingSelected = approved.length > 0 && selected.size === 0;
  const includedCount = rows.filter((row) => row.included && row.text.trim()).length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>
            {step === "select" ? "Add to a resume" : "Review new wording"}
          </DialogTitle>
          <DialogDescription>
            {step === "select"
              ? `Copy bullets from ${entity.title} to a base resume. Adapt rewrites them to fit it. Add as is copies them exactly.`
              : "Only checked bullets are added. You can edit any of them first."}
          </DialogDescription>
        </DialogHeader>

        {step === "select" ? (
          <div className="grid gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="kb-send-target">Resume</Label>
              <Select
                value={targetSlug}
                onValueChange={(value) => setTargetSlug(value ?? "")}
                disabled={resumes.isLoading || targets.length === 0 || pending}
              >
                <SelectTrigger id="kb-send-target" className="w-full">
                  <SelectValue>
                    {selectedTarget
                      ? (selectedTarget.display_name ?? baseResumeLabel(selectedTarget.slug))
                      : resumes.isLoading
                        ? "Loading…"
                        : "Choose a resume"}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {targets.map((resume) => (
                    <SelectItem key={resume.slug} value={resume.slug}>
                      {resume.display_name ?? baseResumeLabel(resume.slug)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {resumes.error && (
                <p role="alert" className="text-destructive text-xs">
                  {couldnt("load your resumes", resumes.error)}
                </p>
              )}
              {!resumes.isLoading && !resumes.error && targets.length === 0 && (
                <p className="text-muted-foreground text-xs">
                  You have no base resumes yet.
                </p>
              )}
            </div>

            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Approved bullets</legend>
              {approved.length === 0 ? (
                <p className="text-muted-foreground rounded-xl bg-muted/45 p-3 text-xs">
                  No approved bullets. Its title and dates can still be added.
                </p>
              ) : (
                <div className="max-h-72 space-y-2 overflow-y-auto rounded-xl bg-muted/45 p-3">
                  {approved.map((point) => (
                    <label
                      key={point.id}
                      className="flex cursor-pointer items-start gap-3 text-sm"
                    >
                      <Checkbox checked={selected.has(point.id)} onCheckedChange={() => toggle(point.id)} disabled={pending} className="mt-1" />
                      <span className="leading-relaxed">{point.text}</span>
                    </label>
                  ))}
                </div>
              )}
            </fieldset>
          </div>
        ) : (
          <div className="max-h-96 space-y-4 overflow-y-auto">
            <ul className="space-y-2">
              {rows.map((row) => (
                <li key={row.key} className="rounded-xl bg-muted/45 p-3">
                  {editingKey === row.key ? (
                    <div className="space-y-2">
                      <Textarea
                        rows={3}
                        aria-label="Edit bullet text"
                        value={editText}
                        onChange={(event) => setEditText(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Escape") {
                            // stopPropagation so the Dialog doesn't also close.
                            event.preventDefault();
                            event.stopPropagation();
                            setEditingKey(null);
                          }
                        }}
                        autoFocus
                      />
                      <div className="flex justify-end gap-2">
                        <Button
                          className="rounded-full"
                          size="sm"
                          variant="ghost"
                          onClick={() => setEditingKey(null)}
                        >
                          <X aria-hidden="true" /> Cancel
                        </Button>
                        <Button
                          className="rounded-full px-4"
                          size="sm"
                          onClick={saveEdit}
                          disabled={!editText.trim()}
                        >
                          Save
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start gap-3">
                      <Checkbox checked={row.included} onCheckedChange={() => toggleRow(row.key)} disabled={pending} className="mt-1" />
                      <div className="min-w-0 flex-1">
                        <p
                          className={cn(
                            "text-sm leading-relaxed",
                            !row.included && "text-muted-foreground line-through",
                          )}
                        >
                          {row.text}
                        </p>
                        {row.replaces !== null &&
                        existingBullets[row.replaces] !== undefined ? (
                          <p className="text-muted-foreground mt-1 text-xs line-through">
                            {existingBullets[row.replaces]}
                          </p>
                        ) : null}
                        {row.action !== "kept"
                          ? row.sourcePointIds.map((id) => {
                              const source = pointText.get(id);
                              return source ? (
                                <p key={id} className="text-muted-foreground mt-1 text-xs">
                                  <span className="font-medium">From bullet:</span> {source}
                                </p>
                              ) : null;
                            })
                          : null}
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          <span
                            className={cn(
                              "inline-flex h-6 items-center rounded-full px-2 text-xs font-medium",
                              ACTION_CHIPS[row.action].chip,
                            )}
                          >
                            {ACTION_CHIPS[row.action].label}
                            {row.action === "merged"
                              ? ` · ${row.sourcePointIds.length}`
                              : ""}
                          </span>
                          {row.reason ? (
                            <span className="text-muted-foreground text-xs">
                              {row.reason}
                            </span>
                          ) : null}
                        </div>
                      </div>
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label="Edit bullet"
                        title="Edit bullet"
                        onClick={() => startEdit(row)}
                        disabled={pending}
                      >
                        <Pencil aria-hidden="true" />
                      </Button>
                    </div>
                  )}
                </li>
              ))}
            </ul>

            {dropped.length > 0 ? (
              <div className="space-y-2">
                <p className="text-muted-foreground text-xs font-medium">
                  Already on this resume
                </p>
                <ul className="space-y-2">
                  {dropped.map((item) => (
                    <li
                      key={item.point_id}
                      className="flex items-start gap-3 rounded-xl bg-muted/30 p-3"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-muted-foreground text-sm leading-relaxed">
                          {pointText.get(item.point_id) ?? "Unknown bullet"}
                        </p>
                        {item.reason ? (
                          <p className="text-muted-foreground mt-1 text-xs">
                            {item.reason}
                          </p>
                        ) : null}
                      </div>
                      <Button
                        className="rounded-full shrink-0"
                        size="sm"
                        variant="ghost"
                        onClick={() => restoreDropped(item)}
                        disabled={pending}
                      >
                        <Plus aria-hidden="true" /> Add anyway
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        )}

        <DialogFooter>
          {step === "select" ? (
            <>
              <Button
                className="rounded-full"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={pending}
              >
                Close
              </Button>
              <Button
                className="rounded-full data-disabled:pointer-events-none data-disabled:opacity-50"
                variant={adaptable ? "outline" : "default"}
                onClick={() => portOnce()}
                disabled={!targetSlug || nothingSelected || pending}
                // These three stay focusable while they work: a disabled
                // button that has focus drops it to the page.
                focusableWhenDisabled
              >
                {port.isPending
                  ? "Adding…"
                  : adaptable
                    ? "Add as is"
                    : "Add to resume"}
              </Button>
              {adaptable ? (
                <Button
                  className="rounded-full px-4 data-disabled:pointer-events-none data-disabled:opacity-50"
                  onClick={() => adaptOnce()}
                  disabled={!targetSlug || selected.size === 0 || pending}
                  focusableWhenDisabled
                >
                  <Sparkles aria-hidden="true" />
                  {adapt.isPending ? "Adapting…" : "Adapt and preview"}
                </Button>
              ) : null}
            </>
          ) : (
            <>
              <Button
                className="rounded-full"
                variant="ghost"
                onClick={() => setStep("select")}
                disabled={pending}
              >
                <ArrowLeft aria-hidden="true" /> Back
              </Button>
              <Button
                ref={applyRef}
                className="rounded-full px-4 data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={() => applyOnce()}
                // Also disabled mid-edit: the pending textarea text is not in
                // `rows` yet, so applying would silently use the old text.
                disabled={includedCount === 0 || pending || editingKey !== null}
                focusableWhenDisabled
              >
                {apply.isPending
                  ? "Adding…"
                  : `Add ${includedCount} to resume`}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
