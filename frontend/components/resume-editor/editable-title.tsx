"use client";

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { toast } from "sonner";

import { IconButton } from "@/components/icon-button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { BaseResumeDetail } from "@/lib/types";

/**
 * The base resume's display name, edited in place as the page title.
 *
 * Writes through `PATCH /identity`, the same endpoint `RoleCategoryPicker`
 * uses: metadata only, so it does not rewrite `data_json`, record a resume
 * version, rewrite the disk file, or recompile the PDF. That is why it is safe
 * to commit on blur without a Save button.
 *
 * This is a deliberate behaviour change. Display name used to ride along on the
 * full PUT behind Save, while Target role — the field directly beside it —
 * saved instantly. Two adjacent identity fields with opposite persistence rules
 * is the kind of thing you only notice by hitting it. Both are instant now, and
 * the heavy Save is left to mean "write the résumé content and re-render the
 * PDF". `onChange` still lifts the value so the PUT keeps sending the same
 * string; the two writers never disagree.
 *
 * Escape reverts to the last committed value rather than keeping the draft —
 * the studio's other editors behave that way, and a title is cheap to retype.
 */
export function EditableTitle({
  slug,
  value,
  onChange,
}: {
  slug: string;
  value: string;
  onChange: (next: string) => void;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const committed = useRef(value);

  const save = useMutation({
    mutationFn: (next: string) =>
      apiFetch<BaseResumeDetail>(`/api/base-resumes/${slug}/identity`, {
        method: "PATCH",
        body: JSON.stringify({ display_name: next || null }),
      }),
    onSuccess: (updated) => {
      qc.setQueryData(["base-resumes", slug], updated);
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      committed.current = updated.display_name ?? "";
    },
    onError: (err: Error) => {
      toast.error(err.message);
      // Put the visible name back to what the server still holds.
      setDraft(committed.current);
      onChange(committed.current);
    },
  });

  const commit = () => {
    setEditing(false);
    const next = draft.trim();
    if (next === committed.current) return;
    onChange(next);
    save.mutate(next);
  };

  if (editing) {
    return (
      <Input
        autoFocus
        aria-label="Display name"
        value={draft}
        disabled={save.isPending}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          } else if (e.key === "Escape") {
            e.preventDefault();
            setDraft(committed.current);
            setEditing(false);
          }
        }}
        className="h-9 max-w-md text-[22px] font-medium tracking-tight"
      />
    );
  }

  return (
    // `group/title` + pointer-coarse so the pencil is reachable on touch, where
    // there is no hover — the failure mode that made every edit control in this
    // directory unusable on a tablet.
    <span className="group/title inline-flex items-center gap-1.5">
      {value || slug}
      <IconButton
        label="Rename resume"
        icon={<Pencil className="size-3.5" />}
        size="icon-xs"
        variant="ghost"
        className="pointer-coarse:opacity-100 opacity-0 transition-opacity group-hover/title:opacity-100 focus-visible:opacity-100"
        onClick={() => {
          setDraft(value);
          setEditing(true);
        }}
      />
    </span>
  );
}
