"use client";

import { AnswerList } from "@/components/profile/answer-list";
import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { TileCard, type TileView } from "@/components/profile/tile";
import { useAutofillQuery } from "@/components/profile/use-autofill-query";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EDUCATION_FIELDS, educationList, isBlank, type EducationEntry } from "@/lib/autofill-options";

const SURFACE = "education";

/** Education: each school, most recent first, as forms ask it. Saves as you go. */
export function useEducationTile(): TileView {
  const { profile } = useAutofillProfile();
  const education = educationList(profile);
  const named = education
    .map((entry) => [entry.degree, entry.discipline].filter((v) => !isBlank(v)).join(" ") || entry.school || "")
    .filter((words) => !isBlank(words));
  return {
    state: { kind: "count", text: education.length === 1 ? "1 school" : `${education.length} schools` },
    summary: <span className="line-clamp-2">{named.length ? named.join(" · ") : "None added"}</span>,
    note: "Most recent first",
    panel: <EducationCard />,
  };
}

function EducationCard() {
  const query = useAutofillQuery();
  return (
    <TileCard tile="education" errorTitle="Couldn't load your form answers." query={query}>
      {() => <EducationEditor />}
    </TileCard>
  );
}

function EducationEditor() {
  const { profile, update } = useAutofillProfile();
  const education = educationList(profile);
  const setEducation = (next: EducationEntry[]) =>
    update(SURFACE, (current) => ({ ...current, education: next }));

  return (
    <AnswerList
      surface={SURFACE}
      entries={education}
      setEntries={setEducation}
      intro={<p className="text-muted-foreground text-body-small">Most recent first.</p>}
      boxed
      removeLabel={(i) => `Remove school ${i + 1}`}
      addLabel="Add education"
      newEntry={() => ({})}
    >
      {(entry, i, change) => (
        <div className="grid flex-1 gap-4 @xl/setting:grid-cols-3">
          {EDUCATION_FIELDS.map((field) => {
            const id = `af-education-${i}-${field.key}`;
            return (
              <div key={field.key} className="grid gap-1.5">
                <Label htmlFor={id}>{field.label}</Label>
                <Input
                  id={id}
                  className="h-8 text-body-medium"
                  value={entry[field.key] ?? ""}
                  onChange={(e) => change({ ...entry, [field.key]: e.target.value })}
                />
              </div>
            );
          })}
        </div>
      )}
    </AnswerList>
  );
}
