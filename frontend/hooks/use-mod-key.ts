"use client";

import { useEffect, useState } from "react";

import { modKeyFor, type ModKey } from "@/lib/shortcuts";

/**
 * The platform's modifier, for shortcut hints. "Ctrl" on the server AND on the
 * first client render so hydration matches; corrected after mount.
 */
export function useModKey(): ModKey {
  const [mod, setMod] = useState<ModKey>("Ctrl");
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the platform is only knowable after mount
    setMod(modKeyFor(navigator.platform || navigator.userAgent));
  }, []);
  return mod;
}
