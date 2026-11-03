"use client";

import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { FieldGrid } from "@/components/profile/field-control";
import { TileCard, type TileView } from "@/components/profile/tile";
import { useAutofillQuery } from "@/components/profile/use-autofill-query";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCardAction } from "@/components/settings/setting-card";
import { answeredIn, groupCount, groupFields, groupValues, legacyNote, withField } from "@/lib/autofill-options";
import type { QuestionSet } from "@/lib/types";

const SURFACE = "start";

/** Start and pay: notice period in days, start date, relocation and how you heard, from the profile's
 *  `preferences`, and the desired salary while no country's set asks the pay of where you live (Country answers
 *  asks it once you apply there). Counted and listed missing by one rule (`answeredIn`), so notice in older
 *  words is set, and its hint says what forms get until days are given (`legacyNote`). Saves as you go. */
export function useStartTile(questionSet: QuestionSet): TileView {
  const { profile } = useAutofillProfile();
  const count = groupCount(profile, questionSet, "preferences");
  const values = groupValues(profile, "preferences");
  const missing = groupFields(questionSet, "preferences")
    .filter((field) => !field.optional && !answeredIn(field, values))
    .map((field) => field.label.replace(/\?$/, "").toLowerCase());
  return {
    state: count.answered === count.answerable ? { kind: "ready" } : { kind: "needs" },
    summary: (
      <span className="line-clamp-2">
        {missing.length === 0
          ? "Every answer set"
          : `${count.answered} of ${count.answerable} set · ${missing.join(", ")} missing`}
      </span>
    ),
    note: "Asked on most applications",
    panel: <StartCard questionSet={questionSet} />,
  };
}

function StartCard({ questionSet }: { questionSet: QuestionSet }) {
  const query = useAutofillQuery();
  return (
    <TileCard
      tile="start"
      description="When you can start, and what forms ask with it."
      errorTitle="Couldn't load your form answers."
      query={query}
    >
      {() => <StartEditor questionSet={questionSet} />}
    </TileCard>
  );
}

function StartEditor({ questionSet }: { questionSet: QuestionSet }) {
  const { profile, update, saveState } = useAutofillProfile();
  const fields = groupFields(questionSet, "preferences");
  const values = groupValues(profile, "preferences");
  // While notice is in older words only, its hint says forms get them until days are given.
  const hints = Object.fromEntries(
    fields.flatMap((field) => {
      const note = legacyNote(field, values);
      return note ? [[field.key, note]] : [];
    }),
  );
  return (
    <div className="grid gap-4">
      <SettingCardAction>
        <AutosaveStatus {...saveState(SURFACE)} />
      </SettingCardAction>
      <FieldGrid
        idPrefix="af-preferences"
        group="preferences"
        fields={fields}
        values={values}
        hints={hints}
        onChange={(key, next) => update(SURFACE, (current) => withField(current, questionSet, "preferences", key, next))}
      />
    </div>
  );
}
