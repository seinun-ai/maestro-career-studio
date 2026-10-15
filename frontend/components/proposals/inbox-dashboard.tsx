"use client";

import { useState } from "react";
import { flushSync } from "react-dom";

import { useInboxVisit } from "@/hooks/use-inbox-visit";

import { ArrivalsStrip } from "./arrivals-strip";
import { InboxHistoryContext, ProposalsSection } from "./proposals-section";
import { InboxRunNotice, RefusedRequests } from "./inbox-run-notice";

/** What is waiting, a line about the newest run, the inbox lanes, then any recent refused requests. */
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
        <InboxRunNotice />
        <ProposalsSection since={since} />
        <RefusedRequests since={since} />
      </div>
    </InboxHistoryContext.Provider>
  );
}
