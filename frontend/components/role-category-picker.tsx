"use client";

import { useCallback, useId, useRef, useState, type ReactNode, type RefObject } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { CountryPicker } from "@/components/country-picker";
import {
  favoredRoleFromTag,
  identityFromFavoredRole,
  MAX_ROLE_LABEL_CHARS,
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { humanizeSlug } from "@/lib/humanize-slug";
import { cn } from "@/lib/utils";
import type { BaseResumeDetail, FavoredRole, RoleCategory } from "@/lib/types";

/** The vocabulary, fetched once. Deliberately NOT duplicated client-side: it
 *  lives in backend/app/services/ats/data/role_categories.yaml, and a second
 *  copy here would recreate exactly the drift that file was written to end. */
export function useRoleCategories({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ["role-categories"],
    queryFn: () => apiFetch<RoleCategory[]>("/api/role-categories"),
    staleTime: 60 * 60 * 1000, // vocabulary changes only on deploy
    enabled,
  });
}

/** key -> display label from the fetched catalog. While it loads, after it
 *  fails, or for a key it no longer has, `humanizeSlug` stands in: the role's
 *  own name, acronyms cased as the catalog cases them, never blank. */
export function useRoleLabel() {
  const { data } = useRoleCategories();
  return useCallback(
    (key: string | null | undefined) => roleLabel(key, data),
    [data],
  );
}

export function roleLabel(key: string | null | undefined, options?: RoleCategory[]) {
  const hit = key ? options?.find((o) => o.key === key) : undefined;
  // A row written before a category was renamed still renders.
  return hit ? hit.label : humanizeSlug(key);
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
    <Badge variant={undeclared ? "outline" : "secondary"} className="text-body-small">
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
  id,
  "aria-label": ariaLabel = "Target role",
}: {
  slug: string;
  roleCategory: string;
  roleLabel?: string | null;
  /** True when the import pipeline guessed this role; the chip must look like a guess. */
  proposed?: boolean;
  className?: string;
  /** For a `<Label htmlFor>` beside it (the Target dialog). */
  id?: string;
  /** The picker's name. Most callers have no visible label beside it, so it needs one. */
  "aria-label"?: string;
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
    onError: (err: Error) => toast.error(couldnt("set the role", err)),
  });

  const value = favoredRoleFromTag(roleCategory, label, options);

  return (
    <div
      className="inline-flex max-w-full align-middle"
      title={guessing ? "Suggested. Confirm it or pick another." : undefined}
      onClick={() => {
        if (guessing) setConfirmed(true);
      }}
    >
      <RolePicker
        mode="single"
        id={id}
        aria-label={ariaLabel}
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
        readOnly={save.isPending}
        disabled={!options}
        className={cn(
          "border-input focus-within:ring-ring flex min-h-9 flex-wrap items-center gap-1.5 rounded-corner-sm border bg-transparent px-2 py-1.5 text-body-medium focus-within:ring-2",
          className,
          guessing && "border-dashed",
        )}
      />
    </div>
  );
}


/** The studio ⋯ item that opens the Target dialog, naming the role when one is set ("Target: Data
 *  Scientist"). With none it reads "Target", the dialog's name. */
export function targetMenuLabel(
  roleCategory: string,
  label: string | null | undefined,
  options?: RoleCategory[],
) {
  if (roleCategory === "unknown" && !label) return "Target";
  return `Target: ${displayRoleTag(roleCategory, label, options)}`;
}

/** The PATCH /identity keys the Target dialog writes besides the role, with their value shapes. */
type AnchorValues = { countries: string[]; company: string; focus: string };

const FIELD_WORDS: Record<keyof AnchorValues, string> = {
  countries: "countries",
  company: "company",
  focus: "focus",
};

/**
 * One Target field's write. PATCH /identity is metadata-only (no PDF, no version), and a key it is
 * not sent stays as it is, so each field sends its own key alone: two fields saved back to back
 * never overwrite each other with a stale copy.
 */
function useAnchorSave<K extends keyof AnchorValues>(slug: string, field: K) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (value: AnchorValues[K]) =>
      apiFetch<BaseResumeDetail>(`/api/base-resumes/${slug}/identity`, {
        method: "PATCH",
        body: JSON.stringify({ [field]: value }),
      }),
    onSuccess: (updated) => {
      qc.setQueryData(["base-resumes", slug], updated);
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      // Countries decide which resumes a job is scored against, and which inbox
      // rows carry the "Resume for another country" mark.
      if (field === "countries") {
        qc.invalidateQueries({ queryKey: ["ats-scores"] });
        qc.invalidateQueries({ queryKey: ["proposals"] });
      }
      const set = field === "countries" ? updated.countries.length > 0 : Boolean(updated[field]);
      const words = FIELD_WORDS[field];
      toast.success(`${words[0].toUpperCase()}${words.slice(1)} ${set ? "saved" : "cleared"}`);
    },
    onError: (err: Error) => toast.error(couldnt(`save the ${FIELD_WORDS[field]}`, err)),
  });
}

