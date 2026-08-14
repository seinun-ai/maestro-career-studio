"use client";

import { useMemo, useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { apiFetch, kbAdapt, kbAdaptApply, kbPort } from "@/lib/api";
import type {
  BaseResumeSummary,
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
  kept: { label: "Kept as-is", chip: "bg-muted text-muted-foreground" },
};

export function SendToResumeDialog({
  open,
  onOpenChange,
  entity,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
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
  const [selected, setSelected] = useState(
    () => new Set(approved.map((point) => point.id)),
  );
  const [targetSlug, setTargetSlug] = useState("");
  const [step, setStep] = useState<"select" | "review">("select");
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [dropped, setDropped] = useState<KBAdaptDropped[]>([]);
  const [createEntry, setCreateEntry] = useState(false);
  const [existingBullets, setExistingBullets] = useState<string[]>([]);
  const [editingKey, setEditingKey] = useState<number | null>(null);
  const [editText, setEditText] = useState("");

  // Certifications and custom sections port directly — there is nothing to adapt.
  const adaptable = entity.kind !== "certification" && entity.kind !== "extra";

  const resumes = useQuery({
    queryKey: ["base-resumes"],
    queryFn: () => apiFetch<BaseResumeSummary[]>("/api/base-resumes"),
    enabled: open,
  });
  const targets = resumes.data ?? [];
  const selectedTarget = targets.find((resume) => resume.slug === targetSlug);
  const targetLabel = selectedTarget
    ? (selectedTarget.display_name ?? baseResumeLabel(selectedTarget.slug))
    : targetSlug;

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
    toast.success(
      `${item?.created_entry ? "Added entity" : `Ported ${ported} ${ported === 1 ? "point" : "points"}`}${skipped ? ` · ${skipped} duplicate${skipped === 1 ? "" : "s"} skipped` : ""}`,
      {
        action: {
          label: "View resume",
          onClick: () => router.push(`/base-resumes/${targetSlug}`),
        },
      },
    );
    onOpenChange(false);
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
    onError: (error: Error) => toast.error(error.message),
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
      setCreateEntry(proposal.create_entry);
      setExistingBullets(proposal.existing_bullets);
      setEditingKey(null);
      setStep("review");
    },
    onError: (error: Error) => toast.error(error.message),
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
    onError: (error: Error) => toast.error(error.message),
  });

  const pending = port.isPending || adapt.isPending || apply.isPending;

  const toggle = (pointId: string) =>
    setSelected((current) => {
      const next = new Set(current);
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
            {step === "select" ? "Send to resume" : "Review adapted points"}
          </DialogTitle>
          <DialogDescription>
            {step === "select"
              ? `Copy approved facts from ${entity.title} into one base resume. Adapt rewrites them to match that resume's voice; send as-is copies them verbatim.`
              : `Only checked bullets are applied to ${targetLabel}${createEntry ? " as a new entry" : "'s matching entry"}. Edit any bullet before applying.`}
          </DialogDescription>
        </DialogHeader>

        {step === "select" ? (
          <div className="grid gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="kb-send-target">Target base resume</Label>
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
                  {resumes.error.message}
                </p>
              )}
              {!resumes.isLoading && !resumes.error && targets.length === 0 && (
                <p className="text-muted-foreground text-xs">
                  No base resumes are available.
                </p>
              )}
            </div>

            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Approved points</legend>
              {approved.length === 0 ? (
                <p className="text-muted-foreground rounded-xl bg-muted/45 p-3 text-xs">
                  This item has no approved points. Its structured fields can still be
                  added.
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
                        aria-label="Edit point text"
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
                                  <span className="font-medium">From point:</span> {source}
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
                  Left out, already covered by this resume
                </p>
                <ul className="space-y-2">
                  {dropped.map((item) => (
                    <li
                      key={item.point_id}
                      className="flex items-start gap-3 rounded-xl bg-muted/30 p-3"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-muted-foreground text-sm leading-relaxed">
                          {pointText.get(item.point_id) ?? "Unknown point"}
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
                Cancel
              </Button>
              <Button
                className="rounded-full"
                variant={adaptable ? "outline" : "default"}
                onClick={() => port.mutate()}
                disabled={!targetSlug || nothingSelected || pending}
              >
                {port.isPending
                  ? "Sending…"
                  : adaptable
                    ? "Send as-is"
                    : "Send to resume"}
              </Button>
              {adaptable ? (
                <Button
                  className="rounded-full px-4"
                  onClick={() => adapt.mutate()}
                  disabled={!targetSlug || selected.size === 0 || pending}
                >
                  <Sparkles aria-hidden="true" />
                  {adapt.isPending ? "Adapting…" : "Adapt & preview"}
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
                className="rounded-full px-4"
                onClick={() => apply.mutate()}
                // Also disabled mid-edit: the pending textarea text is not in
                // `rows` yet, so applying would silently use the old text.
                disabled={includedCount === 0 || pending || editingKey !== null}
              >
                {apply.isPending
                  ? "Applying…"
                  : `Apply ${includedCount} to resume`}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
