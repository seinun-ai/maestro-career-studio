"use client";

import { useEffect, useEffectEvent } from "react";

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
 * the same: blur, let React commit that draft, then re-focus the field and
 * save, so the key never saves less than the button would.
 */
export function useSaveShortcut(onSave: () => void, canSave: boolean) {
  const save = useEffectEvent(() => {
    if (canSave) onSave();
  });
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (!isSaveShortcut(event)) return;
      const claimed = event.defaultPrevented;
      event.preventDefault();
      // A draft commit is pending and will save: a second chord in that gap
      // would find focus on the body and save a second time.
      if (timer !== undefined) return;
      if (claimed || event.repeat || event.isComposing) return;
      if (event.target instanceof Element && event.target.closest(DIALOG)) return;

      const field = document.activeElement;
      if (!holdsDraft(field)) {
        save();
        return;
      }
      field.blur();
      // A blur is a discrete event, so React has committed the draft (and
      // `save` reads the new props) by the next task.
      timer = setTimeout(() => {
        timer = undefined;
        if (field.isConnected) field.focus({ preventScroll: true });
        save();
      }, 0);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      clearTimeout(timer);
    };
  }, []);
}
