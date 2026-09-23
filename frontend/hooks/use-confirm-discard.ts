"use client";

import { useCallback, useEffect, useRef, type KeyboardEvent } from "react";

import { useConfirm } from "@/components/confirm-dialog";

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
 * A local Save/Cancel editor (the Career KB's notes, point and inbox-draft
 * editors). Escape and Cancel go through `requestCancel`, which asks when the
 * text changed: Escape is a reflex key, and it dropped a multi-line edit with
 * no question. Closing unmounts the pressed control, so focus goes back to the
 * Edit button (`editRef`) instead of falling to <body>. A Save arms that with
 * `returnFocus()` before its request: the editor closes when the save lands,
 * and a failed save keeps it open with the flag waiting for the next close.
 * "Keep editing" leaves the editor as it was; the dialog returns focus to the
 * textarea.
 */
export function useDiscardableEditor(editing: boolean) {
  const confirmDiscard = useConfirmDiscard();
  const editRef = useRef<HTMLButtonElement>(null);
  const refocus = useRef(false);
  useEffect(() => {
    if (editing || !refocus.current) return;
    refocus.current = false;
    editRef.current?.focus();
  }, [editing]);
  const returnFocus = useCallback(() => {
    refocus.current = true;
  }, []);
  const requestCancel = useCallback(
    async (changed: boolean, close: () => void) => {
      if (!(await confirmDiscard(changed))) return;
      refocus.current = true;
      close();
    },
    [confirmDiscard],
  );
  /** From the textarea's keydown: Escape asks the same question as Cancel. */
  const cancelOnEscape = (event: KeyboardEvent, changed: boolean, close: () => void) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    void requestCancel(changed, close);
  };
  return { editRef, returnFocus, requestCancel, cancelOnEscape };
}
