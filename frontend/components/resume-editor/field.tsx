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
  placeholder,
  optional = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  optional?: boolean;
}) {
  const id = useId();
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id} optional={optional}>
        {label}
      </Label>
      <Input
        id={id}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
