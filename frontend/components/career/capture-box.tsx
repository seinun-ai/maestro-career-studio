"use client";

import { DragEvent, FormEvent, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { FileUp, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { kbCapture, kbIngestDocument } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DOCUMENT_ACCEPT } from "@/lib/upload-accept";

const ACCEPT = DOCUMENT_ACCEPT;

export function CaptureBox() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [text, setText] = useState("");
  const [dragging, setDragging] = useState(false);
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
        `${count} ${count === 1 ? "point" : "points"} added to inbox for ${result.entity_title}`,
      );
      setText("");
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const ingest = useMutation({
    mutationFn: (file: File) => kbIngestDocument(file),
    onSuccess: (result) => {
      const points =
        result.point_count === 0
          ? "document attached"
          : result.point_count === 1
            ? "1 point to review"
            : `${result.point_count} points to review`;
      toast.success(
        `${result.created_entity ? "Created" : "Matched"} “${result.entity_title}” (${result.entity_kind}) · ${points}`,
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
    onError: (error: Error) => toast.error(error.message),
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

  const isFileDrag = (event: DragEvent) =>
    Array.from(event.dataTransfer?.types ?? []).includes("Files");

  const onDrop = (event: DragEvent) => {
    // Only claim FILE drags: preventDefault on a text drag would cancel the
    // browser's default drop-into-textarea behavior.
    if (!isFileDrag(event)) return;
    event.preventDefault();
    setDragging(false);
    const files = event.dataTransfer.files;
    if (files.length > 1) toast.info("Using the first file only.");
    onPickFile(files?.[0]);
  };

  return (
    <Card
      className={cn(
        "border-0 bg-primary/5 shadow-none ring-0 transition-shadow duration-150",
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
      <CardHeader className="pb-1">
        <CardTitle className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-full bg-primary/10">
            <Sparkles className="text-primary size-4" aria-hidden="true" />
          </span>
          Quick capture
        </CardTitle>
        <p className="text-muted-foreground text-sm">
          Type a recent win, or drop a certification or project doc and let
          it fill itself in.
        </p>
      </CardHeader>
      <CardContent>
        <form className="space-y-3" onSubmit={submit}>
          <Label htmlFor="career-capture" className="sr-only">
            Career update
          </Label>
          <Textarea
            id="career-capture"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="e.g. This week I shipped…"
            rows={4}
            readOnly={capture.isPending}
            aria-describedby="career-capture-help"
            className="rounded-2xl border-0 bg-background/90 px-4 py-3 shadow-sm ring-1 ring-foreground/10 transition-shadow focus-visible:ring-ring"
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
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p id="career-capture-help" className="text-muted-foreground text-xs">
              Nothing is published to a resume until you approve it.
            </p>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                // Focusable while it reads, as Add to inbox is while it captures.
                className="text-muted-foreground rounded-full data-disabled:pointer-events-none data-disabled:opacity-50"
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
                {ingest.isPending ? "Reading document…" : "From document"}
              </Button>
              <Button
                // Stays focusable while it captures: a disabled button that
                // has focus drops it to the page.
                className="rounded-full px-4 data-disabled:pointer-events-none data-disabled:opacity-50"
                type="submit"
                disabled={!text.trim() || capture.isPending}
                focusableWhenDisabled
              >
                {capture.isPending ? "Capturing…" : "Add to inbox"}
              </Button>
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
