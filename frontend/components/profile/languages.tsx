"use client";

import { AnswerList } from "@/components/profile/answer-list";
import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { FieldControl } from "@/components/profile/field-control";
import { TileCard, type TileView } from "@/components/profile/tile";
import { useAutofillQuery } from "@/components/profile/use-autofill-query";
import { Label } from "@/components/ui/label";
import {
  booleanAnswer,
  fieldHint,
  isBlank,
  languageFields,
  languageValue,
  withAnswer,
  type LanguageEntry,
} from "@/lib/autofill-options";
import type { QuestionSet } from "@/lib/types";

const SURFACE = "languages";

/** "German · native", "English · Fluent · C1": the language, the one level that says the most, and its CEFR
 *  level when set. */
function languageWords(entry: LanguageEntry): string | null {
  if (isBlank(entry.language)) return null;
  const level = booleanAnswer(entry.native) ? "native" : booleanAnswer(entry.fluent) ? "fluent" : entry.speak;
  return [entry.language, level, entry.cefr].filter((part) => !isBlank(part)).join(" · ");
}

/** Languages: one entry per language, most important first, with the levels forms offer, and the CEFR level
 *  where a country you apply in asks it (the served `language_fields`). Saves as you go. */
export function useLanguagesTile(questionSet: QuestionSet): TileView {
  const { profile } = useAutofillProfile();
  const languages: LanguageEntry[] = Array.isArray(profile.languages) ? profile.languages : [];
  const words = languages.map(languageWords).filter((w): w is string => w !== null);
  return {
    state: { kind: "count", text: languages.length === 1 ? "1 language" : `${languages.length} languages` },
    summary: words.length ? (
      <span className="flex flex-wrap gap-1.5">
        {words.map((w, i) => (
          <span key={i} className="rounded-full bg-surface-container px-2 py-0.5 text-label-medium text-foreground">
            {w}
          </span>
        ))}
      </span>
    ) : (
      <span>None added</span>
    ),
    note: "The first four go on forms",
    panel: <LanguagesCard questionSet={questionSet} />,
  };
}

function LanguagesCard({ questionSet }: { questionSet: QuestionSet }) {
  const query = useAutofillQuery();
  return (
    <TileCard tile="languages" errorTitle="Couldn't load your form answers." query={query}>
      {() => <LanguagesEditor questionSet={questionSet} />}
    </TileCard>
  );
}

function LanguagesEditor({ questionSet }: { questionSet: QuestionSet }) {
  const { profile, update } = useAutofillProfile();
  const languages: LanguageEntry[] = Array.isArray(profile.languages) ? profile.languages : [];
  const setLanguages = (next: LanguageEntry[]) =>
    update(SURFACE, (current) => ({ ...current, languages: next }));

  return (
    <AnswerList
      surface={SURFACE}
      entries={languages}
      setEntries={setLanguages}
      intro={
        <p className="text-muted-foreground text-body-small">
          Most important first. The first four are used, and the Companion adds a
          language to a form only when its reading, speaking and writing levels are all set.
        </p>
      }
      boxed
      removeLabel={(i) => `Remove language ${i + 1}`}
      addLabel="Add language"
      newEntry={() => ({})}
    >
      {(entry, i, change) => (
        <div className="grid flex-1 items-end gap-4 @xl/setting:grid-cols-3">
          {languageFields(questionSet).map((field) => {
            const id = `af-languages-${i}-${field.key}`;
            // The CEFR level says which countries' forms ask it (`askedBy`), read with its control.
            const hint = fieldHint(field);
            const hintId = hint ? `${id}-hint` : undefined;
            return (
              <div key={field.key} className="grid gap-1.5">
                <Label htmlFor={id}>{field.label}</Label>
                {hint ? (
                  <p id={hintId} className="text-muted-foreground text-body-small">
                    {hint}
                  </p>
                ) : null}
                <FieldControl
                  id={id}
                  group="language"
                  field={field}
                  value={languageValue(field, (entry as Record<string, unknown>)[field.key])}
                  hintId={hintId}
                  onChange={(next) => change(withAnswer(entry, field.key, next))}
                />
              </div>
            );
          })}
        </div>
      )}
    </AnswerList>
  );
}
