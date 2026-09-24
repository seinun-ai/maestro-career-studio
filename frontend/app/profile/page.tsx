"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";

import { LoadErrorState } from "@/components/load-error-state";
import { AutofillSection } from "@/components/settings/autofill-section";
import { JobPreferencesSection } from "@/components/settings/job-preferences-section";
import { MarketSection } from "@/components/settings/market-section";
import { PersonaSection } from "@/components/settings/persona-section";
import { SettingsTabs } from "@/components/settings/settings-tabs";
import { SetupStatusStrip } from "@/components/setup/setup-status-strip";
import { apiFetch } from "@/lib/api";
import { isLoadFailure } from "@/lib/query-state";
import type { SetupStatus } from "@/lib/types";
import { useFocusSection } from "@/lib/use-focus-section";
import { PageHeader, PageShell } from "@/components/page-shell";

/**
 * Who the candidate is, in two tabs (`lib/settings-tabs.ts`). The setup strip spans both tabs (and
 * Settings), so it sits above the tab row, and jumps in place with the page's one `focus`.
 */
export default function ProfilePage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string | string[] }>;
}) {
  // Read, not used: it makes the route dynamic, so the server renders the tab `?tab=` names and
  // SettingsTabs' useSearchParams needs no Suspense boundary (see useSettingsTab).
  use(searchParams);
  const focus = useFocusSection();

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
      {isLoadFailure(setupStatus) ? (
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
          focus={focus}
        />
      )}
      <SettingsTabs
        page="profile"
        panels={{
          you: (
            <>
              <PersonaSection
                draftDisabledReason={
                  setupStatus.data?.import_resumes.done === true
                    ? undefined
                    : "Import a resume first."
                }
              />
              <MarketSection />
              <JobPreferencesSection />
            </>
          ),
          autofill: <AutofillSection />,
        }}
      />
    </PageShell>
  );
}
