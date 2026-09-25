"use client";

import { use } from "react";
import { ArrowLeft } from "lucide-react";

import { GuardedLink as Link } from "@/components/guarded-link";
import { IconButton } from "@/components/icon-button";
import { PageHeader, PageShell } from "@/components/page-shell";

/**
 * A placeholder until Task 12 of the health check v3 plan builds the question pass here
 * (`question-pass.tsx`): the report's Start the questions already opens this route.
 */
export default function HealthQuestionsPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  return (
    <PageShell>
      <PageHeader
        leading={
          <IconButton
            label="Back to the health report"
            icon={<ArrowLeft className="size-4" />}
            size="icon-sm"
            className="mt-1.5 shrink-0"
            nativeButton={false}
            render={<Link href={`/base-resumes/${slug}/health`} className="text-muted-foreground" />}
          />
        }
        title="Questions"
      />
      <p className="text-muted-foreground max-w-[65ch] text-sm">
        Answering every question in one pass is coming in Task 12. Until then, answer each one on
        its card in the health report.
      </p>
    </PageShell>
  );
}
