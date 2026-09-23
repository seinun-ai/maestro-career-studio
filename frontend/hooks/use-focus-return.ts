"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

import { finalFocusOn, focusIfDropped, focusReturnPoint, focusTarget } from "@/lib/focus";

// The DOM helpers live in `lib/focus.ts` (node-tested); callers keep importing them from here.
export { focusIfDropped, focusReturnPoint };

/**
 * For a control that unmounts itself (a pencil that becomes its editor, Done, a collapse toggle). Call the
 * returned function in the handler with a ref to what replaces the control. After this component's next
 * commit, focus that fell to <body> moves there; a container ref focuses its first field.
 */
export function useFocusOnNextCommit() {
  const pending = useRef<RefObject<HTMLElement | null> | null>(null);
  // No deps: it runs after every commit of this component and does nothing unless a handler armed it.
  useEffect(() => {
    const target = pending.current;
    if (!target) return;
    pending.current = null;
    if (target.current) focusIfDropped(focusTarget(target.current));
  });
  return useCallback((target: RefObject<HTMLElement | null>) => {
    pending.current = target;
  }, []);
}

/**
 * For a subtree that can vanish while it holds focus (an error state that recovers, an editor a remount
 * replaces): focus moves to `focusReturnPoint(root)`.
 */
export function useFocusHandoff(ref: RefObject<HTMLElement | null>) {
  // A LAYOUT cleanup: React runs it before it detaches the subtree, so the focused element is still
  // inside `root` here and its ancestors can still be walked.
  useLayoutEffect(() => {
    const root = ref.current;
    return () => {
      if (!root || !root.contains(document.activeElement)) return;
      const back = focusReturnPoint(root);
      queueMicrotask(() => focusIfDropped(back())); // after the commit: the replacement is in the document
    };
  }, [ref]);
}

/**
 * A read view that swaps for an edit view and back. Each swap unmounts the button that was pressed:
 * opening moves focus to the edit view's first field, and Done moves it back to the pencil. `E` is
 * the edit view's element (a table row edits in a `<tr>`). Destructure the result: the React Compiler
 * lint reads `toggle.editRef` as a ref read during render.
 */
export function useEditToggle<E extends HTMLElement = HTMLDivElement>(initial = false) {
  const [editing, setEditing] = useState(initial);
  const editRef = useRef<E>(null);
  const openerRef = useRef<HTMLButtonElement>(null);
  const focusNext = useFocusOnNextCommit();
  return {
    editing,
    editRef,
    openerRef,
    open: () => {
      setEditing(true);
      focusNext(editRef);
    },
    close: () => {
      setEditing(false);
      focusNext(openerRef);
    },
  };
}

/**
 * `finalFocus` for a dialog that stays mounted while closed (`keepMounted`), read when the dialog OPENS: the
 * element that opened it while still connected, else what `focusReturnPoint` finds. Base UI's default return
 * target is the last element any popup recorded that is still connected, and a kept dialog keeps what a nested
 * popup recorded inside it (the role picker's list records the dialog's first tab) connected but hidden, so
 * every close focused a hidden element: <body>. A LAYOUT effect, because Base UI moves focus into the dialog in
 * a microtask after this commit.
 */
export function useOpenerReturn(open: boolean) {
  const opener = useRef<() => HTMLElement | null>(() => null);
  useLayoutEffect(() => {
    if (open) opener.current = focusReturnPoint(document.activeElement);
  }, [open]);
  return useCallback(() => finalFocusOn(opener.current()), []);
}
