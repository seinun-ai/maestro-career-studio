/**
 * What Setup's form answers write, in the same terms as Profile (lib/autofill-options.ts: the served questions,
 * the per-country work permits, `forSaving`). Every save goes out without the one-set `work_auth` view, so the
 * server keeps the per-country map it is given and a home change can never fold one country's answers into
 * another's. Rendered in components/setup/setup-flow.test.mjs (it imports a module, so `node --test` does not
 * load it bare).
 */
import {
  answered,
  answeredIn,
  booleanAnswer,
  citizenshipAnswered,
  citizenshipIsLoose,
  declinedEeo,
  derivedPermits,
  forSaving,
  groupCount,
  groupFields,
  groupValues,
  permitAnswered,
  permitEntry,
  permitQuestions,
  withCitizenshipList,
  withCitizenships,
  withField,
  withPermit,
  type CountryCodes,
  type FieldDef,
  type Profile,
} from "./autofill-options";
import type { FormQuestion, PreferenceKey } from "./setup-flow";
import type { QuestionSet } from "./types";

/** The profile with these citizenships (ISO codes, from the picker). The save reads the questions again, so
 *  what they settle (`derived`) is served before Continue moves on. */
export function withCitizenshipAnswer(profile: Profile, codes: readonly string[]): Profile {
  return forSaving(withCitizenships(profile, codes));
}

/** The profile with a loose citizenship stored as codes (`withCitizenshipList`): what Continue does first, on
 *  the citizenship question, before it moves on. */
export function withCitizenshipListed(profile: Profile, codes: CountryCodes | null): Profile {
  return forSaving(withCitizenshipList(profile, codes));
}

/** What a press of Setup's Continue or Next up's Next does on the citizenship question (`citizenshipNext`). */
export type CitizenshipNext = "store" | "wait" | "move on";

/**
 * On the citizenship question, Setup's Continue and Next up's Next: "store" a citizenship not held as codes
 * (`citizenshipIsLoose`: a plain string, a name, an alias) as codes first; "wait" while a save is on its way,
 * since it reads the questions again and the next question must never be a permit the citizenship is about to
 * settle; else "move on". A press that stores or waits is remembered, and moves on once the save lands (not
 * when it failed: Not saved says so, and the button is there to press again).
 */
export function citizenshipNext(profile: Profile, codes: CountryCodes | null, pending: boolean): CitizenshipNext {
  if (citizenshipIsLoose(profile, codes)) return "store";
  return pending ? "wait" : "move on";
}

/**
 * The work-permit questions one country's card asks: its required ones that your citizenship does not settle
 * (`derivedPermits`, read as the answers now stand) and that were not answered when Setup opened (`opened`).
 * One you answer here stays on its card with your answer, so Back finds it; optional ones (an expiry, a status
 * list outside the US, the country's own answers) are left to Profile.
 */
export function permitAsks(profile: Profile, questionSet: QuestionSet, market: string, opened: Profile): FieldDef[] {
  const derived = derivedPermits(profile, questionSet, market);
  const before = permitEntry(opened, market);
  return permitQuestions(questionSet, market).filter(
    (field) => !(field.key in derived) && !answered(field, before[field.key]),
  );
}

/** The questions Setup asks, in order: `formQuestions` less each country's card with nothing to ask
 *  (`permitAsks`): one your citizenship settles, or one answered before Setup opened, is passed. */
export function questionsToAsk(
  questions: readonly FormQuestion[],
  profile: Profile,
  questionSet: QuestionSet,
  opened: Profile,
): FormQuestion[] {
  return questions.filter(
    (question) => question.kind !== "permit" || permitAsks(profile, questionSet, question.market, opened).length > 0,
  );
}

/** The profile with one work-permit answer on one country's entry (by market, "UK" never "GB"); an answer
 *  that hides another of its fields removes it (`withPermit`). */
export function withPermitAnswer(
  profile: Profile,
  questionSet: QuestionSet,
  market: string,
  key: string,
  value: string | boolean | undefined,
): Profile {
  return forSaving(withPermit(profile, questionSet, market, key, value));
}

/** The profile with one of the Start and pay answers Setup asks: notice in days (a choice's 0, 14, 30 or 90, or
 *  the digits typed into the box; undefined, a cleared box, removes it) or relocation. Once an answer is given,
 *  the older answer it replaces (the served field's `legacy`: notice in words) leaves the held answers, so the
 *  autosave never sends that text again (the server drops it too, since days given win). */
export function withPreference(
  profile: Profile,
  questionSet: QuestionSet,
  key: PreferenceKey,
  value: string | number | boolean | undefined,
): Profile {
  const next = withField(profile, questionSet, "preferences", key, value);
  const field = groupFields(questionSet, "preferences").find((f) => f.key === key);
  if (!field?.legacy || !answered(field, value)) return forSaving(next);
  const { [field.legacy]: _older, ...preferences } = groupValues(next, "preferences");
  void _older;
  return forSaving({ ...next, preferences });
}

/** The profile with one diversity answer (`eeo`), or with the rest declined: every blank question that has a
 *  decline choice (`declinedEeo`; race or ethnicity is typed and stays blank). Only ever sent once the
 *  diversity consent is on record (components/setup/setup-answers-step.tsx). */
export function withDiversityAnswer(
  profile: Profile,
  questionSet: QuestionSet,
  key: string,
  value: string | boolean | undefined,
): Profile {
  return forSaving(withField(profile, questionSet, "eeo", key, value));
}

export function withDiversityDeclined(profile: Profile, questionSet: QuestionSet): Profile {
  return forSaving({ ...profile, eeo: { ...groupValues(profile, "eeo"), ...declinedEeo(profile, questionSet) } });
}

/** Notice, as served: one answer in days (`notice_days`) for everyone, whose older words (`legacy`) still answer
 *  it. Setup's notice question asks it. */
export function noticeField(questionSet: QuestionSet): FieldDef | undefined {
  return groupFields(questionSet, "preferences").find((field) => field.key === "notice_days");
}

/** Whether a question holds its answer, for its progress dot: a passed or skipped question is not answered
 *  (round means a state, so a dot never says done for a question you left). */
export function questionAnswered(
  question: FormQuestion,
  profile: Profile,
  questionSet: QuestionSet,
  codes: CountryCodes | null = null,
): boolean {
  switch (question.kind) {
    case "citizenship":
      return citizenshipAnswered(profile, questionSet, codes);
    case "permit":
      return permitAnswered(profile, questionSet, question.market);
    case "notice": {
      // Days given, 0 included, or older words the server could not read as days (`answeredIn`, as readiness).
      const field = noticeField(questionSet);
      return field !== undefined && answeredIn(field, groupValues(profile, "preferences"));
    }
    case "relocate":
      return booleanAnswer(groupValues(profile, "preferences").willing_to_relocate) !== undefined;
    default: {
      const count = groupCount(profile, questionSet, "eeo");
      return count.answered === count.answerable;
    }
  }
}
