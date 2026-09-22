"use client";

import { useEffect, useRef } from "react";

import { isSaveShortcut } from "@/lib/shortcuts";

/**
 * Cmd/Ctrl+S saves the studio. The browser's own "Save page" dialog is
 * suppressed while a studio is mounted: it saves the app's HTML, never what
 * someone editing a resume meant. `canSave` mirrors the Save button's
 * disabled state, so the key and the button always agree.
 */
export function useSaveShortcut(onSave: () => void, canSave: boolean) {
  const latest = useRef({ onSave, canSave });
  useEffect(() => {
    latest.current = { onSave, canSave };
  });
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!isSaveShortcut(event)) return;
      event.preventDefault();
      if (latest.current.canSave) latest.current.onSave();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
