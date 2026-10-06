"use client";

import { GuardedLink as Link } from "@/components/guarded-link";
import { useRoleLabel } from "@/components/role-category-picker";
import { Info } from "lucide-react";

import { humanizeEnum, SkillGroup, type ExtractedSkill } from "@/components/job-extracted-fields";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Job } from "@/lib/types";

// Cap on badges across all three groups; the rest read as "+N more" under the group that holds them.
const SKILL_CAP = 24;

export function JobExtractionSummary({
  job,
  onScoreAts,
}: {
  job: Job;
  onScoreAts?: () => void;
}) {
  const skills =
    (job.extracted_json?.skills as ExtractedSkill[] | undefined) ?? [];
  const required = skills.filter((x) => x.requirement_level === "required");
  const preferred = skills.filter((x) => x.requirement_level === "preferred");
  const mentioned = skills.filter(
    (x) => x.requirement_level !== "required" && x.requirement_level !== "preferred",
  );
  const preferredLimit = Math.max(0, SKILL_CAP - required.length);
  const mentionedLimit = Math.max(0, preferredLimit - preferred.length);
  // Words, never the stored keys (`ai_ml_engineer`, `full_time`, `on_site`).
  const roleLabelOf = useRoleLabel();

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {job.company ?? "—"} · {job.title ?? "—"}
        </CardTitle>
        {job.already_existed ? (
          <div
            role="status"
            className="mt-1 flex items-center gap-2 rounded-corner-md bg-primary-container p-3 text-body-medium text-on-primary-container"
          >
            <Info className="size-4 shrink-0" aria-hidden="true" />
            This job is already saved.
          </div>
        ) : (
          <p className="text-muted-foreground text-body-medium">
            Saved to{" "}
            <Link href="/applications?status=saved" className="underline">
              Jobs
            </Link>
            .
          </p>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          {job.role_category && (
            <Badge variant="outline">{roleLabelOf(job.role_category)}</Badge>
          )}
          {job.level && <Badge variant="outline">{humanizeEnum(job.level)}</Badge>}
          {job.employment_type && (
            <Badge variant="outline">{humanizeEnum(job.employment_type)}</Badge>
          )}
          {job.work_mode && <Badge variant="outline">{humanizeEnum(job.work_mode)}</Badge>}
          {job.location && <Badge variant="outline">{job.location}</Badge>}
        </div>

        {skills.length > 0 && (
          <div className="space-y-3">
            <SkillGroup title="Required" variant="default" skills={required} limit={SKILL_CAP} />
            <SkillGroup title="Preferred" variant="tonal" skills={preferred} limit={preferredLimit} />
            <SkillGroup title="Mentioned" variant="outline" skills={mentioned} limit={mentionedLimit} />
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            nativeButton={false}
            render={<Link href={`/jobs/${job.id}`}>View job</Link>}
          />
          {onScoreAts && (
            <Button size="sm" onClick={onScoreAts}>
              Score and tailor
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
