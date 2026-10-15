"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { GuardedLink as Link } from "@/components/guarded-link";
import { apiFetch } from "@/lib/api";
import { AGENT_RUNS_LATEST_KEY, RECENT_RUNS_HREF, proposedLine, recentRefusals } from "@/lib/agent-runs";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { formatTimeAgo } from "@/lib/format-date";
import type { AgentRunList, RefusedJobRequest } from "@/lib/types";

function RefusedLine({ request }: { request: RefusedJobRequest }) {
  const job = [request.job_title ?? "Untitled role", request.job_company].filter(Boolean).join(", ");
  return (
    <div className="rounded-corner-md bg-surface-container-low p-3 text-body-small">
      <p className="flex items-center gap-1.5 text-title-small">
        <CONCEPT_ICONS.cannot className="text-muted-foreground size-3.5 shrink-0" aria-hidden="true" />
        Request refused
        {request.answered_at ? <span className="text-muted-foreground text-body-small"> · {formatTimeAgo(request.answered_at)}</span> : null}
      </p>
      {request.job_id ? <p className="mt-1 max-w-[65ch] wrap-anywhere">{job}</p> : null}
      <p className="mt-1 max-w-[65ch]">{request.reason}</p>
      {request.job_id ? <Link href={`/jobs/${request.job_id}`} className="text-primary underline underline-offset-4">Open job</Link> : null}
    </div>
  );
}

function useLatestRuns() {
  return useQuery({
    queryKey: AGENT_RUNS_LATEST_KEY,
    queryFn: () => apiFetch<AgentRunList>("/api/agent-runs/latest"),
  });
}

/**
 * What the inbox says about runs, above the lanes: one line when the newest run proposed jobs ("Job hunt
 * proposed 4 jobs 2 hours ago · See runs"). All the runs live on the Automations page. Nothing to say,
 * nothing shown; a failed read says nothing too.
 */
export function InboxRunNotice() {
  const { data } = useLatestRuns();
  const line = data ? proposedLine(data.items, formatTimeAgo) : null;
  if (!line) return null;
  return (
    <p className="text-muted-foreground text-body-medium wrap-anywhere">
      {line} ·{" "}
      <Link href={RECENT_RUNS_HREF} className="text-primary underline underline-offset-4">See runs</Link>
    </p>
  );
}

/**
 * The requests the other copy refused, below the lanes: they answer something you asked for, so they stay
 * in the inbox, but only the recent ones (since your last visit, never older than a week).
 */
export function RefusedRequests({ since }: { since: string | null }) {
  const { data } = useLatestRuns();
  // The week's edge is read once, when the page opens.
  const [now] = useState(() => Date.now());
  const refused = recentRefusals(data?.refused_requests ?? [], since, now);
  if (refused.length === 0) return null;
  return (
    <div className="flex min-w-0 flex-col gap-2">
      {refused.map((request) => <RefusedLine key={request.id} request={request} />)}
    </div>
  );
}
