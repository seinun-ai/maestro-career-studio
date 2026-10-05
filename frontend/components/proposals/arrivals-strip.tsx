"use client";

import { useQuery } from "@tanstack/react-query";

import { StatTile } from "@/components/analytics/stat-tile";
import { apiFetch } from "@/lib/api";
import type { ProposalSummary } from "@/lib/types";

const TILES = [
  { key: "new", label: "New since your last visit", anchor: "inbox-to-review" },
  { key: "ready", label: "Ready to apply", anchor: "inbox-queued" },
  { key: "needs_you", label: "Needs you", anchor: "inbox-needs-you" },
  { key: "applied_this_week", label: "Applied this week", anchor: "inbox-history" },
] as const;

function jumpTo(anchor: string, onJump?: (anchor: string) => void) {
  onJump?.(anchor);
  const lane = document.getElementById(anchor);
  lane?.scrollIntoView({ block: "start", behavior: "smooth" });
  lane?.focus({ preventScroll: true });
}

/** Four counts over the lanes. Empty counts and lanes absent from this view do not jump. */
export function ArrivalsStrip({ since, onJump }: { since: string | null; onJump?: (anchor: string) => void }) {
  const { data } = useQuery({
    queryKey: ["proposals", "summary", since],
    queryFn: () => apiFetch<ProposalSummary>(`/api/proposals/summary?since=${encodeURIComponent(since ?? "")}`),
    enabled: since != null,
  });
  return (
    <div className="grid min-w-0 grid-cols-4 gap-3" aria-label="Agent inbox summary" role="group">
      {TILES.map((tile) => {
        const count = data?.[tile.key];
        return (
          <button
            key={tile.key}
            type="button"
            disabled={!count}
            onClick={() => jumpTo(tile.anchor, onJump)}
            className="min-w-0 rounded-corner-md border border-transparent text-left outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-default disabled:opacity-50 disabled:[&_p]:text-muted-foreground enabled:hover:[&>div]:bg-surface-container-high"
          >
            <StatTile label={tile.label} value={count == null ? "–" : String(count)} className="h-full min-w-0 wrap-anywhere" />
          </button>
        );
      })}
    </div>
  );
}
