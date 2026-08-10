"use client";

import type { ReactNode } from "react";
import { Star } from "lucide-react";

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

/**
 * Status and engine only.
 *
 * The knob count moved off the face into the title tooltip: it is a property
 * you check when something is wrong, not one you scan a gallery by, and the
 * template editor (one click away now that the card links there) has a whole
 * Knobs tab. The ATS-spacing warning stays, because it is conditional, rare,
 * and reports an actual defect in the rendered output — burying that would be
 * hiding a problem rather than reducing noise.
 */
function TemplateBadgeStrip({ template }: { template: TemplateSummary }) {
  const isReady = template.status === "ready";

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1">
      <Badge variant={isReady ? "default" : "secondary"}>
        {template.status}
      </Badge>
      <Badge variant="outline" className="font-mono">
        {template.engine}
      </Badge>
      {isReady && template.parse_certified === false && (
        <Badge
          variant="outline"
          className="border-amber-500/40 text-amber-600 dark:text-amber-400"
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
}: {
  template: TemplateSummary;
  actions?: ReactNode;
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
            className="min-w-0 truncate text-base"
            title={[
              template.display_name && template.display_name !== template.id
                ? `${template.display_name} · ${template.id}`
                : template.id,
              `Knobs ${knobCoverage(template)}`,
            ].join("\n")}
          >
            {template.display_name ?? template.id}
          </CardTitle>
          {/* Actions share the badges' row so they cost no extra height, and
              being the last row puts them at the card's bottom-right. */}
          <div className="flex items-end gap-2">
            <TemplateBadgeStrip template={template} />
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
              onClick={() => onSelect(t)}
              className="rounded-xl text-left focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <GalleryCard
                className={cn(
                  "h-full transition-shadow hover:ring-foreground/20",
                  selected && "ring-2 ring-primary",
                )}
              >
                <TemplateCardBody template={t} />
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
