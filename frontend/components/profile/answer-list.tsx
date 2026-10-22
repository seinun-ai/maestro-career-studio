"use client";

import { useRef, type ReactNode } from "react";
import { Plus } from "lucide-react";

import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCardAction } from "@/components/settings/setting-card";
import { RemoveButton } from "@/components/settings/setting-layout";
import { Button } from "@/components/ui/button";
import { CardSection } from "@/components/ui/card";
import { useFocusOnNextCommit } from "@/hooks/use-focus-return";

/**
 * A Profile tile's list of answers (Education, Languages, Your own questions), saved as you go under
 * `surface`: the save status in the card header, `intro`, each entry's fields beside a Remove named for that
 * entry, then Add. A removed entry takes its focused Remove with it; focus goes to Add below the list.
 */
export function AnswerList<Entry>({
  surface,
  entries,
  setEntries,
  intro,
  boxed = false,
  removeLabel,
  addLabel,
  newEntry,
  children: fields,
}: {
  surface: string;
  entries: Entry[];
  setEntries: (next: Entry[]) => void;
  intro?: ReactNode;
  /** Each entry in its own tinted section. */
  boxed?: boolean;
  removeLabel: (i: number) => string;
  addLabel: string;
  /** A blank entry (the list's own type decides `Entry`, not this). */
  newEntry: () => NoInfer<Entry>;
  /** One entry's fields; `change` replaces that entry in the list. */
  children: (entry: Entry, i: number, change: (next: Entry) => void) => ReactNode;
}) {
  const { saveState } = useAutofillProfile();
  const armFocus = useFocusOnNextCommit();
  const addRef = useRef<HTMLButtonElement>(null);
  const Row = boxed ? CardSection : "div";

  return (
    <div className="grid gap-4">
      <SettingCardAction>
        <AutosaveStatus {...saveState(surface)} />
      </SettingCardAction>
      {intro}
      {entries.map((entry, i) => (
        <Row key={i} className="flex items-start gap-2">
          {fields(entry, i, (next) => setEntries(entries.map((other, j) => (j === i ? next : other))))}
          <RemoveButton
            label={removeLabel(i)}
            onClick={() => {
              setEntries(entries.filter((_, j) => j !== i));
              armFocus(addRef);
            }}
          />
        </Row>
      ))}
      <div>
        <Button ref={addRef} variant="outline" size="sm" onClick={() => setEntries([...entries, newEntry()])}>
          <Plus className="size-4" />
          {addLabel}
        </Button>
      </div>
    </div>
  );
}
