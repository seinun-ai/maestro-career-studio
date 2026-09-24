"use client";

import { use } from "react";
import { BookOpen } from "lucide-react";

import { AboutSection } from "@/components/settings/about-section";
import { AppearanceSection } from "@/components/settings/appearance-section";
import { AutoApplySection } from "@/components/settings/auto-apply-section";
import { McpWorkflowSection } from "@/components/settings/mcp-workflow-section";
import {
  ApiKeysSection,
  ModelsSection,
} from "@/components/settings/models-section";
import { PromptsSection } from "@/components/settings/prompts-section";
import { QuickTailorSection } from "@/components/settings/quick-tailor-section";
import { SettingsTabs } from "@/components/settings/settings-tabs";
import { Button } from "@/components/ui/button";
import { PageHeader, PageShell } from "@/components/page-shell";
import { useFocusSection } from "@/lib/use-focus-section";

const guideButton = (
  <Button
    variant="outline"
    size="sm"
    nativeButton={false}
    render={
      <a
        href="https://github.com/seinun-ai/maestro-career-studio/blob/main/docs/GETTING_STARTED.md"
        target="_blank"
        rel="noopener noreferrer"
      >
        <BookOpen className="size-4" />
        Getting started guide
      </a>
    }
  />
);

/**
 * System behaviour, in five tabs. Candidate facts live on `/profile`: see the page rule in
 * `docs/frontend-conventions.md`. The first tab is what a new install needs first (nothing works
 * without a key); the tab table, and which tab each card id opens, is `lib/settings-tabs.ts`.
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
      <PageHeader
        title="Settings"
        subtitle="Models, tailoring, connected agents and appearance."
        actions={guideButton}
      />
      <SettingsTabs
        page="settings"
        panels={{
          models: (
            <>
              <ApiKeysSection />
              <ModelsSection />
              <PromptsSection />
            </>
          ),
          tailoring: <QuickTailorSection />,
          agents: (
            <>
              {/* Connected agents explainer (wave 2, id="connected-agents") mounts here, first. */}
              <McpWorkflowSection />
              <AutoApplySection />
            </>
          ),
          appearance: <AppearanceSection />,
          about: <AboutSection />,
        }}
      />
    </PageShell>
  );
}
