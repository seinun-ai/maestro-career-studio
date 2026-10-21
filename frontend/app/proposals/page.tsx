import { InboxDashboard } from "@/components/proposals/inbox-dashboard";
import { PageShell } from "@/components/page-shell";

/** The Agent inbox. Its header lives in the dashboard, beside the counts it shares a query with. */
export default function ProposalsPage() {
  return (
    <PageShell>
      <InboxDashboard />
    </PageShell>
  );
}
