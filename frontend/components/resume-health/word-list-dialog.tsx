"use client";

import { useId, useLayoutEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { focusIfDropped, useOpenerReturn } from "@/hooks/use-focus-return";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { getWording, putWording } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { addWord } from "@/lib/health-report";
import type { WordingRead } from "@/lib/types";

/** The word list's cache: the dialog reads it, Ignore and Save write what the server returned. */
export const WORDING_QUERY_KEY = ["health-wording"] as const;

/** One editable list: its words as removable chips, and an add field that says what is wrong. */
function WordList({
  title,
  hint,
  words,
  onChange,
  disabled,
}: {
  title: string;
  hint: string;
  words: string[];
  onChange: (words: string[]) => void;
  disabled: boolean;
}) {
  const hintId = useId();
  const errorId = useId();
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // A removed word takes its button with it: after the commit, focus goes to the word now in its
  // place, else the one before it, else the add field. Never to <body>.
  const pendingFocus = useRef<(() => HTMLElement | null) | null>(null);
  useLayoutEffect(() => {
    const next = pendingFocus.current;
    if (!next) return;
    pendingFocus.current = null;
    focusIfDropped(next());
  });

  const add = () => {
    const result = addWord(words, draft);
    if ("error" in result) return setError(result.error);
    onChange(result.list);
    setDraft("");
    setError(null);
  };
  const remove = (at: number) => {
    pendingFocus.current = () => {
      const left = listRef.current?.querySelectorAll<HTMLButtonElement>("button[data-remove]");
      return left?.[at] ?? left?.[at - 1] ?? inputRef.current;
    };
    onChange(words.filter((_, i) => i !== at));
    setError(null);
  };

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">
        {title} ({words.length})
      </legend>
      <p id={hintId} className="text-muted-foreground text-xs">
        {hint}
      </p>
      {words.length > 0 ? (
        <ul ref={listRef} className="flex flex-wrap gap-1.5">
          {words.map((word, i) => (
            <li
              key={word}
              className="bg-muted text-foreground inline-flex max-w-full items-center gap-1 rounded-md px-2 py-0.5 text-sm"
            >
              <span className="min-w-0 break-words">{word}</span>
              <button
                type="button"
                data-remove
                aria-label={`Remove ${word}`}
                disabled={disabled}
                className="text-muted-foreground hover:text-foreground relative -mr-0.5 rounded-sm after:absolute after:-inset-2 after:content-['']"
                onClick={() => remove(i)}
              >
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-xs">No words yet.</p>
      )}
      <div className="flex max-w-sm items-start gap-2">
        <Input
          ref={inputRef}
          value={draft}
          aria-label={`Add to ${title}`}
          aria-describedby={error ? `${hintId} ${errorId}` : hintId}
          aria-invalid={error ? true : undefined}
          readOnly={disabled}
          onChange={(e) => {
            setDraft(e.target.value);
            if (error) setError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <Button size="sm" variant="outline" disabled={disabled} onClick={add}>
          Add
        </Button>
      </div>
      {error && (
        <p id={errorId} role="alert" className="text-destructive text-xs">
          {error}
        </p>
      )}
    </fieldset>
  );
}

/** The dialog's editable copy of the lists, made when it opens: Cancel (or Esc) drops it. */
function WordListForm({
  wording,
  onClose,
  onSaved,
}: {
  wording: WordingRead;
  onClose: () => void;
  onSaved: () => void;
}) {
  const qc = useQueryClient();
  const [cliche, setCliche] = useState(wording.cliche);
  const [filler, setFiller] = useState(wording.filler);
  const [ignored, setIgnored] = useState(wording.ignored);
  const [failure, setFailure] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => putWording({ cliche, filler, ignored }),
    onMutate: () => setFailure(null),
    onSuccess: (saved) => {
      qc.setQueryData(WORDING_QUERY_KEY, saved);
      toast.success("Word list saved");
      onClose();
      // After the dialog has gone: the report runs again against the new lists.
      onSaved();
    },
    onError: (err: Error) => setFailure(couldnt("save the word list", err)),
  });
  // One Save per gesture: a double click sent the PUT twice.
  const saveOnce = useSingleFlight(save.mutate);
  const busy = save.isPending;

  return (
    <>
      <div className="grid gap-6">
        <WordList
          title="Clichés"
          hint="Words that claim a trait without showing it."
          words={cliche}
          onChange={setCliche}
          disabled={busy}
        />
        <WordList
          title="Filler words"
          hint="Words that make a line longer and say nothing."
          words={filler}
          onChange={setFiller}
          disabled={busy}
        />
        <div className="flex flex-wrap items-center gap-2">
          {/* No confirm: a word it drops can be added back before Save, and Cancel drops it all. */}
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => {
              setCliche(wording.defaults.cliche);
              setFiller(wording.defaults.filler);
            }}
          >
            Reset to defaults
          </Button>
          <p className="text-muted-foreground text-xs">Puts back the default clichés and filler words.</p>
        </div>
        <WordList
          title="Never flag"
          hint="Never flagged, even when it's on a list above or looks like a slip."
          words={ignored}
          onChange={setIgnored}
          disabled={busy}
        />
      </div>
      {failure && (
        <p role="alert" className="text-destructive text-sm">
          {failure}
        </p>
      )}
      <DialogFooter>
        <Button size="sm" variant="ghost" disabled={busy} onClick={onClose}>
          Cancel
        </Button>
        <Button
          size="sm"
          disabled={busy}
          // Disables itself while saving: a native `disabled` drops focus.
          focusableWhenDisabled
          className="data-disabled:pointer-events-none data-disabled:opacity-50"
          onClick={() => saveOnce()}
        >
          {busy ? "Saving…" : "Save"}
        </Button>
      </DialogFooter>
    </>
  );
}

/**
 * Edit word list: the clichés and filler words the check flags, and the Never flag list. Save sends
 * all three and runs the report again (`onSaved`); Cancel discards.
 */
export function WordListDialog({
  open,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const wording = useQuery({
    queryKey: WORDING_QUERY_KEY,
    queryFn: getWording,
    enabled: open,
    refetchOnWindowFocus: false,
  });
  const close = () => onOpenChange(false);
  // Back to Edit word list, or, when a re-run took the Wording group away, what survived it.
  const returnToOpener = useOpenerReturn(open);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" finalFocus={returnToOpener}>
        <DialogHeader>
          <DialogTitle>Edit word list</DialogTitle>
          <DialogDescription>
            The check flags these in your summary and bullets. They never change your score.
          </DialogDescription>
        </DialogHeader>
        {wording.data ? (
          <WordListForm wording={wording.data} onClose={close} onSaved={onSaved} />
        ) : (
          <>
            {wording.isError ? (
              <p role="alert" className="text-destructive text-sm">
                {couldnt("load your word list", wording.error)}
              </p>
            ) : (
              <p className="text-muted-foreground text-sm">Loading…</p>
            )}
            <DialogFooter>
              <Button size="sm" variant="ghost" onClick={close}>
                Cancel
              </Button>
              {wording.isError && (
                <Button size="sm" variant="outline" onClick={() => void wording.refetch()}>
                  Try again
                </Button>
              )}
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
