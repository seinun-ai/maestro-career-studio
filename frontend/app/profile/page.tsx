"use client";

import { useQuery } from "@tanstack/react-query";

import { LoadErrorState } from "@/components/load-error-state";
import { AutofillSection } from "@/components/settings/autofill-section";
import { JobPreferencesSection } from "@/components/settings/job-preferences-section";
import { MarketSection } from "@/components/settings/market-section";
import { PersonaSection } from "@/components/settings/persona-section";
import { SetupStatusStrip } from "@/components/setup/setup-status-strip";
import { apiFetch } from "@/lib/api";
import type { SetupStatus } from "@/lib/types";
import { useFocusSection } from "@/lib/use-focus-section";
import { PageHeader, PageShell } from "@/components/page-shell";

export default function ProfilePage() {
  useFocusSection();

  const setupStatus = useQuery({
    queryKey: ["setup-status"],
    queryFn: () => apiFetch<SetupStatus>("/api/setup/status"),
    refetchOnMount: "always",
  });

  return (
    <PageShell>
      <PageHeader
        title="Profile"
        subtitle="Who you are as a candidate, and the answers autofill uses."
      />
      {setupStatus.isError ? (
        <LoadErrorState
          className="py-8"
          title="Couldn't load setup progress."
          detail={(setupStatus.error as Error)?.message}
          retrying={setupStatus.isFetching}
          onRetry={() => void setupStatus.refetch()}
        />
      ) : (
        <SetupStatusStrip
          status={setupStatus.data}
          loading={setupStatus.isLoading}
        />
      )}
      <PersonaSection
        draftDisabledReason={
          setupStatus.data?.import_resumes.done === true
            ? undefined
            : "Import a resume first."
        }
      />
      <MarketSection />
      <JobPreferencesSection />
      <AutofillSection />
    </PageShell>
  );
}
