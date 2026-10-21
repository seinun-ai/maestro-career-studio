"use client";

import { useQuery } from "@tanstack/react-query";

import { extractSkills } from "@/components/job-extracted-fields";
import { knockoutNotChecked } from "@/components/job-knockout-card";
import { useBaseResumeLabel } from "@/hooks/use-base-resume-label";
import { apiFetch, listAtsScores, listTailoringSessions } from "@/lib/api";
import { formatShortDate } from "@/lib/format-date";
import { gapCounts } from "@/lib/gap-counts";
import { historyStatusOf } from "@/lib/inbox-readiness";
import { scorePill, standingLine } from "@/lib/job-standing";
import { jobFacts, jobSteps, jobStepsInput } from "@/lib/job-steps";
import { knockoutWords } from "@/lib/knockout-line";
import type { JobDetail, ProposalDetail, ProposalStatus } from "@/lib/types";

/** The gap page's analysis (lib/job-steps.ts `jobStepsInput`'s `shown`): its resume, gaps and the answers on screen. */
export type ShownAnalysis = NonNullable<Parameters<typeof jobStepsInput>[0]["shown"]>;

/**
 * The four steps (lib/job-steps.ts) for the job page and the gap page, from what the detail and the job's own
 * lists carry: no request of its own. Call it before a page's early returns; `standing`, `steps`, `jobLine` and
 * `draft` stay null until the detail loads. The gap page passes `shown`, its own analysis, which step 2's number
 * then counts. `jobLine` is the Job description fold's summary (the skills and the knock-out card's words);
 * `draft` is the tailored score and its base resume's, which step 3's number and step 4's lead card show.
 */
export function useJobSteps(jobId: string, detail: JobDetail | undefined, shown?: ShownAnalysis | null) {
  const application = detail?.application ?? null;
  // Step 2's own query (list only, never scores, the same key): the header shows its best base score.
  const scoreRows = useQuery({
    queryKey: ["ats-scores", jobId],
    queryFn: () => listAtsScores(jobId),
  });
  // Step 2's own query too (the same key): step 2's number counts the open gap analysis and, once the job is
  // tailored, the gaps of the analysis that made the draft.
  const sessions = useQuery({
    queryKey: ["tailoring-sessions", jobId],
    queryFn: () => listTailoringSessions(jobId),
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
  if (!detail) {
    return { scoreRows, sessions, proposalQuery, baseName, scoreShown, standing: null, steps: null, jobLine: null, draft: null };
  }

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
  const skillCount = { total: skills.length, required: skills.filter((s) => s.requirement_level === "required").length };
  const input = jobStepsInput({
    // The rung sits beside `job` on the detail, not in it (JobDetail's `job` has no stage to read).
    rung: detail,
    application,
    scoreRows: scoreRows.data ?? [],
    scoreShown,
    sessions: sessions.data ?? [],
    skills: skillCount,
    countGaps: gapCounts,
    shown,
  });
  const jobLine = jobFacts(
    skillCount,
    knockoutWords(
      detail.knockout?.status ?? null,
      detail.knockout ? knockoutNotChecked(detail.knockout, job) : false,
    ),
  );
  return {
    scoreRows,
    sessions,
    proposalQuery,
    baseName,
    scoreShown,
    standing: { ...standing, text: standingText },
    steps: jobSteps(input),
    jobLine,
    draft: input.draft,
  };
}
