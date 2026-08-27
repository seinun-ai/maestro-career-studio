"use client";

import { useId, useSyncExternalStore } from "react";
import { useTheme } from "next-themes";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

/**
 * Appearance settings.
 *
 * The dark palette shipped from the start — every token has a `.dark`
 * counterpart and the six chart steps were separately validated against the
 * dark surface — but nothing ever mounted a ThemeProvider, so nothing set the
 * `.dark` class and no user could reach any of it. `sonner.tsx` was already
 * calling useTheme() into the void. The provider now lives in app/providers.tsx;
 * this is the control.
 *
 * A switch rather than a light/dark/system cycle, because a switch is how this
 * page already states every other boolean (the quick-tailor knobs) and a
 * three-way cycle hides its states behind clicks. The cost is no explicit way
 * back to "follow the OS" once touched — acceptable here: `defaultTheme
 * ="system"` still governs an untouched profile, and this is a single-user
 * local app.
 */
const subscribeToNothing = () => () => {};

export function AppearanceSection() {
  const { resolvedTheme, setTheme } = useTheme();
  const id = useId();

  // `resolvedTheme` is unknowable on the server, so rendering the real checked
  // state during hydration would flip the switch under the user. This is the
  // "have I hydrated yet" primitive; the usual `useEffect(() =>
  // setMounted(true))` does the same job but sets state synchronously in an
  // effect, which cascades a render and this repo's lint rejects.
  const mounted = useSyncExternalStore(
    subscribeToNothing,
    () => true,
    () => false,
  );
  const isDark = mounted && resolvedTheme === "dark";

  return (
    // Not a SettingCard: there is nothing to fetch, so it has no loading or
    // error state to share. It writes to next-themes, never to the API.
    <Card id="appearance">
      <CardHeader>
        <CardTitle>Appearance</CardTitle>
        <CardDescription>
          Defaults to your system setting until you choose here.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {/* Same row geometry as the quick-tailor and agent-hint switches. */}
        <div className="flex items-center justify-between gap-4 px-3 py-2.5">
          <Label htmlFor={id} className="text-sm">
            Dark mode
          </Label>
          <Switch
            id={id}
            checked={isDark}
            disabled={!mounted}
            onCheckedChange={(next) => setTheme(next ? "dark" : "light")}
          />
        </div>
      </CardContent>
    </Card>
  );
}
