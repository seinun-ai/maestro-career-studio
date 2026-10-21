/**
 * The first run's steps, words and decisions (`/setup`, components/setup/setup-flow.tsx), pure so
 * `node --test` loads it: it imports only types, which the loader erases. Setup stores no progress of its
 * own (docs/entities/others.md, "Setup status"): a step is done when the data it writes is there.
 */
import type {
  CapabilityReport,
  ImportReport,
  MarketOption,
  RecommendedModelsInfo,
  SetupStatus,
} from "./types";

export type SetupStepId = "model" | "resume" | "where" | "answers";

export const SETUP_STEPS: readonly { id: SetupStepId; title: string; time: string }[] = [
  { id: "model", title: "AI model", time: "1 minute" },
  { id: "resume", title: "Your resume", time: "2 minutes" },
  { id: "where", title: "Where and what", time: "1 minute" },
  { id: "answers", title: "Form answers", time: "2 minutes" },
];

/** The autofill profile as Setup reads it: `PUT /api/settings/autofill` takes any JSON object. */
export type AutofillProfile = Record<string, unknown>;

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

/** A yes or no as stored: a boolean from the web app, or "Yes" / "No" as the Companion's pause row types it. */
function yesNo(value: unknown): boolean | undefined {
  if (typeof value === "boolean") return value;
  if (typeof value !== "string") return undefined;
  const word = value.trim().toLowerCase();
  return word === "yes" ? true : word === "no" ? false : undefined;
}

export type PreferenceKey = "notice_period" | "willing_to_relocate";

export function preference(profile: AutofillProfile, key: PreferenceKey): string | boolean | undefined {
  const value = object(profile.preferences)[key];
  if (key === "willing_to_relocate") return yesNo(value);
  return typeof value === "string" ? value : undefined;
}

export type FormQuestion =
  | { kind: "permit"; market: string; label: string; vocab: string | undefined }
  | { kind: "notice" }
  | { kind: "relocate" }
  | { kind: "diversity"; countries: string[] };

/** Step 4, one question at a time: a work permit per country you apply in (named, in its own words), then
 *  notice period and relocation, then diversity only when a country you apply in has a checked set
 *  (`offers_eeo`, from the market list; never decided here). */
export function formQuestions(applyIn: readonly string[], markets: readonly MarketOption[]): FormQuestion[] {
  const byKey = new Map(markets.map((m) => [m.key, m]));
  const permits: FormQuestion[] = applyIn.map((market) => ({
    kind: "permit",
    market,
    label: byKey.get(market)?.label ?? market,
    vocab: byKey.get(market)?.work_auth_vocab,
  }));
  const withSet = applyIn.flatMap((market) => {
    const m = byKey.get(market);
    return m?.offers_eeo ? [m.label] : [];
  });
  const rest: FormQuestion[] = [{ kind: "notice" }, { kind: "relocate" }];
  if (withSet.length > 0) rest.push({ kind: "diversity", countries: [...withSet].sort() });
  return [...permits, ...rest];
}

export type StepsDone = Record<SetupStepId, boolean>;

/** Each step, done from the data it writes: a key, a resume in career history, job preferences, and every
 *  country's work-permit answers, each in its own words (setup status counts them per country, the visa
 *  status where the vocabulary is `us_visa`). */
export function stepsDone(status: SetupStatus, applyIn: readonly string[]): StepsDone {
  const counted = status.autofill.work_auth_by_country;
  return {
    model: status.model_key.done,
    resume: status.import_resumes.done,
    where: status.job_preferences.done,
    answers: applyIn.every((market) => {
      const count = counted[market];
      return count !== undefined && count.answered >= count.answerable;
    }),
  };
}

/** The step Setup opens on: the first not done, else the first (Run setup again). */
export function firstOpenStep(done: StepsDone): number {
  const open = SETUP_STEPS.findIndex((s) => !done[s.id]);
  return open === -1 ? 0 : open;
}

export function progressWords(doneCount: number): string {
  return doneCount === SETUP_STEPS.length ? `All ${doneCount} done` : `${doneCount} of ${SETUP_STEPS.length} done`;
}

/** A brand-new install (no key and no resume) opens Setup once; `seen` is this browser's note that Setup has
 *  been opened, so skipping it never brings it back. */
export function opensSetup(status: SetupStatus, seen: boolean): boolean {
  return !seen && !status.model_key.done && !status.import_resumes.done;
}

export type ModelPlan = {
  /** recommended: the provider's set answers the four roles; own: your picks stay; pick: no set, choose in
   *  Settings; server: your own server's one model does every job. */
  kind: "recommended" | "own" | "pick" | "server";
  /** The model the Test call checks (the Assistant's, the one that needs all three results). */
  test: string | null;
  /** What to send to `PUT /api/settings/models/recommended` once the test passes, or nothing. */
  change: { on: true; provider: string } | { on: false } | null;
};

/**
 * Which models a provider's new key gets. Its recommended set, unless your own picks already run on that
 * provider (then they stay, and a set answering for another provider is turned off so they do). A
 * provider with no set (OpenRouter) keeps your picks and tests one of its own catalog models, if any.
 */
export function modelPlan(
  provider: string,
  rec: RecommendedModelsInfo,
  options: readonly { id: string; provider: string }[],
): ModelPlan {
  const runsOn = (id: string) => options.find((o) => o.id === id)?.provider;
  if (rec.on && rec.active_provider === provider && rec.models) {
    return { kind: "recommended", test: rec.models.assistant, change: null };
  }
  const own = rec.own;
  if ([own.fast, own.smart, own.assistant].every((id) => runsOn(id) === provider)) {
    return { kind: "own", test: own.assistant, change: rec.on ? { on: false } : null };
  }
  const set = rec.sets[provider];
  if (set) return { kind: "recommended", test: set.assistant, change: { on: true, provider } };
  return { kind: "pick", test: options.find((o) => o.provider === provider)?.id ?? null, change: null };
}

/** What a passed test chose for the four jobs, said under its chips. */
export function planWords(plan: ModelPlan, provider: string): string {
  switch (plan.kind) {
    case "recommended":
      return `The recommended ${provider} models are picked for you. Change them in Settings any time.`;
    case "own":
      return "Your own model picks stay. Change them in Settings any time.";
    case "server":
      return `Every job uses ${plan.test} on your server. Change it in Settings any time.`;
    default:
      return `${provider} has no recommended models yet. Pick a model for each job in Settings.`;
  }
}

/** A key passes when the model was reached, wrote, and no result blames the key. */
export function testPassed(report: CapabilityReport, keyProblem: boolean): boolean {
  return !keyProblem && report.reachable !== false && report.text === true;
}

/** "2 base resumes": the import response's counts, only the ones it has, each in its own words. */
export function importCounts(report: ImportReport): { n: number; words: string }[] {
  const out: { n: number; words: string }[] = [];
  const add = (n: number | undefined, one: string, many: string) => {
    if (typeof n === "number" && n > 0) out.push({ n, words: n === 1 ? one : many });
  };
  add(report.bases.length, "base resume", "base resumes");
  const kb = report.kb;
  if (kb) {
    add(kb.entities_created, "new item in your career history", "new items in your career history");
    add(kb.points_approved, "bullet", "bullets");
    add(kb.points_draft, "draft bullet to review", "draft bullets to review");
    add(kb.skills_items_added?.length, "skill", "skills");
  }
  return out;
}
