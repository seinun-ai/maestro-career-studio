"use client";

import { useState } from "react";

import { useFieldMessage } from "@/components/resume-editor/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  NOT_SET,
  fieldValue,
  isBlank,
  storedFieldValue,
  type FieldDef,
} from "@/lib/autofill-options";
import { emailWarning, linkWarning, phoneWarning } from "@/lib/field-checks";

/** The input type, autofill token and format check of the contact fields forms read. */
const CONTACT_INPUT: Record<
  string,
  { type: "email" | "tel" | "url"; autoComplete: string; check: (v: string) => string | null }
> = {
  email: { type: "email", autoComplete: "email", check: (v) => emailWarning(v) },
  phone: { type: "tel", autoComplete: "tel", check: (v) => phoneWarning(v) },
  linkedin: { type: "url", autoComplete: "url", check: (v) => linkWarning(v) },
  github: { type: "url", autoComplete: "url", check: (v) => linkWarning(v) },
  website: { type: "url", autoComplete: "url", check: (v) => linkWarning(v) },
};

/** One answer's control: a select over its options, a date, or a text box. `onChange`
 *  gets what to store; undefined ("Not set") removes the key. */
export function FieldControl({
  id,
  group,
  field,
  value,
  hintId,
  onChange,
}: {
  id: string;
  group: string;
  field: FieldDef;
  value: string;
  hintId?: string;
  onChange: (next: string | boolean | undefined) => void;
}) {
  // A warning shows once the field is left, not on every keystroke, and never blocks a save.
  const [warning, setWarning] = useState<string | null>(null);
  const contact = field.type === "select" || group !== "personal" ? undefined : CONTACT_INPUT[field.key];
  const { control, message } = useFieldMessage({ warning, hintId });
  return field.type === "select" ? (
    <Select
      value={value}
      onValueChange={(v) => onChange(v === NOT_SET.value ? undefined : storedFieldValue(field, v))}
    >
      <SelectTrigger id={id} size="sm" className="w-full" aria-describedby={hintId}>
        <SelectValue placeholder="Choose">
          {field.options?.find((o) => o.value === value)?.label}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {field.options?.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  ) : (
    <>
      <Input
        id={id}
        className="h-8 text-body-medium"
        value={value}
        type={field.type === "date" ? "date" : contact?.type}
        autoComplete={contact?.autoComplete}
        {...control}
        onChange={(e) => {
          setWarning(null);
          // A cleared date removes its key, never stores "".
          onChange(field.type === "date" && !e.target.value ? undefined : e.target.value);
        }}
        onBlur={() => setWarning(contact ? contact.check(value) : null)}
      />
      {message}
    </>
  );
}

/**
 * A group's fields in the editor's grid, each with its label, its hint (a stale answer's "Answer again"
 * instead, while the question is empty) and its control. A field shown only for one answer of another
 * (`when`) is left out until that answer is chosen.
 */
export function FieldGrid({
  idPrefix,
  group,
  fields,
  values,
  stale = [],
  voluntary = false,
  onChange,
}: {
  /** Each control's id is `${idPrefix}-${field.key}` (`af-personal-email`): deep links resolve by prefix. */
  idPrefix: string;
  /** The profile group the values belong to ("personal" checks the contact formats). */
  group: string;
  fields: readonly FieldDef[];
  values: Record<string, unknown>;
  /** The keys of this group the backend dropped because their question changed. */
  stale?: readonly string[];
  /** A voluntary group (diversity): no field says "(optional)" of its own. */
  voluntary?: boolean;
  onChange: (key: string, next: string | boolean | undefined) => void;
}) {
  return (
    // items-end: a label that wraps (the longer questions at 14px) would
    // otherwise push its control below its neighbours'.
    <div className="grid items-end gap-4 @lg/setting:grid-cols-2 @3xl/setting:grid-cols-3">
      {fields.map((field) => {
        if (field.when && values[field.when[0]] !== field.when[1]) {
          return null;
        }
        const id = `${idPrefix}-${field.key}`;
        const rawValue = values[field.key];
        const value = fieldValue(field, rawValue);
        const isStale = Boolean(field.staleHint) && isBlank(rawValue) && stale.includes(field.key);
        const hint = isStale ? field.staleHint : field.hint;
        const hintId = hint ? `${id}-hint` : undefined;
        return (
          <div key={field.key} className="grid gap-1.5">
            <Label htmlFor={id} optional={field.optional && !voluntary}>
              {field.label}
            </Label>
            {hint ? (
              <p id={hintId} className="text-muted-foreground text-body-small">
                {hint}
              </p>
            ) : null}
            <FieldControl
              id={id}
              group={group}
              field={field}
              value={value}
              hintId={hintId}
              onChange={(next) => onChange(field.key, next)}
            />
          </div>
        );
      })}
    </div>
  );
}
