"use client";

import { useMemo, useSyncExternalStore } from "react";

import { parseSwatchTones, type SwatchTones } from "@/lib/resume-color";

function subscribe(onChange: () => void) {
  // next-themes writes `.dark` on <html> (also when the system theme flips), and that is what swaps the tones.
  const watcher = new MutationObserver(onChange);
  watcher.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => watcher.disconnect();
}

function readTones(): string {
  const style = getComputedStyle(document.documentElement);
  return `${style.getPropertyValue("--resume-swatch-l")}|${style.getPropertyValue("--resume-swatch-c")}`;
}

/**
 * The `resume` colour's tones for the current theme, read from the CSS variables (globals.css holds them,
 * light and dark, and nothing here repeats them). For an SVG fill a class cannot reach: pass them to
 * `resumeSwatchColor`. Re-renders when the theme changes. `null` on the server and the hydration render.
 */
export function useResumeSwatchTones(): SwatchTones | null {
  const raw = useSyncExternalStore(subscribe, readTones, () => "");
  return useMemo(() => {
    const [l = "", c = ""] = raw.split("|");
    return parseSwatchTones(l, c);
  }, [raw]);
}
