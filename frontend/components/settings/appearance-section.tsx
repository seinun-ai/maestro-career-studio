"use client";

import { useId, useSyncExternalStore } from "react";
import { useTheme } from "next-themes";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SegmentedChoice } from "@/components/settings/setting-layout";
import { Label } from "@/components/ui/label";

/**
 * Appearance: Light, Dark or Like my computer (next-themes' `system`, also what an untouched
 * profile follows: `defaultTheme="system"` in app/providers.tsx).
 *
 * The dark palette shipped from the start (every token has a `.dark` counterpart, and the chart
 * steps were validated against the dark surface); the provider lives in app/providers.tsx and this is
 * the control. It used to be one Dark mode switch, which had no way back to following the computer
 * once touched; three choices state all three.
 */
const subscribeToNothing = () => () => {};

const THEMES = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "Like my computer" },
] as const;
type Theme = (typeof THEMES)[number]["value"];

function isTheme(value: string | undefined): value is Theme {
  return THEMES.some((theme) => theme.value === value);
}

export function AppearanceSection() {
  const { theme, setTheme } = useTheme();
  const labelId = useId();
  const hintId = useId();

  // `theme` is unknowable on the server, so showing the real choice during hydration would flip it
  // under the user: nothing is pressed until hydrated. This is the "have I hydrated yet" primitive;
  // the usual `useEffect(() => setMounted(true))` sets state synchronously in an effect, which
  // cascades a render and this repo's lint rejects.
  const mounted = useSyncExternalStore(
    subscribeToNothing,
    () => true,
    () => false,
  );

  return (
    // Not a SettingCard: there is nothing to fetch, so it has no loading or
    // error state to share. It writes to next-themes, never to the API.
    <Card id="appearance">
      <CardHeader>
        <CardTitle role="heading" aria-level={2}>
          Appearance
        </CardTitle>
      </CardHeader>
      <CardContent className="@container/setting">
        <div className="grid gap-1.5">
          <Label id={labelId}>Theme</Label>
          <SegmentedChoice
            labelledBy={labelId}
            describedBy={hintId}
            value={mounted && isTheme(theme) ? theme : undefined}
            options={THEMES}
            onChange={setTheme}
          />
          <p id={hintId} className="text-muted-foreground text-body-small">
            Reduced motion follows your computer too.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
