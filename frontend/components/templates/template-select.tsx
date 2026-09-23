"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LayoutGrid, Check } from "lucide-react";

import { apiFetch } from "@/lib/api";
import {
  FORMATTING_DEFAULTS,
  unloadedLayer,
  type FormattingBaseline,
  type ResumeFormatting,
} from "@/lib/formatting";
import type { TemplateSummary } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { TemplateGallery } from "@/components/templates/template-gallery";
import { cn } from "@/lib/utils";

export const DEFAULT_TEMPLATE = "__default__";

/**
 * The picker's `DEFAULT_TEMPLATE` sentinel maps to a null `template_id` on the
 * wire (the backend treats null as "use the server default template"), and back.
 */
export function templateIdToApi(templateId: string): string | null {
  return templateId === DEFAULT_TEMPLATE ? null : templateId;
}

export function templateIdFromApi(
  templateId: string | null | undefined,
): string {
  return templateId ?? DEFAULT_TEMPLATE;
}

/**
 * Resolve which template a `template_id` (or the `DEFAULT_TEMPLATE` sentinel)
 * actually renders with, mirroring the backend's `get_usable_template`: a
 * persisted id that no longer resolves, or resolves to a non-`"ready"` row
 * (deleted, or a draft mid-edit), falls back to the server default rather than
 * that row. {@link useTemplateBaseline} resolves the knob baseline and the
 * knob support through this one lookup, so both come from the same template.
 */
function resolveTemplate(
  list: TemplateSummary[],
  templateId: string,
): TemplateSummary | undefined {
  if (templateId === DEFAULT_TEMPLATE) {
    return list.find((t) => t.is_default);
  }
  return (
    list.find((t) => t.id === templateId && t.status === "ready") ??
    list.find((t) => t.is_default)
  );
}

/**
 * The one `["templates", "all"]` query: the picker's list, and the source of the
 * Formatting panel's template layer. One definition, so the two can never read
 * different keys (or a different endpoint under the same key).
 */
function useTemplatesQuery() {
  return useQuery({
    queryKey: ["templates", "all"],
    queryFn: () => apiFetch<TemplateSummary[]>("/api/templates?include_archived=true"),
  });
}

/**
 * The Formatting panel's template layer: the schema defaults under the selected
 * template's `default_formatting` overlay, plus the `fmt.*` keys it consumes
 * (its list row already carries `supported_fmt_keys`). `DEFAULT_TEMPLATE`
 * resolves to the server's default template.
 *
 * Until the templates list is in, this is `"loading"`, or `"error"` with a retry
 * once the fetch has failed, never a baseline: the overlay is unknown, and a
 * knob diffed against the bare schema defaults drops any explicit override equal
 * to them. The application studio lays the base resume on top
 * (`overlayBaseline`).
 */
export function useTemplateBaseline(templateId: string): FormattingBaseline {
  const q = useTemplatesQuery();
  if (q.data === undefined) return unloadedLayer(q, "the template defaults");
  const match = resolveTemplate(q.data, templateId);
  return {
    status: "ready",
    values: {
      ...FORMATTING_DEFAULTS,
      ...((match?.default_formatting as Partial<ResumeFormatting> | null) ?? {}),
    },
    supportedKeys: match?.supported_fmt_keys ?? [],
  };
}

/**
 * The template picker: ONE control that both names the current template and
 * opens the gallery to change it.
 *
 * It used to be a `<Select>` dropdown AND a "Browse" button side by side, which
 * is two controls doing one job — and the pair was ~270px wide, enough to push
 * the studio toolbars past the edge of their pane (the base editor's row
 * disappeared under the preview; the application studio's preview header forced
 * a horizontal scrollbar across the whole page).
 *
 * The gallery won over the dropdown because a template is a LOOK: the grid
 * shows the rendered page-1 preview of each one, and a text list of names
 * ("Carlito Dense", "harshibar") tells you nothing about what you are choosing.
 * The trigger still carries the current selection, so nothing is hidden behind
 * the dialog.
 */
export function TemplateSelect({
  value,
  onChange,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  className?: string;
}) {
  const q = useTemplatesQuery();
  const all = q.data ?? [];
  // Two different lists on purpose. The BROWSE grid offers only what you would
  // want to pick — ready and not archived, which is the whole point of
  // archiving. The LABEL resolves against everything, because a template can be
  // archived while a resume still points at it; looking that up in the filtered
  // list would render the raw id where a name belongs.
  const ready = all.filter((t) => t.status === "ready");
  const selectable = ready.filter((t) => !t.archived_at);
  const [browseOpen, setBrowseOpen] = useState(false);
  const defaultTemplate = selectable.find((t) => t.is_default);

  const current = ready.find((t) => t.id === value);
  const label =
    value === DEFAULT_TEMPLATE ? "Default" : (current?.display_name ?? value);

  return (
    <>
      {/* The visible "Template:" prefix is load-bearing: a template's display
          name is a look's name ("XCharter Serif"), which without the category
          word reads as a font picker — the accessible name said "Template"
          while the visible label never did. */}
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-label={`Template: ${label}. Choose a different one`}
        onClick={() => setBrowseOpen(true)}
        className={cn("max-w-64 justify-start font-normal", className)}
      >
        <LayoutGrid className="size-3.5 shrink-0 opacity-70" />
        <span className="text-muted-foreground shrink-0">Template:</span>
        <span className="truncate">{label}</span>
      </Button>
      <Dialog open={browseOpen} onOpenChange={setBrowseOpen}>
        {/* Fixed header + dedicated scroll body, matching the pattern used by
            other overflow-prone dialogs (e.g. chat/scope-picker.tsx): a
            multi-row card grid must scroll inside the dialog, never push it
            past the viewport. Wider than those dialogs since this holds a
            2-3 column card grid rather than a list. */}
        <DialogContent className="flex max-h-[80vh] w-[min(92vw,64rem)] max-w-[min(92vw,64rem)] flex-col overflow-hidden">
          <DialogHeader>
            <DialogTitle>Choose a template</DialogTitle>
            <DialogDescription>Previews show a sample resume, not yours.</DialogDescription>
          </DialogHeader>
          {/* "Use the default template" is a real choice with no card of its
              own — it means "whatever the server default is", so it must not
              be pinned to one template's id. It lived in the dropdown that
              this dialog replaced, so it moves here rather than disappearing.
              Named, so you can see which template that currently resolves to. */}
          <button
            type="button"
            onClick={() => {
              onChange(DEFAULT_TEMPLATE);
              setBrowseOpen(false);
            }}
            aria-pressed={value === DEFAULT_TEMPLATE}
            className={cn(
              "flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left transition-colors",
              value === DEFAULT_TEMPLATE
                ? "border-primary bg-primary/5"
                : "hover:bg-muted/50",
            )}
          >
            <span className="flex items-center gap-2 text-sm font-medium">
              {value === DEFAULT_TEMPLATE && <Check className="text-primary size-4 shrink-0" aria-hidden="true" />}
              Use the default template
            </span>
            <span className="text-muted-foreground text-xs">
              {defaultTemplate?.display_name ?? "server default"}
            </span>
          </button>
          <div className="min-h-0 flex-1 overflow-y-auto p-1">
            {selectable.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                {ready.length === 0
                  ? "No templates ready yet."
                  : "Every ready template is archived. Restore one from Templates to pick it here."}
              </p>
            ) : (
              <TemplateGallery
                templates={selectable}
                selectedId={value}
                onSelect={(t) => {
                  onChange(t.id);
                  setBrowseOpen(false);
                }}
              />
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
