"use client";

import { useId } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CONCEPT_ICONS } from "@/lib/concept-icons";

const ErrorIcon = CONCEPT_ICONS.fails;
const WarningIcon = CONCEPT_ICONS.warning;

/**
 * The state line under a control, and the props that tie the control to it.
 *
 * An error (red `CircleX`) marks the control `aria-invalid`; a warning (amber
 * `TriangleAlert`) marks it `data-warning`, which `Input` and `Textarea` style.
 * A warning only says a value looks off and never blocks a save. Error wins
 * when both are set. The icon sits beside its words, so colour never stands
 * alone. Spread `control` on the Input and render `message` under it.
 */
export function useFieldMessage({
  error,
  warning,
  hintId,
}: {
  error?: string | null;
  warning?: string | null;
  /** The id of a static hint the caller already renders; described-by keeps it. */
  hintId?: string;
}) {
  const messageId = useId();
  const kind = error ? "error" : warning ? "warning" : null;
  const describedBy = [hintId, kind ? messageId : null].filter(Boolean).join(" ");
  return {
    control: {
      "aria-invalid": kind === "error" ? true : undefined,
      "data-warning": kind === "warning" ? "true" : undefined,
      "aria-describedby": describedBy || undefined,
    } as const,
    message: <FieldMessage id={messageId} error={error} warning={warning} />,
  };
}

export function FieldMessage({
  id,
  error,
  warning,
}: {
  id: string;
  error?: string | null;
  warning?: string | null;
}) {
  const text = error || warning;
  const Icon = error ? ErrorIcon : WarningIcon;
  // Always mounted, so a message that appears while typing is announced; the id stays put.
  return (
    <div id={id} aria-live="polite">
      {text ? (
        <p className={`flex items-start gap-1.5 text-body-small ${error ? "text-destructive" : "text-warning"}`}>
          <Icon aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          <span>{text}</span>
        </p>
      ) : null}
    </div>
  );
}

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
  error,
  warning,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  /** A format, a default or a consequence: between the label and the field.
   *  No placeholder: a blank field holds no text (Microcopy rules). */
  hint?: string;
  optional?: boolean;
  /** What is wrong, under the field. Wins over `warning`. */
  error?: string;
  /** What looks off, under the field; never blocks a save. */
  warning?: string;
}) {
  const id = useId();
  const hintId = useId();
  const { control, message } = useFieldMessage({
    error,
    warning,
    hintId: hint ? hintId : undefined,
  });
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id} optional={optional}>
        {label}
      </Label>
      {hint ? (
        <p id={hintId} className="text-muted-foreground text-body-small">
          {hint}
        </p>
      ) : null}
      <Input id={id} value={value} {...control} onChange={(e) => onChange(e.target.value)} />
      {message}
    </div>
  );
}
