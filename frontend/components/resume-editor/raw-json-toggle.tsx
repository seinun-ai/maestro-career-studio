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
  ref,
}: {
  value: ResumeData;
  onChange: (next: ResumeData) => void;
  onClose: () => void;
  /** Whether typed JSON differs from `value`: the studio counts it as unsaved. */
  onPendingChange: (pending: boolean) => void;
  ref?: Ref<RawJsonHandle>;
}) {
  const confirm = useConfirm();
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
        setError(result.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("\n"));
        return null;
      }
      setError(null);
      return result.data as ResumeData;
    } catch (e) {
      setError((e as Error).message);
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

  useImperativeHandle(ref, () => ({
    commit: () => {
      if (!pending) return undefined;
      const next = parse();
      if (next) setText(JSON.stringify(next, null, 2));
      return next;
    },
  }));

  // The only discard gesture, so it asks. "Form view" applies instead.
  const cancel = async () => {
    if (
      pending &&
      !(await confirm({
        title: "Discard your JSON edits?",
        description: "The JSON you typed has not been applied. This can't be undone.",
        confirmLabel: "Discard",
        destructive: true,
      }))
    )
      return;
    onClose();
  };

  return (
    <div className="space-y-3">
      <JsonEditor value={text} onChange={setText} />
      {error && (
        <pre
          role="alert"
          className="text-destructive rounded-md bg-destructive/10 p-2 text-xs whitespace-pre-wrap"
        >
          {error}
        </pre>
      )}
      <div className="flex gap-2">
        <Button onClick={apply}>Apply JSON</Button>
        <Button variant="outline" onClick={cancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
