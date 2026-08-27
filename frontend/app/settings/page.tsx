"use client";

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
import { Button } from "@/components/ui/button";
import { PageHeader, PageShell } from "@/components/page-shell";
import { useFocusSection } from "@/lib/use-focus-section";

/**
 * System behaviour. Candidate facts live on `/profile` — see the page rule in
 * `docs/frontend-conventions.md`.
 *
 * Ordered by what a new install needs first. API keys and Models used to sit
 * fifth, below the fold, under Prompts — even though nothing in the app works
 * without a key, and Prompts is the deepest thing on the page. The subtitle had
 * been listing them in this order all along.
 */
export default function SettingsPage() {
  useFocusSection();

  return (
    <PageShell>
      <PageHeader
        title="Settings"
        subtitle="API keys, models, agent behaviour, and appearance."
        actions={
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
        }
      />
      <ApiKeysSection />
      <ModelsSection />
      <QuickTailorSection />
      <AutoApplySection />
      <McpWorkflowSection />
      <PromptsSection />
      <AppearanceSection />
      <AboutSection />
    </PageShell>
  );
}
