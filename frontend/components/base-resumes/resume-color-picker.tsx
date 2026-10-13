"use client";

import { useId, useRef, useState, type CSSProperties } from "react";
import { Check } from "lucide-react";

import { ResumeSwatch } from "@/components/visual";
import { Button } from "@/components/ui/button";
import { CUSTOM_CHROMA, RESUME_PRESETS, presetName, resumeColorStyle } from "@/lib/resume-color";
import { cn } from "@/lib/utils";

// The hue slider's track, drawn from the same recipe as the square so it shows the colour you would get.
// Stops every 30 degrees; the tones are the theme's own, so the track follows light and dark.
const HUE_TRACK = `linear-gradient(to right, ${Array.from({ length: 13 }, (_, i) =>
  `oklch(var(--resume-swatch-l) calc(${CUSTOM_CHROMA} * var(--resume-swatch-c)) ${i * 30})`).join(", ")})`;

// A native range input is the keyboard and screen-reader pattern for free. WebKit needs the thumb pulled up by
// hand to centre on the 8px track; Firefox centres it itself. The thumb is a small bar, not a dot: round means status.
// Focus is a solid `ring` box-shadow, the same as on a swatch; `outline-none` is never used, because it sets the
// outline style to none and the 2px outline utilities (the checked swatch's) then paint nothing.
const HUE_RANGE = [
  "h-5 w-full cursor-pointer appearance-none rounded-corner-xs bg-transparent",
  "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card",
  "[&::-webkit-slider-runnable-track]:h-2 [&::-webkit-slider-runnable-track]:rounded-corner-xs [&::-webkit-slider-runnable-track]:bg-(image:--hue-track)",
  "[&::-moz-range-track]:h-2 [&::-moz-range-track]:rounded-corner-xs [&::-moz-range-track]:bg-(image:--hue-track)",
  "[&::-webkit-slider-thumb]:-mt-1.5 [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:w-2 [&::-webkit-slider-thumb]:appearance-none",
  "[&::-webkit-slider-thumb]:rounded-corner-xs [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-card [&::-webkit-slider-thumb]:bg-foreground",
  "[&::-moz-range-thumb]:h-5 [&::-moz-range-thumb]:w-2 [&::-moz-range-thumb]:rounded-corner-xs [&::-moz-range-thumb]:border-2",
  "[&::-moz-range-thumb]:border-card [&::-moz-range-thumb]:bg-foreground",
].join(" ");

const NAV_KEYS = ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"];

/** One of the ten preset colors, or a custom hue, for a base resume. A radiogroup of swatches: arrow keys move
 *  between them and pick as they go (one tab stop), a taken color is marked and named but can still be chosen.
 *
 *  Two callbacks, for two kinds of caller. `onChange(hue)` is the live value: it fires on every swatch click,
 *  every arrow key and every slider input, so a form that only holds the value (the New dialog) uses it alone.
 *  `onCommit(hue)` fires once per settled choice: a swatch click, the keyup after an arrow, Home or End, and the
 *  slider's pointerup, keyup or blur. A caller that saves each choice (the Target dialog) saves on `onCommit`,
 *  so dragging the slider sends one request, not one per pixel.
 *
 *  `used` lists the OTHER resumes' hues with their names. `pickedAtRandom` shows the hint that the value was not chosen. */
export function ResumeColorPicker({ value, onChange, onCommit, used, label = "Color", pickedAtRandom = false, className }: {
  value: number | null;
  onChange: (hue: number) => void;
  onCommit?: (hue: number) => void;
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
  // The slider follows the value until the person opens, closes or first uses it: a custom hue that arrives
  // after mount opens it, and Custom can still close it.
  const [customOpen, setCustomOpen] = useState<boolean | null>(null);
  const sliderOpen = customOpen ?? isCustom;
  // The last hue chosen by key or slider that has not been committed yet; null once it has.
  const unsettled = useRef<number | null>(null);

  function settle() {
    if (unsettled.current === null) return;
    const hue = unsettled.current;
    unsettled.current = null;
    onCommit?.(hue);
  }

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
          onKeyUp={(e) => { if (NAV_KEYS.includes(e.key)) settle(); }}
          className="flex flex-wrap items-center gap-2 p-1.5">
          {RESUME_PRESETS.map((preset, i) => {
            const on = i === checked;
            const takenBy = used.filter((u) => u.hue === preset.hue).map((u) => u.name);
            const taken = takenBy.length > 0;
            const name = taken ? `${preset.name}, used by ${takenBy.join(", ")}` : preset.name;
            return (
              <button key={preset.hue} type="button" role="radio" aria-checked={on} aria-label={name} title={name}
                ref={(el) => { swatches.current[i] = el; }}
                tabIndex={i === tabStop ? 0 : -1}
                onClick={() => { onChange(preset.hue); if (preset.hue !== value) onCommit?.(preset.hue); }}
                onKeyDown={(e) => {
                  const to = target(i, e.key);
                  if (to === null) return;
                  e.preventDefault();
                  unsettled.current = RESUME_PRESETS[to].hue;
                  onChange(RESUME_PRESETS[to].hue);
                  swatches.current[to]?.focus();
                }}
                style={resumeColorStyle(preset.hue)}
                // Selected is the DS rule: a Check plus the solid 2px outline with an offset. Focus is a separate solid
                // ring (a box-shadow) one step further out, so it stacks outside the outline: a focused swatch never
                // looks like the checked one, and the checked-and-focused one shows both.
                className={cn(
                  "relative flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-corner-sm bg-resume text-primary-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-4 focus-visible:ring-offset-card",
                  on && "outline-2 outline-offset-2 outline-ring",
                )}>
                {on && <Check className="size-4" aria-hidden="true" />}
                {taken && <span aria-hidden="true" className="absolute top-1 right-1 size-1.5 rounded-full bg-card" />}
              </button>
            );
          })}
        </div>
        <Button type="button" variant="outline" size="sm" aria-expanded={sliderOpen} aria-controls={sliderOpen ? sliderId : undefined}
          onClick={() => setCustomOpen(!sliderOpen)}>
          {isCustom && <ResumeSwatch hue={value} />}
          Custom
        </Button>
      </div>
      {sliderOpen && (
        <div className="flex flex-col gap-1">
          <label htmlFor={sliderId} className="text-label-medium">Hue</label>
          <input id={sliderId} type="range" min={0} max={359} step={1} value={value ?? 0}
            aria-valuetext={presetName(value) ?? `Hue ${value ?? 0}`}
            onChange={(e) => { unsettled.current = Number(e.target.value); onChange(unsettled.current); }}
            // Latch the slider open on first touch: dragging onto a preset hue makes the value non-custom, and a
            // slider that follows the value would unmount mid-drag, before its pointerup could commit.
            onFocus={() => { if (customOpen === null) setCustomOpen(true); }}
            onPointerUp={settle} onKeyUp={settle} onBlur={settle}
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
