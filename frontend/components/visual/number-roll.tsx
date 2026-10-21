"use client";

import { useSyncExternalStore } from "react";

import { ROLL_MS } from "@/lib/motion";
import { cn } from "@/lib/utils";

const DIGITS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];
const REDUCE = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void) {
  const query = window.matchMedia(REDUCE);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** True when the person asked for less motion. False on the server, so the first paint matches. */
function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, () => window.matchMedia(REDUCE).matches, () => false);
}

/** A number that rolls to its new value: each digit is a 0-9 column that moves (`translate`, ROLL_MS,
 * strong ease-out), so only the digits that changed move. With reduced motion it is the plain number.
 * The value is read once, as text; the columns are hidden. It never announces: a live region, if the
 * change should be spoken, is the parent's. */
export function NumberRoll({ value, className }: { value: number; className?: string }) {
  const text = String(value);
  const reduce = useReducedMotion();
  if (reduce) return <span className={cn("tabular-nums", className)}>{text}</span>;
  const chars = [...text];
  return (
    <span className={cn("inline-flex tabular-nums", className)}>
      <span className="sr-only">{text}</span>
      {chars.map((ch, i) => {
        // Keyed from the right, so the ones column keeps its place when the number gains a digit.
        const key = chars.length - i;
        const digit = DIGITS.indexOf(ch);
        if (digit < 0) {
          return <span key={key} aria-hidden="true">{ch}</span>;
        }
        return (
          <span key={key} aria-hidden="true" className="inline-block h-[1lh] overflow-hidden">
            <span
              className="flex flex-col transition-[translate] ease-(--ease-out-strong)"
              style={{ translate: `0 -${digit}lh`, transitionDuration: `${ROLL_MS}ms` }}
            >
              {DIGITS.map((d) => (
                <span key={d}>{d}</span>
              ))}
            </span>
          </span>
        );
      })}
    </span>
  );
}
