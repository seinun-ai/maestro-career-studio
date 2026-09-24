"use client";

import { useId } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Labelled text input for the resume editors.
 *
 * The id comes from `useId()`, per instance. It used to be derived from the
 * label text plus a caller-supplied `idPrefix`, which produced duplicate ids
 * the moment the same editor rendered twice — and `EditableCard` keeps its
 * edit state per card, so two experience entries really can be open at once.
 * Two inputs sharing `company` meant clicking the second one's "Company" label
 * focused the FIRST one's input, and the prefix scheme only ever pushed the
 * collision one level out: every entry in a list shared the same prefix.
 */
export function Field({
  label,
  value,
  onChange,
  hint,
  optional = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  /** A format, a default or a consequence: between the label and the field.
   *  No placeholder: a blank field holds no text (Microcopy rules). */
  hint?: string;
  optional?: boolean;
}) {
  const id = useId();
  const hintId = useId();
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id} optional={optional}>
        {label}
      </Label>
      {hint ? (
        <p id={hintId} className="text-muted-foreground text-xs">
          {hint}
        </p>
      ) : null}
      <Input
        id={id}
        value={value}
        aria-describedby={hint ? hintId : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
