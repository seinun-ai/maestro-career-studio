"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { extractSkills } from "@/components/job-extracted-fields";
import { knockoutNotChecked } from "@/components/job-knockout-card";
import { useBaseResumeLabel } from "@/hooks/use-base-resume-label";
import { apiFetch, listAtsScores, listTailoringSessions, resumeDiffQuery } from "@/lib/api";
import { formatShortDate } from "@/lib/format-date";
import { gapCounts } from "@/lib/gap-counts";
import { historyStatusOf } from "@/lib/inbox-readiness";
import { scorePill, standingLine } from "@/lib/job-standing";
import { jobSteps, jobStepsInput } from "@/lib/job-steps";
import { knockoutWords } from "@/lib/knockout-line";
import type { JobDetail, ProposalDetail, ProposalStatus } from "@/lib/types";

/** The gap page's analysis (lib/job-steps.ts `jobStepsInput`'s `shown`): its resume, gaps and the answers on screen. */
export type ShownAnalysis = NonNullable<Parameters<typeof jobStepsInput>[0]["shown"]>;

/**
 * The four steps (lib/job-steps.ts) for the job page and the gap page, from what the detail and the job's own
 * lists carry: no request of its own. Call it before a page's early returns; `standing` and `steps` stay null
 * until the detail loads. The gap page passes `shown`, its own analysis, which step 2's line then describes.
 */
export function useJobSteps(jobId: string, detail: JobDetail | undefined, shown?: ShownAnalysis | null) {
  const application = detail?.application ?? null;
  // Step 2's own query (list only, never scores, the same key): the header shows its best base score.
  const scoreRows = useQuery({
    queryKey: ["ats-scores", jobId],
    queryFn: () => listAtsScores(jobId),
  });
  // Step 2's own query too (the same key): its line names the open gap analysis's resume and, once the job is
  // tailored, counts the gaps of the analysis that made the draft.
  const sessions = useQuery({
    queryKey: ["tailoring-sessions", jobId],
    queryFn: () => listTailoringSessions(jobId),
  });
  // Step 3's own query (the same key): its line counts the changes to review, the previous count standing in
  // while a new draft's list loads.
  const resumeDiff = useQuery({
    ...resumeDiffQuery(application ?? { id: "", updated_at: "" }, !!application?.customized_json),
    placeholderData: keepPreviousData,
  });
  // The newest proposal, in full: the header pill's reason, Keep it's application link (the proposal says
  // whether it has one) and the Overview card all read it, so it is asked once (the card shares the key).
  const proposalId = detail?.job.proposal_id ?? null;
  const proposalQuery = useQuery({
    queryKey: ["proposal", proposalId],
    queryFn: () => apiFetch<ProposalDetail>(`/api/proposals/${proposalId}`),
    enabled: proposalId !== null,
  });
  const baseName = useBaseResumeLabel();
  // The header's one score: the application's tailored score, else the best base score.
  const scoreShown = scorePill(scoreRows.data ?? [], application?.id ?? null);
  if (!detail) return { scoreRows, sessions, proposalQuery, baseName, scoreShown, standing: null, steps: null };

  const { job } = detail;
  const standing = standingLine({
    application,
    appliedOn: application?.applied_at ? formatShortDate(application.applied_at) : null,
    resumeName: application ? detail.base_resume_name ?? baseName(application.base_resume) : null,
    tailored: scoreShown?.tailored === true,
    hasFilledAnswers: Boolean(detail.has_filled_answers),
    proposal: job.proposal_status
      ? {
          status: historyStatusOf(job.proposal_status as ProposalStatus, proposalQuery.data?.reason),
          yourself: job.proposal_status === "rejected" && historyStatusOf("rejected", proposalQuery.data?.reason) === "submitted",
          on: proposalQuery.data ? formatShortDate(proposalQuery.data.updated_at) : null,
        }
      : null,
  });
  // A skip's reason decides whether it reads Applied yourself: hold the words until it loads.
  const standingText = !application && job.proposal_status === "rejected" && proposalQuery.isLoading ? "" : standing.text;
  const skills = extractSkills(job.extracted_json);
  const steps = jobSteps(
    jobStepsInput({
      // The rung sits beside `job` on the detail, not in it (JobDetail's `job` has no stage to read).
      rung: detail,
      application,
      applicationResumeName: detail.base_resume_name ?? null,
      scoreRows: scoreRows.data ?? [],
      scoreShown,
      sessions: sessions.data ?? [],
      skills: { total: skills.length, required: skills.filter((s) => s.requirement_level === "required").length },
      knockout: knockoutWords(
        detail.knockout?.status ?? null,
        detail.knockout ? knockoutNotChecked(detail.knockout, job) : false,
      ),
      standing: standingText,
      draftChanges: resumeDiff.data?.hunks.length ?? null,
      baseName,
      countGaps: gapCounts,
      shown,
    }),
  );
  return { scoreRows, sessions, proposalQuery, baseName, scoreShown, standing, steps };
}
