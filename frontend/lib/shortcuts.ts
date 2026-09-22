/** Keyboard-shortcut helpers. Pure (no DOM, no React) so `node --test` runs them. */

export type ModKey = "⌘" | "Ctrl";

/** Apple platforms use Command; everything else Control. */
export function modKeyFor(platform: string): ModKey {
  return /Mac|iPhone|iPad|iPod/i.test(platform) ? "⌘" : "Ctrl";
}

/** "⌘S" on Apple platforms, "Ctrl+S" elsewhere: each platform's own spelling. */
export function shortcutLabel(mod: ModKey, key: string): string {
  const k = key.toUpperCase();
  return mod === "⌘" ? `⌘${k}` : `Ctrl+${k}`;
}
