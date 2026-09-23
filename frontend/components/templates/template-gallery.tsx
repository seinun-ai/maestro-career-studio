"use client";

import type { ReactNode } from "react";
import { Check, Star } from "lucide-react";

import {
  GalleryCard,
  GalleryCardActions,
  GalleryGrid,
} from "@/components/gallery/gallery-card";
import { Badge } from "@/components/ui/badge";
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FORMATTING_DEFAULTS } from "@/lib/formatting";
import type { TemplateSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

import { RequiresTexBadge } from "./requires-tex-badge";
import { TemplateThumbnail } from "./template-thumbnail";

/** `Knobs n/13`, for the hover summary rather than the card face.
 *
 * supported_fmt_keys is raw scanner output over the source — filter to keys the
 * frontend actually recognizes so a typo'd `fmt.*` (e.g. `font_sizes`) can't
 * inflate the numerator past the denominator. */
export function knobCoverage(template: TemplateSummary): string {
  const supported = (template.supported_fmt_keys ?? []).filter(
    (k) => k in FORMATTING_DEFAULTS,
  ).length;
  return `${supported}/${Object.keys(FORMATTING_DEFAULTS).length}`;
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
 * Status and engine only, and only when authoring. The picker is choosing a
 * look, so both chips are noise there; the "can't render here" fact stays
 * the Requires TeX badge.
 */
function TemplateBadgeStrip({
  template,
  picking,
}: {
  template: TemplateSummary;
  picking?: boolean;
}) {
  const isReady = template.status === "ready";

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1">
      {template.archived_at && <Badge variant="secondary">Archived</Badge>}
      {/* Choosing a look, the engine and status are noise; authoring, they are the source language and state. */}
      {!picking && <Badge variant={isReady ? "default" : "secondary"}>{STATUS_LABEL[template.status]}</Badge>}
      {!picking && <Badge variant="outline">{ENGINE_LABEL[template.engine]}</Badge>}
      {!template.engine_available && <RequiresTexBadge />}
      {isReady && template.parse_certified === false && (
        <Badge
          variant="outline"
          className="border-amber-500/40 text-amber-700 dark:text-amber-400"
          title="A strict PDF text extractor joins words in this template's output, so some ATS may misread it. Prefer a certified template."
        >
          ⚠ ATS spacing
        </Badge>
      )}
    </div>
  );
}

function TemplateCardBody({
  template,
  actions,
  picking,
  selected,
}: {
  template: TemplateSummary;
  actions?: ReactNode;
  picking?: boolean;
  selected?: boolean;
}) {
  const isReady = template.status === "ready";
  return (
    <>
      {/* Default is a corner mark, not a status pill — keeps the badge strip
          from competing for horizontal space. It sits top-LEFT because the
          top-right corner now belongs to the actions menu. */}
      {template.is_default && (
        <span
          className="text-primary bg-background/85 absolute top-2.5 left-2.5 z-20 rounded-full p-1 backdrop-blur"
          title="Default template"
          aria-label="Default template"
        >
          <Star className="size-3.5 fill-current" aria-hidden="true" />
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
              you choose by; the id stays one hover away, and the Edit link is
              /templates/<id> whenever you actually need to copy it. */}
          <CardTitle
            className="flex min-w-0 items-center gap-1.5 text-base"
            title={[
              template.display_name && template.display_name !== template.id
                ? `${template.display_name} · ${template.id}`
                : template.id,
              `Knobs ${knobCoverage(template)}`,
            ].join("\n")}
          >
            {selected && <Check className="text-primary size-4 shrink-0" aria-hidden="true" />}
            <span className="truncate">{template.display_name ?? template.id}</span>
          </CardTitle>
          {/* Actions share the badges' row so they cost no extra height, and
              being the last row puts them at the card's bottom-right. */}
          <div className="flex items-end gap-2">
            <TemplateBadgeStrip template={template} picking={picking} />
            {actions && <GalleryCardActions>{actions}</GalleryCardActions>}
          </div>
        </div>
      </CardHeader>
      {/* Rendered ONLY when there is an error. An always-present CardContent
          left an empty padded block under every healthy card — the band of
          dead space at the bottom of the grid. */}
      {!isReady && template.last_error && (
        <CardContent className="pt-0 text-xs">
          <p
            className="text-muted-foreground truncate"
            title={template.last_error}
          >
            {template.last_error}
          </p>
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
              ariaLabel={`Open ${t.display_name ?? t.id}`}
              className="group/tpl"
            >
              <TemplateCardBody template={t} actions={renderActions?.(t)} />
            </GalleryCard>
          );
        }

        if (onSelect) {
          const selected = selectedId === t.id;
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
              aria-label={t.display_name ?? t.id}
              onClick={() => onSelect(t)}
              // Focus is a ring OUTSIDE the card, 2px off it; selection is the card's own
              // primary edge plus a Check. Both used to be one 2px blue ring on one edge.
              className="rounded-xl text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-popover focus-visible:outline-none"
            >
              <GalleryCard
                className={cn(
                  "h-full transition-shadow hover:ring-foreground/20",
                  selected && "ring-2 ring-primary",
                )}
              >
                <TemplateCardBody template={t} picking selected={selected} />
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
