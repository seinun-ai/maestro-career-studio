import { CapToday } from "@/components/proposals/cap-today";
import { ProposalsSection } from "@/components/proposals/proposals-section";
import { PageHeader, PageShell } from "@/components/page-shell";

export default function ProposalsPage() {
  return (
    <PageShell>
      <PageHeader
        title="Agent inbox"
        // A node slot: PageHeader renders it in a <div>, so the <p> and the
        // client-side cap line are valid children.
        subtitle={
          <>
            <p>Jobs your connected agents found. Nothing is submitted without your yes.</p>
            <CapToday />
          </>
        }
      />
      <ProposalsSection />
    </PageShell>
  );
}
