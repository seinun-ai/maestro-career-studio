"use client";

import { useQuery } from "@tanstack/react-query";

import { GuardedLink as Link } from "@/components/guarded-link";
import { apiFetch } from "@/lib/api";
import { AGENT_RUNS_LATEST_KEY, newJobsLine } from "@/lib/agent-runs";
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

/**
 * What the inbox says about runs: one line when the newest run found new jobs ("Job hunt found 12 new jobs 2
 * hours ago · See runs"), and the requests the other copy refused, which answer something you asked for. All
 * the runs live on the Automations page. Nothing to say, nothing shown; a failed read says nothing too.
 */
export function InboxRunNotice() {
  const { data } = useQuery({
    queryKey: AGENT_RUNS_LATEST_KEY,
    queryFn: () => apiFetch<AgentRunList>("/api/agent-runs/latest"),
  });
  const line = data ? newJobsLine(data.items, formatTimeAgo) : null;
  const refused = data?.refused_requests ?? [];
  if (!line && refused.length === 0) return null;
  return (
    <div className="flex min-w-0 flex-col gap-2">
      {line ? (
        <p className="text-muted-foreground text-body-medium wrap-anywhere">
          {line} ·{" "}
          <Link href="/automations" className="text-primary underline underline-offset-4">See runs</Link>
        </p>
      ) : null}
      {refused.map((request) => <RefusedLine key={request.id} request={request} />)}
    </div>
  );
}
