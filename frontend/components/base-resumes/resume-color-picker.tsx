"use client";

import { useId, useRef, useState, type CSSProperties } from "react";
import { Check } from "lucide-react";

import { ResumeSwatch } from "@/components/visual";
import { Button } from "@/components/ui/button";
import { CUSTOM_CHROMA, RESUME_PRESETS, resumeColorStyle } from "@/lib/resume-color";
import { cn } from "@/lib/utils";

// The hue slider's track, drawn from the same recipe as the square so it shows the colour you would get.
// Stops every 30 degrees; the tones are the theme's own, so the track follows light and dark.
const HUE_TRACK = `linear-gradient(to right, ${Array.from({ length: 13 }, (_, i) =>
  `oklch(var(--resume-swatch-l) calc(${CUSTOM_CHROMA} * var(--resume-swatch-c)) ${i * 30})`).join(", ")})`;

// No `outline-none` on either control: it sets the outline style to none, which the 2px outline utilities then
// inherit, and the ring would never draw. A native range input is the keyboard and screen-reader pattern for free. WebKit needs the thumb pulled up by
// hand to centre on the 8px track; Firefox centres it itself. The thumb is a small bar, not a dot: round means status.
const HUE_RANGE = [
  "h-5 w-full cursor-pointer appearance-none bg-transparent",
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring rounded-corner-xs",
  "[&::-webkit-slider-runnable-track]:h-2 [&::-webkit-slider-runnable-track]:rounded-corner-xs [&::-webkit-slider-runnable-track]:bg-(image:--hue-track)",
  "[&::-moz-range-track]:h-2 [&::-moz-range-track]:rounded-corner-xs [&::-moz-range-track]:bg-(image:--hue-track)",
  "[&::-webkit-slider-thumb]:-mt-1.5 [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:w-2 [&::-webkit-slider-thumb]:appearance-none",
  "[&::-webkit-slider-thumb]:rounded-corner-xs [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-card [&::-webkit-slider-thumb]:bg-foreground",
  "[&::-moz-range-thumb]:h-5 [&::-moz-range-thumb]:w-2 [&::-moz-range-thumb]:rounded-corner-xs [&::-moz-range-thumb]:border-2",
  "[&::-moz-range-thumb]:border-card [&::-moz-range-thumb]:bg-foreground",
].join(" ");

/** One of the ten preset colours, or a custom hue, for a base resume. A radiogroup of swatches: arrow keys move
 *  between them and pick as they go (one tab stop), a taken colour is marked and named but can still be chosen.
 *  `used` lists the OTHER resumes' hues with their names. `pickedAtRandom` shows the hint that the value was not chosen. */
export function ResumeColorPicker({ value, onChange, used, label = "Color", pickedAtRandom = false, className }: {
  value: number | null;
  onChange: (hue: number) => void;
  used: { hue: number | null; name: string }[];
  label?: string;
  pickedAtRandom?: boolean;
  className?: string;
}) {
  const labelId = useId();
  const hintId = useId();
  const sliderId = useId();
  const swatches = useRef<(HTMLButtonElement | null)[]>([]);
  const checked = RESUME_PRESETS.findIndex((p) => p.hue === value);
  const isCustom = value !== null && checked === -1;
  const [customOpen, setCustomOpen] = useState(isCustom);

  // Roving tab stop: the checked swatch, else the first.
  const tabStop = checked === -1 ? 0 : checked;

  // Where an arrow key, Home or End lands; null for any other key.
  function target(from: number, key: string): number | null {
    const last = RESUME_PRESETS.length - 1;
    if (key === "ArrowRight" || key === "ArrowDown") return from === last ? 0 : from + 1;
    if (key === "ArrowLeft" || key === "ArrowUp") return from === 0 ? last : from - 1;
    if (key === "Home") return 0;
    if (key === "End") return last;
    return null;
  }

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <span id={labelId} className="text-label-large">{label}</span>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div role="radiogroup" aria-labelledby={labelId} aria-describedby={pickedAtRandom ? hintId : undefined}
          className="flex flex-wrap items-center gap-2 p-1">
          {RESUME_PRESETS.map((preset, i) => {
            const on = i === checked;
            const takenBy = used.filter((u) => u.hue === preset.hue).map((u) => u.name);
            const taken = takenBy.length > 0;
            const name = taken ? `${preset.name}, used by ${takenBy.join(", ")}` : preset.name;
            return (
              <button key={preset.hue} type="button" role="radio" aria-checked={on} aria-label={name} title={name}
                ref={(el) => { swatches.current[i] = el; }}
                tabIndex={i === tabStop ? 0 : -1}
                onClick={() => onChange(preset.hue)}
                onKeyDown={(e) => {
                  const to = target(i, e.key);
                  if (to === null) return;
                  e.preventDefault();
                  onChange(RESUME_PRESETS[to].hue);
                  swatches.current[to]?.focus();
                }}
                style={resumeColorStyle(preset.hue)}
                // Selected is the DS rule: a Check plus the solid 2px ring with an offset. Focus is that same ring,
                // which is safe because focus follows the checked swatch.
                className={cn(
                  "relative flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-corner-sm bg-resume text-primary-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                  on && "outline-2 outline-offset-2 outline-ring",
                )}>
                {on && <Check className="size-4" aria-hidden="true" />}
                {taken && <span aria-hidden="true" className="absolute top-1 right-1 size-1.5 rounded-full bg-card" />}
              </button>
            );
          })}
        </div>
        <Button type="button" variant="outline" size="sm" aria-expanded={customOpen} aria-controls={sliderId}
          onClick={() => setCustomOpen((open) => !open)}>
          {isCustom && <ResumeSwatch hue={value} />}
          Custom
        </Button>
      </div>
      {customOpen && (
        <div className="flex flex-col gap-1">
          <label htmlFor={sliderId} className="text-label-medium">Hue</label>
          <input id={sliderId} type="range" min={0} max={359} step={1} value={value ?? 0}
            onChange={(e) => onChange(Number(e.target.value))}
            style={{ "--hue-track": HUE_TRACK } as CSSProperties}
            className={HUE_RANGE} />
        </div>
      )}
      {pickedAtRandom && (
        <p id={hintId} className="text-body-small text-muted-foreground">
          Picked at random from colors no other resume uses.
        </p>
      )}
    </div>
  );
}
