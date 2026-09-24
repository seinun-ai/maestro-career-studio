"use client";

import { useState, useSyncExternalStore, type ReactNode } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  parseTab,
  tabForAnchor,
  tabHref,
  tabsFor,
  type SettingsPage,
} from "@/lib/settings-tabs";

function subscribeToLocation(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  window.addEventListener("popstate", onChange);
  return () => {
    window.removeEventListener("hashchange", onChange);
    window.removeEventListener("popstate", onChange);
  };
}
const readAnchor = () => window.location.hash.slice(1);
// The server cannot see a hash: hydrate with none, then React re-renders with the real one.
const noAnchor = () => "";

/**
 * Which tab is open. Three inputs, newest wins:
 * - `?tab=` from the page's `searchParams` (server-rendered, so an internal link that carries it never
 *   flashes the default tab);
 * - the hash, once hydrated: `/profile#autofill` opens the tab that renders `#autofill` (old links,
 *   docs, and `useFocusSection`'s in-page jumps, which announce the anchor with a `hashchange`);
 * - a click on the tab row.
 *
 * A click writes the URL with the NATIVE `history.replaceState`: Next copies its own state in and
 * updates `useSearchParams` with no server round trip and no new history entry
 * (`next/dist/client/components/app-router.js`, Next 16.3). The router's `replace` would fetch the page's
 * RSC payload on every click and flip the tab only when that lands. The written URL drops the hash, so a
 * reload opens what is on screen.
 */
export function useSettingsTab(
  page: SettingsPage,
  param: string | readonly string[] | undefined,
) {
  const urlTab = parseTab(page, param);
  const anchor = useSyncExternalStore(subscribeToLocation, readAnchor, noAnchor);
  const [tab, setTab] = useState(urlTab);
  const [seen, setSeen] = useState({ urlTab, anchor: "" });
  if (seen.urlTab !== urlTab || seen.anchor !== anchor) {
    setSeen({ urlTab, anchor });
    const anchored = anchor !== seen.anchor ? tabForAnchor(page, anchor) : null;
    if (anchored) setTab(anchored);
    else if (urlTab !== seen.urlTab) setTab(urlTab);
  }

  const select = (next: string) => {
    const value = parseTab(page, next);
    setTab(value);
    window.history.replaceState(null, "", tabHref(page, value));
  };
  return [tab, select] as const;
}

const LIST_LABEL: Record<SettingsPage, string> = {
  settings: "Settings sections",
  profile: "Profile sections",
};

/**
 * The tab row and one kept-mounted panel per tab. `keepMounted`, not Base UI's default: a never-opened
 * panel would not exist (so a deep link has no target), and a visited one survives only because these
 * panels have no closing transition (the `[&[inert]]:hidden` note in ui/tabs.tsx). Kept mounted, no
 * editor ever unmounts on a tab switch: Persona, Prompts and Autofill keep their typed text, and their
 * `useLeaveGuard` registrations (effects of a mounted, inert component) keep asking.
 */
export function SettingsTabs({
  page,
  param,
  panels,
}: {
  page: SettingsPage;
  param: string | readonly string[] | undefined;
  panels: Record<string, ReactNode>;
}) {
  const [tab, select] = useSettingsTab(page, param);
  return (
    <Tabs value={tab} onValueChange={(value) => select(String(value))} className="gap-4">
      <TabsList aria-label={LIST_LABEL[page]}>
        {tabsFor(page).map((t) => (
          <TabsTrigger key={t.value} value={t.value}>
            {t.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {tabsFor(page).map((t) => (
        <TabsContent
          key={t.value}
          value={t.value}
          keepMounted
          data-settings-tab={t.value}
          className="grid gap-6"
        >
          {panels[t.value]}
        </TabsContent>
      ))}
    </Tabs>
  );
}
