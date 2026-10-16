/**
 * Step 2's resume pick and the confirm before an action that would replace the job's resume. A job has one
 * application (SYSTEM.md §5): tailoring or using another base resume replaces its resume, so the actions that
 * write ask first, in words that match what the job holds. A pick alone is a preview and never asks.
 * No imports: `node --test` loads this file as it is.
 */

export type PickSession = {
  id?: string;
  base_resume: string;
  status: string;
  created_at: string;
  application_id?: string | null;
};

export type PickApplication = {
  id: string;
  base_resume: string;
  status: string | null;
  customized_json?: unknown;
};

/**
 * The resume step 2 opens on: the newest open gap analysis's resume, else the application's, else the best
 * match. Only a resume in `available` (one with a score row to show) counts, so an archived base falls through.
 */
export function defaultResumePick({
  sessions,
  application,
  best,
  available,
}: {
  sessions: readonly PickSession[];
  application: Pick<PickApplication, "base_resume"> | null;
  best: string | null;
  available: readonly string[];
}): string | null {
  const shown = new Set(available);
  const newestOpen = sessions
    .filter((s) => s.status === "open" && shown.has(s.base_resume))
    .reduce<PickSession | null>((newest, s) => (!newest || s.created_at > newest.created_at ? s : newest), null);
  if (newestOpen) return newestOpen.base_resume;
  if (application && shown.has(application.base_resume)) return application.base_resume;
  return best != null && shown.has(best) ? best : (available[0] ?? null);
}

/** What the job's resume is: applied with, a tailored draft, the base used as is, or nothing to replace. */
export type JobResumeState = "applied" | "tailored" | "as_is" | null;

/**
 * Applied when the application's status is past Draft. Tailored when a `tailored` gap analysis made it (its
 * `application_id`, or one for the application's base). A draft with a resume and no tailored analysis was used
 * as is. A draft with no resume yet holds nothing to replace.
 */
export function jobResumeState(
  application: PickApplication | null,
  sessions: readonly PickSession[],
): JobResumeState {
  if (!application) return null;
  if (application.status != null && application.status !== "draft") return "applied";
  const tailored = sessions.some(
    (s) =>
      s.status === "tailored" &&
      (s.application_id === application.id || s.base_resume === application.base_resume),
  );
  if (tailored) return "tailored";
  return application.customized_json ? "as_is" : null;
}

/** The action a switch confirm guards: its label names it. */
export type SwitchAction = "analyze" | "continue" | "as_is";

const CONFIRM_LABELS: Record<SwitchAction, string> = {
  analyze: "Switch and analyze gaps",
  continue: "Switch and continue",
  as_is: "Switch and use as is",
};

/**
 * The confirm before acting on `to` while the job's resume came from `from` (names, not slugs). Null when
 * nothing would be replaced: no application, the same resume, or a draft with no resume yet.
 */
export function switchConfirm({
  state,
  from,
  to,
  fromSlug,
  toSlug,
  action,
}: {
  state: JobResumeState;
  from: string;
  to: string;
  fromSlug: string;
  toSlug: string;
  action: SwitchAction;
}): { title: string; description: string; confirmLabel: string } | null {
  if (state == null || fromSlug === toSlug) return null;
  // Use resume as is does not tailor: the sentence names what it does.
  const doing = action === "as_is" ? "Using another resume as is" : "Tailoring with another resume";
  const description =
    state === "applied"
      ? `You applied with ${from}. ${doing} replaces that resume and its PDF. Version history keeps them.`
      : state === "tailored"
        ? `This job already has a tailored ${from} resume. ${doing} replaces that draft and removes its PDF. ` +
          `Version history keeps the old one. Answers you gave in the gaps for ${from} stay with it.`
        : `This job's resume is ${from}, used as is. ${doing} replaces it and removes its PDF. ` +
          "Version history keeps the old one.";
  return { title: `Switch to ${to}?`, description, confirmLabel: CONFIRM_LABELS[action] };
}
