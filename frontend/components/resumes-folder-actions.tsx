"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { GuardedLink } from "@/components/guarded-link";
import { IconButton } from "@/components/icon-button";
import { Button } from "@/components/ui/button";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt } from "@/lib/error-text";
import { copiesOn, RESUMES_FOLDER_KEY, RESUMES_FOLDER_URL, revealLabel } from "@/lib/resumes-folder";
import { anchorHref } from "@/lib/settings-tabs";
import type { ResumesFolderSettings } from "@/lib/types";
import { cn } from "@/lib/utils";

/** The resumes-folder setting, shared by every surface that offers the copy (one query key, one cache). */
export function useResumesFolder() {
  return useQuery({
    queryKey: RESUMES_FOLDER_KEY,
    queryFn: () => apiFetch<ResumesFolderSettings>(RESUMES_FOLDER_URL),
    staleTime: 60_000,
  });
}

type ShowCopyButtonProps = {
  applicationId: string;
  variant?: "outline" | "ghost" | "link";
  size?: "default" | "sm" | "icon-sm";
  /** An icon button: the label moves to `aria-label` and the tooltip, and only the folder glyph shows. */
  iconOnly?: boolean;
  disabled?: boolean;
  className?: string;
};

/** Reveals this application's saved PDF copy in the OS file manager. Nothing when copies are off. */
export function ShowCopyButton({
  applicationId,
  variant = "outline",
  size = "default",
  iconOnly = false,
  disabled = false,
  className,
}: ShowCopyButtonProps) {
  const { data } = useResumesFolder();
  const qc = useQueryClient();
  const reveal = useMutation({
    mutationFn: () => apiFetch<{ path: string }>(`/api/applications/${applicationId}/show-copy`, { method: "POST" }),
    onError: (error: Error) => toast.error(couldnt("open the folder", error)),
    // Showing the copy heals a missed one, or fails and records why: either way the saved error moved.
    onSettled: () => qc.invalidateQueries({ queryKey: RESUMES_FOLDER_KEY }),
  });
  // A double click opened two file-manager windows.
  const revealOnce = useSingleFlight(reveal.mutate);
  if (!copiesOn(data)) return null;
  const label = revealLabel(data!.platform);
  if (iconOnly) {
    return (
      <IconButton
        label={label}
        icon={<CONCEPT_ICONS.resumesFolder className="size-4" aria-hidden="true" />}
        variant={variant}
        size="icon-sm"
        className={className}
        pending={reveal.isPending}
        disabled={disabled}
        onClick={() => revealOnce(undefined)}
      />
    );
  }
  return (
    <Button
      variant={variant}
      size={size}
      className={className}
      pending={reveal.isPending}
      disabled={disabled}
      onClick={() => revealOnce(undefined)}
    >
      <CONCEPT_ICONS.resumesFolder className="size-4" aria-hidden="true" />
      {label}
    </Button>
  );
}

/** One small line for the PDF card's header: where the copy went, and Change folder. Nothing when copies are off,
 *  when the last copy failed (Settings shows the error) or when `copyMissed`: the render just answered with no
 *  copy, so the line stays quiet while the saved error is still on its way. Always shown otherwise: it is the
 *  card's metadata, not a notice to dismiss. */
export function ResumesFolderNote({ copyMissed = false, className }: { copyMissed?: boolean; className?: string }) {
  const { data } = useResumesFolder();
  if (!data || !copiesOn(data) || data.last_error || copyMissed || !data.folder_display) return null;
  return (
    <span className={cn("text-muted-foreground inline-flex min-w-0 items-center gap-1 text-body-small", className)}>
      <span className="truncate" title={data.folder_display}>In {data.folder_display}</span>
      <span aria-hidden="true">·</span>
      <GuardedLink
        href={anchorHref("/settings", "resumes-folder")}
        className="text-primary shrink-0 underline-offset-4 hover:underline"
      >
        Change folder
      </GuardedLink>
    </span>
  );
}
