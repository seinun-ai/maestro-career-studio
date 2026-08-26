"use client";

import { useMemo, useState } from "react";
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
import { Textarea } from "@/components/ui/textarea";
import { draftRewrite, apiFetch } from "@/lib/api";
import {
  STALE_APPLY_HINT,
} from "@/lib/health-report";
import { toastRewriteError } from "./report-errors";
import { wordDiff } from "@/lib/word-diff";
import type { ResumeData } from "@/lib/types";

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
}) {
  const groups = useMemo(() => experienceProjects(data), [data]);
  const [picked, setPicked] = useState<PickedBullet | null>(null);
  const [prose, setProse] = useState("");
  const [draft, setDraft] = useState<{
    suggestion: string;
    content_hash: string;
  } | null>(null);

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
      const path =
        kind === "base"
          ? `/api/base-resumes/${resumeKey}/edits`
          : `/api/applications/${resumeKey}/edits`;
      return apiFetch(path, {
        method: "PATCH",
        body: JSON.stringify({
          ops: [
            {
              kind: "replace_bullet",
              section: picked.section,
              index: picked.index,
              bullet_index: picked.bullet_index,
              value: draft.suggestion,
              expected_content_hash: draft.content_hash,
            },
          ],
        }),
      });
    },
    onSuccess: () => {
      toast.success("Applied and saved as a new version");
      onApplied();
      reset();
      onOpenChange(false);
    },
    onError: (err: Error) => toastRewriteError(err, onReanalyze),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="flex max-h-[80vh] w-[min(92vw,34rem)] max-w-[min(92vw,34rem)] flex-col overflow-hidden">
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
          {picked && (
            <Textarea
              rows={2}
              aria-label={`How ${skill} shows up in this bullet`}
              placeholder={`How ${skill} shows up here`}
              value={prose}
              onChange={(e) => setProse(e.target.value)}
              disabled={locked}
              className="text-sm"
            />
          )}
          {draft && picked && (
            <p className="max-w-[65ch] text-sm leading-relaxed">
              {wordDiff(picked.text, draft.suggestion).map((token, i) => (
                <span
                  key={i}
                  className={
                    token.kind === "removed"
                      ? "bg-red-500/10 text-red-600 line-through dark:text-red-400"
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
        <DialogFooter>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              reset();
              onOpenChange(false);
            }}
          >
            Cancel
          </Button>
          {draft ? (
            <Button
              size="sm"
              disabled={locked || applyMut.isPending}
              title={locked ? STALE_APPLY_HINT : undefined}
              onClick={() => applyMut.mutate()}
            >
              {applyMut.isPending ? "Applying…" : "Apply"}
            </Button>
          ) : (
            <Button
              size="sm"
              disabled={
                locked || !picked || prose.trim().length === 0 || draftMut.isPending
              }
              onClick={() => draftMut.mutate()}
            >
              {draftMut.isPending ? "Drafting…" : "Draft rewrite"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
