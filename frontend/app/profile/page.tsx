"use client";

import { useQuery } from "@tanstack/react-query";

import { LoadErrorState } from "@/components/load-error-state";
import { AutofillSection } from "@/components/settings/autofill-section";
import { JobPreferencesSection } from "@/components/settings/job-preferences-section";
import { MarketSection } from "@/components/settings/market-section";
import { TextSettingSection } from "@/components/settings/text-setting-section";
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
      <TextSettingSection
        anchorId="persona"
        settingKey="persona"
        title="Persona"
        description="Vision, strengths, goals, and how you work. Shapes the voice of tailoring, Q&A, and outreach. Never adds facts to your resume."
        placeholder={
          "e.g.\nVision: build data products that actually ship.\nStrengths: pragmatic ML, clear writing, fast prototyping.\nGoals: senior DS/MLE role on a product team.\nHow I work: bias to shipping, evidence over opinion."
        }
        draftAction={{
          label: "Draft from my career",
          endpoint: "/api/settings/persona/draft",
          disabledReason:
            setupStatus.data?.import_resumes.done === true
              ? undefined
              : "Import a resume first.",
        }}
      />
      <MarketSection />
      <JobPreferencesSection />
      <AutofillSection />
    </PageShell>
  );
}
