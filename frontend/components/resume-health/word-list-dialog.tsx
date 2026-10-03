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
import { addWord, withDraft } from "@/lib/health-report";
import type { WordingBody, WordingRead } from "@/lib/types";

/** The word list's cache: the dialog reads it, Ignore and Save write what the server returned. */
export const WORDING_QUERY_KEY = ["health-wording"] as const;

type ListKey = keyof WordingBody;
const LISTS: ListKey[] = ["cliche", "filler", "ignored"];
const NO_TEXT: Record<ListKey, string> = { cliche: "", filler: "", ignored: "" };
const NO_ERRORS: Record<ListKey, string | null> = { cliche: null, filler: null, ignored: null };

/**
 * One editable list: its words as removable chips, and an add field that says what is wrong. The
 * field's text and error live in the form, so Save can commit a word typed but not yet added.
 */
function WordList({
  title,
  hint,
  words,
  onChange,
  draft,
  onDraftChange,
  error,
  onError,
  disabled,
}: {
  title: string;
  hint: string;
  words: string[];
  onChange: (words: string[]) => void;
  draft: string;
  onDraftChange: (draft: string) => void;
  error: string | null;
  onError: (error: string | null) => void;
  disabled: boolean;
}) {
  const hintId = useId();
  const errorId = useId();
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
    if ("error" in result) return onError(result.error);
    onChange(result.list);
    onDraftChange("");
    onError(null);
  };
  const remove = (at: number) => {
    pendingFocus.current = () => {
      const left = listRef.current?.querySelectorAll<HTMLButtonElement>("button[data-remove]");
      return left?.[at] ?? left?.[at - 1] ?? inputRef.current;
    };
    onChange(words.filter((_, i) => i !== at));
    onError(null);
  };

  return (
    <fieldset className="space-y-2">
      <legend className="text-title-small">
        {title} ({words.length})
      </legend>
      <p id={hintId} className="text-muted-foreground text-body-small">
        {hint}
      </p>
      {words.length > 0 ? (
        <ul ref={listRef} className="flex flex-wrap gap-1.5">
          {words.map((word, i) => (
            <li
              key={word}
              className="bg-muted text-foreground inline-flex max-w-full items-center gap-1 rounded-full px-2 py-0.5 text-body-medium"
            >
              <span className="min-w-0 break-words">{word}</span>
              <button
                type="button"
                data-remove
                aria-label={`Remove ${word}`}
                disabled={disabled}
                className="text-muted-foreground hover:text-foreground relative -mr-0.5 rounded-full after:absolute after:-inset-2 after:content-['']"
                onClick={() => remove(i)}
              >
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-body-small">No words yet.</p>
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
            onDraftChange(e.target.value);
            if (error) onError(null);
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
        <p id={errorId} role="alert" className="text-destructive text-body-small">
          {error}
        </p>
      )}
    </fieldset>
  );
}

/** The dialog's editable copy of the lists, made when it opens: Cancel (or Esc) drops it. */
function WordListForm({
  wording,
  busy: groupBusy,
  onClose,
  onSaved,
}: {
  wording: WordingRead;
  busy: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const qc = useQueryClient();
  const [lists, setLists] = useState<WordingBody>({
    cliche: wording.cliche,
    filler: wording.filler,
    ignored: wording.ignored,
  });
  const [drafts, setDrafts] = useState(NO_TEXT);
  const [errors, setErrors] = useState(NO_ERRORS);
  const [failure, setFailure] = useState<string | null>(null);
  const setList = (key: ListKey) => (words: string[]) => setLists((l) => ({ ...l, [key]: words }));

  const save = useMutation({
    mutationFn: (body: WordingBody) => putWording(body),
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
  const busy = save.isPending || groupBusy;

  // A word typed but not added goes in with the Save; one that can't be added stops the Save and
  // says why beside its field.
  const submit = () => {
    const body = { ...lists };
    const found = { ...NO_ERRORS };
    for (const key of LISTS) {
      const result = withDraft(lists[key], drafts[key]);
      if ("error" in result) found[key] = result.error;
      else body[key] = result.list;
    }
    if (LISTS.some((key) => found[key])) return setErrors(found);
    setLists(body);
    setDrafts(NO_TEXT);
    setErrors(NO_ERRORS);
    saveOnce(body);
  };

  const listProps = (key: ListKey) => ({
    words: lists[key],
    onChange: setList(key),
    draft: drafts[key],
    onDraftChange: (text: string) => setDrafts((d) => ({ ...d, [key]: text })),
    error: errors[key],
    onError: (error: string | null) => setErrors((e) => ({ ...e, [key]: error })),
    disabled: busy,
  });

  return (
    <>
      <div className="grid gap-6">
        <WordList title="Clichés" hint="Words that claim a trait without showing it." {...listProps("cliche")} />
        <WordList
          title="Filler words"
          hint="Words that make a line longer and say nothing."
          {...listProps("filler")}
        />
        <div className="flex flex-wrap items-center gap-2">
          {/* No confirm: a word it drops can be added back before Save, and Cancel drops it all. */}
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() =>
              setLists((l) => ({ ...l, cliche: wording.defaults.cliche, filler: wording.defaults.filler }))
            }
          >
            Reset to defaults
          </Button>
          <p className="text-muted-foreground text-body-small">Puts back the default clichés and filler words.</p>
        </div>
        <WordList
          title="Never flag"
          hint="Never flagged, even when it's on a list above or looks like a slip."
          {...listProps("ignored")}
        />
      </div>
      {failure && (
        <p role="alert" className="text-destructive text-body-medium">
          {failure}
        </p>
      )}
      <DialogFooter>
        <Button size="sm" variant="ghost" disabled={save.isPending} onClick={onClose}>
          Cancel
        </Button>
        <Button
          size="sm"
          disabled={busy}
          // Disables itself while saving: a native `disabled` drops focus.
          focusableWhenDisabled
          className="data-disabled:pointer-events-none data-disabled:opacity-50"
          onClick={submit}
        >
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      </DialogFooter>
    </>
  );
}

/**
 * Edit word list: the clichés and filler words the check flags, and the Never flag list. Save sends
 * all three and runs the report again (`onSaved`); Cancel discards. `busy`: an Ignore is still
 * saving and re-running, so Save waits for it.
 */
export function WordListDialog({
  open,
  onOpenChange,
  busy,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  busy: boolean;
  onSaved: () => void;
}) {
  const wording = useQuery({
    queryKey: WORDING_QUERY_KEY,
    queryFn: getWording,
    enabled: open,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const close = () => onOpenChange(false);
  // Back to Edit word list, or, when a re-run took the Wording group away, what survived it.
  const returnToOpener = useOpenerReturn(open);
  // The form copies the lists once, when it mounts: never from a cached copy the refetch on open
  // is about to replace, or Save would write the stale lists back.
  const ready = wording.data != null && !wording.isFetching;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" finalFocus={returnToOpener}>
        <DialogHeader>
          <DialogTitle>Edit word list</DialogTitle>
          <DialogDescription>
            The check flags these in your summary and bullets. They never change your score.
          </DialogDescription>
        </DialogHeader>
        {ready ? (
          <WordListForm wording={wording.data!} busy={busy} onClose={close} onSaved={onSaved} />
        ) : (
          <>
            {wording.isError && !wording.isFetching ? (
              <p role="alert" className="text-destructive text-body-medium">
                {couldnt("load your word list", wording.error)}
              </p>
            ) : (
              <p className="text-muted-foreground text-body-medium">Loading…</p>
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
