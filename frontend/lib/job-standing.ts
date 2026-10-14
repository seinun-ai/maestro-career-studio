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

/**
 * "Where this stands", the line under the header. Applied: when, and with which resume. A draft: not
 * applied, and the best base resume. No application: not applied yet. A job counts as applied when its
 * application is in a submitted stage or carries an applied date (a rejection or withdrawal keeps it). `appliedOn` is the date in words, formatted by the caller.
 */
export function standingLine(args: {
  application: StandingApplication | null;
  appliedOn: string | null;
  /** The application's resume, named. */
  resumeName: string | null;
  bestBase: { name: string; value: number } | null;
  hasFilledAnswers: boolean;
}): Standing {
  const { application, appliedOn, bestBase, hasFilledAnswers } = args;
  const best = bestBase ? ` · best resume ${bestBase.name} ${bestBase.value.toFixed(1)}` : "";
  if (application && (application.applied_at || SUBMITTED_STAGES.includes(application.status ?? ""))) {
    const name = args.resumeName?.trim();
    const text = ["Applied", appliedOn, name ? `with ${name} resume` : null].filter(Boolean).join(" ");
    return { kind: "applied", text, pdf: Boolean(application.pdf_path), submitted: hasFilledAnswers };
  }
  if (application) {
    return { kind: "draft", text: `Not applied${best}`, pdf: false, submitted: hasFilledAnswers };
  }
  return { kind: "none", text: `Not applied yet${best}`, pdf: false, submitted: hasFilledAnswers };
}
