"use client";

import {
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type Ref,
} from "react";

import { useConfirm } from "@/components/confirm-dialog";
import { JsonEditor } from "@/components/json-editor";
import { Button } from "@/components/ui/button";
import { jsonErrorWords, schemaIssuesWords } from "@/lib/describe-edit";
import { resumeDataSchema } from "@/lib/resume-schema";
import { jsonDraftDiffers } from "@/lib/studio";
import type { ResumeData } from "@/lib/types";

export type RawJsonHandle = {
  /** Save's first step: the applied resume; null when invalid (the pane shows why); undefined when there is no draft. */
  commit: () => ResumeData | null | undefined;
};

/**
 * A studio's view of its raw-JSON pane. Typed JSON is an unsaved edit like any
 * other, so the pane reports it (`pending`), and Save commits it first, the way
 * the shortcut blurs a chip input to commit its draft. Shared here so the two
 * studios stay clone-free.
 */
export function useRawJsonDraft() {
  const ref = useRef<RawJsonHandle>(null);
  const [pending, setPending] = useState(false);
  /** Commit a pending draft into `apply`, then run `next`. An invalid draft runs neither. */
  const commitThen = (
    apply: (d: ResumeData) => void,
    next: (d: ResumeData | undefined) => void,
  ) => {
    const committed = ref.current?.commit();
    if (committed === null) return;
    if (committed) apply(committed);
    next(committed);
  };
  return { pending, bind: { ref, onPendingChange: setPending }, commitThen };
}

export function RawJsonToggle({
  value,
  onChange,
  onClose,
  onPendingChange,
  exitFocus,
  ref,
}: {
  value: ResumeData;
  onChange: (next: ResumeData) => void;
  onClose: () => void;
  /** Whether typed JSON differs from `value`: the studio counts it as unsaved. */
  onPendingChange: (pending: boolean) => void;
  /**
   * Where focus goes once a confirmed discard closes the pane: its Cancel is
   * gone by the time the confirm closes. (Apply and an unconfirmed Cancel close
   * straight away, and the studio moves focus itself.)
   */
  exitFocus?: () => HTMLElement | null;
  ref?: Ref<RawJsonHandle>;
}) {
  const confirm = useConfirm();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);
  // A value that changes under an untouched pane (a save's normalized copy)
  // re-syncs the text. Compared with the PREVIOUS value: the normalized copy
  // can differ in shape from what was typed, and comparing with the new one
  // would lock the pane into "pending".
  const [shown, setShown] = useState(value);
  if (value !== shown) {
    setShown(value);
    if (!jsonDraftDiffers(text, shown)) setText(JSON.stringify(value, null, 2));
  }
  const pending = useMemo(() => jsonDraftDiffers(text, value), [text, value]);
  useEffect(() => {
    onPendingChange(pending);
  }, [pending, onPendingChange]);
  // Closing the pane clears it.
  useEffect(() => () => onPendingChange(false), [onPendingChange]);

  const parse = (): ResumeData | null => {
    try {
      const result = resumeDataSchema.safeParse(JSON.parse(text));
      if (!result.success) {
        // Fields by the labels the editors show, never `contact.email`.
        setError(schemaIssuesWords(result.error.issues));
        return null;
      }
      setError(null);
      return result.data as ResumeData;
    } catch (e) {
      // The parser's own words ("Expected ',' or '}' after property value in
      // JSON at position 11") become the line to look at.
      setError(jsonErrorWords(text, e));
      return null;
    }
  };

  const apply = () => {
    const next = parse();
    if (next) {
      onChange(next);
      onClose();
    }
  };

  // An error describes a draft. Text edited back to the form's copy has none,
  // so the alert must not keep reporting a parse failure that no longer exists.
  const edit = (next: string) => {
    setText(next);
    if (!jsonDraftDiffers(next, value)) setError(null);
  };

  useImperativeHandle(ref, () => ({
    commit: () => {
      if (!pending) {
        setError(null);
        return undefined;
      }
      const next = parse();
      if (next) setText(JSON.stringify(next, null, 2));
      return next;
    },
  }));

  // The pane's only discard gesture, so it asks. "Back to form" applies instead.
  const cancel = async () => {
    if (
      pending &&
      !(await confirm({
        title: "Discard your code edits?",
        description: "Your changes haven't been applied yet. You can't get them back.",
        confirmLabel: "Discard",
        destructive: true,
        // Kept: back to Cancel. Discarded: the pane is gone.
        returnFocus: () =>
          cancelRef.current?.isConnected ? cancelRef.current : (exitFocus?.() ?? null),
      }))
    )
      return;
    onClose();
  };

  return (
    <div className="space-y-3">
      <JsonEditor value={text} onChange={edit} />
      {error && (
        <pre
          role="alert"
          className="text-destructive rounded-md bg-destructive/10 p-2 text-xs whitespace-pre-wrap"
        >
          {error}
        </pre>
      )}
      <div className="flex gap-2">
        <Button onClick={apply}>Apply</Button>
        <Button ref={cancelRef} variant="outline" onClick={cancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
