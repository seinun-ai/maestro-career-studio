"use client";

import { DragEvent, FormEvent, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { FileUp, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { kbCapture, kbIngestDocument } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { cn } from "@/lib/utils";
import { DOCUMENT_ACCEPT } from "@/lib/upload-accept";

const ACCEPT = DOCUMENT_ACCEPT;

export function CaptureBox() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [text, setText] = useState("");
  const [dragging, setDragging] = useState(false);
  // One line at rest, the full box while in use: the box sat open above the career history on every
  // visit and pushed it below the fold. It stays open while anything is typed, sending or reading, and
  // while a file is dragged over it; it folds when focus leaves an empty box.
  const [focused, setFocused] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["kb", "drafts"] });
    void queryClient.invalidateQueries({ queryKey: ["kb", "entities"] });
  };

  const capture = useMutation({
    mutationFn: (value: string) => kbCapture({ text: value }),
    onSuccess: (result) => {
      const count = result.point_ids.length;
      toast.success(
        `${count} draft ${count === 1 ? "bullet" : "bullets"} added to ${result.entity_title}`,
      );
      setText("");
      invalidate();
    },
    onError: (error: Error) => toast.error(couldnt("save your update", error)),
  });

  const ingest = useMutation({
    mutationFn: (file: File) => kbIngestDocument(file),
    onSuccess: (result) => {
      // One sentence whether the item is new or matched: "Matched" and the
      // raw kind were the pipeline's words, not the user's.
      const n = result.point_count;
      toast.success(
        n === 0
          ? `Document attached to ${result.entity_title}.`
          : `Added to ${result.entity_title}. ${n} ${n === 1 ? "bullet" : "bullets"} to review.`,
        {
          action: {
            label: "View",
            onClick: () => router.push(`/career/${result.entity_id}`),
          },
        },
      );
      invalidate();
      // A matched existing entity's detail page may be cached.
      void queryClient.invalidateQueries({
        queryKey: ["kb", "entity", result.entity_id],
      });
    },
    onError: (error: Error) => toast.error(couldnt("read the document", error)),
  });

  // One request per click: a double click read isPending === false twice and
  // ran two extractions, two sets of draft points.
  const captureOnce = useSingleFlight(capture.mutate);
  const ingestOnce = useSingleFlight(ingest.mutate);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = text.trim();
    if (value) captureOnce(value);
  };

  const onPickFile = (file: File | undefined) => {
    if (!file) return;
    if (ingest.isPending) {
      toast.info("Still reading the previous document. Try again in a moment.");
      return;
    }
    ingestOnce(file);
  };

  const open = focused || text !== "" || capture.isPending || ingest.isPending || dragging;

  const isFileDrag = (event: DragEvent) =>
    Array.from(event.dataTransfer?.types ?? []).includes("Files");

  const onDrop = (event: DragEvent) => {
    // Only claim FILE drags: preventDefault on a text drag would cancel the
    // browser's default drop-into-textarea behavior.
    if (!isFileDrag(event)) return;
    event.preventDefault();
    setDragging(false);
    const files = event.dataTransfer.files;
    if (files.length > 1) toast.info("Only one file at a time. Using the first.");
    onPickFile(files?.[0]);
  };

  return (
    <Card
      className={cn(
        "border-0 bg-primary/5 py-3 shadow-none ring-0 transition-shadow duration-150",
        dragging && "ring-2 ring-primary/50",
      )}
      onDragOver={(event) => {
        if (!isFileDrag(event) || ingest.isPending) return;
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(event) => {
        // dragleave bubbles from children; only clear when truly leaving the card.
        if (event.currentTarget.contains(event.relatedTarget as Node)) return;
        setDragging(false);
      }}
      onDrop={onDrop}
    >
      <CardContent>
        {/* One grid for both states: the textarea, the file button and the label keep their DOM places
            (focus stays put) and only their cells change. At rest the three share a row (at 375 the
            textarea takes a row of its own); open, the textarea spans a row and the footer follows. */}
        <form
          className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-3 sm:grid-cols-[auto_minmax(0,1fr)_auto]"
          onSubmit={submit}
          onFocus={() => setFocused(true)}
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false);
          }}
        >
          <Label htmlFor="career-capture" className="col-start-1 row-start-1 flex items-center gap-2 text-label-large whitespace-nowrap">
            <span className="flex size-7 items-center justify-center rounded-full bg-primary/10">
              <Sparkles className="text-primary size-3.5" aria-hidden="true" />
            </span>
            Quick capture
          </Label>
          <Textarea
            id="career-capture"
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={open ? 4 : 1}
            readOnly={capture.isPending}
            aria-describedby="career-capture-help"
            className={cn(
              "col-span-2 row-start-2 rounded-2xl border-0 bg-background/90 px-4 shadow-sm ring-1 ring-foreground/10 transition-shadow focus-visible:ring-ring",
              open
                ? "min-h-24 py-3 sm:col-span-3"
                : "min-h-9 resize-none py-1.5 sm:col-span-1 sm:col-start-2 sm:row-start-1",
            )}
          />
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(event) => {
              onPickFile(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            // Focusable while it reads, as Add to drafts is while it captures.
            className="text-muted-foreground col-start-2 row-start-1 justify-self-end rounded-full data-disabled:pointer-events-none data-disabled:opacity-50 sm:col-start-3"
            disabled={ingest.isPending}
            focusableWhenDisabled
            // One picker per gesture: a double click's second click
            // (detail 2) opened a second one.
            onClick={(event) => {
              if (event.detail > 1) return;
              fileInputRef.current?.click();
            }}
          >
            {ingest.isPending ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <FileUp aria-hidden="true" />
            )}
            {ingest.isPending ? "Reading document…" : "Add document"}
          </Button>
          {/* The hint stays in the DOM at rest (sr-only), so the textarea's description never dangles. */}
          <div
            className={cn(
              "col-span-2 row-start-3 flex flex-wrap items-center justify-between gap-2 sm:col-span-3",
              !open && "sr-only",
            )}
          >
            <p id="career-capture-help" className="text-muted-foreground text-body-small">
              Type a recent win or add a document. Nothing goes on a resume until you approve it.
            </p>
            {open ? (
              <Button
                // Stays focusable while it captures: a disabled button that
                // has focus drops it to the page.
                className="rounded-full px-4 data-disabled:pointer-events-none data-disabled:opacity-50"
                type="submit"
                disabled={!text.trim() || capture.isPending}
                focusableWhenDisabled
              >
                {capture.isPending ? "Adding…" : "Add to drafts"}
              </Button>
            ) : null}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
