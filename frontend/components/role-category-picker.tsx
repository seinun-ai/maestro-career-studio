"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  favoredRoleFromTag,
  identityFromFavoredRole,
  RolePicker,
} from "@/components/role-picker";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { BaseResumeDetail, FavoredRole, RoleCategory } from "@/lib/types";

/** The vocabulary, fetched once. Deliberately NOT duplicated client-side: it
 *  lives in backend/app/services/ats/data/role_categories.yaml, and a second
 *  copy here would recreate exactly the drift that file was written to end. */
export function useRoleCategories() {
  return useQuery({
    queryKey: ["role-categories"],
    queryFn: () => apiFetch<RoleCategory[]>("/api/role-categories"),
    staleTime: 60 * 60 * 1000, // vocabulary changes only on deploy
  });
}

export function roleLabel(key: string | null | undefined, options?: RoleCategory[]) {
  if (!key) return "Unknown";
  const hit = options?.find((o) => o.key === key);
  if (hit) return hit.label;
  // A row written before a category was renamed still renders.
  return key
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/** Prefer the free-text label when present; otherwise the catalog category. */
export function displayRoleTag(
  roleCategory: string,
  roleLabelText: string | null | undefined,
  options?: RoleCategory[],
) {
  if (roleLabelText) return roleLabelText;
  return roleLabel(roleCategory, options);
}

/** Read-only role badge. `unknown` is styled as an invitation, not an error —
 *  it is a legitimate state, and the design's promise is that it is always
 *  visible and always one click from being fixed. */
export function RoleBadge({
  role,
  roleLabel: label,
}: {
  role: string;
  roleLabel?: string | null;
}) {
  const { data: options } = useRoleCategories();
  const undeclared = role === "unknown" && !label;
  return (
    <Badge variant={undeclared ? "outline" : "secondary"} className="font-normal">
      {undeclared ? "Role not set" : displayRoleTag(role, label, options)}
    </Badge>
  );
}

/** Inline picker. Writes through PATCH /identity, which is metadata-only —
 *  it does not re-render the PDF or record a resume version. Thin single-mode
 *  wrapper over the shared RolePicker (free text included). */
export function RoleCategoryPicker({
  slug,
  roleCategory,
  roleLabel: label = null,
  proposed = false,
  className,
}: {
  slug: string;
  roleCategory: string;
  roleLabel?: string | null;
  /** True when the import pipeline guessed this role; the chip must look like a guess. */
  proposed?: boolean;
  className?: string;
}) {
  const qc = useQueryClient();
  const { data: options } = useRoleCategories();
  const [confirmed, setConfirmed] = useState(!proposed);
  const guessing = proposed && !confirmed;

  const save = useMutation({
    mutationFn: (entry: FavoredRole | null) =>
      apiFetch<BaseResumeDetail>(`/api/base-resumes/${slug}/identity`, {
        method: "PATCH",
        body: JSON.stringify(identityFromFavoredRole(entry)),
      }),
    onSuccess: (updated) => {
      qc.setQueryData(["base-resumes", slug], updated);
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      // Clearing reports itself as clearing. Routed through the same success
      // path, it used to announce "Role set to Unknown" — the storage sentinel
      // read back as if it were a role someone had chosen.
      const cleared = updated.role_category === "unknown" && !updated.role_label;
      toast.success(
        cleared
          ? "Role cleared"
          : `Role set to ${displayRoleTag(updated.role_category, updated.role_label, options)}`,
      );
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const value = favoredRoleFromTag(roleCategory, label, options);

  return (
    <div
      className="inline-flex max-w-full align-middle"
      title={guessing ? "Suggested — click to confirm or pick another" : undefined}
      onClick={() => {
        if (guessing) setConfirmed(true);
      }}
    >
      <RolePicker
        mode="single"
        value={value}
        onValueChange={(next) => {
          setConfirmed(true);
          // Skip no-ops so a remount / same chip does not PATCH.
          const prev = identityFromFavoredRole(value);
          const nextBody = identityFromFavoredRole(next);
          if (
            prev.role_label === nextBody.role_label &&
            (prev.role_category ?? null) === (nextBody.role_category ?? null)
          ) {
            return;
          }
          save.mutate(next);
        }}
        disabled={save.isPending || !options}
        className={cn(
          "border-input focus-within:ring-ring/50 flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border bg-transparent px-2 py-1.5 text-sm focus-within:ring-2",
          className,
          guessing && "border-dashed",
        )}
        placeholder={roleCategory === "unknown" && !label ? "Set role…" : ""}
      />
    </div>
  );
}


/** Menu-item wording for the role, e.g. "Role: Data Scientist". `unknown` with
 *  no label reads as an invitation, matching RoleBadge. */
export function roleMenuLabel(
  roleCategory: string,
  label: string | null | undefined,
  options?: RoleCategory[],
) {
  if (roleCategory === "unknown" && !label) return "Role not set";
  return `Role: ${displayRoleTag(roleCategory, label, options)}`;
}

/**
 * The picker in a dialog, for surfaces that keep the role OFF the page and
 * behind a menu.
 *
 * A dialog rather than the picker nested straight into the dropdown: the
 * picker is itself a popup, and a combobox popup inside a menu popup fights
 * the menu for focus and dismissal. The dialog also gives the free-text
 * mapping strip ("Count 'X' as Y?") somewhere to appear — inside a menu it
 * would be clipped.
 *
 * The write still lands on blur-free instant PATCH, so there is nothing to
 * save here; the footer button only closes.
 */
export function RoleCategoryDialog({
  slug,
  roleCategory,
  roleLabel: label = null,
  open,
  onOpenChange,
}: {
  slug: string;
  roleCategory: string;
  roleLabel?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Target role</DialogTitle>
          <DialogDescription>
            What this resume is for. It labels generated files and tells the
            tracker which roles you already have a base resume for.
          </DialogDescription>
        </DialogHeader>
        <RoleCategoryPicker
          slug={slug}
          roleCategory={roleCategory}
          roleLabel={label}
          className="w-full"
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
