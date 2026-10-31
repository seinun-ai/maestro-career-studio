"use client";

import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { FieldGrid } from "@/components/profile/field-control";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { Fold } from "@/components/ui/fold";
import { answered, groupFields, groupValues, withField } from "@/lib/autofill-options";
import type { QuestionSet } from "@/lib/types";

const SURFACE = "eligibility";

/**
 * Screening questions, folded: whether you worked for the company before, and what the forms of the countries
 * you apply in ask besides (the US's age and restrictive-agreement questions, India's total experience), as
 * served (the eligibility group). Each is unset until you set it: one the Companion has no answer for is
 * reported and left blank, never guessed. Saves as you go.
 */
export function EligibilityFold({
  questionSet,
  open,
  onOpenChange,
}: {
  questionSet: QuestionSet;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { profile, update, saveState } = useAutofillProfile();
  const values = groupValues(profile, "eligibility");
  const fields = groupFields(questionSet, "eligibility");
  const given = fields.filter((field) => answered(field, values[field.key])).length;
  return (
    <div id="autofill-eligibility">
      <Fold
        title="Screening questions"
        summary={given ? `${given} of ${fields.length} answered` : "Past employers, and what your countries' forms ask"}
        open={open}
        onOpenChange={onOpenChange}
      >
        <div className="@container/setting grid gap-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="max-w-[65ch] text-body-small text-muted-foreground">
              Unanswered ones are left for you on each form.
            </p>
            <AutosaveStatus {...saveState(SURFACE)} />
          </div>
          <FieldGrid
            idPrefix="af-eligibility"
            group="eligibility"
            fields={fields}
            values={values}
            onChange={(key, next) => update(SURFACE, (current) => withField(current, questionSet, "eligibility", key, next))}
          />
        </div>
      </Fold>
    </div>
  );
}
