"use client";

import { useId } from "react";
import { ArrowDown, ArrowUp, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { move } from "@/lib/utils";

export function BulletList({
  label = "Bullets",
  value,
  onChange,
}: {
  label?: string;
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const labelId = useId();
  return (
    <div className="space-y-2" role="group" aria-labelledby={labelId}>
      <span id={labelId} className="text-sm font-medium">
        {label}
      </span>
      {value.map((bullet, i) => (
        <div key={i} className="flex items-start gap-2">
          <Textarea
            rows={2}
            // Position matters here — the reorder buttons beside each row are
            // only meaningful if you can tell which bullet you are on.
            aria-label={`${label} ${i + 1} of ${value.length}`}
            value={bullet}
            onChange={(e) =>
              onChange(value.map((b, idx) => (idx === i ? e.target.value : b)))
            }
          />
          {/* Names carry the position, like the textarea above: "Move up" three
              times in a row tells a screen-reader user nothing about WHICH
              bullet moves. These three were unnamed entirely — the most
              repeated control in the editor, announced only as "button". */}
          <div className="flex flex-col gap-1">
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label={`Move ${label.toLowerCase()} ${i + 1} up`}
              onClick={() => onChange(move(value, i, i - 1))}
              disabled={i === 0}
            >
              <ArrowUp />
            </Button>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label={`Move ${label.toLowerCase()} ${i + 1} down`}
              onClick={() => onChange(move(value, i, i + 1))}
              disabled={i === value.length - 1}
            >
              <ArrowDown />
            </Button>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label={`Delete ${label.toLowerCase()} ${i + 1}`}
              onClick={() => onChange(value.filter((_, idx) => idx !== i))}
            >
              <Trash2 />
            </Button>
          </div>
        </div>
      ))}
      <Button
        size="sm"
        variant="outline"
        onClick={() => onChange([...value, ""])}
      >
        Add bullet
      </Button>
    </div>
  );
}
