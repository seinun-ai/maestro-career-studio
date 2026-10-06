"use client";

import { useEffect, useRef, useState } from "react";

import { valueAt } from "@/lib/count-up";

/** The displayed value of `target`, counting to each new value over `ms` (no motion when reduced). */
export function useCountUp(target: number, ms = 400): number {
  const [shown, setShown] = useState(target);
  // What is on screen now, so a target that changes mid-run counts on from here, not from the last target.
  const from = useRef(target);
  useEffect(() => {
    const start = from.current;
    if (start === target) return;
    // One path: reduced motion is a zero-length run, so state only ever
    // changes inside the frame callback.
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dur = reduce ? 0 : ms;
    let frame = 0;
    const t0 = performance.now();
    const step = (now: number) => {
      const t = dur === 0 ? 1 : (now - t0) / dur;
      const v = valueAt(start, target, t);
      from.current = v;
      setShown(v);
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, ms]);
  return shown;
}
