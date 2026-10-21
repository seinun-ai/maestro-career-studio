"use client";

import { RateLabel } from "@/components/analytics/rate-label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ResumeTag } from "@/components/visual";
import { useBaseResumeLabel } from "@/hooks/use-base-resume-label";
import type { SearchSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Each base resume's applications in the period, most applied first: heard back and interview are both shares of
 * its applied, through RateLabel. The resume keeps its square (the README's base-resume colour rule). */
export function ByResumeCard({ summary, className }: { summary: SearchSummary; className?: string }) {
  const baseName = useBaseResumeLabel();
  const rows = summary.by_resume;
  return (
    <Card className={cn("min-w-0", className)}>
      <CardHeader>
        <CardTitle>By resume</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-muted-foreground text-body-medium">No applications in this period.</p>
        ) : (
          <table className="w-full table-fixed text-body-medium">
            <thead>
              <tr className="border-b text-left text-body-small text-muted-foreground">
                <th scope="col" className="pb-2 font-normal">Resume</th>
                <th scope="col" className="w-16 pb-2 text-right font-normal">Applied</th>
                <th scope="col" className="w-28 pb-2 text-right font-normal">Heard back</th>
                <th scope="col" className="w-28 pb-2 text-right font-normal">Interview</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((row) => {
                const name = row.name ?? baseName(row.slug);
                return (
                  <tr key={row.slug} className="h-11">
                    <th scope="row" className="min-w-0 pr-2 text-left font-normal">
                      <ResumeTag hue={row.color_hue} className="max-w-full">
                        <span className="min-w-0 truncate" title={name}>{name}</span>
                      </ResumeTag>
                    </th>
                    <td className="text-right tabular-nums">{row.applied}</td>
                    <td className="text-right">
                      <RateLabel value={row.heard_back} />
                    </td>
                    <td className="text-right">
                      <RateLabel value={row.interview} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
