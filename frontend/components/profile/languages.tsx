"use client";

import { useRef } from "react";
import { Plus } from "lucide-react";

import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { FieldControl } from "@/components/profile/field-control";
import { TileCard, type TileView } from "@/components/profile/tile";
import { useAutofillQuery } from "@/components/profile/use-autofill-query";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCardAction } from "@/components/settings/setting-card";
import { RemoveButton } from "@/components/settings/setting-layout";
import { Button } from "@/components/ui/button";
import { CardSection } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { useFocusOnNextCommit } from "@/hooks/use-focus-return";
import {
  LANGUAGE_FIELDS,
  booleanAnswer,
  isBlank,
  languageValue,
  withAnswer,
  type LanguageEntry,
} from "@/lib/autofill-options";

const SURFACE = "languages";

/** "German · native", "English · Fluent": the language and the one level that says the most. */
function languageWords(entry: LanguageEntry): string | null {
  if (isBlank(entry.language)) return null;
  const level = booleanAnswer(entry.native) ? "native" : booleanAnswer(entry.fluent) ? "fluent" : entry.speak;
  return level ? `${entry.language} · ${level}` : String(entry.language);
}

/** Languages: one entry per language, most important first, with the levels forms offer. Saves as you go. */
export function useLanguagesTile(): TileView {
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
    panel: <LanguagesCard />,
  };
}

function LanguagesCard() {
  const query = useAutofillQuery();
  return (
    <TileCard tile="languages" errorTitle="Couldn't load your form answers." query={query}>
      {() => <LanguagesEditor />}
    </TileCard>
  );
}

function LanguagesEditor() {
  const { profile, update, saveState } = useAutofillProfile();
  const languages: LanguageEntry[] = Array.isArray(profile.languages) ? profile.languages : [];
  const setLanguages = (next: LanguageEntry[]) =>
    update(SURFACE, (current) => ({ ...current, languages: next }));
  // A removed language takes its focused Remove with it; focus goes to Add language below the list.
  const armFocus = useFocusOnNextCommit();
  const addLanguageRef = useRef<HTMLButtonElement>(null);

  return (
    <div className="grid gap-4">
      <SettingCardAction>
        <AutosaveStatus {...saveState(SURFACE)} />
      </SettingCardAction>
      <p className="text-muted-foreground text-body-small">
        Most important first. The first four are used, and the Companion adds a
        language to a form only when its reading, speaking and writing levels are all set.
      </p>
      {languages.map((entry, i) => (
        <CardSection key={i} className="flex items-start gap-2">
          <div className="grid flex-1 items-end gap-4 @xl/setting:grid-cols-3">
            {LANGUAGE_FIELDS.map((field) => {
              const id = `af-languages-${i}-${field.key}`;
              return (
                <div key={field.key} className="grid gap-1.5">
                  <Label htmlFor={id}>{field.label}</Label>
                  <FieldControl
                    id={id}
                    group="language"
                    field={field}
                    value={languageValue(field, entry[field.key as keyof LanguageEntry])}
                    onChange={(next) =>
                      setLanguages(
                        languages.map((entry2, j) =>
                          j === i ? withAnswer(entry2, field.key, next) : entry2,
                        ),
                      )
                    }
                  />
                </div>
              );
            })}
          </div>
          <RemoveButton
            label={`Remove language ${i + 1}`}
            onClick={() => {
              setLanguages(languages.filter((_, j) => j !== i));
              armFocus(addLanguageRef);
            }}
          />
        </CardSection>
      ))}
      <div>
        <Button
          ref={addLanguageRef}
          variant="outline"
          size="sm"
          onClick={() => setLanguages([...languages, {}])}
        >
          <Plus className="size-4" />
          Add language
        </Button>
      </div>
    </div>
  );
}
