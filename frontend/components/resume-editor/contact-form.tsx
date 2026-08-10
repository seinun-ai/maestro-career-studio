"use client";

import { useState } from "react";
import { Pencil } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ContactInfo } from "@/lib/types";

const FIELDS: {
  key: keyof ContactInfo;
  label: string;
  placeholder?: string;
  required?: boolean;
}[] = [
  { key: "name", label: "Name", required: true },
  {
    key: "email",
    label: "Email",
    placeholder: "you@example.com",
    required: true,
  },
  { key: "phone", label: "Phone" },
  { key: "location", label: "Location" },
  { key: "linkedin", label: "LinkedIn" },
  { key: "github", label: "GitHub" },
  { key: "website", label: "Website" },
];

export function ContactForm({
  value,
  onChange,
}: {
  value: ContactInfo;
  onChange: (next: ContactInfo) => void;
}) {
  const [editing, setEditing] = useState(false);

  const update = (key: keyof ContactInfo, next: string) => {
    onChange({ ...value, [key]: next });
  };

  if (editing) {
    return (
      <div className="grid gap-3">
        <div className="grid gap-3 sm:grid-cols-2">
          {FIELDS.map(({ key, label, placeholder, required }) => (
            <div key={key} className="grid gap-1.5">
              <Label htmlFor={`contact_${key}`}>
                {label}
                {required && <span className="text-destructive"> *</span>}
              </Label>
              <Input
                id={`contact_${key}`}
                placeholder={placeholder}
                value={value[key] ?? ""}
                onChange={(e) => update(key, e.target.value)}
              />
            </div>
          ))}
        </div>
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setEditing(false)}>
            Done
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="group/contact border-border/0 hover:border-border/60 relative rounded-md border px-3 py-3">
      <dl className="grid grid-cols-[8rem_1fr] gap-x-4 gap-y-1.5 pr-10 text-sm">
        {FIELDS.map(({ key, label }) => {
          const v = value[key];
          return (
            <div key={key} className="contents">
              <dt className="text-muted-foreground text-sm font-medium">
                {label}
              </dt>
              <dd className="text-foreground/90">
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
        size="icon-sm"
        variant="ghost"
        aria-label="Edit contact"
        className="pointer-coarse:opacity-100 absolute top-2 right-2 opacity-0 transition-opacity group-hover/contact:opacity-100 focus-within:opacity-100"
        onClick={() => setEditing(true)}
      >
        <Pencil className="size-3.5" />
      </Button>
    </div>
  );
}
