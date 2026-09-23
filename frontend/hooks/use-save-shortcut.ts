"use client";

import { useEffect, useEffectEvent } from "react";
import { flushSync } from "react-dom";

import { focusIfDropped, focusReturnPoint } from "@/hooks/use-focus-return";
import { isSaveShortcut } from "@/lib/shortcuts";

const DIALOG = '[role="dialog"], [role="alertdialog"]';

/** A field that can hold a draft only its blur commits. */
function holdsDraft(el: Element | null): el is HTMLElement {
  return (
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement ||
    (el instanceof HTMLElement && el.isContentEditable)
  );
}

/**
 * Cmd/Ctrl+S saves the studio. The browser's own "Save page" dialog is
 * suppressed while a studio is mounted: it saves the app's HTML, never what
 * someone editing a resume meant. `canSave` mirrors the Save button's
 * disabled state, so the key and the button always agree.
 *
 * The chord is always swallowed, but it saves only from the studio itself:
 * not on key repeat, not mid-IME composition, not when another handler has
 * already claimed it, and never from inside a dialog. In "Load the latest
 * version?" a save would write over the newer copy the dialog is asking about.
 *
 * Clicking Save blurs the focused field first, and some fields (a chip
 * input's pending text, a section rename) commit only on blur. The key does
 * the same, so it never saves less than the button would: it blurs inside
 * `flushSync`, which commits that draft (and updates `save`) before it
 * returns, then puts focus back and saves, all before the handler returns.
 * Keys typed right after the chord are queued behind it, so they land in the
 * field; a refocus on the next task let them fall on <body> and be lost. A
 * field that unmounts on blur (an inline chip edit, a rename, the title)
 * moves focus itself in that same commit; otherwise it goes back to the
 * field, or the nearest container that survived it.
 */
export function useSaveShortcut(onSave: () => void, canSave: boolean) {
  const save = useEffectEvent(() => {
    if (canSave) onSave();
  });
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!isSaveShortcut(event)) return;
      const claimed = event.defaultPrevented;
      event.preventDefault();
      if (claimed || event.repeat || event.isComposing) return;
      if (event.target instanceof Element && event.target.closest(DIALOG)) return;

      const field = document.activeElement;
      if (!holdsDraft(field)) {
        save();
        return;
      }
      const back = focusReturnPoint(field);
      flushSync(() => field.blur());
      focusIfDropped(back());
      save();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
