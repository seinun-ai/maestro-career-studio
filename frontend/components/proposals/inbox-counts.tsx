"use client";

import { useQuery } from "@tanstack/react-query";

import { NumberRoll } from "@/components/visual";
import { apiFetch } from "@/lib/api";
import { inboxCounts } from "@/lib/inbox-summary";
import type { ProposalSummary } from "@/lib/types";

function jumpTo(anchor: string, onJump?: (anchor: string) => void) {
  onJump?.(anchor);
  // A lane with nothing in it is not drawn: the count then goes to the first lane there is.
  const lane = document.getElementById(anchor) ?? document.querySelector<HTMLElement>('section[id^="inbox-"]');
  lane?.scrollIntoView({ block: "start", behavior: "smooth" });
  lane?.focus({ preventScroll: true });
}

/**
 * The Agent inbox header's three counts: "4 to review · 3 queued · 5 applied this week", from the summary the inbox
 * already reads (`GET /api/proposals/summary`). A count above zero is a button that jumps to its lane; a zero is
 * plain text. While the counts load, or when they fail, it shows nothing, which claims nothing. A number that
 * changes rolls to its new value (`NumberRoll`): a triage moves it.
 */
export function InboxCounts({ since, onJump }: { since: string | null; onJump?: (anchor: string) => void }) {
  const { data } = useQuery({
    queryKey: ["proposals", "summary", since],
    queryFn: () => apiFetch<ProposalSummary>(`/api/proposals/summary?since=${encodeURIComponent(since ?? "")}`),
    enabled: since != null,
  });
  if (!data) return null;
  return (
    <p aria-label="Agent inbox summary" className="flex min-w-0 flex-wrap items-baseline gap-x-5 gap-y-1 text-body-small text-muted-foreground">
      {inboxCounts(data).map((count) => {
        const words = (
          <>
            <NumberRoll value={count.value} className="text-title-medium text-foreground" /> {count.label}
          </>
        );
        return count.value > 0 ? (
          <button
            key={count.key}
            type="button"
            onClick={() => jumpTo(count.anchor, onJump)}
            className="cursor-pointer rounded-corner-sm underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring"
          >
            {words}
          </button>
        ) : (
          <span key={count.key}>{words}</span>
        );
      })}
    </p>
  );
}
