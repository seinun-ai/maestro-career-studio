"use client";

import { useId, useMemo, useState, type ComponentProps } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { draftRewrite, applyResumeEdits } from "@/lib/api";
import { notifyRenderNote } from "@/lib/render-note";
import {
  STALE_APPLY_HINT,
} from "@/lib/health-report";
import { toastRewriteError } from "./report-errors";
import { wordDiff } from "@/lib/word-diff";
import type { ResumeData } from "@/lib/types";

type DialogContentProps = ComponentProps<typeof DialogContent>;

type PickedBullet = {
  section: "experience" | "projects";
  index: number;
  bullet_index: number;
  text: string;
  label: string;
};

function experienceProjects(data: ResumeData): {
  title: string;
  section: "experience" | "projects";
  entries: { label: string; index: number; bullets: string[] }[];
}[] {
  return [
    {
      title: "Experience",
      section: "experience" as const,
      entries: (data.experience ?? []).map((entry, index) => ({
        index,
        label: [entry.role, entry.company].filter(Boolean).join(" · ") || `Experience ${index + 1}`,
        bullets: entry.bullets ?? [],
      })),
    },
    {
      title: "Projects",
      section: "projects" as const,
      entries: (data.projects ?? []).map((entry, index) => ({
        index,
        label: entry.name || `Project ${index + 1}`,
        bullets: entry.bullets ?? [],
      })),
    },
  ].filter((group) => group.entries.some((entry) => entry.bullets.length > 0));
}

export function DemonstrateSkillDialog({
  open,
  onOpenChange,
  skill,
  data,
  kind,
  resumeKey,
  locked,
  onApplied,
  onReanalyze,
  finalFocus,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  skill: string;
  data: ResumeData;
  kind: "base" | "application";
  resumeKey: string;
  locked?: boolean;
  onApplied: () => void;
  onReanalyze?: () => void;
  /** Where focus goes when the dialog closes: an Apply disables its opener. */
  finalFocus?: DialogContentProps["finalFocus"];
}) {
  const groups = useMemo(() => experienceProjects(data), [data]);
  const [picked, setPicked] = useState<PickedBullet | null>(null);
  const [prose, setProse] = useState("");
  const [draft, setDraft] = useState<{
    suggestion: string;
    content_hash: string;
  } | null>(null);
  const rewriteId = useId();

  const reset = () => {
    setPicked(null);
    setProse("");
    setDraft(null);
  };

  const draftMut = useMutation({
    mutationFn: () => {
      if (!picked) throw new Error("Pick a bullet first");
      return draftRewrite(kind, resumeKey, {
        location: {
          section: picked.section,
          index: picked.index,
          bullet_index: picked.bullet_index,
        },
        context: `demonstrates ${skill}: ${prose.trim()}`,
        expected_content_hash: undefined,
      });
    },
    onSuccess: (result) => setDraft(result),
    onError: (err: Error) => toastRewriteError(err, onReanalyze),
  });

  const applyMut = useMutation({
    mutationFn: async () => {
      if (!picked || !draft) throw new Error("Nothing to apply");
      return applyResumeEdits(kind, resumeKey, [
        {
          kind: "replace_bullet",
          section: picked.section,
          index: picked.index,
          bullet_index: picked.bullet_index,
          value: draft.suggestion,
          expected_content_hash: draft.content_hash,
        },
      ]);
    },
    onSuccess: (result) => {
      notifyRenderNote(result);
      toast.success("Applied and saved as a new version");
      onApplied();
      reset();
      onOpenChange(false);
    },
    onError: (err: Error) => toastRewriteError(err, onReanalyze),
  });

  // One request per click: a double click read isPending === false twice.
  const draftOnce = useSingleFlight(draftMut.mutate);
  const applyOnce = useSingleFlight(applyMut.mutate);

  return (
    // Closing keeps the picked bullet, the prose and a drafted rewrite (it
    // cost a model call); only a successful apply clears them. A draft kept
    // past a re-analysis is safe: the apply carries its content hash.
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent finalFocus={finalFocus} className="flex max-h-[80vh] w-[min(92vw,34rem)] max-w-[min(92vw,34rem)] flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle>Demonstrate {skill}</DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground -mt-2 text-xs">
          Pick one bullet, then one line on how {skill} shows up there.
        </p>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {groups.map((group) => (
            <div key={group.section}>
              <p className="text-sm font-medium">{group.title}</p>
              <ul className="mt-1 space-y-1">
                {group.entries.map((entry) => (
                  <li key={`${group.section}:${entry.index}`} className="rounded-md border px-2 py-1">
                    <p className="truncate text-sm">{entry.label}</p>
                    <ul className="mt-1 space-y-1">
                      {entry.bullets.map((bullet, bulletIndex) => {
                        const selected =
                          picked?.section === group.section &&
                          picked.index === entry.index &&
                          picked.bullet_index === bulletIndex;
                        return (
                          <li key={bulletIndex}>
                            <button
                              type="button"
                              className={`w-full rounded px-1 py-1 text-left text-xs ${
                                selected ? "bg-muted" : "hover:bg-muted/60"
                              }`}
                              onClick={() => {
                                setPicked({
                                  section: group.section,
                                  index: entry.index,
                                  bullet_index: bulletIndex,
                                  text: bullet,
                                  label: `${entry.label} · bullet ${bulletIndex + 1}`,
                                });
                                setDraft(null);
                              }}
                            >
                              <span className="line-clamp-2">{bullet}</span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        {picked && (
          <div className="space-y-2 border-t pt-3">
            <p className="text-muted-foreground truncate text-xs">
              <span className="font-medium">{picked.label}</span>
              {" · "}
              <span className="italic">{picked.text}</span>
            </p>
            <Label htmlFor={rewriteId}>How {skill} shows up in this bullet</Label>
            <Textarea
              id={rewriteId}
              rows={2}
              value={prose}
              onChange={(e) => setProse(e.target.value)}
              disabled={locked}
              className="text-sm"
            />
            {draft && (
              <p className="max-w-[65ch] text-sm leading-relaxed">
                {wordDiff(picked.text, draft.suggestion).map((token, i) => (
                  <span
                    key={i}
                    className={
                      token.kind === "removed"
                        ? "bg-destructive/10 text-destructive line-through"
                        : token.kind === "added"
                          ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                          : undefined
                    }
                  >
                    {token.text}{" "}
                  </span>
                ))}
              </p>
            )}
          </div>
        )}
        <DialogFooter>
          <Button size="sm" variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {draft ? (
            <Button
              size="sm"
              disabled={locked || applyMut.isPending}
              title={locked ? STALE_APPLY_HINT : undefined}
              // Both stay focusable while they work: a disabled button that
              // has focus drops it to the page.
              focusableWhenDisabled
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={() => applyOnce()}
            >
              {applyMut.isPending ? "Applying…" : "Apply"}
            </Button>
          ) : (
            <Button
              size="sm"
              disabled={
                locked || !picked || prose.trim().length === 0 || draftMut.isPending
              }
              focusableWhenDisabled
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={() => draftOnce()}
            >
              {draftMut.isPending ? "Drafting…" : "Draft rewrite"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
