// What the job page says first: the score pill and the "where this stands" line. Pure, so `node --test`
// loads it (no imports).

type ScoreRow = {
  phase: string;
  target_id: string;
  composite: number;
  application_id: string | null;
  created_at: string;
};

export type ScorePill = {
  /** "Resume match" for the application's tailored score, "Best base resume" for the best base score. */
  label: "Resume match" | "Best base resume";
  value: number;
  /** The base resume's id for a base score; the application's for a tailored one. */
  targetId: string;
  tailored: boolean;
};

/**
 * The header's one score. The application's newest tailored score when there is one ("Resume match N
 * (tailored)"), else the best base score ("Best base resume N"); null when neither exists.
 */
export function scorePill(scores: readonly ScoreRow[], applicationId: string | null): ScorePill | null {
  const tailored = applicationId
    ? scores
        .filter((s) => s.phase === "tailored" && s.application_id === applicationId)
        .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0]
    : undefined;
  if (tailored) {
    return { label: "Resume match", value: tailored.composite, targetId: tailored.target_id, tailored: true };
  }
  const best = scores.filter((s) => s.phase === "base").sort((a, b) => b.composite - a.composite)[0];
  return best ? { label: "Best base resume", value: best.composite, targetId: best.target_id, tailored: false } : null;
}

/** The statuses that mean the application went out (backend `application_status.SUBMITTED_STAGES`). */
const SUBMITTED_STAGES = ["applied", "interviewing", "offered", "accepted"];

type StandingApplication = {
  status: string | null;
  applied_at: string | null;
  pdf_path: string | null;
};

export type Standing = {
  kind: "applied" | "draft" | "none";
  text: string;
  /** Offer View PDF (the application has one). */
  pdf: boolean;
  /** Offer What was submitted (something was filled into the job's form). */
  submitted: boolean;
};

/** Where an open proposal stands, in words. */
const OPEN_PROPOSAL: Record<string, string> = {
  pending_review: "waiting for your review in the Agent inbox",
  accepted: "queued for your agent",
  approved: "your agent is applying",
  needs_decision: "your agent needs you (below)",
  needs_human: "your agent needs you (below)",
  submission_uncertain: "your agent isn't sure it went through: check the Agent inbox",
};

/**
 * "Where this stands", the line under the header. Applied: when, and with which resume (named, with no score:
 * the header's pill has it). A draft: not applied, its resume, and where its open proposal is. No application:
 * not applied yet. A job counts as applied when its application is in a submitted stage or carries an applied
 * date (a rejection or withdrawal keeps it), or, with no application, when its proposal records that it went out (`status`
 * "submitted"; `yourself`: you applied outside the agent, the History lane's Applied yourself). The dates are
 * in words, formatted by the caller.
 */
export function standingLine(args: {
  application: StandingApplication | null;
  appliedOn: string | null;
  /** The application's resume, named. */
  resumeName: string | null;
  /** A tailored score exists for the application. */
  tailored: boolean;
  hasFilledAnswers: boolean;
  /** The newest proposal: its status as History reads it, and the day it last changed. */
  proposal: { status: string; yourself: boolean; on: string | null } | null;
}): Standing {
  const { application, appliedOn, hasFilledAnswers, proposal } = args;
  const name = args.resumeName?.trim();
  const resume = name ? `${name} resume${args.tailored ? ", tailored" : ""}` : null;
  const pdf = Boolean(application?.pdf_path);
  const sent = application && (application.applied_at || SUBMITTED_STAGES.includes(application.status ?? ""));
  if (sent) {
    const text = ["Applied", appliedOn, resume ? `with ${resume}` : null].filter(Boolean).join(" ");
    return { kind: "applied", text, pdf, submitted: hasFilledAnswers };
  }
  // With an application the application decides: one set back to Draft is not applied, whatever its old proposal says.
  if (!application && proposal?.status === "submitted") {
    const text = [proposal.yourself ? "Applied yourself" : "Applied", proposal.on].filter(Boolean).join(" ");
    return { kind: "applied", text, pdf, submitted: hasFilledAnswers };
  }
  if (application) {
    const open = proposal ? OPEN_PROPOSAL[proposal.status] : undefined;
    const text = `Not applied${open ? ` · ${open}` : resume ? ` · ${resume}` : ""}`;
    return { kind: "draft", text, pdf: false, submitted: hasFilledAnswers };
  }
  return { kind: "none", text: "Not applied yet", pdf: false, submitted: hasFilledAnswers };
}

/**
 * The Jobs row's date beside its status chip. Applied reads the applied date (you can set it; it is when you
 * applied). Any other status reads when it began, the status log's newest change into it (`status_since`, "Since
 * Oct 3"). A status older than the log falls back to the applied date the server has; with neither, nothing, and a
 * draft never. The date stays as sent: the caller formats it.
 */
export function statusDate(app: {
  status: string | null;
  applied_at: string | null;
  status_since?: string | null;
}): { at: string; word: "Applied" | "Since" } | null {
  if (!app.status || app.status === "draft") return null;
  if (app.status === "applied" && app.applied_at) return { at: app.applied_at, word: "Applied" };
  if (app.status_since) return { at: app.status_since, word: "Since" };
  return app.applied_at ? { at: app.applied_at, word: "Applied" } : null;
}
