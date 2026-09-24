"use client";

import { Search } from "lucide-react";

import { Input } from "@/components/ui/input";

/** The list pages' search box: a pill above the filter row. `label` names it
 *  (a search field's placeholder is a prompt, not its name). The placeholder
 *  is on test_frontend_placeholders.py's named-prompt list. */
export function ListSearch({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <div className="relative w-full max-w-sm">
      <Search
        aria-hidden="true"
        className="text-muted-foreground pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2"
      />
      <Input
        aria-label={label}
        placeholder="Search company or role…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 rounded-full pl-10"
      />
    </div>
  );
}
