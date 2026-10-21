"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, Copy } from "lucide-react";

import { AutomationCard, AutomationRow, NeverList } from "@/components/automations/automation-card";
import { RecentRuns } from "@/components/automations/recent-runs";
import { LoadErrorState } from "@/components/load-error-state";
import { NewTabLink } from "@/components/new-tab-link";
import { PageHeader, PageShell } from "@/components/page-shell";
import { Fold } from "@/components/ui/fold";
import { Skeleton } from "@/components/ui/skeleton";
import { CONNECT_AGENT_GUIDE_URL } from "@/lib/agent-links";
import { AGENT_RUNS_KEY, AGENT_RUNS_PATH, recentRunsSummary, runsByAutomation } from "@/lib/agent-runs";
import { apiFetch } from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { reportedInStrip } from "@/lib/day-strip";
import { loadErrorDetail } from "@/lib/error-text";
import { isLoadFailure } from "@/lib/query-state";
import type { AgentRunList, AutomationCatalog } from "@/lib/types";

const AUTOMATIONS_KEY = ["automations"] as const;

/** How automations work, in three steps: Maestro hands over a prompt and shows what runs reported; the
 * agent app owns the schedule (D5). */
const STEPS = [
  { Icon: Copy, title: "Copy a prompt", note: "The same one for any agent app" },
  { Icon: CONCEPT_ICONS.agentInbox, title: "Your agent schedules it", note: "You change or stop it there" },
  { Icon: CONCEPT_ICONS.automations, title: "Each run reports here", note: "What it did and what needs you" },
] as const;

function HowItWorks() {
  return (
    <ol aria-label="How automations work" className="grid grid-cols-3 divide-x overflow-clip rounded-corner-md bg-card">
      {STEPS.map(({ Icon, title, note }) => (
        <li key={title} className="flex min-w-0 items-center gap-3 px-5 py-3.5">
          <span className="bg-secondary-container text-on-secondary-container inline-flex size-7 shrink-0 items-center justify-center rounded-full">
            <Icon className="size-3.5" aria-hidden="true" />
          </span>
          <span className="flex min-w-0 flex-col">
            <span className="text-title-small">{title}</span>
            <span className="text-muted-foreground text-body-small">{note}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

// The inbox's "See runs" lands on #recent-runs, which opens that fold. The server has no hash: hydrate with
// none, then React re-renders with the real one.
function subscribeToHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}
const readHash = () => window.location.hash;
const noHash = () => "";

export default function AutomationsPage() {
  const query = useQuery({
    queryKey: AUTOMATIONS_KEY,
    queryFn: () => apiFetch<AutomationCatalog>("/api/automations"),
    // The catalog reads shipped files and the full-automation setting.
  });
  const runs = useQuery({
    queryKey: AGENT_RUNS_KEY,
    queryFn: () => apiFetch<AgentRunList>(AGENT_RUNS_PATH),
  });

  const data = query.data;
  // The cached runs stay through a failed background refetch; with none, no card claims anything about reports.
  const byAutomation = runs.data ? runsByAutomation(runs.data.items) : null;
  const today = new Date();
  const reporting = byAutomation ? (data?.cards ?? []).filter((card) => reportedInStrip(byAutomation.get(card.id) ?? [], today)) : [];
  const quiet = (data?.cards ?? []).filter((card) => !reporting.includes(card));
  const olderReports = quiet.some((card) => byAutomation?.has(card.id));
  // Any report proves an agent reached Maestro. Until one does, connecting it is the step that matters: a
  // callout. Nothing shows while the runs or the catalog are loading; a failed runs read still shows it.
  const anyRan = !!runs.data && runs.data.items.length > 0;
  const noteReady = runs.isError || (!!runs.data && !!data);
  const latest = byAutomation ? [...byAutomation.values()].map((list) => list[0]) : [];

  const anchor = useSyncExternalStore(subscribeToHash, readHash, noHash);
  const [runsOpen, setRunsOpen] = useState<boolean | null>(null);
  const recentOpen = runsOpen ?? anchor === "#recent-runs";

  // The list is not on the page until the catalog and the runs have loaded, so the browser's own jump to
  // #recent-runs finds nothing: scroll to it once, when they have.
  const scrolled = useRef(false);
  const listReady = !!data && !!runs.data;
  useEffect(() => {
    if (!listReady || scrolled.current || window.location.hash !== "#recent-runs") return;
    scrolled.current = true;
    document.getElementById("recent-runs")?.scrollIntoView({ block: "start" });
  }, [listReady]);

  return (
    <PageShell>
      <PageHeader title="Automations" />
      <HowItWorks />
      {noteReady && !anyRan ? (
        <div className="bg-secondary-container text-on-secondary-container rounded-corner-md flex max-w-[65ch] items-start gap-3 p-3">
          <Bot className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p>
            Connect your agent to Maestro first.{" "}
            {"Agent apps that run only in a browser can't reach it yet."}{" "}
            <NewTabLink href={CONNECT_AGENT_GUIDE_URL} className="font-medium underline underline-offset-4">
              How to connect an agent
            </NewTabLink>
          </p>
        </div>
      ) : null}
      {isLoadFailure(query) ? (
        <LoadErrorState
          title="Couldn't load automations."
          detail={loadErrorDetail(query.error)}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
        />
      ) : !data || (!byAutomation && !isLoadFailure(runs)) ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          {reporting.length > 0 ? (
            <section aria-labelledby="reporting" className="flex flex-col gap-2">
              <h2 id="reporting" className="text-title-small">
                Reporting <span className="text-muted-foreground tabular-nums">{reporting.length}</span>
              </h2>
              <div className="grid grid-cols-2 items-start gap-4">
                {reporting.map((card) => (
                  <AutomationCard key={card.id} card={card} runs={byAutomation?.get(card.id) ?? []} />
                ))}
              </div>
            </section>
          ) : null}
          {quiet.length > 0 ? (
            <section aria-labelledby="no-reports" className="flex flex-col gap-2">
              {byAutomation ? (
                <h2 id="no-reports" className="text-title-small">
                  {olderReports ? "No reports in 14 days" : "No reports yet"}{" "}
                  <span className="text-muted-foreground tabular-nums">{quiet.length}</span>
                </h2>
              ) : (
                <p id="no-reports" className="text-muted-foreground text-body-medium">{"Couldn't load reports."}</p>
              )}
              <ul className="divide-y overflow-clip rounded-corner-md bg-card">
                {quiet.map((card) => (
                  <AutomationRow key={card.id} card={card} lastReport={byAutomation?.get(card.id)?.[0]?.finished_at} />
                ))}
              </ul>
            </section>
          ) : null}
          <div className="flex flex-col gap-2">
            <div id="recent-runs" className="scroll-mt-6">
              <Fold
                title="Recent runs"
                summary={recentRunsSummary(latest)}
                open={recentOpen}
                onOpenChange={setRunsOpen}
              >
                <RecentRuns />
              </Fold>
            </div>
            <Fold title="What each one never does">
              <NeverList cards={data.cards} />
            </Fold>
          </div>
        </>
      )}
    </PageShell>
  );
}
