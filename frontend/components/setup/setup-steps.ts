import type { SetupStatus } from "@/lib/types";

export type SetupAction =
  | { kind: "navigate"; href: string }
  | { kind: "dialog"; dialog: "upload" }
  | { kind: "focus"; anchor: string };

export type SetupStepView = {
  id:
    | "model_key"
    | "import"
    | "autofill"
    | "job_preferences"
    | "persona"
    | "template";
  /** Pill text — short. */
  label: string;
  /** Card row title — a full imperative phrase. */
  title: string;
  detail?: string;
  done: boolean;
  /** Route this step's answer lives on. */
  home: string;
  /** Element id within `home`. */
  anchor: string;
  action: SetupAction;
};

function detailNumber(detail: Record<string, unknown>, key: string): number {
  const value = detail[key];
  return typeof value === "number" ? value : 0;
}

function detailString(
  detail: Record<string, unknown>,
  key: string,
): string | null {
  const value = detail[key];
  return typeof value === "string" ? value : null;
}

/** Human label for an autofill group. */
const GROUP_LABELS: Record<string, string> = {
  personal: "personal details",
  work_auth: "work authorization",
  eeo: "voluntary disclosures",
  preferences: "preferences",
};

/**
 * The autofill group to send the user to.
 *
 * `blocking` only ever names work authorization — the knockout answers the
 * extension reports missing_source on — so it is the right target when set.
 * But a profile can sit below 100% with work auth complete and, say, one
 * preference unanswered; `blocking` is empty there, and aiming at the section
 * as a whole would make the user hunt for the gap. Fall back to the first group
 * that is actually short.
 */
function autofillTarget(autofill: SetupStatus["autofill"]): string | null {
  if (autofill.blocking.length) return autofill.blocking[0];
  const short = Object.entries(autofill.groups).find(
    ([, g]) => g.answered < g.answerable,
  );
  return short ? short[0] : null;
}

/**
 * The single source of truth for the five setup steps.
 *
 * Both the compact pill strip and the expanded getting-started card render from
 * this. Neither owns a step list — that is exactly how the two drifted apart,
 * leaving the strip as a degraded copy of the card.
 *
 * `action` resolves against the CURRENT route: a step whose answer already
 * lives on the page you are on focuses in place instead of navigating, because
 * bouncing the user to /profile to answer a question that is already on
 * /profile is the friction this feature exists to remove.
 */
export function buildSetupSteps(
  status: SetupStatus,
  pathname: string,
): SetupStepView[] {
  const readiness = Math.round(status.autofill.readiness * 100);
  const target = autofillTarget(status.autofill);
  const targetLabel = target ? (GROUP_LABELS[target] ?? target) : "";
  const defaultOrigin = detailString(status.template.detail, "default_origin");
  const defaultTemplate = detailString(
    status.template.detail,
    "default_template_id",
  );
  // "seed" is the shipped starter; absent means no template at all yet.
  const starterDefault = defaultOrigin === null || defaultOrigin === "seed";

  const steps: Omit<SetupStepView, "action">[] = [
    {
      id: "model_key",
      label: "API key",
      title: "Add a provider API key",
      detail: "Nothing extracts, tailors or chats without one.",
      done: status.model_key.done,
      home: "/settings",
      anchor: "api-keys",
    },
    {
      id: "import",
      label: "Import resumes",
      title: "Import your resumes",
      detail: `${detailNumber(status.import_resumes.detail, "base_resumes")} base resumes · ${detailNumber(status.import_resumes.detail, "kb_entities")} KB entries`,
      done: status.import_resumes.done,
      home: "/career",
      anchor: "kb-entities",
    },
    {
      id: "autofill",
      label: targetLabel
        ? `Autofill ${readiness}% · ${targetLabel}`
        : `Autofill ${readiness}%`,
      title: "Complete autofill",
      detail: targetLabel
        ? `Readiness ${readiness}% — ${targetLabel} incomplete`
        : `Readiness ${readiness}%`,
      done: status.autofill.done,
      home: "/profile",
      // Aim at the group with the gap, not the section, so the user lands on
      // the actual unanswered question.
      anchor: target ? `autofill-${target}` : "autofill",
    },
    {
      id: "job_preferences",
      label: "Job preferences",
      title: "Set job preferences",
      done: status.job_preferences.done,
      home: "/profile",
      anchor: "job-preferences",
    },
    {
      id: "persona",
      label: "Persona",
      title: "Write your persona",
      done: status.persona.done,
      home: "/profile",
      anchor: "persona",
    },
    {
      id: "template",
      label: "Template",
      title: "Choose your default template",
      detail: starterDefault
        ? "Using the starter template"
        : `Default: ${defaultTemplate ?? "set"}`,
      done: status.template.done,
      home: "/templates",
      anchor: "template-gallery",
    },
  ];

  return steps.map((step) => ({
    ...step,
    action:
      step.id === "import"
        ? { kind: "dialog", dialog: "upload" }
        : pathname === step.home
          ? { kind: "focus", anchor: step.anchor }
          : { kind: "navigate", href: `${step.home}#${step.anchor}` },
  }));
}
