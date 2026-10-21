/**
 * What Setup's form answers write, in the same terms as Profile (lib/autofill-options.ts: the field table,
 * the per-country work permits, `forSaving`). Every save goes out without the one-set `work_auth` view, so the
 * server keeps the per-country map it is given and a home change can never fold one country's answers into
 * another's. Rendered in components/setup/setup-flow.test.mjs (it imports a module, so `node --test` does not
 * load it bare).
 */
import {
  booleanAnswer,
  declinedEeo,
  forSaving,
  groupCount,
  groupValues,
  isBlank,
  permitCount,
  withField,
  withPermit,
  type Profile,
} from "./autofill-options";
import type { FormQuestion } from "./setup-flow";

/** The profile with one work-permit answer on one country's entry (by market, "UK" never "GB"). */
export function withPermitAnswer(
  profile: Profile,
  market: string,
  key: string,
  value: string | boolean | undefined,
): Profile {
  return forSaving(withPermit(profile, market, key, value));
}

export function withPreference(profile: Profile, key: "notice_period" | "willing_to_relocate", value: string | boolean): Profile {
  return forSaving(withField(profile, "preferences", key, value));
}

/** The profile with one diversity answer (`eeo`), or with the rest declined: every blank question that has a
 *  decline choice (`declinedEeo`; race or ethnicity is typed and stays blank). Only ever sent once the
 *  diversity consent is on record (components/setup/setup-answers-step.tsx). */
export function withDiversityAnswer(profile: Profile, key: string, value: string | boolean | undefined): Profile {
  return forSaving(withField(profile, "eeo", key, value));
}

export function withDiversityDeclined(profile: Profile): Profile {
  return forSaving({ ...profile, eeo: { ...groupValues(profile, "eeo"), ...declinedEeo(profile) } });
}

/** Whether a question holds its answer, for its progress dot: a passed or skipped question is not answered
 *  (round means a state, so a dot never says done for a question you left). */
export function questionAnswered(question: FormQuestion, profile: Profile): boolean {
  switch (question.kind) {
    case "permit": {
      const count = permitCount(profile, question.market, question.vocab);
      return count.answered === count.answerable;
    }
    case "notice":
      return !isBlank(groupValues(profile, "preferences").notice_period);
    case "relocate":
      return booleanAnswer(groupValues(profile, "preferences").willing_to_relocate) !== undefined;
    default: {
      const count = groupCount(profile, "eeo");
      return count.answered === count.answerable;
    }
  }
}
