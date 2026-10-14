"use client";

import { useQuery } from "@tanstack/react-query";
import { Fragment } from "react";

import { apiFetch } from "@/lib/api";
import { summaryParts } from "@/lib/inbox-summary";
import type { ProposalSummary } from "@/lib/types";

function jumpTo(anchor: string, onJump?: (anchor: string) => void) {
  onJump?.(anchor);
  // A lane with nothing in it is not drawn: "new" then goes to the first lane there is.
  const lane = document.getElementById(anchor) ?? document.querySelector<HTMLElement>('section[id^="inbox-"]');
  lane?.scrollIntoView({ block: "start", behavior: "smooth" });
  lane?.focus({ preventScroll: true });
}

/**
 * One line over the lanes: "2 need you · 3 queued · 5 applied this week" (and "4 new" first when something
 * arrived since your last visit). Each part jumps to its lane; a zero part is left out, and none is
 * "Nothing waiting". While the counts load it shows nothing, which claims nothing.
 */
export function ArrivalsStrip({ since, onJump }: { since: string | null; onJump?: (anchor: string) => void }) {
  const { data } = useQuery({
    queryKey: ["proposals", "summary", since],
    queryFn: () => apiFetch<ProposalSummary>(`/api/proposals/summary?since=${encodeURIComponent(since ?? "")}`),
    enabled: since != null,
  });
  if (!data) return null;
  const parts = summaryParts(data);
  if (parts.length === 0) {
    return <p className="text-muted-foreground text-body-medium">Nothing waiting</p>;
  }
  return (
    <p aria-label="Agent inbox summary" className="flex min-w-0 flex-wrap items-baseline gap-x-2 text-body-medium">
      {parts.map((part, i) => (
        <Fragment key={part.key}>
          {i > 0 ? <span aria-hidden="true" className="text-muted-foreground">·</span> : null}
          <button
            type="button"
            onClick={() => jumpTo(part.anchor, onJump)}
            className="rounded-corner-sm underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring"
          >
            {part.text}
          </button>
        </Fragment>
      ))}
    </p>
  );
}
