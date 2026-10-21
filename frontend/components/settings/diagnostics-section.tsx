"use client";

import { useId } from "react";

import { AutofillCoverageCard } from "@/components/settings/autofill-coverage-card";
import { GROUP_HEADING } from "@/components/settings/setting-layout";

/**
 * Settings › Advanced › Diagnostics (owner decision D6): what the Companion's fill log recorded, with
 * Clear data. It left Analytics, which shows only what the job search did; this is how the tool did.
 * The card is the one Analytics had, unchanged. The id sits on the group, which a deep link lands on.
 */
export function DiagnosticsSection() {
  const headingId = useId();
  return (
    <div id="diagnostics" role="group" aria-labelledby={headingId} className="grid gap-3">
      <h2 id={headingId} className={GROUP_HEADING}>
        Diagnostics
      </h2>
      <AutofillCoverageCard />
    </div>
  );
}
