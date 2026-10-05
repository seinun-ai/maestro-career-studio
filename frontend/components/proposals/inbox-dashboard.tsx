"use client";

import { useInboxVisit } from "@/hooks/use-inbox-visit";

import { ArrivalsStrip } from "./arrivals-strip";
import { ProposalsSection } from "./proposals-section";
import { RecentRuns } from "./recent-runs";

/** What arrived, what your agent runs did, then the inbox lanes. */
export function InboxDashboard() {
  const since = useInboxVisit();
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <ArrivalsStrip since={since} />
      <RecentRuns />
      <ProposalsSection since={since} />
    </div>
  );
}
