import type { AgentApp, AutomationCard, AutomationNeed } from "@/lib/types";

/** The text Copy puts on the clipboard: the app's wrapper, then the skill. A
 * scheduled card's wrapper tells the agent to ask the user when to run; an
 * attended or custom card's wrapper runs it now. Nothing about the user is
 * inserted (docs/plans/2026-10-04-automations-page-design.md). */
export function promptFor(card: AutomationCard, app: AgentApp): string {
  const wrapper = card.kind === "scheduled" ? app.preamble : app.attended_preamble;
  return `${wrapper}\n\n${card.body}`;
}

export const NEED_LABELS: Record<AutomationNeed, string> = {
  maestro: "Maestro",
  email: "Email",
  browser: "Browser",
  web: "Web",
};

/** The app picker's last choice, kept with `useLocalStorageState`
 * (hooks/use-local-storage-state.ts): `null` means never chosen. */
export const APP_STORE_KEY = "cs-automations-app";
export const parseStoredApp = (raw: string | null) => raw;
export const serializeApp = (id: string | null) => id ?? "";

/** The one card that is attended for now (backend/app/automations/skills). */
export const APPLY_CARD_ID = "apply-session";
