"use client";

import { useState } from "react";
import { flushSync } from "react-dom";

import { PageHeader } from "@/components/page-shell";
import { useInboxVisit } from "@/hooks/use-inbox-visit";
import { CONCEPT_ICONS } from "@/lib/concept-icons";

import { CapToday } from "./cap-today";
import { InboxCounts } from "./inbox-counts";
import { InboxHistoryContext, ProposalsSection } from "./proposals-section";
import { InboxRunNotice, RefusedRequests } from "./inbox-run-notice";

/**
 * The Agent inbox: a header (the title, the promise that nothing goes out without your yes, and three counts in
 * place of a subtitle), a line about the newest run, the lanes, then any recent refused requests.
 */
export function InboxDashboard() {
  const since = useInboxVisit();
  const history = useState(false);
  function openHistory(anchor: string) {
    if (anchor === "inbox-history") flushSync(() => history[1](true));
  }
  return (
    <InboxHistoryContext.Provider value={history}>
      <PageHeader
        title="Agent inbox"
        meta={
          <span className="text-muted-foreground inline-flex items-center gap-1.5 text-body-small">
            <CONCEPT_ICONS.locked className="size-3.5 shrink-0" aria-hidden="true" />
            Nothing is sent without your yes
          </span>
        }
        // Only near the daily limit (or when it fails to load): most days the header is the title and the counts.
        subtitle={<CapToday onlyNearLimit />}
        actions={<InboxCounts since={since} onJump={openHistory} />}
      />
      <div className="flex min-w-0 flex-col gap-6">
        <InboxRunNotice />
        <ProposalsSection since={since} />
        <RefusedRequests since={since} />
      </div>
    </InboxHistoryContext.Provider>
  );
}