/** A Target field: its label, its hint between the label and the control (wired), then the control. */
function AnchorField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: (ids: { id: string; describedBy: string | undefined }) => ReactNode;
}) {
  const id = useId();
  const hintId = useId();
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {hint && (
        <p id={hintId} className="text-muted-foreground text-body-small">
          {hint}
        </p>
      )}
      {children({ id, describedBy: hint ? hintId : undefined })}
    </div>
  );
}

/** Company or focus: saved on blur when the trimmed text changed. A failed save keeps the text. */
function AnchorTextField({
  slug,
  field,
  label,
  hint,
  value,
}: {
  slug: string;
  field: "company" | "focus";
  label: string;
  hint?: string;
  value: string | null;
}) {
  const [draft, setDraft] = useState(value ?? "");
  const save = useAnchorSave(slug, field);
  const commit = () => {
    const next = draft.trim();
    if (next === (value ?? "")) return;
    save.mutate(next, { onSuccess: (updated) => setDraft(updated[field] ?? "") });
  };
  return (
    <AnchorField label={label} hint={hint}>
      {({ id, describedBy }) => (
        <Input
          id={id}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          // MAX_LABEL_CHARS bounds company and focus too, so the server's 422 is unreachable.
          maxLength={MAX_ROLE_LABEL_CHARS}
          aria-describedby={describedBy}
          // Focus stays while it saves; a disabled field would drop it to <body>.
          readOnly={save.isPending}
        />
      )}
    </AnchorField>
  );
}

/**
 * The Target dialog: the resume's countries, role, company and focus, behind the studio's ⋯ (the code
 * calls the four anchors). Countries decide which jobs the resume is scored for; the other three
 * steer tailoring and Ask for changes.
 *
 * A dialog rather than the pickers nested straight into the dropdown: a picker is itself a popup, and
 * a combobox popup inside a menu popup fights the menu for focus and dismissal. The dialog also gives
 * the free-text mapping strip ("Count 'X' as Y?") somewhere to appear.
 *
 * Every field saves itself (countries and role on change, company and focus on blur), so there is
 * nothing to save here; the footer button only closes.
 */
export function TargetDialog({
  slug,
  roleCategory,
  roleLabel: label = null,
  countries,
  company,
  focus,
  open,
  onOpenChange,
  finalFocus,
}: {
  slug: string;
  roleCategory: string;
  roleLabel?: string | null;
  countries: string[];
  company: string | null;
  focus: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /**
   * Where focus returns on close. Opened from a menu, pass the menu's trigger:
   * Base UI's default is the last element it saw focused, and the picker's own
   * input records itself when its popup opens, so Escape "returned" focus to an
   * input the dialog was removing.
   */
  finalFocus?: RefObject<HTMLElement | null>;
}) {
  const saveCountries = useAnchorSave(slug, "countries");
  const bodyRef = useRef<HTMLDivElement>(null);
  const handleOpenChange = (next: boolean) => {
    // Escape unmounts the fields with no blur, so a typed company or focus commits first.
    const active = document.activeElement;
    if (!next && active instanceof HTMLElement && bodyRef.current?.contains(active)) active.blur();
    onOpenChange(next);
  };
  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent finalFocus={finalFocus}>
        <DialogHeader>
          <DialogTitle>Target</DialogTitle>
          <DialogDescription>
            Used when tailoring or asking for changes. Saving here does not change the resume.
          </DialogDescription>
        </DialogHeader>
        <div ref={bodyRef} className="grid gap-4">
          <AnchorField
            label="Countries"
            hint="Only scored for jobs in these countries. Leave empty to use anywhere."
          >
            {({ id, describedBy }) => (
              <CountryPicker
                id={id}
                aria-label="Countries"
                aria-describedby={describedBy}
                // The picked set shows while it saves, not the one before it.
                value={(saveCountries.isPending && saveCountries.variables) || countries}
                onChange={(codes) => saveCountries.mutate(codes)}
                readOnly={saveCountries.isPending}
              />
            )}
          </AnchorField>
          <AnchorField label="Role">
            {({ id }) => (
              <RoleCategoryPicker
                id={id}
                aria-label="Role"
                slug={slug}
                roleCategory={roleCategory}
                roleLabel={label}
                className="w-full"
              />
            )}
          </AnchorField>
          <AnchorTextField slug={slug} field="company" label="Company" value={company} />
          <AnchorTextField
            slug={slug}
            field="focus"
            label="Focus"
            hint="Such as payments platforms."
            value={focus}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
