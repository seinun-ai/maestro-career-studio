"use client";

import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot } from "lucide-react";

import { AutomationCard } from "@/components/automations/automation-card";
import { RecentRuns } from "@/components/automations/recent-runs";
import { LoadErrorState } from "@/components/load-error-state";
import { NewTabLink } from "@/components/new-tab-link";
import { PageHeader, PageShell } from "@/components/page-shell";
import { Skeleton } from "@/components/ui/skeleton";
import { CONNECT_AGENT_GUIDE_URL } from "@/lib/agent-links";
import { AGENT_RUNS_LATEST_KEY, latestByAutomation } from "@/lib/agent-runs";
import { apiFetch } from "@/lib/api";
import { loadErrorDetail } from "@/lib/error-text";
import { isLoadFailure } from "@/lib/query-state";
import type { AgentRunList, AutomationCatalog } from "@/lib/types";

const AUTOMATIONS_KEY = ["automations"] as const;

export default function AutomationsPage() {
  const query = useQuery({
    queryKey: AUTOMATIONS_KEY,
    queryFn: () => apiFetch<AutomationCatalog>("/api/automations"),
    // The catalog reads shipped files and the full-automation setting.
  });
  const runs = useQuery({
    queryKey: AGENT_RUNS_LATEST_KEY,
    queryFn: () => apiFetch<AgentRunList>("/api/agent-runs/latest"),
  });

  const data = query.data;
  const cards = data?.cards.filter((c) => c.kind !== "custom") ?? [];
  const custom = data?.cards.find((c) => c.kind === "custom");
  const ran = runs.data ? latestByAutomation(runs.data.items) : null;
  // Nothing shows while the runs or the catalog are loading; a failed runs query shows the callout (no Last ran is
  // knowable). Until a card has a Last ran, connecting the agent is the step that matters: it gets a callout.
  const anyRan = !!ran && !!data && data.cards.some((c) => ran.has(c.id));
  const noteReady = runs.isError || (!!runs.data && !!data);

  // The inbox's "See runs" opens /automations#recent-runs. The list is not on the page until the catalog and
  // the runs have loaded, so the browser's own jump finds nothing: scroll to it once, when they have.
  const scrolled = useRef(false);
  const listReady = !!data && !!runs.data;
  useEffect(() => {
    if (!listReady || scrolled.current || window.location.hash !== "#recent-runs") return;
    scrolled.current = true;
    document.getElementById("recent-runs")?.scrollIntoView({ block: "start" });
  }, [listReady]);

  return (
    <PageShell>
      <PageHeader
        title="Automations"
        subtitle="Copy a prompt into any agent app connected to Maestro. It asks when to run, then does these jobs with Maestro."
      />
      {!noteReady ? null : anyRan ? (
        <p className="max-w-[65ch]">
          Your agent needs to be connected to Maestro first.{" "}
          {"Agent apps that run only in a browser can't reach it yet."}{" "}
          <NewTabLink href={CONNECT_AGENT_GUIDE_URL} className="text-primary">
            How to connect an agent
          </NewTabLink>
        </p>
      ) : (
        <div className="bg-secondary-container text-on-secondary-container rounded-corner-md flex max-w-[65ch] items-start gap-3 p-3">
          <Bot className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p>
            Your agent needs to be connected to Maestro first.{" "}
            {"Agent apps that run only in a browser can't reach it yet."}{" "}
            <NewTabLink href={CONNECT_AGENT_GUIDE_URL} className="font-medium underline underline-offset-4">
              How to connect an agent
            </NewTabLink>
          </p>
        </div>
      )}
      {isLoadFailure(query) ? (
        <LoadErrorState
          title="Couldn't load automations."
          detail={loadErrorDetail(query.error)}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
        />
      ) : !data ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <div className="grid grid-cols-2 items-start gap-4">
            {cards.map((card) => (
              <AutomationCard
                key={card.id}
                card={card}
                lastRun={ran ? (ran.get(card.id)?.finished_at ?? null) : undefined}
                outcome={ran?.get(card.id)?.outcome}
              />
            ))}
          </div>
          {custom ? <AutomationCard card={custom} /> : null}
          <RecentRuns />
        </>
      )}
    </PageShell>
  );
}
