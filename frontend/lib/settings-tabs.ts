/**
 * The tabs on /settings, and which tab holds each deep-link anchor
 * (docs/frontend-conventions.md, "Settings vs Profile"). No imports: `node --test`
 * loads this file as it is (settings-tabs.test.ts). /profile has no tabs: its
 * tiles and folds are `lib/profile-tiles.ts`, and a deep link there is
 * `/profile#<card>` (anchorHref).
 *
 * The FIRST tab is the default, and its URL carries no `?tab=`.
 * `anchors` lists every card id a panel renders (a pin checks the page against
 * it); ids INSIDE a card would resolve by prefix (`PREFIXES`; none today). The
 * slugs are never shown.
 */
export type SettingsPage = "settings";

export type SettingsTab = {
  value: string;
  label: string;
  anchors: readonly string[];
};

export const SETTINGS_TABS = [
  // How the app behaves, by purpose (owner decision D11): what a new install needs first, then the
  // Companion's own settings, then the connected agent apps, then the rest.
  { value: "basics", label: "Basics", anchors: ["api-keys", "money", "resumes-folder", "appearance", "about"] },
  { value: "companion", label: "Companion", anchors: ["companion-fill", "companion-apply", "form-filling"] },
  // "connected-agents" is the folded explainer, after the connection card.
  {
    value: "agents",
    label: "Agent apps",
    anchors: [
      "connect-assistant",
      "connected-agents",
      "full-automation",
      "auto-apply",
      "job-site-login",
      "agent-writer",
      "agent-hints",
      "second-copy",
    ],
  },
  {
    value: "advanced",
    label: "Advanced",
    anchors: ["models", "model-catalog", "custom-endpoint", "prompts", "quick-tailor", "hours-per-year", "diagnostics"],
  },
] as const satisfies readonly SettingsTab[];

const TABS: Record<SettingsPage, readonly SettingsTab[]> = {
  settings: SETTINGS_TABS,
};

/** [id prefix, tab]: ids inside a card that no table row names. */
const PREFIXES: Record<SettingsPage, readonly (readonly [string, string])[]> = {
  settings: [],
};

/**
 * `?tab=` values an older build wrote, and the tab and card that hold what each one opened with: a
 * bookmark from the five tabs before the four lands on its card. `ai` is the plan's name for the old
 * first tab (its value was `models`). The old `agents` is still a tab (Agent apps), so it is not here.
 */
const OLD_TABS: Record<SettingsPage, Readonly<Record<string, { tab: string; anchor: string }>>> = {
  settings: {
    ai: { tab: "basics", anchor: "api-keys" },
    models: { tab: "basics", anchor: "api-keys" },
    tailoring: { tab: "advanced", anchor: "quick-tailor" },
    appearance: { tab: "basics", anchor: "appearance" },
    about: { tab: "basics", anchor: "about" },
  },
};

/** The old value's landing, or undefined. Own keys only: `?tab=constructor` is not an old tab. */
function oldTab(page: SettingsPage, value: string | undefined) {
  return value !== undefined && Object.hasOwn(OLD_TABS[page], value) ? OLD_TABS[page][value] : undefined;
}

export function tabsFor(page: SettingsPage): readonly SettingsTab[] {
  return TABS[page];
}

export function defaultTab(page: SettingsPage): string {
  return TABS[page][0].value;
}

/** `?tab=` as the page reads it: an old value is its new tab; absent, repeated or unknown is the default tab. */
export function parseTab(
  page: SettingsPage,
  raw: string | readonly string[] | null | undefined,
): string {
  const value = typeof raw === "string" ? raw : raw?.[0];
  if (TABS[page].some((tab) => tab.value === value)) return value as string;
  return oldTab(page, value)?.tab ?? defaultTab(page);
}

/** Where `?tab=` lands: its tab, and the card to land on when the value is an old one (else null). */
export function landingFor(
  page: SettingsPage,
  raw: string | readonly string[] | null | undefined,
): { tab: string; anchor: string | null } {
  const value = typeof raw === "string" ? raw : raw?.[0];
  return { tab: parseTab(page, raw), anchor: oldTab(page, value)?.anchor ?? null };
}

/** The tab that renders `anchor`, or null when no tab does (`#main-content`, the skip link). */
export function tabForAnchor(page: SettingsPage, anchor: string): string | null {
  if (!anchor) return null;
  const exact = TABS[page].find((tab) => tab.anchors.includes(anchor));
  if (exact) return exact.value;
  const prefixed = PREFIXES[page].find(([prefix]) => anchor.startsWith(prefix));
  return prefixed ? prefixed[1] : null;
}

/** `/settings?tab=agents#agent-hints`; the default tab writes no `?tab=`. */
export function tabHref(page: SettingsPage, tab: string, anchor?: string): string {
  const query = tab === defaultTab(page) ? "" : `?tab=${tab}`;
  return `/${page}${query}${anchor ? `#${anchor}` : ""}`;
}

/** The tabbed page a pathname is, or null for every other route (Profile included: it has no tabs). */
export function settingsPageAt(pathname: string): SettingsPage | null {
  return pathname === "/settings" ? "settings" : null;
}

/** A deep link to `anchor` on `home`: settings names the tab, other routes are `home#anchor`. */
export function anchorHref(home: string, anchor: string): string {
  const page = settingsPageAt(home);
  if (page === null) return `${home}#${anchor}`;
  return tabHref(page, tabForAnchor(page, anchor) ?? defaultTab(page), anchor);
}
