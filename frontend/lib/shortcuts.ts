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

type KeyLike = {
  key: string;
  code?: string;
  metaKey: boolean;
  ctrlKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
};

/**
 * Cmd/Ctrl+S exactly. Shift is "Save As" elsewhere; Alt is someone else's.
 *
 * The letter decides, and the key's position (`code`) is the fallback only
 * when the layout types no Latin letter there: a Russian layout reports "ы"
 * for that key, but Colemak's "r" and Dvorak's "o" sit on the same position,
 * and their Cmd+R and Cmd+O must stay reload and open. The modifier checks
 * run first, so a synthetic keydown with no `key` (autofill dispatches them)
 * never reaches `toLowerCase`.
 */
export function isSaveShortcut(e: KeyLike): boolean {
  return (
    (e.metaKey || e.ctrlKey) &&
    !e.altKey &&
    !e.shiftKey &&
    (e.key.toLowerCase() === "s" || (e.code === "KeyS" && !/^[a-z]$/i.test(e.key)))
  );
}

type ChordLike = { defaultPrevented: boolean; repeat: boolean; isComposing: boolean };

/**
 * Whether a save chord should save: not claimed by another handler first, not a held key's repeat (one
 * press, one save), not mid-IME composition (the chord belongs to the input method).
 */
export function isLiveSaveChord(e: ChordLike): boolean {
  return !e.defaultPrevented && !e.repeat && !e.isComposing;
}
