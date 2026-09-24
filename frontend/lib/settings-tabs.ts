/**
 * The tabs on /settings and /profile, and which tab holds each deep-link anchor
 * (docs/frontend-conventions.md, "Settings vs Profile"). No imports: `node --test`
 * loads this file as it is (settings-tabs.test.ts).
 *
 * The FIRST tab of each page is its default, and its URL carries no `?tab=`.
 * `anchors` lists every card id a panel renders (a pin checks the pages against
 * it); ids INSIDE a card resolve by prefix (`autofill-work_auth`, the fieldsets
 * setup-steps.ts and the job knock-out card aim at). The slugs are never shown.
 */
export type SettingsPage = "settings" | "profile";

export type SettingsTab = {
  value: string;
  label: string;
  anchors: readonly string[];
};

export const SETTINGS_TABS = [
  {
    value: "models",
    label: "AI & models",
    anchors: ["api-keys", "models", "model-catalog", "custom-endpoint", "prompts"],
  },
  { value: "tailoring", label: "Tailoring", anchors: ["quick-tailor"] },
  // "connected-agents" is the explainer card wave 2 mounts first in this tab.
  {
    value: "agents",
    label: "Connected agents",
    anchors: ["connected-agents", "agent-hints", "auto-apply"],
  },
  { value: "appearance", label: "Appearance", anchors: ["appearance"] },
  { value: "about", label: "About", anchors: ["about"] },
] as const satisfies readonly SettingsTab[];

export const PROFILE_TABS = [
  { value: "you", label: "About you", anchors: ["persona", "market", "job-preferences"] },
  { value: "autofill", label: "Autofill", anchors: ["autofill"] },
] as const satisfies readonly SettingsTab[];

const TABS: Record<SettingsPage, readonly SettingsTab[]> = {
  settings: SETTINGS_TABS,
  profile: PROFILE_TABS,
};

/** [id prefix, tab]: ids inside a card that no table row names. */
const PREFIXES: Record<SettingsPage, readonly (readonly [string, string])[]> = {
  settings: [],
  profile: [["autofill-", "autofill"]],
};

export function tabsFor(page: SettingsPage): readonly SettingsTab[] {
  return TABS[page];
}

export function defaultTab(page: SettingsPage): string {
  return TABS[page][0].value;
}

/** `?tab=` as the page reads it: absent, repeated or unknown is the default tab. */
export function parseTab(
  page: SettingsPage,
  raw: string | readonly string[] | null | undefined,
): string {
  const value = typeof raw === "string" ? raw : raw?.[0];
  return TABS[page].some((tab) => tab.value === value) ? (value as string) : defaultTab(page);
}

/** The tab that renders `anchor`, or null when no tab does (`#main-content`, the skip link). */
export function tabForAnchor(page: SettingsPage, anchor: string): string | null {
  if (!anchor) return null;
  const exact = TABS[page].find((tab) => tab.anchors.includes(anchor));
  if (exact) return exact.value;
  const prefixed = PREFIXES[page].find(([prefix]) => anchor.startsWith(prefix));
  return prefixed ? prefixed[1] : null;
}

/** `/profile?tab=autofill#autofill-eeo`; the default tab writes no `?tab=`. */
export function tabHref(page: SettingsPage, tab: string, anchor?: string): string {
  const query = tab === defaultTab(page) ? "" : `?tab=${tab}`;
  return `/${page}${query}${anchor ? `#${anchor}` : ""}`;
}

/** The tabbed page a pathname is, or null for every other route. */
export function settingsPageAt(pathname: string): SettingsPage | null {
  return pathname === "/settings" ? "settings" : pathname === "/profile" ? "profile" : null;
}

/** A deep link to `anchor` on `home`: settings and profile name the tab, other routes are `home#anchor`. */
export function anchorHref(home: string, anchor: string): string {
  const page = settingsPageAt(home);
  if (page === null) return `${home}#${anchor}`;
  return tabHref(page, tabForAnchor(page, anchor) ?? defaultTab(page), anchor);
}
