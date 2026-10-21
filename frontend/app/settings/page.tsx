"use client";

import { use } from "react";

import { AboutSection } from "@/components/settings/about-section";
import { AiModelSection } from "@/components/settings/ai-model-section";
import { AppearanceSection } from "@/components/settings/appearance-section";
import { AutoApplySection } from "@/components/settings/auto-apply-section";
import { CompanionFillSection } from "@/components/settings/companion-fill-section";
import { ConnectedAgentsCard } from "@/components/settings/connected-agents-card";
import { ConnectAssistantCard } from "@/components/settings/connect-assistant-card";
import { CompanionApplySection, FormFillingSection } from "@/components/settings/form-filling-section";
import { FullAutomationSection, JobSiteLoginCard } from "@/components/settings/full-automation-section";
import { McpWorkflowSection } from "@/components/settings/mcp-workflow-section";
import { ModelsSection } from "@/components/settings/models-section";
import { HoursPerYearSection } from "@/components/settings/hours-per-year-section";
import { MoneySection } from "@/components/settings/money-section";
import { PromptsSection } from "@/components/settings/prompts-section";
import { QuickTailorSection } from "@/components/settings/quick-tailor-section";
import { ResumesFolderSection } from "@/components/settings/resumes-folder-section";
import { SettingsTabs } from "@/components/settings/settings-tabs";
import { SecondCopySection } from "@/components/settings/second-copy-section";
import { CustomEndpointSection } from "@/components/settings/llm-endpoint";
import { ModelCatalogSection } from "@/components/settings/model-catalog-panel";
import { PageHeader, PageShell } from "@/components/page-shell";
import { useFocusSection } from "@/lib/use-focus-section";

/**
 * How the app behaves, in four tabs by purpose (owner decision D11; candidate facts live on
 * `/profile`: see the page rule in `docs/frontend-conventions.md`). Basics is what a new install needs
 * first (nothing works without an AI model), the Companion tab is the browser extension's, Agent apps is
 * the connected agents', and Advanced holds the rest. The tab table, which tab each card id opens and
 * where each old `?tab=` lands, is `lib/settings-tabs.ts`. Nothing was removed in the move: every item
 * is pinned to its tab by test_frontend_settings_refresh.py.
 */
export default function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string | string[] }>;
}) {
  // Read, not used: it makes the route dynamic, so the server renders the tab `?tab=` names and
  // SettingsTabs' useSearchParams needs no Suspense boundary (see useSettingsTab).
  use(searchParams);
  useFocusSection();

  return (
    <PageShell>
      <PageHeader title="Settings" />
      <SettingsTabs
        page="settings"
        panels={{
          basics: (
            <>
              <AiModelSection />
              <MoneySection />
              <ResumesFolderSection />
              <AppearanceSection />
              <AboutSection />
            </>
          ),
          companion: (
            <>
              <CompanionFillSection />
              <CompanionApplySection />
              <FormFillingSection />
            </>
          ),
          agents: (
            <>
              <ConnectAssistantCard />
              <ConnectedAgentsCard />
              <FullAutomationSection />
              <AutoApplySection />
              <JobSiteLoginCard />
              <McpWorkflowSection />
              <SecondCopySection />
            </>
          ),
          advanced: (
            <>
              <ModelsSection />
              <ModelCatalogSection />
              <CustomEndpointSection />
              <PromptsSection />
              <QuickTailorSection />
              <HoursPerYearSection />
            </>
          ),
        }}
      />
    </PageShell>
  );
}
