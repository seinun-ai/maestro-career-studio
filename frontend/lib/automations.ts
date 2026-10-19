import type { AutomationNeed } from "@/lib/types";

export const NEED_LABELS: Record<AutomationNeed, string> = {
  maestro: "Maestro",
  email: "Email",
  browser: "Browser",
  web: "Web",
};

/** The one card that is attended for now (backend/app/automations/skills). */
export const APPLY_CARD_ID = "apply-session";
