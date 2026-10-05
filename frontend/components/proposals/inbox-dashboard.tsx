"use client";

import { useState } from "react";
import { flushSync } from "react-dom";

import { useInboxVisit } from "@/hooks/use-inbox-visit";

import { ArrivalsStrip } from "./arrivals-strip";
import { InboxHistoryContext, ProposalsSection } from "./proposals-section";
import { RecentRuns } from "./recent-runs";

/** What arrived, what your agent runs did, then the inbox lanes. */
export function InboxDashboard() {
  const since = useInboxVisit();
  const history = useState(false);
  function openHistory(anchor: string) {
    if (anchor === "inbox-history") flushSync(() => history[1](true));
  }
  return (
    <InboxHistoryContext.Provider value={history}>
      <div className="flex min-w-0 flex-col gap-6">
        <ArrivalsStrip since={since} onJump={openHistory} />
        <RecentRuns />
        <ProposalsSection since={since} />
      </div>
    </InboxHistoryContext.Provider>
  );
}
