"use client";

import { useId, type ReactNode } from "react";
import { Check, Star } from "lucide-react";

import {
  GalleryCard,
  GalleryCardActions,
  GalleryGrid,
} from "@/components/gallery/gallery-card";
import { Badge } from "@/components/ui/badge";
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FORMATTING_DEFAULTS } from "@/lib/formatting";
import { templateHasErrors } from "@/lib/template-status";
import type { TemplateSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

import { RequiresTexBadge } from "./requires-tex-badge";
import { TemplateThumbnail } from "./template-thumbnail";

/** "Supports 9 of 13 formatting options", for the hover summary rather than
 * the card face.
 *
 * supported_fmt_keys is raw scanner output over the source — filter to keys the
 * frontend actually recognizes so a typo'd `fmt.*` (e.g. `font_sizes`) can't
 * inflate the numerator past the denominator. */
function formattingCoverage(template: TemplateSummary): string {
  const supported = (template.supported_fmt_keys ?? []).filter(
    (k) => k in FORMATTING_DEFAULTS,
  ).length;
  return `Supports ${supported} of ${Object.keys(FORMATTING_DEFAULTS).length} formatting options`;
}

/** A chosen picker card's edge: an overlay INSIDE the card, above the preview
 *  image and the default star (z-20), so it never touches the focus ring's
 *  outside band. The card is `isolate`, so z-30 stays inside it. */
const SELECTED_CARD_EDGE =
  "after:pointer-events-none after:absolute after:inset-0 after:z-30 after:rounded-xl after:border-2 after:border-primary";

/** A template's own name; its id never stands in for one. */
export function templateName(template: Pick<TemplateSummary, "display_name">): string {
  return template.display_name ?? "Untitled template";
}

export const ENGINE_LABEL: Record<TemplateSummary["engine"], string> = {
  latex: "LaTeX",
  typst: "Typst",
};
export const STATUS_LABEL: Record<TemplateSummary["status"], string> = {
  ready: "Ready",
  draft: "Draft",
};

/**
 * Status only, and only when authoring. The picker is choosing a look, so the
 * chip is noise there; the "can't render here" fact stays the Needs setup
 * badge. The engine (LaTeX, Typst) is named in the template editor only.
 */
function TemplateBadgeStrip({
  template,
  picking,
  id,
}: {
  template: TemplateSummary;
  picking?: boolean;
  /** The picker button's description: its name is only the template's. */
  id?: string;
}) {
  const isReady = template.status === "ready";

  return (
    <div id={id} className="flex min-w-0 flex-wrap items-center gap-1">
      {template.archived_at && <Badge variant="secondary">Archived</Badge>}
      {/* Choosing a look, the status is noise; authoring, it is the template's state. */}
      {!picking && <Badge variant={isReady ? "default" : "secondary"}>{STATUS_LABEL[template.status]}</Badge>}
      {!template.engine_available && <RequiresTexBadge />}
      {isReady && template.parse_certified === false && (
        // The words say it on the card, not only in a hover: ATS is spelled
        // out once here, where it first appears.
        <p className="basis-full text-xs text-amber-700 dark:text-amber-400">
          <span aria-hidden="true">⚠</span> Applicant tracking systems (ATS)
          may read some words as joined together. Pick another template to be
          safe.
        </p>
      )}
    </div>
  );
}

function TemplateCardBody({
  template,
  actions,
  picking,
  selected,
  describedBy,
}: {
  template: TemplateSummary;
  actions?: ReactNode;
  picking?: boolean;
  selected?: boolean;
  /** Id prefix for the default mark and the badge strip, which the picker
   *  button names in `aria-describedby`. */
  describedBy?: string;
}) {
  const isReady = template.status === "ready";
  return (
    <>
      {/* Default is a corner mark, not a status pill — keeps the badge strip
          from competing for horizontal space. It sits top-LEFT because the
          top-right corner now belongs to the actions menu. Its words are
          real (sr-only) text, so a description that points here reads them. */}
      {template.is_default && (
        <span
          id={describedBy && `${describedBy}-default`}
          className="text-primary bg-background/85 absolute top-2.5 left-2.5 z-20 rounded-full p-1 backdrop-blur"
          title="Default template"
        >
          <Star className="size-3.5 fill-current" aria-hidden="true" />
          <span className="sr-only">Default template</span>
        </span>
      )}
      <TemplateThumbnail template={template} />
      <CardHeader>
        <div className="flex min-w-0 flex-col gap-2">
          {/* The id is deliberately NOT a visible line here. It was rendering
              as its own grid row under the badges, which cost a band of
              vertical space on every card — and for any template created
              without a display name it printed the SAME string twice, once as
              the title and once below it. The thumbnail plus the name is what
              you choose by, and the Edit link is /templates/<id> whenever you
              actually need to copy it. */}
          <CardTitle
            className="flex min-w-0 items-center gap-1.5 text-base"
            title={[templateName(template), formattingCoverage(template)].join("\n")}
          >
            {selected && <Check className="text-primary size-4 shrink-0" aria-hidden="true" />}
            <span className="truncate">{templateName(template)}</span>
          </CardTitle>
          {/* Actions share the badges' row so they cost no extra height, and
              being the last row puts them at the card's bottom-right. */}
          <div className="flex items-end gap-2">
            <TemplateBadgeStrip
              template={template}
              picking={picking}
              id={describedBy && `${describedBy}-badges`}
            />
            {actions && <GalleryCardActions>{actions}</GalleryCardActions>}
          </div>
        </div>
      </CardHeader>
      {/* Rendered ONLY when there is an error. An always-present CardContent
          left an empty padded block under every healthy card — the band of
          dead space at the bottom of the grid. */}
      {/* The compiler's words stay in the editor (its preview pane). A LaTeX
          template on a computer without TeX has nothing to fix: the Needs
          setup badge says so, alone. */}
      {!isReady && templateHasErrors(template) && (
        <CardContent className="pt-0 text-xs">
          <p className="text-muted-foreground truncate">Has errors. Open to fix.</p>
        </CardContent>
      )}
    </>
  );
}

export function TemplateGallery({
  templates,
  selectedId,
  onSelect,
  href,
  renderActions,
}: {
  templates: TemplateSummary[];
  selectedId?: string;
  onSelect?: (t: TemplateSummary) => void;
  /** Manage mode: the whole card opens this. Replaces an Edit button. */
  href?: (t: TemplateSummary) => string;
  /** Manage mode: the corner menu. Rendered ABOVE the stretched link. */
  renderActions?: (t: TemplateSummary) => ReactNode;
}) {
  const idPrefix = useId();
  return (
    <GalleryGrid>
      {templates.map((t) => {
        // href/renderActions (manage) and onSelect (pick) are mutually
        // exclusive — a card that both navigates and selects has no single
        // meaning for a click. If both are passed, manage mode wins.
        if (href || renderActions) {
          return (
            <GalleryCard
              key={t.id}
              href={href?.(t)}
              ariaLabel={`Open ${templateName(t)}`}
              className="group/tpl"
            >
              <TemplateCardBody template={t} actions={renderActions?.(t)} />
            </GalleryCard>
          );
        }

        if (onSelect) {
          const selected = selectedId === t.id;
          const describedBy = `${idPrefix}-${t.id}`;
          return (
            // The button only supplies interaction affordances (focus ring,
            // text alignment). GalleryCard owns every visual — including the
            // has-data-*/data-[size=sm]/[img:first-child] rules that a hand
            // copied class list would silently drop — so this stays the one
            // definition of what a card looks like, in both modes, forever.
            // No href: the button owns the interaction, so there is no
            // stretched link to compete with it.
            <button
              key={t.id}
              type="button"
              aria-pressed={selected}
              // The name is the template's; the default mark and the warning
              // badges (requires TeX, ATS spacing) are its description.
              aria-label={templateName(t)}
              aria-describedby={
                t.is_default ? `${describedBy}-default ${describedBy}-badges` : `${describedBy}-badges`
              }
              onClick={() => onSelect(t)}
              // Focus is only ever the ring OUTSIDE the card, 2px off it.
              // Selection lives INSIDE the card: a 2px primary edge drawn over
              // the preview, plus a Check before the name. `--card` equals
              // `--popover`, so an outside selection ring and the offset focus
              // ring used to merge into one 4px blue band.
              className="rounded-xl text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-popover focus-visible:outline-none"
            >
              <GalleryCard
                className={cn(
                  "isolate h-full transition-shadow hover:ring-foreground/20",
                  selected && SELECTED_CARD_EDGE,
                )}
              >
                <TemplateCardBody
                  template={t}
                  picking
                  selected={selected}
                  describedBy={describedBy}
                />
              </GalleryCard>
            </button>
          );
        }

        return (
          <GalleryCard key={t.id}>
            <TemplateCardBody template={t} />
          </GalleryCard>
        );
      })}
    </GalleryGrid>
  );
}
