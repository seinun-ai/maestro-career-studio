"use client";

import { useState } from "react";
import { Pencil } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useFieldMessage } from "@/components/resume-editor/field";
import { useEditToggle } from "@/hooks/use-focus-return";
import { emailWarning } from "@/lib/field-checks";
import type { ContactInfo } from "@/lib/types";

const FIELDS: {
  key: keyof ContactInfo;
  label: string;
  required?: boolean;
}[] = [
  { key: "name", label: "Name", required: true },
  { key: "email", label: "Email", required: true },
  { key: "phone", label: "Phone" },
  { key: "location", label: "Location" },
  { key: "linkedin", label: "LinkedIn" },
  { key: "github", label: "GitHub" },
  { key: "website", label: "Website" },
];

/** Email's input: the type, the autofill token, and a format warning shown once the field is left. */
function EmailInput({ value, onChange }: { value: string; onChange: (next: string) => void }) {
  const [warning, setWarning] = useState<string | null>(null);
  const { control, message } = useFieldMessage({ warning });
  return (
    <>
      <Input
        id="contact_email"
        type="email"
        autoComplete="email"
        value={value}
        {...control}
        onChange={(e) => {
          setWarning(null);
          onChange(e.target.value);
        }}
        onBlur={() => setWarning(emailWarning(value))}
      />
      {message}
    </>
  );
}

export function ContactForm({
  value,
  onChange,
}: {
  value: ContactInfo;
  onChange: (next: ContactInfo) => void;
}) {
  // The pencil and Done each unmount themselves: opening focuses Name, Done
  // the pencil.
  const { editing, editRef, openerRef, open, close } = useEditToggle();

  const update = (key: keyof ContactInfo, next: string) => {
    onChange({ ...value, [key]: next });
  };

  if (editing) {
    return (
      <div ref={editRef} className="@container grid gap-3">
        <div className="grid gap-3 @md:grid-cols-2">
          {FIELDS.map(({ key, label, required }) => (
            <div key={key} className="grid gap-1.5">
              <Label htmlFor={`contact_${key}`}>
                {label}
                {required && <span className="text-destructive"> *</span>}
              </Label>
              {key === "email" ? (
                <EmailInput value={value[key] ?? ""} onChange={(next) => update(key, next)} />
              ) : (
                <Input
                  id={`contact_${key}`}
                  value={value[key] ?? ""}
                  onChange={(e) => update(key, e.target.value)}
                />
              )}
            </div>
          ))}
        </div>
        <div className="flex justify-end">
          <Button size="sm" onClick={close}>
            Done
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="group/contact @container border-border/0 hover:border-border/60 relative rounded-corner-md border px-3 py-3">
      <dl className="grid gap-x-4 gap-y-1.5 pr-10 text-body-medium @xs:grid-cols-[8rem_minmax(0,1fr)]">
        {FIELDS.map(({ key, label }) => {
          const v = value[key];
          return (
            // Narrow pane: each pair stacks. From 20rem the wrapper dissolves
            // and dt/dd join the two-column grid.
            <div key={key} className="grid gap-0.5 @xs:contents">
              <dt className="text-muted-foreground text-label-large">
                {label}
              </dt>
              <dd className="text-foreground/90 min-w-0 wrap-anywhere">
                {v ? (
                  v
                ) : (
                  <span className="text-muted-foreground italic">—</span>
                )}
              </dd>
            </div>
          );
        })}
      </dl>
      <Button
        ref={openerRef}
        size="icon-sm"
        variant="ghost"
        aria-label="Edit contact"
        className="pointer-coarse:opacity-100 absolute top-2 right-2 opacity-0 transition-opacity group-hover/contact:opacity-100 focus-within:opacity-100"
        onClick={open}
      >
        <Pencil className="size-3.5" />
      </Button>
    </div>
  );
}
