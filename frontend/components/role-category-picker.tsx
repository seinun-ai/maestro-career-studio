"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import type { BaseResumeDetail, RoleCategory } from "@/lib/types";

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

/** Read-only role badge. `unknown` is styled as an invitation, not an error —
 *  it is a legitimate state, and the design's promise is that it is always
 *  visible and always one click from being fixed. */
export function RoleBadge({ role }: { role: string }) {
  const { data: options } = useRoleCategories();
  const undeclared = role === "unknown";
  return (
    <Badge variant={undeclared ? "outline" : "secondary"} className="font-normal">
      {undeclared ? "Role not set" : roleLabel(role, options)}
    </Badge>
  );
}

/** Inline picker. Writes through PATCH /identity, which is metadata-only —
 *  it does not re-render the PDF or record a resume version. */
export function RoleCategoryPicker({
  slug,
  role,
  className,
}: {
  slug: string;
  role: string;
  className?: string;
}) {
  const qc = useQueryClient();
  const { data: options } = useRoleCategories();

  const save = useMutation({
    mutationFn: (next: string) =>
      apiFetch<BaseResumeDetail>(`/api/base-resumes/${slug}/identity`, {
        method: "PATCH",
        body: JSON.stringify({ role_category: next }),
      }),
    onSuccess: (updated) => {
      qc.setQueryData(["base-resumes", slug], updated);
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      toast.success(`Role set to ${roleLabel(updated.role_category, options)}`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const selected = options?.find((o) => o.key === role);

  return (
    <Select
      value={role}
      onValueChange={(next) => next && next !== role && save.mutate(next)}
      disabled={save.isPending || !options}
    >
      <SelectTrigger className={className} aria-label="Target role">
        <SelectValue>
          {role === "unknown" ? "Set role…" : (selected?.label ?? roleLabel(role, options))}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {options?.map((option) => (
          <SelectItem key={option.key} value={option.key}>
            <span>{option.label}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
