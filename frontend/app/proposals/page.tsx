import { ProposalsSection } from "@/components/proposals/proposals-section";
import { PageHeader, PageShell } from "@/components/page-shell";

export default function ProposalsPage() {
  return (
    <PageShell>
      <PageHeader
        title="Agent proposals"
        subtitle="What the hunt found. Submitting still needs your approval."
      />
      <ProposalsSection />
    </PageShell>
  );
}
