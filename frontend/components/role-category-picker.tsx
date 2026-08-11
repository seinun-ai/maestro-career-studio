"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  favoredRoleFromTag,
  identityFromFavoredRole,
  RolePicker,
} from "@/components/role-picker";
import { Badge } from "@/components/ui/badge";
import { apiFetch } from "@/lib/api";
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
  className,
}: {
  slug: string;
  roleCategory: string;
  roleLabel?: string | null;
  className?: string;
}) {
  const qc = useQueryClient();
  const { data: options } = useRoleCategories();

  const save = useMutation({
    mutationFn: (entry: FavoredRole | null) =>
      apiFetch<BaseResumeDetail>(`/api/base-resumes/${slug}/identity`, {
        method: "PATCH",
        body: JSON.stringify(identityFromFavoredRole(entry)),
      }),
    onSuccess: (updated) => {
      qc.setQueryData(["base-resumes", slug], updated);
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      toast.success(
        `Role set to ${displayRoleTag(updated.role_category, updated.role_label, options)}`,
      );
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const value = favoredRoleFromTag(roleCategory, label, options);

  return (
    <RolePicker
      mode="single"
      value={value}
      onValueChange={(next) => {
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
      className={
        className ??
        "border-input focus-within:ring-ring/50 flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border bg-transparent px-2 py-1.5 text-sm focus-within:ring-2"
      }
      placeholder={roleCategory === "unknown" && !label ? "Set role…" : ""}
    />
  );
}
