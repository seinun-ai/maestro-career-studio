"use client";

import { Check } from "lucide-react";

import { cn } from "@/lib/utils";
import type { AgentApp } from "@/lib/types";

/** Which agent app the copied prompt is for. A segmented control in
 * SourceToggle's style; the unreachable apps stay pickable, so their note can
 * say why Copy is off. */
export function AppPicker({
  apps,
  value,
  onChange,
}: {
  apps: AgentApp[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <div
      className="inline-flex h-8 items-center self-start rounded-full border p-0.5"
      role="group"
      aria-label="Agent app"
    >
      {apps.map((app) => (
        <button
          key={app.id}
          type="button"
          aria-pressed={value === app.id}
          onClick={() => onChange(app.id)}
          className={cn(
            "inline-flex h-7 cursor-pointer items-center gap-1 rounded-full px-3 text-label-medium transition-colors duration-150",
            value === app.id
              ? "bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"
              : "text-muted-foreground hover:bg-muted",
          )}
        >
          {value === app.id && <Check className="size-3" aria-hidden="true" />}
          {app.label}
        </button>
      ))}
    </div>
  );
}
