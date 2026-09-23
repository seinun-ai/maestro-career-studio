"use client";

import { useCallback, useEffect, useRef, type KeyboardEvent } from "react";

import { useConfirm } from "@/components/confirm-dialog";
import { focusIfDropped } from "@/hooks/use-focus-return";

/** Ask before throwing typed text away; true at once when nothing changed. The one copy of the question. */
export function useConfirmDiscard() {
  const confirm = useConfirm();
  return useCallback(
    (changed: boolean) =>
      changed
        ? confirm({
            title: "Discard your changes?",
            description: "What you typed here will be lost.",
            confirmLabel: "Discard",
            cancelLabel: "Keep editing",
            destructive: true,
          })
        : Promise.resolve(true),
    [confirm],
  );
}

/**
 * Focus back to the Edit button (`editRef`) when a local editor closes:
 * closing unmounts the pressed control, and focus would fall to <body>.
 * `returnFocus()` arms it before a save, whose close lands later (a failed
 * save keeps the editor open and the flag waits for the next close). By then
 * the user may have moved on, so a save's close moves focus only when it fell
 * to <body> (it does when it was inside the closing editor).
 * `returnFocus("always")` is for a Discard: focus then sits in the closing
 * confirm, not on <body>, so an "only when dropped" check would miss it.
 */
export function useEditorFocusReturn(editing: boolean) {
  const editRef = useRef<HTMLButtonElement>(null);
  const armed = useRef<"if-dropped" | "always" | null>(null);
  useEffect(() => {
    if (editing || !armed.current) return;
    const always = armed.current === "always";
    armed.current = null;
    if (always) editRef.current?.focus();
    else focusIfDropped(editRef.current);
  }, [editing]);
  const returnFocus = useCallback((when: "if-dropped" | "always" = "if-dropped") => {
    armed.current = when;
  }, []);
  return { editRef, returnFocus };
}

/**
 * A local Save/Cancel editor (the Career KB's notes, point and inbox-draft
 * editors). Escape (`onKeyDown` on the textarea) and Cancel (`onCancel`) ask
 * when the text `changed`, then `close`: Escape is a reflex key, and it
 * dropped a multi-line edit with no question. Both do nothing while `busy`
 * (a save in flight): a Discard then would close the editor and the save
 * land a moment later with a "saved" toast. "Keep editing" leaves the editor
 * as it was; the dialog returns focus to the textarea. `onSave(save)` runs
 * the save, or closes at once when nothing changed; Save unmounts either way,
 * so it arms the focus return first.
 */
export function useDiscardableEditor({
  editing,
  changed,
  close,
  busy,
}: {
  editing: boolean;
  changed: boolean;
  close: () => void;
  busy: boolean;
}) {
  const confirmDiscard = useConfirmDiscard();
  const { editRef, returnFocus } = useEditorFocusReturn(editing);
  const onCancel = async () => {
    if (busy || !(await confirmDiscard(changed))) return;
    returnFocus("always");
    close();
  };
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    void onCancel();
  };
  const onSave = (save: () => void) => {
    returnFocus();
    if (changed) save();
    else close();
  };
  return { editRef, onCancel, onKeyDown, onSave };
}
