import { LeadCard } from "@/components/ui/lead-card";

/** Today's lead with no job saved yet (setup done, nothing else next): one button to Add job (`/new`). */
export function FirstJobCard() {
  return (
    <LeadCard eyebrow="Next up" action={{ label: "Add job", href: "/new" }}>
      <h2 className="text-headline-small">Add your first job</h2>
    </LeadCard>
  );
}
