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

function jumpTo(anchor: string) {
  const lane = document.getElementById(anchor);
  lane?.scrollIntoView({ block: "start", behavior: "smooth" });
  lane?.focus({ preventScroll: true });
}

/** Four counts over the lanes. Empty counts and lanes absent from this view do not jump. */
export function ArrivalsStrip({ since }: { since: string | null }) {
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
            onClick={() => jumpTo(tile.anchor)}
            className="min-w-0 rounded-corner-md text-left disabled:cursor-default enabled:hover:[&>div]:bg-surface-container-high"
          >
            <StatTile label={tile.label} value={count == null ? "–" : String(count)} className="h-full min-w-0 wrap-anywhere" />
          </button>
        );
      })}
    </div>
  );
}
