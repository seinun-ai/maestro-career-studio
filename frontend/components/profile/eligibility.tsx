"use client";

import { useAutofillProfile } from "@/components/profile/autofill-profile";
import { FieldGrid } from "@/components/profile/field-control";
import { AutosaveStatus } from "@/components/settings/autosave-status";
import { Fold } from "@/components/ui/fold";
import { answered, groupFields, groupValues, withField } from "@/lib/autofill-options";

const SURFACE = "eligibility";

/**
 * Eligibility, folded: the three knockout questions nearly every US application asks and nothing else in the
 * profile can derive. Each is unset until you set it: one the Companion has no answer for is reported and
 * left blank, never guessed. Saves as you go.
 */
export function EligibilityFold({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { profile, update, saveState } = useAutofillProfile();
  const values = groupValues(profile, "eligibility");
  const fields = groupFields("eligibility");
  const given = fields.filter((field) => answered(field, values[field.key])).length;
  return (
    <div id="autofill-eligibility">
      <Fold
        title="Eligibility"
        summary={given ? `${given} of ${fields.length} answered` : "Age, past employers, restrictive agreements"}
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
            onChange={(key, next) => update(SURFACE, (current) => withField(current, "eligibility", key, next))}
          />
        </div>
      </Fold>
    </div>
  );
}
