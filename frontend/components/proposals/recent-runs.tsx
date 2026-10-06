"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";

import { GuardedLink as Link } from "@/components/guarded-link";
import { apiFetch } from "@/lib/api";
import { agentDisplayName } from "@/lib/agent-name";
import { AGENT_RUNS_LATEST_KEY, countsLine, outcomeWord } from "@/lib/agent-runs";
import { formatTimeAgo } from "@/lib/format-date";
import type { AgentRun, AgentRunList, RefusedJobRequest } from "@/lib/types";

function RunLine({ run }: { run: AgentRun }) {
  const who = agentDisplayName(run.agent);
  return (
    <details className="group min-w-0 rounded-corner-md bg-card p-4 ring-1 ring-foreground/5">
      <summary className="flex min-w-0 cursor-pointer flex-wrap items-baseline gap-x-3 gap-y-1 wrap-anywhere">
        <ChevronDown className="size-3.5 shrink-0 transition-transform group-open:rotate-180" aria-hidden="true" />
        <span className="min-w-0 max-w-full text-title-small">{run.title}</span>
        <span className="min-w-0 max-w-full text-muted-foreground text-body-small">
          {formatTimeAgo(run.finished_at)}
          {who ? ` · ${who}` : ""}{run.on_bot ? " · on your bot" : ""} · {outcomeWord(run.outcome)}
        </span>
        <span className="min-w-0 max-w-full text-body-small">{countsLine(run.counts)}</span>
      </summary>
      {run.digest ? <p className="mt-2 max-w-[65ch] whitespace-pre-wrap text-body-medium wrap-anywhere">{run.digest}</p> : null}
      {run.jobs.length > 0 ? (
        <ul className="mt-2 flex min-w-0 flex-col gap-1 text-body-medium wrap-anywhere">
          {run.jobs.map((job) => (
            <li key={job.id}>
              <Link href={`/jobs/${job.id}?from=proposals`} className="text-primary underline underline-offset-4">
                {[job.title ?? "Untitled role", job.company].filter(Boolean).join(", ")}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </details>
  );
}

function RefusedLine({ request }: { request: RefusedJobRequest }) {
  const job = [request.job_title ?? "Untitled role", request.job_company].filter(Boolean).join(", ");
  return (
    <div className="rounded-corner-md bg-surface-container-low p-3 text-body-small">
      <p className="text-title-small">
        Request refused
        {request.answered_at ? <span className="text-muted-foreground text-body-small"> · {formatTimeAgo(request.answered_at)}</span> : null}
      </p>
      {request.job_id ? <p className="mt-1 max-w-[65ch] wrap-anywhere">{job}</p> : null}
      <p className="mt-1 max-w-[65ch]">{request.reason}</p>
      {request.job_id ? <Link href={`/jobs/${request.job_id}`} className="text-primary underline underline-offset-4">Open job</Link> : null}
    </div>
  );
}

/** The newest reported run for each automation, and the requests the other copy refused. */
export function RecentRuns() {
  const { data, isError } = useQuery({
    queryKey: AGENT_RUNS_LATEST_KEY,
    queryFn: () => apiFetch<AgentRunList>("/api/agent-runs/latest"),
  });
  return (
    <section aria-labelledby="recent-runs" className="flex min-w-0 flex-col gap-2">
      <h2 id="recent-runs" className="text-muted-foreground text-title-small">Recent runs</h2>
      {isError ? (
        <p className="text-muted-foreground text-body-medium">{"Couldn't load recent runs."}</p>
      ) : !data ? null : data.items.length === 0 ? (
        <p className="text-muted-foreground text-body-medium">
          No runs yet. Set one up on Automations.{" "}
          <Link href="/automations" className="text-primary underline underline-offset-4">Open Automations</Link>
        </p>
      ) : (
        data.items.map((run) => <RunLine key={run.id} run={run} />)
      )}
      {data?.refused_requests?.map((request) => <RefusedLine key={request.id} request={request} />)}
    </section>
  );
}
