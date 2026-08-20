"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  Briefcase,
  Building2,
  FileText,
  Images,
  ListChecks,
  MessageSquareText,
} from "lucide-react";
import type { ReactNode } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadErrorState } from "@/components/load-error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { formatAbsoluteDateTime } from "@/lib/format-date";
import type { ProposalDetail } from "@/lib/types";

/**
 * Proposal-only fields for the job Overview tab — plan, expires, evidence.
 * Fit scores live on Score & Tailor / triage; salary / work-auth / level live
 * in JobExtractedFields. Do not duplicate them here.
 */
export function ProposalAgentPanel({ proposalId }: { proposalId: string }) {
  const { data, isLoading, isError, error, isFetching, refetch } = useQuery({
    queryKey: ["proposal", proposalId],
    queryFn: () =>
      apiFetch<ProposalDetail>(`/api/proposals/${proposalId}`),
  });

  if (isError) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle>Agent proposal</CardTitle>
        </CardHeader>
        <CardContent>
          <LoadErrorState
            className="py-8"
            title="Couldn't load the agent proposal."
            detail={(error as Error)?.message}
            retrying={isFetching}
            onRetry={() => void refetch()}
          />
        </CardContent>
      </Card>
    );
  }

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle>Agent proposal</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }

  const plan = (data.plan_json ?? {}) as Record<string, unknown>;
  const planSummary = typeof plan.summary === "string" ? plan.summary : null;
  const companyNote =
    typeof plan.company_note === "string" ? plan.company_note : null;
  const evidence = data.evidence_json ?? [];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle>Agent proposal</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5 text-sm">
        {/* Meta labels match JobExtractedFields StatLine (uppercase 11px). */}
        <dl className="flex flex-wrap gap-x-6 gap-y-3">
          <Fact label="Proposed">
            {formatAbsoluteDateTime(data.created_at)}
          </Fact>
          <Fact label="Expires">
            {data.expires_at ? formatAbsoluteDateTime(data.expires_at) : "—"}
          </Fact>
          {data.reason ? <Fact label="Reason">{data.reason}</Fact> : null}
        </dl>

        {companyNote ? (
          <section>
            <SectionHeading icon={<Building2 />}>
              About the company
            </SectionHeading>
            <p className="text-muted-foreground text-sm leading-relaxed">
              {companyNote}
            </p>
          </section>
        ) : null}

        {planSummary ? (
          <section>
            <SectionHeading icon={<ListChecks />}>
              Tailoring plan
            </SectionHeading>
            <p className="text-muted-foreground text-sm leading-relaxed">
              {planSummary}
            </p>
          </section>
        ) : null}

        {data.qa_entries.length > 0 ? (
          <section>
            <SectionHeading icon={<MessageSquareText />}>
              Drafted answers
            </SectionHeading>
            <ul className="flex flex-col gap-2">
              {data.qa_entries.map((q) => (
                <li key={q.id} className="rounded-md border p-2.5">
                  <div className="text-xs font-medium">{q.prompt}</div>
                  <div className="text-muted-foreground mt-1 whitespace-pre-wrap text-xs">
                    {q.answer}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {evidence.length > 0 ? (
          <section>
            <SectionHeading icon={<Images />}>Evidence</SectionHeading>
            <div className="flex flex-wrap gap-2">
              {evidence.map((e) => {
                const name = e.path.split("/").pop() ?? e.path;
                const src = `/api/proposals/${data.id}/evidence/${name}`;
                return (
                  <a
                    key={`${e.step}-${e.path}`}
                    href={src}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group relative"
                    title={`Step ${e.step}: ${e.label}`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element -- backend-served evidence, no next/image loader */}
                    <img
                      src={src}
                      alt={`Step ${e.step}: ${e.label}`}
                      className="h-24 rounded-md border object-cover"
                    />
                  </a>
                );
              })}
            </div>
          </section>
        ) : null}

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {data.application?.pdf_ready ? (
            <a
              href={`/api/applications/${data.application.id}/pdf`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs underline"
            >
              <FileText className="size-3.5" aria-hidden="true" />
              Tailored resume PDF
            </a>
          ) : null}
          <Link
            href={`/proposals`}
            className="text-muted-foreground inline-flex items-center gap-1.5 text-xs underline"
          >
            <Briefcase className="size-3.5" aria-hidden="true" />
            All proposals
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

function SectionHeading({
  icon,
  children,
}: {
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold [&>svg]:size-4">
      {icon}
      {children}
    </h4>
  );
}

function Fact({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col">
      <dt className="text-muted-foreground text-[11px] tracking-wide uppercase">
        {label}
      </dt>
      <dd>{children}</dd>
    </div>
  );
}
