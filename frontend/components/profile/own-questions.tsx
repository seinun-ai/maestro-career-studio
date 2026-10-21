"use client";

import { useRef } from "react";
import { Plus } from "lucide-react";

import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { TileCard, type TileView } from "@/components/profile/tile";
import { useAutofillQuery } from "@/components/profile/use-autofill-query";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { SettingCardAction } from "@/components/settings/setting-card";
import { RemoveButton } from "@/components/settings/setting-layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useFocusOnNextCommit } from "@/hooks/use-focus-return";
import { CUSTOM_IN_USE, isBlank, type CustomQA } from "@/lib/autofill-options";

const SURFACE = "questions";

/** Your own questions: the questions you get often, with your usual answers. Saves as you go. */
export function useQuestionsTile(): TileView {
  const { profile } = useAutofillProfile();
  const custom: CustomQA[] = Array.isArray(profile.custom) ? profile.custom : [];
  const asked = custom.map((qa) => qa.question).filter((q) => !isBlank(q));
  return {
    state: { kind: "count", text: `${custom.length} saved` },
    summary: (
      <span className="line-clamp-2">{asked.length ? asked.slice(0, 2).map((q) => `“${q}”`).join(" · ") : "None saved"}</span>
    ),
    note: "Reused whenever a form asks",
    panel: <QuestionsCard />,
  };
}

function QuestionsCard() {
  const query = useAutofillQuery();
  return (
    <TileCard
      tile="questions"
      description="Questions you get often, with your usual answers."
      errorTitle="Couldn't load your form answers."
      query={query}
    >
      {() => <QuestionsEditor />}
    </TileCard>
  );
}

function QuestionsEditor() {
  const { profile, update, saveState } = useAutofillProfile();
  const custom: CustomQA[] = Array.isArray(profile.custom) ? profile.custom : [];
  const setCustom = (next: CustomQA[]) => update(SURFACE, (current) => ({ ...current, custom: next }));
  // A removed question takes its focused Remove with it; focus goes to Add question below the list.
  const armFocus = useFocusOnNextCommit();
  const addQuestionRef = useRef<HTMLButtonElement>(null);

  return (
    <div className="grid gap-4">
      <SettingCardAction>
        <AutosaveStatus {...saveState(SURFACE)} />
      </SettingCardAction>
      {custom.length > CUSTOM_IN_USE ? (
        <p className="text-body-small">
          Only the first {CUSTOM_IN_USE} are used when filling for now.
          Remove the ones you no longer need.
        </p>
      ) : null}
      {custom.map((qa, i) => (
        <div key={i} className="flex items-start gap-2">
          <div className="grid flex-1 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor={`af-custom-${i}-question`}>Question</Label>
              <Input
                id={`af-custom-${i}-question`}
                className="h-8 text-body-medium"
                aria-label={`Custom question ${i + 1}`}
                value={qa.question}
                onChange={(e) =>
                  setCustom(
                    custom.map((c, j) =>
                      j === i ? { ...c, question: e.target.value } : c,
                    ),
                  )
                }
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`af-custom-${i}-answer`}>Answer</Label>
              <Textarea
                id={`af-custom-${i}-answer`}
                className="text-body-medium"
                rows={2}
                aria-label={`Answer to custom question ${i + 1}`}
                value={qa.answer}
                onChange={(e) =>
                  setCustom(
                    custom.map((c, j) =>
                      j === i ? { ...c, answer: e.target.value } : c,
                    ),
                  )
                }
              />
            </div>
            {qa.only_for ? (
              <p className="text-muted-foreground text-body-small">
                Only for {qa.only_for}
                <Button
                  type="button"
                  variant="link"
                  size="xs"
                  className="ml-2 h-auto p-0"
                  aria-label={`Use custom question ${i + 1} for every job`}
                  onClick={() =>
                    setCustom(
                      custom.map((c, j) => {
                        if (j !== i) return c;
                        const general = { ...c };
                        delete general.only_for;
                        delete general.only_for_kind;
                        return general;
                      }),
                    )
                  }
                >
                  Use for every job
                </Button>
              </p>
            ) : null}
          </div>
          <RemoveButton
            label={`Remove custom question ${i + 1}`}
            onClick={() => {
              setCustom(custom.filter((_, j) => j !== i));
              armFocus(addQuestionRef);
            }}
          />
        </div>
      ))}
      <div>
        <Button
          ref={addQuestionRef}
          variant="outline"
          size="sm"
          onClick={() => setCustom([...custom, { question: "", answer: "" }])}
        >
          <Plus className="size-4" />
          Add question
        </Button>
      </div>
    </div>
  );
}
