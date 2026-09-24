"use client";

import { GuardedLink as Link } from "@/components/guarded-link";
import { useRoleLabel } from "@/components/role-category-picker";
import { Info } from "lucide-react";

import { humanizeEnum } from "@/components/job-extracted-fields";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Job } from "@/lib/types";

interface ExtractedSkill {
  skill_name: string;
  requirement_level?: string;
}

function skillVariant(
  level: string | undefined,
): "default" | "secondary" | "outline" {
  if (level === "required") return "default";
  if (level === "preferred") return "secondary";
  return "outline";
}

export function JobExtractionSummary({
  job,
  onScoreAts,
}: {
  job: Job;
  onScoreAts?: () => void;
}) {
  const skills =
    (job.extracted_json?.skills as ExtractedSkill[] | undefined) ?? [];
  const visible = skills.slice(0, 24);
  const extra = skills.length - visible.length;
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
            className="mt-1 flex items-center gap-2 rounded-lg border border-blue-500/40 bg-blue-500/10 p-3 text-sm text-blue-900 dark:text-blue-100"
          >
            <Info className="size-4 shrink-0" aria-hidden="true" />
            This job is already saved.
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">
            Saved to{" "}
            <Link href="/applications?status=saved" className="underline">
              Applications
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

        {visible.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {visible.map((skill) => (
              <Badge
                key={skill.skill_name}
                variant={skillVariant(skill.requirement_level)}
              >
                {skill.skill_name}
              </Badge>
            ))}
            {extra > 0 && (
              <span className="text-muted-foreground self-center text-xs">
                +{extra} more
              </span>
            )}
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
