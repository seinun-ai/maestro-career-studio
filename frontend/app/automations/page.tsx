"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { AppPicker } from "@/components/automations/app-picker";
import { AutomationCard } from "@/components/automations/automation-card";
import { LoadErrorState } from "@/components/load-error-state";
import { NewTabLink } from "@/components/new-tab-link";
import { PageHeader, PageShell } from "@/components/page-shell";
import { Skeleton } from "@/components/ui/skeleton";
import { useLocalStorageState } from "@/hooks/use-local-storage-state";
import { CONNECT_AGENT_GUIDE_URL } from "@/lib/agent-links";
import { apiFetch } from "@/lib/api";
import {
  APP_STORE_KEY,
  parseStoredApp,
  serializeApp,
} from "@/lib/automations";
import { loadErrorDetail } from "@/lib/error-text";
import { isLoadFailure } from "@/lib/query-state";
import type { AutomationCatalog } from "@/lib/types";

const AUTOMATIONS_KEY = ["automations"] as const;
const DEFAULT_APP = "claude-desktop";

export default function AutomationsPage() {
  const query = useQuery({
    queryKey: AUTOMATIONS_KEY,
    queryFn: () => apiFetch<AutomationCatalog>("/api/automations"),
  });
  // The last app chosen, if storage allows; an unknown or missing id falls
  // back to the default below.
  const [storedApp, setStoredApp] = useLocalStorageState(
    APP_STORE_KEY,
    parseStoredApp,
    serializeApp,
  );
  // Also held in state: with storage blocked the choice must still switch.
  const [picked, setPicked] = useState<string | null>(null);

  const data = query.data;
  const wanted = picked ?? storedApp ?? DEFAULT_APP;
  const app =
    data?.apps.find((a) => a.id === wanted) ??
    data?.apps.find((a) => a.id === DEFAULT_APP) ??
    data?.apps[0];
  const cards = data?.cards.filter((c) => c.kind !== "custom") ?? [];
  const custom = data?.cards.find((c) => c.kind === "custom");

  return (
    <PageShell>
      <PageHeader
        title="Automations"
        subtitle="Copy a prompt into your own agent app. It asks when to run, then does these jobs with Maestro."
      />
      <p className="max-w-[65ch]">
        Your agent needs the Maestro connector first.{" "}
        <NewTabLink href={CONNECT_AGENT_GUIDE_URL} className="text-primary">
          How to connect an agent
        </NewTabLink>
      </p>
      {isLoadFailure(query) ? (
        <LoadErrorState
          title="Couldn't load automations."
          detail={loadErrorDetail(query.error)}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
        />
      ) : !data || !app ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <AppPicker
            apps={data.apps}
            value={app.id}
            onChange={(id) => {
              setPicked(id);
              setStoredApp(id);
            }}
          />
          {app.note ? (
            <p className="text-muted-foreground max-w-[65ch]">{app.note}</p>
          ) : null}
          <div className="grid grid-cols-2 gap-4">
            {cards.map((card) => (
              <AutomationCard key={card.id} card={card} app={app} />
            ))}
          </div>
          {custom ? <AutomationCard card={custom} app={app} /> : null}
        </>
      )}
    </PageShell>
  );
}
