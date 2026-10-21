"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { opensSetup } from "@/lib/setup-flow";
import type { SetupStatus } from "@/lib/types";

/** This browser's note that Setup has been opened. A convenience, not progress: Setup's steps read their
 *  data (lib/setup-flow.ts), and a cleared note at worst opens Setup once more on a brand-new install. */
const SEEN_KEY = "maestro-cs:setup-seen";

function seen(): boolean {
  try {
    return window.localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return false; // storage disabled: a new install still lands on Today's setup card
  }
}

export function markSetupSeen() {
  try {
    window.localStorage.setItem(SEEN_KEY, "1");
  } catch {
    // Storage disabled: Today's setup card still leads the way back.
  }
}

/** Today sends a brand-new install (no key and no resume) to /setup, once: Setup marks itself seen when it
 *  opens, so a user who skips it lands on Today next time, and anyone with a key or a resume never moves. */
export function useOpenSetupOnFirstLaunch(status: SetupStatus | undefined) {
  const router = useRouter();
  useEffect(() => {
    if (status && opensSetup(status, seen())) router.replace("/setup");
  }, [status, router]);
}
